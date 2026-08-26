"""In-memory fakes for use-case and API tests (no Postgres)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

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
from beerwolf_shop.config import BotMode, Settings
from beerwolf_shop.domain.entities import CompletionLink, CustomerRequestIssue, Order, User
from beerwolf_shop.domain.enums import ACTIVE_CUSTOMER_STATUSES, OrderStatus, OrderType
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
        public_base_url="",
        telegram_webhook_secret="tg-secret",
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

    async def get_for_update(self, order_id: UUID) -> Order | None:
        return self.items.get(order_id)

    async def lock_customer(self, telegram_id: int) -> None:
        _ = telegram_id

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

    async def get_active_commission(self, telegram_id: int) -> Order | None:
        rows = [
            order
            for order in self.items.values()
            if order.customer_telegram_id == telegram_id
            and order.type == OrderType.commission
            and order.status in ACTIVE_CUSTOMER_STATUSES
        ]
        return max(rows, key=lambda order: order.created_at) if rows else None

    async def get_latest_commission(self, telegram_id: int) -> Order | None:
        rows = [
            order
            for order in self.items.values()
            if order.customer_telegram_id == telegram_id
            and order.type == OrderType.commission
            and order.status not in {OrderStatus.spam, OrderStatus.cancelled}
        ]
        return max(rows, key=lambda order: order.created_at) if rows else None

    async def get_active_by_project_id(self, project_id: str) -> Order | None:
        return next(
            (
                order
                for order in self.items.values()
                if order.github_project_id == project_id
                and order.type == OrderType.commission
                and order.status in ACTIVE_CUSTOMER_STATUSES
            ),
            None,
        )

    async def find_by_repo(self, owner: str, repo: str) -> list[Order]:
        owner_key = owner.lower()
        repo_key = repo.lower()
        return [
            o
            for o in self.items.values()
            if (o.github_owner or "").lower() == owner_key and (o.github_repo or "").lower() == repo_key
        ]


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

    async def claim(self, delivery_id: str) -> bool:
        if delivery_id in self.ids:
            return False
        self.ids.add(delivery_id)
        return True


class FakeMilestoneNotificationRepo:
    def __init__(self) -> None:
        self.ids: set[tuple[UUID, int]] = set()

    async def claim(self, order_id: UUID, milestone_number: int) -> bool:
        key = (order_id, milestone_number)
        if key in self.ids:
            return False
        self.ids.add(key)
        return True


class FakeCustomerRequestIssueRepo:
    def __init__(self) -> None:
        self.items: dict[str, CustomerRequestIssue] = {}

    async def add(self, link: CustomerRequestIssue) -> None:
        self.items[link.github_node_id] = link

    async def find_order_id(self, github_node_id: str) -> UUID | None:
        link = self.items.get(github_node_id)
        return link.order_id if link else None


class FakeGithub:
    def __init__(self) -> None:
        self.repo = GithubRepo(owner="acme", name="shop", url="https://github.com/acme/shop", node_id="R_1")
        self.projects = [GithubProject(id="PVT_1", title="Board")]
        self.milestones = [
            GithubMilestone(
                number=1,
                title="v1",
                due_on="2026-09-01T00:00:00Z",
                open_issues=1,
                closed_issues=0,
                state="open",
            ),
            GithubMilestone(
                number=2,
                title="v2",
                due_on="2026-10-01T00:00:00Z",
                open_issues=2,
                closed_issues=0,
                state="open",
            ),
        ]
        self.issues: list[GithubIssue] = []
        self.created: list[dict[str, Any]] = []
        self.hooks: list[str] = []
        self.labels: set[str] = set()
        self.project_items: list[ProjectItem] = [
            ProjectItem(
                number=1,
                node_id="I_1",
                repo_full_name="acme/shop",
                title="Draw UI",
                state="OPEN",
                status="In Progress",
                due="2026-09-12",
                milestone_title="v1",
                milestone_due_on="2026-09-01T00:00:00Z",
                is_closed=False,
            ),
            ProjectItem(
                number=2,
                node_id="I_2",
                repo_full_name="acme/shop",
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

    async def get_milestone(self, owner: str, repo: str, number: int) -> GithubMilestone:
        return next(item for item in self.milestones if item.number == number)

    async def create_milestone(self, owner: str, repo: str, title: str) -> GithubMilestone:
        milestone = GithubMilestone(
            number=max((item.number for item in self.milestones), default=0) + 1,
            title=title,
            due_on=None,
            open_issues=0,
            closed_issues=0,
            state="open",
        )
        self.milestones.append(milestone)
        return milestone

    async def close_milestone(self, owner: str, repo: str, number: int) -> None:
        await self.set_milestone_state(owner, repo, number, "closed")

    async def set_milestone_state(self, owner: str, repo: str, number: int, state: str) -> None:
        milestone = await self.get_milestone(owner, repo, number)
        milestone.state = state

    async def delete_milestone(self, owner: str, repo: str, number: int) -> None:
        self.milestones = [item for item in self.milestones if item.number != number]

    async def list_milestone_issues(self, owner: str, repo: str, number: int) -> list[GithubIssue]:
        title = (await self.get_milestone(owner, repo, number)).title
        return [issue for issue in self.issues if issue.milestone_title == title]

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

    async def set_issue_state(self, owner: str, repo: str, number: int, state: str) -> None:
        for issue in self.issues:
            if issue.number == number:
                issue.state = state

    async def add_issue_to_project(self, project_id: str, content_id: str) -> str:
        if getattr(self, "add_project_error", None):
            raise self.add_project_error
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
        self.admin_requests: list[tuple] = []
        self.customer: list[tuple] = []
        self.issue_updates: list[tuple] = []

    async def notify_admins_new_order(self, order: Order, customer: User | None, locale: str = "ru") -> None:
        self.admin.append((order.id, customer, locale))

    async def notify_admins_customer_request(
        self,
        order: Order,
        customer: User | None,
        title: str,
        wish: str,
        url: str,
        locale: str = "ru",
    ) -> None:
        self.admin_requests.append((order.id, customer, title, wish, url, locale))

    async def notify_customer(
        self,
        telegram_id: int,
        locale: str,
        key: str,
        *,
        refresh_menu: bool = False,
        reply_markup=None,
        **kwargs: object,
    ) -> None:
        _ = (refresh_menu, reply_markup)
        self.customer.append((telegram_id, locale, key, kwargs))

    def customer_menu(self, telegram_id: int, locale: str, project: Order | None):
        return {"telegram_id": telegram_id, "locale": locale, "project": project}

    async def send_issue_update(
        self,
        telegram_id: int,
        locale: str,
        header_key: str,
        title: str,
        url: str,
        rendered: object,
    ) -> None:
        self.issue_updates.append((telegram_id, header_key, title, url))


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
        self.milestone_notifications = FakeMilestoneNotificationRepo()
        self.request_issues = FakeCustomerRequestIssueRepo()
        self.upsert_user = UpsertUser(self.users, self.settings.default_locale)
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
        self.list_projects = ListRepoProjects(self.github)
        self.start_in_progress = StartInProgress(self.orders, self.github, self.settings)
        self.build_progress = BuildProgress(self.orders, self.github, self.settings)
        self.get_milestone_details = GetMilestoneDetails(self.orders, self.github)
        self.create_request = CreateCustomerRequest(
            self.orders,
            self.request_issues,
            self.github,
            self.settings,
        )
        self.handle_github_issue_event = HandleGithubIssueEvent(
            self.orders,
            self.deliveries,
            self.milestone_notifications,
            self.request_issues,
            self.github,
        )
        self.create_support = CreateSupportTicket(self.users, self.orders)
        self.take_support = TakeSupportTicket(self.orders, self.github)
        self.cancel_support = CancelSupportTicket(self.orders)
        self.complete_support = CompleteSupportTicket(self.orders, self.github)
