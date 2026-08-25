"""GitHub Flavored Markdown → Telegram HTML plus extracted image URLs."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_CODE_BLOCK = re.compile(r"```(?:\w+)?\n?([\s\S]*?)```")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
_STRIKE = re.compile(r"~~(.+?)~~")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


@dataclass(slots=True)
class RenderedMarkdown:
    html: str
    photos: list[tuple[str, str]]


def gfm_to_telegram(markdown: str, *, fallback_caption: str = "") -> RenderedMarkdown:
    """Turn GFM issue text into Telegram HTML and a list of (url, caption) photos.

    Images (`![alt](url)`) are stripped from the text and returned separately so
    the bot can send them as real photos with clickable remaining links.
    """
    photos: list[tuple[str, str]] = []

    def take_image(match: re.Match[str]) -> str:
        alt = match.group(1).strip() or fallback_caption
        photos.append((match.group(2).strip(), alt))
        return ""

    text = _IMAGE.sub(take_image, markdown or "")

    blocks: list[str] = []

    def stash_block(match: re.Match[str]) -> str:
        body = html.escape(match.group(1).rstrip("\n"))
        blocks.append(f"<pre>{body}</pre>")
        return f"\x00B{len(blocks) - 1}\x00"

    text = _CODE_BLOCK.sub(stash_block, text)

    codes: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        codes.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00C{len(codes) - 1}\x00"

    text = _INLINE_CODE.sub(stash_code, text)

    def heading(match: re.Match[str]) -> str:
        return f"<b>{html.escape(match.group(2))}</b>"

    text = _HEADING.sub(heading, text)

    # Escape raw HTML first, then restore protected spans and wrap markup.
    escaped = html.escape(text)

    # After html.escape the stash tokens are unchanged (\x00 is not escaped).
    for index, chunk in enumerate(codes):
        escaped = escaped.replace(f"\x00C{index}\x00", chunk)
    for index, chunk in enumerate(blocks):
        escaped = escaped.replace(f"\x00B{index}\x00", chunk)

    def repl_link(match: re.Match[str]) -> str:
        label = match.group(1)
        url = html.escape(match.group(2), quote=True)
        return f'<a href="{url}">{label}</a>'

    # Links were escaped: [text](url) stays the same because those chars are safe.
    escaped = _LINK.sub(repl_link, escaped)

    def repl_bold(match: re.Match[str]) -> str:
        return f"<b>{match.group(1) or match.group(2)}</b>"

    def repl_italic(match: re.Match[str]) -> str:
        return f"<i>{match.group(1) or match.group(2)}</i>"

    def repl_strike(match: re.Match[str]) -> str:
        return f"<s>{match.group(1)}</s>"

    escaped = _BOLD.sub(repl_bold, escaped)
    escaped = _STRIKE.sub(repl_strike, escaped)
    escaped = _ITALIC.sub(repl_italic, escaped)

    html_text = escaped.strip()
    if not html_text and not photos:
        html_text = ""
    return RenderedMarkdown(html=html_text, photos=photos)
