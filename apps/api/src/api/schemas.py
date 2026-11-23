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


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=4000)


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
