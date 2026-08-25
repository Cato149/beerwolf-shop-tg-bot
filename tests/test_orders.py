import pytest

from beerwolf_shop.application.dto import CompleteOrderDTO, LinkGithubDTO, SubmitOrderDTO
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import GithubIntegrationError, InvalidStatusTransitionError

from tests.fakes import FakeContext


@pytest.mark.asyncio
async def test_submit_and_spam_does_not_change_customer_flow() -> None:
    ctx = FakeContext()
    order = await ctx.submit_order.execute(
        SubmitOrderDTO(
            customer_telegram_id=42,
            display_name="Wolf",
            idea="Pixel art wolf",
            extra_contacts="discord:w",
        )
    )
    assert order.status == OrderStatus.application
    user = await ctx.users.get_by_telegram_id(42)
    assert user is not None
    assert user.display_name == "Wolf"
    spam = await ctx.mark_spam.execute(order.id)
    assert spam.status == OrderStatus.spam


@pytest.mark.asyncio
async def test_discussion_then_complete_requires_in_progress() -> None:
    ctx = FakeContext()
    order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=7, display_name="A", idea="logo"))
    discussed = await ctx.start_discussion.execute(order.id)
    assert discussed.status == OrderStatus.discussion
    with pytest.raises(InvalidStatusTransitionError):
        await ctx.complete_order.execute(CompleteOrderDTO(order_id=order.id, links=[], message="x"))


@pytest.mark.asyncio
async def test_complete_stores_links() -> None:
    ctx = FakeContext()
    order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=7, display_name="A", idea="logo"))
    await ctx.start_discussion.execute(order.id)
    order.github_owner = "acme"
    order.github_repo = "shop"
    order.status = OrderStatus.discussion
    await ctx.orders.save(order)
    linked, _ms, _projects = await ctx.start_in_progress.execute(
        LinkGithubDTO(
            order_id=order.id,
            repo_url="https://github.com/acme/shop",
            project_display_name="Wolf shop",
        )
    )
    assert linked.status == OrderStatus.in_progress
    done = await ctx.complete_order.execute(
        CompleteOrderDTO(order_id=order.id, links=[("https://ex.com", "Site")], message="thanks")
    )
    assert done.status == OrderStatus.completed
    links = await ctx.links.list_for_order(order.id)
    assert links[0].url == "https://ex.com"
    assert links[0].title == "Site"


@pytest.mark.asyncio
async def test_support_ticket_links_parent() -> None:
    ctx = FakeContext()
    parent = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=9, display_name="A", idea="game"))
    parent.status = OrderStatus.completed
    await ctx.orders.save(parent)
    ticket, stored_parent = await ctx.create_support.execute(parent.id, 9, "fix collision")
    assert ticket.type == OrderType.support
    assert ticket.parent_order_id == parent.id
    assert stored_parent.id == parent.id


@pytest.mark.asyncio
async def test_in_progress_requires_discussion() -> None:
    ctx = FakeContext()
    order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=1, display_name="A", idea="logo"))
    with pytest.raises(InvalidStatusTransitionError):
        await ctx.start_in_progress.execute(
            LinkGithubDTO(
                order_id=order.id,
                repo_url="https://github.com/acme/shop",
                project_display_name="Shop",
            )
        )


@pytest.mark.asyncio
async def test_customer_request_survives_project_add_failure() -> None:
    from beerwolf_shop.application.dto import CustomerRequestDTO

    ctx = FakeContext()
    order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=5, display_name="A", idea="ui"))
    await ctx.start_discussion.execute(order.id)
    linked, _ms, _projects = await ctx.start_in_progress.execute(
        LinkGithubDTO(order_id=order.id, repo_url="https://github.com/acme/shop", project_display_name="Shop")
    )
    ctx.github.add_project_error = GithubIntegrationError("github_project_add_failed")
    url = await ctx.create_request.execute(
        CustomerRequestDTO(order_id=linked.id, title="Bigger ears", body="pls", actor_telegram_id=5)
    )
    assert url.endswith("/issues/1")
