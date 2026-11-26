"""One row per chat turn, written at the end of the turn (metrics + feedback correlation).

Deliberately stores NO message or answer text: free text lives only in scrubbed, truncated
feedback excerpts, so this telemetry table can never leak raw conversation content.
"""

import uuid
from datetime import datetime

from db.models._base import utcnow
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class TurnRecord(SQLModel, table=True):
    __tablename__ = "turn_records"

    # The orchestrator's per-turn id; primary key so a double write can never duplicate a turn.
    correlation_id: str = Field(primary_key=True, max_length=64)
    session_id: uuid.UUID | None = Field(default=None, foreign_key="bank_sessions.id", index=True)
    intent: str = Field(default="unknown", index=True)
    auth_level: str = Field(default="anonymous")
    refused: bool = Field(default=False)
    human_offer: bool = Field(default=False)
    error: str | None = Field(default=None, max_length=200)
    timings: str = Field(default="[]")  # JSON list of {"stage": str, "ms": float}
    model: str | None = Field(default=None, max_length=100)  # null when the API returns none
    tokens: str | None = Field(default=None)  # JSON usage object, null when unavailable
    # True on the first turn of a session: the AI disclaimer was displayed at conversation start.
    disclaimer_shown: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
