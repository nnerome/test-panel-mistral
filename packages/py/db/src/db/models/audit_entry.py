"""Audit log: one row per security-relevant event.

`masked_args` is JSON that has been scrubbed of anything resembling a full PAN/IBAN, so the
audit trail can never contain an unmasked card number even if a caller forgets to mask.
"""

import uuid
from datetime import datetime

from db.models._base import utcnow
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class AuditEntry(SQLModel, table=True):
    __tablename__ = "audit_entries"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ts: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    customer_id: uuid.UUID | None = Field(default=None, foreign_key="customers.id")
    session_id: uuid.UUID | None = Field(default=None, foreign_key="bank_sessions.id")
    auth_level: str
    action: str
    masked_args: str
    result: str
    correlation_id: str | None = None
