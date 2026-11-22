"""One-time-code table accessor."""

import uuid
from datetime import datetime

from db.models.otp_code import OtpCode
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, update


async def create(session: AsyncSession, *, session_id: uuid.UUID, code_hash: str, expires_at: datetime) -> OtpCode:
    row = OtpCode(session_id=session_id, code_hash=code_hash, expires_at=expires_at)
    session.add(row)
    await session.flush()
    return row


async def invalidate_active_for_session(session: AsyncSession, session_id: uuid.UUID, now: datetime) -> None:
    # A new code supersedes the previous ones: an old code can never be replayed later.
    await session.execute(
        update(OtpCode).where(OtpCode.session_id == session_id, OtpCode.used_at.is_(None)).values(expires_at=now)
    )


async def latest_active_for_session(session: AsyncSession, session_id: uuid.UUID, now: datetime) -> OtpCode | None:
    return (
        await session.execute(
            select(OtpCode)
            .where(OtpCode.session_id == session_id, OtpCode.used_at.is_(None), OtpCode.expires_at > now)
            .order_by(OtpCode.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def register_attempt(session: AsyncSession, row: OtpCode) -> None:
    row.attempts += 1
    await session.flush()


async def mark_used(session: AsyncSession, row: OtpCode, now: datetime) -> None:
    row.used_at = now
    await session.flush()
