"""Reply and inline keyboards. Button labels come from i18n keys."""

from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from beerwolf_shop.domain.entities import Order
from beerwolf_shop.domain.enums import OrderStatus, OrderType
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.infrastructure.telegram.markdown import render_locale


class AdminOrderCb(CallbackData, prefix="aord"):
    action: str
    order_id: str


class AdminListCb(CallbackData, prefix="alist"):
    status: str
    page: int
    kind: str = "all"


class LangCb(CallbackData, prefix="lang"):
    code: str


class ProjectPickCb(CallbackData, prefix="aprj"):
    idx: int


class OrderViewCb(CallbackData, prefix="oview"):
    order_id: str


class MilestoneCb(CallbackData, prefix="mile"):
    action: str
    order_id: str
    number: int


STATUS_FILTERS: tuple[tuple[str, OrderStatus | None], ...] = (
    ("all", None),
    ("application", OrderStatus.application),
    ("discussion", OrderStatus.discussion),
    ("in_progress", OrderStatus.in_progress),
    ("completed", OrderStatus.completed),
    ("cancelled", OrderStatus.cancelled),
    ("spam", OrderStatus.spam),
)


def _label(i18n: I18n, locale: str, key: str, **kwargs: object) -> str:
    # Keyboard labels are plain text (not MarkdownV2).
    return i18n.get(locale, key, **kwargs)


def main_menu(i18n: I18n, locale: str, *, is_admin: bool, project: Order | None = None) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    if project is None or project.status == OrderStatus.completed:
        builder.button(text=_label(i18n, locale, "common.btn_new_order"))
    if project is not None:
        builder.button(text=_label(i18n, locale, "common.btn_my_order"))
    if project is not None and project.status in {OrderStatus.in_progress, OrderStatus.completed}:
        builder.button(text=_label(i18n, locale, "customer.btn_recommend"))
    builder.button(text=_label(i18n, locale, "common.btn_language"))
    if is_admin:
        builder.button(text=_label(i18n, locale, "admin.btn_menu"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def wizard_menu(i18n: I18n, locale: str, *, with_skip: bool) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    if with_skip:
        builder.button(text=_label(i18n, locale, "common.btn_skip"))
    builder.button(text=_label(i18n, locale, "common.btn_cancel"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def confirm_menu(i18n: I18n, locale: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=_label(i18n, locale, "common.btn_confirm"))
    builder.button(text=_label(i18n, locale, "common.btn_cancel"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def language_inline(i18n: I18n, locale: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=_label(i18n, locale, "common.btn_ru"), callback_data=LangCb(code="ru"))
    builder.button(text=_label(i18n, locale, "common.btn_en"), callback_data=LangCb(code="en"))
    return builder.as_markup()


def admin_new_order_actions(
    order_id: UUID,
    i18n: I18n,
    locale: str,
    order_type: OrderType = OrderType.commission,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    oid = str(order_id)
    if order_type == OrderType.support:
        builder.button(
            text=_label(i18n, locale, "admin.btn_support_take"),
            callback_data=AdminOrderCb(action="sup_take", order_id=oid),
        )
        builder.button(
            text=_label(i18n, locale, "admin.btn_support_cancel"),
            callback_data=AdminOrderCb(action="sup_cancel", order_id=oid),
        )
    else:
        builder.button(
            text=_label(i18n, locale, "admin.btn_take_discussion"),
            callback_data=AdminOrderCb(action="disc", order_id=oid),
        )
        builder.button(
            text=_label(i18n, locale, "admin.btn_spam"),
            callback_data=AdminOrderCb(action="spam", order_id=oid),
        )
    builder.button(
        text=_label(i18n, locale, "admin.btn_view"),
        callback_data=AdminOrderCb(action="view", order_id=oid),
    )
    builder.adjust(1)
    return builder.as_markup()


def admin_order_card(
    order_id: UUID,
    status: OrderStatus,
    i18n: I18n,
    locale: str,
    order_type: OrderType = OrderType.commission,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    oid = str(order_id)
    if order_type == OrderType.support and status == OrderStatus.application:
        builder.button(
            text=_label(i18n, locale, "admin.btn_support_take"),
            callback_data=AdminOrderCb(action="sup_take", order_id=oid),
        )
        builder.button(
            text=_label(i18n, locale, "admin.btn_support_cancel"),
            callback_data=AdminOrderCb(action="sup_cancel", order_id=oid),
        )
    elif order_type == OrderType.support and status == OrderStatus.in_progress:
        builder.button(
            text=_label(i18n, locale, "admin.btn_complete"),
            callback_data=AdminOrderCb(action="sup_done", order_id=oid),
        )
    elif status == OrderStatus.application:
        builder.button(
            text=_label(i18n, locale, "admin.btn_take_discussion"),
            callback_data=AdminOrderCb(action="disc", order_id=oid),
        )
        builder.button(
            text=_label(i18n, locale, "admin.btn_spam"),
            callback_data=AdminOrderCb(action="spam", order_id=oid),
        )
    if status == OrderStatus.discussion:
        builder.button(
            text=_label(i18n, locale, "admin.btn_in_progress"),
            callback_data=AdminOrderCb(action="ip", order_id=oid),
        )
        builder.button(
            text=_label(i18n, locale, "admin.btn_spam"),
            callback_data=AdminOrderCb(action="spam", order_id=oid),
        )
    if status == OrderStatus.in_progress:
        if order_type == OrderType.commission:
            builder.button(
                text=_label(i18n, locale, "admin.btn_complete"),
                callback_data=AdminOrderCb(action="done", order_id=oid),
            )
    builder.button(
        text=_label(i18n, locale, "admin.btn_back_list"),
        callback_data=AdminListCb(
            status="application" if order_type == OrderType.support else "all",
            page=0,
            kind="support" if order_type == OrderType.support else "all",
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def admin_list_keyboard(
    i18n: I18n,
    locale: str,
    *,
    current: str,
    page: int,
    has_next: bool,
    orders: list[tuple[UUID, str]],
    kind: str = "all",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order_id, title in orders:
        builder.button(text=title, callback_data=AdminOrderCb(action="view", order_id=str(order_id)))
    for key, _status in STATUS_FILTERS:
        marker = "• " if key == current else ""
        builder.button(
            text=f"{marker}{_label(i18n, locale, f'admin.filter_{key}')}",
            callback_data=AdminListCb(status=key, page=0, kind=kind),
        )
    nav = []
    if page > 0:
        nav.append(("common.btn_prev", AdminListCb(status=current, page=page - 1, kind=kind)))
    if has_next:
        nav.append(("common.btn_next", AdminListCb(status=current, page=page + 1, kind=kind)))
    for key, cb in nav:
        builder.button(text=_label(i18n, locale, key), callback_data=cb)
    builder.button(text=_label(i18n, locale, "admin.btn_create"), callback_data="admin:create")
    builder.button(text=_label(i18n, locale, "admin.btn_support_queue"), callback_data="admin:support")
    builder.adjust(1, 1, 1, 1, 1, 3, 3, 2, 2)
    return builder.as_markup()


def admin_menu(i18n: I18n, locale: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=_label(i18n, locale, "admin.btn_orders"), callback_data=AdminListCb(status="all", page=0))
    builder.button(text=_label(i18n, locale, "admin.btn_support_queue"), callback_data="admin:support")
    builder.button(text=_label(i18n, locale, "admin.btn_create"), callback_data="admin:create")
    builder.adjust(1)
    return builder.as_markup()


def project_choice(projects: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, (_pid, title) in enumerate(projects):
        builder.button(text=title[:60], callback_data=ProjectPickCb(idx=index))
    builder.adjust(1)
    return builder.as_markup()


def customer_order_actions(
    i18n: I18n,
    locale: str,
    order_id: UUID,
    status: OrderStatus,
    *,
    order_type: OrderType = OrderType.commission,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    oid = str(order_id)
    if status == OrderStatus.in_progress:
        builder.button(text=_label(i18n, locale, "customer.btn_request"), callback_data=f"cust:req:{oid}")
    if status == OrderStatus.completed:
        builder.button(text=_label(i18n, locale, "customer.btn_links"), callback_data=f"cust:links:{oid}")
        if order_type == OrderType.commission:
            builder.button(text=_label(i18n, locale, "customer.btn_support"), callback_data=f"cust:sup:{oid}")
    builder.adjust(1)
    return builder.as_markup()


def recommendation_share(i18n: I18n, locale: str, bot_username: str, share_text: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    url = f"https://t.me/share/url?url={quote(f'https://t.me/{bot_username}')}&text={quote(share_text)}"
    builder.button(text=_label(i18n, locale, "customer.btn_share"), url=url)
    return builder.as_markup()


def progress_milestones(
    i18n: I18n,
    locale: str,
    order_id: UUID,
    milestones: list,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for milestone in milestones:
        due = f" · {milestone.due_on[:10]}" if milestone.due_on else ""
        builder.button(
            text=f"{milestone.title}{due}"[:64],
            callback_data=MilestoneCb(
                action="open",
                order_id=str(order_id),
                number=milestone.number,
            ),
        )
    builder.adjust(1)
    return builder.as_markup()


def milestone_back(i18n: I18n, locale: str, order_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=_label(i18n, locale, "common.btn_back"),
        callback_data=MilestoneCb(action="back", order_id=str(order_id), number=0),
    )
    return builder.as_markup()


def customer_orders_list(orders: list[tuple[UUID, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order_id, title in orders:
        builder.button(text=title[:60], callback_data=OrderViewCb(order_id=str(order_id)))
    builder.adjust(1)
    return builder.as_markup()


def render_md(i18n: I18n, locale: str, key: str, **kwargs: object) -> str:
    return render_locale(i18n.get(locale, key), **kwargs)
