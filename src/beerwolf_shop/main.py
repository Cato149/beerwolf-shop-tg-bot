"""FastAPI application factory: REST API, webhooks, optional Telegram polling."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from beerwolf_shop.config import BotMode, Settings, get_settings
from beerwolf_shop.domain.exceptions import DomainError
from beerwolf_shop.infrastructure.db.session import create_session_factory
from beerwolf_shop.infrastructure.github.client import GithubClient
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.notifier import TelegramNotifier
from beerwolf_shop.infrastructure.telegram.outbox import OutboxProcessor
from beerwolf_shop.presentation.api.errors import domain_error_response
from beerwolf_shop.presentation.api.routers import admin, auth, health, me, orders, webhooks
from beerwolf_shop.presentation.telegram.bot import create_bot, create_dispatcher

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app. Pass settings in tests to avoid reading a local `.env`."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=logging.INFO)
        i18n = I18n(default_locale=settings.default_locale)
        session_factory = create_session_factory(settings)
        github = GithubClient(settings.github_token)
        bot = create_bot(settings)
        notifier = TelegramNotifier(bot, i18n, settings)
        outbox = OutboxProcessor(session_factory, notifier)
        dispatcher = create_dispatcher(settings, session_factory, i18n, github, outbox)

        if settings.bot_token and not settings.bot_username:
            try:
                me_info = await bot.get_me()
                settings.bot_username = me_info.username or ""
            except Exception:
                logger.warning("Could not resolve bot username via getMe")

        app.state.settings = settings
        app.state.i18n = i18n
        app.state.session_factory = session_factory
        app.state.github = github
        app.state.bot = bot
        app.state.dispatcher = dispatcher
        app.state.notifier = notifier
        app.state.outbox = outbox

        polling_task: asyncio.Task[None] | None = None
        try:
            if settings.bot_token and settings.bot_mode == BotMode.webhook:
                url = settings.telegram_webhook_url()
                if url:
                    await bot.set_webhook(url, secret_token=settings.telegram_webhook_secret or None)
            elif settings.bot_token and settings.bot_mode == BotMode.polling:
                await bot.delete_webhook(drop_pending_updates=False)
                polling_task = asyncio.create_task(dispatcher.start_polling(bot))

            yield
        finally:
            if polling_task:
                polling_task.cancel()
                try:
                    await polling_task
                except asyncio.CancelledError:
                    pass
            await github.aclose()
            await bot.session.close()

    app = FastAPI(
        title="Beerwolf commission shop",
        description=(
            "Telegram bot and REST API for commission requests, GitHub progress, "
            "and support tickets. Customer auth uses Telegram initData + JWT; "
            "admin auth uses a static bearer token."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(DomainError)
    async def domain_error_handler(_request, exc: DomainError) -> JSONResponse:
        status_code, detail = domain_error_response(exc)
        return JSONResponse(status_code=status_code, content={"detail": detail})

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(orders.router)
    app.include_router(admin.router)
    app.include_router(webhooks.router)
    return app


app = create_app()
