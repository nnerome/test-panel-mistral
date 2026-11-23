# Revue sécurité du prototype (faite après les prompts 3/4)

## Findings, ranked

| # | Sévérité | Finding | Statut |
|---|----------|---------|--------|
| 1 | haute | Le endpoint de confirmation devait rejeter un rejeu comme un conflit (409) au lieu de retourner le résultat stocké — un double-clic aurait pu sembler "échouer" alors que l'action est exécutée, poussant à réessayer. | **corrigé** : la vérification d'exécution (table `card_lock_executions`, PK = id d'action) passe AVANT le check de statut ; rejeu = résultat stocké, `executed=false`, jamais de seconde exécution (test `test_concurrent_double_confirm_executes_once` + rejeu). |
| 2 | moyenne | Les exceptions internes pouvaient remonter en clair dans l'événement SSE `error` (fuite potentielle de détails internes). | **corrigé** : message générique côté client, trace complète dans les logs serveur (`routers/api/chat.py`). |
| 3 | moyenne | Cookie de session sans attribut `Secure` en dur ; endpoints démo (`/api/demo/*`, code OTP affiché) actifs par défaut. | **corrigé** : `SESSION_COOKIE_SECURE` (false en local http, true derrière TLS) + `DEMO_MODE` (à false, `/api/demo/*` répond 404 et le code OTP n'est plus renvoyé ; test `test_demo_endpoints_404_when_demo_mode_off`). |
| 4 | moyenne (par design) | Le header custom anti-CSRF (`X-Bnp-Client`) est une valeur statique lisible dans le bundle JS : il bloque les formulaires cross-site (qui ne peuvent pas poser d'en-tête custom) mais pas un attaquant same-origin/XSS. Cookie `SameSite=Strict` en complément. | documenté, hors périmètre prototype (vrai cycle de tokens CSRF). |
| 5 | faible | Pas de rate limiting sur login / OTP / confirm ; pas de verrouillage de compte. L'OTP a déjà max 5 tentatives + TTL 5 min + usage unique. | hors périmètre prototype (listé ci-dessous). |
| 6 | faible | `GET /api/demo/customers` expose e-mails + indice de mot de passe (démo). | OK en démo ; éteint par `DEMO_MODE=false`. |
| 7 | info | Injection via documents récupérés : l'entrée empoisonnée de `knowledge/fr/remboursement-fraude.md` est traitée comme données non fiables (instructions de l'agent + contrôle de sortie qui flague toute reprise de phrasé d'injection) ; test `test_poisoned_kb_entry_is_retrieved_but_never_obeyed`. | couvert. |
| 8 | info | Ownership sur chaque lecture/écriture, 404 uniforme (pas de fuite d'existence) ; PAN jamais sélectionné par les accesseurs (test sur logs `echo=debug`) ; audit scrubbé des séquences 13-19 chiffres. | couvert par tests. |
| 9 | info | En cas d'indisponibilité de l'API de modération, le tour échoue en « fermé » (pas de réponse sans guardrail) + offre de relais humain. Choix volontaire : fail-closed. | documenté. |

## Ce qui est explicitement HORS périmètre du prototype (à dire à l'oral)

Rate limiting, verrouillage de compte, cycle de vie réel des tokens CSRF, rotation des secrets,
KDF réelle pour les mots de passe (démo : SHA-256), TLS/gestion des certificats, hébergement des
données (UE), journalisation d'audit immuable (WORM), tests d'intrusion, revue de dépendances.

## Les 3 corrections en deux lignes chacune

1. **Idempotence avant statut** (`actions/service.py`) : un rejeu de confirm lit d'abord la table
   d'exécution (UNIQUE sur l'id d'action) et renvoie le résultat stocké ; le 409 ne concerne plus
   que les actions annulées/expirées. Double exécution impossible, même en double-clic concurrent.
2. **Plus de fuite d'erreurs au client** (`routers/api/chat.py`) : l'événement SSE `error` dit
   « internal error » ; la trace complète part dans les logs serveur uniquement.
3. **Mode démo commutable + cookie Secure** (`env/assistant.py`, `routers/api/demo.py`,
   `routers/api/auth.py`, `routers/api/chat.py`) : `DEMO_MODE=false` éteint `/api/demo/*` et
   l'affichage du code OTP ; `SESSION_COOKIE_SECURE=true` en prod pose `Secure` sur le cookie.

4. **Double transport du token de session** (`auth/service.py`, `auth/dependencies.py`, `routers/api/auth.py`, `routers/api/chat.py`, web `index.tsx`) : le login renvoie le token dans le corps ET pose le cookie `bnp_session` ; le SPA le renvoie en en-tête `X-Bnp-Session` à chaque appel. Motif : déployée derrière la gateway Studio, le `Set-Cookie` du module peut ne pas atteindre le navigateur (la gateway gère les cookies d'auth du domaine — constaté en prod : login 200 mais session restait anonyme). En local le cookie seul suffit. La posture CSRF ne change pas : `X-Bnp-Client` reste exigé sur les endpoints à état, et un formulaire cross-site ne peut poser ni l'un ni l'autre en-tête custom. Test : `test_session_token_header_works_without_cookie`.
