"""Execution record of a confirmed action. The primary key IS the pending action's id, so the
UNIQUE constraint on it is what makes concurrent double-confirms execute exactly once: the
second insert fails and the stored result is returned instead."""

import uuid
from datetime import datetime

from db.models._base import utcnow
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class CardLockExecution(SQLModel, table=True):
    __tablename__ = "card_lock_executions"

    action_id: uuid.UUID = Field(foreign_key="pending_actions.id", primary_key=True)
    idempotency_key: str = Field(unique=True, index=True)
    result_json: str
    executed_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
