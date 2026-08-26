from uuid import uuid4

from beerwolf_shop.domain.entities import Order
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.keyboards import (
    admin_list_keyboard,
    admin_work_menu,
    main_menu,
    progress_milestones,
)


def test_ru_and_en_have_core_keys() -> None:
    i18n = I18n(default_locale="ru")
    for locale in ("ru", "en"):
        assert (
            "комисс" in i18n.get(locale, "common.start", name="Ann").lower()
            or "commission" in i18n.get(locale, "common.start", name="Ann").lower()
        )
        assert i18n.get(locale, "order.ask_idea")
        assert i18n.get(locale, "admin.btn_spam")
        assert i18n.get(locale, "customer.btn_share")


def test_fallback_to_ru() -> None:
    i18n = I18n(default_locale="ru")
    text = i18n.get("de", "common.cancelled")
    assert text == i18n.get("ru", "common.cancelled")


def test_button_labels_match_every_locale() -> None:
    i18n = I18n(default_locale="ru")
    assert i18n.matches("Подтвердить", "common.btn_confirm")
    assert i18n.matches("Confirm", "common.btn_confirm")
    assert i18n.matches("Новая заявка", "common.btn_new_order")
    assert i18n.matches("New request", "common.btn_new_order")
    assert i18n.matches("Админка", "admin.btn_menu")
    assert i18n.matches("Admin", "admin.btn_menu")
    assert not i18n.matches("Nope", "common.btn_confirm")


def _menu_texts(menu) -> set[str]:
    return {button.text for row in menu.keyboard for button in row}


def test_main_menu_follows_project_lifecycle() -> None:
    i18n = I18n(default_locale="ru")
    assert _menu_texts(main_menu(i18n, "ru", is_admin=False)) == {"Новая заявка", "Язык"}

    project = Order(
        customer_telegram_id=1,
        type=OrderType.commission,
        idea="x",
        status=OrderStatus.in_progress,
    )
    active = _menu_texts(main_menu(i18n, "ru", is_admin=False, project=project))
    assert "Новая заявка" not in active
    assert {"Мой заказ", "Порекомендовать", "Язык"} <= active

    project.status = OrderStatus.completed
    completed = _menu_texts(main_menu(i18n, "ru", is_admin=False, project=project))
    assert {"Новая заявка", "Мой заказ", "Порекомендовать", "Язык"} <= completed

    project.status = OrderStatus.application
    pending = _menu_texts(main_menu(i18n, "ru", is_admin=False, project=project))
    assert {"Новая заявка", "Мой заказ", "Язык"} <= pending
    assert "Порекомендовать" not in pending

    project.status = OrderStatus.discussion
    discussed = _menu_texts(main_menu(i18n, "ru", is_admin=False, project=project))
    assert "Новая заявка" not in discussed
    assert "Мой заказ" in discussed


def test_admin_list_keyboard_keeps_filters_without_legacy_actions() -> None:
    i18n = I18n(default_locale="ru")
    markup = admin_list_keyboard(i18n, "ru", current="all", page=0, has_next=True)
    texts = {button.text for row in markup.inline_keyboard for button in row}
    assert "Создать заявку" not in texts
    assert "Очередь поддержки" not in texts
    assert "• Все" in texts
    assert "Старее" in texts

    work = _menu_texts(admin_work_menu(i18n, "ru"))
    assert work == {"Заявки", "Спам", "Очередь поддержки", "Создать заявку", "Назад"}

    progress = progress_milestones(i18n, "ru", uuid4(), [], show_request=True)
    assert progress.inline_keyboard[0][0].text == "Запросить правку / идею"
