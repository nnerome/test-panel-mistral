"""Prototype-only settings for the banking assistant: models per stage, KB retrieval,
mock-bank fault injection, demo authentication and pending-action lifetimes.

Every value has a default, so nothing here needs a line in `.env`; add one there only to
override locally. Names are declared (empty) in `.env.example` per the repo convention.
"""

from env._base import BaseEnv


class Env(BaseEnv):
    # Model per orchestrator stage. The moderation model is free of charge; the classifier
    # uses the smallest chat model to keep the per-turn cost and latency down. The assistant
    # defaults to the GA flagship (mistral-large-4); set ASSISTANT_MODEL=mistral-small-latest
    # for the cheapest turns — see docs/LATENCY-COST.md.
    assistant_model: str = "mistral-large-4"
    # The FAQ path runs on the small fast model by default: public Q&A doesn't need the
    # flagship, and it cuts both latency and cost per turn (account/action stay on the
    # flagship). See docs/LATENCY-COST.md.
    faq_model: str = "mistral-small-latest"
    # Pinned to a dated snapshot, not the moving -latest alias: the alias rolled to a new
    # snapshot and silently changed routing (faq -> action/account_info), which the regression
    # suite caught. Pinning keeps intent classification reproducible; bump deliberately.
    classifier_model: str = "mistral-small-2603"
    moderation_model: str = "mistral-moderation-2603"
    embedding_model: str = "mistral-embed"

    # Output checks cost one extra model call per turn, so they ship disabled: flip the flag
    # to enable them and see the latency delta in the per-stage timings.
    output_check_enabled: bool = False
    output_check_model: str = "mistral-small-latest"

    # Knowledge-base retrieval: top-k passages and the chunk size used at index time.
    kb_top_k: int = 5
    kb_chunk_chars: int = 700

    # Mock bank adapter fault injection. The UI demo toggles override these at runtime.
    bank_latency_ms: float = 0.0
    bank_failure_rate: float = 0.0
    bank_timeout_ms: float = 8000.0

    # Demo authentication: session and one-time-code lifetimes.
    session_ttl_seconds: int = 8 * 3600
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    # The demo has no real SMS channel, so the step-up response carries the fake code.
    demo_show_otp: bool = True
    # Demo endpoints (customer list with password hint, live bank-fault toggles) exist only in
    # demo mode; set false in any real deployment so /api/demo/* answers 404.
    demo_mode: bool = True
    # Reserved routes (metrics, feedback list, handoff queue, /api/demo/* incl. the DB reset) are
    # active in demo mode only; otherwise they answer a uniform 404. The demo is openly labelled
    # and uses fake data, so in demo mode they are open to every visitor on purpose.
    # Kill switch for state-changing actions (lock card). When false, no action agent runs and
    # confirm refuses with actions_disabled. Hot-togglable in demo mode via /api/demo/feature-flags.
    actions_enabled: bool = True
    # Secure attribute on the session cookie: false for local http, true behind TLS in prod.
    session_cookie_secure: bool = False

    # A pending action (e.g. card lock) expires after this; the confirm endpoint refuses past it.
    pending_action_ttl_seconds: int = 300

    # State-changing endpoints require this custom header, set only by our own frontend:
    # a cross-site form cannot set custom headers, which is the CSRF defence for the prototype.
    require_client_header: bool = True
    client_header_name: str = "X-Bnp-Client"
    client_header_value: str = "bnp-assistant-web"


env = Env()
