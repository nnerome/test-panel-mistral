"""Intent classification with a small fast Mistral model. Runs in parallel with the input
guardrails in the orchestrator — latency is a first-class concern, so the two never queue."""

from env.assistant import env as assistant_env
from utils.mistral import mistral_client

INTENTS = ("faq", "account_info", "action", "human_request", "out_of_scope")

_SYSTEM = (
    "You classify one message of a retail-banking chatbot into exactly one label:\n"
    "- faq: GENERAL public product/FAQ question answerable from the knowledge base, e.g.\n"
    "  \"quels sont les horaires d'ouverture des agences ?\", \"quels sont les frais de tenue\n"
    "  de compte ?\", \"quel est le plafond d'un virement ?\"\n"
    "- account_info: anything about the customer's OWN situation or data, even when it looks\n"
    "  like a public topic — e.g. \"à quelle heure ouvre MON agence ?\", \"mon solde\", \"mes\n"
    "  cartes\", \"mes opérations\". Personal phrasing means authenticated data, never public.\n"
    "- action: the customer wants to DO something (e.g. lock a card)\n"
    "- human_request: the customer asks for a human advisor\n"
    "- out_of_scope: not banking-related at all\n"
    "Reply with only the label, nothing else."
)


async def classify_intent(client=None, message: str = "", model: str | None = None) -> str:
    client = client or mistral_client()
    model = model or assistant_env.classifier_model
    response = await client.chat.complete_async(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": message},
        ],
        temperature=0.0,
        max_tokens=16,
    )
    label = (response.choices[0].message.content or "").strip().lower()
    for intent in INTENTS:
        if intent in label:
            return intent
    return "faq"  # unknown labels fall back to the safest public route
