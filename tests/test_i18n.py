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
