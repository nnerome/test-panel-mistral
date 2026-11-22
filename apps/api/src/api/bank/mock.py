"""`MockBank`: the `Bank` protocol backed by Postgres, standing in for the legacy systems.

Swappable without touching the agents: anything implementing `Bank` can be injected.

Fault injection for the demo: every call sleeps `latency_ms` and fails with probability
`failure_rate` (a `BankError`), and is bounded by `timeout_ms` (a `BankTimeoutError`). The
values come from env by default and can be overridden at runtime through the demo flags, so
the UI can switch slow/failure mode live.

Masking boundary: this adapter is the only place that turns DB rows into DTOs, and the
accessors never even SELECT the full PAN/IBAN — so no full number can leak into a return
value, a log line or a query parameter.
"""

import asyncio
import json
import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from db import accessors as acc
from db.engine import get_session_maker
from env.assistant import env as assistant_env
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from api.bank.protocol import AccountInfo, AgencyHours, BankError, BankTimeoutError, CardLockResult, CardView, Money
from api.domain.masking import mask_iban_parts


@dataclass
class BankFlags:
    latency_ms: float
    failure_rate: float

    @classmethod
    def from_env(cls) -> "BankFlags":
        return cls(latency_ms=assistant_env.bank_latency_ms, failure_rate=assistant_env.bank_failure_rate)


def mask_pan_last4(pan_last4: str) -> str:
    return f"**** **** **** {pan_last4}"


class MockBank:
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        flags_provider: Callable[[], BankFlags] | None = None,
        timeout_ms: float | None = None,
    ):
        self._session_maker = session_maker or get_session_maker()
        self._flags_provider = flags_provider or BankFlags.from_env
        self._timeout_ms = assistant_env.bank_timeout_ms if timeout_ms is None else timeout_ms

    async def _call(self, fn):
        """Wrap one adapter call with the simulated latency, failure and timeout."""
        flags = self._flags_provider()
        if flags.latency_ms > 0:
            await asyncio.sleep(flags.latency_ms / 1000.0)
        if flags.failure_rate > 0 and random.random() < flags.failure_rate:
            raise BankError("simulated bank failure (BANK_FAILURE_RATE)")

        async def run():
            return await fn()

        try:
            return await asyncio.wait_for(run(), timeout=self._timeout_ms / 1000.0)
        except asyncio.TimeoutError as error:
            raise BankTimeoutError("bank system timed out") from error

    async def get_agency_hours(self, agency_id: uuid.UUID) -> AgencyHours:
        async def fn() -> AgencyHours:
            async with self._session_maker() as session:
                agency = await acc.agencies.get(session, agency_id)
                if agency is None:
                    raise BankError(f"unknown agency {agency_id}")
                return AgencyHours(agency_id=agency.id, name=agency.name, lines=agency.hours_text.splitlines())

        return await self._call(fn)  # type: ignore[return-value]

    async def get_accounts(self, customer_id: uuid.UUID) -> list[AccountInfo]:
        async def fn() -> list[AccountInfo]:
            async with self._session_maker() as session:
                rows = await acc.accounts.list_views_for_customer(session, customer_id)
                return [
                    AccountInfo(
                        account_id=r.account_id,
                        label=r.label,
                        masked_iban=mask_iban_parts(r.iban_prefix, r.iban_last4),
                        balance_cents=r.balance_cents,
                        currency=r.currency,
                    )
                    for r in rows
                ]

        return await self._call(fn)  # type: ignore[return-value]

    async def get_balance(self, account_id: uuid.UUID) -> Money:
        async def fn() -> Money:
            async with self._session_maker() as session:
                row = await acc.accounts.get_view(session, account_id)
                if row is None:
                    raise BankError(f"unknown account {account_id}")
                return Money(amount_cents=row.balance_cents, currency=row.currency)

        return await self._call(fn)  # type: ignore[return-value]

    async def list_cards(self, customer_id: uuid.UUID) -> list[CardView]:
        async def fn() -> list[CardView]:
            async with self._session_maker() as session:
                rows = await acc.cards.list_views_for_customer(session, customer_id)
                return [
                    CardView(
                        card_id=r.card_id,
                        masked_number=mask_pan_last4(r.pan_last4),
                        brand=r.brand,
                        label=r.label,
                        status=r.status,
                    )
                    for r in rows
                ]

        return await self._call(fn)  # type: ignore[return-value]

    async def lock_card(self, card_id: uuid.UUID, idempotency_key: str) -> CardLockResult:
        """Idempotent at the adapter too: the ledger's UNIQUE(idempotency_key) means a retried
        call returns the stored result instead of locking twice."""

        async def fn() -> CardLockResult:
            async with self._session_maker() as session:
                existing = await acc.bank_locks.get_by_key(session, idempotency_key)
                if existing is not None:
                    return self._result_from_event(existing)
                view = await acc.cards.get_view(session, card_id)
                if view is None:
                    raise BankError(f"unknown card {card_id}")
                now = datetime.now(timezone.utc)
                result = CardLockResult(
                    card_id=view.card_id,
                    masked_number=mask_pan_last4(view.pan_last4),
                    status="locked",
                    locked_at=now,
                    idempotency_key=idempotency_key,
                )
                await acc.bank_locks.create(
                    session, idempotency_key=idempotency_key, card_id=view.card_id, result_json=result.model_dump_json(), locked_at=now
                )
                await acc.cards.set_locked(session, view.card_id, now)
                await session.commit()
                return result

        try:
            return await self._call(fn)  # type: ignore[return-value]
        except IntegrityError as error:
            # Lost the race on UNIQUE(idempotency_key): read back the winner's stored result.
            async with self._session_maker() as session:
                existing = await acc.bank_locks.get_by_key(session, idempotency_key)
            if existing is None:
                raise BankError("lock failed") from error
            return self._result_from_event(existing)

    @staticmethod
    def _result_from_event(event) -> CardLockResult:
        stored = json.loads(event.result_json)
        return CardLockResult(
            card_id=event.card_id,
            masked_number=stored["masked_number"],
            status=stored["status"],
            locked_at=event.locked_at,
            idempotency_key=event.idempotency_key,
        )
