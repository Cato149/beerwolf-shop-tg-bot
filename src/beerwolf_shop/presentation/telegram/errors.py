"""Global Telegram error handler: log and tell the user something went wrong."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent

from beerwolf_shop.infrastructure.telegram.i18n import I18n

logger = logging.getLogger(__name__)


async def handle_telegram_error(event: ErrorEvent, i18n: I18n, locale: str = "ru") -> bool:
    """Catch unhandled handler/middleware exceptions so the user is not left in silence."""
    logger.exception("Unhandled Telegram update", exc_info=event.exception)
    text = i18n.get(locale, "common.error_generic")
    update = event.update
    try:
        if update.callback_query:
            await update.callback_query.answer(text[:200], show_alert=True)
        elif update.message:
            # parse_mode=None: error text has punctuation and the bot default is MarkdownV2.
            await update.message.answer(text, parse_mode=None)
        elif update.edited_message:
            await update.edited_message.answer(text, parse_mode=None)
    except TelegramAPIError:
        logger.info("Could not send error feedback for update %s", update.update_id)
    return True
