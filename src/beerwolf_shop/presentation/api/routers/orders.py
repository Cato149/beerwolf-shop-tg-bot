"""Customer-facing order endpoints mirroring the bot use cases."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from beerwolf_shop.application.dto import CustomerRequestDTO, SubmitOrderDTO
from beerwolf_shop.domain.entities import Order
from beerwolf_shop.domain.exceptions import AccessDeniedError, DomainError, OrderNotFoundError
from beerwolf_shop.presentation.api.deps import get_context, get_current_telegram_id
from beerwolf_shop.presentation.api.schemas import (
    CompletionLinkOut,
    CustomerRequestIn,
    CustomerRequestOut,
    OrderCreateIn,
    OrderOut,
    ProgressOut,
    SupportCreateIn,
)
from beerwolf_shop.presentation.telegram.context import AppContext

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def to_order_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        type=order.type,
        status=order.status,
        customer_telegram_id=order.customer_telegram_id,
        idea=order.idea,
        extra_contacts=order.extra_contacts,
        references=order.references,
        budget=order.budget,
        parent_order_id=order.parent_order_id,
        github_repo_url=order.github_repo_url,
        github_owner=order.github_owner,
        github_repo=order.github_repo,
        github_project_id=order.github_project_id,
        project_display_name=order.project_display_name,
        completion_message=order.completion_message,
        created_at=order.created_at,
        updated_at=order.updated_at,
        links=[CompletionLinkOut(id=link.id, url=link.url, title=link.title) for link in order.links],
    )


@router.get(
    "",
    response_model=list[OrderOut],
    summary="List my orders",
    description="Returns commissions and support tickets owned by the authenticated Telegram user. Spam is hidden.",
)
async def list_mine(
    telegram_id: Annotated[int, Depends(get_current_telegram_id)],
    ctx: Annotated[AppContext, Depends(get_context)],
) -> list[OrderOut]:
    orders = await ctx.list_customer_orders.execute(telegram_id)
    return [to_order_out(order) for order in orders if order.status.value != "spam"]


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a commission request",
    description="Creates an `application` commission and notifies admins in Telegram.",
)
async def create_order(
    body: OrderCreateIn,
    telegram_id: Annotated[int, Depends(get_current_telegram_id)],
    ctx: Annotated[AppContext, Depends(get_context)],
) -> OrderOut:
    user = await ctx.users.get_by_telegram_id(telegram_id)
    order = await ctx.submit_order.execute(
        SubmitOrderDTO(
            customer_telegram_id=telegram_id,
            display_name=body.display_name,
            idea=body.idea,
            extra_contacts=body.extra_contacts,
            references=body.references,
            budget=body.budget,
            username=user.username if user else None,
            language=user.language if user else "ru",
        )
    )
    await ctx.notifier.notify_admins_new_order(order, user)
    return to_order_out(order)


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    summary="Get order",
    description="Returns one order owned by the caller.",
)
async def get_order(
    order_id: UUID,
    telegram_id: Annotated[int, Depends(get_current_telegram_id)],
    ctx: Annotated[AppContext, Depends(get_context)],
) -> OrderOut:
    try:
        order = await ctx.get_order.execute(order_id, actor_telegram_id=telegram_id)
    except OrderNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order_not_found") from exc
    except AccessDeniedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden") from exc
    return to_order_out(order)


@router.get(
    "/{order_id}/progress",
    response_model=ProgressOut,
    summary="GitHub progress snapshot",
    description="Counts tasks, builds a text bar, and returns current/next milestones. Available from `in_progress`.",
)
async def progress(
    order_id: UUID,
    telegram_id: Annotated[int, Depends(get_current_telegram_id)],
    ctx: Annotated[AppContext, Depends(get_context)],
) -> ProgressOut:
    try:
        snapshot = await ctx.build_progress.execute(order_id, actor_telegram_id=telegram_id)
    except DomainError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ProgressOut.model_validate(snapshot.model_dump())


@router.get(
    "/{order_id}/links",
    response_model=list[CompletionLinkOut],
    summary="Completion links",
    description="Result URLs stored when the admin marked the order completed.",
)
async def links(
    order_id: UUID,
    telegram_id: Annotated[int, Depends(get_current_telegram_id)],
    ctx: Annotated[AppContext, Depends(get_context)],
) -> list[CompletionLinkOut]:
    try:
        order = await ctx.get_order.execute(order_id, actor_telegram_id=telegram_id)
    except DomainError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return [CompletionLinkOut(id=link.id, url=link.url, title=link.title) for link in order.links]


@router.post(
    "/{order_id}/requests",
    response_model=CustomerRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer request issue",
    description="Opens a GitHub issue labeled `customer request`, adds it to the Project, and sets Status to backlog.",
)
async def create_request(
    order_id: UUID,
    body: CustomerRequestIn,
    telegram_id: Annotated[int, Depends(get_current_telegram_id)],
    ctx: Annotated[AppContext, Depends(get_context)],
) -> CustomerRequestOut:
    try:
        url = await ctx.create_request.execute(
            CustomerRequestDTO(
                order_id=order_id,
                title=body.title,
                body=body.body,
                actor_telegram_id=telegram_id,
            )
        )
    except DomainError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CustomerRequestOut(html_url=url)


@router.post(
    "/{order_id}/support",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Open a support ticket",
    description="Creates a new `support` order linked to a completed commission via `parent_order_id`.",
)
async def create_support(
    order_id: UUID,
    body: SupportCreateIn,
    telegram_id: Annotated[int, Depends(get_current_telegram_id)],
    ctx: Annotated[AppContext, Depends(get_context)],
) -> OrderOut:
    try:
        ticket, _parent = await ctx.create_support.execute(
            parent_order_id=order_id,
            actor_telegram_id=telegram_id,
            idea=body.idea,
            extra_contacts=body.extra_contacts,
            references=body.references,
            budget=body.budget,
        )
    except DomainError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    user = await ctx.users.get_by_telegram_id(telegram_id)
    await ctx.notifier.notify_admins_new_order(ticket, user)
    return to_order_out(ticket)
