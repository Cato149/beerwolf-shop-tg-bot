"""SQLModel implementations of domain repository protocols."""

from uuid import UUID

from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from beerwolf_shop.domain.entities import CompletionLink, Order, User
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.infrastructure.db.models import (
    CompletionLinkTable,
    OrderTable,
    UserTable,
    WebhookDeliveryTable,
)


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.exec(select(UserTable).where(UserTable.telegram_id == telegram_id))
        row = result.first()
        return row.to_domain() if row else None

    async def get_by_username(self, username: str) -> User | None:
        normalized = username.lstrip("@").lower()
        result = await self._session.exec(select(UserTable))
        for row in result.all():
            if row.username and row.username.lstrip("@").lower() == normalized:
                return row.to_domain()
        return None

    async def add(self, user: User) -> User:
        row = UserTable.from_domain(user)
        self._session.add(row)
        await self._session.flush()
        return row.to_domain()

    async def save(self, user: User) -> User:
        row = await self._session.get(UserTable, user.id)
        if row is None:
            return await self.add(user)
        row.apply(user)
        await self._session.flush()
        return row.to_domain()


class SqlOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, order_id: UUID) -> Order | None:
        row = await self._session.get(OrderTable, order_id)
        if row is None:
            return None
        await self._session.refresh(row, attribute_names=["links"])
        return row.to_domain()

    async def add(self, order: Order) -> Order:
        row = OrderTable.from_domain(order)
        self._session.add(row)
        await self._session.flush()
        return row.to_domain()

    async def save(self, order: Order) -> Order:
        row = await self._session.get(OrderTable, order.id)
        if row is None:
            return await self.add(order)
        row.apply(order)
        await self._session.flush()
        return row.to_domain()

    def _filtered(self, status: OrderStatus | None, order_type: OrderType | None):
        stmt = select(OrderTable)
        if status is not None:
            stmt = stmt.where(OrderTable.status == status.value)
        if order_type is not None:
            stmt = stmt.where(OrderTable.type == order_type.value)
        return stmt.order_by(OrderTable.created_at.desc())

    async def list_by_status(
        self,
        status: OrderStatus | None,
        order_type: OrderType | None = None,
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> list[Order]:
        stmt = self._filtered(status, order_type).offset(offset).limit(limit)
        result = await self._session.exec(stmt)
        return [row.to_domain() for row in result.all()]

    async def count_by_status(
        self,
        status: OrderStatus | None,
        order_type: OrderType | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(OrderTable)
        if status is not None:
            stmt = stmt.where(OrderTable.status == status.value)
        if order_type is not None:
            stmt = stmt.where(OrderTable.type == order_type.value)
        result = await self._session.exec(stmt)
        return int(result.one())

    async def list_for_customer(self, telegram_id: int) -> list[Order]:
        result = await self._session.exec(
            select(OrderTable)
            .where(OrderTable.customer_telegram_id == telegram_id)
            .order_by(OrderTable.created_at.desc())
        )
        return [row.to_domain() for row in result.all()]

    async def find_by_repo(self, owner: str, repo: str) -> list[Order]:
        result = await self._session.exec(
            select(OrderTable).where(
                OrderTable.github_owner == owner,
                OrderTable.github_repo == repo,
            )
        )
        return [row.to_domain() for row in result.all()]


class SqlCompletionLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_order(self, order_id: UUID) -> list[CompletionLink]:
        result = await self._session.exec(select(CompletionLinkTable).where(CompletionLinkTable.order_id == order_id))
        return [row.to_domain() for row in result.all()]

    async def replace_for_order(self, order_id: UUID, links: list[CompletionLink]) -> None:
        existing = await self._session.exec(select(CompletionLinkTable).where(CompletionLinkTable.order_id == order_id))
        for row in existing.all():
            await self._session.delete(row)
        for link in links:
            self._session.add(CompletionLinkTable.from_domain(link))
        await self._session.flush()


class SqlWebhookDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def seen(self, delivery_id: str) -> bool:
        row = await self._session.get(WebhookDeliveryTable, delivery_id)
        return row is not None

    async def mark(self, delivery_id: str) -> None:
        self._session.add(WebhookDeliveryTable(delivery_id=delivery_id))
        await self._session.flush()
