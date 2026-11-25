import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

import { renderMarkdown } from "../markdown";

/**
 * The demo chat page. Every decision stays server-side: this component only renders what the
 * API returns (streamed deltas, sources, pending action, per-stage timings) and sends the
 * custom header on state-changing calls. No banking logic lives here. Styling comes from the
 * fictional demo-bank design tokens in `index.css` (not any real bank's brand assets).
 */

type AuthLevel = "anonymous" | "authenticated" | "strong";

interface SessionInfo {
  session_id: string;
  level: AuthLevel;
  customer_id: string | null;
  customer_name: string | null;
  expires_in_seconds: number;
}

interface DemoCustomer {
  email: string;
  display_name: string;
  password: string;
}

interface PendingAction {
  action_id: string;
  kind: string;
  card_masked_number: string;
  card_label: string;
  effect: string;
  status: string;
  expires_at: string;
}

interface Source {
  source: string;
  score: number;
  content: string;
}

interface Turn {
  correlation_id: string;
  intent: string;
  answer: string;
  timings: { stage: string; ms: number }[];
  guardrails: unknown;
  tool_calls: { name: string; arguments: unknown }[];
  sources: Source[];
  pending_action: PendingAction | null;
  needs_login: boolean;
  needs_step_up: boolean;
  human_offer: boolean;
  refused: boolean;
  auth_level: AuthLevel;
  handoff_id?: string | null;
}

interface StageLatency {
  p50: number | null;
  p95: number | null;
  n: number;
}

interface MetricsView {
  window_minutes: number;
  turns_total: number;
  by_intent: Record<string, number>;
  refused_rate: number | null;
  human_offer_rate: number | null;
  error_rate: number | null;
  downvotes_rated: number;
  downvotes_down: number;
  downvote_rate: number | null;
  latency_ms: Record<string, StageLatency>;
  end_to_end_ms: StageLatency;
  actions: Record<string, number>;
  method: string;
}

interface Message {
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  pending?: PendingAction;
  turn?: Turn;
}

const CLIENT_HEADERS = { "X-Bnp-Client": "bnp-assistant-web" };

// The session token from the login response, echoed as X-Bnp-Session on every call: behind the
// Studio gateway the module's Set-Cookie may not reach the browser, so the cookie alone is not
// enough there (locally, it is).
let SESSION_TOKEN: string | null = null;

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...CLIENT_HEADERS,
      ...(SESSION_TOKEN ? { "X-Bnp-Session": SESSION_TOKEN } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status} ${JSON.stringify(detail)}`);
  }
  return res.json() as Promise<T>;
}

const LEVEL_LABEL: Record<AuthLevel, string> = {
  anonymous: "anonyme",
  authenticated: "connecté",
  strong: "authentification forte",
};

const LEVEL_BADGE: Record<AuthLevel, string> = {
  anonymous: "bg-white/10 text-brand-100",
  authenticated: "bg-amber-300/20 text-amber-100",
  strong: "bg-brand-300/25 text-brand-50",
};

// Per-turn feedback widget state, keyed by correlation_id.
type FbState = { rating: "up" | "down"; reason: string; comment: string; sent: boolean; open: boolean };

const REASON_LABEL: Record<string, string> = {
  wrong: "Réponse erronée",
  off_topic: "Hors sujet",
  too_long: "Trop long",
  other: "Autre",
};

function FeedbackWidget(props: {
  fb: FbState | undefined;
  onUp: () => void;
  onDown: () => void;
  onReason: (r: string) => void;
  onComment: (c: string) => void;
  onSend: () => void;
}) {
  const { fb, onUp, onDown, onReason, onComment, onSend } = props;
  if (fb?.sent) {
    return <div className="mt-2 text-[11px] font-medium text-brand-700">Merci pour votre retour ✓</div>;
  }
  if (!fb) {
    return (
      <div className="mt-2 flex gap-1.5">
        <button className="chip hover:bg-brand-50" title="Bonne réponse" onClick={onUp}>
          👍
        </button>
        <button className="chip hover:bg-red-50" title="Mauvaise réponse" onClick={onDown}>
          👎
        </button>
      </div>
    );
  }
  if (fb.rating === "up") return null; // sent immediately on click
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 rounded-lg border border-ink-100 bg-ink-50 p-2">
      <select className="select px-2! py-1! text-xs" value={fb.reason} onChange={(e) => onReason(e.target.value)}>
        {Object.entries(REASON_LABEL).map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
      <input
        className="input flex-1 px-2! py-1! text-xs"
        maxLength={280}
        placeholder="Commentaire (optionnel, 280 max)"
        value={fb.comment}
        onChange={(e) => onComment(e.target.value)}
      />
      <button className="btn-primary px-2.5! py-1! text-xs!" onClick={onSend}>
        Envoyer
      </button>
    </div>
  );
}

export const Route = createFileRoute("/")({
  component: ChatPage,
});

function ChatPage() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [customers, setCustomers] = useState<DemoCustomer[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [otpPending, setOtpPending] = useState<string | null>(null);
  const [lastTurn, setLastTurn] = useState<Turn | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [flags, setFlags] = useState({ latency_ms: 0, failure_rate: 0 });
  const [latencyInput, setLatencyInput] = useState("0");
  const [failureInput, setFailureInput] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useState<"fr" | "en">("fr");
  const [now, setNow] = useState(Date.now());
  // The user message that triggered a needs_login / needs_step_up turn: re-sent automatically
  // once the auth step succeeds, so the chat resumes the conversation by itself.
  const [pendingResume, setPendingResume] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<SessionInfo>("/api/auth/me").then(setSession).catch(() => setSession(null));
    api<DemoCustomer[]>("/api/demo/customers").then(setCustomers).catch(() => {});
    api<{ latency_ms: number; failure_rate: number }>("/api/demo/bank-flags")
      .then((f) => {
        setFlags(f);
        setLatencyInput(String(f.latency_ms));
        setFailureInput(String(f.failure_rate));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, busy]);

  // Pure display clock so the pending-action countdown ticks; no logic, just re-render.
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [pending]);

  async function login(email: string) {
    setError(null);
    try {
      await api("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password: "demo1234" }) }).then((res) => {
        SESSION_TOKEN = (res as { token: string }).token;
      });
      setSession(await api<SessionInfo>("/api/auth/me"));
      const resume = pendingResume;
      if (resume) {
        setPendingResume(null);
        await send(resume);
      }
    } catch (e) {
      setError(String(e));
    }
  }

  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST", body: "{}" });
    } finally {
      SESSION_TOKEN = null; // local logout even if the call itself failed
    }
    setSession(await api<SessionInfo>("/api/auth/me"));
    setPending(null);
  }

  async function stepUp() {
    setError(null);
    try {
      const res = await api<{ otp_id: string; demo_code: string | null }>("/api/auth/step-up", {
        method: "POST",
        body: "{}",
      });
      setOtpPending(res.demo_code ?? "");
    } catch (e) {
      setError(String(e));
    }
  }

  async function verifyOtp() {
    setError(null);
    try {
      await api("/api/auth/step-up/verify", { method: "POST", body: JSON.stringify({ code: otpCode }) });
      setOtpPending(null);
      setOtpCode("");
      setSession(await api<SessionInfo>("/api/auth/me"));
      const resume = pendingResume;
      if (resume) {
        setPendingResume(null);
        await send(resume); // step-up done: the chat resumes the message that asked for it
      }
    } catch (e) {
      setError(String(e));
    }
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    const userMsg: Message = { role: "user", text };
    const assistantMsg: Message = { role: "assistant", text: "" };
    setMessages((m) => [...m, userMsg, assistantMsg]);
    setInput("");
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", ...(SESSION_TOKEN ? { "X-Bnp-Session": SESSION_TOKEN } : {}) },
        body: JSON.stringify({ message: text, lang }),
      });
      if (!res.ok || !res.body) throw new Error(`chat HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";
      const patch = (fn: (m: Message) => Message) =>
        setMessages((ms) => ms.map((m, i) => (i === ms.length - 1 ? fn(m) : m)));
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx: number;
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          let data = "";
          for (const line of raw.split("\n")) {
            if (line.startsWith("event:")) currentEvent = line.slice(6).trim();
            else if (line.startsWith("data:")) data = line.slice(5).trim();
          }
          if (!data) continue;
          const payload = JSON.parse(data);
          if (currentEvent === "delta") patch((m) => ({ ...m, text: m.text + payload.text }));
          else if (currentEvent === "sources") patch((m) => ({ ...m, sources: [...(m.sources ?? []), payload.source] }));
          else if (currentEvent === "pending_action") {
            patch((m) => ({ ...m, pending: payload.action }));
            setPending(payload.action);
          } else if (currentEvent === "turn") {
            const turn = payload.turn as Turn;
            setLastTurn(turn);
            patch((m) => ({ ...m, turn }));
            if (turn.needs_login || turn.needs_step_up) setPendingResume(text);
            else setPendingResume(null);
          } else if (currentEvent === "error") {
            patch((m) => ({ ...m, text: m.text + `\n[erreur: ${payload.message}]` }));
          }
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirmAction(actionId: string) {
    setError(null);
    try {
      const res = await api<{ executed: boolean; result: { status?: string }; action: { status: string } }>(
        `/api/actions/${actionId}/confirm`,
        { method: "POST", body: "{}" },
      );
      // Mark the pending card on its message as done (it disappears from the actionable list)
      // and stop the global countdown; a result line is appended below.
      setMessages((ms) =>
        ms.map((m) => (m.pending?.action_id === actionId ? { ...m, pending: { ...m.pending, status: res.action.status } } : m)),
      );
      setPending(null);
      setMessages((ms) => [
        ...ms,
        {
          role: "assistant",
          text: res.executed
            ? `Carte ${res.action ? "" : ""}bloquée (résultat confirmé côté serveur, exécuté une seule fois).`
            : `Confirmation rejouée : le résultat enregistré est retourné sans réexécuter (idempotence).`,
        },
      ]);
    } catch (e) {
      setError(String(e));
    }
  }

  async function cancelAction(actionId: string) {
    setError(null);
    try {
      await api(`/api/actions/${actionId}/cancel`, { method: "POST", body: "{}" });
      setMessages((ms) =>
        ms.map((m) => (m.pending?.action_id === actionId ? { ...m, pending: { ...m.pending, status: "cancelled" } } : m)),
      );
      setPending(null);
    } catch (e) {
      setError(String(e));
    }
  }

  async function saveFlags() {
    setError(null);
    try {
      const f = await api<{ latency_ms: number; failure_rate: number }>("/api/demo/bank-flags", {
        method: "POST",
        body: JSON.stringify({ latency_ms: Number(latencyInput) || 0, failure_rate: Number(failureInput) || 0 }),
      });
      setFlags(f);
    } catch (e) {
      setError(String(e));
    }
  }

  const [resetInfo, setResetInfo] = useState<string | null>(null);
  // Feedback state per turn correlation_id: { rating, reason, comment, sent, open }
  const [fbByCorr, setFbByCorr] = useState<Record<string, FbState>>({});

  function updateFb(corr: string, patch: Partial<FbState>) {
    setFbByCorr((c) => ({ ...c, [corr]: { rating: "down", reason: "other", comment: "", sent: false, open: false, ...c[corr], ...patch } }));
  }

  function vote(corr: string, rating: "up" | "down", i: number) {
    const cur = fbByCorr[corr];
    const next: FbState = { rating, reason: cur?.reason || "other", comment: cur?.comment || "", sent: cur?.sent || false, open: rating === "down" };
    setFbByCorr((c) => ({ ...c, [corr]: next }));
    if (rating === "up") void sendFeedback(i, next); // thumbs up sends immediately
  }

  async function sendFeedback(i: number, fb: FbState | undefined) {
    const m = messages[i];
    const turn = m?.turn;
    if (!turn || !fb || fb.sent) return;
    const userText = i > 0 && messages[i - 1]?.role === "user" ? messages[i - 1].text : "";
    try {
      await api("/api/feedback", {
        method: "POST",
        body: JSON.stringify({
          correlation_id: turn.correlation_id,
          rating: fb.rating,
          reason: fb.rating === "down" ? fb.reason || null : null,
          comment: fb.comment || null,
          // excerpts only for "down"; the server scrubs and truncates them anyway
          message_excerpt: fb.rating === "down" ? userText.slice(0, 500) : null,
          answer_excerpt: fb.rating === "down" ? m.text.slice(0, 500) : null,
        }),
      });
      setFbByCorr((c) => ({ ...c, [turn.correlation_id]: { ...fb, sent: true } }));
    } catch (e) {
      setError(String(e));
    }
  }

  async function resetDemo() {
    setError(null);
    setResetInfo(null);
    try {
      const res = await api<{ ok: boolean; cards_unlocked: number; deleted: Record<string, number> }>("/api/demo/reset", {
        method: "POST",
        body: "{}",
      });
      setResetInfo(`OK — cartes débloquées : ${res.cards_unlocked}, lignes supprimées : ${JSON.stringify(res.deleted)}`);
      setPending(null);
    } catch (e) {
      setError(String(e));
    }
  }

  // Aggregate metrics over the last hour (reserved route: demo mode or admin token).
  const [metrics, setMetrics] = useState<MetricsView | null>(null);
  // Actions kill switch (runtime feature flag, hot-toggled via /api/demo/feature-flags).
  const [actionsEnabled, setActionsEnabled] = useState(true);

  useEffect(() => {
    api<{ actions_enabled: boolean }>("/api/demo/feature-flags")
      .then((f) => setActionsEnabled(f.actions_enabled))
      .catch(() => {});
  }, []);

  async function toggleActions() {
    try {
      const f = await api<{ actions_enabled: boolean; default_actions_enabled: boolean }>("/api/demo/feature-flags", {
        method: "POST",
        body: JSON.stringify({ actions_enabled: !actionsEnabled }),
      });
      setActionsEnabled(f.actions_enabled);
    } catch (e) {
      setError(String(e));
    }
  }

  async function refreshMetrics() {
    try {
      setMetrics(await api<MetricsView>("/api/metrics?window_minutes=60"));
    } catch (e) {
      setError(String(e));
    }
  }

  function pct(x: number | null): string {
    return x === null ? "—" : `${(x * 100).toFixed(0)}%`;
  }

  function ms(x: StageLatency): string {
    return x.n === 0 ? "—" : `p50 ${x.p50} / p95 ${x.p95} (n=${x.n})`;
  }

  const remaining = pending ? Math.max(0, Math.floor((new Date(pending.expires_at).getTime() - now) / 1000)) : 0;

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-10 bg-brand-900 text-white shadow-card">
        <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-base font-bold text-white">
              B
            </span>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight">
                BNP Paribas <span className="font-normal text-brand-200">· Assistant</span>
              </div>
              <div className="text-[11px] text-brand-200">démo fictive — données inventées</div>
            </div>
          </div>
          <span className={`badge ${LEVEL_BADGE[session?.level ?? "anonymous"]}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {LEVEL_LABEL[session?.level ?? "anonymous"]}
            {session?.customer_name ? ` · ${session.customer_name}` : ""}
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <div className="flex overflow-hidden rounded-lg border border-white/25 text-xs font-semibold" title="Langue de réponse">
              <button
                className={lang === "fr" ? "bg-white px-2 py-1 text-brand-900" : "px-2 py-1 text-white hover:bg-white/10"}
                onClick={() => setLang("fr")}
              >
                FR
              </button>
              <button
                className={lang === "en" ? "bg-white px-2 py-1 text-brand-900" : "px-2 py-1 text-white hover:bg-white/10"}
                onClick={() => setLang("en")}
              >
                EN
              </button>
            </div>
            <select
              className="select"
              defaultValue=""
              onChange={(e) => e.target.value && login(e.target.value)}
            >
              <option value="">Connexion client fictif…</option>
              {customers.map((c) => (
                <option key={c.email} value={c.email}>
                  {c.display_name} ({c.email})
                </option>
              ))}
            </select>
            {session && session.level !== "anonymous" && (
              <>
                <button className="btn-outline-light" onClick={stepUp}>
                  Recevoir un code SMS
                </button>
                <button className="btn-outline-light" onClick={logout}>
                  Déconnexion
                </button>
              </>
            )}
            <button className="btn-advisor" onClick={() => send("Je veux parler à un conseiller")}>
              Parler à un conseiller
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-3 px-4 py-4">
        {error && <div className="notice border-red-300 bg-red-50 text-red-700">{error}</div>}

        <div ref={scrollRef} className="card flex min-h-64 flex-1 flex-col gap-3 overflow-y-auto p-4">
          {messages.length === 0 && (
            <div className="m-auto max-w-sm text-center text-sm text-ink-500">
              Posez une question publique (FAQ) ou connectez-vous pour consulter vos comptes et bloquer
              une carte.
            </div>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="max-w-[85%] self-end whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand-600 px-3.5 py-2.5 text-sm text-white shadow-card">
                {m.text}
              </div>
            ) : (
              <div key={i} className="max-w-[85%] self-start">
                <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-ink-500">
                  <span className="h-5 w-5 rounded-full bg-brand-600 text-center text-[10px] font-bold leading-5 text-white">
                    A
                  </span>
                  Assistant
                </div>
                <div className="rounded-2xl rounded-tl-md border border-ink-100 bg-white px-3.5 py-2.5 text-sm shadow-card">
                  {renderMarkdown(m.text)}
                  {m.sources && m.sources.length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-[11px] font-semibold text-brand-700">
                        Sources ({m.sources.length}) ▾ — citées dans le texte [n]
                      </summary>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {m.sources.map((s, j) => (
                          <span key={j} className="chip" title={s.content}>
                            [{j + 1}] {s.source}
                          </span>
                        ))}
                      </div>
                    </details>
                  )}
                  {m.pending && m.pending.status !== "pending" && (
                    <div className="mt-2 rounded-lg border border-brand-200 bg-brand-50 px-2.5 py-1 text-xs text-brand-800">
                      {m.pending.status === "confirmed" ? "✓ Action confirmée — la carte est bloquée." : "Action annulée."}
                    </div>
                  )}
                  {m.pending && m.pending.status === "pending" && (
                    <div className="mt-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-950">
                      <div className="font-semibold">Action proposée — confirmation requise</div>
                      <div className="mt-0.5">
                        {m.pending.card_label} {m.pending.card_masked_number} — {m.pending.effect}
                      </div>
                      <div className="mt-0.5 font-mono">expire dans {remaining} s</div>
                      <div className="mt-2 flex gap-2">
                        <button className="btn-confirm px-2.5! py-1! text-xs!" onClick={() => confirmAction(m.pending!.action_id)}>
                          Confirmer
                        </button>
                        <button className="btn-ghost px-2.5! py-1! text-xs!" onClick={() => cancelAction(m.pending!.action_id)}>
                          Annuler
                        </button>
                      </div>
                    </div>
                  )}
                  {m.turn?.needs_login && (
                    <div className="notice mt-2 border-brand-300 bg-brand-50 px-2.5! py-1! text-xs text-brand-800">
                      → connectez-vous avec le menu « Connexion client fictif » en haut pour continuer
                    </div>
                  )}
                  {m.turn?.needs_step_up && (
                    <div className="mt-2">
                      <button className="btn-primary px-2.5! py-1! text-xs!" onClick={stepUp}>
                        Recevoir un code SMS (montée en sécurité)
                      </button>
                    </div>
                  )}
                  {m.turn?.human_offer && (
                    <div className="mt-2">
                      <button className="btn-ghost px-2.5! py-1! text-xs!" onClick={() => send("Je veux parler à un conseiller")}>
                        Parler à un conseiller
                      </button>
                    </div>
                  )}
                  {m.turn && (
                    <FeedbackWidget
                      fb={fbByCorr[m.turn.correlation_id]}
                      onUp={() => vote(m.turn!.correlation_id, "up", i)}
                      onDown={() => vote(m.turn!.correlation_id, "down", i)}
                      onReason={(r) => updateFb(m.turn!.correlation_id, { reason: r })}
                      onComment={(c) => updateFb(m.turn!.correlation_id, { comment: c })}
                      onSend={() => sendFeedback(i, fbByCorr[m.turn!.correlation_id])}
                    />
                  )}
                </div>
              </div>
            ),
          )}
          {busy && <div className="self-start text-sm text-ink-500">…</div>}
        </div>

        {otpPending !== null && (
          <div className="notice border-amber-300 bg-amber-50 text-amber-900">
            Code de démonstration (démo, pas de vrai SMS) : <b className="font-mono">{otpPending}</b>
            <input
              className="input ml-2 inline-block w-28 px-2! py-1! text-sm"
              placeholder="code à 6 chiffres"
              value={otpCode}
              onChange={(e) => setOtpCode(e.target.value)}
            />
            <button className="btn-primary ml-2 px-2.5! py-1! text-sm" onClick={verifyOtp}>
              Valider
            </button>
          </div>
        )}

        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            className="input flex-1"
            placeholder="Votre message…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button className="btn-primary px-4 py-2" disabled={busy || !input.trim()}>
            Envoyer
          </button>
        </form>

        <details className="card px-3 py-2 text-xs text-ink-700">
          <summary className="cursor-pointer font-medium">Espace démo — latence / panne de la banque fictive</summary>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5">
              latence ms
              <input className="input w-20 px-2! py-1!" value={latencyInput} onChange={(e) => setLatencyInput(e.target.value)} />
            </label>
            <label className="flex items-center gap-1.5">
              taux d'échec
              <input className="input w-16 px-2! py-1!" value={failureInput} onChange={(e) => setFailureInput(e.target.value)} />
            </label>
            <button className="btn-ghost px-2.5! py-1!" onClick={saveFlags}>
              Appliquer
            </button>
            <span className="text-ink-500">actuel : {flags.latency_ms} ms / {flags.failure_rate}</span>
            <button className="btn-ghost px-2.5! py-1! border-red-300! text-red-700!" onClick={resetDemo}>
              Réinitialiser la BDD (démo)
            </button>
            <button
              className={`btn-ghost px-2.5! py-1! ${actionsEnabled ? "border-red-300! text-red-700!" : "border-green-400! text-green-700!"}`}
              onClick={toggleActions}
              title="Kill switch : aucune action ne s'exécute tant qu'il est coupé"
            >
              {actionsEnabled ? "Couper les actions" : "Réactiver les actions"}
            </button>
            <span className="text-ink-500">actions : {actionsEnabled ? "activées" : "coupées"}</span>
            {resetInfo && <span className="text-brand-700">{resetInfo}</span>}
          </div>
        </details>

        <details className="card px-3 py-2 text-xs text-ink-700">
          <summary className="cursor-pointer font-medium">Métriques agrégées (60 min) — route réservée (démo/admin)</summary>
          <div className="mt-2">
            <button className="btn-ghost px-2.5! py-1!" onClick={refreshMetrics}>
              Rafraîchir
            </button>
            {metrics && (
              <div className="mt-2 overflow-x-auto">
                <table className="w-full border-collapse text-left">
                  <tbody>
                    <tr><td className="pr-3 text-ink-500">tours</td><td className="font-semibold">{metrics.turns_total}</td>
                        <td className="pr-3 text-ink-500">par intention</td><td>{JSON.stringify(metrics.by_intent)}</td></tr>
                    <tr><td className="pr-3 text-ink-500">refus</td><td>{pct(metrics.refused_rate)}</td>
                        <td className="pr-3 text-ink-500">escalade (conseiller)</td><td>{pct(metrics.human_offer_rate)}</td>
                        <td className="pr-3 text-ink-500">erreurs</td><td>{pct(metrics.error_rate)}</td></tr>
                    <tr><td className="pr-3 text-ink-500">pouces bas</td><td>{pct(metrics.downvote_rate)} ({metrics.downvotes_down}/{metrics.downvotes_rated})</td>
                        <td className="pr-3 text-ink-500">bout en bout</td><td>{ms(metrics.end_to_end_ms)}</td></tr>
                    {Object.entries(metrics.latency_ms).map(([stage, l]) => (
                      <tr key={stage}><td className="pr-3 text-ink-500">{stage}</td><td colSpan={5}>{ms(l)}</td></tr>
                    ))}
                    <tr><td className="pr-3 text-ink-500">actions</td><td colSpan={5}>{JSON.stringify(metrics.actions)}</td></tr>
                  </tbody>
                </table>
                <div className="mt-1 text-[10px] text-ink-400">percentiles : méthode {metrics.method}</div>
              </div>
            )}
          </div>
        </details>

        <details className="card px-3 py-2 text-xs text-ink-700">
          <summary className="cursor-pointer font-medium">Under the hood — dernier tour (JSON brut)</summary>
          <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-ink-900 p-3 font-mono text-[11px] leading-relaxed text-brand-100">
            {lastTurn ? JSON.stringify(lastTurn, null, 2) : "aucun tour pour le moment"}
          </pre>
        </details>

        <p className="pb-2 text-center text-[11px] text-ink-500">
          Maquette de démonstration — banque et données entièrement fictives.
        </p>
      </main>
    </div>
  );
}
