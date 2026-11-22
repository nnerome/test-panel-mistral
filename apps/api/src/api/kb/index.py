"""Index `knowledge/` into kb_chunks: chunk each markdown file, embed, store."""

import json
from pathlib import Path

from db import accessors as acc
from db.engine import get_session_maker
from db.models.kb_chunk import KbChunk
from env.assistant import env as assistant_env
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from api.kb.retriever import Embedder

REPO_ROOT = Path(__file__).resolve().parents[5]  # apps/api/src/api/kb/index.py -> repo root
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"


def chunk_markdown(text: str, max_chars: int) -> list[str]:
    """Split on blank lines (paragraphs/headings), then merge small neighbours up to max_chars."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks


async def index_knowledge(
    *,
    embedder: Embedder,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    root: Path | None = None,
) -> int:
    """Replace the KB index with the current content of `knowledge/`. Returns chunk count."""
    session_maker = session_maker or get_session_maker()
    root = root or KNOWLEDGE_DIR
    max_chars = assistant_env.kb_chunk_chars
    docs: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        docs.append((rel, path.read_text(encoding="utf-8")))
    chunks = [(rel, i, text) for rel, content in docs for i, text in enumerate(chunk_markdown(content, max_chars))]
    vectors = await embedder.embed([text for _, _, text in chunks])
    rows = [
        KbChunk(doc_path=rel, chunk_index=i, content=text, embedding=json.dumps(vec))
        for (rel, i, text), vec in zip(chunks, vectors)
    ]
    async with session_maker() as session:
        await acc.kb_chunks.replace_all(session, rows)
        await session.commit()
    return len(rows)


async def ensure_indexed(embedder: Embedder, session_maker: async_sessionmaker[AsyncSession] | None = None) -> None:
    """Index on first use only (empty table), so a restart does not re-embed everything."""
    session_maker = session_maker or get_session_maker()
    async with session_maker() as session:
        chunks = await acc.kb_chunks.list_all(session)
    if not chunks:
        await index_knowledge(embedder=embedder, session_maker=session_maker)
