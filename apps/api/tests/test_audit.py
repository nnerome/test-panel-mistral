"""Prompt 1 tests: the audit log never contains a PAN, even if the caller forgot to mask."""

from db import accessors as acc

from api.audit.service import log_action
from api.bank import seed


async def test_audit_scrubs_pan_like_values(seeded) -> None:
    await log_action(
        seeded,
        customer_id=seed.CUSTOMER_ALICE,
        session_id=None,
        auth_level="strong",
        action="lock_card",
        masked_args={"card": "**** **** **** 0001", "note": f"raw attempt {seed.PAN_ALICE}"},
        result="locked",
        correlation_id="corr-1",
    )
    async with seeded() as session:
        rows = await acc.audit.list_all(session)
        assert len(rows) == 1
        assert seed.PAN_ALICE not in rows[0].masked_args
        assert "****" in rows[0].masked_args
        assert rows[0].action == "lock_card" and rows[0].auth_level == "strong"
