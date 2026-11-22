"""Fictional bank agency with its opening hours, shown as preformatted lines."""

from db.models._base import Base
from sqlmodel import Field


class Agency(Base, table=True):
    __tablename__ = "agencies"

    name: str
    city: str
    address: str
    hours_text: str
