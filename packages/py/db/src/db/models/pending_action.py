"""A state-changing action proposed by the agent and awaiting explicit user confirmation.

Bound to the session that created it; the confirm endpoint re-checks that binding, the auth
level, the expiry and the card ownership before executing anything.
"""

import uuid
from datetime import datetime

from db.models._base import Base
from sqlalchemy import DateTime
from sqlmodel import Field


class PendingAction(Base, table=True):
    __tablename__ = "pending_actions"

    session_id: uuid.UUID = Field(foreign_key="bank_sessions.id", index=True)
    customer_id: uuid.UUID = Field(foreign_key="customers.id", index=True)
    kind: str  # e.g. "lock_card"
    card_id: uuid.UUID = Field(foreign_key="cards.id")
    status: str = Field(default="pending", index=True)  # pending | confirmed | cancelled | expired
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
