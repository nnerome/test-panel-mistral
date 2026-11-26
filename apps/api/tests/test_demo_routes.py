"""Demo routes (/api/demo/* incl. the DB reset) are open to EVERY visitor in demo mode —
the prototype is openly labelled and uses fake data only, so no admin token exists anymore.
Outside demo mode they answer a uniform 404, as if the routes did not exist. The fictional
customer list and the demo OTP code stay accessible in demo mode exactly as before."""

import asyncio
from pathlib import Path

import httpx
import pytest
from conftest import build_app
from db import accessors as acc  # noqa: F401  (kept for parity with the other HTTP test modules)
from api.bank.mock import BankFlags, MockBank
from api.kb.retriever import FakeEmbedder
from api.runtime import Runtime
from env.assistant import env as assistant_env

CLIENT_HEADERS = {"X-Bnp-Client": "bnp-assistant-web"}


@pytest.fixture()
async def http(seeded):
    """In-loop ASGI client + app, runtime on a fake embedder (no Mistral key needed)."""
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


DEMO_ROUTES = [
    ("GET", "/api/demo/bank-flags", None),
    ("POST", "/api/demo/bank-flags", {"latency_ms": 0, "failure_rate": 0}),
    ("GET", "/api/demo/feature-flags", None),
    ("POST", "/api/demo/feature-flags", {"actions_enabled": True}),
    ("POST", "/api/demo/reset", {}),
    ("GET", "/api/demo/customers", None),
]


async def test_demo_routes_open_to_all_visitors_in_demo_mode(http, monkeypatch) -> None:
    """No token of any kind: in demo mode the reset and the flag routes answer 200 to anyone
    sending our own client header (the CSRF defence) — and the GETs need not even that."""
    monkeypatch.setattr(assistant_env, "demo_mode", True)
    client, _app = http
    for method, path, body in DEMO_ROUTES:
        headers = CLIENT_HEADERS if method == "POST" else {}
        res = await client.request(method, path, json=body, headers=headers)
        assert res.status_code == 200, f"{method} {path} -> {res.status_code}, attendu 200 en mode démo"
    # stray token headers change nothing
    res = await client.post("/api/demo/reset", json={}, headers={**CLIENT_HEADERS, "X-Admin-Token": "whatever"})
    assert res.status_code == 200 and res.json()["ok"] is True


async def test_demo_reset_actually_resets(http, seeded, monkeypatch) -> None:
    monkeypatch.setattr(assistant_env, "demo_mode", True)
    client, _app = http
    reset = await client.post("/api/demo/reset", json={}, headers=CLIENT_HEADERS)
    assert reset.status_code == 200
    body = reset.json()
    assert body["ok"] is True and "pending_actions" in body["deleted"]
    # idempotent: a second reset is fine too
    again = await client.post("/api/demo/reset", json={}, headers=CLIENT_HEADERS)
    assert again.status_code == 200 and again.json()["ok"] is True


async def test_demo_routes_404_outside_demo_mode(http, monkeypatch) -> None:
    """Uniform 404 as if the routes did not exist, whatever the headers."""
    monkeypatch.setattr(assistant_env, "demo_mode", False)
    client, _app = http
    for method, path, body in DEMO_ROUTES:
        headers = {**CLIENT_HEADERS, "X-Admin-Token": "whatever"} if method == "POST" else {"X-Admin-Token": "whatever"}
        res = await client.request(method, path, json=body, headers=headers)
        assert res.status_code == 404, f"{method} {path} -> {res.status_code}, attendu 404 hors mode démo"


async def test_customers_and_otp_still_open_in_demo_mode(http, seeded, monkeypatch) -> None:
    monkeypatch.setattr(assistant_env, "demo_mode", True)
    client, _app = http
    res = await client.get("/api/demo/customers")
    assert res.status_code == 200 and len(res.json()) == 3
    await client.post("/api/auth/login", json={"email": "alice.demo@bank-fictive.fr", "password": "demo1234"})
    otp = (await client.post("/api/auth/step-up", headers=CLIENT_HEADERS)).json()
    assert otp.get("demo_code")  # demo OTP still displayed, as before
