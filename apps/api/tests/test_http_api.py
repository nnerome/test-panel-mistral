"""End-to-end HTTP tests (in-loop ASGI client): SSE chat streaming, login -> step-up -> confirm
with the CSRF custom header, and the login prompt for unauthenticated account questions."""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from conftest import build_app
from db import accessors as acc
from mistralai import agents

from api.bank import seed
from api.bank.mock import BankFlags, MockBank
from api.kb.retriever import FakeEmbedder
from api.runtime import Runtime

CLIENT_HEADERS = {"X-Bnp-Client": "bnp-assistant-web"}


@pytest.fixture()
async def http(seeded):
    """An in-loop ASGI client plus the app, with the runtime pre-built on a fake embedder so
    no Mistral API key is needed (agent/moderation/classifier are overridden per test)."""
    app = build_app()
    app.state.bank_flags = BankFlags(0, 0)
    app.state.bnp_runtime = Runtime(
        client=None,
        bank=MockBank(session_maker=seeded, flags_provider=lambda: BankFlags(0, 0)),
        embedder=FakeEmbedder(),
        kb_root=__import__("pathlib").Path(__file__).resolve().parents[3] / "knowledge",
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


async def _read_sse(response) -> dict[str, list]:
    events: dict[str, list] = {}
    current_event = None
    async for line in response.aiter_lines():
        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            payload = json.loads(line[len("data:") :].strip())
            events.setdefault(current_event or "data", []).append(payload)
    return events


async def test_chat_faq_streams_sse_with_sources_and_turn(http) -> None:
    client, app = http
    _scripted(
        app,
        "faq",
        [
            agents.testing.call("search_knowledge_base", query="plafond virement"),
            agents.testing.reply("Le plafond est de 5 000 € par jour (source : knowledge/fr/plafonds-virements.md)."),
        ],
    )
    async with client.stream("POST", "/api/chat", json={"message": "Quel est le plafond d'un virement ?"}) as response:
        assert response.status_code == 200
        events = await _read_sse(response)
    assert events["delta"], "text must stream as delta events"
    assert any("5 000" in d["text"] for d in events["delta"])
    assert events["sources"], "FAQ answers must carry their sources"
    turn = events["turn"][0]["turn"]
    assert turn["intent"] == "faq"
    assert "plafonds-virements.md" in turn["answer"]
    stages = {t["stage"]: t["ms"] for t in turn["timings"]}
    assert {"moderation", "classification", "agent_faq", "output_check"} <= set(stages)
    assert turn["correlation_id"]
    assert "done" in events


async def test_chat_anonymous_account_question_yields_login_prompt(http) -> None:
    client, app = http
    _scripted(app, "account_info", [agents.testing.reply("ne doit pas tourner")])
    async with client.stream("POST", "/api/chat", json={"message": "Quel est mon solde ?"}) as response:
        events = await _read_sse(response)
    turn = events["turn"][0]["turn"]
    assert turn["needs_login"] is True
    assert "connecter" in turn["answer"]
    assert not any(t["stage"].startswith("agent_") for t in turn["timings"])


async def test_login_stepup_confirm_flow_over_http(http, seeded) -> None:
    client, app = http

    # login as Alice (fictional demo customer)
    res = await client.post("/api/auth/login", json={"email": "alice.demo@bank-fictive.fr", "password": "demo1234"})
    assert res.status_code == 200
    me = (await client.get("/api/auth/me")).json()
    assert me["level"] == "authenticated" and me["customer_id"] == str(seed.CUSTOMER_ALICE)

    # step-up: receive the fake code, verify it -> strong
    res = await client.post("/api/auth/step-up")
    assert res.status_code == 200
    code = res.json()["demo_code"]
    assert code and len(code) == 6
    res = await client.post("/api/auth/step-up/verify", json={"code": "000000" if code == "111111" else "000000"})
    assert res.status_code == 401  # wrong code refused
    res = await client.post("/api/auth/step-up/verify", json={"code": code})
    assert res.status_code == 200
    me = (await client.get("/api/auth/me")).json()
    assert me["level"] == "strong"

    # a pending action bound to this session (as the action agent would create)
    session_id = uuid.UUID(me["session_id"])
    async with seeded() as session:
        action = await acc.pending_actions.create(
            session,
            session_id=session_id,
            customer_id=seed.CUSTOMER_ALICE,
            kind="lock_card",
            card_id=seed.CARD_ALICE,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        await session.commit()
        action_id = action.id

    # CSRF defence: confirm without our custom header -> 403
    res = await client.post(f"/api/actions/{action_id}/confirm")
    assert res.status_code == 403

    # with the header -> executes
    res = await client.post(f"/api/actions/{action_id}/confirm", headers=CLIENT_HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert body["executed"] is True and body["result"]["status"] == "locked"
    assert body["action"]["card_masked_number"] == "**** **** **** 0001"

    # replay -> stored result, not executed twice
    res = await client.post(f"/api/actions/{action_id}/confirm", headers=CLIENT_HEADERS)
    assert res.status_code == 200 and res.json()["executed"] is False

    # status endpoint reflects it
    res = await client.get(f"/api/actions/{action_id}")
    assert res.status_code == 200 and res.json()["status"] == "confirmed"

    # card is locked in the DB, and the audit trail holds exactly one lock_card entry, masked
    async with seeded() as session:
        card = await acc.cards.get_view(session, seed.CARD_ALICE)
        assert card is not None and card.status == "locked"
        audits = [a for a in await acc.audit.list_all(session) if a.action == "lock_card"]
        assert len(audits) == 1
        assert seed.PAN_ALICE not in audits[0].masked_args


async def test_confirm_of_another_sessions_action_is_404(http, seeded) -> None:
    client, app = http
    await client.post("/api/auth/login", json={"email": "bob.demo@bank-fictive.fr", "password": "demo1234"})
    _, code, _ = None, None, None
    res = await client.post("/api/auth/step-up")
    code = res.json()["demo_code"]
    await client.post("/api/auth/step-up/verify", json={"code": code})
    me = (await client.get("/api/auth/me")).json()

    # pending action owned by ALICE's session, confirmed from BOB's session -> 404
    async with seeded() as session:
        alice = await acc.customers.get_by_email(session, "alice.demo@bank-fictive.fr")
        from api.auth import service as auth_service

        alice_ctx = await auth_service.create_session(seeded, customer_id=alice.id, level="strong")
        action = await acc.pending_actions.create(
            session,
            session_id=alice_ctx.session_id,
            customer_id=alice.id,
            kind="lock_card",
            card_id=seed.CARD_ALICE,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        await session.commit()
        action_id = action.id
    res = await client.post(f"/api/actions/{action_id}/confirm", headers=CLIENT_HEADERS)
    assert res.status_code == 404


async def test_demo_endpoints_404_when_demo_mode_off(http, seeded, monkeypatch) -> None:
    from env.assistant import env as assistant_env

    client, app = http
    monkeypatch.setattr(assistant_env, "demo_mode", False)
    res = await client.get("/api/demo/customers")
    assert res.status_code == 404
    res = await client.post("/api/demo/bank-flags", json={"latency_ms": 0, "failure_rate": 0}, headers=CLIENT_HEADERS)
    assert res.status_code == 404


async def test_session_token_header_works_without_cookie(http, seeded) -> None:
    """Deployed behind the Studio gateway, the module's Set-Cookie may not reach the browser;
    the SPA then sends the login token back in X-Bnp-Session. Header alone must authenticate."""
    client, app = http
    res = await client.post("/api/auth/login", json={"email": "alice.demo@bank-fictive.fr", "password": "demo1234"})
    assert res.status_code == 200
    token = res.json()["token"]

    # a client with an empty cookie jar: only the header carries the session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as anon:
        me = (await anon.get("/api/auth/me", headers={"X-Bnp-Session": token})).json()
        assert me["level"] == "authenticated" and me["customer_id"] == str(seed.CUSTOMER_ALICE)
        me_anon = (await anon.get("/api/auth/me")).json()
        assert me_anon["level"] == "anonymous"
