"""Server-side app session: anonymous, authenticated or strong.

Only the SHA-256 of the bearer token is stored; the level is a column the customer can never
write through a payload, and `customer_id` is NULL until login binds the session.
"""

import uuid
from datetime import datetime

from db.models._base import Base
from sqlalchemy import DateTime
from sqlmodel import Field


class BankSession(Base, table=True):
    __tablename__ = "bank_sessions"

    token_hash: str = Field(unique=True, index=True)
    customer_id: uuid.UUID | None = Field(default=None, foreign_key="customers.id")
    level: str = Field(default="anonymous", index=True)  # anonymous | authenticated | strong
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    last_seen_at: datetime = Field(sa_type=DateTime(timezone=True))
