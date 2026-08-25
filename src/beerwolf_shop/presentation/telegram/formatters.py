"""Human-readable order cards (still rendered as MarkdownV2 via locale templates)."""

from beerwolf_shop.domain.entities import Order, User
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.keyboards import render_md


def status_label(i18n: I18n, locale: str, status: OrderStatus) -> str:
    return i18n.get(locale, f"order.status_{status.value}")


def type_label(i18n: I18n, locale: str, order_type: OrderType) -> str:
    return i18n.get(locale, f"order.type_{order_type.value}")


def dash(i18n: I18n, locale: str) -> str:
    return i18n.get(locale, "order.dash")


def customer_order_card(i18n: I18n, locale: str, order: Order) -> str:
    return render_md(
        i18n,
        locale,
        "order.order_card",
        type=type_label(i18n, locale, order.type),
        status=status_label(i18n, locale, order.status),
        idea=order.idea,
    )


def admin_order_card(i18n: I18n, locale: str, order: Order, customer: User | None, parent: Order | None) -> str:
    username = f"@{customer.username}" if customer and customer.username else dash(i18n, locale)
    name = customer.display_name if customer else str(order.customer_telegram_id)
    parent_id = str(parent.id) if parent else dash(i18n, locale)
    return render_md(
        i18n,
        locale,
        "admin.order_card",
        id=str(order.id),
        type=type_label(i18n, locale, order.type),
        status=status_label(i18n, locale, order.status),
        name=name,
        username=username,
        telegram_id=str(order.customer_telegram_id),
        idea=order.idea,
        contacts=order.extra_contacts or dash(i18n, locale),
        references=order.references or dash(i18n, locale),
        budget=order.budget or dash(i18n, locale),
        repo=order.github_repo_url or dash(i18n, locale),
        project=order.project_display_name or dash(i18n, locale),
        parent=parent_id,
    )


def progress_message(i18n: I18n, locale: str, project: str, snapshot) -> str:
    lines = [
        render_md(
            i18n,
            locale,
            "progress.header",
            project=project,
            done=snapshot.done,
            total=snapshot.total,
            bar=snapshot.bar,
            percent=snapshot.percent,
        )
    ]
    if snapshot.in_progress:
        lines.append(render_md(i18n, locale, "progress.in_work"))
        for item in snapshot.in_progress:
            lines.append(render_md(i18n, locale, "progress.in_work_item", item=item))
    if snapshot.current_milestone:
        lines.append(render_md(i18n, locale, "progress.current_milestone", title=snapshot.current_milestone))
    else:
        lines.append(render_md(i18n, locale, "progress.no_milestones"))
    if snapshot.next_milestone:
        lines.append(render_md(i18n, locale, "progress.next_milestone", title=snapshot.next_milestone))
    return "\n".join(lines)


def list_title(order: Order, i18n: I18n, locale: str) -> str:
    prefix = "🛠" if order.type.value == "support" else "🎨"
    return f"{prefix} {status_label(i18n, locale, order.status)} · {order.idea[:32]}"
