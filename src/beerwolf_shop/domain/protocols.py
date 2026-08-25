"""Repository and gateway protocols (ports)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from beerwolf_shop.domain.entities import CompletionLink, Order, User
from beerwolf_shop.domain.enums import OrderStatus, OrderType


class UserRepository(Protocol):
    async def get_by_telegram_id(self, telegram_id: int) -> User | None: ...

    async def get_by_username(self, username: str) -> User | None: ...

    async def add(self, user: User) -> User: ...

    async def save(self, user: User) -> User: ...


class OrderRepository(Protocol):
    async def get(self, order_id: UUID) -> Order | None: ...

    async def add(self, order: Order) -> Order: ...

    async def save(self, order: Order) -> Order: ...

    async def list_by_status(
        self,
        status: OrderStatus | None,
        order_type: OrderType | None = None,
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> list[Order]: ...

    async def count_by_status(
        self,
        status: OrderStatus | None,
        order_type: OrderType | None = None,
    ) -> int: ...

    async def list_for_customer(self, telegram_id: int) -> list[Order]: ...

    async def find_by_repo(self, owner: str, repo: str) -> list[Order]: ...


class CompletionLinkRepository(Protocol):
    async def list_for_order(self, order_id: UUID) -> list[CompletionLink]: ...

    async def replace_for_order(self, order_id: UUID, links: list[CompletionLink]) -> None: ...


class WebhookDeliveryRepository(Protocol):
    async def seen(self, delivery_id: str) -> bool: ...

    async def mark(self, delivery_id: str) -> None: ...
