"""Human-readable Telegram HTML cards and project updates."""

from beerwolf_shop.application.dto import MilestoneDetails
from beerwolf_shop.domain.entities import CompletionLink, Order, User
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.infrastructure.github.gfm import gfm_to_telegram
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.keyboards import render_md
from beerwolf_shop.infrastructure.telegram.markdown import SafeHtml, html_lines, html_link


def status_label(i18n: I18n, locale: str, status: OrderStatus) -> str:
    return i18n.get(locale, f"order.status_{status.value}")


def task_status_label(i18n: I18n, locale: str, status: str) -> str:
    """Map standard GitHub Projects statuses while preserving custom columns."""
    normalized = status.strip().casefold().replace("_", " ")
    key = {
        "ready": "ready",
        "in progress": "in_progress",
        "done": "done",
        "open": "open",
    }.get(normalized)
    return i18n.get(locale, f"progress.task_status_{key}") if key else status


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
    return "\n".join(lines)


def milestone_message(i18n: I18n, locale: str, details: MilestoneDetails) -> str:
    due = details.due_on[:10] if details.due_on else i18n.get(locale, "progress.none")
    lines = [
        render_md(
            i18n,
            locale,
            "progress.milestone_header",
            title=details.title,
            due=due,
            done=details.done,
            total=details.total,
            percent=details.percent,
        )
    ]
    if not details.tasks:
        lines.append(render_md(i18n, locale, "progress.milestone_empty"))
    for task in details.tasks:
        task_due = task.due_on[:10] if task.due_on else i18n.get(locale, "progress.none")
        labels = ", ".join(task.labels) if task.labels else i18n.get(locale, "progress.none")
        lines.append(
            render_md(
                i18n,
                locale,
                "progress.milestone_task",
                title=task.title,
                status=task_status_label(i18n, locale, task.status),
                due=task_due,
                labels=labels,
            )
        )
        rendered_description = gfm_to_telegram(
            task.description,
            fallback_caption=task.title,
            extract_images=False,
        ).html
        description: str | SafeHtml = (
            SafeHtml(rendered_description)
            if rendered_description
            else i18n.get(locale, "progress.task_description_empty")
        )
        lines.append(
            render_md(
                i18n,
                locale,
                "progress.milestone_task_description",
                description=description,
            )
        )
    return "\n\n".join(lines)


def completion_links_html(links: list[CompletionLink], fallback: str) -> SafeHtml:
    """Render result links with readable labels and validated destinations."""
    if not links:
        return SafeHtml(fallback)
    return html_lines([SafeHtml(f"• {html_link(link.title, link.url)}") for link in links])


def list_title(order: Order, i18n: I18n, locale: str) -> str:
    prefix = "🛠" if order.type.value == "support" else "🎨"
    return f"{prefix} {status_label(i18n, locale, order.status)} · {order.idea[:32]}"
