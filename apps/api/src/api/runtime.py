"""App runtime wiring: the shared bank adapter (with live demo flags), the Mistral client, the
KB embedder — cached on app.state, plus first-use seeding/indexing."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from db.engine import get_session_maker
from fastapi import Request
from utils.mistral import mistral_client

from api.bank.mock import BankFlags, MockBank
from api.bank.protocol import Bank
from api.bank.seed import seed_if_empty
from api.kb.index import ensure_indexed
from api.kb.retriever import Embedder, MistralEmbedder


@dataclass
class Runtime:
    client: object
    bank: Bank
    embedder: Embedder
    kb_root: Path
    ready_lock: asyncio.Lock


def get_runtime(request: Request) -> Runtime:
    runtime = getattr(request.app.state, "bnp_runtime", None)
    if runtime is None:
        app = request.app
        flags = getattr(app.state, "bank_flags", None)
        if flags is None:
            flags = BankFlags.from_env()
            app.state.bank_flags = flags
        client = mistral_client()
        runtime = Runtime(
            client=client,
            # The flags provider reads app.state.bank_flags, so the demo toggles hit the adapter live.
            bank=MockBank(flags_provider=lambda: app.state.bank_flags),
            embedder=MistralEmbedder(client),
            kb_root=Path(__file__).resolve().parents[4] / "knowledge",
            ready_lock=asyncio.Lock(),
        )
        app.state.bnp_runtime = runtime
    return runtime


async def ensure_ready(runtime: Runtime) -> None:
    """Seed the fake data and index the KB once per process (idempotent, lock-guarded)."""
    async with runtime.ready_lock:
        session_maker = get_session_maker()
        await seed_if_empty(session_maker)
        await ensure_indexed(runtime.embedder, session_maker)
