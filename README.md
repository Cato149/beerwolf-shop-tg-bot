# Beerwolf commission bot

Telegram-бот и REST API для заявок на комиссии: пайплайн статусов, прогресс GitHub Issues / Milestones / Projects v2, правки заказчика в backlog и тикеты поддержки.

Языки интерфейса: **ru** (по умолчанию) и **en**. Тексты только в `locales/*.ini`.

## Архитектура

DDD + use cases: хендлеры aiogram и роутеры FastAPI тонкие, логика в `src/beerwolf_shop/application`.

```
src/beerwolf_shop/
  config.py                 # Pydantic Settings
  main.py                   # FastAPI: API + webhooks + polling/webhook бота
  domain/                   # сущности, протоколы, исключения
  application/              # use cases + DTO
  infrastructure/
    db/                     # SQLModel, репозитории, Postgres
    github/                 # REST + GraphQL (httpx), GFM → Telegram HTML
    telegram/               # i18n INI, MarkdownV2, клавиатуры
    fsm/                    # FSM aiogram в Postgres (без Redis)
  presentation/
    telegram/handlers/      # маршрутизация бота
    api/                    # REST + Swagger
locales/
tests/
```

Один заказ = одно репо + один Project v2. У клиента может быть только одна комиссия в `discussion`
или `in_progress`. Заявку в статусе `application` можно заменить новой, пока админ не взял её дальше.
Support-заявки — отдельные `Order(type=support)` с
`parent_order_id`; при взятии такой заявки бот создаёт отдельный GitHub milestone и временно возвращает
основной проект в работу.

Клиентская reply-клавиатура зависит от состояния проекта:

- новый клиент видит только создание заявки и смену языка;
- пока заявка в статусе `application` (ещё не взята в обсуждение/работу), кнопка новой заявки остаётся — повторная отправка заменяет предыдущую;
- в `discussion` и `in_progress` доступен «Мой заказ», новой заявки нет;
- во время и после работы доступна рекомендация бота;
- после завершения снова можно создать новую комиссию.

В мастере заявки можно присылать фото (в том числе альбомом); они сохраняются в заявке и уходят админу вместе с карточкой.

Админ-панель показывает счётчики новых / в работе / готовых комиссий. Список заявок — карточки по 5 на страницу, под ними фильтры и пагинация. Спам, очередь поддержки и создание заявки — на reply-клавиатуре админки.

## Запуск

### Локально (uv)

Нужны Python 3.12+, [uv](https://docs.astral.sh/uv/) и Postgres 16 (можно только `db` из Compose).

```bash
cp .env.example .env
# заполните BOT_TOKEN, ADMIN_TELEGRAM_IDS, GITHUB_TOKEN, DATABASE_URL (localhost)

docker compose up -d db
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn beerwolf_shop.main:app --reload --host 0.0.0.0 --port 8000
```

`BOT_MODE=polling` — long polling (удобно для разработки).  
`BOT_MODE=webhook` — Telegram шлёт апдейты на `PUBLIC_BASE_URL/webhooks/telegram`.

Проверка: `GET /health`, документация API: `/docs`.

### Docker Compose

В `.env` для контейнера `DATABASE_URL` должен указывать на хост `db`:

`postgresql+asyncpg://beerwolf:beerwolf@db:5432/beerwolf`

```bash
cp .env.example .env
docker compose up --build
```

Сервисы только `app` и `db`. Переменные не переназначаются в compose — только `env_file: .env`.

Порт приложения опубликован как `127.0.0.1:8000`. Снаружи его должен закрывать reverse proxy на хосте.

### Caddyfile (на хосте, не в репозитории)

Caddy в Compose нет. На сервере в свой `/etc/caddy/Caddyfile` добавьте сайт с `reverse_proxy` на loopback-порт приложения. `PUBLIC_BASE_URL` в `.env` должен совпадать с этим хостом (`https://...`, без `/` на конце), `BOT_MODE=webhook`.

```caddyfile
{
	email you@example.com
}

bot.example.com {
	encode gzip zstd

	reverse_proxy 127.0.0.1:8000 {
		transport http {
			read_timeout 60s
			write_timeout 60s
		}
	}
}
```

Нужны DNS A/AAAA на этот хост и открытые порты 80/443. После `caddy reload` Telegram и GitHub ходят на `https://bot.example.com/webhooks/...`.

### Тесты и линт

```bash
uv run ruff check src tests
uv run pytest
```

Тесты не требуют живых Telegram / GitHub / Postgres: репозитории in-memory, GitHub — httpx mock.

## Переменные окружения

См. `.env.example` (комментарий у каждой переменной). Кратко:

| Переменная | Назначение |
|---|---|
| `BOT_TOKEN` | токен бота |
| `BOT_MODE` | `polling` или `webhook` |
| `PUBLIC_BASE_URL` | публичный HTTPS origin, без `/` на конце |
| `TELEGRAM_WEBHOOK_SECRET` | секрет заголовка Telegram webhook |
| `ADMIN_TELEGRAM_IDS` | id админов через запятую |
| `ADMIN_TELEGRAM_CONTACT` | контакт, который видит заказчик в статусе «Обсуждение» |
| `ADMIN_API_TOKEN` | Bearer для `/api/v1/admin/*` |
| `JWT_SECRET` / `JWT_EXPIRE_MINUTES` | JWT после initData |
| `DATABASE_URL` | SQLAlchemy async URL |
| `POSTGRES_USER/PASSWORD/DB` | для образа Postgres, синхронизировать с URL |
| `GITHUB_TOKEN` | REST issues/milestones/hooks + GraphQL Projects v2 |
| `GITHUB_WEBHOOK_SECRET` | HMAC webhook GitHub |
| `GITHUB_STATUS_BACKLOG` / `IN_PROGRESS` / `DONE` | имена опций поля Status в Project |
| `DEFAULT_LOCALE` | `ru` или `en` |
| `BOT_USERNAME` | без `@`, для кнопки «Поделиться» |

## GitHub token и webhook

Рекомендуемые права classic PAT: `repo`, `read:project`, `project`, `write:repo_hook` (или `admin:repo_hook`).

Fine-grained: доступ к целевым репозиториям, Issues (read/write), Metadata, Webhooks, Projects.

При переводе заявки **В работу** бот:

1. проверяет доступ к репо;
2. читает Projects v2 (если несколько — админ выбирает);
3. ставит webhook `issues` на `PUBLIC_BASE_URL/webhooks/github` (идемпотентно);
4. шлёт заказчику открытые milestones без раскрытия URL репозитория.

GitHub `issues` webhook обрабатывает:

- закрытие Issue — заказчику отправляются title и текст (последний комментарий или body);
- добавление label `ready` к Issue с label `customer request` — заказчик получает описание принятой доработки;
- закрытие последней открытой задачи milestone — однократное уведомление о 100% готовности.

GFM-ссылки кликабельны; картинки `![](url)` уходят отдельными фото. Повторные webhook deliveries и повторные
закрытия milestone дедуплицируются в PostgreSQL.

Правка заказчика вводится одним сообщением, создаёт Issue с лейблом `customer request` и карточку в Backlog.
Администратор получает Telegram заказчика. В «Мой заказ» показываются общий прогресс, текущие задачи и кнопки
открытых milestones; каждая кнопка открывает задачи этапа со статусами и сроками.

Заявка поддержки после завершения также содержит только одно пожелание. В очереди поддержки её можно отменить
или взять в работу. Взятие создаёт отдельный milestone в репозитории родительского проекта; завершение закрывает
support-заявку и возвращает основной проект в `completed`.

## REST API

- Клиент: `POST /api/v1/auth/telegram` с Mini App `initData` → JWT.
- Админ: `Authorization: Bearer {ADMIN_API_TOKEN}`.
- Заказы, статусы, прогресс, задачи milestone, customer request, support, язык и completion links — те же use
  cases, что у бота.
- OpenAPI: `/docs`.

## lazysql

В корне лежит `.lazysql.toml`. URL берёт `POSTGRES_*` из окружения:

```bash
set -a && source .env && set +a
lazysql
```

Навык `add-config-to-lazysql` в среде не найден — конфиг добавлен по формату [lazysql](https://github.com/jorgerojas26/lazysql).

## Деплой (GitHub Actions)

После зелёных `lint-and-test` и `docker` push (или ручной `workflow_dispatch`) в `main` job **Deploy to production**:

1. по SSH передаёт секрет `APP_ENV` и на сервере пишет `.env` (`chmod 600`);
2. делает `git pull` и `docker compose up --build -d`. Reverse proxy на хосте настраивается отдельно (см. Caddyfile выше).

Environment в GitHub: **production** (Settings → Environments).

### Secrets

| Секрет | Назначение |
|---|---|
| `APP_ENV` | полный текст `.env` (как `.env.example`, реальные значения) |
| `DEPLOY_HOST` | IP или hostname сервера |
| `DEPLOY_USER` | SSH-пользователь |
| `DEPLOY_SSH_KEY` | приватный ключ входа CI на VPS |
| `GIT_SSH_KEY` | приватный ключ **Deploy key** репозитория (тот же, чей `.pub` в Settings → Deploy keys) |

В `APP_ENV` для Compose укажите `DATABASE_URL` с хостом `db`, `BOT_MODE=webhook` и `PUBLIC_BASE_URL` как публичный HTTPS-хост из Caddyfile.

### Variables

| Variable | Назначение |
|---|---|
| `DEPLOY_PATH` | абсолютный путь клона на сервере |
| `DEPLOY_SSH_PORT` | SSH-порт, по умолчанию `22` |

Первый раз на сервере: пользователь `DEPLOY_USER` в группе `docker`. Каталог `DEPLOY_PATH` пустой или его ещё нет. `.env` руками не нужен. Caddy на хосте настраивается отдельно.

Два разных SSH-ключа:

1. **`DEPLOY_SSH_KEY`** в GitHub — вход CI на VPS (публичная часть в `authorized_keys` на сервере).
2. **Deploy key репозитория** — вход VPS на `github.com`. Публичный ключ — Settings → Deploy keys (read-only). Приватный файл на сервере: **`~/.ssh/bot-bw-deploy`** (CI его подхватит). Либо секрет `GIT_SSH_KEY` — тогда ключ запишется как `~/.ssh/github_deploy`.

Не кладите в Deploy keys публичную часть от `DEPLOY_SSH_KEY`: этот приватный ключ есть только в Actions, `git clone` на VPS его не видит.

```bash
ssh-keygen -t ed25519 -f github_deploy -N ""
# github_deploy.pub → Deploy keys
# содержимое github_deploy → секрет GIT_SSH_KEY (весь файл, с BEGIN/END)

sudo rm -rf /opt/tg-bot   # если прошлый clone сломан
```

## Gitflow

- `main` — стабильное
- `develop` — интеграция (создайте при необходимости)
- фичи: `feature/...` (эта поставка — `feature/commission-bot`)
