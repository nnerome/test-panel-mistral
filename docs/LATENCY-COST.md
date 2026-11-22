# Budget de latence et de coût par tour

Tarifs issus de la page de pricing Mistral (docs.mistral.ai/inference/pricing, consultée via les
outils MCP) : `mistral-small-2603` (Small 4) **input $0.15/M, output $0.6/M** ; `mistral-large-4`
**input $0.7/M (cached $0.07/M), output $2.1/M** ; `mistral-embed` **$0.1/M** ; `mistral-moderation-2603`
**gratuit**.

## Budget de latence par chemin (p50 / p95 estimés, modèle réel)

Mesuré localement hors modèle (doublons déterministes) dans `docs/REGRESSION-RESULTS.txt` ;
les étages modèle sont estimés à partir des caractéristiques publiées des modèles.

| Chemin | moderation (free) | classification (small) | parallèle vs séquentiel | agent (large-4, 1-2 appels d'outils) | output check (local) | **total p50 / p95** |
|--------|------------------:|-----------------------:|------------------------:|-------------------------------------:|---------------------:|--------------------:|
| FAQ | ~150 / 300 ms | ~200 / 400 ms | **~400 / 500 ms** (gagné vs ~350 ms séquentiel en plus) | ~1.2 / 2.5 s (avec retrieval + réponse) | ~0 / 1 ms | **~1.6 / 3.0 s** |
| Question compte (auth) | idem | idem | idem | ~0.8 / 1.8 s (outil read-only, pas de retrieval) | ~0 | **~1.2 / 2.3 s** |
| Action (bloquer carte) | idem | idem | idem | ~1.0 / 2.0 s (propose uniquement ; l'exécution est hors tour, au confirm) | ~0 | **~1.4 / 2.5 s** |
| Refus (guardrail) | ~150 / 300 ms | ~200 / 400 ms (parallèle) | — | **aucun appel agent** | — | **~0.4 / 0.5 s** |

Le point clé défendable : **modération et classification tournent en parallèle**
(`asyncio.gather` dans `orchestrator.run_turn`, timings séparés `moderation` / `classification` /
`guardrails+classification (parallel)`), testé par `test_moderation_and_classification_run_in_parallel_with_separate_timings`
(2 × 250 ms simulés → groupe < 400 ms). Le refus par guardrail **ne coûte aucun appel agent**.

## Coût par tour (ordre de grandeur)

Hypothèses : message ~100 tokens ; system + passages KB ~1 500 tokens en entrée agent ;
réponse ~200 tokens ; classification ~150/10 ; modération ~100 tokens entrée, **gratuit** ;
retrieval : 1 embedding de requête (~100 tokens × $0.1/M ≈ $0.00001, négligeable).

| Chemin | Modèle agent | coût entrée | coût sortie | **total/tour** |
|--------|--------------|------------:|------------:|---------------:|
| FAQ / compte / action | `mistral-large-4` | 1 600 × $0.7/M ≈ $0.00112 | 200 × $2.1/M ≈ $0.00042 | **≈ $0.0015** (~0.15 ¢) |
| idem | `mistral-small-latest` (`ASSISTANT_MODEL=mistral-small-latest`) | 1 600 × $0.15/M ≈ $0.00024 | 200 × $0.6/M ≈ $0.00012 | **≈ $0.0004** (~0.04 ¢) |
| + classification (small) | | 150 × $0.15/M + 10 × $0.6/M | | ≈ $0.00003 |
| + output check LLM (optionnel, OFF par défaut) | small | ~$0.00003 | | ≈ $0.00006 |

Soit **~10⁻³ $ par tour** avec large-4, ~4×10⁻⁴ $ avec small-latest. À 1 M de tours/mois :
~1 500 $ (large-4) vs ~400 $ (small-latest) — ordres de grandeur à affiner avec le trafic réel.

## Les 3 gains les moins chers (et l'étage qu'ils touchent)

1. **Classifieur sur le plus petit modèle + consignes courtes** — étage `classification`
   (~200-400 ms et ~$0.00003/tour) : déjà en place (`mistral-small-latest`, `max_tokens=16`,
   température 0). Win : garder ce réglage, ne jamais classifiez avec le gros modèle.
2. **Guardrails en parallèle de la classification, jamais en série** — étages
   `moderation` + `classification` : divise par ~2 le pré-agent (déjà en place, prouvé par test).
   Win futur : cache de la modération côté gateway si le même texte revient.
3. **Sortie structurée courte + streaming des deltas** — étage `agent_*` : TTFT ressenti bas
   même si le tour total est long ; et `OUTPUT_CHECK_ENABLED=false` par défaut évite un appel
   modèle entier par tour (l'étage `output_check` local est gratuit). Win : activer le
   *prompt caching* sur le préfixe system+KB de l'agent FAQ (cached input $0.07/M sur large-4,
   soit ~10× moins cher sur la part système des entrées).
