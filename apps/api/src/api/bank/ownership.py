"""Ownership checks. The api layer MUST call one of these before touching any account or card
on behalf of a session — including reads, exactly as for the confirmation endpoint. A cross-
customer request raises `OwnershipError`, which maps to 404 so it never leaks existence.

The probes read only the owner column, never the object's secret fields."""

import uuid

from db import accessors as acc
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.errors import OwnershipError


async def assert_account_owned(session: AsyncSession, *, customer_id: uuid.UUID, account_id: uuid.UUID) -> None:
    owner = await acc.accounts.get_owner(session, account_id)
    if owner is None or owner != customer_id:
        raise OwnershipError("account not found")


async def assert_card_owned(session: AsyncSession, *, customer_id: uuid.UUID, card_id: uuid.UUID) -> None:
    owner = await acc.cards.get_owner(session, card_id)
    if owner is None or owner != customer_id:
        raise OwnershipError("card not found")
