"""Card-lock execution table accessor. `create` relies on the primary key (the action id) for
idempotency: a concurrent replay raises IntegrityError, which the caller turns into 'return the
stored result'."""

import uuid

from db.models.card_lock_execution import CardLockExecution
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def get_by_action_id(session: AsyncSession, action_id: uuid.UUID) -> CardLockExecution | None:
    return await session.get(CardLockExecution, action_id)


async def create(session: AsyncSession, *, action_id: uuid.UUID, idempotency_key: str, result_json: str) -> CardLockExecution:
    row = CardLockExecution(action_id=action_id, idempotency_key=idempotency_key, result_json=result_json)
    session.add(row)
    await session.flush()
    return row
