"""Per-update wiring: DB session, use cases, current user."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from beerwolf_shop.application.github import (
    BuildProgress,
    CreateCustomerRequest,
    GetMilestoneDetails,
    HandleGithubIssueEvent,
    ListRepoProjects,
    StartInProgress,
)
from beerwolf_shop.application.orders import (
    ChangeStatus,
    CompleteOrder,
    CreateManualOrder,
    GetCustomerProject,
    GetOrder,
    ListCustomerOrders,
    ListOrders,
    MarkSpam,
    StartDiscussion,
    SubmitOrder,
)
from beerwolf_shop.application.support import (
    CancelSupportTicket,
    CompleteSupportTicket,
    CreateSupportTicket,
    TakeSupportTicket,
)
from beerwolf_shop.application.users import SetLanguage, UpsertUser
from beerwolf_shop.config import Settings
from beerwolf_shop.domain.entities import User
from beerwolf_shop.infrastructure.db.repositories import (
    SqlCompletionLinkRepository,
    SqlCustomerRequestIssueRepository,
    SqlMilestoneNotificationRepository,
    SqlOrderRepository,
    SqlOutboxRepository,
    SqlUserRepository,
    SqlWebhookDeliveryRepository,
)
from beerwolf_shop.infrastructure.db.session import (
    SessionRollbackRegistry,
    clear_rollback_compensations,
    run_rollback_compensations,
)
from beerwolf_shop.infrastructure.github.client import GithubClient
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.notifier import NotifierPort
from beerwolf_shop.infrastructure.telegram.outbox import OutboxNotifier, OutboxProcessor


class AppContext:
    """Bundle of ports for a single unit of work (one DB session)."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        i18n: I18n,
        github: GithubClient,
        notifier: NotifierPort,
    ) -> None:
        self.session = session
        self.settings = settings
        self.i18n = i18n
        self.github = github
        self.notifier = notifier
        self.users = SqlUserRepository(session)
        self.orders = SqlOrderRepository(session)
        self.links = SqlCompletionLinkRepository(session)
        self.deliveries = SqlWebhookDeliveryRepository(session)
        self.milestone_notifications = SqlMilestoneNotificationRepository(session)
        self.request_issues = SqlCustomerRequestIssueRepository(session)
        self.upsert_user = UpsertUser(self.users, settings.default_locale)
        self.set_language = SetLanguage(self.users)
        self.submit_order = SubmitOrder(self.users, self.orders)
        self.create_manual = CreateManualOrder(self.users, self.orders)
        self.list_orders = ListOrders(self.orders)
        self.get_order = GetOrder(self.orders, self.links)
        self.get_customer_project = GetCustomerProject(self.orders)
        self.list_customer_orders = ListCustomerOrders(self.orders)
        self.change_status = ChangeStatus(self.orders)
        self.mark_spam = MarkSpam(self.orders)
        self.start_discussion = StartDiscussion(self.orders)
        self.complete_order = CompleteOrder(self.orders, self.links)
        self.list_projects = ListRepoProjects(github)
        self.start_in_progress = StartInProgress(self.orders, github, settings)
        self.build_progress = BuildProgress(self.orders, github, settings)
        self.get_milestone_details = GetMilestoneDetails(self.orders, github)
        rollback_registry = SessionRollbackRegistry(session)
        self.create_request = CreateCustomerRequest(
            self.orders,
            self.request_issues,
            github,
            settings,
            rollback_registry,
        )
        self.handle_github_issue_event = HandleGithubIssueEvent(
            self.orders,
            self.deliveries,
            self.milestone_notifications,
            self.request_issues,
            github,
        )
        self.create_support = CreateSupportTicket(self.users, self.orders)
        self.take_support = TakeSupportTicket(self.orders, github, rollback_registry)
        self.cancel_support = CancelSupportTicket(self.orders)
        self.complete_support = CompleteSupportTicket(self.orders, github, rollback_registry)


class DbMiddleware(BaseMiddleware):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        i18n: I18n,
        github: GithubClient,
        outbox: OutboxProcessor,
    ) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._settings = settings
        self._i18n = i18n
        self._github = github
        self._outbox = outbox

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._session_factory() as session:
            ctx = AppContext(
                session,
                self._settings,
                self._i18n,
                self._github,
                OutboxNotifier(SqlOutboxRepository(session)),
            )
            data["ctx"] = ctx
            data["settings"] = self._settings
            data["i18n"] = self._i18n
            # Registered on Update (outer). Message/CallbackQuery are nested events —
            # take Telegram user from UserContextMiddleware, not isinstance(event, Message).
            from_user: TgUser | None = data.get("event_from_user")
            if from_user is None and isinstance(event, (Message, CallbackQuery)):
                from_user = event.from_user
            if from_user:
                user = await ctx.upsert_user.execute(
                    from_user.id,
                    from_user.username,
                    display_name=from_user.full_name,
                )
                data["user"] = user
                data["locale"] = user.language
                data["is_admin"] = self._settings.is_admin(from_user.id)
            else:
                data["user"] = None
                data["locale"] = self._settings.default_locale
                data["is_admin"] = False
            try:
                result = await handler(event, data)
                await session.commit()
                clear_rollback_compensations(session)
            except Exception:
                try:
                    await session.rollback()
                finally:
                    await run_rollback_compensations(session)
                raise
            await self._outbox.drain()
            return result


def locale_of(user: User | None, settings: Settings) -> str:
    if user:
        return user.language
    return settings.default_locale
