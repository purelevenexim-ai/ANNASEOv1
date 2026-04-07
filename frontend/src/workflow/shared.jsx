// Shared UI primitives and constants for the 4-step keyword workflow
import { useRef, useEffect } from "react"

export { default as apiCall } from "../lib/apiCall"
export { API } from "../lib/apiCall"

// ─── Design Tokens — Apple iOS design system ──────────────────────────────────
export const T = {
  purple:     "#007AFF",
  purpleLight:"rgba(0,122,255,0.1)",
  purpleDark: "#0040DD",
  teal:       "#34C759",
  tealLight:  "rgba(52,199,89,0.1)",
  amber:      "#FF9500",
  amberLight: "rgba(255,149,0,0.1)",
  red:        "#FF3B30",
  green:      "#34C759",
  greenLight: "rgba(52,199,89,0.1)",
  gray:       "#8E8E93",
  grayLight:  "#F2F2F7",
  border:     "rgba(60,60,67,0.12)",
  text:       "#000000",
  textSoft:   "rgba(60,60,67,0.55)",
  cardShadow: "0 1px 2px rgba(0,0,0,0.05), 0 0 0 0.5px rgba(0,0,0,0.07)",
}

// ─── Constants ────────────────────────────────────────────────────────────────
export const INTENT_OPTIONS = [
  { value: "transactional", label: "Buy / Purchase" },
  { value: "informational", label: "Information / Learn" },
  { value: "commercial",    label: "Commercial Research" },
  { value: "local",         label: "Local / Near me" },
  { value: "comparison",    label: "Comparison / Review" },
]

export const SEASONAL_PRESETS = ["Christmas","Onam","Eid","Diwali","Vishu","Easter","Ramadan","Holi"]

export const SOURCE_COLORS = {
  user:            "#10b981",
  google:          "#3b82f6",
  ai_generated:    "#f59e0b",
  cross_multiply:  "#7c3aed",
  site_crawl:      "#0d9488",
  competitor_crawl:"#e11d48",
  wikipedia:       "#f97316",
  fallback_generation: "#94a3b8",
}

export function intentColor(intent) {
  return {
    transactional: "#0d9488", informational: "#7c3aed", commercial: "#d97706",
    local: "#0284c7", comparison: "#5b21b6", question: "#0891b2",
  }[intent] || "#6b7280"
}

// ─── UI Primitives ────────────────────────────────────────────────────────────
export function Card({ children, style }) {
  return (
    <div style={{
      background: "#fff", borderRadius: 13,
      boxShadow: T.cardShadow,
      padding: 20, ...style,
    }}>
      {children}
    </div>
  )
}

export function Btn({ children, onClick, variant = "default", disabled, small, style }) {
  const base = {
    padding: small ? "5px 12px" : "8px 18px",
    borderRadius: 9, fontSize: small ? 11 : 13, fontWeight: 500,
    cursor: disabled ? "not-allowed" : "pointer",
    border: "none", transition: "opacity 0.15s",
    opacity: disabled ? 0.5 : 1,
  }
  const variants = {
    primary: { background: T.purple,    color: "#fff" },
    teal:    { background: T.teal,      color: "#fff" },
    danger:  { background: "rgba(255,59,48,0.1)", color: T.red },
    default: { background: T.grayLight, color: T.text },
  }
  return (
    <button style={{ ...base, ...(variants[variant] || variants.default), ...style }}
      onClick={onClick} disabled={disabled}>
      {children}
    </button>
  )
}

export function Badge({ color, children }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "2px 8px",
      borderRadius: 99, fontSize: 10, fontWeight: 600,
      background: color + "22", color,
    }}>
      {children}
    </span>
  )
}

export function Spinner() {
  return (
    <span style={{
      display: "inline-block", width: 14, height: 14,
      border: "2px solid rgba(0,122,255,0.2)", borderTopColor: T.purple,
      borderRadius: "50%", animation: "spin 0.7s linear infinite",
    }}/>
  )
}

// ─── Live Console ─────────────────────────────────────────────────────────────
const LOG_LEVEL_COLOR = { success: "#10b981", warn: "#f59e0b", warning: "#f59e0b", error: "#ef4444", info: "#64748b" }
const LOG_LEVEL_ICON  = { success: "✓", warn: "⚠", warning: "⚠", error: "✗", info: "›" }

export function LiveConsole({ logs = [], running = false, maxHeight = 260, title = "LIVE CONSOLE" }) {
  const ref = useRef(null)
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [logs])

  if (!running && logs.length === 0) return null

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{
        fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#64748b",
        marginBottom: 5, display: "flex", alignItems: "center", gap: 8,
      }}>
        {title}
        {running && (
          <span style={{
            width: 7, height: 7, borderRadius: "50%", background: "#10b981",
            display: "inline-block", animation: "lcPulse 1.2s ease-in-out infinite",
          }}/>
        )}
      </div>
      <div ref={ref} style={{
        background: "#0f172a", borderRadius: 8, padding: "10px 12px",
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace", fontSize: 11, lineHeight: 1.65,
        maxHeight, overflowY: "auto", border: "1px solid #1e293b",
      }}>
        {logs.map((l, i) => (
          <div key={i} style={{ display: "flex", gap: 6, alignItems: "flex-start", marginBottom: 1 }}>
            <span style={{ color: LOG_LEVEL_COLOR[l.level] || "#64748b", minWidth: 10 }}>
              {LOG_LEVEL_ICON[l.level] || "›"}
            </span>
            {l.source && (
              <span style={{ color: "#334155", fontSize: 9, minWidth: 46, paddingTop: 1,
                             textTransform: "uppercase", letterSpacing: "0.05em" }}>
                [{l.source?.slice(0, 8)}]
              </span>
            )}
            {l.ai_model && (
              <span style={{ color: "#6d28d9", fontSize: 9, minWidth: 40, paddingTop: 1 }}>
                {({ ollama: "Ollama", groq: "Groq", gemini: "Gemini", rule_based: "Rules",
                   deepseek: "DeepSeek", claude: "Claude" })[l.ai_model] || l.ai_model}
              </span>
            )}
            <span style={{ color: LOG_LEVEL_COLOR[l.level] || "#94a3b8", flex: 1, wordBreak: "break-word" }}>
              {l.msg}
            </span>
          </div>
        ))}
        {running && (
          <div style={{ color: "#334155", marginTop: 4, animation: "lcBlink 1s step-end infinite" }}>█</div>
        )}
      </div>
      <style>{`
        @keyframes spin    { to { transform: rotate(360deg); } }
        @keyframes lcPulse { 0%,100%{opacity:1} 50%{opacity:.3} }
        @keyframes lcBlink { 0%,100%{opacity:1} 50%{opacity:0} }
      `}</style>
    </div>
  )
}
