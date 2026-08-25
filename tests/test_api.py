from fastapi.testclient import TestClient

from beerwolf_shop.application.auth import create_access_token
from beerwolf_shop.application.dto import SubmitOrderDTO
from beerwolf_shop.domain.enums import OrderStatus
from beerwolf_shop.main import create_app
from beerwolf_shop.presentation.api.deps import get_context, get_settings

from tests.fakes import FakeContext, make_test_settings
from tests.test_auth import make_init_data


def _client(ctx: FakeContext | None = None):
    settings = make_test_settings()
    ctx = ctx or FakeContext(settings)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_context] = lambda: ctx
    return TestClient(app), settings, ctx


def test_health() -> None:
    client, _settings, _ctx = _client()
    with client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_and_me() -> None:
    client, settings, ctx = _client()
    with client:
        response = client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(settings.bot_token)})
        assert response.status_code == 200
        token = response.json()["access_token"]
        me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["telegram_id"] == 99
        assert ctx.users.items[99].username == "ann"


def test_customer_creates_order() -> None:
    import asyncio

    client, settings, ctx = _client()
    token = create_access_token(settings, 99)
    asyncio.run(ctx.upsert_user.execute(99, "ann", display_name="Ann"))
    with client:
        created = client.post(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {token}"},
            json={"idea": "Wolf sprite", "display_name": "Ann"},
        )
        assert created.status_code == 201
        assert created.json()["status"] == "application"
        listed = client.get("/api/v1/orders", headers={"Authorization": f"Bearer {token}"})
        assert listed.status_code == 200
        assert len(listed.json()) == 1


def test_admin_status_and_list() -> None:
    import asyncio

    client, _settings, ctx = _client()
    order = asyncio.run(ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=5, display_name="A", idea="logo")))
    with client:
        listed = client.get(
            "/api/v1/admin/orders",
            headers={"Authorization": "Bearer admin-secret"},
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        changed = client.post(
            f"/api/v1/admin/orders/{order.id}/status",
            headers={"Authorization": "Bearer admin-secret"},
            json={"status": "discussion"},
        )
        assert changed.status_code == 200
        assert changed.json()["status"] == "discussion"
        assert ctx.notifier.customer[-1][2] == "order.discussion_started"


def test_github_webhook_closed_issue() -> None:
    import asyncio
    import hashlib
    import hmac
    import json

    client, settings, ctx = _client()
    payload = {
        "action": "closed",
        "issue": {
            "number": 3,
            "title": "Ship it",
            "body": "See [site](https://ex.com) ![art](https://ex.com/a.png)",
            "html_url": "https://github.com/acme/shop/issues/3",
        },
        "repository": {"name": "shop", "owner": {"login": "acme"}},
    }
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    async def _seed() -> None:
        order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=5, display_name="A", idea="logo"))
        order.github_owner = "acme"
        order.github_repo = "shop"
        order.status = OrderStatus.in_progress
        await ctx.orders.save(order)

    asyncio.run(_seed())
    with client:
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "del-1",
                "Content-Type": "application/json",
            },
        )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert ctx.notifier.closed


def test_github_webhook_rejects_unsigned() -> None:
    client, _settings, _ctx = _client()
    with client:
        response = client.post(
            "/webhooks/github",
            content=b'{"action":"closed"}',
            headers={"X-GitHub-Event": "issues", "Content-Type": "application/json"},
        )
    assert response.status_code == 401


def test_github_webhook_ignores_non_issues_event() -> None:
    import hashlib
    import hmac

    client, settings, _ctx = _client()
    body = b"{}"
    sig = "sha256=" + hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    with client:
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "push",
                "Content-Type": "application/json",
            },
        )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_github_webhook_duplicate_delivery() -> None:
    import asyncio
    import hashlib
    import hmac
    import json

    client, settings, ctx = _client()
    payload = {
        "action": "closed",
        "issue": {"number": 3, "title": "Ship it", "body": "done", "html_url": "https://github.com/acme/shop/issues/3"},
        "repository": {"name": "shop", "owner": {"login": "acme"}},
    }
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(settings.github_webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    async def _seed() -> None:
        order = await ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=5, display_name="A", idea="logo"))
        order.github_owner = "acme"
        order.github_repo = "shop"
        order.status = OrderStatus.in_progress
        await ctx.orders.save(order)

    asyncio.run(_seed())
    headers = {
        "X-Hub-Signature-256": sig,
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "del-dup",
        "Content-Type": "application/json",
    }
    with client:
        first = client.post("/webhooks/github", content=body, headers=headers)
        second = client.post("/webhooks/github", content=body, headers=headers)
    assert first.status_code == 200
    assert first.json()["status"] == "ok"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert len(ctx.notifier.closed) == 1


def test_customer_cannot_read_foreign_order() -> None:
    import asyncio

    client, settings, ctx = _client()
    order = asyncio.run(ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=5, display_name="A", idea="logo")))
    token = create_access_token(settings, 99)
    with client:
        response = client.get(f"/api/v1/orders/{order.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"


def test_admin_in_progress_from_application_is_conflict() -> None:
    import asyncio

    client, _settings, ctx = _client()
    order = asyncio.run(ctx.submit_order.execute(SubmitOrderDTO(customer_telegram_id=5, display_name="A", idea="logo")))
    with client:
        response = client.post(
            f"/api/v1/admin/orders/{order.id}/status",
            headers={"Authorization": "Bearer admin-secret"},
            json={
                "status": "in_progress",
                "github_repo_url": "https://github.com/acme/shop",
                "project_display_name": "Shop",
            },
        )
    assert response.status_code == 409
