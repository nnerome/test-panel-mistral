"""Feedback accessor. One row per (session, turn): upsert, never a duplicate."""

import uuid
from datetime import datetime

from db.models.feedback import Feedback
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def upsert(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    correlation_id: str,
    rating: str,
    reason: str | None,
    comment: str | None,
    message_excerpt: str | None,
    answer_excerpt: str | None,
) -> Feedback:
    row = (
        await session.execute(select(Feedback).where(Feedback.session_id == session_id, Feedback.correlation_id == correlation_id))
    ).scalar_one_or_none()
    if row is None:
        row = Feedback(session_id=session_id, correlation_id=correlation_id, rating=rating)
        session.add(row)
    row.rating = rating
    row.reason = reason
    row.comment = comment
    row.message_excerpt = message_excerpt
    row.answer_excerpt = answer_excerpt
    await session.flush()
    return row


async def get(session: AsyncSession, feedback_id: uuid.UUID) -> Feedback | None:
    return await session.get(Feedback, feedback_id)


async def list_recent(session: AsyncSession, *, rating: str | None = None, limit: int = 50) -> list[Feedback]:
    stmt = select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
    if rating is not None:
        stmt = stmt.where(Feedback.rating == rating)
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def count_since(session: AsyncSession, since: datetime) -> tuple[int, int]:
    """(rated, down) feedback rows created since `since` — for the downvote rate."""
    rows = await session.execute(select(Feedback).where(Feedback.created_at >= since))
    all_rows = list(rows.scalars().all())
    return len(all_rows), sum(1 for r in all_rows if r.rating == "down")
