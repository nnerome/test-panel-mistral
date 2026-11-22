"""The `Bank` protocol: the only surface the api layer has of the bank's legacy systems.

Design rules defended in the interview:
- Identity arguments (`customer_id`, `account_id`, `card_id`) exist here because the legacy
  systems key on them, but they ALWAYS come from the server session at the call site — never
  from the model (see the agent tools: their schemas contain no identity parameter at all).
- Card data crosses this boundary only as `CardView`, which has no PAN field by construction.
- `lock_card` takes an idempotency key so a retry can never lock twice.
"""

import uuid
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class BankError(Exception):
    """The legacy system failed. The api turns this into a customer message + human offer."""


class BankTimeoutError(BankError):
    """The legacy system did not answer in time."""


class AgencyHours(BaseModel):
    agency_id: uuid.UUID
    name: str
    lines: list[str]


class AccountInfo(BaseModel):
    """Account view for callers: IBAN already masked."""

    account_id: uuid.UUID
    label: str
    masked_iban: str
    balance_cents: int
    currency: str


class CardView(BaseModel):
    """Masked card DTO. Note what is absent: there is no `pan` field, so a caller cannot leak it."""

    card_id: uuid.UUID
    masked_number: str
    brand: str
    label: str
    status: str


class Money(BaseModel):
    amount_cents: int
    currency: str


class CardLockResult(BaseModel):
    card_id: uuid.UUID
    masked_number: str
    status: str
    locked_at: datetime
    idempotency_key: str


class Bank(Protocol):
    async def get_agency_hours(self, agency_id: uuid.UUID) -> AgencyHours: ...
    async def get_accounts(self, customer_id: uuid.UUID) -> list[AccountInfo]: ...
    async def get_balance(self, account_id: uuid.UUID) -> Money: ...
    async def list_cards(self, customer_id: uuid.UUID) -> list[CardView]: ...
    async def lock_card(self, card_id: uuid.UUID, idempotency_key: str) -> CardLockResult: ...
