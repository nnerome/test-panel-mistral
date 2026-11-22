"""The confirmation path for state-changing actions — the heart of the demo.

The model NEVER confirms anything: `propose_lock_card` only creates a pending action. Execution
happens exclusively in POST /api/actions/{id}/confirm, which checks, in order: session binding,
strong auth level, expiry, card ownership, and idempotency (UNIQUE constraint on the action id in
the execution table + stored result)."""
