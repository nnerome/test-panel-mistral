"""Demo-only routes: the login dropdown's customer list and the live bank-fault toggles."""

from typing import Annotated

from db import accessors as acc
from db.engine import get_session_maker
from env.assistant import env as assistant_env
from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth.dependencies import ClientHeaderDep
from api.bank.mock import BankFlags
from api.schemas import BankFlagsBody, BankFlagsView, DemoCustomer

router = APIRouter(tags=["demo"])

DEMO_PASSWORD_HINT = "demo1234"


def _demo_only() -> None:
    """Demo routes exist only in demo mode; any real deployment turns them off (404)."""
    if not assistant_env.demo_mode:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "demo mode disabled"})


def flags_holder(request: Request) -> BankFlags:
    """Runtime flags live on app.state so the UI toggles them without a restart."""
    flags = getattr(request.app.state, "bank_flags", None)
    if flags is None:
        flags = BankFlags.from_env()
        request.app.state.bank_flags = flags
    return flags


@router.get("/customers", operation_id="demo_customers")
async def customers(_: None = Depends(_demo_only)) -> list[DemoCustomer]:
    """The 3 fictional demo customers for the login dropdown (fake data, demo password shown)."""
    async with get_session_maker()() as session:
        rows = await acc.customers.list_all(session)
        return [DemoCustomer(email=c.email, display_name=c.display_name, password=DEMO_PASSWORD_HINT) for c in rows]


@router.get("/bank-flags", operation_id="demo_bank_flags_get")
async def get_bank_flags(request: Request, _: None = Depends(_demo_only)) -> BankFlagsView:
    """Current mock-bank fault-injection flags (latency and failure rate)."""
    flags = flags_holder(request)
    return BankFlagsView(
        latency_ms=flags.latency_ms,
        failure_rate=flags.failure_rate,
        defaults=BankFlagsBody(latency_ms=assistant_env.bank_latency_ms, failure_rate=assistant_env.bank_failure_rate),
    )


@router.post("/bank-flags", operation_id="demo_bank_flags_set")
async def set_bank_flags(body: BankFlagsBody, request: Request, _h: ClientHeaderDep, _d: None = Depends(_demo_only)) -> BankFlagsView:
    """Set the mock-bank fault-injection flags live (slow mode / failure mode for the demo)."""
    flags = flags_holder(request)
    flags.latency_ms = body.latency_ms
    flags.failure_rate = body.failure_rate
    return BankFlagsView(
        latency_ms=flags.latency_ms,
        failure_rate=flags.failure_rate,
        defaults=BankFlagsBody(latency_ms=assistant_env.bank_latency_ms, failure_rate=assistant_env.bank_failure_rate),
    )
