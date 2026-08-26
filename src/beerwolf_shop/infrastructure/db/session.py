"""Async SQLAlchemy engine and session factory."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from beerwolf_shop.config import Settings

logger = logging.getLogger(__name__)
_ROLLBACK_CALLBACKS = "beerwolf_rollback_callbacks"


class SessionRollbackRegistry:
    """Register external side-effect compensation until the DB commit succeeds."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def register(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._session.info.setdefault(_ROLLBACK_CALLBACKS, []).append(callback)


def clear_rollback_compensations(session: AsyncSession) -> None:
    session.info.pop(_ROLLBACK_CALLBACKS, None)


async def run_rollback_compensations(session: AsyncSession) -> None:
    callbacks = session.info.pop(_ROLLBACK_CALLBACKS, [])
    for callback in reversed(callbacks):
        try:
            await callback()
        except Exception:
            # Preserve the original transaction failure while making drift visible.
            logger.exception("Rollback compensation failed")


def create_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
