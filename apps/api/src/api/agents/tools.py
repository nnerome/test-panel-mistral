"""The agent tools. Every rule of the demo lives in this file:

- Tool schemas contain NO identity parameter: the customer id arrives only via the
  `BankSessionInput` session input (`agents.Depends()`), which the SDK keeps out of the schema.
- Ownership is verified inside each tool (defence in depth), even though the id is
  server-injected: the same helper the confirm endpoint uses.
- Cards are addressed by MASKED LABEL only ("card ending 1234"); the server resolves the label
  to a real card id within the session's own cards and rejects anything unresolved.
- `propose_lock_card` never executes anything: it creates a pending action row and returns it
  masked. Execution happens only in the confirm endpoint.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from db import accessors as acc
from env.assistant import env as assistant_env
from mistralai import agents
from pydantic import Field
from sqlmodel import select

from api.agents.deps import collector, run_deps
from api.agents.inputs import BankSessionInput
from api.bank.ownership import assert_account_owned, assert_card_owned
from api.domain.errors import OwnershipError


def _session_uuid(session: BankSessionInput) -> uuid.UUID:
    return uuid.UUID(session.session_id)


def _customer_uuid(session: BankSessionInput) -> uuid.UUID:
    if session.customer_id is None:
        raise agents.ToolError("anonymous session: no customer data is available")
    return uuid.UUID(session.customer_id)


@agents.tool(model_access="direct")
async def search_knowledge_base(
    query: Annotated[str, Field(description="The customer's question, rephrased as a search query.")],
) -> list[dict]:
    """Search the bank's public FAQ knowledge base. Returns the most relevant passages with
    their source file; relevance is judged by the agent, not by this tool."""
    from api.kb.retriever import retrieve

    deps = run_deps()
    passages = await retrieve(query, embedder=deps.embedder, session_maker=deps.session_maker)
    results = [p.model_dump() for p in passages]
    collector().sources.extend(results)
    return results


@agents.tool(model_access="direct")
async def list_cards(
    session: Annotated[BankSessionInput, agents.Depends()],
) -> list[dict]:
    """List the session customer's cards. Returns masked card numbers only (e.g. '**** **** **** 1234')."""
    deps = run_deps()
    customer_id = _customer_uuid(session)
    cards = await deps.bank.list_cards(customer_id)
    async with deps.session_maker() as db:
        for card in cards:
            # Defence in depth: the list came from a customer-scoped query, and we still check
            # each card's owner before returning it.
            await assert_card_owned(db, customer_id=customer_id, card_id=card.card_id)
    return [c.model_dump(mode="json") for c in cards]


@agents.tool(model_access="direct")
async def get_my_agency_hours(
    session: Annotated[BankSessionInput, agents.Depends()],
) -> dict:
    """Opening hours of the session customer's OWN agency. The agency id is resolved server-side
    from the customer's own row — the schema carries no id parameter, and no other customer's
    agency can ever be reached through it."""
    deps = run_deps()
    customer_id = _customer_uuid(session)
    async with deps.session_maker() as db:
        customer = await acc.customers.get(db, customer_id)
        if customer is None or customer.agency_id is None:
            raise agents.ToolError("no agency is linked to your profile in this demo")
        hours = await deps.bank.get_agency_hours(customer.agency_id)
    return hours.model_dump(mode="json")


@agents.tool(model_access="direct")
async def get_balance(
    session: Annotated[BankSessionInput, agents.Depends()],
    account_label: Annotated[
        str | None,
        Field(description="Optional account label or masked IBAN suffix (e.g. '7001') to pick one account; omit for all accounts."),
    ] = None,
) -> list[dict]:
    """Read-only balances of the session customer's accounts. Never any other customer's data."""
    deps = run_deps()
    customer_id = _customer_uuid(session)
    accounts = await deps.bank.get_accounts(customer_id)
    if account_label is not None:
        needle = account_label.strip().lower().replace(" ", "")
        accounts = [a for a in accounts if needle in a.masked_iban.lower().replace(" ", "") or needle in a.label.lower()]
        if not accounts:
            raise agents.ToolError(f"no account of yours matches {account_label!r}")
    out = []
    async with deps.session_maker() as db:
        for account in accounts:
            await assert_account_owned(db, customer_id=customer_id, account_id=account.account_id)
            money = await deps.bank.get_balance(account.account_id)
            out.append(
                {
                    "label": account.label,
                    "masked_iban": account.masked_iban,
                    "balance": money.amount_cents / 100.0,
                    "currency": money.currency,
                }
            )
    return out


def resolve_card_label(cards: list, card_label: str) -> object:
    """Resolve a masked label like 'ending 1234' or '5678' to exactly one of the session's
    cards. The model never holds a usable internal identifier: anything unresolved or ambiguous
    is rejected here, server-side."""
    needle = "".join(ch for ch in card_label if ch.isdigit())
    matches = [c for c in cards if (needle and c.masked_number.endswith(needle)) or card_label.strip().lower() in c.label.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise agents.ToolError(
            "no card of yours matches that label; here are your cards: "
            + ", ".join(f"{c.label} ({c.masked_number})" for c in cards)
        )
    raise agents.ToolError(
        "several cards match; ask the customer which one: " + ", ".join(f"{c.label} ({c.masked_number})" for c in matches)
    )


@agents.tool(model_access="direct")
async def propose_lock_card(
    session: Annotated[BankSessionInput, agents.Depends()],
    card_label: Annotated[str, Field(description="The card to lock, by its MASKED label only, e.g. 'card ending 1234'.")],
) -> dict:
    """Propose locking one of the session customer's cards. NEVER executes anything: creates a
    pending action (UUID, bound to this session, 5-minute expiry) that the customer must confirm
    through the dedicated endpoint after strong authentication."""
    deps = run_deps()
    if session.auth_level != "strong":
        raise agents.ToolError("strong authentication is required before proposing a card lock; ask the customer to step up")
    customer_id = _customer_uuid(session)
    cards = await deps.bank.list_cards(customer_id)
    async with deps.session_maker() as db:
        for card in cards:
            await assert_card_owned(db, customer_id=customer_id, card_id=card.card_id)
    card = resolve_card_label(cards, card_label)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=assistant_env.pending_action_ttl_seconds)
    async with deps.session_maker() as db:
        await assert_card_owned(db, customer_id=customer_id, card_id=card.card_id)
        action = await acc.pending_actions.create(
            db,
            session_id=_session_uuid(session),
            customer_id=customer_id,
            kind="lock_card",
            card_id=card.card_id,
            expires_at=expires_at,
        )
        await db.commit()
    from api.audit.service import log_action

    await log_action(
        deps.session_maker,
        customer_id=customer_id,
        session_id=_session_uuid(session),
        auth_level=session.auth_level,
        action="propose_lock_card",
        masked_args={"card": card.masked_number, "label": card.label},
        result="pending",
        correlation_id=session.correlation_id,
    )
    pending = {
        "action_id": str(action.id),
        "kind": action.kind,
        "card_masked_number": card.masked_number,
        "card_label": card.label,
        "effect": "Blocage temporaire et réversible de la carte : paiements et retraits refusés.",
        "status": "pending",
        "expires_at": action.expires_at.isoformat(),
    }
    collector().pending_action = pending
    # Masked only: the internal card id never reaches the model.
    return pending


__all__ = ["search_knowledge_base", "list_cards", "get_balance", "get_my_agency_hours", "propose_lock_card", "resolve_card_label"]

# Keep imports used by OwnershipError path explicit for readers.
_ = OwnershipError
