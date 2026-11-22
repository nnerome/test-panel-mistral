"""Prompt 1 tests: adapter masking, ownership rejection, fault injection, adapter idempotency."""

import json
import logging
import re
import time
import uuid

import pytest
from env.db import env as db_env
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.bank import seed
from api.bank.mock import BankFlags, MockBank
from api.bank.ownership import assert_account_owned, assert_card_owned
from api.bank.protocol import BankError
from api.domain.errors import OwnershipError

ALL_PANS = [seed.PAN_ALICE, seed.PAN_BOB_DEBIT, seed.PAN_BOB_CREDIT, seed.PAN_CAROLE]
ALL_IBANS = [
    "FR7630004000010001234567001",
    "FR7630004000020009876543002",
    "FR7630004000020001111222233",
    "FR7630004000030005555666677",
]


def make_bank(session_maker, latency_ms=0.0, failure_rate=0.0) -> MockBank:
    return MockBank(session_maker=session_maker, flags_provider=lambda: BankFlags(latency_ms, failure_rate))


async def test_list_cards_returns_masked_dtos_only(seeded) -> None:
    bank = make_bank(seeded)
    cards = await bank.list_cards(seed.CUSTOMER_BOB)
    assert len(cards) == 2  # Bob has two cards: the ambiguity the demo needs
    for card in cards:
        assert re.fullmatch(r"\*\*\*\* \*\*\*\* \*\*\*\* \d{4}", card.masked_number)
        blob = json.dumps(card.model_dump(mode="json"))
        for pan in ALL_PANS:
            assert pan not in blob


async def test_no_full_pan_or_iban_in_db_query_logs(seeded, caplog) -> None:
    """With echo='debug' SQLAlchemy logs the bound parameters too; the accessors never select
    the secret columns, so no PAN/IBAN can appear even there."""
    engine = create_async_engine(db_env.async_database_url, echo="debug")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        bank = make_bank(maker)
        with caplog.at_level(logging.DEBUG, logger="sqlalchemy.engine"):
            await bank.list_cards(seed.CUSTOMER_BOB)
            await bank.get_accounts(seed.CUSTOMER_BOB)
            await bank.get_balance(seed.ACCOUNT_BOB_MAIN)
            await bank.lock_card(seed.CARD_BOB_DEBIT, idempotency_key="log-test-1")
        for secret in [*ALL_PANS, *ALL_IBANS]:
            assert secret not in caplog.text, f"secret leaked into query logs: {secret}"
    finally:
        await engine.dispose()


async def test_get_balance_and_accounts_are_masked(seeded) -> None:
    bank = make_bank(seeded)
    accounts = await bank.get_accounts(seed.CUSTOMER_ALICE)
    assert len(accounts) == 1
    assert accounts[0].masked_iban == "FR76 **** **** 7001"
    for iban in ALL_IBANS:
        assert iban not in json.dumps([a.model_dump(mode="json") for a in accounts])
    money = await bank.get_balance(seed.ACCOUNT_ALICE)
    assert money.amount_cents == 254310 and money.currency == "EUR"


async def test_ownership_rejects_cross_customer(seeded) -> None:
    async with seeded() as session:
        with pytest.raises(OwnershipError):
            await assert_card_owned(session, customer_id=seed.CUSTOMER_ALICE, card_id=seed.CARD_BOB_DEBIT)
        with pytest.raises(OwnershipError):
            await assert_account_owned(session, customer_id=seed.CUSTOMER_CAROLE, account_id=seed.ACCOUNT_BOB_MAIN)
        # nonexistent ids raise the same 404-mapped error: no existence leak
        with pytest.raises(OwnershipError):
            await assert_card_owned(session, customer_id=seed.CUSTOMER_ALICE, card_id=uuid.uuid4())
        # the rightful owner passes
        await assert_card_owned(session, customer_id=seed.CUSTOMER_BOB, card_id=seed.CARD_BOB_DEBIT)


async def test_adapter_lock_card_is_idempotent(seeded) -> None:
    from db import accessors as acc

    bank = make_bank(seeded)
    first = await bank.lock_card(seed.CARD_BOB_CREDIT, idempotency_key="idem-1")
    second = await bank.lock_card(seed.CARD_BOB_CREDIT, idempotency_key="idem-1")
    assert first == second
    assert first.status == "locked"
    async with seeded() as session:
        event = await acc.bank_locks.get_by_key(session, "idem-1")
        assert event is not None
        view = await acc.cards.get_view(session, seed.CARD_BOB_CREDIT)
        assert view is not None and view.status == "locked"


async def test_failure_injection_raises_bank_error(seeded) -> None:
    bank = make_bank(seeded, failure_rate=1.0)
    with pytest.raises(BankError):
        await bank.list_cards(seed.CUSTOMER_ALICE)


async def test_latency_injection_slows_calls(seeded) -> None:
    bank = make_bank(seeded, latency_ms=300)
    start = time.perf_counter()
    await bank.get_balance(seed.ACCOUNT_ALICE)
    assert time.perf_counter() - start >= 0.3


async def test_agency_hours(seeded) -> None:
    bank = make_bank(seeded)
    hours = await bank.get_agency_hours(seed.AGENCY_PARIS)
    assert hours.name == "Agence Paris Centre"
    assert any("9h00-17h15" in line for line in hours.lines)
