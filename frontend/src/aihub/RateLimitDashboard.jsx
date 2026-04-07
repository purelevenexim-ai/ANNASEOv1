import { useState, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { T, api } from "../App"

const PROVIDER_LABELS = {
  groq: "⚡ Groq",
  gemini_free: "💎 Gemini Free",
  gemini_paid: "💎 Gemini Paid",
  anthropic: "🧠 Claude",
  openai_paid: "🤖 ChatGPT",
  ollama: "🦙 Ollama",
  openrouter: "🌐 OpenRouter",
}

// Countdown timer that decrements client-side between API refreshes
function CountdownTimer({ seconds }) {
  const [remaining, setRemaining] = useState(seconds)
  useEffect(() => {
    setRemaining(seconds)
    if (seconds <= 0) return
    const id = setInterval(() => setRemaining(r => Math.max(0, r - 1)), 1000)
    return () => clearInterval(id)
  }, [seconds])
  if (remaining <= 0) return <span style={{ color: T.teal, fontWeight: 600 }}>Ready</span>
  return <span style={{ color: T.red, fontWeight: 600 }}>Resets in {remaining}s</span>
}

function TokenBar({ label, remaining, limit }) {
  const pct = limit > 0 ? Math.min(100, Math.round((remaining / limit) * 100)) : null
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
        <span style={{ color: T.textSoft }}>{label}</span>
        <span style={{ fontWeight: 600 }}>
          {remaining != null ? remaining.toLocaleString() : "—"}
          {limit ? ` / ${limit.toLocaleString()}` : ""}
        </span>
      </div>
      {pct != null && (
        <div style={{ height: 4, background: "#E5E5EA", borderRadius: 99 }}>
          <div style={{
            height: 4, borderRadius: 99, transition: "width 0.4s",
            width: `${pct}%`,
            background: pct > 50 ? T.teal : pct > 20 ? T.amber : T.red,
          }} />
        </div>
      )}
    </div>
  )
}

function ProviderRow({ id, info }) {
  const label = PROVIDER_LABELS[id] || id
  const rl = info.rate_limit_info || {}
  const isBlocked = info.status !== "ok"
  return (
    <div style={{
      padding: "10px 14px", borderRadius: 10, marginBottom: 8,
      background: isBlocked ? "#FFF0EB" : "#F9F9F9",
      border: `1px solid ${isBlocked ? "#FF3B3040" : T.border}`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: rl.tokens_remaining != null ? 8 : 0 }}>
        <span style={{ fontSize: 14, fontWeight: 600, flex: 1, color: T.text }}>{label}</span>
        <span style={{
          fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
          background: isBlocked ? "#FF3B3020" : "#34C75920",
          color: isBlocked ? "#CC3300" : "#1B7A2E",
        }}>
          {isBlocked ? info.status.replace("_", " ") : "OK"}
        </span>
        {isBlocked && <CountdownTimer seconds={info.seconds_remaining} />}
      </div>
      {rl.tokens_remaining != null && (
        <TokenBar label="Tokens remaining" remaining={rl.tokens_remaining} limit={null} />
      )}
      {rl.requests_remaining != null && (
        <TokenBar label="Requests remaining" remaining={rl.requests_remaining} limit={null} />
      )}
      {rl.daily_exhausted && (
        <div style={{ fontSize: 10, color: T.red, fontWeight: 600 }}>⚠ Daily token quota exhausted</div>
      )}
    </div>
  )
}

function UsageTable({ usage }) {
  if (!usage || usage.length === 0) {
    return <div style={{ fontSize: 11, color: T.textSoft, textAlign: "center", padding: 12 }}>No usage data since last server restart</div>
  }
  const byProvider = {}
  usage.forEach(e => {
    if (!byProvider[e.provider]) byProvider[e.provider] = 0
    byProvider[e.provider] += e.tokens_estimated || 0
  })
  const total = Object.values(byProvider).reduce((a, b) => a + b, 0)
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: T.text, marginBottom: 6 }}>
        Session Token Usage — Est. total: {total.toLocaleString()} tokens
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {Object.entries(byProvider).sort((a, b) => b[1] - a[1]).map(([prov, tokens]) => (
          <div key={prov} style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
            <span style={{ color: T.textSoft }}>{PROVIDER_LABELS[prov] || prov}</span>
            <span style={{ fontWeight: 600 }}>{tokens.toLocaleString()} tokens</span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 8 }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: T.textSoft, marginBottom: 4 }}>Recent calls</div>
        {usage.slice(-10).reverse().map((e, i) => (
          <div key={i} style={{ fontSize: 10, color: T.textSoft, padding: "2px 0" }}>
            {new Date(e.ts * 1000).toLocaleTimeString()} · Step {e.step} {e.step_name} · {PROVIDER_LABELS[e.provider] || e.provider} · ~{(e.tokens_estimated || 0).toLocaleString()} tokens
          </div>
        ))}
      </div>
    </div>
  )
}

export default function RateLimitDashboard() {
  const { data: statusData, isLoading: statusLoading } = useQuery({
    queryKey: ["ai-status"],
    queryFn: () => api.get("/api/ai/status"),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    staleTime: 0,
  })

  const { data: usageData } = useQuery({
    queryKey: ["ai-usage"],
    queryFn: () => api.get("/api/ai/usage"),
    refetchInterval: 10000,
    refetchIntervalInBackground: false,
    staleTime: 0,
  })

  const providers = statusData || {}
  const usage = usageData?.usage || []
  const blockedCount = Object.values(providers).filter(p => p.status !== "ok").length

  return (
    <div style={{ padding: "16px 18px", overflowY: "auto", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: T.text }}>Rate Limit Dashboard</div>
        {blockedCount > 0 && (
          <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99, background: "#FF3B3020", color: "#CC3300" }}>
            {blockedCount} blocked
          </span>
        )}
        {statusLoading && <span style={{ fontSize: 10, color: T.textSoft }}>Refreshing…</span>}
      </div>

      {/* Provider status rows */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
          Provider Status
        </div>
        {Object.entries(providers).map(([id, info]) => (
          <ProviderRow key={id} id={id} info={info} />
        ))}
        {Object.keys(providers).length === 0 && (
          <div style={{ fontSize: 11, color: T.textSoft }}>Loading provider status…</div>
        )}
      </div>

      {/* Session usage */}
      <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
          Session Usage
        </div>
        <UsageTable usage={usage} />
      </div>
    </div>
  )
}
