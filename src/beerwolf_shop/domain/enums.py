"""Domain enums."""

from enum import StrEnum


class OrderType(StrEnum):
    commission = "commission"
    support = "support"


class OrderStatus(StrEnum):
    application = "application"
    discussion = "discussion"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    spam = "spam"


# Statuses shown in the customer's "active order" menu (GitHub progress is only for in_progress).
ACTIVE_CUSTOMER_STATUSES = (
    OrderStatus.application,
    OrderStatus.discussion,
    OrderStatus.in_progress,
)

# Until admin takes the request further, the customer may still open "new request"
# (a fresh application replaces the previous one).
LOCKED_CUSTOMER_STATUSES = (
    OrderStatus.discussion,
    OrderStatus.in_progress,
)

ADMIN_FILTERABLE_STATUSES = tuple(OrderStatus)
