"""Pending action table accessor."""

import uuid
from datetime import datetime

from db.models.pending_action import PendingAction
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, update


async def create(session: AsyncSession, *, session_id: uuid.UUID, customer_id: uuid.UUID, kind: str, card_id: uuid.UUID, expires_at: datetime) -> PendingAction:
    row = PendingAction(session_id=session_id, customer_id=customer_id, kind=kind, card_id=card_id, expires_at=expires_at)
    session.add(row)
    await session.flush()
    return row


async def get(session: AsyncSession, action_id: uuid.UUID) -> PendingAction | None:
    return await session.get(PendingAction, action_id)


async def set_status(session: AsyncSession, row: PendingAction, status: str) -> None:
    row.status = status
    await session.flush()


async def expire_stale(session: AsyncSession, now: datetime) -> None:
    await session.execute(update(PendingAction).where(PendingAction.status == "pending", PendingAction.expires_at <= now).values(status="expired"))


async def list_since(session: AsyncSession, since: datetime) -> list[PendingAction]:
    """Pending actions created since `since` (for the metrics window)."""
    rows = await session.execute(select(PendingAction).where(PendingAction.created_at >= since).order_by(PendingAction.created_at))
    return list(rows.scalars().all())
