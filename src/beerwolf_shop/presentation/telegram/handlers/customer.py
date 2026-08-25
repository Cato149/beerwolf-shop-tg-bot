"""Customer order list, progress, requests, share, support."""

from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from beerwolf_shop.application.dto import CustomerRequestDTO
from beerwolf_shop.domain.entities import User
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import DomainError
from beerwolf_shop.infrastructure.telegram.keyboards import (
    OrderViewCb,
    confirm_menu,
    customer_order_actions,
    customer_orders_list,
    main_menu,
    render_md,
    wizard_menu,
)
from beerwolf_shop.infrastructure.telegram.markdown import escape_markdown_v2
from beerwolf_shop.presentation.telegram.context import AppContext
from beerwolf_shop.presentation.telegram.formatters import (
    customer_order_card,
    progress_message,
    status_label,
)
from beerwolf_shop.presentation.telegram.handlers.common import LocaleText, reply_error, require_text
from beerwolf_shop.presentation.telegram.states import CustomerRequestWizard, SupportWizard

router = Router(name="customer")


def _blank(i18n, value: str | None) -> str | None:
    if value is None or not value.strip() or i18n.matches(value, "common.btn_skip"):
        return None
    return value.strip()


def _actions(ctx: AppContext, locale: str, order_id: UUID, status: OrderStatus, order_type: OrderType):
    return customer_order_actions(
        ctx.i18n,
        locale,
        order_id,
        status,
        order_type=order_type,
        bot_username=ctx.settings.bot_username,
        share_text=ctx.i18n.get(locale, "customer.share_text"),
    )


@router.message(LocaleText("common.btn_my_orders"))
async def my_orders(message: Message, ctx: AppContext, user: User, locale: str) -> None:
    orders = await ctx.list_customer_orders.execute(user.telegram_id)
    visible = [order for order in orders if order.status != OrderStatus.spam]
    if not visible:
        await message.answer(render_md(ctx.i18n, locale, "order.no_orders"), parse_mode="MarkdownV2")
        return
    items = [(order.id, f"{status_label(ctx.i18n, locale, order.status)} · {order.idea[:40]}") for order in visible]
    await message.answer(
        render_md(ctx.i18n, locale, "common.btn_my_orders"),
        parse_mode="MarkdownV2",
        reply_markup=customer_orders_list(items),
    )


@router.callback_query(OrderViewCb.filter())
async def view_order(
    query: CallbackQuery, callback_data: OrderViewCb, ctx: AppContext, user: User, locale: str
) -> None:
    try:
        order = await ctx.get_order.execute(UUID(callback_data.order_id), actor_telegram_id=user.telegram_id)
    except DomainError:
        await query.answer(ctx.i18n.get(locale, "common.error_generic"), show_alert=True)
        return
    await query.answer()
    text = customer_order_card(ctx.i18n, locale, order)
    if order.status in {OrderStatus.application, OrderStatus.discussion}:
        text = render_md(
            ctx.i18n,
            locale,
            "customer.only_status",
            status=status_label(ctx.i18n, locale, order.status),
        )
    if query.message:
        await query.message.answer(
            text,
            parse_mode="MarkdownV2",
            reply_markup=_actions(ctx, locale, order.id, order.status, order.type),
        )


@router.callback_query(F.data.startswith("cust:prog:"))
async def show_progress(query: CallbackQuery, ctx: AppContext, user: User, locale: str) -> None:
    await query.answer()
    order_id = UUID(query.data.split(":", 2)[2])
    try:
        order = await ctx.get_order.execute(order_id, actor_telegram_id=user.telegram_id)
        snapshot = await ctx.build_progress.execute(order_id, actor_telegram_id=user.telegram_id)
    except DomainError:
        if query.message:
            await query.message.answer(
                render_md(ctx.i18n, locale, "customer.progress_unavailable"),
                parse_mode="MarkdownV2",
            )
        return
    if query.message:
        await query.message.answer(
            progress_message(ctx.i18n, locale, order.project_display_name or order.github_repo or "", snapshot),
            parse_mode="MarkdownV2",
            reply_markup=_actions(ctx, locale, order.id, order.status, order.type),
        )


@router.callback_query(F.data.startswith("cust:req:"))
async def start_request(query: CallbackQuery, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await query.answer()
    order_id = query.data.split(":", 2)[2]
    await state.update_data(order_id=order_id)
    await state.set_state(CustomerRequestWizard.title)
    if query.message:
        await query.message.answer(
            render_md(ctx.i18n, locale, "customer.ask_request_title"),
            parse_mode="MarkdownV2",
            reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
        )


@router.message(CustomerRequestWizard.title)
async def request_title(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    title = await require_text(message, ctx, locale)
    if title is None:
        return
    await state.update_data(title=title)
    await state.set_state(CustomerRequestWizard.body)
    await message.answer(
        render_md(ctx.i18n, locale, "customer.ask_request_body"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
    )


@router.message(CustomerRequestWizard.body)
async def request_body(
    message: Message,
    ctx: AppContext,
    user: User,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    body = await require_text(message, ctx, locale)
    if body is None:
        return
    try:
        url = await ctx.create_request.execute(
            CustomerRequestDTO(
                order_id=UUID(data["order_id"]),
                title=data["title"],
                body=body,
                actor_telegram_id=user.telegram_id,
            )
        )
    except DomainError:
        await reply_error(message, ctx, locale)
        await state.clear()
        return
    await state.clear()
    await message.answer(
        render_md(ctx.i18n, locale, "customer.request_created", url=url),
        parse_mode="MarkdownV2",
        reply_markup=main_menu(ctx.i18n, locale, is_admin=is_admin),
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
        for link in order.links:
            lines.append(render_md(ctx.i18n, locale, "customer.links_item", title=link.title, url=link.url))
        if order.completion_message:
            lines.append(escape_markdown_v2(order.completion_message))
        text = "\n".join(lines)
    if query.message:
        await query.message.answer(
            text,
            parse_mode="MarkdownV2",
            reply_markup=_actions(ctx, locale, order.id, order.status, order.type),
        )


@router.callback_query(F.data.startswith("cust:sup:"))
async def start_support(query: CallbackQuery, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await query.answer()
    await state.update_data(parent_order_id=query.data.split(":", 2)[2])
    await state.set_state(SupportWizard.idea)
    if query.message:
        await query.message.answer(
            render_md(ctx.i18n, locale, "customer.support_intro"),
            parse_mode="MarkdownV2",
            reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
        )


@router.message(SupportWizard.idea)
async def support_idea(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    idea = await require_text(message, ctx, locale)
    if idea is None:
        return
    await state.update_data(idea=idea)
    await state.set_state(SupportWizard.contacts)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_contacts"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(SupportWizard.contacts)
async def support_contacts(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(contacts=_blank(ctx.i18n, message.text))
    await state.set_state(SupportWizard.references)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_references"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(SupportWizard.references)
async def support_references(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(references=_blank(ctx.i18n, message.text))
    await state.set_state(SupportWizard.budget)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_budget"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(SupportWizard.budget)
async def support_budget(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    data = await state.update_data(budget=_blank(ctx.i18n, message.text))
    await state.set_state(SupportWizard.confirm)
    dash = ctx.i18n.get(locale, "order.dash")
    await message.answer(
        render_md(
            ctx.i18n,
            locale,
            "order.confirm_preview",
            name=dash,
            idea=data.get("idea") or dash,
            contacts=data.get("contacts") or dash,
            references=data.get("references") or dash,
            budget=data.get("budget") or dash,
        ),
        parse_mode="MarkdownV2",
        reply_markup=confirm_menu(ctx.i18n, locale),
    )


@router.message(SupportWizard.confirm, LocaleText("common.btn_confirm"))
async def support_confirm(
    message: Message,
    ctx: AppContext,
    user: User,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    try:
        ticket, parent = await ctx.create_support.execute(
            parent_order_id=UUID(data["parent_order_id"]),
            actor_telegram_id=user.telegram_id,
            idea=data["idea"],
            extra_contacts=data.get("contacts"),
            references=data.get("references"),
            budget=data.get("budget"),
        )
    except DomainError:
        await reply_error(message, ctx, locale)
        return
    await ctx.notifier.notify_admins_new_order(ticket, user, locale=ctx.settings.default_locale)
    await state.clear()
    _ = parent
    await message.answer(
        render_md(ctx.i18n, locale, "order.submitted"),
        parse_mode="MarkdownV2",
        reply_markup=main_menu(ctx.i18n, locale, is_admin=is_admin),
    )
