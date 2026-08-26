"""Domain entities (pure dataclasses, no ORM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from beerwolf_shop.domain.enums import OrderStatus, OrderType


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class User:
    telegram_id: int
    username: str | None
    display_name: str
    language: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class CompletionLink:
    order_id: UUID
    url: str
    title: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class MilestoneNotification:
    """A completed milestone already announced for an order."""

    order_id: UUID
    github_milestone_number: int
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class CustomerRequestIssue:
    """Persistent ownership of a customer-created GitHub issue."""

    order_id: UUID
    github_node_id: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class Order:
    customer_telegram_id: int
    type: OrderType
    idea: str
    extra_contacts: str | None = None
    references: str | None = None
    budget: str | None = None
    status: OrderStatus = OrderStatus.application
    parent_order_id: UUID | None = None
    github_repo_url: str | None = None
    github_owner: str | None = None
    github_repo: str | None = None
    github_project_id: str | None = None
    github_milestone_number: int | None = None
    github_milestone_title: str | None = None
    project_display_name: str | None = None
    completion_message: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    links: list[CompletionLink] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = _utcnow()
