"""Start, language, cancel, help."""

from aiogram import Router
from aiogram.filters import Command, CommandStart, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from beerwolf_shop.domain.entities import User
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.keyboards import (
    LangCb,
    language_inline,
    main_menu,
    render_md,
)
from beerwolf_shop.infrastructure.telegram.photos import collect_photo_file_ids
from beerwolf_shop.presentation.telegram.context import AppContext

router = Router(name="common")

PHOTO_IDS_KEY = "photo_file_ids"


async def build_main_menu(ctx: AppContext, user: User, locale: str, is_admin: bool):
    """Render the persistent keyboard from the customer's current primary project."""

    project = await ctx.get_customer_project.execute(user.telegram_id)
    return main_menu(ctx.i18n, locale, is_admin=is_admin, project=project)


async def append_message_photos(state: FSMContext, message: Message) -> list[str]:
    """Accumulate Telegram photo file_ids in FSM so albums can be sent across several updates."""
    incoming = collect_photo_file_ids(message)
    data = await state.get_data()
    stored = list(data.get(PHOTO_IDS_KEY) or [])
    if incoming:
        stored.extend(incoming)
        await state.update_data(**{PHOTO_IDS_KEY: stored})
    return stored


async def wizard_step_value(
    message: Message,
    state: FSMContext,
    ctx: AppContext,
    locale: str,
    *,
    required: bool,
) -> str | None:
    """Read text/caption for a wizard step. Photo-only messages stay on the same step.

    Returns None when the handler must wait (required empty, or photos without caption).
    Returns "" when a skippable step is skipped.
    """
    await append_message_photos(state, message)
    raw = (message.text or message.caption or "").strip()
    if ctx.i18n.matches(raw, "common.btn_skip"):
        return None if required else ""
    if raw:
        return raw
    if collect_photo_file_ids(message):
        await message.answer(
            render_md(ctx.i18n, locale, "order.photo_saved"),
            parse_mode="HTML",
        )
        return None
    if required:
        await message.answer(
            render_md(ctx.i18n, locale, "common.error_empty"),
            parse_mode="HTML",
        )
        return None
    return ""


class LocaleText(Filter):
    """Match a reply-keyboard label from any locale catalog, not a hardcoded string."""

    def __init__(self, key: str) -> None:
        self.key = key

    async def __call__(self, message: Message, i18n: I18n) -> bool:
        return i18n.matches(message.text, self.key)


async def reply_error(message: Message, ctx: AppContext, locale: str) -> None:
    await message.answer(
        render_md(ctx.i18n, locale, "common.error_generic"),
        parse_mode="HTML",
    )


async def require_text(message: Message, ctx: AppContext, locale: str) -> str | None:
    text = (message.text or "").strip()
    if not text:
        await message.answer(
            render_md(ctx.i18n, locale, "common.error_empty"),
            parse_mode="HTML",
        )
        return None
    return text


@router.message(CommandStart())
async def cmd_start(
    message: Message, ctx: AppContext, user: User, locale: str, is_admin: bool, state: FSMContext
) -> None:
    await state.clear()
    await message.answer(
        render_md(ctx.i18n, locale, "common.start", name=user.display_name),
        parse_mode="HTML",
        reply_markup=await build_main_menu(ctx, user, locale, is_admin),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, ctx: AppContext, locale: str) -> None:
    await message.answer(render_md(ctx.i18n, locale, "common.help"), parse_mode="HTML")


@router.message(LocaleText("common.btn_language"))
@router.message(Command("language"))
async def cmd_language(message: Message, ctx: AppContext, locale: str) -> None:
    await message.answer(
        render_md(ctx.i18n, locale, "common.choose_language"),
        parse_mode="HTML",
        reply_markup=language_inline(ctx.i18n, locale),
    )


@router.callback_query(LangCb.filter())
async def set_language(
    query: CallbackQuery,
    callback_data: LangCb,
    ctx: AppContext,
    user: User,
    is_admin: bool,
) -> None:
    updated = await ctx.set_language.execute(user.telegram_id, callback_data.code)
    locale = updated.language
    await query.answer()
    if query.message:
        await query.message.answer(
            render_md(ctx.i18n, locale, "common.language_changed"),
            parse_mode="HTML",
            reply_markup=await build_main_menu(ctx, updated, locale, is_admin),
        )


@router.message(LocaleText("common.btn_cancel"))
@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message,
    ctx: AppContext,
    user: User,
    locale: str,
    is_admin: bool,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer(
        render_md(ctx.i18n, locale, "common.cancelled"),
        parse_mode="HTML",
        reply_markup=await build_main_menu(ctx, user, locale, is_admin),
    )
