"""Card table accessor — the only module allowed to know the cards table's shape.

The masking boundary is enforced HERE at the query level: no accessor ever selects the `pan`
column, so a full PAN cannot appear in a return value *or in the DB query logs*. Callers get
`pan_last4` only, and the adapter formats the masked number from it."""

import uuid
from datetime import datetime
from typing import NamedTuple

from db.models.card import Card
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, update


class CardViewRow(NamedTuple):
    card_id: uuid.UUID
    customer_id: uuid.UUID
    brand: str
    label: str
    status: str
    pan_last4: str


_VIEW_COLUMNS = (Card.id, Card.customer_id, Card.brand, Card.label, Card.status, Card.pan_last4)


async def get_owner(session: AsyncSession, card_id: uuid.UUID) -> uuid.UUID | None:
    """Ownership probe: returns the owning customer id, reading nothing else."""
    row = (await session.execute(select(Card.customer_id).where(Card.id == card_id))).scalar_one_or_none()
    return row


async def get_view(session: AsyncSession, card_id: uuid.UUID) -> CardViewRow | None:
    row = (await session.execute(select(*_VIEW_COLUMNS).where(Card.id == card_id))).first()
    return CardViewRow(*row) if row else None


async def list_views_for_customer(session: AsyncSession, customer_id: uuid.UUID) -> list[CardViewRow]:
    rows = (await session.execute(select(*_VIEW_COLUMNS).where(Card.customer_id == customer_id).order_by(Card.created_at))).all()
    return [CardViewRow(*row) for row in rows]


async def set_locked(session: AsyncSession, card_id: uuid.UUID, locked_at: datetime) -> None:
    await session.execute(update(Card).where(Card.id == card_id).values(status="locked", locked_at=locked_at))
