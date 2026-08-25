"""User upsert and language change."""

from datetime import UTC, datetime

from beerwolf_shop.domain.entities import User
from beerwolf_shop.domain.exceptions import UserNotFoundError
from beerwolf_shop.domain.protocols import UserRepository
from beerwolf_shop.infrastructure.telegram.i18n import SUPPORTED_LOCALES


class UpsertUser:
    def __init__(self, users: UserRepository, default_locale: str) -> None:
        self._users = users
        self._default_locale = default_locale

    async def execute(
        self,
        telegram_id: int,
        username: str | None,
        display_name: str | None = None,
        language: str | None = None,
    ) -> User:
        existing = await self._users.get_by_telegram_id(telegram_id)
        if existing is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                display_name=display_name or username or str(telegram_id),
                language=language or self._default_locale,
            )
            return await self._users.add(user)
        existing.username = username if username is not None else existing.username
        # Preferred display name is collected in the order wizard; do not clobber it
        # with Telegram full_name on every subsequent update.
        if language:
            existing.language = language
        existing.updated_at = datetime.now(UTC)
        return await self._users.save(existing)


class SetLanguage:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, telegram_id: int, language: str) -> User:
        if language not in SUPPORTED_LOCALES:
            language = "ru"
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None:
            raise UserNotFoundError(str(telegram_id))
        user.language = language
        user.updated_at = datetime.now(UTC)
        return await self._users.save(user)
