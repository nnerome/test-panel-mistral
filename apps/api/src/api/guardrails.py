"""Input guardrails: Mistral moderation + a cheap pattern check for known injection/jailbreak
phrasings. Both run inside the same stage (which the orchestrator runs in PARALLEL with intent
classification, never sequentially)."""

import re
from dataclasses import dataclass, field

from env.assistant import env as assistant_env
from utils.mistral import mistral_client

# Known injection / jailbreak phrasings, French and English, matched case-insensitively.
INJECTION_PATTERNS = [
    # "ignore" + any short run of qualifier words + the keyword ("ignore all your previous instructions")
    r"\bignore\b.{0,60}?\b(consignes|instructions|directives|rules|guidelines|policies)\b",
    r"\b(disregard|forget)\b.{0,60}?\b(consignes|instructions|directives|rules|guidelines|policies)\b",
    # cross-customer targeting, e.g. "block someone else's card" / "bloque la carte de quelqu'un d'autre"
    r"(someone else|another (?:customer|user|client|person))\s*'?s?\s*(card|account|carte|compte)",
    r"\b(carte|compte|account|card)\s+(de|d'|of)\s*(quelqu'un|un autre|une autre|someone else|another (?:customer|user|client|person))",
    r"oublie\s+(tes|vos)\s+(consignes|instructions)",
    r"ne\s+plus\s+suivre\s+(tes|vos)\s+consignes",
    r"tu\s+es\s+maintenant",
    r"you\s+are\s+now\s+(a|an|in)",
    r"system\s+prompt",
    r"r[ée]v[èe]le\s+(ton|ta|votre)\s+(prompt|instructions)",
    r"reveal\s+(your|the)\s+(system\s+)?prompt",
    r"INSTRUCTION\s+INTERNE",
    r"\bDAN\b\s+mode",
    r"jailbreak",
    r"act\s+as\s+if\s+you\s+had\s+no\s+restrictions",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def pattern_check(text: str) -> str | None:
    """Returns the matched pattern when the text looks like an injection attempt, else None."""
    for pattern in _COMPILED:
        if pattern.search(text):
            return pattern.pattern
    return None


# Moderation categories that hard-refuse a turn. `law`, `financial` and `health` are deliberately
# NOT blocking: for a retail-bank FAQ they fire on legitimate in-domain questions ("contester un
# prélèvement", "plafond d'un virement", "fraude") which the knowledge base answers — out-of-scope
# is the classifier's job. They stay visible in result.moderation.categories for observability.
# `pii` is special-cased below: the moderation model false-positives on benign questions such as
# "What is my balance?", so pii only blocks when the message actually contains a PAN-like digit
# run (the thing we mask everywhere else).
BLOCKING_MODERATION_CATEGORIES = frozenset(
    {
        "sexual",
        "hate_and_discrimination",
        "violence_and_threats",
        "dangerous",
        "criminal",
        "selfharm",
        "pii",
        "jailbreaking",
    }
)


@dataclass
class GuardrailResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    moderation: dict = field(default_factory=dict)
    pattern_hit: str | None = None


async def moderate_text(client, text: str, model: str | None = None) -> dict:
    """One call to the Mistral moderation API. Returns {'safe': bool, 'categories': {...}}.

    `mistral-moderation-2603` is free; results[i].categories maps category -> violated flag.
    """
    model = model or assistant_env.moderation_model
    response = await client.classifiers.moderate_async(model=model, inputs=[text])
    results = response.results or []
    categories: dict[str, bool] = {}
    for result in results:
        if result.categories:
            for name, violated in result.categories.items():
                categories[name] = bool(violated) or categories.get(name, False)
    from api.domain.masking import contains_pan_like

    blocking = sorted(
        c
        for c, v in categories.items()
        if v and c in BLOCKING_MODERATION_CATEGORIES and (c != "pii" or contains_pan_like(text))
    )
    return {"safe": not blocking, "categories": categories, "blocking": blocking}


async def run_input_guardrails(client=None, text: str = "", model: str | None = None) -> GuardrailResult:
    """Moderation + injection patterns. A moderation failure or a pattern hit refuses the turn."""
    client = client or mistral_client()
    moderation = await moderate_text(client, text, model)
    hit = pattern_check(text)
    reasons = []
    if not moderation["safe"]:
        reasons.append(f"moderation: {sorted(k for k, v in moderation['categories'].items() if v)}")
    if hit:
        reasons.append("injection_pattern")
    return GuardrailResult(passed=not reasons, reasons=reasons, moderation=moderation, pattern_hit=hit)
