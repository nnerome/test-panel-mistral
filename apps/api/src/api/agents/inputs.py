"""The session input injected into every agent session: server-side identity, invisible to
the model (the SDK keeps it out of the tool schemas — verified in tests)."""

from mistralai import agents


class BankSessionInput(agents.SessionInput):
    input_id = "bnp.bank_session"

    customer_id: str | None  # None while anonymous
    session_id: str
    auth_level: str  # anonymous | authenticated | strong
    correlation_id: str
