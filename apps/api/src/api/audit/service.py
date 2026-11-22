"""Audit write path. `masked_args` is JSON-serialized and passed through `scrub_secrets`, so a
13-19 digit run (a PAN) is masked even if a caller forgot to mask it upstream."""

import json
import uuid

from db import accessors as acc
from db.engine import get_session_maker
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from api.domain.masking import scrub_secrets


async def log_action(
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    *,
    customer_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    auth_level: str,
    action: str,
    masked_args: dict | None,
    result: str,
    correlation_id: str | None = None,
) -> None:
    session_maker = session_maker or get_session_maker()
    payload = scrub_secrets(json.dumps(masked_args or {}, ensure_ascii=False, default=str))
    async with session_maker() as session:
        await acc.audit.add(
            session,
            customer_id=customer_id,
            session_id=session_id,
            auth_level=auth_level,
            action=action,
            masked_args=payload,
            result=scrub_secrets(result),
            correlation_id=correlation_id,
        )
        await session.commit()
