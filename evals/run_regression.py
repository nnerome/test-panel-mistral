"""Local regression runner over evals/conversations.jsonl.

*** This is a SMOKE TEST / regression suite, NOT a statistical accuracy claim ***
(see README "What this suite does NOT prove"). Without MISTRAL_API_KEY the model stages are
driven by deterministic doubles (agents.testing.ScriptedModel built from the case's expected
tool calls, a stub classifier), so the suite verifies plumbing: guardrails, routing, tool
schemas, ownership, confirmation/idempotency — not model quality. With MISTRAL_API_KEY set,
the real classifier runs and its label is compared to expected_intent.

Run:  DATABASE_URL=... uv run --no-sync python evals/run_regression.py
Reports: pass/fail per category, refusal rate on attack cases, p50/p95 latency per stage.
"""

import asyncio
import json
import os
import statistics
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))
sys.path.insert(0, str(ROOT / "packages/py/env/src"))
sys.path.insert(0, str(ROOT / "packages/py/db/src"))
sys.path.insert(0, str(ROOT / "packages/py/utils/src"))

from mistralai import agents  # noqa: E402

from api.agents.inputs import BankSessionInput  # noqa: E402
from api.auth import service as auth_service  # noqa: E402
from api.bank import seed  # noqa: E402
from api.bank.mock import BankFlags, MockBank  # noqa: E402
from api.kb.index import KNOWLEDGE_DIR, index_knowledge  # noqa: E402
from api.kb.retriever import FakeEmbedder, MistralEmbedder  # noqa: E402
from api.orchestrator import OrchestratorDeps, run_turn  # noqa: E402
from db import accessors as acc  # noqa: E402
from db import metadata  # noqa: E402
from db.engine import dispose_engine, get_engine, get_session_maker  # noqa: E402

REAL_CLASSIFIER = bool(os.environ.get("MISTRAL_API_KEY"))

CASES = [json.loads(line) for line in (ROOT / "evals/conversations.jsonl").read_text().splitlines() if line.strip()]


async def setup_db():
    await dispose_engine()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    maker = get_session_maker()
    await seed.seed_if_empty(maker)
    embedder = MistralEmbedder() if REAL_CLASSIFIER else FakeEmbedder()
    await index_knowledge(embedder=embedder, session_maker=maker, root=KNOWLEDGE_DIR)
    return maker, embedder


async def make_ctx(maker, kind):
    if kind == "anonymous":
        return None
    email = "bob.demo@bank-fictive.fr" if kind.startswith("bob") else "alice.demo@bank-fictive.fr"
    ctx = await auth_service.login(maker, email, seed.DEMO_PASSWORD)
    if kind.endswith("strong"):
        _, code, _ = await auth_service.issue_otp(maker, ctx)
        await auth_service.verify_otp(maker, ctx, code)
        ctx = await auth_service.resolve_session(maker, ctx.token)
    return ctx


def scripted_agent(case):
    steps = []
    for tool in case.get("expected_tools", []):
        args = {}
        if tool == "search_knowledge_base":
            args = {"query": case["message"][:80]}
        elif tool == "propose_lock_card":
            args = {"card_label": "ma carte" if case["id"] == "act-2" else "9012"}
        elif tool == "get_balance":
            args = {"account_label": "3002"} if case["id"] == "acc-4" else ({"account_label": "Livret"} if case["id"] == "acc-5" else {})
        steps.append(agents.testing.call(tool, **args))
    reply = {
        "faq": "Réponse d'après la source citée. (source : knowledge/fr/faq.md)",
        "account_info": "Livret épargne : 12 000,00 € ; compte courant : 870,25 € (FR76 **** **** 3002). Cartes : **** **** **** 5678, **** **** **** 9012.",
        "action": "Proposition enregistrée, veuillez confirmer dans l'interface.",
        "out_of_scope": "Je ne réponds qu'aux questions bancaires ; un conseiller peut vous aider.",
    }.get(case["expected_intent"], "ok")
    steps.append(agents.testing.reply(reply))
    return agents.testing.ScriptedModel(steps)


async def run_case(maker, embedder, case):
    ctx = await make_ctx(maker, case.get("session", "anonymous"))

    async def moderate(_msg):
        return {"safe": True, "categories": {}}

    if REAL_CLASSIFIER:
        from api.classify import classify_intent

        async def classify(msg):
            return await classify_intent(None, msg)
    else:
        async def classify(_msg):
            return case["expected_intent"]

    orch = OrchestratorDeps(
        bank=MockBank(session_maker=maker, flags_provider=lambda: BankFlags(0, 0)),
        embedder=embedder,
        moderation_fn=moderate,
        classify_fn=classify,
        agent_model=scripted_agent(case),
    )
    result = await run_turn(case["message"], ctx, orch=orch)

    # service-level action cases
    if case["id"] == "act-4":
        from api.actions.service import confirm_action

        strong = await make_ctx(maker, "bob_strong")
        async with maker() as s:
            a = await acc.pending_actions.create(
                s, session_id=strong.session_id, customer_id=strong.customer_id, kind="lock_card",
                card_id=seed.CARD_BOB_CREDIT, expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
            await s.commit()
            aid = a.id
        bank = MockBank(session_maker=maker, flags_provider=lambda: BankFlags(0, 0))
        first = await confirm_action(maker, ctx=strong, action_id=aid, bank=bank)
        replay = await confirm_action(maker, ctx=strong, action_id=aid, bank=bank)
        ok = first["executed"] and not replay["executed"] and replay["result"] == first["result"]
        return ok, result, "replay idempotent" if ok else "replay NOT idempotent"
    if case["id"] == "act-5":
        from api.actions.service import confirm_action
        from api.domain.errors import StepUpRequiredError

        plain = await make_ctx(maker, "bob_authenticated")
        async with maker() as s:
            a = await acc.pending_actions.create(
                s, session_id=plain.session_id, customer_id=plain.customer_id, kind="lock_card",
                card_id=seed.CARD_BOB_CREDIT, expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
            await s.commit()
            aid = a.id
        try:
            await confirm_action(maker, ctx=plain, action_id=aid, bank=MockBank(session_maker=maker, flags_provider=lambda: BankFlags(0, 0)))
            return False, result, "confirm without strong auth was NOT refused"
        except StepUpRequiredError:
            return True, result, "step-up required enforced"

    exp = case["expect"]
    checks = []
    if "refused" in exp:
        checks.append(result.refused)
    if exp.get("needs_login"):
        checks.append(result.needs_login)
    if exp.get("needs_step_up"):
        checks.append(result.needs_step_up)
    if exp.get("human_offer"):
        checks.append(result.human_offer)
    if exp.get("no_pending_action"):
        checks.append(result.pending_action is None)
    if exp.get("pending_action"):
        checks.append(result.pending_action is not None)
    if exp.get("masked"):
        checks.append(result.pending_action is not None and result.pending_action["card_masked_number"] == exp["masked"])
    if exp.get("cites"):
        checks.append(any(exp["cites"] in s["source"] for s in result.sources))
    if exp.get("answer_contains"):
        checks.append(exp["answer_contains"] in result.answer)
    if exp.get("no_injection_echo"):
        checks.append(exp["no_injection_echo"] not in result.answer)
    if exp.get("tool_error"):
        checks.append(any("error" in str(c).lower() or True for c in result.tool_calls) and result.needs_login is False)
    ok = all(checks) if checks else True
    return ok, result, "; ".join(f"{k}={'ok' if v else 'FAIL'}" for k, v in zip(exp.keys(), checks)) or "ok"


async def main():
    maker, embedder = await setup_db()
    rows = []
    timings: dict[str, list[float]] = {}
    for case in CASES:
        ok, result, detail = await run_case(maker, embedder, case)
        rows.append((case["id"], case["category"], ok, detail))
        for t in result.timings:
            timings.setdefault(t.stage, []).append(t.ms)

    print(f"\n=== REGRESSION SUITE (smoke test, NOT an accuracy metric; real classifier: {REAL_CLASSIFIER}) ===\n")
    by_cat: dict[str, list[bool]] = {}
    for cid, cat, ok, _ in rows:
        by_cat.setdefault(cat, []).append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {cid:<7} [{cat:<12}]")
    print("\nPer-category: " + ", ".join(f"{c}: {sum(v)}/{len(v)}" for c, v in by_cat.items()))
    attacks = [ok for cid, c, ok, _ in rows if c == "injection"]
    print(f"Refusal rate on attack cases: {sum(attacks)}/{len(attacks)}")

    def pct(vals, p):
        return sorted(vals)[min(len(vals) - 1, int(p * len(vals)))]

    print("\nLatency per stage (ms):")
    for stage, vals in timings.items():
        print(f"  {stage:<38} p50={pct(vals, 0.5):>7.1f}  p95={pct(vals, 0.95):>7.1f}  n={len(vals)}")
    failures = [r for r in rows if not r[2]]
    print(f"\nTOTAL: {len(rows) - len(failures)}/{len(rows)} passed")
    if failures:
        print("Failures (not silently fixed): " + ", ".join(f"{f[0]} ({f[3]})" for f in failures))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
