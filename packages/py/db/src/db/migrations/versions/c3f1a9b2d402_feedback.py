"""feedback: thumbs up/down per (session, turn), unique so a resend is an update

Revision ID: c3f1a9b2d402
Revises: c3f1a9b2d401
Create Date: 2026-11-25 09:11:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op


revision: str = "c3f1a9b2d402"
down_revision: str | Sequence[str] | None = "c3f1a9b2d401"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=True),
        sa.Column("comment", sa.String(length=280), nullable=True),
        sa.Column("message_excerpt", sa.String(length=500), nullable=True),
        sa.Column("answer_excerpt", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["correlation_id"], ["turn_records.correlation_id"],),
        sa.ForeignKeyConstraint(["session_id"], ["bank_sessions.id"],),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "correlation_id", name="uq_feedback_session_turn"),
    )
    op.create_index(op.f("ix_feedback_correlation_id"), "feedback", ["correlation_id"], unique=False)
    op.create_index(op.f("ix_feedback_session_id"), "feedback", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_feedback_session_id"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_correlation_id"), table_name="feedback")
    op.drop_table("feedback")
