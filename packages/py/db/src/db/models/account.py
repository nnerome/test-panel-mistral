"""Fictional account. The full (fake) IBAN is stored here and masked by the adapter boundary."""

import uuid

from db.models._base import Base
from sqlmodel import Field


class Account(Base, table=True):
    __tablename__ = "accounts"

    customer_id: uuid.UUID = Field(foreign_key="customers.id", index=True)
    label: str
    iban: str  # full FAKE IBAN, read by nothing but the seed: accessors never select it
    iban_prefix: str  # first 4 chars (country + check digits), not secret
    iban_last4: str
    balance_cents: int
    currency: str = "EUR"
