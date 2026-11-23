"""Bank session table accessor."""

import uuid
from datetime import datetime

from db.models.bank_session import BankSession
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def create(session: AsyncSession, *, token_hash: str, level: str, expires_at: datetime, last_seen_at: datetime, customer_id: uuid.UUID | None = None) -> BankSession:
    row = BankSession(token_hash=token_hash, level=level, expires_at=expires_at, last_seen_at=last_seen_at, customer_id=customer_id)
    session.add(row)
    await session.flush()
    return row


async def get_by_token_hash(session: AsyncSession, token_hash: str) -> BankSession | None:
    return (await session.execute(select(BankSession).where(BankSession.token_hash == token_hash))).scalar_one_or_none()


async def get(session: AsyncSession, session_id: uuid.UUID) -> BankSession | None:
    return await session.get(BankSession, session_id)


async def set_level(session: AsyncSession, row: BankSession, level: str, last_seen_at: datetime) -> None:
    row.level = level
    row.last_seen_at = last_seen_at
    await session.flush()


async def touch(session: AsyncSession, row: BankSession, last_seen_at: datetime) -> None:
    row.last_seen_at = last_seen_at
    await session.flush()


async def delete(session: AsyncSession, row: BankSession) -> None:
    await session.delete(row)


async def expire(session: AsyncSession, row: BankSession, when: datetime) -> None:
    """Soft-delete: the row stays (otp_codes / pending_actions / audit_entries reference it by
    FK without cascade, so a hard delete would violate them), but it resolves to None once
    `expires_at` is in the past."""
    row.expires_at = when
    await session.flush()
