"""Readable markdown in INI files → Telegram MarkdownV2."""

from __future__ import annotations

import re

# Telegram MarkdownV2 special characters that must be escaped in plain text.
_MDV2_SPECIALS = r"_*[]()~`>#+-=|{}.!\\"

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_CODE_BLOCK = re.compile(r"```([\s\S]*?)```")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def escape_markdown_v2(text: str) -> str:
    """Escape a dynamic value so it is safe inside MarkdownV2."""
    return "".join(f"\\{ch}" if ch in _MDV2_SPECIALS else ch for ch in text)


def _escape_plain(text: str) -> str:
    return escape_markdown_v2(text)


def md_to_markdown_v2(text: str) -> str:
    """Convert a limited CommonMark subset used in INI files to MarkdownV2.

    Supported: **bold**, *italic*, `code`, ```blocks```, [label](url).
    Everything else is escaped so Telegram does not reject the message.
    """
    blocks: list[str] = []

    def stash_block(match: re.Match[str]) -> str:
        blocks.append(f"```{match.group(1)}```")
        return f"\x00B{len(blocks) - 1}\x00"

    text = _CODE_BLOCK.sub(stash_block, text)

    inlines: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        inlines.append(f"`{escape_markdown_v2(match.group(1))}`")
        return f"\x00C{len(inlines) - 1}\x00"

    def stash_link(match: re.Match[str]) -> str:
        label = escape_markdown_v2(match.group(1))
        url = match.group(2).replace("\\", "\\\\").replace(")", "\\)")
        inlines.append(f"[{label}]({url})")
        return f"\x00C{len(inlines) - 1}\x00"

    def stash_bold(match: re.Match[str]) -> str:
        inlines.append(f"*{_escape_plain(match.group(1))}*")
        return f"\x00C{len(inlines) - 1}\x00"

    def stash_italic(match: re.Match[str]) -> str:
        inlines.append(f"_{_escape_plain(match.group(1))}_")
        return f"\x00C{len(inlines) - 1}\x00"

    text = _INLINE_CODE.sub(stash_code, text)
    text = _LINK.sub(stash_link, text)
    text = _BOLD.sub(stash_bold, text)
    text = _ITALIC.sub(stash_italic, text)
    text = _escape_plain(text)

    for index, chunk in enumerate(inlines):
        text = text.replace(f"\x00C{index}\x00", chunk)
    for index, chunk in enumerate(blocks):
        text = text.replace(f"\x00B{index}\x00", chunk)
    return text


def render_locale(template: str, **kwargs: object) -> str:
    """Format an INI template then convert it to MarkdownV2.

    Placeholders are filled with escaped values so user input cannot break markup.
    """
    tokens: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        token = f"\x00T{len(tokens)}\x00"
        value = kwargs.get(name, "")
        tokens[token] = escape_markdown_v2("" if value is None else str(value))
        return token

    staged = _PLACEHOLDER.sub(replace, template)
    converted = md_to_markdown_v2(staged)
    for token, value in tokens.items():
        converted = converted.replace(escape_markdown_v2(token), value)
        converted = converted.replace(token, value)
    return converted
