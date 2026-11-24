"""Intent classification with a small fast Mistral model. Runs in parallel with the input
guardrails in the orchestrator — latency is a first-class concern, so the two never queue."""

from env.assistant import env as assistant_env
from utils.mistral import mistral_client

INTENTS = ("faq", "account_info", "action", "human_request", "out_of_scope")

_SYSTEM = (
    "You classify one message of a retail-banking chatbot into exactly one label:\n"
    "- faq: GENERAL public product/FAQ question answerable from the knowledge base — procedures,\n"
    "  policies, limits, fees, refunds, disputes — e.g. \"quels sont les horaires d'ouverture des\n"
    "  agences ?\", \"quels sont les frais de tenue de compte ?\", \"quel est le plafond d'un virement\n"
    "  ?\", \"comment contester un prélèvement ?\", \"ma carte a été volée ou perdue, que faire ?\",\n"
    "  \"serai-je remboursé si je constate une fraude sur mon compte ?\", \"jusqu'à combien peut\n"
    "  aller mon découvert autorisé ?\".\n"
    "  These stay faq EVEN WHEN they mention \"mon\"/\"ma\": a question about a RULE, POLICY or LIMIT\n"
    "  (refund policy, ceilings, authorized overdraft, fees, dispute procedure) is faq; only a\n"
    "  question about the actual BALANCE or STATE of the customer's own account is account_info.\n"
    "- account_info: the customer asks about their OWN data or personal situation — the actual\n"
    "  balance, operations, card list, or own agency — e.g. \"mon solde\", \"mes opérations\",\n"
    "  \"montre-moi mes cartes\", \"à quelle heure ouvre MON agence ?\", \"combien ai-je sur mon\n"
    "  compte ?\", \"quel est le solde de mon livret épargne ?\". Asking for personal DATA means\n"
    "  authenticated data, never public.\n"
    "- action: the customer wants to DO a state-changing operation now (e.g. \"bloque ma carte\",\n"
    "  \"je veux verrouiller ma carte de crédit\"). Procedures such as \"que faire si ma carte est\n"
    "  volée ?\" are faq, not action.\n"
    "- human_request: the customer asks for a human advisor\n"
    "- out_of_scope: not banking-related at all\n"
    "Key distinction: \"ma carte a été volée, que faire ?\" = procedure (faq); \"montre-moi mes\n"
    "  cartes\" = personal data (account_info); \"bloque ma carte\" = operation (action).\n"
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
