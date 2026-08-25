"""FastAPI dependencies: settings, DB session, auth, AppContext."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from beerwolf_shop.application.auth import decode_access_token
from beerwolf_shop.config import Settings
from beerwolf_shop.domain.exceptions import AuthError
from beerwolf_shop.presentation.telegram.context import AppContext

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_context(request: Request, session: Annotated[AsyncSession, Depends(get_session)]) -> AppContext:
    return AppContext(
        session=session,
        settings=request.app.state.settings,
        i18n=request.app.state.i18n,
        github=request.app.state.github,
        notifier=request.app.state.notifier,
    )


async def get_current_telegram_id(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> int:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_bearer")
    if settings.admin_api_token and credentials.credentials == settings.admin_api_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin_token_on_customer_route")
    try:
        payload = decode_access_token(settings, credentials.credentials)
        return int(payload["sub"])
    except (AuthError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token") from exc


async def require_admin(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    token = credentials.credentials if credentials else x_admin_token
    if not settings.admin_api_token or token != settings.admin_api_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_admin_token")


async def get_optional_admin(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> bool:
    if credentials and settings.admin_api_token and credentials.credentials == settings.admin_api_token:
        return True
    return False
