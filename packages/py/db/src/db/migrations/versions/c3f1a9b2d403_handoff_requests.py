"""handoff_requests: advisor handoff queue (one open request per session+reason)

Revision ID: c3f1a9b2d403
Revises: c3f1a9b2d402
Create Date: 2026-11-25 09:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op


revision: str = "c3f1a9b2d403"
down_revision: str | Sequence[str] | None = "c3f1a9b2d402"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "handoff_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("intent", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("auth_level", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("pending_action_id", sa.Uuid(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["correlation_id"], ["turn_records.correlation_id"],),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"],),
        sa.ForeignKeyConstraint(["pending_action_id"], ["pending_actions.id"],),
        sa.ForeignKeyConstraint(["session_id"], ["bank_sessions.id"],),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_handoff_requests_correlation_id"), "handoff_requests", ["correlation_id"], unique=False)
    op.create_index(op.f("ix_handoff_requests_session_id"), "handoff_requests", ["session_id"], unique=False)
    op.create_index(op.f("ix_handoff_requests_reason"), "handoff_requests", ["reason"], unique=False)
    op.create_index(op.f("ix_handoff_requests_status"), "handoff_requests", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_handoff_requests_status"), table_name="handoff_requests")
    op.drop_index(op.f("ix_handoff_requests_reason"), table_name="handoff_requests")
    op.drop_index(op.f("ix_handoff_requests_session_id"), table_name="handoff_requests")
    op.drop_index(op.f("ix_handoff_requests_correlation_id"), table_name="handoff_requests")
    op.drop_table("handoff_requests")
