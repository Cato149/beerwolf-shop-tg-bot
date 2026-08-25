"""Order lifecycle use cases."""

from __future__ import annotations

from uuid import UUID

from beerwolf_shop.application.dto import CompleteOrderDTO, ManualOrderDTO, SubmitOrderDTO
from beerwolf_shop.domain.entities import CompletionLink, Order, User
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import (
    AccessDeniedError,
    InvalidStatusTransitionError,
    OrderNotFoundError,
    UserNotFoundError,
)
from beerwolf_shop.domain.protocols import CompletionLinkRepository, OrderRepository, UserRepository

ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.application: {OrderStatus.discussion, OrderStatus.spam},
    OrderStatus.discussion: {OrderStatus.in_progress, OrderStatus.spam, OrderStatus.application},
    OrderStatus.in_progress: {OrderStatus.completed, OrderStatus.discussion},
    OrderStatus.completed: set(),
    OrderStatus.spam: {OrderStatus.application},
}


async def require_order(orders: OrderRepository, order_id: UUID) -> Order:
    order = await orders.get(order_id)
    if order is None:
        raise OrderNotFoundError(str(order_id))
    return order


def assert_owner(order: Order, telegram_id: int) -> None:
    if order.customer_telegram_id != telegram_id:
        raise AccessDeniedError("not_owner")


class SubmitOrder:
    def __init__(self, users: UserRepository, orders: OrderRepository) -> None:
        self._users = users
        self._orders = orders

    async def execute(self, dto: SubmitOrderDTO) -> Order:
        user = await self._users.get_by_telegram_id(dto.customer_telegram_id)
        if user is None:
            user = User(
                telegram_id=dto.customer_telegram_id,
                username=dto.username,
                display_name=dto.display_name,
                language=dto.language,
            )
            await self._users.add(user)
        else:
            user.display_name = dto.display_name
            if dto.username:
                user.username = dto.username
            await self._users.save(user)
        order = Order(
            customer_telegram_id=dto.customer_telegram_id,
            type=dto.order_type,
            idea=dto.idea,
            extra_contacts=dto.extra_contacts,
            references=dto.references,
            budget=dto.budget,
            parent_order_id=dto.parent_order_id,
            status=OrderStatus.application,
        )
        return await self._orders.add(order)


class CreateManualOrder:
    def __init__(self, users: UserRepository, orders: OrderRepository) -> None:
        self._users = users
        self._orders = orders

    async def execute(self, dto: ManualOrderDTO) -> Order:
        telegram_id = dto.customer_telegram_id
        if telegram_id is None and dto.customer_username:
            found = await self._users.get_by_username(dto.customer_username)
            if found is None:
                raise UserNotFoundError(dto.customer_username)
            telegram_id = found.telegram_id
        if telegram_id is None:
            raise UserNotFoundError("missing_customer")
        submit = SubmitOrder(self._users, self._orders)
        return await submit.execute(
            SubmitOrderDTO(
                customer_telegram_id=telegram_id,
                display_name=dto.display_name,
                idea=dto.idea,
                extra_contacts=dto.extra_contacts,
                references=dto.references,
                budget=dto.budget,
                username=dto.customer_username,
                order_type=dto.order_type,
            )
        )


class ListOrders:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def execute(
        self,
        status: OrderStatus | None = None,
        order_type: OrderType | None = None,
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> tuple[list[Order], int]:
        items = await self._orders.list_by_status(status, order_type, offset=offset, limit=limit)
        total = await self._orders.count_by_status(status, order_type)
        return items, total


class GetOrder:
    def __init__(self, orders: OrderRepository, links: CompletionLinkRepository) -> None:
        self._orders = orders
        self._links = links

    async def execute(self, order_id: UUID, *, actor_telegram_id: int | None = None, is_admin: bool = False) -> Order:
        order = await require_order(self._orders, order_id)
        if not is_admin and actor_telegram_id is not None:
            assert_owner(order, actor_telegram_id)
        order.links = await self._links.list_for_order(order.id)
        return order


class ListCustomerOrders:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def execute(self, telegram_id: int) -> list[Order]:
        return await self._orders.list_for_customer(telegram_id)


class ChangeStatus:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def execute(self, order_id: UUID, new_status: OrderStatus) -> Order:
        order = await require_order(self._orders, order_id)
        allowed = ALLOWED_TRANSITIONS.get(order.status, set())
        if new_status not in allowed:
            raise InvalidStatusTransitionError(f"{order.status}->{new_status}")
        order.status = new_status
        order.touch()
        return await self._orders.save(order)


class MarkSpam:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def execute(self, order_id: UUID) -> Order:
        return await ChangeStatus(self._orders).execute(order_id, OrderStatus.spam)


class StartDiscussion:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def execute(self, order_id: UUID) -> Order:
        return await ChangeStatus(self._orders).execute(order_id, OrderStatus.discussion)


class CompleteOrder:
    def __init__(self, orders: OrderRepository, links: CompletionLinkRepository) -> None:
        self._orders = orders
        self._links = links

    async def execute(self, dto: CompleteOrderDTO) -> Order:
        order = await require_order(self._orders, dto.order_id)
        if order.status != OrderStatus.in_progress:
            raise InvalidStatusTransitionError(f"{order.status}->completed")
        order.status = OrderStatus.completed
        order.completion_message = dto.message
        order.touch()
        saved = await self._orders.save(order)
        stored = [
            CompletionLink(order_id=saved.id, url=url, title=title or url) for url, title in dto.links if url.strip()
        ]
        await self._links.replace_for_order(saved.id, stored)
        saved.links = stored
        return saved
