"""One chunk of the FAQ knowledge base with its embedding.

The embedding is stored as a JSON list of floats rather than a pgvector column on purpose:
the prototype's KB is ~100 small chunks, so exact cosine in Python is instant, and the app then
runs on any Postgres (the deployed image ships pgvector for the day the KB outgrows this).
"""

from db.models._base import Base
from sqlmodel import Field


class KbChunk(Base, table=True):
    __tablename__ = "kb_chunks"

    doc_path: str = Field(index=True)
    chunk_index: int
    content: str
    embedding: str  # JSON-encoded list[float]
