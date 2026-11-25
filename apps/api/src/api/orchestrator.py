"""The per-turn orchestrator. Every stage is traced and timed in the turn result:

1) input guardrails (Mistral moderation + injection patterns) and 2) intent classification
   (small fast model) run IN PARALLEL via asyncio.gather — never sequentially — and abort the
   turn on guardrail failure. Their latencies are recorded as separate stages.
3) routing: faq -> FAQ agent (public); account_info -> login prompt if anonymous, else the
   account agent; action -> step-up invite if not strong, else the action agent; human_request
   and out_of_scope get direct answers. (The "action" route is the seam prompt 3b fills.)
4) output checks on the answer (local by default; optional LLM judge behind OUTPUT_CHECK_ENABLED).

The model proposes, the application decides: the agents only call the tools in
api.agents.tools, whose schemas carry no identity parameter, and all state changes wait for
the dedicated confirm endpoint."""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from env.assistant import env as assistant_env
from mistralai import agents
from pydantic import BaseModel, Field
from utils.mistral import mistral_client

from api.agents import deps as agent_deps
from api.agents.factory import make_account_agent, make_action_agent, make_faq_agent
from api.agents.inputs import BankSessionInput
from api.auth.service import SessionContext
from api.bank.protocol import Bank
from api.classify import classify_intent
from api.guardrails import pattern_check, run_input_guardrails
from api.kb.retriever import Embedder
from api.output_checks import local_output_checks, model_output_check

# Canned answers are bilingual: the chat request carries the UI language (FR/EN toggle), so every
# fixed message follows it — same for the agent's answer via apply_lang() below.
REFUSAL_TEXT = (
    "Je ne peux pas répondre à cette demande. Si elle concerne votre compte, un conseiller peut vous aider : "
    "vous pouvez à tout moment demander à parler à un humain."
)
LOGIN_PROMPT_TEXT = (
    "Cette question porte sur vos données de compte : veuillez d'abord vous connecter (démo : un des 3 clients fictifs)."
)
STEP_UP_TEXT = (
    "Cette action est protégée : une authentification forte est requise. Lancez la montée en sécurité "
    "(réception d'un code à usage unique) puis confirmez l'action proposée."
)
ADVISOR_TEXT = (
    "Vous pouvez joindre un conseiller par téléphone du lundi au vendredi de 8h00 à 19h00 et le samedi de 9h00 à 17h00, "
    "ou via la messagerie sécurisée de votre espace client (réponse sous 24h ouvrées). "
    "(source: knowledge/fr/joindre-conseiller.md)"
)
OUT_OF_SCOPE_TEXT = (
    "Je suis l'assistant d'une banque de démonstration : je réponds aux questions bancaires publiques et à celles "
    "portant sur votre compte. Pour autre chose, un conseiller peut vous aider."
)
STAGE_ERROR_TEXT = (
    "Je rencontre un problème technique, je peux vous mettre en relation avec un conseiller."
)
ACTIONS_DISABLED_TEXT = (
    "Cette opération est momentanément indisponible ; un conseiller peut vous aider."
)

_TEXTS_EN = {
    "refusal": (
        "I can't help with that request. If it concerns your account, an advisor can help you: "
        "you can ask to talk to a human at any time."
    ),
    "login_prompt": (
        "This question is about your account data: please sign in first (demo: one of the 3 fictional customers)."
    ),
    "step_up": (
        "This action is protected: strong authentication is required. Start the step-up "
        "(one-time code) and then confirm the proposed action."
    ),
    "advisor": (
        "You can reach an advisor by phone Monday to Friday from 8:00 AM to 7:00 PM and on Saturday from 9:00 AM to 5:00 PM, "
        "or via the secure messaging of your online banking area (reply within 24 business hours). "
        "(source: knowledge/en/contact-advisor.md)"
    ),
    "out_of_scope": (
        "I am the assistant of a demo bank: I answer public banking questions and questions about your account. "
        "For anything else, an advisor can help you."
    ),
    "stage_error": (
        "I'm experiencing a technical issue, I can put you in touch with an advisor."
    ),
    "actions_disabled": (
        "This operation is temporarily unavailable; an advisor can help you."
    ),
}


def canned(key: str, lang: str | None, fr_text: str) -> str:
    """Pick the canned answer in the UI language (defaults to French)."""
    if lang == "en":
        return _TEXTS_EN[key]
    return fr_text


class StageTiming(BaseModel):
    stage: str
    ms: float


class TurnResult(BaseModel):
    correlation_id: str
    intent: str
    answer: str
    sources: list[dict] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)
    pending_action: dict | None = None
    timings: list[StageTiming] = Field(default_factory=list)
    guardrails: dict = Field(default_factory=dict)
    output_issues: list[str] = Field(default_factory=list)
    auth_level: str = "anonymous"
    refused: bool = False
    needs_login: bool = False
    needs_step_up: bool = False
    human_offer: bool = False
    error: str | None = None
    # Recorded with the turn (see api.turnlog): model from the agent config, tokens only when
    # the API returns usage, else null.
    model: str | None = None
    tokens: dict | None = None
    handoff_id: str | None = None  # set by the chat route when a handoff request was created
    handoff_reason: str | None = None  # explicit handoff reason override (e.g. actions_disabled)


@dataclass
class OrchestratorDeps:
    """Injectable stage implementations — tests pass fakes (scripted model, sleeping
    moderation) to prove parallelism; `bank`/`embedder` back the tools' default RunDeps."""

    client: Any = None
    bank: Bank | None = None
    embedder: Embedder | None = None
    moderation_fn: Callable[[str], Awaitable[dict]] | None = None
    classify_fn: Callable[[str], Awaitable[str]] | None = None
    agent_model: Any = None  # agents.testing.ScriptedModel in tests
    run_deps: agent_deps.RunDeps | None = None
    # Kill switch for state-changing actions; reads the live runtime flags when wired to a request.
    actions_enabled_fn: Callable[[], bool] | None = None


class _Timer:
    def __init__(self) -> None:
        self.timings: list[StageTiming] = []

    def record(self, stage: str, start: float) -> None:
        self.timings.append(StageTiming(stage=stage, ms=round((time.perf_counter() - start) * 1000, 1)))


def cap_sources(sources: list[dict], k: int) -> list[dict]:
    """Dedupe by (source, chunk) in first-seen order, then cap at k: the UI shows at most k
    sources (collapsed by default) and the answer cites them inline as [n] in the same order."""
    seen: set = set()
    out: list[dict] = []
    for s in sources:
        key = (s.get("source"), s.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= k:
            break
    return out


async def _run_agent(agent, message: str, session_input: BankSessionInput, emit) -> tuple[str, list[dict], str | None, dict | None]:
    """Run one agent turn, streaming text deltas through `emit`. Returns (answer, tool_calls,
    model, tokens) — model/tokens are None when the SDK/API does not provide them."""

    async def on_event(event) -> None:
        if isinstance(event, agents.TextDelta):
            if emit is not None:
                await emit({"type": "delta", "text": event.text})

    session = await agent.start_session(session_inputs={BankSessionInput.input_id: session_input})
    try:
        state = await session.run(message, on_event=on_event)
    finally:
        await session.cancel()
    if isinstance(state, agents.Completed):
        tool_calls = [{"name": c.name, "arguments": c.arguments} for c in state.tool_calls]
        usage = getattr(state, "usage", None)
        tokens = usage.model_dump(mode="json") if hasattr(usage, "model_dump") else (dict(usage) if isinstance(usage, dict) else None)
        model = getattr(state, "model", None) or getattr(agent, "model", None)
        return state.text, tool_calls, (str(model) if model else None), tokens
    return (getattr(state, "text", "") or ""), [], None, None


def apply_lang(message: str, lang: str | None) -> str:
    """UI language toggle: when set, ask the agent explicitly to answer in that language."""
    if lang == "en":
        return message + "\n\n(The customer asked to be answered in English.)"
    if lang == "fr":
        return message + "\n\n(Le client demande une réponse en français.)"
    return message


async def run_turn(
    message: str,
    ctx: SessionContext | None,
    *,
    orch: OrchestratorDeps,
    emit: Callable[[dict], Awaitable[None]] | None = None,
    lang: str | None = None,
) -> TurnResult:
    correlation_id = uuid.uuid4().hex
    timer = _Timer()
    result = TurnResult(
        correlation_id=correlation_id,
        intent="unknown",
        answer="",
        auth_level=ctx.level if ctx else "anonymous",
    )

    client = orch.client or mistral_client()
    moderation_fn = orch.moderation_fn
    if moderation_fn is None:
        async def moderation_fn(text: str) -> dict:  # type: ignore[no-redef]
            from api.guardrails import moderate_text

            return await moderate_text(client, text)

    classify_fn = orch.classify_fn
    if classify_fn is None:
        async def classify_fn(text: str) -> str:  # type: ignore[no-redef]
            return await classify_intent(client, text)

    try:
        # --- stages 1 + 2 in parallel ----------------------------------------------
        group_start = time.perf_counter()

        async def timed_moderation() -> dict:
            start = time.perf_counter()
            try:
                return await moderation_fn(message)
            finally:
                timer.record("moderation", start)

        async def timed_classify() -> str:
            start = time.perf_counter()
            try:
                return await classify_fn(message)
            finally:
                timer.record("classification", start)

        moderation, intent = await asyncio.gather(timed_moderation(), timed_classify())
        timer.record("guardrails+classification (parallel)", group_start)

        pattern_hit = pattern_check(message)
        result.guardrails = {"moderation": moderation, "pattern_hit": pattern_hit}
        result.intent = intent

        if not moderation.get("safe", True) or pattern_hit:
            # abort on guardrail failure: no agent call at all
            result.refused = True
            result.human_offer = True
            result.answer = canned("refusal", lang, REFUSAL_TEXT)
            await _audit_refusal(ctx, correlation_id, pattern_hit or "moderation")
            return result

        # --- stage 3: route ----------------------------------------------------------
        if orch.run_deps is not None:
            run_deps = orch.run_deps
        else:
            run_deps = agent_deps.RunDeps(
                session_maker=agent_deps.get_session_maker(),
                bank=orch.bank,  # type: ignore[arg-type]
                embedder=orch.embedder,  # type: ignore[arg-type]
            )
        collector = agent_deps.RunCollector()
        token = agent_deps.bind_run(run_deps, collector)
        try:
            session_input = BankSessionInput(
                customer_id=str(ctx.customer_id) if ctx and ctx.customer_id else None,
                session_id=str(ctx.session_id) if ctx else "anonymous",
                auth_level=ctx.level if ctx else "anonymous",
                correlation_id=correlation_id,
            )

            agent_message = apply_lang(message, lang)
            if intent == "faq":
                start = time.perf_counter()
                answer, tool_calls, model, tokens = await _run_agent(make_faq_agent(orch.agent_model), agent_message, session_input, emit)
                timer.record("agent_faq", start)
                result.model, result.tokens = model, tokens
            elif intent == "account_info":
                if ctx is None or ctx.level == "anonymous" or ctx.customer_id is None:
                    result.needs_login = True
                    result.answer = canned("login_prompt", lang, LOGIN_PROMPT_TEXT)
                    return result
                start = time.perf_counter()
                answer, tool_calls, model, tokens = await _run_agent(make_account_agent(orch.agent_model), agent_message, session_input, emit)
                timer.record("agent_account", start)
                result.model, result.tokens = model, tokens
            elif intent == "action":
                if ctx is None or ctx.level == "anonymous" or ctx.customer_id is None:
                    result.needs_login = True
                    result.answer = canned("login_prompt", lang, LOGIN_PROMPT_TEXT)
                    return result
                if ctx.level != "strong":
                    result.needs_step_up = True
                    result.human_offer = True
                    result.answer = canned("step_up", lang, STEP_UP_TEXT)
                    return result
                actions_on = orch.actions_enabled_fn() if orch.actions_enabled_fn is not None else assistant_env.actions_enabled
                if not actions_on:
                    # kill switch: NO action agent runs at all; FAQ and account info keep working
                    result.human_offer = True
                    result.handoff_reason = "actions_disabled"
                    result.answer = canned("actions_disabled", lang, ACTIONS_DISABLED_TEXT)
                    return result
                start = time.perf_counter()
                answer, tool_calls, model, tokens = await _run_agent(make_action_agent(orch.agent_model), agent_message, session_input, emit)
                timer.record("agent_action", start)
                result.model, result.tokens = model, tokens
            elif intent == "human_request":
                result.human_offer = True
                result.answer = canned("advisor", lang, ADVISOR_TEXT)
                return result
            else:  # out_of_scope
                result.human_offer = True
                result.answer = canned("out_of_scope", lang, OUT_OF_SCOPE_TEXT)
                return result

            result.answer = answer
            result.tool_calls = tool_calls
            result.sources = cap_sources(collector.sources, assistant_env.kb_top_k)
            result.pending_action = collector.pending_action

            # --- stage 4: output checks ---------------------------------------------
            start = time.perf_counter()
            issues = local_output_checks(answer, tool_calls, collector.sources)
            if assistant_env.output_check_enabled:
                issues += await model_output_check(message, answer, client=client)
            timer.record("output_check", start)
            result.output_issues = issues
            return result
        finally:
            agent_deps.reset_run(token)
    except Exception as error:  # stage down (bank/model/moderation): neutral message + human offer
        result.error = type(error).__name__
        result.human_offer = True
        result.answer = canned("stage_error", lang, STAGE_ERROR_TEXT)
        return result
    finally:
        result.timings = timer.timings


async def _audit_refusal(ctx: SessionContext | None, correlation_id: str, reason: str) -> None:
    try:
        from api.audit.service import log_action

        await log_action(
            None,
            customer_id=ctx.customer_id if ctx else None,
            session_id=ctx.session_id if ctx else None,
            auth_level=ctx.level if ctx else "anonymous",
            action="guardrail_refusal",
            masked_args={"reason": reason},
            result="refused",
            correlation_id=correlation_id,
        )
    except Exception:
        pass  # audit must never break the turn


_ = run_input_guardrails  # re-exported for tests
