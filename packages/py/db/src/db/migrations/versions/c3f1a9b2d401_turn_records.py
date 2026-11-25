"""turn_records: one row per chat turn (telemetry for metrics and feedback correlation)

Revision ID: c3f1a9b2d401
Revises: 68064a80683b
Create Date: 2026-11-25 09:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op


revision: str = "c3f1a9b2d401"
down_revision: str | Sequence[str] | None = "68064a80683b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "turn_records",
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("intent", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("auth_level", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("refused", sa.Boolean(), nullable=False),
        sa.Column("human_offer", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.Column("timings", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("tokens", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["bank_sessions.id"],),
        sa.PrimaryKeyConstraint("correlation_id"),
    )
    op.create_index(op.f("ix_turn_records_session_id"), "turn_records", ["session_id"], unique=False)
    op.create_index(op.f("ix_turn_records_intent"), "turn_records", ["intent"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_turn_records_intent"), table_name="turn_records")
    op.drop_index(op.f("ix_turn_records_session_id"), table_name="turn_records")
    op.drop_table("turn_records")
