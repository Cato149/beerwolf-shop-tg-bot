"""Application configuration loaded from environment / `.env`."""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotMode(StrEnum):
    """How the Telegram bot receives updates."""

    polling = "polling"
    webhook = "webhook"


class Settings(BaseSettings):
    """Runtime settings. Every field maps to an env variable of the same name."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(
        default="",
        description="Telegram bot token issued by @BotFather.",
    )
    bot_mode: BotMode = Field(
        default=BotMode.polling,
        description="Update delivery mode: polling for development, webhook for production.",
    )
    public_base_url: str = Field(
        default="",
        description="Public HTTPS origin of this app (no trailing slash) used to register webhooks.",
    )
    telegram_webhook_secret: str = Field(
        default="",
        description="Secret Telegram sends in X-Telegram-Bot-Api-Secret-Token for webhook mode.",
    )
    admin_telegram_ids: list[int] = Field(
        default_factory=list,
        description="Comma-separated Telegram user IDs that have admin privileges.",
    )
    admin_telegram_contact: str = Field(
        default="",
        description="Contact shown to the customer when an order enters discussion.",
    )
    admin_api_token: str = Field(
        default="",
        description="Bearer token accepted by admin REST endpoints.",
    )
    jwt_secret: str = Field(
        default="dev-jwt-secret",
        description="HMAC secret for customer JWTs issued after Telegram initData verification.",
    )
    jwt_expire_minutes: int = Field(
        default=60 * 24 * 7,
        description="Customer JWT lifetime in minutes.",
    )
    database_url: str = Field(
        default="postgresql+asyncpg://beerwolf:beerwolf@localhost:5432/beerwolf",
        description="SQLAlchemy async URL for Postgres.",
    )
    github_token: str = Field(
        default="",
        description="GitHub token used for REST issues/milestones/hooks and GraphQL Projects v2.",
    )
    github_webhook_secret: str = Field(
        default="",
        description="Secret used to verify X-Hub-Signature-256 on GitHub webhooks.",
    )
    github_status_backlog: str = Field(
        default="Backlog",
        description="Projects v2 Status option name used as the backlog column.",
    )
    github_status_in_progress: str = Field(
        default="In Progress",
        description="Projects v2 Status option name used as the in-progress column.",
    )
    github_status_done: str = Field(
        default="Done",
        description="Projects v2 Status option name treated as completed work.",
    )
    default_locale: str = Field(
        default="ru",
        description="Default UI language (ru or en) until the user picks one.",
    )
    bot_username: str = Field(
        default="",
        description="Public bot username without @, used in share URLs. Filled from getMe if empty.",
    )
    app_host: str = Field(
        default="0.0.0.0",
        description="HTTP bind host for uvicorn.",
    )
    app_port: int = Field(
        default=8000,
        description="HTTP bind port for uvicorn.",
    )

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> list[int]:
        """Accept a comma-separated env string or an already parsed list."""
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(item) for item in value]
        return [int(part.strip()) for part in str(value).split(",") if part.strip()]

    @field_validator("public_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_telegram_ids

    def github_webhook_url(self) -> str | None:
        if not self.public_base_url:
            return None
        return f"{self.public_base_url}/webhooks/github"

    def telegram_webhook_url(self) -> str | None:
        if not self.public_base_url:
            return None
        return f"{self.public_base_url}/webhooks/telegram"


@lru_cache
def get_settings() -> Settings:
    return Settings()
