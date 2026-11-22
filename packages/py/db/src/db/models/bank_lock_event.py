"""Idempotency ledger inside the mock bank adapter, standing in for the legacy card system's
own deduplication: one row per idempotency key, so a retried lock executes once."""

import uuid
from datetime import datetime

from db.models._base import utcnow
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class BankLockEvent(SQLModel, table=True):
    __tablename__ = "bank_lock_events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    idempotency_key: str = Field(unique=True, index=True)
    card_id: uuid.UUID = Field(foreign_key="cards.id")
    locked_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    result_json: str
