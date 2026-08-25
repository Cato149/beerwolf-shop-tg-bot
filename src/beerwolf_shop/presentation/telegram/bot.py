"""Aiogram dispatcher factory."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from beerwolf_shop.config import Settings
from beerwolf_shop.infrastructure.fsm.postgres import PostgresStorage
from beerwolf_shop.infrastructure.github.client import GithubClient
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.notifier import TelegramNotifier
from beerwolf_shop.presentation.telegram.context import DbMiddleware
from beerwolf_shop.presentation.telegram.handlers.admin import router as admin_router
from beerwolf_shop.presentation.telegram.handlers.common import router as common_router
from beerwolf_shop.presentation.telegram.handlers.customer import router as customer_router
from beerwolf_shop.presentation.telegram.handlers.order_wizard import router as order_router


def create_bot(settings: Settings) -> Bot:
    return Bot(token=settings.bot_token or "0:init", default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2))


def _include(dispatcher: Dispatcher, router) -> None:
    # Module-level routers are reused across FastAPI app factories (tests).
    router._parent_router = None
    dispatcher.include_router(router)


def create_dispatcher(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    i18n: I18n,
    github: GithubClient,
    bot: Bot,
) -> Dispatcher:
    storage = PostgresStorage(session_factory)
    dispatcher = Dispatcher(storage=storage)
    notifier = TelegramNotifier(bot, i18n, settings)
    middleware = DbMiddleware(session_factory, settings, i18n, github, notifier)
    dispatcher.update.outer_middleware(middleware)
    _include(dispatcher, common_router)
    _include(dispatcher, admin_router)
    _include(dispatcher, order_router)
    _include(dispatcher, customer_router)
    return dispatcher
