from beerwolf_shop.infrastructure.github.gfm import gfm_to_telegram


def test_gfm_links_and_images() -> None:
    rendered = gfm_to_telegram(
        "See [docs](https://example.com) and ![logo](https://example.com/logo.png)\n\n**Done**",
        fallback_caption="Issue",
    )
    assert '<a href="https://example.com">docs</a>' in rendered.html
    assert "<b>Done</b>" in rendered.html
    assert rendered.photos == [("https://example.com/logo.png", "logo")]
    assert "logo.png" not in rendered.html
