"""Collect Telegram photo file_ids and resend them to another chat."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InputMediaPhoto, Message

logger = logging.getLogger(__name__)
_MEDIA_GROUP_LIMIT = 10


def collect_photo_file_ids(message: Message) -> list[str]:
    """Return Telegram file_ids from a photo or an image document."""
    ids: list[str] = []
    if message.photo:
        ids.append(message.photo[-1].file_id)
    document = message.document
    if document is not None and (document.mime_type or "").startswith("image/"):
        ids.append(document.file_id)
    return ids


async def send_file_id_photos(bot: Bot, chat_id: int, file_ids: Sequence[str]) -> list[int]:
    """Attach previously received photos to another chat (admin card or notify).

    Returns Telegram message ids so a paginated admin list can delete them later.
    """
    unique = list(dict.fromkeys(file_id for file_id in file_ids if file_id))
    if not unique:
        return []
    sent_ids: list[int] = []
    for start in range(0, len(unique), _MEDIA_GROUP_LIMIT):
        chunk = unique[start : start + _MEDIA_GROUP_LIMIT]
        try:
            if len(chunk) == 1:
                message = await bot.send_photo(chat_id, chunk[0])
                sent_ids.append(message.message_id)
            else:
                messages = await bot.send_media_group(
                    chat_id,
                    [InputMediaPhoto(media=file_id) for file_id in chunk],
                )
                sent_ids.extend(item.message_id for item in messages)
        except TelegramAPIError:
            logger.warning("Could not attach order photos to chat %s", chat_id)
    return sent_ids
