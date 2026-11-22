import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

/**
 * The demo chat page. Every decision stays server-side: this component only renders what the
 * API returns (streamed deltas, sources, pending action, per-stage timings) and sends the
 * custom header on state-changing calls. No banking logic lives here.
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

const LEVEL_CLASS: Record<AuthLevel, string> = {
  anonymous: "bg-gray-200 text-gray-700",
  authenticated: "bg-blue-100 text-blue-800",
  strong: "bg-green-100 text-green-800",
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

  const remaining = pending ? Math.max(0, Math.floor((new Date(pending.expires_at).getTime() - Date.now()) / 1000)) : 0;

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col gap-3 p-4">
      <header className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">bnp-assistant (démo banque fictive)</h1>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${LEVEL_CLASS[session?.level ?? "anonymous"]}`}>
          {LEVEL_LABEL[session?.level ?? "anonymous"]}
          {session?.customer_name ? ` · ${session.customer_name}` : ""}
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <select
            className="rounded border px-2 py-1 text-sm"
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
              <button className="rounded border px-2 py-1 text-sm" onClick={stepUp}>
                Recevoir un code SMS
              </button>
              <button className="rounded border px-2 py-1 text-sm" onClick={logout}>
                Déconnexion
              </button>
            </>
          )}
          <button
            className="rounded bg-gray-800 px-2 py-1 text-sm text-white"
            onClick={() => send("Je veux parler à un conseiller")}
          >
            Parler à un conseiller
          </button>
        </div>
      </header>

      {otpPending !== null && (
        <div className="rounded border border-yellow-400 bg-yellow-50 p-2 text-sm">
          Code de démonstration (démo, pas de vrai SMS) : <b>{otpPending}</b>
          <input
            className="ml-2 w-24 rounded border px-1"
            placeholder="code à 6 chiffres"
            value={otpCode}
            onChange={(e) => setOtpCode(e.target.value)}
          />
          <button className="ml-2 rounded bg-gray-800 px-2 py-0.5 text-white" onClick={verifyOtp}>
            Valider
          </button>
        </div>
      )}

      <div className="flex items-center gap-2 rounded border p-2 text-xs">
        <span className="font-medium">Démo banque (latence/panne) :</span>
        <label>
          latence ms{" "}
          <input className="w-20 rounded border px-1" value={latencyInput} onChange={(e) => setLatencyInput(e.target.value)} />
        </label>
        <label>
          taux d'échec{" "}
          <input className="w-16 rounded border px-1" value={failureInput} onChange={(e) => setFailureInput(e.target.value)} />
        </label>
        <button className="rounded border px-2 py-0.5" onClick={saveFlags}>
          Appliquer
        </button>
        <span className="text-gray-500">actuel : {flags.latency_ms} ms / {flags.failure_rate}</span>
      </div>

      {error && <div className="rounded border border-red-400 bg-red-50 p-2 text-sm text-red-700">{error}</div>}

      <div ref={scrollRef} className="flex min-h-64 flex-1 flex-col gap-2 overflow-y-auto rounded border p-3">
        {messages.length === 0 && <p className="text-sm text-gray-500">Posez une question publique (FAQ) ou connectez-vous pour voir vos comptes.</p>}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "self-end rounded bg-blue-600 px-3 py-2 text-sm text-white" : "self-start rounded bg-gray-100 px-3 py-2 text-sm"}>
            <div className="whitespace-pre-wrap">{m.text}</div>
            {m.sources && m.sources.length > 0 && (
              <ul className="mt-1 list-disc pl-4 text-xs text-gray-600">
                {m.sources.map((s, j) => (
                  <li key={j}>source : {s.source} (score {s.score})</li>
                ))}
              </ul>
            )}
            {m.pending && (
              <div className="mt-2 rounded border border-amber-500 bg-amber-50 p-2 text-xs">
                <div className="font-semibold">Action proposée — confirmation requise</div>
                <div>
                  {m.pending.card_label} {m.pending.card_masked_number} — {m.pending.effect}
                </div>
                <div>Expire dans {remaining}s</div>
                <div className="mt-1 flex gap-2">
                  <button className="rounded bg-green-700 px-2 py-0.5 text-white" onClick={() => confirmAction(m.pending!.action_id)}>
                    Confirmer
                  </button>
                  <button className="rounded border px-2 py-0.5" onClick={() => cancelAction(m.pending!.action_id)}>
                    Annuler
                  </button>
                </div>
              </div>
            )}
            {m.turn?.needs_login && <div className="mt-1 text-xs text-blue-700">→ invite de connexion</div>}
            {m.turn?.needs_step_up && <div className="mt-1 text-xs text-blue-700">→ montée en sécurité requise (bouton « Recevoir un code SMS »)</div>}
            {m.turn?.human_offer && <div className="mt-1 text-xs text-gray-600">→ un conseiller peut prendre le relais (bouton en haut)</div>}
          </div>
        ))}
        {busy && <div className="self-start text-sm text-gray-400">…</div>}
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          className="flex-1 rounded border px-3 py-2 text-sm"
          placeholder="Votre message…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button className="rounded bg-blue-700 px-4 py-2 text-sm text-white disabled:opacity-50" disabled={busy || !input.trim()}>
          Envoyer
        </button>
      </form>

      <details className="rounded border p-2 text-xs">
        <summary className="cursor-pointer font-medium">Under the hood — dernier tour (JSON brut)</summary>
        <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all rounded bg-gray-50 p-2">
          {lastTurn ? JSON.stringify(lastTurn, null, 2) : "aucun tour pour le moment"}
        </pre>
      </details>
    </main>
  );
}
