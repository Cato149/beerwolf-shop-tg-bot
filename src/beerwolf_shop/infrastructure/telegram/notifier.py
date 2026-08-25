"""Outbound Telegram notifications used by use cases and webhooks."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from beerwolf_shop.config import Settings
from beerwolf_shop.domain.entities import Order, User
from beerwolf_shop.infrastructure.github.gfm import RenderedMarkdown
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.keyboards import admin_new_order_actions, render_md

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot: Bot, i18n: I18n, settings: Settings) -> None:
        self._bot = bot
        self._i18n = i18n
        self._settings = settings

    async def send_md(
        self,
        telegram_id: int,
        locale: str,
        key: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        **kwargs: object,
    ) -> None:
        text = render_md(self._i18n, locale, key, **kwargs)
        try:
            await self._bot.send_message(
                telegram_id,
                text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=reply_markup,
            )
        except TelegramAPIError:
            logger.info("Could not deliver to %s (user may not have started the bot)", telegram_id)

    async def notify_admins_new_order(self, order: Order, customer: User | None, locale: str = "ru") -> None:
        username = f"@{customer.username}" if customer and customer.username else "—"
        name = customer.display_name if customer else str(order.customer_telegram_id)
        for admin_id in self._settings.admin_telegram_ids:
            await self.send_md(
                admin_id,
                locale,
                "admin.new_order_notify",
                order_id=str(order.id),
                order_type=order.type.value,
                name=name,
                username=username,
                idea=order.idea,
                contacts=order.extra_contacts or "—",
                references=order.references or "—",
                budget=order.budget or "—",
                reply_markup=admin_new_order_actions(order.id, self._i18n, locale),
            )

    async def notify_customer(self, telegram_id: int, locale: str, key: str, **kwargs: object) -> None:
        await self.send_md(telegram_id, locale, key, **kwargs)

    async def send_html_with_photos(
        self,
        telegram_id: int,
        html_text: str,
        photos: Sequence[tuple[str, str]],
    ) -> None:
        try:
            if html_text:
                await self._bot.send_message(telegram_id, html_text, parse_mode=ParseMode.HTML)
            for url, caption in photos:
                await self._bot.send_photo(telegram_id, url, caption=caption[:1024] or None)
        except TelegramAPIError:
            logger.info("Could not deliver media to %s", telegram_id)

    async def send_closed_issue(
        self,
        telegram_id: int,
        locale: str,
        title: str,
        url: str,
        rendered: RenderedMarkdown,
    ) -> None:
        header = render_md(self._i18n, locale, "progress.issue_closed", title=title, url=url)
        try:
            await self._bot.send_message(telegram_id, header, parse_mode=ParseMode.MARKDOWN_V2)
        except TelegramAPIError:
            logger.info("Could not deliver issue header to %s", telegram_id)
        await self.send_html_with_photos(telegram_id, rendered.html, rendered.photos)
