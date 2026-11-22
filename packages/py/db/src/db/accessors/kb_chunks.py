"""Knowledge-base chunk accessor."""

from db.models.kb_chunk import KbChunk
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import delete, select


async def replace_all(session: AsyncSession, chunks: list[KbChunk]) -> None:
    await session.execute(delete(KbChunk))
    for chunk in chunks:
        session.add(chunk)
    await session.flush()


async def list_all(session: AsyncSession) -> list[KbChunk]:
    return list((await session.execute(select(KbChunk).order_by(KbChunk.doc_path, KbChunk.chunk_index))).scalars().all())
