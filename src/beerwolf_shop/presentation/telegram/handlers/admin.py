"""Admin list/filter, status pipeline, GitHub link, complete, manual create."""

from __future__ import annotations

import logging
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from beerwolf_shop.application.dto import CompleteOrderDTO, LinkGithubDTO, ManualOrderDTO
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import DomainError, GithubIntegrationError
from beerwolf_shop.infrastructure.telegram.keyboards import (
    STATUS_FILTERS,
    AdminListCb,
    AdminOrderCb,
    ProjectPickCb,
    admin_menu,
    confirm_menu,
    main_menu,
    project_choice,
    render_md,
    wizard_menu,
)
from beerwolf_shop.infrastructure.telegram.keyboards import (
    admin_order_card as admin_order_kb,
)
from beerwolf_shop.presentation.telegram.context import AppContext
from beerwolf_shop.presentation.telegram.formatters import (
    admin_order_card,
    list_title,
)
from beerwolf_shop.presentation.telegram.states import (
    AdminComplete,
    AdminLinkGithub,
    AdminManualWizard,
)

logger = logging.getLogger(__name__)
router = Router(name="admin")

PAGE_SIZE = 5
SKIP = {"Пропустить", "Skip"}
CONFIRM = {"Подтвердить", "Confirm"}
ADMIN_MENU = {"Админка", "Admin"}


def _blank(value: str | None) -> str | None:
    if value is None or value.strip() in SKIP or not value.strip():
        return None
    return value.strip()


def _status_from_filter(key: str) -> OrderStatus | None:
    for name, status in STATUS_FILTERS:
        if name == key:
            return status
    return None


async def _require_admin(query_or_message: CallbackQuery | Message, is_admin: bool) -> bool:
    if is_admin:
        return True
    if isinstance(query_or_message, CallbackQuery):
        await query_or_message.answer("forbidden", show_alert=True)
    return False


@router.message(F.text.in_(ADMIN_MENU))
@router.message(Command("admin"))
async def open_admin(message: Message, ctx: AppContext, locale: str, is_admin: bool) -> None:
    if not is_admin:
        return
    await message.answer(
        render_md(ctx.i18n, locale, "admin.menu"),
        parse_mode="MarkdownV2",
        reply_markup=admin_menu(ctx.i18n, locale),
    )


async def _send_order_list(
    target: Message,
    ctx: AppContext,
    locale: str,
    status_key: str,
    page: int,
    *,
    order_type: OrderType | None = None,
) -> None:
    status = _status_from_filter(status_key)
    offset = page * PAGE_SIZE
    items, total = await ctx.list_orders.execute(status, order_type, offset=offset, limit=PAGE_SIZE)
    if not items:
        await target.answer(render_md(ctx.i18n, locale, "admin.list_empty"), parse_mode="MarkdownV2")
        return
    from beerwolf_shop.infrastructure.telegram.keyboards import admin_list_keyboard

    buttons = [(order.id, list_title(order, ctx.i18n, locale)) for order in items]
    has_next = offset + PAGE_SIZE < total
    await target.answer(
        render_md(ctx.i18n, locale, "admin.btn_orders"),
        parse_mode="MarkdownV2",
        reply_markup=admin_list_keyboard(
            ctx.i18n, locale, current=status_key, page=page, has_next=has_next, orders=buttons
        ),
    )


@router.callback_query(AdminListCb.filter())
async def list_orders_cb(
    query: CallbackQuery,
    callback_data: AdminListCb,
    ctx: AppContext,
    locale: str,
    is_admin: bool,
) -> None:
    if not await _require_admin(query, is_admin):
        return
    await query.answer()
    if query.message:
        await _send_order_list(query.message, ctx, locale, callback_data.status, callback_data.page)


@router.callback_query(F.data == "admin:support")
async def support_queue(query: CallbackQuery, ctx: AppContext, locale: str, is_admin: bool) -> None:
    if not await _require_admin(query, is_admin):
        return
    await query.answer()
    items, _total = await ctx.list_orders.execute(OrderStatus.application, OrderType.support, offset=0, limit=PAGE_SIZE)
    if query.message:
        if not items:
            await query.message.answer(render_md(ctx.i18n, locale, "admin.list_empty"), parse_mode="MarkdownV2")
            return
        from beerwolf_shop.infrastructure.telegram.keyboards import admin_list_keyboard

        buttons = [(order.id, list_title(order, ctx.i18n, locale)) for order in items]
        await query.message.answer(
            render_md(ctx.i18n, locale, "admin.btn_support_queue"),
            parse_mode="MarkdownV2",
            reply_markup=admin_list_keyboard(
                ctx.i18n, locale, current="application", page=0, has_next=False, orders=buttons
            ),
        )


async def _show_admin_card(message: Message, ctx: AppContext, locale: str, order_id: UUID) -> None:
    order = await ctx.get_order.execute(order_id, is_admin=True)
    customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
    parent = await ctx.orders.get(order.parent_order_id) if order.parent_order_id else None
    text = admin_order_card(ctx.i18n, locale, order, customer, parent)
    if parent and parent.github_repo_url:
        text += "\n" + render_md(ctx.i18n, locale, "admin.support_card_extra", repo=parent.github_repo_url)
    await message.answer(
        text,
        parse_mode="MarkdownV2",
        reply_markup=admin_order_kb(order.id, order.status, ctx.i18n, locale),
    )


@router.callback_query(AdminOrderCb.filter(F.action == "view"))
async def view_order(
    query: CallbackQuery, callback_data: AdminOrderCb, ctx: AppContext, locale: str, is_admin: bool
) -> None:
    if not await _require_admin(query, is_admin):
        return
    await query.answer()
    if query.message:
        await _show_admin_card(query.message, ctx, locale, UUID(callback_data.order_id))


@router.callback_query(AdminOrderCb.filter(F.action == "spam"))
async def mark_spam(
    query: CallbackQuery, callback_data: AdminOrderCb, ctx: AppContext, locale: str, is_admin: bool
) -> None:
    if not await _require_admin(query, is_admin):
        return
    await ctx.mark_spam.execute(UUID(callback_data.order_id))
    await query.answer()
    if query.message:
        await query.message.answer(render_md(ctx.i18n, locale, "admin.spam_marked"), parse_mode="MarkdownV2")


@router.callback_query(AdminOrderCb.filter(F.action == "disc"))
async def start_discussion(
    query: CallbackQuery,
    callback_data: AdminOrderCb,
    ctx: AppContext,
    locale: str,
    is_admin: bool,
) -> None:
    if not await _require_admin(query, is_admin):
        return
    order = await ctx.start_discussion.execute(UUID(callback_data.order_id))
    customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
    customer_locale = customer.language if customer else ctx.settings.default_locale
    await ctx.notifier.notify_customer(
        order.customer_telegram_id,
        customer_locale,
        "order.discussion_started",
        contact=ctx.settings.admin_telegram_contact,
    )
    await query.answer()
    if query.message:
        await query.message.answer(render_md(ctx.i18n, locale, "admin.discussion_marked"), parse_mode="MarkdownV2")


@router.callback_query(AdminOrderCb.filter(F.action == "ip"))
async def start_in_progress(
    query: CallbackQuery,
    callback_data: AdminOrderCb,
    ctx: AppContext,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    if not await _require_admin(query, is_admin):
        return
    await state.update_data(order_id=callback_data.order_id)
    await state.set_state(AdminLinkGithub.repo_url)
    await query.answer()
    if query.message:
        await query.message.answer(
            render_md(ctx.i18n, locale, "admin.ask_repo_url"),
            parse_mode="MarkdownV2",
            reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
        )


@router.message(AdminLinkGithub.repo_url)
async def got_repo(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(repo_url=(message.text or "").strip())
    await state.set_state(AdminLinkGithub.project_name)
    await message.answer(
        render_md(ctx.i18n, locale, "admin.ask_project_name"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
    )


async def _finish_link(
    message: Message,
    ctx: AppContext,
    locale: str,
    is_admin: bool,
    state: FSMContext,
    project_id: str | None,
) -> None:
    data = await state.get_data()
    try:
        order, milestones, projects = await ctx.start_in_progress.execute(
            LinkGithubDTO(
                order_id=UUID(data["order_id"]),
                repo_url=data["repo_url"],
                project_display_name=data["project_display_name"],
                project_id=project_id,
            )
        )
    except GithubIntegrationError:
        await message.answer(render_md(ctx.i18n, locale, "admin.repo_fail"), parse_mode="MarkdownV2")
        return
    if project_id is None and len(projects) > 1:
        await state.update_data(projects=[{"id": p.id, "title": p.title} for p in projects])
        await state.set_state(AdminLinkGithub.project_choice)
        await message.answer(
            render_md(ctx.i18n, locale, "admin.choose_project"),
            parse_mode="MarkdownV2",
            reply_markup=project_choice([(p.id, p.title) for p in projects]),
        )
        return
    lines = []
    for milestone in milestones:
        due = f" ({milestone.due_on[:10]})" if milestone.due_on else ""
        lines.append(f"• {milestone.title}{due}")
    milestone_text = "\n".join(lines) if lines else ctx.i18n.get(locale, "progress.no_milestones")
    customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
    customer_locale = customer.language if customer else ctx.settings.default_locale
    await ctx.notifier.notify_customer(
        order.customer_telegram_id,
        customer_locale,
        "order.in_progress_started",
        project=order.project_display_name or "",
        repo=order.github_repo_url or "",
        milestones=milestone_text,
    )
    await state.clear()
    await message.answer(
        render_md(
            ctx.i18n,
            locale,
            "order.in_progress_started",
            project=order.project_display_name or "",
            repo=order.github_repo_url or "",
            milestones=milestone_text,
        ),
        parse_mode="MarkdownV2",
        reply_markup=main_menu(ctx.i18n, locale, is_admin=is_admin),
    )


@router.message(AdminLinkGithub.project_name)
async def got_project_name(
    message: Message,
    ctx: AppContext,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    await state.update_data(project_display_name=(message.text or "").strip())
    await _finish_link(message, ctx, locale, is_admin, state, project_id=None)


@router.callback_query(ProjectPickCb.filter())
async def pick_project(
    query: CallbackQuery,
    callback_data: ProjectPickCb,
    ctx: AppContext,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    if not await _require_admin(query, is_admin):
        return
    data = await state.get_data()
    projects = data.get("projects") or []
    chosen = projects[callback_data.idx]
    await query.answer()
    if query.message:
        await _finish_link(query.message, ctx, locale, is_admin, state, project_id=chosen["id"])


@router.callback_query(AdminOrderCb.filter(F.action == "done"))
async def start_complete(
    query: CallbackQuery,
    callback_data: AdminOrderCb,
    ctx: AppContext,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    if not await _require_admin(query, is_admin):
        return
    await state.update_data(order_id=callback_data.order_id)
    await state.set_state(AdminComplete.links)
    await query.answer()
    if query.message:
        await query.message.answer(
            render_md(ctx.i18n, locale, "admin.ask_completion_links"),
            parse_mode="MarkdownV2",
            reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
        )


def _parse_links(text: str | None) -> list[tuple[str, str]]:
    if not text or text.strip() in SKIP:
        return []
    result: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "|" in line:
            title, url = line.split("|", 1)
            result.append((url.strip(), title.strip()))
        else:
            result.append((line, line))
    return result


@router.message(AdminComplete.links)
async def got_links(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(links=_parse_links(message.text))
    await state.set_state(AdminComplete.message)
    await message.answer(
        render_md(ctx.i18n, locale, "admin.ask_completion_text"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(AdminComplete.message)
async def got_complete_message(
    message: Message,
    ctx: AppContext,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    extra = _blank(message.text)
    order = await ctx.complete_order.execute(
        CompleteOrderDTO(order_id=UUID(data["order_id"]), links=data.get("links") or [], message=extra)
    )
    customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
    customer_locale = customer.language if customer else ctx.settings.default_locale
    await ctx.notifier.notify_customer(
        order.customer_telegram_id,
        customer_locale,
        "order.completed_customer",
        message=extra or "",
    )
    await state.clear()
    await message.answer(
        render_md(ctx.i18n, locale, "order.completed_customer", message=extra or ""),
        parse_mode="MarkdownV2",
        reply_markup=main_menu(ctx.i18n, locale, is_admin=is_admin),
    )


@router.callback_query(F.data == "admin:create")
async def start_manual(query: CallbackQuery, ctx: AppContext, locale: str, is_admin: bool, state: FSMContext) -> None:
    if not await _require_admin(query, is_admin):
        return
    await state.set_state(AdminManualWizard.customer)
    await query.answer()
    if query.message:
        await query.message.answer(
            render_md(ctx.i18n, locale, "admin.ask_customer_id"),
            parse_mode="MarkdownV2",
            reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
        )


@router.message(AdminManualWizard.customer)
async def manual_customer(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    raw = (message.text or "").strip()
    telegram_id = None
    username = None
    if raw.startswith("@"):
        username = raw
        try:
            chat = await message.bot.get_chat(raw)
            telegram_id = chat.id
        except Exception:
            logger.info("Could not resolve %s via getChat", raw)
    elif raw.isdigit():
        telegram_id = int(raw)
    else:
        username = raw
    await state.update_data(customer_telegram_id=telegram_id, customer_username=username)
    await state.set_state(AdminManualWizard.name)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_name"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
    )


@router.message(AdminManualWizard.name)
async def manual_name(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(display_name=(message.text or "").strip())
    await state.set_state(AdminManualWizard.idea)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_idea"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
    )


@router.message(AdminManualWizard.idea)
async def manual_idea(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(idea=(message.text or "").strip())
    await state.set_state(AdminManualWizard.contacts)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_contacts"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(AdminManualWizard.contacts)
async def manual_contacts(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(contacts=_blank(message.text))
    await state.set_state(AdminManualWizard.references)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_references"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(AdminManualWizard.references)
async def manual_references(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(references=_blank(message.text))
    await state.set_state(AdminManualWizard.budget)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_budget"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(AdminManualWizard.budget)
async def manual_budget(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    data = await state.update_data(budget=_blank(message.text))
    await state.set_state(AdminManualWizard.confirm)
    dash = ctx.i18n.get(locale, "order.dash")
    await message.answer(
        render_md(
            ctx.i18n,
            locale,
            "order.confirm_preview",
            name=data.get("display_name") or dash,
            idea=data.get("idea") or dash,
            contacts=data.get("contacts") or dash,
            references=data.get("references") or dash,
            budget=data.get("budget") or dash,
        ),
        parse_mode="MarkdownV2",
        reply_markup=confirm_menu(ctx.i18n, locale),
    )


@router.message(AdminManualWizard.confirm, F.text.in_(CONFIRM))
async def manual_confirm(
    message: Message,
    ctx: AppContext,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    try:
        order = await ctx.create_manual.execute(
            ManualOrderDTO(
                customer_telegram_id=data.get("customer_telegram_id"),
                customer_username=(data.get("customer_username") or "").lstrip("@") or None,
                display_name=data["display_name"],
                idea=data["idea"],
                extra_contacts=data.get("contacts"),
                references=data.get("references"),
                budget=data.get("budget"),
            )
        )
    except DomainError:
        await message.answer(render_md(ctx.i18n, locale, "common.error_generic"), parse_mode="MarkdownV2")
        await state.clear()
        return
    customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
    await ctx.notifier.notify_admins_new_order(order, customer, locale=locale)
    await state.clear()
    await message.answer(
        render_md(ctx.i18n, locale, "admin.created_manual"),
        parse_mode="MarkdownV2",
        reply_markup=main_menu(ctx.i18n, locale, is_admin=is_admin),
    )
