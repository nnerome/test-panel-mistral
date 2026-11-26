"""Turn telemetry accessor (one row per chat turn)."""

import uuid
from datetime import datetime

from db.models.turn_record import TurnRecord
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def record(
    session: AsyncSession,
    *,
    correlation_id: str,
    session_id: uuid.UUID | None,
    intent: str,
    auth_level: str,
    refused: bool,
    human_offer: bool,
    error: str | None,
    timings: str,
    model: str | None,
    tokens: str | None,
    disclaimer_shown: bool = False,
) -> TurnRecord:
    """Insert or update the row for this turn (idempotent on the correlation id)."""
    row = await session.get(TurnRecord, correlation_id)
    if row is None:
        row = TurnRecord(correlation_id=correlation_id)
        session.add(row)
    row.session_id = session_id
    row.intent = intent
    row.auth_level = auth_level
    row.refused = refused
    row.human_offer = human_offer
    row.error = error
    row.timings = timings
    row.model = model
    row.tokens = tokens
    row.disclaimer_shown = disclaimer_shown
    await session.flush()
    return row


async def get(session: AsyncSession, correlation_id: str) -> TurnRecord | None:
    return await session.get(TurnRecord, correlation_id)


async def list_since(session: AsyncSession, since: datetime, limit: int = 100_000) -> list[TurnRecord]:
    rows = await session.execute(select(TurnRecord).where(TurnRecord.created_at >= since).order_by(TurnRecord.created_at).limit(limit))
    return list(rows.scalars().all())


async def count_for_session(session: AsyncSession, session_id: uuid.UUID) -> int:
    """How many turns this session already has (used to flag the first one)."""
    from sqlalchemy import func

    result = await session.execute(select(func.count()).select_from(TurnRecord).where(TurnRecord.session_id == session_id))
    return int(result.scalar_one())


async def list_all(session: AsyncSession, limit: int = 100_000) -> list[TurnRecord]:
    rows = await session.execute(select(TurnRecord).order_by(TurnRecord.created_at).limit(limit))
    return list(rows.scalars().all())
