import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

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
}

interface Message {
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  pending?: PendingAction;
  turn?: Turn;
}

const CLIENT_HEADERS = { "X-Bnp-Client": "bnp-assistant-web" };

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", ...CLIENT_HEADERS, ...(init.headers ?? {}) },
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
  const [now, setNow] = useState(Date.now());
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
      await api("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password: "demo1234" }) });
      setSession(await api<SessionInfo>("/api/auth/me"));
    } catch (e) {
      setError(String(e));
    }
  }

  async function logout() {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
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
      setPending((p) => (p ? { ...p, status: res.action.status } : p));
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
                <div className="whitespace-pre-wrap rounded-2xl rounded-tl-md border border-ink-100 bg-white px-3.5 py-2.5 text-sm shadow-card">
                  {m.text}
                  {m.sources && m.sources.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {m.sources.map((s, j) => (
                        <span key={j} className="chip" title={s.content}>
                          source : {s.source} · score {s.score}
                        </span>
                      ))}
                    </div>
                  )}
                  {m.pending && (
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
                      → connectez-vous (client fictif) pour continuer
                    </div>
                  )}
                  {m.turn?.needs_step_up && (
                    <div className="notice mt-2 border-brand-300 bg-brand-50 px-2.5! py-1! text-xs text-brand-800">
                      → montée en sécurité requise (bouton « Recevoir un code SMS »)
                    </div>
                  )}
                  {m.turn?.human_offer && (
                    <div className="notice mt-2 border-ink-300 bg-ink-50 px-2.5! py-1! text-xs text-ink-700">
                      → un conseiller peut prendre le relais (bouton en haut)
                    </div>
                  )}
                </div>
              </div>
            ),
          )}
          {busy && <div className="self-start text-sm text-ink-500">…</div>}
        </div>

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
