"""Customer table accessor."""

import uuid

from db.models.customer import Customer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


async def get(session: AsyncSession, customer_id: uuid.UUID) -> Customer | None:
    return await session.get(Customer, customer_id)


async def get_by_email(session: AsyncSession, email: str) -> Customer | None:
    return (await session.execute(select(Customer).where(Customer.email == email.lower()))).scalar_one_or_none()


async def list_all(session: AsyncSession) -> list[Customer]:
    return list((await session.execute(select(Customer).order_by(Customer.email))).scalars().all())
