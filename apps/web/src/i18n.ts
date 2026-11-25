/**
 * Single source of truth for every user-facing string of the chat UI, in French and English.
 * The FR/EN toggle in the header switches `lang`, and the whole interface renders `TEXTS[lang]`.
 * The bank can reword everything here without touching the components.
 */

export type Lang = "fr" | "en";

const fr = {
  // header
  demoTag: "démo fictive — données inventées",
  langToggleTitle: "Langue de réponse",
  level: {
    anonymous: "anonyme",
    authenticated: "connecté",
    strong: "authentification forte",
  },
  signInPlaceholder: "Connexion client fictif…",
  smsButton: "Recevoir un code SMS",
  signOut: "Déconnexion",
  advisorButton: "Parler à un conseiller",
  advisorMessage: "Je veux parler à un conseiller",
  // chat
  emptyHint: "Posez une question publique (FAQ) ou connectez-vous pour gérer vos opérations courantes.",
  assistantLabel: "Assistant",
  sourcesLabel: (n: number) => `Sources (${n}) ▾ — citées dans le texte [n]`,
  actionConfirmed: "✓ Action confirmée — la carte est bloquée.",
  actionCancelled: "Action annulée.",
  actionProposed: "Action proposée — confirmation requise",
  expiresIn: (s: number) => `expire dans ${s} s`,
  confirm: "Confirmer",
  cancel: "Annuler",
  loginHint: "→ connectez-vous avec le menu « Connexion client fictif » en haut pour continuer",
  stepUpInline: "Recevoir un code SMS (montée en sécurité)",
  handoffNotice: (ref: string) => `Un conseiller a reçu votre demande avec le contexte (réf. ${ref}).`,
  // feedback widget
  thanksFeedback: "Merci pour votre retour ✓",
  goodAnswer: "Bonne réponse",
  badAnswer: "Mauvaise réponse",
  reason: {
    wrong: "Réponse erronée",
    off_topic: "Hors sujet",
    too_long: "Trop long",
    other: "Autre",
  },
  commentPlaceholder: "Commentaire (optionnel, 280 max)",
  send: "Envoyer",
  // action results
  cardLocked: "Carte bloquée (résultat confirmé côté serveur, exécuté une seule fois).",
  replayConfirmed: "Confirmation rejouée : le résultat enregistré est retourné sans réexécuter (idempotence).",
  streamError: (m: string) => `[erreur : ${m}]`,
  // OTP + composer
  otpBanner: "Code de démonstration (démo, pas de vrai SMS) : ",
  otpPlaceholder: "code à 6 chiffres",
  verify: "Valider",
  inputPlaceholder: "Votre message…",
  // demo panel (admin-token protected routes)
  demoPanel: "Espace démo — latence / panne de la banque fictive (jeton admin requis)",
  adminToken: "jeton admin",
  adminTokenHint:
    "saisissez le jeton admin pour afficher les boutons panne / reset / kill switch (routes protégées, 404 sinon)",
  latencyMs: "latence ms",
  failureRate: "taux d'échec",
  apply: "Appliquer",
  currentFlags: (ms: number, rate: number) => `actuel : ${ms} ms / ${rate}`,
  resetDb: "Réinitialiser la BDD (démo)",
  killSwitchTitle: "Kill switch : aucune action ne s'exécute tant qu'il est coupé",
  disableActions: "Couper les actions",
  enableActions: "Réactiver les actions",
  actionsState: (on: boolean) => `actions : ${on ? "activées" : "coupées"}`,
  resetInfo: (cards: number, deleted: string) => `OK — cartes débloquées : ${cards}, lignes supprimées : ${deleted}`,
  // metrics panel
  metricsPanel: "Métriques agrégées (60 min) — route réservée (démo/admin)",
  refresh: "Rafraîchir",
  mTurns: "tours",
  mByIntent: "par intention",
  mRefused: "refus",
  mEscalation: "escalade (conseiller)",
  mErrors: "erreurs",
  mDownvotes: "pouces bas",
  mE2E: "bout en bout",
  mActions: "actions",
  percentilesMethod: (m: string) => `percentiles : méthode ${m}`,
  // advisor queue panel
  handoffsPanel: "File conseiller — demandes ouvertes (route réservée)",
  noOpenRequests: "aucune demande ouverte",
  take: "Prendre",
  close: "Clôturer",
  ref: "réf",
  // under the hood + footer
  underHood: "Under the hood — dernier tour (JSON brut)",
  noTurnYet: "aucun tour pour le moment",
  footer: "Maquette de démonstration — banque et données entièrement fictives.",
};

export type Texts = typeof fr;

const en: Texts = {
  // header
  demoTag: "fictional demo — invented data",
  langToggleTitle: "Response language",
  level: {
    anonymous: "anonymous",
    authenticated: "signed in",
    strong: "strong auth",
  },
  signInPlaceholder: "Fictional client sign-in…",
  smsButton: "Receive an SMS code",
  signOut: "Sign out",
  advisorButton: "Talk to an advisor",
  advisorMessage: "I want to talk to an advisor",
  // chat
  emptyHint: "Ask a public question (FAQ) or sign in to manage your everyday banking operations.",
  assistantLabel: "Assistant",
  sourcesLabel: (n: number) => `Sources (${n}) ▾ — cited in the text as [n]`,
  actionConfirmed: "✓ Action confirmed — the card is locked.",
  actionCancelled: "Action cancelled.",
  actionProposed: "Proposed action — confirmation required",
  expiresIn: (s: number) => `expires in ${s} s`,
  confirm: "Confirm",
  cancel: "Cancel",
  loginHint: "→ sign in with the “Fictional client sign-in” menu at the top to continue",
  stepUpInline: "Receive an SMS code (step-up)",
  handoffNotice: (ref: string) => `An advisor received your request with context (ref. ${ref}).`,
  // feedback widget
  thanksFeedback: "Thanks for your feedback ✓",
  goodAnswer: "Good answer",
  badAnswer: "Bad answer",
  reason: {
    wrong: "Wrong answer",
    off_topic: "Off topic",
    too_long: "Too long",
    other: "Other",
  },
  commentPlaceholder: "Comment (optional, 280 max)",
  send: "Send",
  // action results
  cardLocked: "Card locked (result confirmed server-side, executed once).",
  replayConfirmed: "Replayed confirmation: the stored result is returned without re-executing (idempotency).",
  streamError: (m: string) => `[error: ${m}]`,
  // OTP + composer
  otpBanner: "Demo code (demo, no real SMS): ",
  otpPlaceholder: "6-digit code",
  verify: "Verify",
  inputPlaceholder: "Your message…",
  // demo panel (admin-token protected routes)
  demoPanel: "Demo area — fictional bank latency / outage (admin token required)",
  adminToken: "admin token",
  adminTokenHint:
    "enter the admin token to show the outage / reset / kill switch buttons (protected routes, 404 otherwise)",
  latencyMs: "latency ms",
  failureRate: "failure rate",
  apply: "Apply",
  currentFlags: (ms: number, rate: number) => `current: ${ms} ms / ${rate}`,
  resetDb: "Reset the DB (demo)",
  killSwitchTitle: "Kill switch: no action executes while it is off",
  disableActions: "Disable actions",
  enableActions: "Re-enable actions",
  actionsState: (on: boolean) => `actions: ${on ? "enabled" : "disabled"}`,
  resetInfo: (cards: number, deleted: string) => `OK — cards unlocked: ${cards}, rows deleted: ${deleted}`,
  // metrics panel
  metricsPanel: "Aggregated metrics (60 min) — reserved route (demo/admin)",
  refresh: "Refresh",
  mTurns: "turns",
  mByIntent: "by intent",
  mRefused: "refusals",
  mEscalation: "escalation (advisor)",
  mErrors: "errors",
  mDownvotes: "downvotes",
  mE2E: "end-to-end",
  mActions: "actions",
  percentilesMethod: (m: string) => `percentiles: method ${m}`,
  // advisor queue panel
  handoffsPanel: "Advisor queue — open requests (reserved route)",
  noOpenRequests: "no open requests",
  take: "Take",
  close: "Close",
  ref: "ref",
  // under the hood + footer
  underHood: "Under the hood — last turn (raw JSON)",
  noTurnYet: "no turn yet",
  footer: "Demo prototype — bank and data are entirely fictional.",
};

export const TEXTS: Record<Lang, Texts> = { fr, en };
