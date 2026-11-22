"""Agency table accessor."""

import uuid

from db.models.agency import Agency
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def get(session: AsyncSession, agency_id: uuid.UUID) -> Agency | None:
    return await session.get(Agency, agency_id)

async def list_all(session: AsyncSession) -> list[Agency]:
    return list((await session.execute(select(Agency).order_by(Agency.name))).scalars().all())
