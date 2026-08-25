from beerwolf_shop.infrastructure.telegram.i18n import I18n


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
