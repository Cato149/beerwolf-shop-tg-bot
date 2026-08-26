"""GitHub linking, progress, customer requests, and issue webhook handling."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from beerwolf_shop.application.dto import (
    CustomerRequestDTO,
    LinkGithubDTO,
    MilestoneDetails,
    MilestoneSummary,
    MilestoneTask,
    ProgressSnapshot,
)
from beerwolf_shop.application.orders import assert_owner, assert_transition, require_order
from beerwolf_shop.config import Settings
from beerwolf_shop.domain.entities import CustomerRequestIssue, Order
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import (
    AccessDeniedError,
    DuplicateDeliveryError,
    GithubIntegrationError,
    InvalidStatusTransitionError,
)
from beerwolf_shop.domain.protocols import (
    CustomerRequestIssueRepository,
    MilestoneNotificationRepository,
    OrderRepository,
    RollbackRegistry,
    WebhookDeliveryRepository,
)
from beerwolf_shop.infrastructure.github.client import (
    CUSTOMER_REQUEST_LABEL,
    ClosedIssuePayload,
    GithubClient,
    GithubIssue,
    GithubMilestone,
    GithubProject,
    parse_repo_url,
)
from beerwolf_shop.infrastructure.github.gfm import RenderedMarkdown, gfm_to_telegram

READY_LABEL = "ready"


@dataclass(slots=True)
class GithubIssueEventResult:
    kind: str
    orders: list[Order]
    rendered: RenderedMarkdown
    issue: ClosedIssuePayload
    milestone: GithubMilestone | None = None
    milestone_orders: list[Order] | None = None


def _same_repo(item_repo: str, owner: str, repo: str) -> bool:
    return not item_repo or item_repo.casefold() == f"{owner}/{repo}".casefold()


def progress_bar(done: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "░" * width
    filled = min(width, round(width * done / total))
    return "▓" * filled + "░" * (width - filled)


class ListRepoProjects:
    def __init__(self, github: GithubClient) -> None:
        self._github = github

    async def execute(self, repo_url: str) -> tuple[str, str, list[GithubProject]]:
        owner, repo = parse_repo_url(repo_url)
        await self._github.get_repo(owner, repo)
        projects = await self._github.list_repository_projects(owner, repo)
        return owner, repo, projects


class StartInProgress:
    """Move an order to in_progress, bind repo + Project v2, install webhook, return milestones."""

    def __init__(self, orders: OrderRepository, github: GithubClient, settings: Settings) -> None:
        self._orders = orders
        self._github = github
        self._settings = settings

    async def execute(
        self,
        dto: LinkGithubDTO,
    ) -> tuple[Order, list[GithubMilestone], list[GithubProject]]:
        order = await require_order(self._orders, dto.order_id)
        assert_transition(order, OrderStatus.in_progress)
        owner, repo = parse_repo_url(dto.repo_url)
        github_repo = await self._github.get_repo(owner, repo)
        projects = await self._github.list_repository_projects(owner, repo)
        selected_id = dto.project_id
        project_ids = {item.id for item in projects}
        if selected_id is not None and selected_id not in project_ids:
            raise GithubIntegrationError("github_project_unknown")
        if selected_id is None:
            if len(projects) == 1:
                selected_id = projects[0].id
            elif len(projects) > 1:
                return order, [], projects
        if selected_id:
            existing = await self._orders.get_active_by_project_id(selected_id)
            if existing and existing.id != order.id:
                raise GithubIntegrationError("github_project_already_linked")
        hook_url = self._settings.github_webhook_url()
        if hook_url and self._settings.github_webhook_secret:
            await self._github.ensure_issues_webhook(owner, repo, hook_url, self._settings.github_webhook_secret)
        milestones = await self._github.list_milestones(owner, repo)
        order.status = OrderStatus.in_progress
        order.github_repo_url = github_repo.url
        order.github_owner = github_repo.owner
        order.github_repo = github_repo.name
        order.github_project_id = selected_id
        order.project_display_name = dto.project_display_name
        order.touch()
        saved = await self._orders.save(order)
        return saved, milestones, projects


class BuildProgress:
    def __init__(self, orders: OrderRepository, github: GithubClient, settings: Settings) -> None:
        self._orders = orders
        self._github = github
        self._settings = settings

    async def execute(
        self, order_id, *, actor_telegram_id: int | None = None, is_admin: bool = False
    ) -> ProgressSnapshot:
        order = await require_order(self._orders, order_id)
        if not is_admin:
            if actor_telegram_id is None:
                raise AccessDeniedError("not_owner")
            assert_owner(order, actor_telegram_id)
        if order.status not in {OrderStatus.in_progress, OrderStatus.completed}:
            raise GithubIntegrationError("progress_unavailable")
        if not order.github_owner or not order.github_repo:
            raise GithubIntegrationError("repo_not_linked")

        in_progress_names: list[str] = []
        total = 0
        done = 0
        source = "repo"
        if order.github_project_id:
            try:
                items = await self._github.list_project_items(order.github_project_id)
                items = [
                    item
                    for item in items
                    if _same_repo(item.repo_full_name, order.github_owner, order.github_repo)
                ]
                source = "project"
                total = len(items)
                done_name = self._settings.github_status_done.casefold()
                ip_name = self._settings.github_status_in_progress.casefold()
                for item in items:
                    is_done = item.is_closed or (item.status or "").casefold() == done_name
                    if is_done:
                        done += 1
                    status = (item.status or "").casefold()
                    if status == ip_name and not is_done:
                        due = item.due or item.milestone_due_on
                        label = item.title
                        if due:
                            label = f"{item.title} — {due[:10]}"
                        in_progress_names.append(label)
            except GithubIntegrationError:
                source = "repo"

        if source == "repo":
            issues = [
                issue
                for issue in await self._github.list_repo_issues(order.github_owner, order.github_repo)
                if not issue.is_pull_request
            ]
            source = "repo"
            total = len(issues)
            done = sum(1 for issue in issues if issue.state == "closed")
            in_progress_names = [issue.title for issue in issues if issue.state == "open"][:8]

        milestones = await self._github.list_milestones(order.github_owner, order.github_repo)
        percent = 0 if total == 0 else round(100 * done / total)
        return ProgressSnapshot(
            total=total,
            done=done,
            percent=percent,
            bar=progress_bar(done, total),
            in_progress=in_progress_names[:8],
            milestones=[
                MilestoneSummary(number=item.number, title=item.title, due_on=item.due_on)
                for item in milestones
            ],
            source=source,
        )


class GetMilestoneDetails:
    """Build one milestone view using Projects v2 metadata when available."""

    def __init__(self, orders: OrderRepository, github: GithubClient) -> None:
        self._orders = orders
        self._github = github

    async def execute(
        self,
        order_id: UUID,
        milestone_number: int,
        *,
        actor_telegram_id: int | None = None,
        is_admin: bool = False,
    ) -> MilestoneDetails:
        order = await require_order(self._orders, order_id)
        if not is_admin:
            if actor_telegram_id is None:
                raise AccessDeniedError("not_owner")
            assert_owner(order, actor_telegram_id)
        if order.status not in {OrderStatus.in_progress, OrderStatus.completed}:
            raise GithubIntegrationError("progress_unavailable")
        if not order.github_owner or not order.github_repo:
            raise GithubIntegrationError("repo_not_linked")

        milestone = await self._github.get_milestone(order.github_owner, order.github_repo, milestone_number)
        issues = await self._github.list_milestone_issues(order.github_owner, order.github_repo, milestone_number)
        project_items = (
            await self._github.list_project_items(order.github_project_id) if order.github_project_id else []
        )
        project_by_number = {
            item.number: item
            for item in project_items
            if item.number and _same_repo(item.repo_full_name, order.github_owner, order.github_repo)
        }
        tasks: list[MilestoneTask] = []
        for issue in issues:
            item = project_by_number.get(issue.number)
            status = item.status if item and item.status else ("Done" if issue.state == "closed" else "Open")
            tasks.append(
                MilestoneTask(
                    number=issue.number,
                    title=issue.title,
                    status=status,
                    due_on=item.due if item else None,
                )
            )
        return MilestoneDetails(
            number=milestone.number,
            title=milestone.title,
            due_on=milestone.due_on,
            tasks=tasks,
        )


class CreateCustomerRequest:
    def __init__(
        self,
        orders: OrderRepository,
        request_issues: CustomerRequestIssueRepository,
        github: GithubClient,
        settings: Settings,
        rollback_registry: RollbackRegistry | None = None,
    ) -> None:
        self._orders = orders
        self._request_issues = request_issues
        self._github = github
        self._settings = settings
        self._rollback_registry = rollback_registry

    async def execute(self, dto: CustomerRequestDTO) -> GithubIssue:
        order = await require_order(self._orders, dto.order_id)
        assert_owner(order, dto.actor_telegram_id)
        if order.status != OrderStatus.in_progress:
            raise InvalidStatusTransitionError("request_requires_in_progress")
        if not order.github_owner or not order.github_repo:
            raise GithubIntegrationError("repo_not_linked")
        wish = dto.wish.strip()
        title = next((line.strip() for line in wish.splitlines() if line.strip()), wish)[:80]
        await self._github.ensure_label(order.github_owner, order.github_repo, CUSTOMER_REQUEST_LABEL)
        issue = await self._github.create_issue(
            order.github_owner,
            order.github_repo,
            title=title,
            body=wish,
            labels=[CUSTOMER_REQUEST_LABEL],
        )
        if self._rollback_registry:
            self._rollback_registry.register(
                lambda: self._github.set_issue_state(
                    order.github_owner or "",
                    order.github_repo or "",
                    issue.number,
                    "closed",
                )
            )
        if issue.node_id:
            await self._request_issues.add(
                CustomerRequestIssue(order_id=order.id, github_node_id=issue.node_id)
            )
        if order.github_project_id and issue.node_id:
            try:
                item_id = await self._github.add_issue_to_project(order.github_project_id, issue.node_id)
                await self._github.set_project_status(
                    order.github_project_id,
                    item_id,
                    "Status",
                    self._settings.github_status_backlog,
                )
            except GithubIntegrationError:
                # Issue already exists; a missing project column or add failure must not hide the URL.
                pass
        return issue


class HandleGithubIssueEvent:
    def __init__(
        self,
        orders: OrderRepository,
        deliveries: WebhookDeliveryRepository,
        milestone_notifications: MilestoneNotificationRepository,
        request_issues: CustomerRequestIssueRepository,
        github: GithubClient,
    ) -> None:
        self._orders = orders
        self._deliveries = deliveries
        self._milestone_notifications = milestone_notifications
        self._request_issues = request_issues
        self._github = github

    async def execute(
        self,
        delivery_id: str | None,
        payload: dict,
    ) -> GithubIssueEventResult | None:
        action = payload.get("action")
        if action not in {"closed", "labeled"}:
            return None
        issue = payload.get("issue") or {}
        if issue.get("pull_request"):
            return None
        if action == "labeled":
            label = (payload.get("label") or {}).get("name") or ""
            labels = {str(item.get("name") or "").casefold() for item in issue.get("labels") or []}
            if label.casefold() != READY_LABEL or CUSTOMER_REQUEST_LABEL.casefold() not in labels:
                return None
        repo = payload.get("repository") or {}
        owner = (repo.get("owner") or {}).get("login") or ""
        name = repo.get("name") or ""
        if not owner or not name:
            return None
        try:
            number = int(issue["number"])
        except (KeyError, TypeError, ValueError):
            return None
        if delivery_id:
            claimed = await self._deliveries.claim(delivery_id)
            if not claimed:
                raise DuplicateDeliveryError(delivery_id)
        comments = await self._github.list_issue_comments(owner, name, number) if action == "closed" else []
        last_comment = next((body for body in reversed(comments) if body.strip()), None)
        body = last_comment or issue.get("body") or ""
        title = issue.get("title") or ""
        rendered = gfm_to_telegram(body, fallback_caption=title)
        closed = ClosedIssuePayload(
            owner=owner,
            repo=name,
            number=number,
            title=title,
            body=body,
            last_comment=last_comment,
            html_url=issue.get("html_url") or "",
            is_pull_request=False,
        )
        candidates = [
            order
            for order in await self._orders.find_by_repo(owner, name)
            if order.status == OrderStatus.in_progress and order.type == OrderType.commission
        ]
        matched: list[Order] = []
        project_cache: dict[str, list] = {}
        issue_node_id = str(issue.get("node_id") or "")
        mapped_order_id = await self._request_issues.find_order_id(issue_node_id) if issue_node_id else None
        if mapped_order_id:
            mapped = await self._orders.get(mapped_order_id)
            if mapped in candidates:
                matched = [mapped]
        for order in candidates if not mapped_order_id else []:
            if not order.github_project_id:
                matched.append(order)
                continue
            items = project_cache.get(order.github_project_id)
            if items is None:
                items = await self._github.list_project_items(order.github_project_id)
                project_cache[order.github_project_id] = items
            belongs = any(
                (issue_node_id and item.node_id == issue_node_id)
                or (
                    item.number == number
                    and _same_repo(item.repo_full_name, owner, name)
                )
                for item in items
            )
            if belongs:
                matched.append(order)
        milestone = None
        milestone_orders: list[Order] = []
        milestone_payload = issue.get("milestone") or {}
        if action == "closed" and milestone_payload.get("number"):
            milestone = await self._github.get_milestone(owner, name, int(milestone_payload["number"]))
            if milestone.open_issues == 0 and milestone.closed_issues > 0:
                for order in matched:
                    if await self._milestone_notifications.claim(order.id, milestone.number):
                        milestone_orders.append(order)
        return GithubIssueEventResult(
            kind="ready" if action == "labeled" else "closed",
            orders=matched,
            rendered=rendered,
            issue=closed,
            milestone=milestone,
            milestone_orders=milestone_orders,
        )
