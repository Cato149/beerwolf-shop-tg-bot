"""Admin REST: list/filter, manual create, status pipeline."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from beerwolf_shop.application.dto import CompleteOrderDTO, LinkGithubDTO, ManualOrderDTO
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import DomainError, GithubIntegrationError, OrderNotFoundError
from beerwolf_shop.presentation.api.deps import get_context, require_admin
from beerwolf_shop.presentation.api.routers.orders import to_order_out
from beerwolf_shop.presentation.api.schemas import (
    ManualOrderIn,
    OrderListResponse,
    OrderOut,
    ProjectChoiceResponse,
    ProjectOption,
    StatusChangeIn,
)
from beerwolf_shop.presentation.telegram.context import AppContext

router = APIRouter(
    prefix="/api/v1/admin/orders",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "",
    response_model=OrderListResponse,
    summary="List orders (admin)",
    description="Paginated list with optional status and type filters, including spam and support tickets.",
)
async def list_orders(
    ctx: Annotated[AppContext, Depends(get_context)],
    status_filter: Annotated[
        OrderStatus | None, Query(alias="status", description="Filter by pipeline status.")
    ] = None,
    order_type: Annotated[
        OrderType | None, Query(alias="type", description="Filter by `commission` or `support`.")
    ] = None,
    offset: Annotated[int, Query(ge=0, description="Pagination offset.")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size.")] = 20,
) -> OrderListResponse:
    items, total = await ctx.list_orders.execute(status_filter, order_type, offset=offset, limit=limit)
    return OrderListResponse(items=[to_order_out(order) for order in items], total=total)


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an order for a customer",
    description=(
        "Admin-created request. The customer may not have pressed /start yet; "
        "Telegram delivery happens only after the first contact with the bot."
    ),
)
async def create_manual(
    body: ManualOrderIn,
    ctx: Annotated[AppContext, Depends(get_context)],
) -> OrderOut:
    try:
        order = await ctx.create_manual.execute(
            ManualOrderDTO(
                customer_telegram_id=body.customer_telegram_id,
                customer_username=body.customer_username,
                display_name=body.display_name,
                idea=body.idea,
                extra_contacts=body.extra_contacts,
                references=body.references,
                budget=body.budget,
                order_type=body.type,
            )
        )
    except DomainError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
    await ctx.notifier.notify_admins_new_order(order, customer)
    return to_order_out(order)


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    summary="Get any order (admin)",
    description="Full order card including GitHub fields and completion links.",
)
async def get_order(order_id: UUID, ctx: Annotated[AppContext, Depends(get_context)]) -> OrderOut:
    try:
        order = await ctx.get_order.execute(order_id, is_admin=True)
    except OrderNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order_not_found") from exc
    return to_order_out(order)


@router.post(
    "/{order_id}/status",
    response_model=OrderOut | ProjectChoiceResponse,
    summary="Change order status",
    description=(
        "Moves an order along the pipeline. `spam` does not notify the customer. "
        "`discussion` sends ADMIN_TELEGRAM_CONTACT. `in_progress` links GitHub. "
        "`completed` stores links and notifies the customer."
    ),
)
async def change_status(
    order_id: UUID,
    body: StatusChangeIn,
    ctx: Annotated[AppContext, Depends(get_context)],
) -> OrderOut | ProjectChoiceResponse:
    try:
        if body.status == OrderStatus.spam:
            order = await ctx.mark_spam.execute(order_id)
            return to_order_out(order)
        if body.status == OrderStatus.discussion:
            order = await ctx.start_discussion.execute(order_id)
            customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
            locale = customer.language if customer else ctx.settings.default_locale
            await ctx.notifier.notify_customer(
                order.customer_telegram_id,
                locale,
                "order.discussion_started",
                contact=ctx.settings.admin_telegram_contact,
            )
            return to_order_out(order)
        if body.status == OrderStatus.in_progress:
            if not body.github_repo_url or not body.project_display_name:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "github_fields_required")
            order, _milestones, projects = await ctx.start_in_progress.execute(
                LinkGithubDTO(
                    order_id=order_id,
                    repo_url=body.github_repo_url,
                    project_display_name=body.project_display_name,
                    project_id=body.github_project_id,
                )
            )
            if body.github_project_id is None and len(projects) > 1 and not order.github_project_id:
                return ProjectChoiceResponse(
                    detail="multiple_projects",
                    projects=[ProjectOption(id=item.id, title=item.title) for item in projects],
                )
            customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
            locale = customer.language if customer else ctx.settings.default_locale
            await ctx.notifier.notify_customer(
                order.customer_telegram_id,
                locale,
                "order.in_progress_started",
                project=order.project_display_name or "",
                repo=order.github_repo_url or "",
                milestones="",
            )
            return to_order_out(order)
        if body.status == OrderStatus.completed:
            links = [(item.url, item.title or item.url) for item in (body.links or [])]
            order = await ctx.complete_order.execute(
                CompleteOrderDTO(order_id=order_id, links=links, message=body.message)
            )
            customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
            locale = customer.language if customer else ctx.settings.default_locale
            await ctx.notifier.notify_customer(
                order.customer_telegram_id,
                locale,
                "order.completed_customer",
                message=body.message or "",
            )
            return to_order_out(order)
        order = await ctx.change_status.execute(order_id, body.status)
        return to_order_out(order)
    except GithubIntegrationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
