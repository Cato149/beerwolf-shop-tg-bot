"""In-memory fakes for use-case and API tests (no Postgres)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from beerwolf_shop.application.github import (
    BuildProgress,
    CreateCustomerRequest,
    HandleIssueClosed,
    ListRepoProjects,
    StartInProgress,
)
from beerwolf_shop.application.orders import (
    ChangeStatus,
    CompleteOrder,
    CreateManualOrder,
    GetOrder,
    ListCustomerOrders,
    ListOrders,
    MarkSpam,
    StartDiscussion,
    SubmitOrder,
)
from beerwolf_shop.application.support import CreateSupportTicket
from beerwolf_shop.application.users import SetLanguage, UpsertUser
from beerwolf_shop.config import BotMode, Settings
from beerwolf_shop.domain.entities import CompletionLink, Order, User
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.infrastructure.github.client import (
    GithubIssue,
    GithubMilestone,
    GithubProject,
    GithubRepo,
    ProjectItem,
)
from beerwolf_shop.infrastructure.telegram.i18n import I18n


def make_test_settings() -> Settings:
    return Settings(
        bot_token="123:test",
        bot_mode=BotMode.webhook,
        admin_api_token="admin-secret",
        admin_telegram_ids="1",
        admin_telegram_contact="@admin",
        jwt_secret="jwt-secret-please-use-at-least-32b",
        github_token="gh-token",
        github_webhook_secret="wh-secret",
        default_locale="ru",
        bot_username="beerwolf_bot",
    )


class FakeUserRepo:
    def __init__(self) -> None:
        self.items: dict[int, User] = {}

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return self.items.get(telegram_id)

    async def get_by_username(self, username: str) -> User | None:
        needle = username.lstrip("@").lower()
        for user in self.items.values():
            if user.username and user.username.lstrip("@").lower() == needle:
                return user
        return None

    async def add(self, user: User) -> User:
        self.items[user.telegram_id] = user
        return user

    async def save(self, user: User) -> User:
        self.items[user.telegram_id] = user
        return user


class FakeOrderRepo:
    def __init__(self) -> None:
        self.items: dict[UUID, Order] = {}

    async def get(self, order_id: UUID) -> Order | None:
        return self.items.get(order_id)

    async def add(self, order: Order) -> Order:
        self.items[order.id] = order
        return order

    async def save(self, order: Order) -> Order:
        self.items[order.id] = order
        return order

    async def list_by_status(
        self,
        status: OrderStatus | None,
        order_type: OrderType | None = None,
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> list[Order]:
        rows = list(self.items.values())
        if status is not None:
            rows = [o for o in rows if o.status == status]
        if order_type is not None:
            rows = [o for o in rows if o.type == order_type]
        rows.sort(key=lambda o: o.created_at, reverse=True)
        return rows[offset : offset + limit]

    async def count_by_status(
        self,
        status: OrderStatus | None,
        order_type: OrderType | None = None,
    ) -> int:
        return len(await self.list_by_status(status, order_type, offset=0, limit=10_000))

    async def list_for_customer(self, telegram_id: int) -> list[Order]:
        return [o for o in self.items.values() if o.customer_telegram_id == telegram_id]

    async def find_by_repo(self, owner: str, repo: str) -> list[Order]:
        return [o for o in self.items.values() if o.github_owner == owner and o.github_repo == repo]


class FakeLinkRepo:
    def __init__(self) -> None:
        self.items: dict[UUID, list[CompletionLink]] = {}

    async def list_for_order(self, order_id: UUID) -> list[CompletionLink]:
        return list(self.items.get(order_id, []))

    async def replace_for_order(self, order_id: UUID, links: list[CompletionLink]) -> None:
        self.items[order_id] = list(links)


class FakeDeliveryRepo:
    def __init__(self) -> None:
        self.ids: set[str] = set()

    async def seen(self, delivery_id: str) -> bool:
        return delivery_id in self.ids

    async def mark(self, delivery_id: str) -> None:
        self.ids.add(delivery_id)


class FakeGithub:
    def __init__(self) -> None:
        self.repo = GithubRepo(owner="acme", name="shop", url="https://github.com/acme/shop", node_id="R_1")
        self.projects = [GithubProject(id="PVT_1", title="Board")]
        self.milestones = [
            GithubMilestone(title="v1", due_on="2026-09-01T00:00:00Z", open_issues=1, closed_issues=0, state="open"),
            GithubMilestone(title="v2", due_on="2026-10-01T00:00:00Z", open_issues=2, closed_issues=0, state="open"),
        ]
        self.issues: list[GithubIssue] = []
        self.created: list[dict[str, Any]] = []
        self.hooks: list[str] = []
        self.labels: set[str] = set()
        self.project_items: list[ProjectItem] = [
            ProjectItem(
                title="Draw UI",
                state="OPEN",
                status="In Progress",
                due="2026-09-12",
                milestone_title="v1",
                milestone_due_on="2026-09-01T00:00:00Z",
                is_closed=False,
            ),
            ProjectItem(
                title="Done task",
                state="CLOSED",
                status="Done",
                due=None,
                milestone_title="v1",
                milestone_due_on=None,
                is_closed=True,
            ),
        ]

    async def get_repo(self, owner: str, repo: str) -> GithubRepo:
        return GithubRepo(owner=owner, name=repo, url=f"https://github.com/{owner}/{repo}", node_id="R_1")

    async def list_repository_projects(self, owner: str, repo: str) -> list[GithubProject]:
        return list(self.projects)

    async def list_milestones(self, owner: str, repo: str) -> list[GithubMilestone]:
        return list(self.milestones)

    async def list_repo_issues(self, owner: str, repo: str) -> list[GithubIssue]:
        return list(self.issues)

    async def ensure_issues_webhook(self, owner: str, repo: str, hook_url: str, secret: str) -> None:
        self.hooks.append(hook_url)

    async def ensure_label(self, owner: str, repo: str, name: str, color: str = "c5def5") -> None:
        self.labels.add(name)

    async def create_issue(
        self, owner: str, repo: str, *, title: str, body: str, labels: list[str] | None = None
    ) -> GithubIssue:
        issue = GithubIssue(
            number=len(self.created) + 1,
            title=title,
            state="open",
            body=body,
            node_id="I_1",
            html_url=f"https://github.com/{owner}/{repo}/issues/{len(self.created) + 1}",
            milestone_title=None,
            milestone_due_on=None,
            is_pull_request=False,
        )
        self.created.append({"title": title, "body": body, "labels": labels})
        return issue

    async def add_issue_to_project(self, project_id: str, content_id: str) -> str:
        return "PVTI_1"

    async def set_project_status(self, project_id: str, item_id: str, status_field_name: str, option_name: str) -> None:
        self.created.append({"status": option_name, "project_id": project_id})

    async def list_project_items(self, project_id: str) -> list[ProjectItem]:
        return list(self.project_items)

    async def list_issue_comments(self, owner: str, repo: str, number: int) -> list[str]:
        return ["last comment with [link](https://example.com)"]


class FakeNotifier:
    def __init__(self) -> None:
        self.admin: list[tuple] = []
        self.customer: list[tuple] = []
        self.closed: list[tuple] = []

    async def notify_admins_new_order(self, order: Order, customer: User | None, locale: str = "ru") -> None:
        self.admin.append((order.id, customer, locale))

    async def notify_customer(self, telegram_id: int, locale: str, key: str, **kwargs: object) -> None:
        self.customer.append((telegram_id, locale, key, kwargs))

    async def send_closed_issue(self, telegram_id: int, locale: str, title: str, url: str, rendered: object) -> None:
        self.closed.append((telegram_id, title, url))


class FakeContext:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings(bot_token="t", admin_api_token="admin", jwt_secret="jwt")
        self.i18n = I18n(default_locale="ru")
        self.github = FakeGithub()
        self.notifier = FakeNotifier()
        self.users = FakeUserRepo()
        self.orders = FakeOrderRepo()
        self.links = FakeLinkRepo()
        self.deliveries = FakeDeliveryRepo()
        self.upsert_user = UpsertUser(self.users, self.settings.default_locale)
        self.set_language = SetLanguage(self.users)
        self.submit_order = SubmitOrder(self.users, self.orders)
        self.create_manual = CreateManualOrder(self.users, self.orders)
        self.list_orders = ListOrders(self.orders)
        self.get_order = GetOrder(self.orders, self.links)
        self.list_customer_orders = ListCustomerOrders(self.orders)
        self.change_status = ChangeStatus(self.orders)
        self.mark_spam = MarkSpam(self.orders)
        self.start_discussion = StartDiscussion(self.orders)
        self.complete_order = CompleteOrder(self.orders, self.links)
        self.list_projects = ListRepoProjects(self.github)
        self.start_in_progress = StartInProgress(self.orders, self.github, self.settings)
        self.build_progress = BuildProgress(self.orders, self.github, self.settings)
        self.create_request = CreateCustomerRequest(self.orders, self.github, self.settings)
        self.handle_issue_closed = HandleIssueClosed(self.orders, self.deliveries, self.github)
        self.create_support = CreateSupportTicket(self.users, self.orders)
