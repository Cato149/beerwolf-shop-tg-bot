import configparser
import re
from pathlib import Path
from uuid import uuid4

from beerwolf_shop.application.dto import MilestoneSummary
from beerwolf_shop.domain.entities import Order
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.keyboards import (
    AdminOrderCb,
    admin_list_keyboard,
    admin_order_card,
    admin_work_menu,
    main_menu,
    progress_milestones,
)


def test_ru_and_en_have_core_keys() -> None:
    i18n = I18n(default_locale="ru")
    for locale in ("ru", "en"):
        assert "Beerwolf" in i18n.get(locale, "common.start", name="Ann")
        assert i18n.get(locale, "order.ask_idea")
        assert i18n.get(locale, "admin.btn_spam")
        assert i18n.get(locale, "customer.btn_share")


def test_fallback_to_ru() -> None:
    i18n = I18n(default_locale="ru")
    text = i18n.get("de", "common.cancelled")
    assert text == i18n.get("ru", "common.cancelled")


def test_button_labels_match_every_locale() -> None:
    i18n = I18n(default_locale="ru")
    assert i18n.matches("Отправить заявку", "common.btn_confirm")
    assert i18n.matches("Send brief", "common.btn_confirm")
    assert i18n.matches("Новый проект", "common.btn_new_order")
    assert i18n.matches("New project", "common.btn_new_order")
    assert i18n.matches("Админка", "admin.btn_menu")
    assert i18n.matches("Admin", "admin.btn_menu")
    assert not i18n.matches("Nope", "common.btn_confirm")


def _menu_texts(menu) -> set[str]:
    return {button.text for row in menu.keyboard for button in row}


def test_main_menu_follows_project_lifecycle() -> None:
    i18n = I18n(default_locale="ru")
    assert _menu_texts(main_menu(i18n, "ru", is_admin=False)) == {"Новый проект", "Сменить язык"}

    project = Order(
        customer_telegram_id=1,
        type=OrderType.commission,
        idea="x",
        status=OrderStatus.in_progress,
    )
    active = _menu_texts(main_menu(i18n, "ru", is_admin=False, project=project))
    assert "Новый проект" not in active
    assert {"Мой проект", "Порекомендовать", "Сменить язык"} <= active

    project.status = OrderStatus.completed
    completed = _menu_texts(main_menu(i18n, "ru", is_admin=False, project=project))
    assert {"Новый проект", "Мой проект", "Порекомендовать", "Сменить язык"} <= completed

    project.status = OrderStatus.application
    pending = _menu_texts(main_menu(i18n, "ru", is_admin=False, project=project))
    assert {"Новый проект", "Мой проект", "Сменить язык"} <= pending
    assert "Порекомендовать" not in pending

    project.status = OrderStatus.discussion
    discussed = _menu_texts(main_menu(i18n, "ru", is_admin=False, project=project))
    assert "Новый проект" not in discussed
    assert "Мой проект" in discussed


def test_admin_list_keyboard_keeps_filters_without_legacy_actions() -> None:
    i18n = I18n(default_locale="ru")
    markup = admin_list_keyboard(i18n, "ru", current="all", page=0, has_next=True)
    buttons = [button for row in markup.inline_keyboard for button in row]
    texts = {button.text for button in buttons}
    assert "Создать проект" not in texts
    assert "Доработки" not in texts
    assert "• Все" in texts
    assert "· Новее" in texts
    assert "Старее →" in texts
    assert next(button for button in buttons if button.text == "· Новее").callback_data == "admin:page:noop"

    last_page = admin_list_keyboard(i18n, "ru", current="all", page=2, has_next=False)
    last_buttons = [button for row in last_page.inline_keyboard for button in row]
    assert {button.text for button in last_buttons} >= {"← Новее", "Старее ·"}
    assert next(button for button in last_buttons if button.text == "Старее ·").callback_data == "admin:page:noop"

    work = _menu_texts(admin_work_menu(i18n, "ru"))
    assert work == {"Проекты", "Спам", "Доработки", "Создать проект", "Назад"}

    progress = progress_milestones(i18n, "ru", uuid4(), [], show_request=True)
    assert progress.inline_keyboard[0][0].text == "Предложить правку"


def test_admin_projects_appear_above_filters_and_open_the_card() -> None:
    i18n = I18n(default_locale="ru")
    order = Order(
        customer_telegram_id=1,
        type=OrderType.commission,
        idea="Личный сайт",
        status=OrderStatus.application,
    )
    markup = admin_list_keyboard(
        i18n,
        "ru",
        current="application",
        page=0,
        has_next=False,
        kind="commission",
        projects=[(order, "Волк")],
    )
    project_button = markup.inline_keyboard[0][0]
    callback = AdminOrderCb.unpack(project_button.callback_data)
    assert project_button.text == "Личный сайт · Заявка · Волк"
    assert callback.action == "view"
    assert callback.order_id == str(order.id)
    assert markup.inline_keyboard[1][0].text == "Все"


def test_admin_project_card_has_status_workflows() -> None:
    i18n = I18n(default_locale="ru")
    markup = admin_order_card(
        uuid4(),
        OrderStatus.application,
        i18n,
        "ru",
        OrderType.commission,
    )
    texts = {button.text for row in markup.inline_keyboard for button in row}
    assert {"Отменить проект", "Открыть студию", "Выпустить проект"} <= texts


def test_milestone_button_shows_percent_and_completion_checkmark() -> None:
    i18n = I18n(default_locale="ru")
    order_id = uuid4()
    milestones = [
        MilestoneSummary(number=1, title="Concept", percent=60),
        MilestoneSummary(number=2, title="Launch", percent=100),
    ]
    markup = progress_milestones(i18n, "ru", order_id, milestones)
    texts = [row[0].text for row in markup.inline_keyboard]
    assert texts == ["60% · Concept", "✅ 100% · Launch"]


def _read_catalog(locale: str) -> dict[str, str]:
    parser = configparser.RawConfigParser()
    parser.read(Path("locales") / f"{locale}.ini", encoding="utf-8")
    return {
        f"{section}.{key}": value
        for section in parser.sections()
        for key, value in parser.items(section)
    }


def test_locale_keys_and_placeholders_stay_in_sync() -> None:
    catalogs = {locale: _read_catalog(locale) for locale in ("ru", "en")}
    assert catalogs["ru"].keys() == catalogs["en"].keys()
    for key in catalogs["ru"]:
        ru_placeholders = set(re.findall(r"\{(\w+)\}", catalogs["ru"][key]))
        en_placeholders = set(re.findall(r"\{(\w+)\}", catalogs["en"][key]))
        assert ru_placeholders == en_placeholders, key
