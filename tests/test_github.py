import json

import httpx
import pytest

from beerwolf_shop.infrastructure.github.client import GithubClient, parse_repo_url


def test_parse_repo_url() -> None:
    assert parse_repo_url("https://github.com/acme/shop") == ("acme", "shop")
    assert parse_repo_url("acme/shop.git") == ("acme", "shop")


@pytest.mark.asyncio
async def test_get_repo_and_graphql_mocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/repos/acme/shop":
            return httpx.Response(
                200,
                json={
                    "name": "shop",
                    "html_url": "https://github.com/acme/shop",
                    "node_id": "R_1",
                    "owner": {"login": "acme"},
                },
            )
        if request.method == "POST" and str(request.url).endswith("/graphql"):
            body = json.loads(request.content)
            assert "projectsV2" in body["query"]
            return httpx.Response(
                200,
                json={"data": {"repository": {"projectsV2": {"nodes": [{"id": "PVT_1", "title": "Board"}]}}}},
            )
        return httpx.Response(404, json={"message": "nope"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as http:
        client = GithubClient("token", client=http)
        repo = await client.get_repo("acme", "shop")
        assert repo.owner == "acme"
        projects = await client.list_repository_projects("acme", "shop")
        assert projects[0].title == "Board"


@pytest.mark.asyncio
async def test_progress_and_customer_request() -> None:
    from beerwolf_shop.application.dto import CustomerRequestDTO, LinkGithubDTO, SubmitOrderDTO
    from beerwolf_shop.domain.enums import OrderStatus

    from tests.fakes import FakeContext

    ctx = FakeContext()
    ctx.github.milestones[0].open_issues = 1
    ctx.github.milestones[0].closed_issues = 1
    order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=5, display_name="A", idea="ui"))
    await ctx.start_discussion.execute(order.id)
    linked, milestones, _ = await ctx.start_in_progress.execute(
        LinkGithubDTO(order_id=order.id, repo_url="https://github.com/acme/shop", project_display_name="Shop")
    )
    assert linked.status == OrderStatus.in_progress
    assert milestones[0].title == "v1"
    snapshot = await ctx.build_progress.execute(linked.id, actor_telegram_id=5)
    assert snapshot.total == 2
    assert snapshot.done == 1
    assert snapshot.percent == 50
    assert snapshot.milestones[0].percent == 50
    assert "Draw UI" in snapshot.in_progress[0]
    issue = await ctx.create_request.execute(
        CustomerRequestDTO(order_id=linked.id, wish="Bigger ears\npls", actor_telegram_id=5)
    )
    assert issue.html_url.endswith("/issues/1")
    assert issue.title == "Bigger ears"
    assert "customer request" in ctx.github.labels


@pytest.mark.asyncio
async def test_graphql_network_error_is_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as http:
        client = GithubClient("token", client=http)
        from beerwolf_shop.domain.exceptions import GithubIntegrationError

        with pytest.raises(GithubIntegrationError, match="github_unreachable"):
            await client.list_repository_projects("acme", "shop")


@pytest.mark.asyncio
async def test_rest_issue_parser_keeps_label_names() -> None:
    from beerwolf_shop.infrastructure.github.client import GithubClient

    async with httpx.AsyncClient(base_url="https://api.github.com") as http:
        client = GithubClient("token", client=http)
        issue = client._issue_from_rest(
            {
                "number": 1,
                "title": "Task",
                "state": "open",
                "labels": [{"name": "design"}, {"name": " ready "}, {"color": "fff"}],
            }
        )

    assert issue.labels == ["design", "ready"]


@pytest.mark.asyncio
async def test_milestone_details_use_project_status_and_due_date() -> None:
    from beerwolf_shop.application.dto import LinkGithubDTO, SubmitOrderDTO
    from beerwolf_shop.infrastructure.github.client import GithubIssue, ProjectItem

    from tests.fakes import FakeContext

    ctx = FakeContext()
    ctx.github.milestones[0].open_issues = 1
    ctx.github.milestones[0].closed_issues = 1
    order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=5, display_name="A", idea="ui"))
    await ctx.start_discussion.execute(order.id)
    linked, _, _ = await ctx.start_in_progress.execute(
        LinkGithubDTO(order_id=order.id, repo_url="https://github.com/acme/shop", project_display_name="Shop")
    )
    ctx.github.issues = [
        GithubIssue(
            number=1,
            title="Draw UI",
            state="open",
            body="**Detailed** brief",
            node_id="I_1",
            html_url="https://github.com/acme/shop/issues/1",
            milestone_title="v1",
            milestone_due_on="2026-09-01T00:00:00Z",
            is_pull_request=False,
            labels=["design", "ready"],
        )
    ]
    ctx.github.project_items.append(
        ProjectItem(
            number=1,
            node_id="OTHER_1",
            repo_full_name="acme/other",
            title="Other repository issue",
            state="OPEN",
            status="Blocked",
            due="2027-01-01",
            milestone_title="v1",
            milestone_due_on=None,
            is_closed=False,
        )
    )

    details = await ctx.get_milestone_details.execute(linked.id, 1, actor_telegram_id=5)
    assert details.title == "v1"
    assert details.total == 2
    assert details.done == 1
    assert details.percent == 50
    assert details.tasks[0].status == "In Progress"
    assert details.tasks[0].due_on == "2026-09-12"
    assert details.tasks[0].labels == ["design", "ready"]
    assert details.tasks[0].description == "**Detailed** brief"


@pytest.mark.asyncio
async def test_ready_and_milestone_completion_events_are_idempotent() -> None:
    from beerwolf_shop.application.dto import LinkGithubDTO, SubmitOrderDTO
    from beerwolf_shop.infrastructure.github.client import ProjectItem

    from tests.fakes import FakeContext

    ctx = FakeContext()
    order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=5, display_name="A", idea="ui"))
    await ctx.start_discussion.execute(order.id)
    linked, _, _ = await ctx.start_in_progress.execute(
        LinkGithubDTO(order_id=order.id, repo_url="https://github.com/acme/shop", project_display_name="Shop")
    )
    ctx.github.project_items.append(
        ProjectItem(
            number=7,
            node_id="I_7",
            repo_full_name="acme/shop",
            title="Bigger ears",
            state="OPEN",
            status="Backlog",
            due=None,
            milestone_title=None,
            milestone_due_on=None,
            is_closed=False,
        )
    )
    ready = await ctx.handle_github_issue_event.execute(
        "ready-1",
        {
            "action": "labeled",
            "label": {"name": "ready"},
            "issue": {
                "number": 7,
                "node_id": "I_7",
                "title": "Bigger ears",
                "body": "Please enlarge them",
                "html_url": "https://github.com/acme/shop/issues/7",
                "labels": [{"name": "customer request"}, {"name": "ready"}],
            },
            "repository": {"name": "shop", "owner": {"login": "acme"}},
        },
    )
    assert ready is not None
    assert ready.kind == "ready"
    assert ready.orders == [linked]

    ctx.github.milestones[0].open_issues = 0
    ctx.github.milestones[0].closed_issues = 1
    payload = {
        "action": "closed",
        "issue": {
            "number": 1,
            "title": "Draw UI",
            "body": "done",
            "html_url": "https://github.com/acme/shop/issues/1",
            "milestone": {"number": 1},
        },
        "repository": {"name": "shop", "owner": {"login": "acme"}},
    }
    first = await ctx.handle_github_issue_event.execute("closed-1", payload)
    second = await ctx.handle_github_issue_event.execute("closed-2", payload)
    assert first is not None and first.milestone_orders == [linked]
    assert second is not None and second.milestone_orders == []


@pytest.mark.asyncio
async def test_empty_selected_project_does_not_fallback_to_repository_issues() -> None:
    from beerwolf_shop.application.dto import LinkGithubDTO, SubmitOrderDTO
    from beerwolf_shop.infrastructure.github.client import GithubIssue

    from tests.fakes import FakeContext

    ctx = FakeContext()
    order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=5, display_name="A", idea="ui"))
    await ctx.start_discussion.execute(order.id)
    linked, _, _ = await ctx.start_in_progress.execute(
        LinkGithubDTO(order_id=order.id, repo_url="https://github.com/acme/shop", project_display_name="Shop")
    )
    ctx.github.project_items = []
    ctx.github.issues = [
        GithubIssue(
            number=99,
            title="Unrelated repository issue",
            state="open",
            body="",
            node_id="I_99",
            html_url="https://github.com/acme/shop/issues/99",
            milestone_title=None,
            milestone_due_on=None,
            is_pull_request=False,
        )
    ]

    snapshot = await ctx.build_progress.execute(linked.id, actor_telegram_id=5)
    assert snapshot.source == "project"
    assert snapshot.total == 0


@pytest.mark.asyncio
async def test_active_github_project_cannot_be_linked_twice() -> None:
    from beerwolf_shop.application.dto import LinkGithubDTO, SubmitOrderDTO
    from beerwolf_shop.domain.exceptions import GithubIntegrationError

    from tests.fakes import FakeContext

    ctx = FakeContext()
    first = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=1, display_name="A", idea="one"))
    second = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=2, display_name="B", idea="two"))
    await ctx.start_discussion.execute(first.id)
    await ctx.start_discussion.execute(second.id)
    await ctx.start_in_progress.execute(
        LinkGithubDTO(order_id=first.id, repo_url="https://github.com/acme/shop", project_display_name="One")
    )
    with pytest.raises(GithubIntegrationError, match="github_project_already_linked"):
        await ctx.start_in_progress.execute(
            LinkGithubDTO(order_id=second.id, repo_url="https://github.com/acme/shop", project_display_name="Two")
        )


@pytest.mark.asyncio
async def test_stale_customer_request_mapping_never_falls_back_to_reused_project() -> None:
    from beerwolf_shop.application.dto import CustomerRequestDTO, LinkGithubDTO, SubmitOrderDTO
    from beerwolf_shop.domain.enums import OrderStatus

    from tests.fakes import FakeContext

    ctx = FakeContext()
    old = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=1, display_name="A", idea="old"))
    await ctx.start_discussion.execute(old.id)
    old, _, _ = await ctx.start_in_progress.execute(
        LinkGithubDTO(order_id=old.id, repo_url="https://github.com/acme/shop", project_display_name="Old")
    )
    issue = await ctx.create_request.execute(
        CustomerRequestDTO(order_id=old.id, wish="Old request", actor_telegram_id=1)
    )
    old.status = OrderStatus.completed
    await ctx.orders.save(old)

    new = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=2, display_name="B", idea="new"))
    await ctx.start_discussion.execute(new.id)
    await ctx.start_in_progress.execute(
        LinkGithubDTO(order_id=new.id, repo_url="https://github.com/acme/shop", project_display_name="New")
    )
    result = await ctx.handle_github_issue_event.execute(
        "stale-ready",
        {
            "action": "labeled",
            "label": {"name": "ready"},
            "issue": {
                "number": issue.number,
                "node_id": issue.node_id,
                "title": issue.title,
                "body": issue.body,
                "html_url": issue.html_url,
                "labels": [{"name": "customer request"}, {"name": "ready"}],
            },
            "repository": {"name": "shop", "owner": {"login": "acme"}},
        },
    )
    assert result is not None
    assert result.orders == []
