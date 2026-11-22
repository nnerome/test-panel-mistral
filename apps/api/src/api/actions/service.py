"""Confirm/cancel a pending action. The checks run IN THIS ORDER and every one is server-side:

1. the pending action exists and belongs to THIS session (else 404, no existence leak);
2. the session is at `strong` auth level;
3. the action has not expired (5-minute TTL) and is still pending;
4. the card still belongs to the session's customer (ownership re-check);
5. idempotency: the execution table's primary key is the action id, so a concurrent or replayed
   confirm cannot execute twice — the stored result is returned instead;
6. only then bank.lock_card, with the action id as idempotency key; a timeout/error is retried
   at most once WITH THE SAME KEY (never a blind retry), and one audit entry is written total."""

import json
import logging
import uuid
from datetime import datetime, timezone

from db import accessors as acc
from db.engine import get_session_maker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from api.bank.ownership import assert_card_owned
from api.bank.protocol import Bank, BankError
from api.domain.errors import AuthRequiredError, ConflictError, NotFoundError, StepUpRequiredError

logger = logging.getLogger("bnp.actions")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_pending_action_view(session_maker, session_ctx, action_id: uuid.UUID):
    """The pending action if it belongs to this session, else None (404 at the route)."""
    async with session_maker() as session:
        action = await acc.pending_actions.get(session, action_id)
        if action is None or action.session_id != session_ctx.session_id:
            return None
        card = await acc.cards.get_view(session, action.card_id)
        return action, card


async def confirm_action(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    ctx,
    action_id: uuid.UUID,
    bank: Bank,
) -> dict:
    """Execute a pending action exactly once. Returns {'action': view, 'executed': bool, 'result': dict}."""
    from api.audit.service import log_action

    async with session_maker() as session:
        action = await acc.pending_actions.get(session, action_id)
        # 1) session binding — a pending action of another session is indistinguishable from none
        if action is None or action.session_id != ctx.session_id:
            raise NotFoundError("action not found")
        # 2) strong auth level
        if ctx.level != "strong":
            raise StepUpRequiredError("strong authentication required to confirm")
        # 3) expiry
        now = utcnow()
        if action.expires_at <= now:
            await acc.pending_actions.set_status(session, action, "expired")
            await session.commit()
            raise ConflictError("action expired", code="action_expired")
        # 4) ownership re-check
        await assert_card_owned(session, customer_id=ctx.customer_id, card_id=action.card_id)
        card = await acc.cards.get_view(session, action.card_id)
        await session.commit()

    # 5) idempotency FIRST among the state checks: an already-executed action (replay or the
    # loser of a concurrent double-confirm) returns the stored result, never a 409, never a
    # second execution
    async with session_maker() as session:
        existing = await acc.executions.get_by_action_id(session, action_id)
    if existing is not None:
        async with session_maker() as session:
            action = await acc.pending_actions.get(session, action_id)
            snapshot = (action.id, action.kind, action.status, action.created_at, action.expires_at)
        return _view(snapshot, card, executed=False, result=json.loads(existing.result_json))

    # still pending? anything else (cancelled) is a conflict
    async with session_maker() as session:
        action = await acc.pending_actions.get(session, action_id)
        if action.status != "pending":
            raise ConflictError(f"action already {action.status}")

    idempotency_key = f"lock-card:{action.id}"
    try:
        lock_result = await bank.lock_card(action.card_id, idempotency_key=idempotency_key)
    except BankError as error:
        # 6) never silently retry a state-changing call: at most one retry, SAME idempotency key
        logger.warning("bank.lock_card failed (%s); one retry with the same idempotency key", error)
        await log_action(
            session_maker,
            customer_id=ctx.customer_id,
            session_id=ctx.session_id,
            auth_level=ctx.level,
            action="lock_card_retry",
            masked_args={"action_id": str(action.id)},
            result=type(error).__name__,
            correlation_id=None,
        )
        lock_result = await bank.lock_card(action.card_id, idempotency_key=idempotency_key)

    stored = lock_result.model_dump(mode="json")
    async with session_maker() as session:
        # re-fetch in THIS session: the earlier `action` is detached from the closed one.
        # Snapshot its scalar fields immediately: after a rollback the ORM would lazily reload
        # them, which cannot run in the sync context that builds the response view.
        action = await acc.pending_actions.get(session, action_id)
        snapshot = (action.id, action.kind, action.status, action.created_at, action.expires_at)
        try:
            await acc.executions.create(
                session,
                action_id=action.id,
                idempotency_key=idempotency_key,
                result_json=json.dumps(stored),
            )
            await acc.pending_actions.set_status(session, action, "confirmed")
            await session.commit()
        except IntegrityError:
            # concurrent double-confirm: the UNIQUE(action_id) constraint lost the race —
            # return the stored result, never execute twice
            await session.rollback()
            async with session_maker() as s2:
                existing = await acc.executions.get_by_action_id(s2, action_id)
            if existing is not None:
                return _view(snapshot, card, executed=False, result=json.loads(existing.result_json))
            raise

    # exactly ONE audit entry for the action, whether first confirm or replay
    await log_action(
        session_maker,
        customer_id=ctx.customer_id,
        session_id=ctx.session_id,
        auth_level=ctx.level,
        action="lock_card",
        masked_args={"action_id": str(action.id), "card": stored["masked_number"]},
        result="locked",
        correlation_id=None,
    )
    return _view(snapshot, card, executed=True, result=stored)


async def cancel_action(session_maker, *, ctx, action_id: uuid.UUID) -> dict:
    async with session_maker() as session:
        action = await acc.pending_actions.get(session, action_id)
        if action is None or action.session_id != ctx.session_id:
            raise NotFoundError("action not found")
        if action.status != "pending":
            raise ConflictError(f"action already {action.status}")
        await acc.pending_actions.set_status(session, action, "cancelled")
        card = await acc.cards.get_view(session, action.card_id)
        snapshot = (action.id, action.kind, action.status, action.created_at, action.expires_at)
        await session.commit()
    return _view(snapshot, card, executed=False, result={"status": "cancelled"})


def _view(snapshot, card, *, executed: bool, result: dict) -> dict:
    action_id, kind, status, created_at, expires_at = snapshot
    return {
        "action": {
            "id": str(action_id),
            "kind": kind,
            "card_masked_number": result.get("masked_number") or (f"**** **** **** {card.pan_last4}" if card else "****"),
            "card_label": card.label if card else "",
            "status": status,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
        "executed": executed,
        "result": result,
    }
