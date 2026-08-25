"""Telegram and GitHub webhook receivers on the same FastAPI app."""

import hmac
import json
from hashlib import sha256
from typing import Annotated

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from beerwolf_shop.config import Settings
from beerwolf_shop.domain.exceptions import DuplicateDeliveryError
from beerwolf_shop.presentation.api.deps import get_context, get_settings
from beerwolf_shop.presentation.telegram.context import AppContext

router = APIRouter(tags=["webhooks"])


def _verify_github_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not secret:
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest()
    return hmac.compare_digest(expected, header)


@router.post(
    "/webhooks/telegram",
    summary="Telegram bot webhook",
    description="Receives Bot API updates when BOT_MODE=webhook. Validates X-Telegram-Bot-Api-Secret-Token if set.",
)
async def telegram_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_telegram_secret")
    payload = await request.json()
    bot: Bot = request.app.state.bot
    dispatcher: Dispatcher = request.app.state.dispatcher
    update = Update.model_validate(payload, context={"bot": bot})
    await dispatcher.feed_update(bot, update)
    return {"ok": True}


@router.post(
    "/webhooks/github",
    summary="GitHub issues webhook",
    description=(
        "Handles `issues` closed events. Verifies X-Hub-Signature-256, is idempotent by X-GitHub-Delivery, "
        "and notifies the customer with HTML + photos converted from the issue/comment GFM."
    ),
)
async def github_webhook(
    request: Request,
    ctx: Annotated[AppContext, Depends(get_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_delivery: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    body = await request.body()
    if not _verify_github_signature(settings.github_webhook_secret, body, x_hub_signature_256):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_github_signature")
    if x_github_event not in {None, "issues", "ping"}:
        return {"status": "ignored"}
    if x_github_event == "ping":
        return {"status": "pong"}
    payload = json.loads(body.decode() or "{}")
    try:
        result = await ctx.handle_issue_closed.execute(x_github_delivery, payload)
    except DuplicateDeliveryError:
        return {"status": "duplicate"}
    if result is None:
        return {"status": "ignored"}
    orders, rendered, closed = result
    for order in orders:
        customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
        locale = customer.language if customer else settings.default_locale
        await ctx.notifier.send_closed_issue(
            order.customer_telegram_id,
            locale,
            closed.title,
            closed.html_url,
            rendered,
        )
    return {"status": "ok"}
