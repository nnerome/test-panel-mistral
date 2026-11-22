"""Audit log accessor."""

import uuid

from db.models.audit_entry import AuditEntry
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def add(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    auth_level: str,
    action: str,
    masked_args: str,
    result: str,
    correlation_id: str | None,
) -> AuditEntry:
    row = AuditEntry(
        customer_id=customer_id,
        session_id=session_id,
        auth_level=auth_level,
        action=action,
        masked_args=masked_args,
        result=result,
        correlation_id=correlation_id,
    )
    session.add(row)
    await session.flush()
    return row


async def list_all(session: AsyncSession, limit: int = 500) -> list[AuditEntry]:
    return list((await session.execute(select(AuditEntry).order_by(AuditEntry.ts.desc()).limit(limit))).scalars().all())
