"""Strict Pydantic schemas for every API input and output. Extra fields are forbidden so a
crafted payload cannot smuggle in fields the server never reads."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AuthLevel = Literal["anonymous", "authenticated", "strong"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class SessionInfo(StrictModel):
    session_id: uuid.UUID
    level: AuthLevel
    customer_id: uuid.UUID | None
    customer_name: str | None = None
    expires_in_seconds: int


class LoginResponse(StrictModel):
    session: SessionInfo
    # The raw token, so the SPA can send it back in the X-Bnp-Session header: behind the Studio
    # gateway the module's Set-Cookie may not reach the browser (the gateway owns the domain's
    # cookies). The cookie is still set for direct/local access.
    token: str


class LogoutResponse(StrictModel):
    ok: bool


class StepUpResponse(StrictModel):
    otp_id: uuid.UUID
    expires_at: datetime
    # Present only because this is a demo with no SMS channel (DEMO_SHOW_OTP).
    demo_code: str | None = None


class VerifyOtpRequest(StrictModel):
    code: str = Field(pattern=r"^\d{6}$")


class DemoCustomer(StrictModel):
    email: str
    display_name: str
    # Demo hint only: all fake accounts share the same demo password.
    password: str


class BankFlagsBody(StrictModel):
    latency_ms: float = Field(ge=0, le=60000)
    failure_rate: float = Field(ge=0.0, le=1.0)


class BankFlagsView(StrictModel):
    latency_ms: float
    failure_rate: float
    defaults: BankFlagsBody


class DemoResetResponse(StrictModel):
    ok: bool
    cards_unlocked: int
    deleted: dict[str, int]


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=4000)
    # Optional UI language toggle: when set, the agent is asked to answer in that language
    # (the agents otherwise answer in the customer's own language).
    lang: Literal["fr", "en"] | None = None


class PendingActionView(StrictModel):
    id: uuid.UUID
    kind: str
    card_masked_number: str
    card_label: str
    status: str
    created_at: datetime
    expires_at: datetime


class ConfirmResponse(StrictModel):
    action: PendingActionView
    executed: bool  # False on replay: the stored result is returned, nothing re-executes
    result: dict


# --- feedback loop -----------------------------------------------------------

FeedbackRating = Literal["up", "down"]
FeedbackReason = Literal["wrong", "off_topic", "too_long", "other"]


class FeedbackRequest(StrictModel):
    correlation_id: str = Field(min_length=1, max_length=64)
    rating: FeedbackRating  # invalid values are rejected with 422 by the Literal
    reason: FeedbackReason | None = None
    comment: str | None = Field(default=None, max_length=280)
    # Excerpts are stored only for "down" ratings; the route scrubs and truncates them anyway.
    message_excerpt: str | None = Field(default=None, max_length=500)
    answer_excerpt: str | None = Field(default=None, max_length=500)


class FeedbackView(StrictModel):
    id: uuid.UUID
    correlation_id: str
    rating: str
    reason: str | None
    comment: str | None
    created_at: datetime


class FeedbackList(StrictModel):
    count: int
    items: list[FeedbackView]


# --- aggregate metrics ---------------------------------------------------------


class StageLatency(StrictModel):
    p50: float | None
    p95: float | None
    n: int


class MetricsView(StrictModel):
    window_minutes: int
    since: datetime
    turns_total: int
    by_intent: dict[str, int]
    refused_rate: float | None
    human_offer_rate: float | None
    error_rate: float | None
    downvotes_rated: int
    downvotes_down: int
    downvote_rate: float | None
    latency_ms: dict[str, StageLatency]
    end_to_end_ms: StageLatency
    actions: dict[str, int]
    method: str  # percentile method, "nearest-rank"
