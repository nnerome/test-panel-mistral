"""Audit logging. One row per security-relevant event; arguments are scrubbed of PAN-like
sequences before storage so the audit trail can never contain an unmasked card number."""
