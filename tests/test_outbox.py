from uuid import uuid4

from beerwolf_shop.application.dto import SubmitOrderDTO
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.keyboards import AdminListCb, admin_order_card
from beerwolf_shop.infrastructure.telegram.markdown import SafeHtml
from beerwolf_shop.infrastructure.telegram.outbox import (
    KIND_CLOSED_ISSUE,
    KIND_NOTIFY_ADMINS,
    KIND_NOTIFY_CUSTOMER,
    deliver_outbox_event,
    deserialize_rich_value,
    serialize_rich_value,
)

from tests.fakes import FakeContext


def test_admin_list_callback_keeps_support_kind() -> None:
    packed = AdminListCb(status="application", page=2, kind="support").pack()
    data = AdminListCb.unpack(packed)
    assert data.status == "application"
    assert data.page == 2
    assert data.kind == "support"


def test_support_card_has_take_and_cancel_actions() -> None:
    markup = admin_order_card(
        uuid4(),
        OrderStatus.application,
        I18n(default_locale="ru"),
        "ru",
        OrderType.support,
    )
    callbacks = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert any(value and "sup_take" in value for value in callbacks)
    assert any(value and "sup_cancel" in value for value in callbacks)
    back = next(value for value in callbacks if value and value.startswith("alist:"))
    assert AdminListCb.unpack(back).kind == "support"


def test_safe_html_survives_outbox_serialization() -> None:
    encoded = serialize_rich_value({"links": SafeHtml('<a href="https://example.com">Project</a>')})
    decoded = deserialize_rich_value(encoded)
    assert isinstance(decoded, dict)
    assert isinstance(decoded["links"], SafeHtml)
    assert decoded["links"] == '<a href="https://example.com">Project</a>'


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
            "refresh_menu": True,
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
    assert ctx.notifier.issue_updates[0][0] == 9
    assert ctx.notifier.issue_updates[0][2] == "Done"


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
