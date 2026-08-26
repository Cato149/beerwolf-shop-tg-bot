"""Safe Telegram HTML rendering for localized rich messages."""

from __future__ import annotations

import html
import re
from urllib.parse import urlsplit

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_ANCHOR = re.compile(r'<a href="\{(\w+)\}">([\s\S]*?)</a>')
_ALLOWED_LINK_SCHEMES = frozenset({"http", "https", "tg"})


class SafeHtml(str):
    """HTML fragment constructed by trusted application code."""


def escape_html(value: object) -> str:
    """Escape an untrusted dynamic value for Telegram HTML."""
    return html.escape("" if value is None else str(value), quote=False)


def html_link(label: object, url: object) -> SafeHtml:
    """Build a safe human-readable link, falling back to plain text."""
    escaped_label = str(label) if isinstance(label, SafeHtml) else escape_html(label)
    raw_url = "" if url is None else str(url).strip()
    parsed = urlsplit(raw_url)
    if parsed.scheme not in _ALLOWED_LINK_SCHEMES or not parsed.netloc:
        return SafeHtml(escaped_label)
    return SafeHtml(f'<a href="{html.escape(raw_url, quote=True)}">{escaped_label}</a>')


def html_lines(lines: list[str | SafeHtml]) -> SafeHtml:
    """Join already escaped or trusted fragments without re-escaping them."""
    return SafeHtml("\n".join(str(line) for line in lines))


def _render_value(value: object) -> str:
    return str(value) if isinstance(value, SafeHtml) else escape_html(value)


def render_locale(template: str, **kwargs: object) -> str:
    """Fill a trusted locale template while escaping all dynamic values.

    Locale files may use Telegram's supported HTML tags. Dynamic anchors use
    ``<a href="{url}">label</a>`` and are validated before being emitted.
    """

    def replace_anchor(match: re.Match[str]) -> str:
        url_name, label_template = match.groups()
        label = _PLACEHOLDER.sub(lambda item: _render_value(kwargs.get(item.group(1), "")), label_template)
        return str(html_link(SafeHtml(label), kwargs.get(url_name, "")))

    with_links = _ANCHOR.sub(replace_anchor, template)
    return _PLACEHOLDER.sub(lambda match: _render_value(kwargs.get(match.group(1), "")), with_links)
