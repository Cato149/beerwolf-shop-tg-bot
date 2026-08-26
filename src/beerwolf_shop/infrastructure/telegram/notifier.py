"""Outbound Telegram notifications used by use cases and webhooks."""

from __future__ import annotations

import html
import logging
from collections.abc import Sequence
from typing import Protocol

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from beerwolf_shop.config import Settings
from beerwolf_shop.domain.entities import Order, User
from beerwolf_shop.infrastructure.github.gfm import RenderedMarkdown
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.keyboards import admin_new_order_actions, main_menu, render_md
from beerwolf_shop.infrastructure.telegram.photos import send_file_id_photos

logger = logging.getLogger(__name__)
_RETRYABLE_TELEGRAM_ERRORS = (TelegramNetworkError, TelegramRetryAfter, TelegramServerError)


class NotifierPort(Protocol):
    """Send or enqueue customer/admin Telegram notifications."""

    async def notify_admins_new_order(self, order: Order, customer: User | None, locale: str = "ru") -> None: ...

    async def notify_admins_customer_request(
        self,
        order: Order,
        customer: User | None,
        title: str,
        wish: str,
        url: str,
        locale: str = "ru",
    ) -> None: ...

    async def notify_customer(
        self,
        telegram_id: int,
        locale: str,
        key: str,
        *,
        refresh_menu: bool = False,
        reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
        **kwargs: object,
    ) -> None: ...

    async def send_issue_update(
        self,
        telegram_id: int,
        locale: str,
        header_key: str,
        title: str,
        url: str,
        rendered: RenderedMarkdown,
    ) -> None: ...


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
        reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
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
        except _RETRYABLE_TELEGRAM_ERRORS:
            # Let the outbox retain and retry transient Telegram failures.
            raise
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
                reply_markup=admin_new_order_actions(order.id, self._i18n, locale, order.type),
            )
            await send_file_id_photos(self._bot, admin_id, order.photo_file_ids)

    async def notify_admins_customer_request(
        self,
        order: Order,
        customer: User | None,
        title: str,
        wish: str,
        url: str,
        locale: str = "ru",
    ) -> None:
        username = f"@{customer.username}" if customer and customer.username else "—"
        for admin_id in self._settings.admin_telegram_ids:
            await self.send_md(
                admin_id,
                locale,
                "admin.customer_request_notify",
                username=username,
                telegram_id=order.customer_telegram_id,
                title=title,
                wish=wish,
                url=url,
            )

    def customer_menu(self, telegram_id: int, locale: str, project: Order | None) -> ReplyKeyboardMarkup:
        return main_menu(
            self._i18n,
            locale,
            is_admin=self._settings.is_admin(telegram_id),
            project=project,
        )

    async def notify_customer(
        self,
        telegram_id: int,
        locale: str,
        key: str,
        *,
        refresh_menu: bool = False,
        reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
        **kwargs: object,
    ) -> None:
        _ = refresh_menu
        await self.send_md(telegram_id, locale, key, reply_markup=reply_markup, **kwargs)

    async def send_html_with_photos(
        self,
        telegram_id: int,
        html_text: str,
        photos: Sequence[tuple[str, str]],
    ) -> None:
        if html_text:
            await self._bot.send_message(telegram_id, html_text, parse_mode=ParseMode.HTML)
        for url, caption in photos:
            await self._bot.send_photo(
                telegram_id,
                url,
                caption=html.escape(caption[:1024]) or None,
                parse_mode=ParseMode.HTML,
            )

    async def send_issue_update(
        self,
        telegram_id: int,
        locale: str,
        header_key: str,
        title: str,
        url: str,
        rendered: RenderedMarkdown,
    ) -> None:
        header = render_md(self._i18n, locale, header_key, title=title, url=url)
        try:
            await self._bot.send_message(telegram_id, header, parse_mode=ParseMode.MARKDOWN_V2)
            await self.send_html_with_photos(telegram_id, rendered.html, rendered.photos)
        except _RETRYABLE_TELEGRAM_ERRORS:
            raise
        except TelegramAPIError:
            logger.warning("Could not deliver closed-issue notification to %s", telegram_id)
