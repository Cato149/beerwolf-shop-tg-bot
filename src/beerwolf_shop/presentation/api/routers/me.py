"""Current user profile and language."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from beerwolf_shop.config import Settings
from beerwolf_shop.domain.exceptions import UserNotFoundError
from beerwolf_shop.presentation.api.deps import get_context, get_current_telegram_id, get_settings
from beerwolf_shop.presentation.api.schemas import LanguageUpdate, MeResponse
from beerwolf_shop.presentation.telegram.context import AppContext

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Current user",
    description="Returns the profile of the customer identified by the JWT.",
)
async def me(
    telegram_id: Annotated[int, Depends(get_current_telegram_id)],
    ctx: Annotated[AppContext, Depends(get_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MeResponse:
    user = await ctx.users.get_by_telegram_id(telegram_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    return MeResponse(
        telegram_id=user.telegram_id,
        username=user.username,
        display_name=user.display_name,
        language=user.language,
        is_admin=settings.is_admin(user.telegram_id),
    )


@router.patch(
    "/me/language",
    response_model=MeResponse,
    summary="Change UI language",
    description="Sets `ru` or `en` for the authenticated customer. Unknown values fall back to `ru`.",
)
async def change_language(
    body: LanguageUpdate,
    telegram_id: Annotated[int, Depends(get_current_telegram_id)],
    ctx: Annotated[AppContext, Depends(get_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MeResponse:
    try:
        user = await ctx.set_language.execute(telegram_id, body.language)
    except UserNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found") from exc
    return MeResponse(
        telegram_id=user.telegram_id,
        username=user.username,
        display_name=user.display_name,
        language=user.language,
        is_admin=settings.is_admin(user.telegram_id),
    )
