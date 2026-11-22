"""Masking at the adapter boundary: card numbers are stored full (fake) in the DB but every
value that leaves the adapter layer — DTOs, audit rows, logs, LLM context, UI payloads — is
masked here. A full PAN outside the DB is a bug by definition."""

import re

_PAN_LIKE = re.compile(r"\b\d{13,19}\b")


def mask_pan(pan: str) -> str:
    digits = re.sub(r"\D", "", pan)
    return f"**** **** **** {digits[-4:]}"


def mask_iban_parts(prefix: str, last4: str) -> str:
    return f"{prefix} **** **** {last4}"


def scrub_secrets(text: str) -> str:
    """Last-line defence for anything written to logs/audit: mask any 13-19 digit run."""
    return _PAN_LIKE.sub("****", text)
