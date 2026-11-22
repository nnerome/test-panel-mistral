"""Account table accessor. Like cards, the full `iban` column is never selected by any query:
callers get the prefix and last 4, which the adapter masks into a display IBAN."""

import uuid
from typing import NamedTuple

from db.models.account import Account
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


class AccountViewRow(NamedTuple):
    account_id: uuid.UUID
    customer_id: uuid.UUID
    label: str
    iban_prefix: str
    iban_last4: str
    balance_cents: int
    currency: str


_VIEW_COLUMNS = (Account.id, Account.customer_id, Account.label, Account.iban_prefix, Account.iban_last4, Account.balance_cents, Account.currency)


async def get_owner(session: AsyncSession, account_id: uuid.UUID) -> uuid.UUID | None:
    return (await session.execute(select(Account.customer_id).where(Account.id == account_id))).scalar_one_or_none()


async def get_view(session: AsyncSession, account_id: uuid.UUID) -> AccountViewRow | None:
    row = (await session.execute(select(*_VIEW_COLUMNS).where(Account.id == account_id))).first()
    return AccountViewRow(*row) if row else None


async def list_views_for_customer(session: AsyncSession, customer_id: uuid.UUID) -> list[AccountViewRow]:
    rows = (await session.execute(select(*_VIEW_COLUMNS).where(Account.customer_id == customer_id).order_by(Account.label))).all()
    return [AccountViewRow(*row) for row in rows]
