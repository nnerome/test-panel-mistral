"""turn_records: disclaimer_shown (AI disclaimer displayed at conversation start)

Revision ID: e7a1b93c2d54
Revises: c3f1a9b2d403
Create Date: 2026-11-25 20:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e7a1b93c2d54"
down_revision: str | Sequence[str] | None = "c3f1a9b2d403"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "turn_records",
        sa.Column("disclaimer_shown", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("turn_records", "disclaimer_shown")
