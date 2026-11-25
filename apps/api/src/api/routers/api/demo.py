"""Demo-only routes: the login dropdown's customer list, the live bank-fault toggles, and a
database reset so a live demo can start from the seeded state again."""

from typing import Annotated

from db import accessors as acc
from db.engine import get_session_maker
from env.assistant import env as assistant_env
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, update

from api.auth.dependencies import ClientHeaderDep
from api.bank.mock import BankFlags
from api.schemas import BankFlagsBody, BankFlagsView, DemoCustomer, DemoResetResponse
from db.models.audit_entry import AuditEntry
from db.models.bank_lock_event import BankLockEvent
from db.models.card import Card
from db.models.card_lock_execution import CardLockExecution
from db.models.feedback import Feedback
from db.models.otp_code import OtpCode
from db.models.pending_action import PendingAction
from db.models.turn_record import TurnRecord

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


@router.post("/reset", operation_id="demo_reset")
async def reset_demo(_h: ClientHeaderDep, _d: None = Depends(_demo_only)) -> DemoResetResponse:
    """Reset the demo state to the seeded one: unlock every card, drop pending actions, lock
    executions, the adapter idempotency ledger, OTP codes and audit entries. Static seed rows
    (customers, accounts, agencies, KB chunks) and live sessions are kept on purpose."""
    async with get_session_maker()() as session:
        cards_unlocked = (
            await session.execute(update(Card).where(Card.status != "active").values(status="active", locked_at=None))
        ).rowcount
        deleted: dict[str, int] = {}
        # Delete children before parents (card_lock_executions -> pending_actions,
        # feedback -> turn_records).
        for name, model in [
            ("card_lock_executions", CardLockExecution),
            ("pending_actions", PendingAction),
            ("bank_lock_events", BankLockEvent),
            ("otp_codes", OtpCode),
            ("feedback", Feedback),
            ("audit_entries", AuditEntry),
            ("turn_records", TurnRecord),
        ]:
            deleted[name] = (await session.execute(delete(model))).rowcount or 0
        await session.commit()
    return DemoResetResponse(ok=True, cards_unlocked=cards_unlocked or 0, deleted=deleted)
