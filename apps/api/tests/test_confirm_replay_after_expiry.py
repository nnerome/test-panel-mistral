"""Regression: a confirmed action replayed AFTER its TTL must return the stored result
(executed=False, no 409, status stays "confirmed", one audit entry), while a never-confirmed
action past its TTL must still expire."""

from datetime import timedelta

import pytest
from db import accessors as acc

from api.actions.service import confirm_action
from api.auth import service
from api.bank import seed
from api.bank.mock import BankFlags, MockBank
from api.domain.errors import ConflictError


def _bank(seeded):
    return MockBank(session_maker=seeded, flags_provider=lambda: BankFlags(0, 0))


async def _strong_ctx(seeded, email="bob.demo@bank-fictive.fr"):
    ctx = await service.login(seeded, email, seed.DEMO_PASSWORD)
    _, code, _ = await service.issue_otp(seeded, ctx)
    await service.verify_otp(seeded, ctx, code)
    return await service.resolve_session(seeded, ctx.token)


async def _make_pending(seeded, ctx, card_id=seed.CARD_BOB_CREDIT):
    from datetime import datetime, timezone

    async with seeded() as session:
        action = await acc.pending_actions.create(
            session,
            session_id=ctx.session_id,
            customer_id=ctx.customer_id,
            kind="lock_card",
            card_id=card_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        await session.commit()
        return action.id


async def _age(seeded, action_id, minutes=10):
    async with seeded() as session:
        action = await acc.pending_actions.get(session, action_id)
        action.expires_at = action.expires_at - timedelta(minutes=minutes)
        await session.commit()


async def test_replay_after_ttl_returns_stored_result(seeded) -> None:
    ctx = await _strong_ctx(seeded)
    action_id = await _make_pending(seeded, ctx)

    first = await confirm_action(seeded, ctx=ctx, action_id=action_id, bank=_bank(seeded))
    assert first["executed"] is True

    await _age(seeded, action_id)

    replay = await confirm_action(seeded, ctx=ctx, action_id=action_id, bank=_bank(seeded))
    assert replay["executed"] is False
    assert replay["result"] == first["result"]
    assert replay["action"]["status"] == "confirmed"

    async with seeded() as session:
        action = await acc.pending_actions.get(session, action_id)
        assert action.status == "confirmed"
        audits = await acc.audit.list_all(session)
        assert len([a for a in audits if a.action == "lock_card"]) == 1


async def test_unconfirmed_action_past_ttl_still_expires(seeded) -> None:
    ctx = await _strong_ctx(seeded)
    action_id = await _make_pending(seeded, ctx)
    await _age(seeded, action_id)

    with pytest.raises(ConflictError) as first:
        await confirm_action(seeded, ctx=ctx, action_id=action_id, bank=_bank(seeded))
    assert first.value.code == "action_expired"

    with pytest.raises(ConflictError) as second:
        await confirm_action(seeded, ctx=ctx, action_id=action_id, bank=_bank(seeded))
    assert second.value.code == "action_expired"

    async with seeded() as session:
        card = await acc.cards.get_view(session, seed.CARD_BOB_CREDIT)
        assert card is not None and card.status != "locked"
