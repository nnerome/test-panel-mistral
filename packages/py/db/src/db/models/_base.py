"""Shared SQLModel base: UUID primary key and a creation timestamp on every table.

Lives in a `_`-prefixed module, which the models loader skips on purpose: it registers no table.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
