"""One-time step-up code. Single-use, hashed at rest, short-lived, attempt-limited."""

import uuid
from datetime import datetime

from db.models._base import Base
from sqlalchemy import DateTime
from sqlmodel import Field


class OtpCode(Base, table=True):
    __tablename__ = "otp_codes"

    session_id: uuid.UUID = Field(foreign_key="bank_sessions.id", index=True)
    code_hash: str
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    attempts: int = 0
    used_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
