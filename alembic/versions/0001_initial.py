"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False, server_default="ru"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("customer_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("idea", sa.Text(), nullable=False),
        sa.Column("extra_contacts", sa.Text(), nullable=True),
        sa.Column("references", sa.Text(), nullable=True),
        sa.Column("budget", sa.String(), nullable=True),
        sa.Column("parent_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("github_repo_url", sa.String(), nullable=True),
        sa.Column("github_owner", sa.String(), nullable=True),
        sa.Column("github_repo", sa.String(), nullable=True),
        sa.Column("github_project_id", sa.String(), nullable=True),
        sa.Column("project_display_name", sa.String(), nullable=True),
        sa.Column("completion_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_order_id"], ["orders.id"]),
    )
    op.create_index("ix_orders_customer_telegram_id", "orders", ["customer_telegram_id"])
    op.create_index("ix_orders_type", "orders", ["type"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_parent_order_id", "orders", ["parent_order_id"])
    op.create_index("ix_orders_github_owner", "orders", ["github_owner"])
    op.create_index("ix_orders_github_repo", "orders", ["github_repo"])

    op.create_table(
        "completion_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
    )
    op.create_index("ix_completion_links_order_id", "completion_links", ["order_id"])

    op.create_table(
        "fsm_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("bot_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.BigInteger(), nullable=True),
        sa.Column("business_connection_id", sa.String(), nullable=False, server_default=""),
        sa.Column("destiny", sa.String(), nullable=False, server_default="default"),
        sa.Column("state", sa.String(), nullable=True),
        sa.Column("data", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint(
            "bot_id",
            "chat_id",
            "user_id",
            "thread_id",
            "business_connection_id",
            "destiny",
            name="uq_fsm_storage_key",
        ),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("delivery_id", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("fsm_states")
    op.drop_table("completion_links")
    op.drop_table("orders")
    op.drop_table("users")
