from beerwolf_shop.infrastructure.telegram.markdown import (
    SafeHtml,
    escape_html,
    html_lines,
    html_link,
    render_locale,
)


def test_escape_html_specials() -> None:
    assert escape_html("<wolf & fox>") == "&lt;wolf &amp; fox&gt;"


def test_link_has_readable_label_and_validated_url() -> None:
    assert html_link("Open <project>", "https://example.com/a?x=1&y=2") == (
        '<a href="https://example.com/a?x=1&amp;y=2">Open &lt;project&gt;</a>'
    )
    assert html_link("Unsafe", "javascript:alert(1)") == "Unsafe"


def test_render_preserves_template_markup_and_escapes_user_input() -> None:
    out = render_locale("<b>Hello, {name}</b>", name="<script>alert(1)</script>")
    assert out == "<b>Hello, &lt;script&gt;alert(1)&lt;/script&gt;</b>"


def test_render_builds_safe_dynamic_anchor() -> None:
    out = render_locale('<a href="{url}">{title}</a>', title="A & B", url="https://example.com/?x=1&y=2")
    assert out == '<a href="https://example.com/?x=1&amp;y=2">A &amp; B</a>'
    assert render_locale('<a href="{url}">Open</a>', url="file:///secret") == "Open"


def test_safe_fragments_are_not_escaped_again() -> None:
    links = html_lines([SafeHtml(f"• {html_link('Project', 'https://example.com')}")])
    assert render_locale("<b>Links</b>\n{links}", links=links).endswith(
        '• <a href="https://example.com">Project</a>'
    )
