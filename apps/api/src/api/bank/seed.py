"""Fake seed data: 3 fictional customers, accounts, cards (one customer has two, so
"lock my card" is ambiguous), 3 agencies. Idempotent: a populated DB is left alone.

All PANs/IBANs are invented test numbers. Customer ids are fixed UUIDs so tests and demos can
refer to them stably."""

import uuid
from datetime import datetime, timezone

from db.engine import get_session_maker
from db.models.account import Account
from db.models.agency import Agency
from db.models.card import Card
from db.models.customer import Customer
from sqlmodel import select

from api.auth.service import hash_secret

CUSTOMER_ALICE = uuid.UUID("11111111-1111-4111-8111-111111111111")
CUSTOMER_BOB = uuid.UUID("22222222-2222-4222-8222-222222222222")
CUSTOMER_CAROLE = uuid.UUID("33333333-3333-4333-8333-333333333333")

DEMO_PASSWORD = "demo1234"

ACCOUNT_ALICE = uuid.UUID("aaaaaaa1-0000-4000-8000-000000000001")
ACCOUNT_BOB_MAIN = uuid.UUID("bbbbbbb1-0000-4000-8000-000000000001")
ACCOUNT_BOB_SAVINGS = uuid.UUID("bbbbbbb2-0000-4000-8000-000000000002")
ACCOUNT_CAROLE = uuid.UUID("ccccccc1-0000-4000-8000-000000000001")

CARD_ALICE = uuid.UUID("c0000001-0000-4000-8000-000000000001")
CARD_BOB_DEBIT = uuid.UUID("c0000002-0000-4000-8000-000000000001")
CARD_BOB_CREDIT = uuid.UUID("c0000002-0000-4000-8000-000000000002")
CARD_CAROLE = uuid.UUID("c0000003-0000-4000-8000-000000000001")

AGENCY_PARIS = uuid.UUID("d0000001-0000-4000-8000-000000000001")
AGENCY_LYON = uuid.UUID("d0000002-0000-4000-8000-000000000001")
AGENCY_BORDEAUX = uuid.UUID("d0000003-0000-4000-8000-000000000001")

# Fake PANs (invented, Visa/Mastercard test-style prefixes).
PAN_ALICE = "4001234567890001"
PAN_BOB_DEBIT = "5412345678905678"
PAN_BOB_CREDIT = "5412349012349012"
PAN_CAROLE = "4001987654320004"


async def seed_if_empty(session_maker=None) -> None:
    session_maker = session_maker or get_session_maker()
    async with session_maker() as session:
        count = len((await session.execute(select(Customer))).scalars().all())
        if count:
            return
        now = datetime.now(timezone.utc)
        customers = [
            Customer(id=CUSTOMER_ALICE, email="alice.demo@bank-fictive.fr", display_name="Alice Martin", password_hash=hash_secret(DEMO_PASSWORD)),
            Customer(id=CUSTOMER_BOB, email="bob.demo@bank-fictive.fr", display_name="Bob Durand", password_hash=hash_secret(DEMO_PASSWORD)),
            Customer(id=CUSTOMER_CAROLE, email="carole.demo@bank-fictive.fr", display_name="Carole Petit", password_hash=hash_secret(DEMO_PASSWORD)),
        ]
        accounts = [
            Account(id=ACCOUNT_ALICE, customer_id=CUSTOMER_ALICE, label="Compte courant", iban="FR7630004000010001234567001", iban_prefix="FR76", iban_last4="7001", balance_cents=254310, currency="EUR"),
            Account(id=ACCOUNT_BOB_MAIN, customer_id=CUSTOMER_BOB, label="Compte courant", iban="FR7630004000020009876543002", iban_prefix="FR76", iban_last4="3002", balance_cents=87025, currency="EUR"),
            Account(id=ACCOUNT_BOB_SAVINGS, customer_id=CUSTOMER_BOB, label="Livret épargne", iban="FR7630004000020001111222233", iban_prefix="FR76", iban_last4="2233", balance_cents=1200000, currency="EUR"),
            Account(id=ACCOUNT_CAROLE, customer_id=CUSTOMER_CAROLE, label="Compte courant", iban="FR7630004000030005555666677", iban_prefix="FR76", iban_last4="6677", balance_cents=-42150, currency="EUR"),
        ]
        cards = [
            Card(id=CARD_ALICE, customer_id=CUSTOMER_ALICE, account_id=ACCOUNT_ALICE, pan=PAN_ALICE, pan_last4=PAN_ALICE[-4:], brand="Visa", label="Carte de débit"),
            # Bob owns two cards on purpose: "lock my card" must be disambiguated by masked label.
            Card(id=CARD_BOB_DEBIT, customer_id=CUSTOMER_BOB, account_id=ACCOUNT_BOB_MAIN, pan=PAN_BOB_DEBIT, pan_last4=PAN_BOB_DEBIT[-4:], brand="Mastercard", label="Carte de débit"),
            Card(id=CARD_BOB_CREDIT, customer_id=CUSTOMER_BOB, account_id=ACCOUNT_BOB_MAIN, pan=PAN_BOB_CREDIT, pan_last4=PAN_BOB_CREDIT[-4:], brand="Mastercard", label="Carte de crédit"),
            Card(id=CARD_CAROLE, customer_id=CUSTOMER_CAROLE, account_id=ACCOUNT_CAROLE, pan=PAN_CAROLE, pan_last4=PAN_CAROLE[-4:], brand="Visa", label="Carte de débit"),
        ]
        agencies = [
            Agency(id=AGENCY_PARIS, name="Agence Paris Centre", city="Paris", address="12 rue de la Paix, 75002 Paris", hours_text="Lun-Ven : 9h00-17h15\nSamedi : 9h00-12h00"),
            Agency(id=AGENCY_LYON, name="Agence Lyon Bellecour", city="Lyon", address="3 place Bellecour, 69002 Lyon", hours_text="Lun-Ven : 9h00-17h15"),
            Agency(id=AGENCY_BORDEAUX, name="Agence Bordeaux Gambetta", city="Bordeaux", address="28 cours de l'Intendance, 33000 Bordeaux", hours_text="Lun-Ven : 9h00-17h15\nSamedi : 9h00-12h00"),
        ]
        # Flush in dependency order: without declared relationships the unit of work does
        # not know accounts/cards depend on customers, and would insert in table-name order.
        for row in customers:
            session.add(row)
        await session.flush()
        for row in [*accounts, *cards, *agencies]:
            session.add(row)
        await session.commit()
