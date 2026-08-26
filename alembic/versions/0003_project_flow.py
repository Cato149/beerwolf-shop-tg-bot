"""single project, support milestone and milestone notifications

Revision ID: 0003_project_flow
Revises: 0002_outbox_events
Create Date: 2026-08-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_project_flow"
down_revision: Union[str, None] = "0002_outbox_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("github_milestone_number", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("github_milestone_title", sa.String(), nullable=True))
    op.create_index("ix_orders_github_milestone_number", "orders", ["github_milestone_number"])

    # Older releases allowed several unfinished commissions per customer.
    # Keep the most recently updated one active and preserve older rows as cancelled
    # instead of deleting customer history before adding the invariant.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY customer_telegram_id
                        ORDER BY
                            CASE status
                                WHEN 'in_progress' THEN 3
                                WHEN 'discussion' THEN 2
                                ELSE 1
                            END DESC,
                            updated_at DESC,
                            created_at DESC,
                            id DESC
                    ) AS position
                FROM orders
                WHERE type = 'commission'
                  AND status IN ('application', 'discussion', 'in_progress')
            )
            UPDATE orders
            SET status = 'cancelled', updated_at = now()
            FROM ranked
            WHERE orders.id = ranked.id
              AND ranked.position > 1
            """
        )
    )

    # PostgreSQL enforces the invariant even when two requests arrive concurrently.
    op.create_index(
        "uq_orders_one_active_commission_per_customer",
        "orders",
        ["customer_telegram_id"],
        unique=True,
        postgresql_where=sa.text(
            "type = 'commission' AND status IN ('application', 'discussion', 'in_progress')"
        ),
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY github_project_id
                        ORDER BY
                            CASE status
                                WHEN 'in_progress' THEN 3
                                WHEN 'discussion' THEN 2
                                ELSE 1
                            END DESC,
                            updated_at DESC,
                            created_at DESC,
                            id DESC
                    ) AS position
                FROM orders
                WHERE type = 'commission'
                  AND status IN ('application', 'discussion', 'in_progress')
                  AND github_project_id IS NOT NULL
            )
            UPDATE orders
            SET status = 'cancelled', updated_at = now()
            FROM ranked
            WHERE orders.id = ranked.id
              AND ranked.position > 1
            """
        )
    )
    op.create_index(
        "uq_orders_one_active_commission_per_github_project",
        "orders",
        ["github_project_id"],
        unique=True,
        postgresql_where=sa.text(
            "type = 'commission' "
            "AND status IN ('application', 'discussion', 'in_progress') "
            "AND github_project_id IS NOT NULL"
        ),
    )

    op.create_table(
        "milestone_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_milestone_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "order_id",
            "github_milestone_number",
            name="uq_milestone_notifications_order_number",
        ),
    )
    op.create_index("ix_milestone_notifications_order_id", "milestone_notifications", ["order_id"])
    op.create_table(
        "customer_request_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_node_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customer_request_issues_order_id", "customer_request_issues", ["order_id"])
    op.create_index(
        "ix_customer_request_issues_github_node_id",
        "customer_request_issues",
        ["github_node_id"],
        unique=True,
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_customer_request_issues_github_node_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_customer_request_issues_order_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS customer_request_issues"))
    op.drop_index("ix_milestone_notifications_order_id", table_name="milestone_notifications")
    op.drop_table("milestone_notifications")
    op.execute(sa.text("DROP INDEX IF EXISTS uq_orders_one_active_commission_per_github_project"))
    op.drop_index("uq_orders_one_active_commission_per_customer", table_name="orders")
    op.drop_index("ix_orders_github_milestone_number", table_name="orders")
    op.drop_column("orders", "github_milestone_title")
    op.drop_column("orders", "github_milestone_number")
