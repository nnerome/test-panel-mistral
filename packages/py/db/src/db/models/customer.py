"""Fictional demo customer. `password_hash` is a plain SHA-256 of the demo password:
this is a prototype with fake data, not a credential store (production would use Argon2id)."""

import uuid

from db.models._base import Base
from sqlmodel import Field


class Customer(Base, table=True):
    __tablename__ = "customers"

    email: str = Field(unique=True, index=True)
    display_name: str
    password_hash: str
    # The customer's own agency (drives "horaires de mon agence"); nullable for old rows.
    agency_id: uuid.UUID | None = Field(default=None, foreign_key="agencies.id")
