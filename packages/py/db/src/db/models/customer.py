"""Fictional demo customer. `password_hash` is a plain SHA-256 of the demo password:
this is a prototype with fake data, not a credential store (production would use Argon2id)."""

from db.models._base import Base
from sqlmodel import Field


class Customer(Base, table=True):
    __tablename__ = "customers"

    email: str = Field(unique=True, index=True)
    display_name: str
    password_hash: str
