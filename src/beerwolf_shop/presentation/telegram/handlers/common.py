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
from beerwolf_shop.presentation.telegram.context import AppContext

router = Router(name="common")


class LocaleText(Filter):
    """Match a reply-keyboard label from any locale catalog, not a hardcoded string."""

    def __init__(self, key: str) -> None:
        self.key = key

    async def __call__(self, message: Message, i18n: I18n) -> bool:
        return i18n.matches(message.text, self.key)


async def reply_error(message: Message, ctx: AppContext, locale: str) -> None:
    await message.answer(
        render_md(ctx.i18n, locale, "common.error_generic"),
        parse_mode="MarkdownV2",
    )


async def require_text(message: Message, ctx: AppContext, locale: str) -> str | None:
    text = (message.text or "").strip()
    if not text:
        await message.answer(
            render_md(ctx.i18n, locale, "common.error_empty"),
            parse_mode="MarkdownV2",
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
        parse_mode="MarkdownV2",
        reply_markup=main_menu(ctx.i18n, locale, is_admin=is_admin),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, ctx: AppContext, locale: str) -> None:
    await message.answer(render_md(ctx.i18n, locale, "common.help"), parse_mode="MarkdownV2")


@router.message(LocaleText("common.btn_language"))
@router.message(Command("language"))
async def cmd_language(message: Message, ctx: AppContext, locale: str) -> None:
    await message.answer(
        render_md(ctx.i18n, locale, "common.choose_language"),
        parse_mode="MarkdownV2",
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
            parse_mode="MarkdownV2",
            reply_markup=main_menu(ctx.i18n, locale, is_admin=is_admin),
        )


@router.message(LocaleText("common.btn_cancel"))
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, ctx: AppContext, locale: str, is_admin: bool, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        render_md(ctx.i18n, locale, "common.cancelled"),
        parse_mode="MarkdownV2",
        reply_markup=main_menu(ctx.i18n, locale, is_admin=is_admin),
    )
