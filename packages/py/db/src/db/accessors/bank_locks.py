"""Adapter-side idempotency ledger accessor."""

from datetime import datetime

from db.models.bank_lock_event import BankLockEvent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def get_by_key(session: AsyncSession, idempotency_key: str) -> BankLockEvent | None:
    return (await session.execute(select(BankLockEvent).where(BankLockEvent.idempotency_key == idempotency_key))).scalar_one_or_none()


async def create(session: AsyncSession, *, idempotency_key: str, card_id, result_json: str, locked_at: datetime) -> BankLockEvent:
    row = BankLockEvent(idempotency_key=idempotency_key, card_id=card_id, result_json=result_json, locked_at=locked_at)
    session.add(row)
    await session.flush()
    return row
