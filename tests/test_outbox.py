from uuid import uuid4

from beerwolf_shop.application.dto import SubmitOrderDTO
from beerwolf_shop.infrastructure.telegram.keyboards import AdminListCb
from beerwolf_shop.infrastructure.telegram.outbox import (
    KIND_CLOSED_ISSUE,
    KIND_NOTIFY_ADMINS,
    KIND_NOTIFY_CUSTOMER,
    deliver_outbox_event,
)

from tests.fakes import FakeContext


def test_admin_list_callback_keeps_support_kind() -> None:
    packed = AdminListCb(status="application", page=2, kind="support").pack()
    data = AdminListCb.unpack(packed)
    assert data.status == "application"
    assert data.page == 2
    assert data.kind == "support"


async def test_deliver_notify_admins_and_customer() -> None:
    ctx = FakeContext()
    order = await ctx.submit_order.execute(
        SubmitOrderDTO(customer_telegram_id=5, display_name="Ann", idea="logo")
    )
    await deliver_outbox_event(
        KIND_NOTIFY_ADMINS,
        {"order_id": str(order.id), "locale": "ru"},
        ctx.notifier,
        ctx.users,
        ctx.orders,
    )
    assert ctx.notifier.admin
    assert ctx.notifier.admin[0][0] == order.id

    await deliver_outbox_event(
        KIND_NOTIFY_CUSTOMER,
        {
            "telegram_id": 5,
            "locale": "ru",
            "key": "order.discussion_started",
            "kwargs": {"contact": "@admin"},
        },
        ctx.notifier,
        ctx.users,
        ctx.orders,
    )
    assert ctx.notifier.customer[-1][2] == "order.discussion_started"


async def test_deliver_closed_issue() -> None:
    ctx = FakeContext()
    await deliver_outbox_event(
        KIND_CLOSED_ISSUE,
        {
            "telegram_id": 9,
            "locale": "en",
            "title": "Done",
            "url": "https://github.com/acme/shop/issues/1",
            "html": "<p>hi</p>",
            "photos": [["https://ex.com/a.png", "art"]],
        },
        ctx.notifier,
        ctx.users,
        ctx.orders,
    )
    assert ctx.notifier.closed[0][0] == 9
    assert ctx.notifier.closed[0][1] == "Done"


async def test_deliver_missing_order_is_noop() -> None:
    ctx = FakeContext()
    await deliver_outbox_event(
        KIND_NOTIFY_ADMINS,
        {"order_id": str(uuid4()), "locale": "ru"},
        ctx.notifier,
        ctx.users,
        ctx.orders,
    )
    assert ctx.notifier.admin == []
