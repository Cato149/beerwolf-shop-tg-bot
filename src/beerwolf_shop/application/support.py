"""Support tickets linked to a completed primary commission."""

from uuid import UUID

from beerwolf_shop.application.dto import SubmitOrderDTO
from beerwolf_shop.application.orders import SubmitOrder, require_order
from beerwolf_shop.domain.entities import Order
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import AccessDeniedError, InvalidStatusTransitionError
from beerwolf_shop.domain.protocols import OrderRepository, RollbackRegistry, UserRepository
from beerwolf_shop.infrastructure.github.client import GithubClient


async def _require_locked(orders: OrderRepository, order_id: UUID) -> Order:
    order = await orders.get_for_update(order_id)
    if order is None:
        return await require_order(orders, order_id)
    return order


class CreateSupportTicket:
    def __init__(self, users: UserRepository, orders: OrderRepository) -> None:
        self._users = users
        self._orders = orders

    async def execute(
        self,
        parent_order_id: UUID,
        actor_telegram_id: int,
        idea: str,
    ) -> tuple[Order, Order]:
        await self._orders.lock_customer(actor_telegram_id)
        parent = await _require_locked(self._orders, parent_order_id)
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
                username=user.username if user else None,
                language=user.language if user else "ru",
                order_type=OrderType.support,
                parent_order_id=parent.id,
            )
        )
        return ticket, parent


class TakeSupportTicket:
    """Create a dedicated milestone and reopen the parent while support is active."""

    def __init__(
        self,
        orders: OrderRepository,
        github: GithubClient,
        rollback_registry: RollbackRegistry | None = None,
    ) -> None:
        self._orders = orders
        self._github = github
        self._rollback_registry = rollback_registry

    async def execute(self, ticket_id: UUID) -> tuple[Order, Order]:
        ticket = await _require_locked(self._orders, ticket_id)
        await self._orders.lock_customer(ticket.customer_telegram_id)
        if ticket.type != OrderType.support or ticket.status != OrderStatus.application:
            raise InvalidStatusTransitionError("support_take_requires_application")
        if ticket.parent_order_id is None:
            raise InvalidStatusTransitionError("support_parent_missing")
        parent = await _require_locked(self._orders, ticket.parent_order_id)
        if parent.status != OrderStatus.completed or not parent.github_owner or not parent.github_repo:
            raise InvalidStatusTransitionError("support_parent_must_be_completed_and_linked")
        if await self._orders.get_active_commission(ticket.customer_telegram_id):
            raise InvalidStatusTransitionError("another_commission_is_active")

        wish = " ".join(ticket.idea.split())
        title = f"Доработка {str(ticket.id)[:8]}: {wish}"[:256]
        milestone = await self._github.create_milestone(parent.github_owner, parent.github_repo, title)
        if self._rollback_registry:
            self._rollback_registry.register(
                lambda: self._github.delete_milestone(
                    parent.github_owner or "",
                    parent.github_repo or "",
                    milestone.number,
                )
            )

        ticket.github_repo_url = parent.github_repo_url
        ticket.github_owner = parent.github_owner
        ticket.github_repo = parent.github_repo
        ticket.github_project_id = parent.github_project_id
        ticket.project_display_name = parent.project_display_name
        ticket.github_milestone_number = milestone.number
        ticket.github_milestone_title = milestone.title
        ticket.status = OrderStatus.in_progress
        ticket.touch()
        parent.status = OrderStatus.in_progress
        parent.touch()
        return await self._orders.save(ticket), await self._orders.save(parent)


class CancelSupportTicket:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def execute(self, ticket_id: UUID) -> tuple[Order, Order]:
        ticket = await _require_locked(self._orders, ticket_id)
        if ticket.type != OrderType.support or ticket.status != OrderStatus.application:
            raise InvalidStatusTransitionError("support_cancel_requires_application")
        if ticket.parent_order_id is None:
            raise InvalidStatusTransitionError("support_parent_missing")
        parent = await _require_locked(self._orders, ticket.parent_order_id)
        ticket.status = OrderStatus.cancelled
        ticket.touch()
        return await self._orders.save(ticket), parent


class CompleteSupportTicket:
    def __init__(
        self,
        orders: OrderRepository,
        github: GithubClient,
        rollback_registry: RollbackRegistry | None = None,
    ) -> None:
        self._orders = orders
        self._github = github
        self._rollback_registry = rollback_registry

    async def execute(self, ticket_id: UUID) -> tuple[Order, Order]:
        ticket = await _require_locked(self._orders, ticket_id)
        if ticket.type != OrderType.support or ticket.status != OrderStatus.in_progress:
            raise InvalidStatusTransitionError("support_complete_requires_in_progress")
        if ticket.parent_order_id is None:
            raise InvalidStatusTransitionError("support_parent_missing")
        parent = await _require_locked(self._orders, ticket.parent_order_id)
        if ticket.github_owner and ticket.github_repo and ticket.github_milestone_number:
            await self._github.set_milestone_state(
                ticket.github_owner,
                ticket.github_repo,
                ticket.github_milestone_number,
                "closed",
            )
            if self._rollback_registry:
                self._rollback_registry.register(
                    lambda: self._github.set_milestone_state(
                        ticket.github_owner or "",
                        ticket.github_repo or "",
                        ticket.github_milestone_number or 0,
                        "open",
                    )
                )
        ticket.status = OrderStatus.completed
        ticket.touch()
        parent.status = OrderStatus.completed
        parent.touch()
        return await self._orders.save(ticket), await self._orders.save(parent)
