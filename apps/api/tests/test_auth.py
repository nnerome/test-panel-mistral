"""Prompt 1 tests: auth levels, login, OTP single-use/expiry/attempt-limit, session handling."""

import uuid
from datetime import timedelta

import pytest
from db import accessors as acc

from api.auth import service
from api.auth.service import AuthRequiredError, OtpError, StepUpRequiredError
from api.bank import seed
from api.domain.errors import AuthRequiredError as DomainAuthRequired


async def test_login_and_levels(seeded) -> None:
    with pytest.raises(DomainAuthRequired):
        await service.login(seeded, "nobody@bank-fictive.fr", "demo1234")
    with pytest.raises(DomainAuthRequired):
        await service.login(seeded, "alice.demo@bank-fictive.fr", "wrong-password")
    ctx = await service.login(seeded, "alice.demo@bank-fictive.fr", seed.DEMO_PASSWORD)
    assert ctx.level == "authenticated" and ctx.customer_id == seed.CUSTOMER_ALICE
    resolved = await service.resolve_session(seeded, ctx.token)
    assert resolved is not None and resolved.session_id == ctx.session_id
    # the token is stored hashed: the raw token appears nowhere in the table
    async with seeded() as session:
        row = await acc.sessions.get_by_token_hash(session, service.hash_secret(ctx.token))
        assert row is not None
        assert ctx.token != row.token_hash


async def test_require_level_transitions(seeded) -> None:
    anon = await service.create_session(seeded)
    assert anon.level == "anonymous"
    with pytest.raises(DomainAuthRequired):
        service.require_level(anon, "authenticated")
    with pytest.raises(StepUpRequiredError):
        service.require_level(anon, "strong")
    ctx = await service.login(seeded, "bob.demo@bank-fictive.fr", seed.DEMO_PASSWORD)
    with pytest.raises(StepUpRequiredError):
        service.require_level(ctx, "strong")
    service.require_level(ctx, "authenticated")  # no raise


async def test_otp_happy_path_raises_strong(seeded) -> None:
    ctx = await service.login(seeded, "alice.demo@bank-fictive.fr", seed.DEMO_PASSWORD)
    otp_id, code, expires_at = await service.issue_otp(seeded, ctx)
    assert len(code) == 6 and otp_id is not None
    await service.verify_otp(seeded, ctx, code)
    resolved = await service.resolve_session(seeded, ctx.token)
    assert resolved is not None and resolved.level == "strong"
    service.require_level(resolved, "strong")  # no raise


async def test_otp_single_use_replay_fails(seeded) -> None:
    ctx = await service.login(seeded, "alice.demo@bank-fictive.fr", seed.DEMO_PASSWORD)
    _, code, _ = await service.issue_otp(seeded, ctx)
    await service.verify_otp(seeded, ctx, code)
    with pytest.raises(OtpError):
        await service.verify_otp(seeded, ctx, code)  # replay of a consumed code


async def test_otp_expiry(seeded) -> None:
    ctx = await service.login(seeded, "carole.demo@bank-fictive.fr", seed.DEMO_PASSWORD)
    _, code, _ = await service.issue_otp(seeded, ctx)
    # force the code into the past, as if 5 minutes had elapsed
    async with seeded() as session:
        otp = await acc.otps.latest_active_for_session(session, ctx.session_id, service.utcnow())
        assert otp is not None
        otp.expires_at = service.utcnow() - timedelta(seconds=1)
        await session.commit()
    with pytest.raises(OtpError) as exc:
        await service.verify_otp(seeded, ctx, code)
    assert exc.value.code == "otp_expired"


async def test_otp_attempt_limit(seeded) -> None:
    ctx = await service.login(seeded, "bob.demo@bank-fictive.fr", seed.DEMO_PASSWORD)
    _, code, _ = await service.issue_otp(seeded, ctx)
    for _ in range(5):
        with pytest.raises(OtpError) as exc:
            await service.verify_otp(seeded, ctx, "000000" if code != "000000" else "111111")
        assert exc.value.code == "otp_wrong"
    with pytest.raises(OtpError) as exc:
        await service.verify_otp(seeded, ctx, code)
    assert exc.value.code == "otp_locked"  # even the right code is refused now


async def test_new_otp_invalidates_previous(seeded) -> None:
    ctx = await service.login(seeded, "alice.demo@bank-fictive.fr", seed.DEMO_PASSWORD)
    _, code1, _ = await service.issue_otp(seeded, ctx)
    _, code2, _ = await service.issue_otp(seeded, ctx)
    with pytest.raises(OtpError):
        await service.verify_otp(seeded, ctx, code1)  # superseded code no longer works
    await service.verify_otp(seeded, ctx, code2)


async def test_session_token_unknown_or_expired(seeded) -> None:
    assert await service.resolve_session(seeded, None) is None
    assert await service.resolve_session(seeded, "not-a-real-token") is None
    ctx = await service.create_session(seeded)
    async with seeded() as session:
        row = await acc.sessions.get(session, ctx.session_id)
        assert row is not None
        row.expires_at = service.utcnow() - timedelta(seconds=1)
        await session.commit()
    assert await service.resolve_session(seeded, ctx.token) is None
