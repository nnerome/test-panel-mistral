"""Metrics endpoint tests: hand-computed nearest-rank percentiles on a synthetic turn set,
empty window -> nulls, reserved route (404 when demo mode is off), and the response
never carries message or answer content."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from conftest import build_app
from db import accessors as acc
from db.models.pending_action import PendingAction
from env.assistant import env as assistant_env
from mistralai import agents

from api.bank import seed
from api.bank.mock import BankFlags, MockBank
from api.kb.retriever import FakeEmbedder
from api.metrics.service import percentile_nearest_rank
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


def test_nearest_rank_percentiles_by_hand() -> None:
    # n=4 -> p50 rank = ceil(0.5*4)=2 -> 20 ; p95 rank = ceil(0.95*4)=4 -> 40
    assert percentile_nearest_rank([40, 10, 30, 20], 50) == 20
    assert percentile_nearest_rank([40, 10, 30, 20], 95) == 40
    assert percentile_nearest_rank([7], 50) == 7 and percentile_nearest_rank([7], 95) == 7
    assert percentile_nearest_rank([], 50) is None


async def _seed_turns(seeded, session_id) -> None:
    """4 turns whose moderation stage is [10,20,30,40] ms; one refused, one human_offer, one error."""
    async with seeded() as session:
        for i, ms in enumerate([10, 20, 30, 40]):
            await acc.turn_records.record(
                session,
                correlation_id=f"c{i}",
                session_id=session_id,
                intent="faq" if i < 3 else "action",
                auth_level="anonymous",
                refused=(i == 0),
                human_offer=(i == 1),
                error="BankError" if i == 2 else None,
                timings=json.dumps([{"stage": "moderation", "ms": ms}, {"stage": "guardrails+classification (parallel)", "ms": ms}]),
                model=None,
                tokens=None,
            )
        # feedback: 2 rated, 1 down
        await acc.feedback.upsert(session, session_id=session_id, correlation_id="c0", rating="down", reason="wrong", comment=None, message_excerpt=None, answer_excerpt=None)
        await acc.feedback.upsert(session, session_id=session_id, correlation_id="c1", rating="up", reason=None, comment=None, message_excerpt=None, answer_excerpt=None)
        # actions: 3 proposed in-window -> 1 confirmed, 1 cancelled, 1 expired
        for j, status in enumerate(["confirmed", "cancelled", "expired"]):
            session.add(
                PendingAction(
                    session_id=session_id,
                    customer_id=seed.CUSTOMER_BOB,
                    kind="lock_card",
                    card_id=seed.CARD_BOB_CREDIT,
                    status=status,
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
            )
        await session.commit()


async def test_metrics_synthetic_window(http, seeded) -> None:
    client, app = http
    await client.post("/api/auth/login", json={"email": "bob.demo@bank-fictive.fr", "password": "demo1234"})
    me = (await client.get("/api/auth/me")).json()
    await _seed_turns(seeded, me["session_id"])

    res = await client.get("/api/metrics?window_minutes=60")
    assert res.status_code == 200, res.text
    m = res.json()
    assert m["method"] == "nearest-rank"
    assert m["window_minutes"] == 60
    assert m["turns_total"] == 4
    assert m["by_intent"] == {"faq": 3, "action": 1}
    assert m["refused_rate"] == 0.25
    assert m["human_offer_rate"] == 0.25
    assert m["error_rate"] == 0.25
    assert m["downvotes_rated"] == 2 and m["downvotes_down"] == 1 and m["downvote_rate"] == 0.5
    # hand-computed nearest-rank on moderation [10,20,30,40]: p50=20, p95=40
    assert m["latency_ms"]["moderation"] == {"p50": 20, "p95": 40, "n": 4}
    # e2e excludes the parallel group: each turn's e2e == its moderation ms
    assert m["end_to_end_ms"] == {"p50": 20, "p95": 40, "n": 4}
    assert m["latency_ms"]["agent_faq"] == {"p50": None, "p95": None, "n": 0}
    assert m["actions"] == {"proposed": 3, "pending": 0, "confirmed": 1, "cancelled": 1, "expired": 1}
    # aggregates only: no message/answer content anywhere in the payload
    assert "answer" not in res.text and "message" not in res.text


async def test_metrics_empty_window_returns_nulls(http) -> None:
    client, app = http
    res = await client.get("/api/metrics?window_minutes=60")
    assert res.status_code == 200
    m = res.json()
    assert m["turns_total"] == 0
    assert m["refused_rate"] is None and m["human_offer_rate"] is None and m["error_rate"] is None
    assert m["downvote_rate"] is None
    assert m["end_to_end_ms"] == {"p50": None, "p95": None, "n": 0}
    assert all(v == {"p50": None, "p95": None, "n": 0} for v in m["latency_ms"].values())
    assert m["actions"]["proposed"] == 0


async def test_metrics_route_is_reserved(http, monkeypatch) -> None:
    client, app = http
    monkeypatch.setattr(assistant_env, "demo_mode", False)
    assert (await client.get("/api/metrics")).status_code == 404
    # token headers are gone: demo mode is the only gate, with or without any header
    res = await client.get("/api/metrics", headers={"X-Admin-Token": "whatever"})
    assert res.status_code == 404
    monkeypatch.setattr(assistant_env, "demo_mode", True)
    res = await client.get("/api/metrics")
    assert res.status_code == 200
