"""One feedback row per (session, turn): thumbs up/down with an optional reason and comment.

The unique constraint on (session_id, correlation_id) makes a second submission an update
(upsert), never a duplicate. `message_excerpt`/`answer_excerpt` are stored ONLY for "down"
ratings, scrubbed and truncated server-side (see the route), so the table holds no raw
conversation content beyond what a reviewer explicitly needs.
"""

import uuid
from datetime import datetime

from db.models._base import utcnow
from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class Feedback(SQLModel, table=True):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("session_id", "correlation_id", name="uq_feedback_session_turn"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    correlation_id: str = Field(foreign_key="turn_records.correlation_id", index=True, max_length=64)
    session_id: uuid.UUID = Field(foreign_key="bank_sessions.id", index=True)
    rating: str  # "up" | "down" (enum enforced by the API schema)
    reason: str | None = Field(default=None, max_length=40)  # wrong | off_topic | too_long | other
    comment: str | None = Field(default=None, max_length=280)
    message_excerpt: str | None = Field(default=None, max_length=500)
    answer_excerpt: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
