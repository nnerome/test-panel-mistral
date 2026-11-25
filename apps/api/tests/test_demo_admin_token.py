"""The state-changing demo routes (POST /api/demo/reset, /api/demo/bank-flags, /api/demo/feature-flags
and their GETs) require a valid X-Admin-Token matching the ADMIN_TOKEN secret: without it, a
uniform 404 as if the route did not exist. The fictional customer list and the demo OTP code
stay accessible in demo mode exactly as before."""

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
ADMIN = {"X-Admin-Token": "s3cret-admin"}


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

PROTECTED = [
    ("GET", "/api/demo/bank-flags", None),
    ("POST", "/api/demo/bank-flags", {"latency_ms": 0, "failure_rate": 0}),
    ("GET", "/api/demo/feature-flags", None),
    ("POST", "/api/demo/feature-flags", {"actions_enabled": True}),
    ("POST", "/api/demo/reset", {}),
]


async def _call_all(client, headers):
    out = []
    for method, path, body in PROTECTED:
        res = await client.request(method, path, json=body, headers=headers)
        out.append((method, path, res.status_code))
    return out


async def _assert_customers_and_otp_open(client) -> None:
    res = await client.get("/api/demo/customers")
    assert res.status_code == 200 and len(res.json()) == 3
    await client.post("/api/auth/login", json={"email": "alice.demo@bank-fictive.fr", "password": "demo1234"})
    otp = (await client.post("/api/auth/step-up", headers=CLIENT_HEADERS)).json()
    assert otp.get("demo_code")  # demo OTP still displayed, as before


async def test_protected_routes_404_without_token(http, seeded, monkeypatch) -> None:
    monkeypatch.setattr(assistant_env, "admin_token", "s3cret-admin")
    client, _app = http
    for method, path, status in await _call_all(client, CLIENT_HEADERS):
        assert status == 404, f"{method} {path} -> {status}, attendu 404 (pas de X-Admin-Token)"
    await _assert_customers_and_otp_open(client)


async def test_protected_routes_404_with_wrong_token(http, seeded, monkeypatch) -> None:
    monkeypatch.setattr(assistant_env, "admin_token", "s3cret-admin")
    client, _app = http
    bad = {**CLIENT_HEADERS, "X-Admin-Token": "wrong-token"}
    for method, path, status in await _call_all(client, bad):
        assert status == 404, f"{method} {path} -> {status}, attendu 404 (mauvais jeton)"
    await _assert_customers_and_otp_open(client)


async def test_protected_routes_404_when_admin_token_unset(http, seeded, monkeypatch) -> None:
    monkeypatch.setattr(assistant_env, "admin_token", None)
    client, _app = http
    for method, path, status in await _call_all(client, {**CLIENT_HEADERS, **ADMIN}):
        assert status == 404, f"{method} {path} -> {status}, attendu 404 (ADMIN_TOKEN non configuré)"
    await _assert_customers_and_otp_open(client)


async def test_protected_routes_200_with_good_token(http, seeded, monkeypatch) -> None:
    monkeypatch.setattr(assistant_env, "admin_token", "s3cret-admin")
    client, _app = http
    good = {**CLIENT_HEADERS, **ADMIN}
    results = await _call_all(client, good)
    for method, path, status in results:
        assert status == 200, f"{method} {path} -> {status}, attendu 200 (bon jeton)"
    # the reset actually ran and reported the cleared tables
    reset = await client.post("/api/demo/reset", json={}, headers=good)
    assert reset.status_code == 200 and reset.json()["ok"] is True
    assert "pending_actions" in reset.json()["deleted"]
    await _assert_customers_and_otp_open(client)
