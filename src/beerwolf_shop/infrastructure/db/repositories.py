"""SQLModel implementations of domain repository protocols."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel.ext.asyncio.session import AsyncSession

from beerwolf_shop.domain.entities import CompletionLink, CustomerRequestIssue, Order, User
from beerwolf_shop.domain.enums import ACTIVE_CUSTOMER_STATUSES, OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import ActiveCommissionExistsError
from beerwolf_shop.infrastructure.db.models import (
    CompletionLinkTable,
    CustomerRequestIssueTable,
    MilestoneNotificationTable,
    OrderTable,
    OutboxEventTable,
    UserTable,
    WebhookDeliveryTable,
)


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(select(UserTable).where(UserTable.telegram_id == telegram_id))
        row = result.scalars().first()
        return row.to_domain() if row else None

    async def get_by_username(self, username: str) -> User | None:
        needle = username.lstrip("@").lower()
        stmt = select(UserTable).where(func.lower(func.ltrim(UserTable.username, "@")) == needle)
        result = await self._session.execute(stmt)
        row = result.scalars().first()
        return row.to_domain() if row else None

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
        result = await self._session.execute(
            select(OrderTable).options(selectinload(OrderTable.links)).where(OrderTable.id == order_id)
        )
        row = result.scalars().first()
        return row.to_domain() if row else None

    async def get_for_update(self, order_id: UUID) -> Order | None:
        result = await self._session.execute(
            select(OrderTable)
            .options(selectinload(OrderTable.links))
            .where(OrderTable.id == order_id)
            .with_for_update()
        )
        row = result.scalars().first()
        return row.to_domain() if row else None

    async def lock_customer(self, telegram_id: int) -> None:
        # The transaction-level advisory lock also serializes new-order creation
        # against reopening a completed parent for support.
        await self._session.execute(select(func.pg_advisory_xact_lock(telegram_id)))

    async def add(self, order: Order) -> Order:
        row = OrderTable.from_domain(order)
        try:
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
        except IntegrityError as exc:
            if order.type == OrderType.commission:
                raise ActiveCommissionExistsError(str(order.customer_telegram_id)) from exc
            raise
        return row.to_domain()

    async def save(self, order: Order) -> Order:
        result = await self._session.execute(
            select(OrderTable).options(selectinload(OrderTable.links)).where(OrderTable.id == order.id)
        )
        row = result.scalars().first()
        if row is None:
            return await self.add(order)
        row.apply(order)
        await self._session.flush()
        return row.to_domain()

    def _filtered(self, status: OrderStatus | None, order_type: OrderType | None):
        stmt = select(OrderTable).options(selectinload(OrderTable.links))
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
        # execute+scalars: session.exec() + selectinload yields Row, not OrderTable.
        result = await self._session.execute(stmt)
        return [row.to_domain() for row in result.scalars().all()]

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
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_for_customer(self, telegram_id: int) -> list[Order]:
        result = await self._session.execute(
            select(OrderTable)
            .options(selectinload(OrderTable.links))
            .where(OrderTable.customer_telegram_id == telegram_id)
            .order_by(OrderTable.created_at.desc())
        )
        return [row.to_domain() for row in result.scalars().all()]

    async def get_active_commission(self, telegram_id: int) -> Order | None:
        result = await self._session.execute(
            select(OrderTable)
            .options(selectinload(OrderTable.links))
            .where(
                OrderTable.customer_telegram_id == telegram_id,
                OrderTable.type == OrderType.commission.value,
                OrderTable.status.in_([status.value for status in ACTIVE_CUSTOMER_STATUSES]),
            )
            .order_by(OrderTable.created_at.desc())
            .limit(1)
        )
        row = result.scalars().first()
        return row.to_domain() if row else None

    async def get_latest_commission(self, telegram_id: int) -> Order | None:
        result = await self._session.execute(
            select(OrderTable)
            .options(selectinload(OrderTable.links))
            .where(
                OrderTable.customer_telegram_id == telegram_id,
                OrderTable.type == OrderType.commission.value,
                OrderTable.status.notin_([OrderStatus.spam.value, OrderStatus.cancelled.value]),
            )
            .order_by(OrderTable.created_at.desc())
            .limit(1)
        )
        row = result.scalars().first()
        return row.to_domain() if row else None

    async def get_active_by_project_id(self, project_id: str) -> Order | None:
        result = await self._session.execute(
            select(OrderTable)
            .options(selectinload(OrderTable.links))
            .where(
                OrderTable.github_project_id == project_id,
                OrderTable.type == OrderType.commission.value,
                OrderTable.status.in_([status.value for status in ACTIVE_CUSTOMER_STATUSES]),
            )
            .limit(1)
        )
        row = result.scalars().first()
        return row.to_domain() if row else None

    async def find_by_repo(self, owner: str, repo: str) -> list[Order]:
        result = await self._session.execute(
            select(OrderTable)
            .options(selectinload(OrderTable.links))
            .where(
                func.lower(OrderTable.github_owner) == owner.lower(),
                func.lower(OrderTable.github_repo) == repo.lower(),
            )
        )
        return [row.to_domain() for row in result.scalars().all()]


class SqlCompletionLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_order(self, order_id: UUID) -> list[CompletionLink]:
        result = await self._session.execute(
            select(CompletionLinkTable).where(CompletionLinkTable.order_id == order_id)
        )
        return [row.to_domain() for row in result.scalars().all()]

    async def replace_for_order(self, order_id: UUID, links: list[CompletionLink]) -> None:
        existing = await self._session.execute(
            select(CompletionLinkTable).where(CompletionLinkTable.order_id == order_id)
        )
        for row in existing.scalars().all():
            await self._session.delete(row)
        for link in links:
            self._session.add(CompletionLinkTable.from_domain(link))
        await self._session.flush()


class SqlWebhookDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, delivery_id: str) -> bool:
        """Insert delivery id; return False if another worker already claimed it.

        Uses a SAVEPOINT so a unique-key race does not abort the outer transaction.
        """
        if await self._session.get(WebhookDeliveryTable, delivery_id):
            return False
        try:
            async with self._session.begin_nested():
                self._session.add(WebhookDeliveryTable(delivery_id=delivery_id))
                await self._session.flush()
        except IntegrityError:
            return False
        return True


class SqlMilestoneNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, order_id: UUID, milestone_number: int) -> bool:
        stmt = select(MilestoneNotificationTable).where(
            MilestoneNotificationTable.order_id == order_id,
            MilestoneNotificationTable.github_milestone_number == milestone_number,
        )
        if (await self._session.execute(stmt)).scalars().first():
            return False
        try:
            async with self._session.begin_nested():
                self._session.add(
                    MilestoneNotificationTable(
                        order_id=order_id,
                        github_milestone_number=milestone_number,
                    )
                )
                await self._session.flush()
        except IntegrityError:
            return False
        return True


class SqlCustomerRequestIssueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, link: CustomerRequestIssue) -> None:
        self._session.add(
            CustomerRequestIssueTable(
                id=link.id,
                order_id=link.order_id,
                github_node_id=link.github_node_id,
                created_at=link.created_at,
            )
        )
        await self._session.flush()

    async def find_order_id(self, github_node_id: str) -> UUID | None:
        result = await self._session.execute(
            select(CustomerRequestIssueTable.order_id).where(
                CustomerRequestIssueTable.github_node_id == github_node_id
            )
        )
        return result.scalar_one_or_none()


class SqlOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, kind: str, payload: dict) -> None:
        self._session.add(OutboxEventTable(kind=kind, payload=payload))

    async def claim_pending(self, *, limit: int = 25, max_attempts: int = 8) -> list[OutboxEventTable]:
        """Lock a batch of unsent events. SKIP LOCKED lets concurrent drains proceed."""
        stmt = (
            select(OutboxEventTable)
            .where(OutboxEventTable.processed_at.is_(None))
            .where(OutboxEventTable.attempts < max_attempts)
            .order_by(OutboxEventTable.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
