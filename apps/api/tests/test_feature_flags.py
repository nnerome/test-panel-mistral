"""Kill switch (ACTIONS_ENABLED) tests: with actions off, no action agent runs (FAQ/account
unaffected), confirm refuses with actions_disabled leaving card+action untouched while cancel
still works, and re-enabling restores confirm. Plus the demo hot-toggle route."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from conftest import build_app
from db import accessors as acc
from mistralai import agents

from api.actions.service import cancel_action, confirm_action
from api.auth import service
from api.bank import seed
from api.bank.mock import BankFlags, MockBank
from api.domain.errors import ConflictError
from api.kb.retriever import FakeEmbedder
from api.orchestrator import ACTIONS_DISABLED_TEXT, OrchestratorDeps, run_turn
from api.runtime import Runtime

CLIENT_HEADERS = {"X-Bnp-Client": "bnp-assistant-web"}


def _bank(seeded):
    return MockBank(session_maker=seeded, flags_provider=lambda: BankFlags(0, 0))


async def _strong_ctx(seeded, email="bob.demo@bank-fictive.fr"):
    ctx = await service.login(seeded, email, seed.DEMO_PASSWORD)
    _, code, _ = await service.issue_otp(seeded, ctx)
    await service.verify_otp(seeded, ctx, code)
    return await service.resolve_session(seeded, ctx.token)


def _orch(seeded, agent_model, intent, actions_enabled):
    async def moderate(_msg):
        return {"safe": True, "categories": {}}

    async def classify(_msg):
        return intent

    return OrchestratorDeps(
        bank=_bank(seeded),
        embedder=FakeEmbedder(),
        moderation_fn=moderate,
        classify_fn=classify,
        agent_model=agent_model,
        actions_enabled_fn=lambda: actions_enabled,
    )


async def _make_pending(seeded, ctx):
    async with seeded() as session:
        action = await acc.pending_actions.create(
            session,
            session_id=ctx.session_id,
            customer_id=ctx.customer_id,
            kind="lock_card",
            card_id=seed.CARD_BOB_CREDIT,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        await session.commit()
        return action.id


async def test_action_intent_with_kill_switch_off_runs_no_agent(seeded) -> None:
    ctx = await _strong_ctx(seeded)
    model = agents.testing.ScriptedModel([agents.testing.reply("ne doit pas tourner")])
    result = await run_turn("Bloque ma carte", ctx, orch=_orch(seeded, model, "action", actions_enabled=False))
    assert result.answer == ACTIONS_DISABLED_TEXT
    assert result.human_offer is True
    assert result.handoff_reason == "actions_disabled"
    assert not any(t.stage.startswith("agent_") for t in result.timings), "no agent stage while disabled"


async def test_faq_still_works_with_kill_switch_off(seeded) -> None:
    model = agents.testing.ScriptedModel([agents.testing.reply("Réponse FAQ normale.")])
    result = await run_turn("Quels sont les frais de tenue de compte ?", None, orch=_orch(seeded, model, "faq", actions_enabled=False))
    assert result.answer == "Réponse FAQ normale."
    assert any(t.stage == "agent_faq" for t in result.timings)
    assert result.human_offer is False


async def test_confirm_refused_when_disabled_card_and_action_untouched(seeded) -> None:
    ctx = await _strong_ctx(seeded)
    action_id = await _make_pending(seeded, ctx)

    with pytest.raises(ConflictError) as exc:
        await confirm_action(seeded, ctx=ctx, action_id=action_id, bank=_bank(seeded), actions_enabled_fn=lambda: False)
    assert exc.value.code == "actions_disabled"

    async with seeded() as session:
        action = await acc.pending_actions.get(session, action_id)
        card = await acc.cards.get_view(session, seed.CARD_BOB_CREDIT)
    assert action.status == "pending", "status untouched by the refusal"
    assert card.status == "active", "card not locked"

    # cancel stays possible while disabled
    outcome = await cancel_action(seeded, ctx=ctx, action_id=action_id)
    assert outcome["action"]["status"] == "cancelled"

    # re-enable -> confirm works again (fresh pending action)
    action_id2 = await _make_pending(seeded, ctx)
    outcome = await confirm_action(seeded, ctx=ctx, action_id=action_id2, bank=_bank(seeded), actions_enabled_fn=lambda: True)
    assert outcome["executed"] is True
    async with seeded() as session:
        card = await acc.cards.get_view(session, seed.CARD_BOB_CREDIT)
    assert card.status == "locked"


# --- HTTP hot toggle -----------------------------------------------------------


@pytest.fixture()
async def http(seeded):
    app = build_app()
    app.state.bank_flags = BankFlags(0, 0)
    app.state.bnp_runtime = Runtime(
        client=None,
        bank=MockBank(session_maker=seeded, flags_provider=lambda: BankFlags(0, 0)),
        embedder=FakeEmbedder(),
        kb_root=Path(__file__).resolve().parents[3] / "knowledge",
        ready_lock=asyncio.Lock(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, app


def _scripted(app, intent, steps):
    async def moderate(_msg):
        return {"safe": True, "categories": {}}

    async def classify(_msg):
        return intent

    app.state.bnp_orch_overrides = {
        "moderation_fn": moderate,
        "classify_fn": classify,
        "agent_model": agents.testing.ScriptedModel(steps),
    }


async def _read_sse(response) -> dict:
    events: dict[str, list] = {}
    current_event = None
    async for line in response.aiter_lines():
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            events.setdefault(current_event or "data", []).append(json.loads(line[len("data:"):].strip()))
    return events


async def _chat(client, app, message) -> dict:
    async with client.stream("POST", "/api/chat", json={"message": message}) as response:
        events = await _read_sse(response)
    return events["turn"][0]["turn"]


async def test_demo_feature_flags_toggle_and_chat_effect(http, seeded) -> None:
    client, app = http
    # initial state from env default
    res = await client.get("/api/demo/feature-flags")
    assert res.status_code == 200 and res.json()["actions_enabled"] is True

    # toggle off (client header required)
    res = await client.post("/api/demo/feature-flags", json={"actions_enabled": False})
    assert res.status_code == 403  # missing X-Bnp-Client
    res = await client.post("/api/demo/feature-flags", json={"actions_enabled": False}, headers=CLIENT_HEADERS)
    assert res.status_code == 200 and res.json()["actions_enabled"] is False
    assert (await client.get("/api/demo/feature-flags")).json()["actions_enabled"] is False

    # strong session, then an action turn while disabled -> no agent, clear message
    await client.post("/api/auth/login", json={"email": "bob.demo@bank-fictive.fr", "password": "demo1234"})
    otp = (await client.post("/api/auth/step-up")).json()
    await client.post("/api/auth/step-up/verify", json={"code": otp["demo_code"]}, headers=CLIENT_HEADERS)
    _scripted(app, "action", [agents.testing.reply("ne doit pas tourner")])
    turn = await _chat(client, app, "Bloque ma carte")
    assert turn["answer"] == ACTIONS_DISABLED_TEXT
    assert turn["human_offer"] is True
    assert not any(t["stage"].startswith("agent_") for t in turn["timings"])

    # toggle back on -> the action agent runs and proposes
    await client.post("/api/demo/feature-flags", json={"actions_enabled": True}, headers=CLIENT_HEADERS)
    _scripted(app, "action", [agents.testing.call("propose_lock_card", card_label="9012"), agents.testing.reply("Proposition enregistrée.")])
    turn = await _chat(client, app, "Bloque ma carte de crédit")
    assert turn["pending_action"] is not None
    assert any(t["stage"] == "agent_action" for t in turn["timings"])
