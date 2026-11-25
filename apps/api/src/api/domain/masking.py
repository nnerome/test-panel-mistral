"""Masking at the adapter boundary: card numbers are stored full (fake) in the DB but every
value that leaves the adapter layer — DTOs, audit rows, logs, LLM context, UI payloads — is
masked here. A full PAN outside the DB is a bug by definition."""

import re

# A "candidate" run is a maximal sequence of digits possibly broken by single spaces, dots or
# dashes (how humans type card numbers: "4970 1010 2020 3030", "4970-1010-2020-3030", "4970.1010.2020.3030").
# Letters, colons, commas, quotes etc. always break a run, so timestamps, UUIDs, JSON and prose
# keep their short numeric runs readable.
_CANDIDATE_RUN = re.compile(r"\d(?:[\d .\-]*\d)?")
_PAN_MIN_DIGITS = 13  # below that it is a phone number / amount / date part, not a PAN


def mask_pan(pan: str) -> str:
    digits = re.sub(r"\D", "", pan)
    return f"**** **** **** {digits[-4:]}"


def mask_iban_parts(prefix: str, last4: str) -> str:
    return f"{prefix} **** **** {last4}"


def contains_pan_like(text: str) -> bool:
    """True when the text contains a run of 13+ digits (contiguous or typed with separators)."""
    return any(
        sum(ch.isdigit() for ch in m.group(0)) >= _PAN_MIN_DIGITS for m in _CANDIDATE_RUN.finditer(text)
    )


def scrub_secrets(text: str) -> str:
    """Last-line defence for anything written to logs/audit/feedback: mask any run of 13+ digits,
    contiguous or typed with separators. Anything shorter (phone numbers, amounts, date parts,
    timestamps, UUID fragments) is left untouched."""

    def _mask_if_pan_like(match: re.Match) -> str:
        run = match.group(0)
        if sum(ch.isdigit() for ch in run) >= _PAN_MIN_DIGITS:
            return "****"
        return run

    return _CANDIDATE_RUN.sub(_mask_if_pan_like, text)
