"""Support / revision tickets as separate orders linked to a parent commission."""

from uuid import UUID

from beerwolf_shop.application.dto import SubmitOrderDTO
from beerwolf_shop.application.orders import SubmitOrder, require_order
from beerwolf_shop.domain.entities import Order
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import AccessDeniedError, InvalidStatusTransitionError
from beerwolf_shop.domain.protocols import OrderRepository, UserRepository


class CreateSupportTicket:
    def __init__(self, users: UserRepository, orders: OrderRepository) -> None:
        self._users = users
        self._orders = orders

    async def execute(
        self,
        parent_order_id: UUID,
        actor_telegram_id: int,
        idea: str,
        extra_contacts: str | None = None,
        references: str | None = None,
        budget: str | None = None,
    ) -> tuple[Order, Order]:
        parent = await require_order(self._orders, parent_order_id)
        if parent.customer_telegram_id != actor_telegram_id:
            raise AccessDeniedError("not_owner")
        if parent.status != OrderStatus.completed:
            raise InvalidStatusTransitionError("support_requires_completed")
        if parent.type != OrderType.commission:
            raise InvalidStatusTransitionError("support_requires_commission_parent")
        user = await self._users.get_by_telegram_id(actor_telegram_id)
        ticket = await SubmitOrder(self._users, self._orders).execute(
            SubmitOrderDTO(
                customer_telegram_id=actor_telegram_id,
                display_name=user.display_name if user else str(actor_telegram_id),
                idea=idea,
                extra_contacts=extra_contacts,
                references=references,
                budget=budget,
                username=user.username if user else None,
                language=user.language if user else "ru",
                order_type=OrderType.support,
                parent_order_id=parent.id,
            )
        )
        return ticket, parent
