"""SQLModel tables mapped from domain entities."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from beerwolf_shop.domain.entities import (
    CompletionLink,
    CustomerRequestIssue,
    MilestoneNotification,
    Order,
    User,
)
from beerwolf_shop.domain.enums import OrderStatus, OrderType


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserTable(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    telegram_id: int = Field(sa_column=Column(BigInteger, unique=True, index=True, nullable=False))
    username: str | None = Field(default=None, index=True)
    display_name: str
    language: str = Field(default="ru")
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))

    def to_domain(self) -> User:
        return User(
            id=self.id,
            telegram_id=self.telegram_id,
            username=self.username,
            display_name=self.display_name,
            language=self.language,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, user: User) -> "UserTable":
        return cls(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            display_name=user.display_name,
            language=user.language,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    def apply(self, user: User) -> None:
        self.username = user.username
        self.display_name = user.display_name
        self.language = user.language
        self.updated_at = user.updated_at


class OrderTable(SQLModel, table=True):
    __tablename__ = "orders"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    customer_telegram_id: int = Field(sa_column=Column(BigInteger, index=True, nullable=False))
    type: str = Field(index=True)
    status: str = Field(index=True)
    idea: str = Field(sa_column=Column(Text, nullable=False))
    extra_contacts: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    references: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    budget: str | None = None
    parent_order_id: UUID | None = Field(default=None, foreign_key="orders.id", index=True)
    github_repo_url: str | None = None
    github_owner: str | None = Field(default=None, index=True)
    github_repo: str | None = Field(default=None, index=True)
    github_project_id: str | None = None
    github_milestone_number: int | None = Field(default=None, index=True)
    github_milestone_title: str | None = None
    project_display_name: str | None = None
    completion_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))

    links: list["CompletionLinkTable"] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={"lazy": "noload"},
    )

    def to_domain(self) -> Order:
        # Read the instrumented collection from instance state only. Accessing
        # `self.links` would emit a lazy SELECT and raise MissingGreenlet on
        # the async session (add/save after flush, lists without selectinload).
        raw_links = self.__dict__.get("links") or []
        return Order(
            id=self.id,
            customer_telegram_id=self.customer_telegram_id,
            type=OrderType(self.type),
            status=OrderStatus(self.status),
            idea=self.idea,
            extra_contacts=self.extra_contacts,
            references=self.references,
            budget=self.budget,
            parent_order_id=self.parent_order_id,
            github_repo_url=self.github_repo_url,
            github_owner=self.github_owner,
            github_repo=self.github_repo,
            github_project_id=self.github_project_id,
            github_milestone_number=self.github_milestone_number,
            github_milestone_title=self.github_milestone_title,
            project_display_name=self.project_display_name,
            completion_message=self.completion_message,
            created_at=self.created_at,
            updated_at=self.updated_at,
            links=[row.to_domain() for row in raw_links],
        )

    @classmethod
    def from_domain(cls, order: Order) -> "OrderTable":
        return cls(
            id=order.id,
            customer_telegram_id=order.customer_telegram_id,
            type=order.type.value,
            status=order.status.value,
            idea=order.idea,
            extra_contacts=order.extra_contacts,
            references=order.references,
            budget=order.budget,
            parent_order_id=order.parent_order_id,
            github_repo_url=order.github_repo_url,
            github_owner=order.github_owner,
            github_repo=order.github_repo,
            github_project_id=order.github_project_id,
            github_milestone_number=order.github_milestone_number,
            github_milestone_title=order.github_milestone_title,
            project_display_name=order.project_display_name,
            completion_message=order.completion_message,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    def apply(self, order: Order) -> None:
        self.customer_telegram_id = order.customer_telegram_id
        self.type = order.type.value
        self.status = order.status.value
        self.idea = order.idea
        self.extra_contacts = order.extra_contacts
        self.references = order.references
        self.budget = order.budget
        self.parent_order_id = order.parent_order_id
        self.github_repo_url = order.github_repo_url
        self.github_owner = order.github_owner
        self.github_repo = order.github_repo
        self.github_project_id = order.github_project_id
        self.github_milestone_number = order.github_milestone_number
        self.github_milestone_title = order.github_milestone_title
        self.project_display_name = order.project_display_name
        self.completion_message = order.completion_message
        self.updated_at = order.updated_at


class CompletionLinkTable(SQLModel, table=True):
    __tablename__ = "completion_links"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    url: str
    title: str
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))

    order: OrderTable | None = Relationship(
        back_populates="links",
        sa_relationship_kwargs={"lazy": "noload"},
    )

    def to_domain(self) -> CompletionLink:
        return CompletionLink(
            id=self.id,
            order_id=self.order_id,
            url=self.url,
            title=self.title,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, link: CompletionLink) -> "CompletionLinkTable":
        return cls(
            id=link.id,
            order_id=link.order_id,
            url=link.url,
            title=link.title,
            created_at=link.created_at,
        )


class FsmStateTable(SQLModel, table=True):
    """Aiogram FSM snapshot stored in Postgres (replaces Redis)."""

    __tablename__ = "fsm_states"
    __table_args__ = (
        UniqueConstraint(
            "bot_id",
            "chat_id",
            "user_id",
            "thread_id",
            "business_connection_id",
            "destiny",
            name="uq_fsm_storage_key",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    bot_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    chat_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    user_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    thread_id: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    business_connection_id: str = Field(default="")
    destiny: str = Field(default="default")
    state: str | None = None
    data: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class WebhookDeliveryTable(SQLModel, table=True):
    """Idempotency keys for GitHub webhook deliveries."""

    __tablename__ = "webhook_deliveries"

    delivery_id: str = Field(primary_key=True, max_length=128)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))


class MilestoneNotificationTable(SQLModel, table=True):
    """Milestone completion notifications already emitted for an order."""

    __tablename__ = "milestone_notifications"
    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "github_milestone_number",
            name="uq_milestone_notifications_order_number",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    github_milestone_number: int = Field(sa_column=Column(Integer, nullable=False))
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))

    def to_domain(self) -> MilestoneNotification:
        return MilestoneNotification(
            id=self.id,
            order_id=self.order_id,
            github_milestone_number=self.github_milestone_number,
            created_at=self.created_at,
        )


class CustomerRequestIssueTable(SQLModel, table=True):
    """Maps a customer-created GitHub issue back to its exact order."""

    __tablename__ = "customer_request_issues"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    github_node_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))

    def to_domain(self) -> CustomerRequestIssue:
        return CustomerRequestIssue(
            id=self.id,
            order_id=self.order_id,
            github_node_id=self.github_node_id,
            created_at=self.created_at,
        )


class OutboxEventTable(SQLModel, table=True):
    """Durable Telegram notifications sent only after the business transaction commits."""

    __tablename__ = "outbox_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kind: str = Field(index=True, max_length=64)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    attempts: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    last_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))
    processed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True, index=True)
    )
