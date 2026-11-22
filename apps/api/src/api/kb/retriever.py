"""KB retrieval: embed the query, rank chunks by cosine similarity.

Why embeddings in the app's own Postgres instead of a Studio Library: the docs recommend
Libraries / document search for a KB of this size, but a Studio Library needs console
provisioning and workspace sharing, and cannot be exercised in local tests at all. The
prototype therefore embeds with `mistral-embed` (Mistral SDK only) and stores vectors in the
app's own Postgres — self-contained, deployable as-is, testable offline with a fake embedder.
The rejected alternative (Studio Library + `document_library` tool) is what the pre-read will
recommend for production. The KB is ~100 small chunks, so exact in-Python cosine is instant;
the deployed image ships pgvector for the day this outgrows brute force.
"""

import hashlib
import json
import math
from typing import Protocol

from db import accessors as acc
from db.engine import get_session_maker
from db.models.kb_chunk import KbChunk
from env.assistant import env as assistant_env
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from utils.mistral import mistral_client


class KbPassage(BaseModel):
    source: str  # e.g. knowledge/fr/plafonds-virements.md
    chunk_index: int
    content: str
    score: float


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class MistralEmbedder:
    """Embeds through the Mistral embeddings API (`mistral-embed`, 1024 dims)."""

    def __init__(self, client=None, model: str | None = None):
        self._client = client
        self._model = model or assistant_env.embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = self._client or mistral_client()
        response = await client.embeddings.create_async(model=self._model, inputs=texts)
        return [list(data.embedding) for data in response.data]


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder for offline tests (no API key needed).
    Word-level hashing into a wide space so French keyword overlap ranks the right doc."""

    DIM = 2048

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        import re

        vec = [0.0] * self.DIM
        for token in re.findall(r"[a-zàâäéèêëîïôöùûüç0-9]+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vec[digest[0] % self.DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1.0)


async def retrieve(
    query: str,
    *,
    embedder: Embedder,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    top_k: int | None = None,
) -> list[KbPassage]:
    """Top-k passages for a query. Retrieval is dumb by design: it returns whatever ranks high,
    including any poisoned content — treating retrieved text as untrusted is the agent's job."""
    session_maker = session_maker or get_session_maker()
    top_k = top_k or assistant_env.kb_top_k
    query_vec = (await embedder.embed([query]))[0]
    async with session_maker() as session:
        chunks = await acc.kb_chunks.list_all(session)
    scored = []
    for chunk in chunks:
        vec = json.loads(chunk.embedding)
        scored.append((cosine(query_vec, vec), chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        KbPassage(source=chunk.doc_path, chunk_index=chunk.chunk_index, content=chunk.content, score=round(score, 4))
        for score, chunk in scored[:top_k]
    ]
