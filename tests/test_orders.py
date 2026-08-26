import pytest

from beerwolf_shop.application.dto import CompleteOrderDTO, LinkGithubDTO, SubmitOrderDTO
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.domain.exceptions import (
    ActiveCommissionExistsError,
    GithubIntegrationError,
    InvalidStatusTransitionError,
)

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
async def test_submit_replaces_pending_application() -> None:
    ctx = FakeContext()
    first = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=42, display_name="Wolf", idea="First"))
    second = await ctx.submit_order.execute(
        SubmitOrderDTO(customer_telegram_id=42, display_name="Wolf", idea="Second", photo_file_ids=["file-1"])
    )
    stored_first = await ctx.orders.get(first.id)
    assert stored_first is not None
    assert stored_first.status == OrderStatus.cancelled
    assert second.status == OrderStatus.application
    assert second.idea == "Second"
    assert second.photo_file_ids == ["file-1"]


@pytest.mark.asyncio
async def test_customer_cannot_submit_second_active_commission() -> None:
    ctx = FakeContext()
    order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=42, display_name="Wolf", idea="First"))
    await ctx.start_discussion.execute(order.id)
    with pytest.raises(ActiveCommissionExistsError):
        await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=42, display_name="Wolf", idea="Second"))


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
async def test_support_take_and_complete_reopens_and_closes_parent() -> None:
    ctx = FakeContext()
    parent = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=9, display_name="A", idea="game"))
    parent.status = OrderStatus.completed
    parent.github_owner = "acme"
    parent.github_repo = "shop"
    parent.github_repo_url = "https://github.com/acme/shop"
    await ctx.orders.save(parent)
    ticket, _ = await ctx.create_support.execute(parent.id, 9, "fix collision")

    active_ticket, active_parent = await ctx.take_support.execute(ticket.id)
    assert active_ticket.status == OrderStatus.in_progress
    assert active_ticket.github_milestone_number is not None
    assert active_parent.status == OrderStatus.in_progress

    done_ticket, done_parent = await ctx.complete_support.execute(ticket.id)
    assert done_ticket.status == OrderStatus.completed
    assert done_parent.status == OrderStatus.completed
    milestone = await ctx.github.get_milestone("acme", "shop", active_ticket.github_milestone_number)
    assert milestone.state == "closed"


@pytest.mark.asyncio
async def test_cancel_support_keeps_parent_completed() -> None:
    ctx = FakeContext()
    parent = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=10, display_name="A", idea="game"))
    parent.status = OrderStatus.completed
    await ctx.orders.save(parent)
    ticket, _ = await ctx.create_support.execute(parent.id, 10, "not needed")

    cancelled, stored_parent = await ctx.cancel_support.execute(ticket.id)
    assert cancelled.status == OrderStatus.cancelled
    assert stored_parent.status == OrderStatus.completed


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
async def test_admin_status_workflows_can_override_current_stage() -> None:
    ctx = FakeContext()
    order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=1, display_name="A", idea="logo"))

    linked, _milestones, _projects = await ctx.start_in_progress.execute(
        LinkGithubDTO(
            order_id=order.id,
            repo_url="https://github.com/acme/shop",
            project_display_name="Shop",
        ),
        allow_any_status=True,
    )
    assert linked.status == OrderStatus.in_progress

    done = await ctx.complete_order.execute(
        CompleteOrderDTO(order_id=order.id),
        allow_any_status=True,
    )
    assert done.status == OrderStatus.completed

    cancelled = await ctx.cancel_order.execute(order.id)
    assert cancelled.status == OrderStatus.cancelled


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
    issue = await ctx.create_request.execute(
        CustomerRequestDTO(order_id=linked.id, wish="Bigger ears\npls", actor_telegram_id=5)
    )
    assert issue.html_url.endswith("/issues/1")
    assert await ctx.request_issues.find_order_id(issue.node_id) == linked.id


@pytest.mark.asyncio
async def test_admin_stats_count_commission_pipeline() -> None:
    ctx = FakeContext()
    await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=1, display_name="A", idea="a"))
    second = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=2, display_name="B", idea="b"))
    await ctx.start_discussion.execute(second.id)
    stored = await ctx.orders.get(second.id)
    assert stored is not None
    stored.status = OrderStatus.in_progress
    await ctx.orders.save(stored)
    third = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=3, display_name="C", idea="c"))
    third.status = OrderStatus.completed
    await ctx.orders.save(third)
    stats = await ctx.get_admin_stats.execute()
    assert stats == {"new": 1, "in_progress": 1, "completed": 1}
