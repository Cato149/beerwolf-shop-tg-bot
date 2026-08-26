"""Persist Telegram notifications in the business transaction; send after commit.

GitHub REST/GraphQL calls that return data needed to finish a use case (issue URL,
milestones, project list) stay in the use case. Only outbound Telegram is deferred
so a later rollback cannot leave admins/customers with a phantom update.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from beerwolf_shop.domain.entities import Order, User
from beerwolf_shop.domain.protocols import OrderRepository, UserRepository
from beerwolf_shop.infrastructure.db.repositories import SqlOrderRepository, SqlOutboxRepository, SqlUserRepository
from beerwolf_shop.infrastructure.github.gfm import RenderedMarkdown
from beerwolf_shop.infrastructure.telegram.notifier import TelegramNotifier

logger = logging.getLogger(__name__)

KIND_NOTIFY_ADMINS = "notify_admins_new_order"
KIND_NOTIFY_ADMINS_REQUEST = "notify_admins_customer_request"
KIND_NOTIFY_CUSTOMER = "notify_customer"
KIND_CLOSED_ISSUE = "closed_issue"
KIND_ISSUE_UPDATE = "issue_update"


class OutboxNotifier:
    """NotifierPort that inserts outbox rows instead of calling Telegram."""

    def __init__(self, outbox: SqlOutboxRepository) -> None:
        self._outbox = outbox

    async def notify_admins_new_order(self, order: Order, customer: User | None, locale: str = "ru") -> None:
        await self._outbox.enqueue(
            KIND_NOTIFY_ADMINS,
            {"order_id": str(order.id), "locale": locale},
        )

    async def notify_admins_customer_request(
        self,
        order: Order,
        customer: User | None,
        title: str,
        wish: str,
        url: str,
        locale: str = "ru",
    ) -> None:
        await self._outbox.enqueue(
            KIND_NOTIFY_ADMINS_REQUEST,
            {
                "order_id": str(order.id),
                "title": title,
                "wish": wish,
                "url": url,
                "locale": locale,
            },
        )

    async def notify_customer(
        self,
        telegram_id: int,
        locale: str,
        key: str,
        *,
        refresh_menu: bool = False,
        reply_markup=None,
        **kwargs: object,
    ) -> None:
        # Reply markup is rebuilt after commit; aiogram objects are not JSON serializable.
        _ = reply_markup
        await self._outbox.enqueue(
            KIND_NOTIFY_CUSTOMER,
            {
                "telegram_id": telegram_id,
                "locale": locale,
                "key": key,
                "kwargs": kwargs,
                "refresh_menu": refresh_menu,
            },
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
        await self._outbox.enqueue(
            KIND_ISSUE_UPDATE,
            {
                "telegram_id": telegram_id,
                "locale": locale,
                "header_key": header_key,
                "title": title,
                "url": url,
                "html": rendered.html,
                "photos": [[url_, caption] for url_, caption in rendered.photos],
            },
        )


async def deliver_outbox_event(
    kind: str,
    payload: dict,
    notifier: TelegramNotifier,
    users: UserRepository,
    orders: OrderRepository,
) -> None:
    """Replay one persisted event through the real Telegram notifier."""
    if kind == KIND_NOTIFY_ADMINS:
        order = await orders.get(UUID(payload["order_id"]))
        if order is None:
            logger.warning("outbox %s: order %s is gone", kind, payload.get("order_id"))
            return
        customer = await users.get_by_telegram_id(order.customer_telegram_id)
        await notifier.notify_admins_new_order(order, customer, locale=payload.get("locale") or "ru")
        return
    if kind == KIND_NOTIFY_ADMINS_REQUEST:
        order = await orders.get(UUID(payload["order_id"]))
        if order is None:
            logger.warning("outbox %s: order %s is gone", kind, payload.get("order_id"))
            return
        customer = await users.get_by_telegram_id(order.customer_telegram_id)
        await notifier.notify_admins_customer_request(
            order,
            customer,
            payload.get("title") or "",
            payload.get("wish") or "",
            payload.get("url") or "",
            locale=payload.get("locale") or "ru",
        )
        return
    if kind == KIND_NOTIFY_CUSTOMER:
        kwargs = payload.get("kwargs") or {}
        if not isinstance(kwargs, dict):
            kwargs = {}
        reply_markup = None
        if payload.get("refresh_menu"):
            project = await orders.get_active_commission(int(payload["telegram_id"]))
            if project is None:
                project = await orders.get_latest_commission(int(payload["telegram_id"]))
            reply_markup = notifier.customer_menu(
                int(payload["telegram_id"]),
                payload.get("locale") or "ru",
                project,
            )
        await notifier.notify_customer(
            int(payload["telegram_id"]),
            payload.get("locale") or "ru",
            payload["key"],
            reply_markup=reply_markup,
            **kwargs,
        )
        return
    if kind in {KIND_CLOSED_ISSUE, KIND_ISSUE_UPDATE}:
        photos_raw = payload.get("photos") or []
        photos = [(str(item[0]), str(item[1])) for item in photos_raw]
        rendered = RenderedMarkdown(html=payload.get("html") or "", photos=photos)
        await notifier.send_issue_update(
            int(payload["telegram_id"]),
            payload.get("locale") or "ru",
            payload.get("header_key") or "progress.issue_closed",
            payload.get("title") or "",
            payload.get("url") or "",
            rendered,
        )
        return
    logger.error("unknown outbox kind %s", kind)


class OutboxProcessor:
    """After a successful commit, send pending rows and mark them processed."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        notifier: TelegramNotifier,
    ) -> None:
        self._session_factory = session_factory
        self._notifier = notifier

    async def drain(self) -> None:
        try:
            await self._drain()
        except Exception:
            # Never fail the user-facing request: the row stays pending for the next drain.
            logger.exception("outbox drain failed")

    async def _drain(self) -> None:
        async with self._session_factory() as session:
            repo = SqlOutboxRepository(session)
            rows = await repo.claim_pending()
            if not rows:
                return
            users = SqlUserRepository(session)
            orders = SqlOrderRepository(session)
            now = datetime.now(UTC)
            for row in rows:
                try:
                    payload = row.payload if isinstance(row.payload, dict) else {}
                    await deliver_outbox_event(row.kind, payload, self._notifier, users, orders)
                    row.processed_at = now
                    row.last_error = None
                except Exception as exc:
                    row.attempts += 1
                    row.last_error = str(exc)[:2000]
                    logger.exception("outbox event %s (%s) failed", row.id, row.kind)
            await session.commit()
