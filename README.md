# bnp-assistant — prototype d'assistant bancaire (démo entretien, données 100 % fictives)

Prototype « production-minded » d'un chatbot bancaire de détail, construit sur le scaffold
`mistral init --preset app` (TanStack Start web + FastAPI api + Postgres managé + worker), avec
**uniquement la capacité `core`** : logs locaux, timings par étage dans chaque réponse `/api/chat`,
runner de régression local. Rien ne dépend du Trace Explorer Studio (Observability/Evaluations
sont Enterprise-tier et ne sont pas supposés disponibles).

Deux flux de la consigne : **FAQ publique ancrée** dans une base de connaissance, et **action
avec confirmation** (bloquer une carte), les deux derrière une orchestration par tour tracée et
temporisée. L'intégration aux systèmes existants, le plan projet et l'hébergement (apps cloud
Mistral vs agents/workflows chez la banque) sont volontairement hors prototype — voir le pré-read.

## Lancer en local

```bash
mistral login                      # la session alimente la gateway locale `mistral dev`
# OU exporter MISTRAL_API_KEY dans le shell qui lance dev (la clé du .env n'alimente que les modules)
mistral dev                        # web sur :3001, api sur :3000, proxy /api -> :3000
```

Sans Docker (la base ne démarre pas), pointez `DATABASE_URL` vers tout Postgres 16+ local, ex. :
`export DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost:5432/postgres'`, puis
`bunx nx run db:migrate` (les migrations sont dans `packages/py/db/src/db/migrations/versions/`).

Tests (nécessitent un Postgres atteignable via `DATABASE_URL`) :

```bash
DATABASE_URL='...' bash tools/uv.sh run --no-sync pytest apps/api/tests -q
DATABASE_URL='...' bash tools/uv.sh run --no-sync python evals/run_regression.py   # suite de régression (smoke test)
```

Script de démo live (6 conversations) : **DEMO.md**. Déploiement (préparé, non exécuté ici) :
**docs/DEPLOY.md**. Diagramme de séquence du blocage de carte : **docs/lock-card-flow.mmd**.
Exemple de stream SSE complet : **docs/STREAM-EXAMPLE.txt**.

## Les deux couches d'authentification (ne jamais les confondre)

1. **La connexion Studio** (`mistral login`) ne sert qu'à **qui peut ouvrir l'app déployée**
   (contrôle d'accès à la démo) et alimente la gateway locale en dev.
2. **Le login « client » fictif** (3 comptes de démo, mot de passe `demo1234`) simule
   **l'authentification bancaire** : session serveur, niveaux `anonymous / authenticated / strong`,
   montée en sécurité par code à usage unique. C'est une couche applicative, indépendante de la
   première.

## Principes de conception (ce qu'on défend à l'oral)

- **Le modèle propose, l'application décide.** Les outils des agents (`api/agents/tools.py`)
  n'ont **aucun paramètre d'identité** dans leur schéma : l'identité du client arrive uniquement
  via un *session input* du SDK (`BankSessionInput`, invisible du modèle), et les libellés masqués
  (« carte **** 9012 ») sont résolus côté serveur dans les cartes de la session.
- **Ownership vérifié serveur-side partout** (`api/bank/ownership.py`) : lectures comme écritures,
  404 (pas 403) pour ne pas trahir l'existence d'un objet d'un autre client.
- **Toute action à effet de bord** exige : auth forte + confirmation explicite (clic sur
  Confirmer, jamais produite par le modèle) + action pendante (UUID, liée à la session, TTL 5 min)
  + **idempotence** (clé primaire = id d'action dans la table d'exécution + résultat stocké +
  contrainte UNIQUE côté adaptateur) + **audit**.
- **Masquage à la frontière adaptateur** : les PAN complets (fictifs) restent en base ; aucun
  accesseur ne les sélectionne même (test : aucun PAN dans les logs de requêtes `echo=debug`).
- **Guardrails à chaque entrée** (modération Mistral `mistral-moderation-2603`, gratuite, +
  patterns d'injection) **en parallèle** de la classification d'intention (petit modèle) — jamais
  en séquence ; timings séparés par étage. Contrôles de sortie à chaque réponse (local et gratuit
  par défaut ; juge LLM optionnel derrière `OUTPUT_CHECK_ENABLED`).
- **Relais humain toujours possible** : bouton dédié + offre automatique sur erreur bancaire ou
  cas hors périmètre.
- **Systèmes legacy derrière un Protocol** (`api/bank/protocol.py`) : `MockBank` est remplaçable
  sans toucher aux agents ; flags de latence/panne (`BANK_LATENCY_MS`, `BANK_FAILURE_RATE` ou
  toggles UI) pour la démo.
- **Honnêteté des evals** : `evals/` est une **suite de régression (smoke test), PAS une mesure
  d'accuracy** — voir « Ce que cette suite ne prouve pas ».

## Ce que cette suite de régression ne prouve PAS

- 25 cas, échantillon minuscule : aucune signification statistique, aucune mesure d'accuracy.
- Pas de red-teaming adversarial systématique (les 4 cas d'injection couvrent des patterns
  connus, pas une exploration).
- Pas de monitoring de dérive du modèle (model drift) : les poids changent, la suite non.
- Sans `MISTRAL_API_KEY`, les étages modèle sont des doublons déterministes
  (`agents.testing.ScriptedModel`) : la suite vérifie alors le câblage (guardrails, routage,
  schémas d'outils, ownership, idempotence), pas la qualité du modèle. Avec la clé, le
  classifieur réel tourne et son label est comparé à l'attendu.
- Données 100 % fictives ; aucune donnée réelle n'a été utilisée ni testée.

## Arborescence clé

```
apps/api/src/api/
  bank/        Protocol Bank + MockBank (Postgres), ownership, seed (données fictives)
  auth/        sessions serveur, niveaux, OTP à usage unique, dépendances FastAPI
  actions/     confirm_action : checks ordonnés + idempotence + audit
  agents/      tools sans paramètre d'identité, factory des 3 agents (FAQ / compte / action)
  kb/          indexation + retrieval de knowledge/ (embeddings mistral-embed)
  guardrails.py, classify.py, output_checks.py, orchestrator.py   # le tour, étage par étage
  routers/api/ chat.py (SSE), auth.py, demo.py, actions/[id]/{route,confirm,cancel}.py
packages/py/db/src/db/   models/ + accessors/ (une table chacun), migrations alembic
knowledge/               base de connaissance fictive (README = avertissement), dont UNE entrée
                         empoisonnée (fr/remboursement-fraude.md) : fixture d'injection volontaire
apps/web/src/routes/index.tsx   page de chat frugale (aucune logique métier côté client)
evals/                   conversations.jsonl (25 cas) + run_regression.py (smoke test)
docs/                    DEPLOY.md, lock-card-flow.mmd, SECURITY-REVIEW.md, LATENCY-COST.md,
                         STREAM-EXAMPLE.txt, REGRESSION-RESULTS.txt
```

## Choix de retrieval (et l'alternative rejetée)

La doc Mistral recommande une **Library** (document search) pour une KB de cette taille. Le
prototype utilise à la place des **embeddings `mistral-embed` + cosine dans le Postgres de l'app**
(`api/kb/`), parce qu'une Library Studio exige un provisioning console + partage de workspace et
est impossible à exercer en test local ; l'app reste ainsi auto-contenue et déployable telle
quelle. Alternative rejetée documentée ici ; en production, la Library + outil `document_library`
est le chemin recommandé (pré-read).
