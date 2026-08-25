from beerwolf_shop.infrastructure.telegram.markdown import (
    escape_markdown_v2,
    md_to_markdown_v2,
    render_locale,
)


def test_escape_specials() -> None:
    assert r"\." in escape_markdown_v2("v1.0")
    assert r"\!" in escape_markdown_v2("hi!")


def test_bold_and_link() -> None:
    out = md_to_markdown_v2("Hello **world** and [docs](https://ex.com)")
    assert "*world*" in out
    assert "[docs](https://ex.com)" in out


def test_render_escapes_user_input() -> None:
    out = render_locale("Hi, *{name}*!", name="A.B")
    assert r"A\.B" in out
