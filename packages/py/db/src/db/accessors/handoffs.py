"""Handoff queue accessor."""

import uuid

from db.models.handoff_request import HandoffRequest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def create(
    session: AsyncSession,
    *,
    correlation_id: str,
    session_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    reason: str,
    intent: str,
    auth_level: str,
    summary: str,
    pending_action_id: uuid.UUID | None,
) -> HandoffRequest:
    row = HandoffRequest(
        correlation_id=correlation_id,
        session_id=session_id,
        customer_id=customer_id,
        reason=reason,
        intent=intent,
        auth_level=auth_level,
        summary=summary,
        pending_action_id=pending_action_id,
    )
    session.add(row)
    await session.flush()
    return row


async def get(session: AsyncSession, handoff_id: uuid.UUID) -> HandoffRequest | None:
    return await session.get(HandoffRequest, handoff_id)


async def find_open(session: AsyncSession, session_id: uuid.UUID, reason: str) -> HandoffRequest | None:
    """The open request for this (session, reason), if any — one open per pair, no duplicates."""
    rows = await session.execute(
        select(HandoffRequest).where(HandoffRequest.session_id == session_id, HandoffRequest.reason == reason, HandoffRequest.status == "open")
    )
    return rows.scalars().first()


async def list_by_status(session: AsyncSession, status: str | None = "open", limit: int = 100) -> list[HandoffRequest]:
    stmt = select(HandoffRequest).order_by(HandoffRequest.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(HandoffRequest.status == status)
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def set_status(session: AsyncSession, row: HandoffRequest, status: str) -> None:
    row.status = status
    await session.flush()
