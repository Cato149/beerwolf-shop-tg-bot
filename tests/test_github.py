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
    assert "Draw UI" in snapshot.in_progress[0]
    url = await ctx.create_request.execute(
        CustomerRequestDTO(order_id=linked.id, title="Bigger ears", body="pls", actor_telegram_id=5)
    )
    assert url.endswith("/issues/1")
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
