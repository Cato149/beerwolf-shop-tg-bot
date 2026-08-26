"""Customer project, progress, revisions, recommendation and support."""

from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from beerwolf_shop.application.dto import CustomerRequestDTO
from beerwolf_shop.domain.entities import Order, User
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import DomainError
from beerwolf_shop.infrastructure.telegram.keyboards import (
    MilestoneCb,
    OrderViewCb,
    customer_order_actions,
    milestone_back,
    progress_milestones,
    recommendation_share,
    render_md,
    wizard_menu,
)
from beerwolf_shop.infrastructure.telegram.markdown import escape_html
from beerwolf_shop.presentation.telegram.context import AppContext
from beerwolf_shop.presentation.telegram.formatters import (
    customer_order_card,
    milestone_message,
    progress_message,
    status_label,
)
from beerwolf_shop.presentation.telegram.handlers.common import (
    LocaleText,
    build_main_menu,
    reply_error,
    require_text,
)
from beerwolf_shop.presentation.telegram.states import CustomerRequestWizard, SupportWizard

router = Router(name="customer")


def _actions(ctx: AppContext, locale: str, order: Order):
    return customer_order_actions(
        ctx.i18n,
        locale,
        order.id,
        order.status,
        order_type=order.type,
    )


async def _send_project(message: Message, ctx: AppContext, user: User, locale: str, order: Order) -> None:
    if order.status == OrderStatus.in_progress:
        try:
            snapshot = await ctx.build_progress.execute(order.id, actor_telegram_id=user.telegram_id)
        except DomainError:
            await message.answer(
                render_md(ctx.i18n, locale, "customer.progress_unavailable"),
                parse_mode="HTML",
            )
            return
        await message.answer(
            progress_message(ctx.i18n, locale, order.project_display_name or "", snapshot),
            parse_mode="HTML",
            reply_markup=progress_milestones(
                ctx.i18n,
                locale,
                order.id,
                snapshot.milestones,
                show_request=order.type == OrderType.commission,
            ),
        )
        return
    if order.status in {OrderStatus.application, OrderStatus.discussion}:
        text = render_md(
            ctx.i18n,
            locale,
            "customer.only_status",
            status=status_label(ctx.i18n, locale, order.status),
        )
    else:
        text = customer_order_card(ctx.i18n, locale, order)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=_actions(ctx, locale, order),
    )


@router.message(LocaleText("common.btn_my_order"))
async def my_order(message: Message, ctx: AppContext, user: User, locale: str) -> None:
    order = await ctx.get_customer_project.execute(user.telegram_id)
    if order is None:
        await message.answer(render_md(ctx.i18n, locale, "order.no_orders"), parse_mode="HTML")
        return
    await _send_project(message, ctx, user, locale, order)


@router.callback_query(OrderViewCb.filter())
async def view_order(
    query: CallbackQuery,
    callback_data: OrderViewCb,
    ctx: AppContext,
    user: User,
    locale: str,
) -> None:
    try:
        order = await ctx.get_order.execute(UUID(callback_data.order_id), actor_telegram_id=user.telegram_id)
    except DomainError:
        await query.answer(ctx.i18n.get(locale, "common.error_generic"), show_alert=True)
        return
    await query.answer()
    if query.message:
        await _send_project(query.message, ctx, user, locale, order)


@router.callback_query(F.data.startswith("cust:prog:"))
async def show_progress(query: CallbackQuery, ctx: AppContext, user: User, locale: str) -> None:
    order_id = UUID(query.data.split(":", 2)[2])
    await query.answer()
    if query.message:
        order = await ctx.get_order.execute(order_id, actor_telegram_id=user.telegram_id)
        await _send_project(query.message, ctx, user, locale, order)


@router.callback_query(MilestoneCb.filter(F.action == "open"))
async def show_milestone(
    query: CallbackQuery,
    callback_data: MilestoneCb,
    ctx: AppContext,
    user: User,
    locale: str,
) -> None:
    try:
        details = await ctx.get_milestone_details.execute(
            UUID(callback_data.order_id),
            callback_data.number,
            actor_telegram_id=user.telegram_id,
        )
    except DomainError:
        await query.answer(ctx.i18n.get(locale, "common.error_generic"), show_alert=True)
        return
    await query.answer()
    if query.message:
        await query.message.answer(
            milestone_message(ctx.i18n, locale, details),
            parse_mode="HTML",
            reply_markup=milestone_back(ctx.i18n, locale, UUID(callback_data.order_id)),
        )


@router.callback_query(MilestoneCb.filter(F.action == "back"))
async def milestone_return(
    query: CallbackQuery,
    callback_data: MilestoneCb,
    ctx: AppContext,
    user: User,
    locale: str,
) -> None:
    await query.answer()
    if query.message:
        order = await ctx.get_order.execute(UUID(callback_data.order_id), actor_telegram_id=user.telegram_id)
        await _send_project(query.message, ctx, user, locale, order)


@router.message(LocaleText("customer.btn_recommend"))
async def recommend(message: Message, ctx: AppContext, locale: str) -> None:
    if not ctx.settings.bot_username:
        await message.answer(render_md(ctx.i18n, locale, "common.error_generic"), parse_mode="HTML")
        return
    await message.answer(
        render_md(ctx.i18n, locale, "customer.recommend_text"),
        parse_mode="HTML",
        reply_markup=recommendation_share(
            ctx.i18n,
            locale,
            ctx.settings.bot_username,
            ctx.i18n.get(locale, "customer.share_text"),
        ),
    )


@router.callback_query(F.data.startswith("cust:req:"))
async def start_request(query: CallbackQuery, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await query.answer()
    await state.update_data(order_id=query.data.split(":", 2)[2])
    await state.set_state(CustomerRequestWizard.wish)
    if query.message:
        await query.message.answer(
            render_md(ctx.i18n, locale, "customer.ask_request_wish"),
            parse_mode="HTML",
            reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
        )


@router.message(CustomerRequestWizard.wish)
async def request_wish(
    message: Message,
    ctx: AppContext,
    user: User,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    wish = await require_text(message, ctx, locale)
    if wish is None:
        return
    data = await state.get_data()
    try:
        order = await ctx.get_order.execute(UUID(data["order_id"]), actor_telegram_id=user.telegram_id)
        issue = await ctx.create_request.execute(
            CustomerRequestDTO(
                order_id=order.id,
                wish=wish,
                actor_telegram_id=user.telegram_id,
            )
        )
    except DomainError:
        await reply_error(message, ctx, locale)
        await state.clear()
        return
    await ctx.notifier.notify_admins_customer_request(
        order,
        user,
        issue.title,
        wish,
        issue.html_url,
        locale=ctx.settings.default_locale,
    )
    await state.clear()
    await message.answer(
        render_md(ctx.i18n, locale, "customer.request_created", url=issue.html_url),
        parse_mode="HTML",
        reply_markup=await build_main_menu(ctx, user, locale, is_admin),
    )


@router.callback_query(F.data.startswith("cust:links:"))
async def show_links(query: CallbackQuery, ctx: AppContext, user: User, locale: str) -> None:
    order_id = UUID(query.data.split(":", 2)[2])
    try:
        order = await ctx.get_order.execute(order_id, actor_telegram_id=user.telegram_id)
    except DomainError:
        await query.answer(ctx.i18n.get(locale, "common.error_generic"), show_alert=True)
        return
    await query.answer()
    if not order.links:
        text = render_md(ctx.i18n, locale, "customer.no_links")
    else:
        lines = [render_md(ctx.i18n, locale, "customer.links_header")]
        lines.extend(
            render_md(ctx.i18n, locale, "customer.links_item", title=link.title, url=link.url)
            for link in order.links
        )
        if order.completion_message:
            lines.append(escape_html(order.completion_message))
        text = "\n".join(lines)
    if query.message:
        await query.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=_actions(ctx, locale, order),
        )


@router.callback_query(F.data.startswith("cust:sup:"))
async def start_support(query: CallbackQuery, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await query.answer()
    await state.update_data(parent_order_id=query.data.split(":", 2)[2])
    await state.set_state(SupportWizard.wish)
    if query.message:
        await query.message.answer(
            render_md(ctx.i18n, locale, "customer.support_intro"),
            parse_mode="HTML",
            reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
        )


@router.message(SupportWizard.wish)
async def support_wish(
    message: Message,
    ctx: AppContext,
    user: User,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    wish = await require_text(message, ctx, locale)
    if wish is None:
        return
    data = await state.get_data()
    try:
        ticket, _parent = await ctx.create_support.execute(
            parent_order_id=UUID(data["parent_order_id"]),
            actor_telegram_id=user.telegram_id,
            idea=wish,
        )
    except DomainError:
        await reply_error(message, ctx, locale)
        return
    await ctx.notifier.notify_admins_new_order(ticket, user, locale=ctx.settings.default_locale)
    await state.clear()
    await message.answer(
        render_md(ctx.i18n, locale, "customer.support_submitted"),
        parse_mode="HTML",
        reply_markup=await build_main_menu(ctx, user, locale, is_admin),
    )
