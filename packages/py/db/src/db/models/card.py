"""Fictional card. `pan` holds the full (fake) card number and NEVER leaves the adapter
layer: every DTO returned to callers carries only the masked number."""

import uuid
from datetime import datetime

from db.models._base import Base
from sqlalchemy import DateTime
from sqlmodel import Field


class Card(Base, table=True):
    __tablename__ = "cards"

    customer_id: uuid.UUID = Field(foreign_key="customers.id", index=True)
    account_id: uuid.UUID | None = Field(default=None, foreign_key="accounts.id")
    pan: str  # full FAKE number, read by nothing but the seed: accessors never select it
    pan_last4: str  # the only PAN fragment queries are allowed to carry
    brand: str
    label: str
    status: str = Field(default="active", index=True)  # active | locked
    locked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
