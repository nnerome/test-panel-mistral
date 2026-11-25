"""Feedback loop tests: turn_records written per chat turn, POST /api/feedback ownership check
(uniform 404), upsert without duplicate, secret scrubbing, enum 422, reserved list route."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from conftest import build_app
from db import accessors as acc
from env.assistant import env as assistant_env
from mistralai import agents

from api.bank import seed
from api.bank.mock import BankFlags, MockBank
from api.kb.retriever import FakeEmbedder
from api.runtime import Runtime

CLIENT_HEADERS = {"X-Bnp-Client": "bnp-assistant-web"}


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


async def _chat_turn(client, app, message="Bonjour") -> dict:
    _scripted(app, "faq", [agents.testing.call("search_knowledge_base", query=message[:80]), agents.testing.reply("Réponse de test.")])
    async with client.stream("POST", "/api/chat", json={"message": message}) as response:
        assert response.status_code == 200
        events = await _read_sse(response)
    return events["turn"][0]["turn"]


async def test_chat_writes_turn_record(http, seeded) -> None:
    client, app = http
    turn = await _chat_turn(client, app)
    async with seeded() as session:
        row = await acc.turn_records.get(session, turn["correlation_id"])
    assert row is not None
    assert row.intent == "faq"
    assert row.refused is False and row.human_offer is False and row.error is None
    timings = json.loads(row.timings)
    assert {t["stage"] for t in timings} >= {"moderation", "classification", "agent_faq", "output_check"}
    assert row.model == "mistral-small-latest"  # the agent's configured model is recorded
    assert row.tokens is None  # ScriptedModel returns no usage -> null, as designed


async def test_feedback_ok_for_own_session_turn(http, seeded) -> None:
    client, app = http
    await client.post("/api/auth/login", json={"email": "alice.demo@bank-fictive.fr", "password": "demo1234"})
    turn = await _chat_turn(client, app)
    res = await client.post(
        "/api/feedback",
        json={
            "correlation_id": turn["correlation_id"],
            "rating": "down",
            "reason": "wrong",
            "comment": "ma carte 4111111111111111 a été débitée deux fois",
            "message_excerpt": "Pourquoi ce débit ?",
            "answer_excerpt": turn["answer"][:500],
        },
        headers=CLIENT_HEADERS,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["rating"] == "down" and body["reason"] == "wrong"
    async with seeded() as session:
        rows = await acc.feedback.list_recent(session, rating="down", limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert "4111111111111111" not in (row.comment or "")  # PAN-like run scrubbed
    assert "****" in row.comment
    assert row.message_excerpt == "Pourquoi ce débit ?"
    assert row.answer_excerpt is not None


async def test_feedback_up_drops_excerpts(http, seeded) -> None:
    client, app = http
    await client.post("/api/auth/login", json={"email": "bob.demo@bank-fictive.fr", "password": "demo1234"})
    turn = await _chat_turn(client, app)
    res = await client.post(
        "/api/feedback",
        json={"correlation_id": turn["correlation_id"], "rating": "up", "message_excerpt": "x", "answer_excerpt": "y"},
        headers=CLIENT_HEADERS,
    )
    assert res.status_code == 200
    async with seeded() as session:
        rows = await acc.feedback.list_recent(session, limit=10)
    assert len(rows) == 1 and rows[0].rating == "up"
    assert rows[0].message_excerpt is None and rows[0].answer_excerpt is None  # excerpts only on "down"


async def test_feedback_of_another_session_is_404(http) -> None:
    client, app = http
    await client.post("/api/auth/login", json={"email": "alice.demo@bank-fictive.fr", "password": "demo1234"})
    turn = await _chat_turn(client, app)
    # second client = bob's session
    other = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    await other.post("/api/auth/login", json={"email": "bob.demo@bank-fictive.fr", "password": "demo1234"})
    res = await other.post(
        "/api/feedback",
        json={"correlation_id": turn["correlation_id"], "rating": "down"},
        headers=CLIENT_HEADERS,
    )
    assert res.status_code == 404
    await other.aclose()


async def test_feedback_upsert_never_duplicates(http, seeded) -> None:
    client, app = http
    await client.post("/api/auth/login", json={"email": "alice.demo@bank-fictive.fr", "password": "demo1234"})
    turn = await _chat_turn(client, app)
    for rating in ("up", "down"):
        res = await client.post("/api/feedback", json={"correlation_id": turn["correlation_id"], "rating": rating}, headers=CLIENT_HEADERS)
        assert res.status_code == 200
    async with seeded() as session:
        rows = await acc.feedback.list_recent(session, limit=10)
    assert len(rows) == 1, "one row per (session, turn): the second send updates it"
    assert rows[0].rating == "down"


async def test_feedback_invalid_enum_is_422(http) -> None:
    client, app = http
    await client.post("/api/auth/login", json={"email": "alice.demo@bank-fictive.fr", "password": "demo1234"})
    turn = await _chat_turn(client, app)
    res = await client.post("/api/feedback", json={"correlation_id": turn["correlation_id"], "rating": "meh"}, headers=CLIENT_HEADERS)
    assert res.status_code == 422
    res = await client.post(
        "/api/feedback", json={"correlation_id": turn["correlation_id"], "rating": "down", "reason": "bad"}, headers=CLIENT_HEADERS
    )
    assert res.status_code == 422


async def test_feedback_recent_is_reserved(http, seeded, monkeypatch) -> None:
    client, app = http
    await client.post("/api/auth/login", json={"email": "alice.demo@bank-fictive.fr", "password": "demo1234"})
    turn = await _chat_turn(client, app)
    await client.post("/api/feedback", json={"correlation_id": turn["correlation_id"], "rating": "down", "reason": "other"}, headers=CLIENT_HEADERS)

    # demo off, no admin token -> uniform 404
    monkeypatch.setattr(assistant_env, "demo_mode", False)
    monkeypatch.setattr(assistant_env, "admin_token", None)
    res = await client.get("/api/feedback/recent")
    assert res.status_code == 404

    # admin token path -> 200
    monkeypatch.setattr(assistant_env, "admin_token", "s3cret-admin")
    res = await client.get("/api/feedback/recent")
    assert res.status_code == 404  # missing header
    res = await client.get("/api/feedback/recent", headers={"X-Admin-Token": "s3cret-admin"})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 1 and body["items"][0]["rating"] == "down"
    # rating filter
    res = await client.get("/api/feedback/recent?rating=up", headers={"X-Admin-Token": "s3cret-admin"})
    assert res.json()["count"] == 0
