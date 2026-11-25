"""One advisor-handoff request per (session, reason) while open — created automatically when a
turn offers a human. The summary is a deterministic template (no model call) holding only masked
identifiers: never a full PAN, never balances or raw account data."""

import uuid

from db.models._base import Base
from sqlmodel import Field


class HandoffRequest(Base, table=True):
    __tablename__ = "handoff_requests"

    correlation_id: str = Field(foreign_key="turn_records.correlation_id", max_length=64, index=True)
    session_id: uuid.UUID = Field(foreign_key="bank_sessions.id", index=True)
    customer_id: uuid.UUID | None = Field(default=None, foreign_key="customers.id")
    reason: str = Field(index=True)  # human_request | out_of_scope | guardrail_refusal | bank_error | actions_disabled | step_up_needed
    intent: str
    auth_level: str
    summary: str  # deterministic template, scrubbed
    pending_action_id: uuid.UUID | None = Field(default=None, foreign_key="pending_actions.id")
    status: str = Field(default="open", index=True)  # open | taken | closed
