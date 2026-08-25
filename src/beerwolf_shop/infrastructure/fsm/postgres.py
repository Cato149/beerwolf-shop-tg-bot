"""Postgres-backed FSM storage for aiogram 3 (no Redis)."""

from __future__ import annotations

import json
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import (
    BaseStorage,
    DefaultKeyBuilder,
    KeyBuilder,
    StateType,
    StorageKey,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from beerwolf_shop.infrastructure.db.models import FsmStateTable


class PostgresStorage(BaseStorage):
    """Persists FSM state and data in the `fsm_states` table.

    Keys follow aiogram's StorageKey (bot, chat, user, thread, destiny).
    Nullable Telegram thread ids are stored as 0 so the unique constraint works.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        key_builder: KeyBuilder | None = None,
    ) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._key_builder = key_builder or DefaultKeyBuilder(with_destiny=True)

    async def _get_row(self, session: AsyncSession, key: StorageKey) -> FsmStateTable | None:
        stmt = select(FsmStateTable).where(
            FsmStateTable.bot_id == key.bot_id,
            FsmStateTable.chat_id == key.chat_id,
            FsmStateTable.user_id == key.user_id,
            FsmStateTable.thread_id == (key.thread_id or 0),
            FsmStateTable.business_connection_id == (key.business_connection_id or ""),
            FsmStateTable.destiny == key.destiny,
        )
        result = await session.exec(stmt)
        return result.first()

    async def _get_or_create(self, session: AsyncSession, key: StorageKey) -> FsmStateTable:
        row = await self._get_row(session, key)
        if row is not None:
            return row
        row = FsmStateTable(
            bot_id=key.bot_id,
            chat_id=key.chat_id,
            user_id=key.user_id,
            thread_id=key.thread_id or 0,
            business_connection_id=key.business_connection_id or "",
            destiny=key.destiny,
            state=None,
            data="{}",
        )
        session.add(row)
        await session.flush()
        return row

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        async with self._session_factory() as session:
            row = await self._get_or_create(session, key)
            row.state = value
            await session.commit()

    async def get_state(self, key: StorageKey) -> str | None:
        async with self._session_factory() as session:
            row = await self._get_row(session, key)
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            row = await self._get_or_create(session, key)
            row.data = json.dumps(data, ensure_ascii=False)
            await session.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self._session_factory() as session:
            row = await self._get_row(session, key)
            if row is None or not row.data:
                return {}
            loaded = json.loads(row.data)
            return loaded if isinstance(loaded, dict) else {}

    async def close(self) -> None:
        return None
