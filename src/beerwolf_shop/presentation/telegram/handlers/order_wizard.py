"""Customer commission request wizard."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from beerwolf_shop.application.dto import SubmitOrderDTO
from beerwolf_shop.domain.entities import User
from beerwolf_shop.infrastructure.telegram.keyboards import (
    confirm_menu,
    main_menu,
    render_md,
    wizard_menu,
)
from beerwolf_shop.presentation.telegram.context import AppContext
from beerwolf_shop.presentation.telegram.states import OrderWizard

router = Router(name="order_wizard")

SKIP = {"Пропустить", "Skip"}
CONFIRM = {"Подтвердить", "Confirm"}
START = {"Новая заявка", "New request"}


def _blank(value: str | None) -> str | None:
    if value is None or value.strip() in SKIP or not value.strip():
        return None
    return value.strip()


@router.message(F.text.in_(START))
async def start_wizard(message: Message, ctx: AppContext, locale: str, state: FSMContext) -> None:
    await state.set_state(OrderWizard.name)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_name"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
    )


@router.message(OrderWizard.name)
async def got_name(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(display_name=(message.text or "").strip())
    await state.set_state(OrderWizard.idea)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_idea"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=False),
    )


@router.message(OrderWizard.idea)
async def got_idea(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(idea=(message.text or "").strip())
    await state.set_state(OrderWizard.contacts)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_contacts"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(OrderWizard.contacts)
async def got_contacts(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(contacts=_blank(message.text))
    await state.set_state(OrderWizard.references)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_references"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(OrderWizard.references)
async def got_references(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    await state.update_data(references=_blank(message.text))
    await state.set_state(OrderWizard.budget)
    await message.answer(
        render_md(ctx.i18n, locale, "order.ask_budget"),
        parse_mode="MarkdownV2",
        reply_markup=wizard_menu(ctx.i18n, locale, with_skip=True),
    )


@router.message(OrderWizard.budget)
async def got_budget(message: Message, locale: str, state: FSMContext, ctx: AppContext) -> None:
    data = await state.update_data(budget=_blank(message.text))
    await state.set_state(OrderWizard.confirm)
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


@router.message(OrderWizard.confirm, F.text.in_(CONFIRM))
async def confirm_order(
    message: Message,
    ctx: AppContext,
    user: User,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    data = await state.get_data()
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
        )
    )
    await ctx.notifier.notify_admins_new_order(order, user, locale=ctx.settings.default_locale)
    await state.clear()
    await message.answer(
        render_md(ctx.i18n, locale, "order.submitted"),
        parse_mode="MarkdownV2",
        reply_markup=main_menu(ctx.i18n, locale, is_admin=is_admin),
    )
