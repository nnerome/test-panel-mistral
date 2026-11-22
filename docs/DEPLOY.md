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
