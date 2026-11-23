# Déploiement (préparé, NON exécuté depuis ce poste)

Le prototype est conçu pour tourner avec uniquement la capacité `core` : logs locaux, table de
timings par tour dans la réponse `/api/chat`, runner de régression local. **Observability /
Evaluations (Trace Explorer Studio) ne sont PAS supposés disponibles** — ne rien y fonder.

## Prérequis

- `mistral login` (la session browser alimente la gateway locale et le déploiement ; une clé
  `MISTRAL_API_KEY` exportée dans le shell qui lance `mistral dev` fait de même pour la gateway
  locale — la clé posée dans le `.env` de l'app n'alimente que les modules eux-mêmes).
- Un remote git `origin` vers un dépôt que vous contrôlez (le déploiement build le **commit
  poussé**, pas l'arbre de travail).
- Dockerfiles déjà commités (`deploy/docker/Dockerfile.api`, `Dockerfile.web`) — c'est le cas.

## Checklist

1. Renseigner les valeurs de production dans Studio (Settings / Secrets Manager), jamais dans git :
   - secret `MISTRAL_API_KEY` (workspace secret ; le code le lit via `env.mistral` qui tombe
     sur le Secrets Manager quand `MISTRAL_SECRETS_ENABLED=true`) ;
   - éventuellement `ASSISTANT_MODEL`, `CLASSIFIER_MODEL`, `OUTPUT_CHECK_ENABLED` (déclarés dans
     `.env.example`, valeurs par défaut dans `packages/py/env/src/env/assistant.py`).
2. `git add -A && git commit -m "..." && git push origin <branche>` — arbre propre, y compris
   les fichiers non suivis (`knowledge/`, `evals/`, `docs/`).
3. Depuis la racine de l'app : `mistral deploy --organization <org-id> --name bnp-assistant`
   (ajouter `--workspace <id>` s'il y en a plusieurs ; `--json` hors terminal).
   Le premier deploy crée l'app, build chaque module, déploie en `production` et crée la base
   Postgres managée (les `POSTGRES_*` injectés alimentent `DATABASE_URL` via `env.db`).
4. Le premier deploy écrit un binding `deployment` dans `mistral.json` **dès que l'app existe**,
   même si le build échoue ensuite : le committer et le push (`mistral deploy -y` le fait) pour
   que les déploiements suivants ciblent la même app.
5. Suivre le deploy : `mistral apps modules` puis, côté Studio/MCP, `list_apps` → `get_app`
   (ids des modules, environnements, URLs publiques, version par module), `list_app_deploy_runs`
   / `get_app_deploy_run` jusqu'à sortie de `pending`/`running` ; en cas d'échec, `get_app_logs`
   avec `module_id` (build : `order=asc`) ; logs runtime du module, et logs gateway sans
   `module_id` pour les problèmes de login/routing.
6. Vérifier l'app déployée : ouvrir l'URL publique, se connecter (Studio) avec un compte
   autorisé, rejouer les 6 conversations de DEMO.md, **y compris les appels web → api** en
   environnement déployé.
7. Visibilité : une App Studio n'est atteignable que par les comptes **autorisés par votre
   organisation**. Vérifier dans Studio (app → Settings/visibility, ou `get_app`) qui peut
   réellement ouvrir l'URL ; options : restreindre à des membres nommés, ou laisser au niveau
   workspace selon la politique. **Les intervieweurs peuvent ne pas avoir accès à l'URL** :
   la démo de référence reste `mistral dev` en partage d'écran + la vidéo de 3 min + captures.
8. (Optionnel) publier dans le catalogue d'apps Vibe : `publish_app` (puis `unpublish_app`) —
   l'app reste accessible à son URL dans les deux cas.

## Ce qui reste hors périmètre prototype (à dire à l'oral)

Rate limiting, verrouillage de compte, cycle de vie réel des tokens CSRF (ici : en-tête custom
fixe + cookie SameSite=Strict), rotation des secrets, vraie KDF pour les mots de passe (démo :
SHA-256), hébergement des données hors UE, etc.

## Déploiement effectué (2026-11-23, depuis le bac à sable, `--from-disk` + clé API)

- App **bnp-assistant** (`01a20778-ff40-7353-a08b-b6280787a837`), orga « Perso », workspace « Default Workspace », environnement `production`.
- URL : https://432ce56e-bnp-assistant-productio-91f5642c-49e7-41f9-9a-1dd862ea.apps.mistral.run
- Studio : https://console.mistral.ai/apps/01a20778-ff40-7353-a08b-b6280787a837 (visibilité actuelle : `workspace`)
- Modules déployés (run 1, tag `1df4de790b17-756e6301`, statut `succeeded`) : `web` (`01a20779-0148-…`, route `/`), `api` (`01a20779-00ce-…`, route `/api`), `postgres` managé (`01a20779-0036-…`) — migration `a5bcbdadb361` appliquée au démarrage, instance api « healthy ».
- Binding `deployment` commité dans `mistral.json` (commit local ; à pousser depuis une machine ayant accès au dépôt GitHub).
- **Fait le 2026-11-23 08:26 UTC** : secret `MISTRAL_API_KEY` ajouté dans Studio (visible par nom uniquement dans `get_app` sur les modules `api` et `web`), puis redéploiement des deux modules (`redeploy_app_module`, même tag `1df4de790b17-756e6301`) : runs `01a20783-a205-…` (api) et `01a20783-a2bb-…` (web) passés à `succeeded` à 08:28 UTC ; nouvelles instances « healthy », aucune erreur au démarrage, migration déjà à jour. Reste : vérifier la visibilité (qui peut ouvrir l'URL) et rejouer les 6 conversations de DEMO.md en étant connecté à Studio (`/api/health` doit alors montrer `mistral.configured=true`).
- **Redéploiement 2026-11-23 11:21 UTC** (`mistral deploy --from-disk`, nouveau tag `26a9173ff04a-360da0de`, runs `01a20824-0139-…` web et `01a20824-012c-…` api → `succeeded`) : nouveau design system « banque fictive » dans le module web (tokens `brand`/`ink` dans `apps/web/src/index.css`, page chat restylée, favicon démo, `APP_NAME` = « BNP Paribas · Assistant (démo fictive) » dans `.env` non commité) ; `unsetEnv` vide au deploy. Nouvelles instances healthy à 11:23 UTC, anciennes arrêtées proprement. Ouvrir l'URL dans Safari (Chrome bloque via une extension locale) en étant connecté à Studio, forcer le rechargement (Ctrl+F5) pour vider le cache de l'ancien bundle.
- Sonde non authentifiée de l'URL → `401 session_expired` (gateway) : l'app répond et n'est accessible qu'aux comptes autorisés par l'orga.

## Redéploiement 2026-11-23 13:59 UTC — tag `54660552121a-d0e668c6` (runs `01a208b4-0671-…` api / `01a208b4-0661-…` web, `succeeded`)

Corrections constatées en prod (login qui restait anonyme, latence FAQ 20-60 s, liste de sources interminable) :
- **Session par en-tête `X-Bnp-Session`** en plus du cookie : la gateway Studio possède les cookies d'auth du domaine et le `Set-Cookie` du module n'atteint pas le navigateur en déployé (login 200 mais `/api/auth/me` restait `anonymous`). Le login renvoie désormais le token dans le corps, le SPA le renvoie en en-tête à chaque appel. Test : `test_session_token_header_works_without_cookie`.
- **Latence FAQ** : agent FAQ sur `FAQ_MODEL=mistral-small-latest` (compte/action restent sur `ASSISTANT_MODEL`), consigne « un seul appel à `search_knowledge_base` », seed+index KB au démarrage (lifespan) et non à la première requête.
- **Sources** : dédoublonnées et plafonnées à `KB_TOP_K`=5 côté orchestrateur (`cap_sources`), repliées par défaut dans l'UI (« Sources (n) ▾ »), citées en ligne `[n]` dans la réponse.
- Tests : 109 passed / 3 skipped (API), 31/31 (web), build web OK.

## Redéploiement 2026-11-23 14:14 UTC — tag `5c133378bc31-b1af58fc` (run api `01a208c1-ba5d-…`, `succeeded`)

Correction constatée en prod : `POST /api/auth/logout` → **500 ForeignKeyViolationError** après un step-up
(`otp_codes`/`pending_actions`/`audit_entries` référencent `bank_sessions` sans cascade). Le logout
expire désormais la ligne (soft delete, `acc.sessions.expire`) au lieu de la supprimer — la piste d'audit
conserve la session et plus de 500. Test de régression : `test_logout_after_step_up_soft_expires_session`.
Le bouton SMS, lui, répondait déjà 200 côté serveur (le bandeau code s'affichait). Tests : 110 passed / 3 skipped.

## Redéploiement 2026-11-23 14:35 UTC — tag `36c22b98919e-e7a8766a` (runs `01a208d5-…`, `succeeded`, instance healthy 14:37)

- La carte d'action en attente disparaît maintenant après Confirmer/Annuler (statut posé sur le message,
  compte à rebours arrêté, ligne « ✓ Action confirmée » à la place).
- Le classifieur route « à quelle heure ouvre mon agence ? » vers `faq` (exemples explicites dans le
  prompt : les questions d'info publique formulées au possessif restent de la FAQ). Nouveau cas d'eval `faq-9`. Régression : 26/26.
