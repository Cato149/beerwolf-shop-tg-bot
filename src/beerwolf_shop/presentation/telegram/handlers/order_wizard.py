"""Customer commission request wizard."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from beerwolf_shop.application.dto import SubmitOrderDTO
from beerwolf_shop.domain.entities import User
from beerwolf_shop.domain.enums import LOCKED_CUSTOMER_STATUSES
from beerwolf_shop.domain.exceptions import DomainError
from beerwolf_shop.infrastructure.telegram.keyboards import (
    confirm_menu,
    render_md,
    wizard_menu,
)
from beerwolf_shop.presentation.telegram.context import AppContext
from beerwolf_shop.presentation.telegram.handlers.common import (
    PHOTO_IDS_KEY,
    LocaleText,
    build_main_menu,
    reply_error,
    wizard_step_value,
)
from beerwolf_shop.presentation.telegram.states import OrderWizard

router = Router(name="order_wizard")


def _optional(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


@router.message(LocaleText("common.btn_new_order"))
async def start_wizard(message: Message, ctx: AppContext, locale: str, state: FSMContext) -> None:
    if message.from_user:
        active = await ctx.orders.get_active_commission(message.from_user.id)
        if active is not None and active.status in LOCKED_CUSTOMER_STATUSES:
            await message.answer(
                render_md(ctx.i18n, locale, "order.active_exists"),
                parse_mode="HTML",
            )
            return
        if active is not None:
            await message.answer(
                render_md(ctx.i18n, locale, "order.replace_application"),
                parse_mode="HTML",
            )
    await state.set_state(OrderWizard.name)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_name"),
        parse_mode="HTML",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
    )


@router.message(OrderWizard.name)
async def got_name(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    name = await wizard_step_value(message, state, ctx, locale, required=True)
    if name is None:
        return
    await state.update_data(display_name=name)
    await state.set_state(OrderWizard.idea)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_idea"),
        parse_mode="HTML",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
    )


@router.message(OrderWizard.idea)
async def got_idea(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    idea = await wizard_step_value(message, state, ctx, locale, required=True)
    if idea is None:
        return
    await state.update_data(idea=idea)
    await state.set_state(OrderWizard.contacts)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_contacts"),
        parse_mode="HTML",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(OrderWizard.contacts)
async def got_contacts(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    value = await wizard_step_value(message, state, ctx, locale, required=False)
    if value is None:
        return
    await state.update_data(contacts=_optional(value))
    await state.set_state(OrderWizard.references)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_references"),
        parse_mode="HTML",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(OrderWizard.references)
async def got_references(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    value = await wizard_step_value(message, state, ctx, locale, required=False)
    if value is None:
        return
    await state.update_data(references=_optional(value))
    await state.set_state(OrderWizard.budget)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_budget"),
        parse_mode="HTML",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(OrderWizard.budget)
async def got_budget(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    value = await wizard_step_value(message, state, ctx, locale, required=False)
    if value is None:
        return
    data = await state.update_data(budget=_optional(value))
    await state.set_state(OrderWizard.confirm)
    dash = ctx.i18n.get(locale, "order.dash")
    text = render_md(
        ctx.i18n,
        locale,
        "order.confirm_preview",
        name=data.get("display_name") or dash,
        idea=data.get("idea") or dash,
        contacts=data.get("contacts") or dash,
        references=data.get("references") or dash,
        budget=data.get("budget") or dash,
    )
    photos = data.get(PHOTO_IDS_KEY) or []
    if photos:
        text += "\n" + render_md(ctx.i18n, locale, "order.photos_attached", count=len(photos))
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=confirm_menu(ctx.i18n, locale),
    )


@router.message(OrderWizard.confirm, LocaleText("common.btn_confirm"))
async def confirm_order(
    message: Message,
    ctx: AppContext,
    user: User,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    await state.clear()
    try:
        order = await ctx.submit_order.execute(
            SubmitOrderDTO(
                customer_telegram_id=user.telegram_id,
                display_name=data["display_name"],
                idea=data["idea"],
                extra_contacts=data.get("contacts"),
                references=data.get("references"),
                budget=data.get("budget"),
                username=user.username,
                language=locale,
                photo_file_ids=list(data.get(PHOTO_IDS_KEY) or []),
            )
        )
    except DomainError:
        await reply_error(message, ctx, locale)
        return
    await ctx.notifier.notify_admins_new_order(order, user, locale=ctx.settings.default_locale)
    await message.answer(
        render_md(ctx.i18n, locale, "order.submitted"),
        parse_mode="HTML",
        reply_markup=await build_main_menu(ctx, user, locale, is_admin),
    )
