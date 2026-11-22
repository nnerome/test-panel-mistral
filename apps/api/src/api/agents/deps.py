"""Per-run infrastructure for tools, plus a per-turn collector.

Tools are module-level functions (the SDK requires it), so they reach the request's
infrastructure through a contextvar set by the orchestrator around each agent run:
session maker, bank adapter, KB embedder. The collector accumulates what the turn's tools
returned (sources, proposed action) so the orchestrator can put it in the turn result and the
UI — the model never needs to carry it."""

import contextvars
from dataclasses import dataclass, field

from api.bank.protocol import Bank
from api.kb.retriever import Embedder
from db.engine import get_session_maker
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession


@dataclass
class RunDeps:
    session_maker: async_sessionmaker[AsyncSession]
    bank: Bank
    embedder: Embedder


@dataclass
class RunCollector:
    sources: list[dict] = field(default_factory=list)
    pending_action: dict | None = None
    tool_results: list[dict] = field(default_factory=list)


_current_deps: contextvars.ContextVar[RunDeps] = contextvars.ContextVar("bnp_run_deps")
_current_collector: contextvars.ContextVar[RunCollector] = contextvars.ContextVar("bnp_run_collector")


def bind_run(deps: RunDeps, collector: RunCollector) -> contextvars.Token:
    t1 = _current_deps.set(deps)
    t2 = _current_collector.set(collector)
    return (t1, t2)  # type: ignore[return-value]


def reset_run(token) -> None:
    t1, t2 = token
    _current_deps.reset(t1)
    _current_collector.reset(t2)


def run_deps() -> RunDeps:
    return _current_deps.get()


def collector() -> RunCollector:
    return _current_collector.get()


def default_deps(bank: Bank, embedder: Embedder) -> RunDeps:
    return RunDeps(session_maker=get_session_maker(), bank=bank, embedder=embedder)
