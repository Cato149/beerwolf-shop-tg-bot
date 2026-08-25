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

Один заказ = одно репо + один Project v2. Support-заявки — отдельные `Order(type=support)` с `parent_order_id`.

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

Порт приложения опубликован как `127.0.0.1:8000` — снаружи его закрывает Caddy на хосте.

### Caddy (на сервере, вне Docker)

Caddy ставится на хост (пакет или бинарник), в Compose его нет. Он выдаёт HTTPS и проксирует на `127.0.0.1:8000`.

1. DNS A/AAAA `CADDY_DOMAIN` → IP сервера, открыты порты 80 и 443.
2. В `.env`: `CADDY_DOMAIN`, `CADDY_EMAIL`, `PUBLIC_BASE_URL=https://<CADDY_DOMAIN>`, `BOT_MODE=webhook`, `APP_PORT=8000`.
3. Запуск из корня репозитория:

```bash
caddy run --envfile .env --config Caddyfile
```

Пакет Debian/Ubuntu: symlink `Caddyfile` в `/etc/caddy/Caddyfile` и drop-in systemd, чтобы подтянуть `.env`:

```ini
# /etc/systemd/system/caddy.service.d/beerwolf.conf
[Service]
EnvironmentFile=/absolute/path/to/beerwolf-shop-tg-bot/.env
```

```bash
sudo systemctl daemon-reload
sudo systemctl reload caddy
```

После этого Telegram и GitHub ходят на `https://<CADDY_DOMAIN>/webhooks/...`.

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
| `CADDY_DOMAIN` / `CADDY_EMAIL` | хост и ACME-почта для Caddyfile (Python их не читает) |
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
4. шлёт заказчику открытые milestones.

Закрытие Issue: `POST /webhooks/github` → заказчику title + текст (последний комментарий или body). GFM-ссылки кликабельны; картинки `![](url)` уходят отдельными фото.

Правка заказчика создаёт Issue с лейблом `customer request` и карточку в Backlog.

## REST API

- Клиент: `POST /api/v1/auth/telegram` с Mini App `initData` → JWT.
- Админ: `Authorization: Bearer {ADMIN_API_TOKEN}`.
- Заказы, статусы, прогресс, customer request, support, язык, completion links — те же use cases, что у бота.
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

1. пишет `.env` из секрета `APP_ENV` (весь файл одним значением);
2. копирует `.env` на VPS по SCP;
3. по SSH делает `git pull`, `docker compose up --build -d`, копирует `Caddyfile` в `/etc/caddy/` и `systemctl reload`.

Environment в GitHub: **production** (Settings → Environments).

### Secrets

| Секрет | Назначение |
|---|---|
| `APP_ENV` | полный текст `.env` (как `.env.example`, реальные значения) |
| `DEPLOY_HOST` | IP или hostname сервера |
| `DEPLOY_USER` | SSH-пользователь |
| `DEPLOY_SSH_KEY` | приватный ключ |

В `APP_ENV` для Compose укажите `DATABASE_URL` с хостом `db`, `BOT_MODE=webhook`, `PUBLIC_BASE_URL` / `CADDY_DOMAIN` / `CADDY_EMAIL` как на проде.

### Variables

| Variable | Назначение |
|---|---|
| `DEPLOY_PATH` | абсолютный путь клона на сервере |
| `DEPLOY_SSH_PORT` | SSH-порт, по умолчанию `22` |

Первый раз на сервере: клон репозитория, deploy key для `git fetch`, пользователь в группе `docker`, для reload Caddy — `sudo` без пароля на `cp`/`systemctl reload caddy`. `.env` руками создавать не нужно — его пишет CI.

## Gitflow

- `main` — стабильное
- `develop` — интеграция (создайте при необходимости)
- фичи: `feature/...` (эта поставка — `feature/commission-bot`)
