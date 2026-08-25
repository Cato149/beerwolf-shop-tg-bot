"""Telegram Mini App / Login initData → JWT."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from beerwolf_shop.application.auth import create_access_token, validate_telegram_init_data
from beerwolf_shop.config import Settings
from beerwolf_shop.domain.exceptions import AuthError
from beerwolf_shop.presentation.api.deps import get_context, get_settings
from beerwolf_shop.presentation.api.schemas import TelegramAuthRequest, TokenResponse
from beerwolf_shop.presentation.telegram.context import AppContext

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/telegram",
    response_model=TokenResponse,
    summary="Authenticate with Telegram initData",
    description=(
        "Validates Mini App initData using HMAC-SHA256 as documented by Telegram, "
        "upserts the user, and returns a customer JWT."
    ),
)
async def auth_telegram(
    body: TelegramAuthRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    ctx: Annotated[AppContext, Depends(get_context)],
) -> TokenResponse:
    try:
        tg_user = validate_telegram_init_data(body.init_data, settings.bot_token)
        telegram_id = int(tg_user["id"])
    except (AuthError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_init_data") from exc
    user = await ctx.upsert_user.execute(
        telegram_id,
        tg_user.get("username"),
        display_name=tg_user.get("first_name") or str(telegram_id),
    )
    token = create_access_token(settings, user.telegram_id, is_admin=settings.is_admin(telegram_id))
    return TokenResponse(access_token=token, telegram_id=telegram_id)
