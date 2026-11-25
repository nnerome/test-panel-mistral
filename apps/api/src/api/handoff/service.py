"""Handoff creation rules.

A handoff request is created automatically when a turn returns human_offer=true — at most ONE
open request per (session, reason), so a user insisting does not duplicate the queue entry.
The summary is a deterministic template (no model call) containing only the reason, intent,
auth level and masked identifiers (e.g. a pending card lock as "**** 9012, non confirmée") —
never a full PAN, never balances or raw account data. Everything is scrubbed as a last line."""

import uuid

from db import accessors as acc

from api.domain.masking import scrub_secrets
from api.orchestrator import TurnResult

REASONS = ("human_request", "out_of_scope", "guardrail_refusal", "bank_error", "actions_disabled", "step_up_needed")


def reason_for(result: TurnResult) -> str:
    if result.handoff_reason in REASONS:
        return result.handoff_reason
    if result.refused:
        return "guardrail_refusal"
    if result.error:
        return "bank_error"
    if result.needs_step_up:
        return "step_up_needed"
    if result.intent == "human_request":
        return "human_request"
    if result.intent == "out_of_scope":
        return "out_of_scope"
    return "human_request"


def build_summary(result: TurnResult, *, reason: str) -> str:
    parts = [f"Motif : {reason}.", f"Intention : {result.intent}.", f"Authentification : {result.auth_level}."]
    pa = result.pending_action
    if pa:
        masked = pa.get("card_masked_number") or "****"
        kind = pa.get("kind") or "action"
        status = pa.get("status") or "pending"
        note = "non confirmée" if status == "pending" else f"statut : {status}"
        parts.append(f"Étape : action proposée ({kind} sur carte {masked}, {note}).")
    else:
        parts.append("Aucune action proposée.")
    return scrub_secrets(" ".join(parts))


async def maybe_create_handoff(session_maker, result: TurnResult, ctx) -> str | None:
    """Create (or return the existing) open handoff for this turn's session+reason.
    Returns the handoff id, or None when the turn does not offer a human."""
    if not result.human_offer or ctx is None:
        return None
    reason = reason_for(result)
    async with session_maker() as session:
        existing = await acc.handoffs.find_open(session, ctx.session_id, reason)
        if existing is not None:
            return str(existing.id)
        pending_id = None
        action_id = (result.pending_action or {}).get("action_id")
        if action_id:
            try:
                pending_id = uuid.UUID(str(action_id))
            except (ValueError, TypeError):
                pending_id = None
        row = await acc.handoffs.create(
            session,
            correlation_id=result.correlation_id,
            session_id=ctx.session_id,
            customer_id=ctx.customer_id,
            reason=reason,
            intent=result.intent,
            auth_level=result.auth_level,
            summary=build_summary(result, reason=reason),
            pending_action_id=pending_id,
        )
        await session.commit()
        return str(row.id)
