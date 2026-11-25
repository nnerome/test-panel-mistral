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

## Redéploiement 2026-11-23 15:22 UTC — tag `7a19b8a829e7-28f5799a` (run api `01a20900-9772-…`, `succeeded`; migration `68064a80683b` appliquée au boot, instance healthy 15:24)

- **Questions personnelles = authentification requise** : le classifieur route « à quelle heure ouvre MON agence ? » vers `account_info` (anonyme → invite de connexion, aucune réponse). Connecté, l'agent compte répond via le nouvel outil `get_my_agency_hours` (agence résolue depuis la ligne client, aucun paramètre d'identité dans le schéma). Migration `68064a80683b` : `customers.agency_id` + backfill au seed pour les bases existantes. Cas d'eval `acc-7` (connecté → outil appelé) et `acc-8` (anonyme → `needs_login`).
- **Mise en forme** : rendu markdown maison et sûr dans le chat (`apps/web/src/markdown.tsx`, aucun innerHTML : gras, italique, `code`, badges de citation [n], listes, paragraphes ; le HTML brut reste du texte). Tests `markdown.test.tsx`.
- **Boutons inline dans le chat** : « Recevoir un code SMS » directement dans le message de step-up, « Parler à un conseiller » dans le message d'offre de relais humain.
- Tests : 111 passed / 3 skipped (API), régression 27/27 (refus 4/4), web 34/34, build OK.

## Redéploiement 2026-11-23 15:33 UTC — tag `97849ff15da9-69bfed67` (runs `01a2090a-…`, `succeeded`, healthy 15:35)

- **Toggle FR/EN** dans le header du chat : `ChatRequest.lang` → l'orchestrateur ajoute au message de l'agent « answer in English / répondre en français » (`apply_lang`). Les questions anglaises récupèrent déjà les 3 pages EN de la KB (vérifié : « What are the transfer limits? » → `transfer-limits.md`). Cas d'eval `faq-10`. Tests : 113 passed API, régression 28/28, web 34/34.
- Rappel du comportement voulu : les questions **générales** restent publiques (FAQ anonyme) ; seules les questions **personnelles** (« mon agence », « mon solde »…) exigent la connexion. « Quels prêts proposez-vous ? » n'a pas de page dans la KB (20 fichiers fixés par le brief) → l'agent répond « je ne sais pas + conseiller », comportement prévu hors-KB.

## Redéploiement 2026-11-23 15:51 UTC — tag `6bb1d3424acc-8526b076` (web, `succeeded`, healthy 15:52)

- Le formulaire OTP (code + champ + Valider) est déplacé juste au-dessus du composer, toujours visible :
  le bouton inline « Recevoir un code SMS » fonctionnait (step-up → 200 dans les logs) mais le code
  apparaissait en haut du chat, hors écran après l'auto-scroll.

## Redéploiement 2026-11-23 16:00 UTC — tag `80ebe437ff23-383802b2` (web, `succeeded`, healthy 16:01)

- Après un login ou un step-up SMS réussi, le chat **renvoie automatiquement** le message qui avait
  déclenché l'invite d'auth (`pendingResume`) : la conversation reprend sans ressaisie.

## Redéploiement 2026-11-23 16:50 UTC — tag `297ce1e264d3-946cd4d8` (runs `01a20951-…`, `succeeded`)

- Nouveau `POST /api/demo/reset` (mode démo uniquement + en-tête client) : débloque toutes les cartes
  et supprime actions en attente, exécutions, ledger d'idempotence, OTP et audit. Bouton « Réinitialiser
  la BDD (démo) » dans le panneau « Espace démo ». Appliqué en prod via `X-Api-Key` (la gateway accepte la
  clé API en visiteur) : `cards_unlocked: 1` (carte d'Alice), 1 pending/exécution/lock event, 12 OTP,
  2 audit supprimés ; second appel idempotent (0 partout). Tests : 114 passed / 3 skipped.

## Déploiement 2026-11-24 21:24 UTC — commit `f31ed02` (runs api `01a20f71-4f6d-76ac-8871-8048268155f2`, web `01a20f71-4fef-74e7-82b7-60c74bda2b94`, `deployed`, healthy 21:25)

- Correctif **replay après TTL** (`81396f3` + test `8f08023`) : une action confirmée rejouée après expiration renvoie le résultat stocké (`executed=false`) au lieu d'être rétroactivement passée à `expired` + 409 ; une action jamais confirmée passée le TTL garde le code `action_expired`. Tests : `test_actions_flow.py` + `test_confirm_replay_after_expiry.py` = 9/9.
- Correctif **classifieur** (`f31ed02`) : l'alias `mistral-small-latest` a roulé vers un nouveau snapshot qui routait « contester un prélèvement », « carte volée », « fraude remboursée », « découvert autorisé » vers action/account_info (détecté par la régression : 4 échecs `cites`). Le prompt énonce maintenant la règle (question de règle/limite/procédure = faq même avec « mon » ; seule la donnée personnelle réelle = account_info) avec exemples concrets, et `classifier_model` est épinglé à `mistral-small-2603` (snapshot daté) pour la reproductibilité.
- Note : outils MCP Studio indisponibles dans cette session, donc pas de tag image serveur ; enregistré avec SHA git + runIds. Sondes prod (via `X-Api-Key`) : health 200 `mistral.configured=true, database.reachable=true` ; 401 `session_expired` hors auth (comportement gateway normal).

## Redéploiement 2026-11-24 21:30 UTC — commit `c00e522` (runs api `01a20f76-406d-750b-8e44-a23ed67c654c`, web `01a20f76-40ac-761a-a591-0310da877185`, `deployed`, healthy 21:30)

- Correctif **guardrails de modération** (`c00e522`) : sonde prod a montré que « Comment contester un prélèvement… » était **refusé** (catégorie `law=true` du modérateur, et l'ancienne règle bloquait sur n'importe quelle catégorie) alors que la régression locale (modération mockée) restait verte. Le blocage est maintenant une allowlist explicite (sexual, hate, violence, dangerous, criminal, selfharm, pii, jailbreaking) ; `law`/`financial`/`health` restent visibles dans `categories` mais passent — le hors-sujet est le job du classifieur. Vérifié contre l'API de modération live : contestation → safe, « fabriquer une bombe » → bloqué (criminal+dangerous), jailbreak → bloqué.
- Sondes prod après rollout : « contester un prélèvement » → `intent=faq, refused=false`, sources `[contester-prelevement.md, …]` ; « découvert autorisé » → faq + `decouvert-autorise.md` ; « à quelle heure ouvre mon agence ? » → `account_info, needs_login=true` (inchangé, conforme au brief) ; « bloque ma carte » → `action, needs_login=true`. Health 200. Tests : 74 passed (apps/api), 112 passed/3 skipped (workspace ciblé), régression **28/28** (refus 4/4).

## Déploiement 2026-11-25 09:05 UTC — commit `0a25e77` (4 fonctionnalités : feedback, métriques, kill switch, handoff) — runs api `01a211f2-5e17-742c-bbd7-197e24dd2f04`, web `01a211f2-5e2f-765a-b509-42b6be5e6589`, `deployed`, healthy 09:05

- Push GitHub `master:main` (`1e8f454..0a25e77`), arbre vérifié blob-identique côté remote (295 fichiers). Dépôt remis en **privé** après le push.
- `mistral deploy --from-disk --name bnp-assistant --json` → `ok:true`, `unsetEnv:[]`, URL inchangée. Migrations alembic appliquées au boot, « Instance is healthy ».
- Sondes prod (via `X-Api-Key`) : health 200 (`mistral.configured=true`, `database.reachable=true`) ; 401 `session_expired` sans clé (gateway) ; tour FAQ anonyme → SSE complet, `intent=faq`, stages `moderation/classification/agent_faq/output_check`, `handoff_id=null` ; `GET /api/metrics?window_minutes=60` → 200 `turns_total>=1`, `method=nearest-rank` (prouve que `record_turn` écrit en prod) ; « parler à un conseiller » → `intent=human_request`, `handoff_id` renseigné ; `GET /api/handoffs?status=open` → 1 demande, résumé sans PAN ; `GET /api/demo/feature-flags` → `actions_enabled:true`.
- Tests au moment du push : API 105 passed, packages 42 (db 16/3 skipped, cli 4, env 22), web 34/34, régression 28/28 (refus 4/4).

## Redéploiement 2026-11-25 09:18 UTC — commit `6fd2f49` (correctif sécurité scrub_secrets) — runs api `01a211ff-2b1b-7511-b929-16d14d1d3db9`, web `01a211ff-2b29-7657-a014-92e03d6e5772`, `deployed`, healthy 09:18:32

- **Sonde prod a trouvé un trou** : `scrub_secrets` ne masquait que les runs contigus de 13-19 chiffres ; un PAN tapé « 4970 1010 2020 3030 » (espaces/tirets/points) aurait été stocké en clair dans `feedback.comment` / excerpts. Correctif : toute run maximale de chiffres (séparateurs espace/point/tiret autorisés) contenant ≥13 chiffres est masquée ; timestamps, UUID, téléphones, montants restent lisibles. Tests : 9 tests unitaires `test_masking.py` + cas PAN espacé dans `test_feedback.py`.
- Suite complète verte avant push : API 105 passed, packages 42, web 34/34, régression 28/28.
- Push `0a25e77..6fd2f49` → main. Sondes prod après rollout (7/7 OK) : health 200 ; login + tour `account_info` ; `POST /api/feedback` down avec PAN contigu + espacé + à tirets → réponse `"cartes **** et **** et **** refusées"` (aucune fuite) ; `GET /api/feedback/recent?rating=down` → 1 ligne, commentaire scrubbé ; `GET /api/metrics?window_minutes=60` → `turns_total=6`, `downvotes=1/2`, `method=nearest-rank` ; `GET /api/demo/feature-flags` → `actions_enabled:true` ; `GET /api/handoffs?status=open` → 1 demande, aucune fuite de chiffres.
