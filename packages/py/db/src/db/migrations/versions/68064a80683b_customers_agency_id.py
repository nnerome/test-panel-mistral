"""link customers to their agency (agency_id)

Revision ID: 68064a80683b
Revises: a5bcbdadb361
Create Date: 2026-11-23 16:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "68064a80683b"
down_revision: str | Sequence[str] | None = "a5bcbdadb361"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("agency_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_customers_agency_id", "customers", "agencies", ["agency_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_customers_agency_id", "customers", type_="foreignkey")
    op.drop_column("customers", "agency_id")
