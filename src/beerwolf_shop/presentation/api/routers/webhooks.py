"""Telegram and GitHub webhook receivers on the same FastAPI app."""

import hmac
import json
from hashlib import sha256
from typing import Annotated

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError

from beerwolf_shop.config import Settings
from beerwolf_shop.domain.exceptions import DuplicateDeliveryError, GithubIntegrationError
from beerwolf_shop.presentation.api.deps import get_context, get_settings
from beerwolf_shop.presentation.telegram.context import AppContext

router = APIRouter(tags=["webhooks"])


def _verify_github_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Reject unsigned payloads. An empty secret would otherwise accept anything."""
    if not secret or not header or not header.startswith("sha256="):
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
    expected = settings.telegram_webhook_secret
    received = x_telegram_bot_api_secret_token or ""
    if expected and not hmac.compare_digest(expected, received):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_telegram_secret")
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_json") from exc
    bot: Bot = request.app.state.bot
    dispatcher: Dispatcher = request.app.state.dispatcher
    try:
        update = Update.model_validate(payload, context={"bot": bot})
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_update") from exc
    await dispatcher.feed_update(bot, update)
    return {"ok": True}


@router.post(
    "/webhooks/github",
    summary="GitHub issues webhook",
    description=(
        "Handles closed issues, customer-request `ready` labels and 100% milestones. "
        "Verifies X-Hub-Signature-256 and is idempotent by X-GitHub-Delivery."
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
    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "issues":
        return {"status": "ignored"}
    try:
        payload = json.loads(body.decode() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_json") from exc
    try:
        result = await ctx.handle_github_issue_event.execute(x_github_delivery, payload)
    except DuplicateDeliveryError:
        return {"status": "duplicate"}
    except GithubIntegrationError:
        # 502 so GitHub retries; the delivery id is rolled back with the request session.
        raise
    if result is None:
        return {"status": "ignored"}
    header_key = "progress.request_ready" if result.kind == "ready" else "progress.issue_closed"
    for order in result.orders:
        customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
        locale = customer.language if customer else settings.default_locale
        await ctx.notifier.send_issue_update(
            order.customer_telegram_id,
            locale,
            header_key,
            result.issue.title,
            result.issue.html_url,
            result.rendered,
        )
    if result.milestone:
        for order in result.milestone_orders or []:
            customer = await ctx.users.get_by_telegram_id(order.customer_telegram_id)
            locale = customer.language if customer else settings.default_locale
            await ctx.notifier.notify_customer(
                order.customer_telegram_id,
                locale,
                "progress.milestone_completed",
                title=result.milestone.title,
            )
    return {"status": "ok"}
