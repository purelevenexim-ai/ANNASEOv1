/**
 * SessionStrategyPage.jsx
 * Full-screen dedicated strategy development page for a single KW2 session.
 * Tabs: Dashboard | Configure | Keywords | Research | Strategy & Plan
 */
import { useState, useMemo, useRef, useEffect, useCallback, Fragment } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import * as api from "./api"

const T = {
  purple: "#007AFF", purpleLight: "rgba(0,122,255,0.1)", purpleDark: "#0040DD",
  teal: "#34C759", tealLight: "rgba(52,199,89,0.1)",
  red: "#FF3B30", amber: "#FF9500", amberLight: "rgba(255,149,0,0.1)",
  gray: "#8E8E93", grayLight: "#F2F2F7", border: "rgba(60,60,67,0.12)",
  text: "#000000", textSoft: "rgba(60,60,67,0.55)",
  cardShadow: "0 1px 2px rgba(0,0,0,0.05), 0 0 0 0.5px rgba(0,0,0,0.07)",
}

const MODE_STYLE = {
  brand:  { bg: "#eff6ff", border: "#bfdbfe", badge: "#1e40af", badgeBg: "#dbeafe", icon: "🏢", label: "Brand" },
  expand: { bg: "#f0fdf4", border: "#bbf7d0", badge: "#166534", badgeBg: "#dcfce7", icon: "🌱", label: "Expand" },
  review: { bg: "#faf5ff", border: "#e9d5ff", badge: "#5b21b6", badgeBg: "#ede9fe", icon: "🔍", label: "Review" },
  v2:     { bg: "#f0fdfa", border: "#99f6e4", badge: "#0f766e", badgeBg: "#ccfbf1", icon: "⚡", label: "Smart v2" },
}

const TABS = [
  { id: "overview",      icon: "📊", label: "Dashboard"       },
  { id: "keywords",      icon: "🔑", label: "Keywords"       },
  { id: "intelligence",  icon: "🧠", label: "Research"       },
  { id: "params",        icon: "⚙️", label: "Configure"      },
  { id: "strategy",      icon: "🗺️", label: "Strategy & Plan" },
  { id: "tree",          icon: "🌳", label: "Content Map"     },
]

const CP_DEFAULTS = {
  blogs_per_week: 3,
  duration_weeks: 12,
  content_mix: { informational: 60, transactional: 20, commercial: 20 },
  publishing_cadence: ["Mon", "Wed", "Fri"],
  ai_provider: "auto",
  extra_prompt: "",
  start_date: "",            // ISO date string; empty = "today"
}

// Default per-task AI config (brief generation)
const BRIEF_AI_DEFAULTS = { ai_provider: "auto", custom_prompt: "" }

const PROVIDERS = [
  { id: "auto",   label: "Auto",   icon: "⚡", color: "#6366f1", desc: "Groq → Ollama → Gemini cascade" },
  { id: "groq",   label: "Groq",   icon: "🚀", color: "#f59e0b", desc: "Fast · Free · Llama 3.1-8b" },
  { id: "ollama", label: "Local",  icon: "🏠", color: "#10b981", desc: "Offline · Private · qwen2.5" },
  { id: "gemini", label: "Gemini", icon: "💎", color: "#3b82f6", desc: "Google · Complex analysis" },
  { id: "claude", label: "Claude", icon: "🧠", color: "#8b5cf6", desc: "Best quality · Higher cost" },
]
const COST_EST = { auto: 0, groq: 0, ollama: 0, gemini: 0.001, claude: 0.012 }
const DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

function Card({ children, style = {} }) {
  return <div style={{ background: "#fff", borderRadius: 12, boxShadow: T.cardShadow, padding: 18, ...style }}>{children}</div>
}
function Btn({ children, onClick, disabled, loading, variant = "primary", small, style = {} }) {
  const base = { padding: small ? "5px 12px" : "9px 20px", borderRadius: 9, fontWeight: 600, cursor: (disabled || loading) ? "not-allowed" : "pointer", opacity: (disabled || loading) ? 0.6 : 1, fontSize: small ? 12 : 13, border: "none", transition: "opacity .15s" }
  const v = { primary: { background: T.purple, color: "#fff" }, teal: { background: T.teal, color: "#fff" }, outline: { background: T.grayLight, color: T.text }, danger: { background: "rgba(255,59,48,0.1)", color: T.red }, ghost: { background: "transparent", color: T.gray } }
  return <button onClick={onClick} disabled={disabled || loading} style={{ ...base, ...v[variant], ...style }}>{loading ? "…" : children}</button>
}
function Badge({ label, color = T.purple }) {
  return <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 99, fontSize: 10, fontWeight: 700, background: color + "18", color }}>{label}</span>
}

// ─────────────────────────────────────────────────────────────────────────────
//  GLOBAL AI CHOOSER MODAL
//  Usage: const { chooseAI, AIChooserModal } = useAIChooser()
//         const provider = await chooseAI("Running strategy generation")
//         if (!provider) return   // user cancelled
// ─────────────────────────────────────────────────────────────────────────────
function useAIChooser() {
  const [state, setState] = useState(null) // { title, resolve }

  const chooseAI = (title = "Choose AI Provider") =>
    new Promise(resolve => setState({ title, resolve }))

  const handlePick = (provider) => {
    if (state?.resolve) state.resolve(provider)
    setState(null)
  }

  const handleCancel = () => {
    if (state?.resolve) state.resolve(null)
    setState(null)
  }

  const AIChooserModal = state ? (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9999,
      background: "rgba(0,0,0,0.45)", backdropFilter: "blur(3px)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}
      onClick={e => e.target === e.currentTarget && handleCancel()}
    >
      <div style={{
        background: "#fff", borderRadius: 16, padding: "28px 28px 22px",
        width: 420, maxWidth: "95vw", boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
      }}>
        <div style={{ fontSize: 15, fontWeight: 800, color: T.text, marginBottom: 4 }}>
          🤖 Choose AI Provider
        </div>
        <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 20 }}>
          {state.title}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
          {PROVIDERS.map(p => (
            <button
              key={p.id}
              onClick={() => handlePick(p.id)}
              style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "12px 16px", borderRadius: 10, border: `1.5px solid ${p.color}30`,
                background: p.color + "08", cursor: "pointer", textAlign: "left",
                transition: "all .12s",
              }}
              onMouseEnter={e => { e.currentTarget.style.background = p.color + "15"; e.currentTarget.style.borderColor = p.color + "60" }}
              onMouseLeave={e => { e.currentTarget.style.background = p.color + "08"; e.currentTarget.style.borderColor = p.color + "30" }}
            >
              <span style={{ fontSize: 20, flexShrink: 0 }}>{p.icon}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: p.color }}>{p.label}</div>
                <div style={{ fontSize: 11, color: T.textSoft }}>{p.desc}</div>
              </div>
              {COST_EST[p.id] > 0 && (
                <span style={{ fontSize: 10, color: T.amber, fontWeight: 700, flexShrink: 0 }}>
                  ~${(COST_EST[p.id] * 5).toFixed(3)}/call
                </span>
              )}
              {p.id === "auto" && (
                <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 99, background: p.color + "20", color: p.color, flexShrink: 0 }}>
                  Recommended
                </span>
              )}
            </button>
          ))}
        </div>

        <button onClick={handleCancel}
          style={{ width: "100%", padding: "9px", borderRadius: 8, border: `1px solid ${T.border}`,
            background: T.grayLight, cursor: "pointer", fontSize: 12, fontWeight: 600, color: T.textSoft }}>
          Cancel
        </button>
      </div>
    </div>
  ) : null

  return { chooseAI, AIChooserModal }
}

const intentColor = i => ({ informational: "#3b82f6", transactional: "#10b981", navigational: "#f59e0b", commercial: "#8b5cf6" }[(i || "").toLowerCase()] || "#6b7280")
const scoreColor  = s => s >= 70 ? T.teal : s >= 50 ? T.amber : T.red

function buildStrategyPrereqs({ bizContext = null, validatedData = null, pipelineStatus = null } = {}) {
  const q = pipelineStatus || {}
  const totalQuestions = q?.questions?.count ?? 0
  const scoredQuestions = q?.scoring?.scored ?? 0
  const clusterCount = q?.clusters?.count ?? 0

  const validatedCount =
    validatedData?.count ??
    (Array.isArray(validatedData?.items) ? validatedData.items.length : null) ??
    bizContext?.keywords_validated ??
    0

  const bi = bizContext?.biz_intel || {}
  const hasBizIntel = Boolean(
    (Array.isArray(bi.usps) && bi.usps.length > 0) ||
    (Array.isArray(bi.goals) && bi.goals.length > 0) ||
    (Array.isArray(bi.audience_segments) && bi.audience_segments.length > 0) ||
    (typeof bi.website_summary === "string" && bi.website_summary.trim().length > 0) ||
    (typeof bi.knowledge_summary === "string" && bi.knowledge_summary.trim().length > 0)
  )

  const items = [
    {
      label: "Business Intelligence",
      done: hasBizIntel,
      desc: hasBizIntel ? "USPs, goals, and audience loaded" : "Run business intelligence first",
    },
    {
      label: "Validated Keywords",
      done: validatedCount > 0,
      desc: validatedCount > 0 ? `${validatedCount} keywords validated` : "Run keyword pipeline first",
    },
    {
      label: "Intelligence Questions",
      done: totalQuestions > 0,
      desc: totalQuestions > 0 ? `${totalQuestions} questions generated` : "Run Research Step 1",
    },
    {
      label: "Scored & Clustered",
      done: scoredQuestions > 0 && clusterCount > 0,
      desc:
        scoredQuestions > 0 && clusterCount > 0
          ? `${scoredQuestions} scored, ${clusterCount} clusters`
          : "Run Research scoring and clustering",
    },
  ]

  const readyCount = items.filter(i => i.done).length
  return {
    items,
    readyCount,
    totalCount: items.length,
    allPrereqsMet: readyCount === items.length,
    hasSnapshot: !!pipelineStatus,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  AI TASK CONFIG — compact per-task provider + prompt selector
// ─────────────────────────────────────────────────────────────────────────────
function AITaskConfig({ config, onChange, label = "AI for this task", collapsed = true }) {
  const [open, setOpen] = useState(!collapsed)
  const cur = PROVIDERS.find(p => p.id === config.ai_provider) || PROVIDERS[0]

  return (
    <div style={{ border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden", fontSize: 12 }}>
      {/* Header row */}
      <div
        onClick={() => setOpen(o => !o)}
        style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                 background: T.grayLight, cursor: "pointer", userSelect: "none" }}
      >
        <span style={{ fontSize: 14 }}>{cur.icon}</span>
        <span style={{ fontWeight: 600, color: T.purpleDark, flex: 1 }}>{label}</span>
        <span style={{ fontSize: 10, padding: "1px 7px", borderRadius: 99,
                       background: cur.color + "20", color: cur.color, fontWeight: 700 }}>
          {cur.label}
        </span>
        {COST_EST[config.ai_provider] > 0 && (
          <span style={{ fontSize: 10, color: T.amber, fontWeight: 600 }}>
            ~${(COST_EST[config.ai_provider] * 5).toFixed(3)}/brief
          </span>
        )}
        {COST_EST[config.ai_provider] === 0 && (
          <span style={{ fontSize: 10, color: T.teal, fontWeight: 600 }}>Free</span>
        )}
        {config.custom_prompt && (
          <span style={{ fontSize: 10, color: "#8b5cf6", padding: "1px 6px",
                         borderRadius: 99, background: "#ede9fe" }}>+ prompt</span>
        )}
        <span style={{ color: T.gray, fontSize: 10 }}>{open ? "▲" : "▼"}</span>
      </div>

      {/* Body */}
      {open && (
        <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 10, background: "#fff" }}>
          {/* Provider chips */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {PROVIDERS.map(p => {
              const active = config.ai_provider === p.id
              return (
                <button
                  key={p.id}
                  onClick={() => onChange({ ...config, ai_provider: p.id })}
                  title={p.desc}
                  style={{
                    padding: "4px 10px", borderRadius: 20, fontSize: 11, fontWeight: active ? 700 : 500,
                    border: active ? `2px solid ${p.color}` : `1px solid ${T.border}`,
                    background: active ? p.color + "15" : "#fff",
                    color: active ? p.color : T.textSoft, cursor: "pointer",
                  }}
                >
                  {p.icon} {p.label}
                  {COST_EST[p.id] > 0 && (
                    <span style={{ marginLeft: 4, fontSize: 9, opacity: 0.7 }}>
                      ${COST_EST[p.id].toFixed(3)}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Custom prompt */}
          <textarea
            value={config.custom_prompt}
            onChange={e => onChange({ ...config, custom_prompt: e.target.value })}
            placeholder="Optional: Add context or focus for this AI task… (e.g. 'emphasize beginner-friendly sections')"
            rows={2}
            style={{
              width: "100%", padding: "6px 8px", borderRadius: 7,
              border: `1px solid ${T.border}`, fontSize: 12,
              resize: "vertical", lineHeight: 1.5, boxSizing: "border-box",
            }}
          />
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  AI COST HUB — usage table + summary for a session
// ─────────────────────────────────────────────────────────────────────────────
function AICostHub({ projectId, sessionId, refreshKey = 0 }) {
  const [open, setOpen] = useState(false)

  const { data, refetch, isFetching } = useQuery({
    queryKey: ["ai-usage", projectId, sessionId, refreshKey],
    queryFn: () => api.getSessionAiUsage(projectId, sessionId),
    enabled: !!sessionId && open,
    staleTime: 10_000,
    retry: false,
  })

  // Auto-refresh when open
  useEffect(() => {
    if (!open) return
    const id = setInterval(() => refetch(), 15_000)
    return () => clearInterval(id)
  }, [open, refetch])

  const entries = data?.entries || []
  const summary = data?.summary || {}

  const providerColors = { groq: "#f59e0b", ollama: "#10b981", gemini: "#3b82f6", claude: "#8b5cf6", auto: "#6366f1" }

  return (
    <div style={{ border: `1px solid ${T.border}`, borderRadius: 10, overflow: "hidden" }}>
      {/* Header */}
      <div
        onClick={() => setOpen(o => !o)}
        style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
                 background: T.grayLight, cursor: "pointer", userSelect: "none" }}
      >
        <span style={{ fontSize: 16 }}>💰</span>
        <span style={{ fontWeight: 700, color: T.purpleDark, flex: 1, fontSize: 13 }}>AI Cost Hub</span>
        {summary.total_calls > 0 && (
          <>
            <span style={{ fontSize: 11, color: T.textSoft }}>{summary.total_calls} calls</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: summary.total_cost_usd > 0 ? T.amber : T.teal }}>
              {summary.total_cost_usd > 0 ? `$${Number(summary.total_cost_usd).toFixed(4)}` : "Free"}
            </span>
          </>
        )}
        {!sessionId && (
          <span style={{ fontSize: 11, color: T.textSoft }}>Generate a strategy to track costs</span>
        )}
        {isFetching && <span style={{ fontSize: 10, color: T.textSoft }}>↻</span>}
        <span style={{ color: T.gray, fontSize: 11 }}>{open ? "▲" : "▼"}</span>
      </div>

      {open && (
        <div style={{ padding: "14px", display: "flex", flexDirection: "column", gap: 12 }}>
          {!sessionId ? (
            <div style={{ fontSize: 12, color: T.textSoft, textAlign: "center", padding: 16 }}>
              Cost tracking is available after generating a strategy.
            </div>
          ) : entries.length === 0 ? (
            <div style={{ fontSize: 12, color: T.textSoft, textAlign: "center", padding: 16 }}>
              No AI usage recorded yet. Generate a strategy or briefs to start tracking.
              <br /><button onClick={() => refetch()} style={{ marginTop: 8, fontSize: 11, color: T.purple, background: "none", border: "none", cursor: "pointer" }}>↻ Refresh</button>
            </div>
          ) : (
            <>
              {/* Summary row */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
                {[
                  { label: "Total Calls", val: summary.total_calls || 0, color: T.purpleDark },
                  { label: "Total Tokens", val: ((summary.total_tokens || 0) / 1000).toFixed(1) + "k", color: "#6366f1" },
                  { label: "Total Cost", val: summary.total_cost_usd > 0 ? `$${Number(summary.total_cost_usd).toFixed(4)}` : "Free", color: summary.total_cost_usd > 0 ? T.amber : T.teal },
                  { label: "Avg Latency", val: summary.avg_latency_ms ? `${Math.round(summary.avg_latency_ms)}ms` : "—", color: T.gray },
                ].map(s => (
                  <div key={s.label} style={{ background: T.grayLight, borderRadius: 8, padding: "8px 10px", textAlign: "center" }}>
                    <div style={{ fontSize: 14, fontWeight: 800, color: s.color }}>{s.val}</div>
                    <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{s.label}</div>
                  </div>
                ))}
              </div>

              {/* By provider mini-bars */}
              {summary.by_provider && Object.keys(summary.by_provider).length > 0 && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: T.textSoft, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>By Provider</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    {Object.entries(summary.by_provider).map(([prov, info]) => {
                      const col = providerColors[prov] || T.gray
                      const pct = summary.total_calls > 0 ? Math.round((info.calls / summary.total_calls) * 100) : 0
                      return (
                        <div key={prov} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: 11, fontWeight: 600, color: col, minWidth: 56 }}>{prov}</span>
                          <div style={{ flex: 1, height: 6, background: T.grayLight, borderRadius: 3, overflow: "hidden" }}>
                            <div style={{ height: "100%", width: `${pct}%`, background: col, borderRadius: 3 }} />
                          </div>
                          <span style={{ fontSize: 10, color: T.textSoft, minWidth: 48, textAlign: "right" }}>
                            {info.calls} calls
                          </span>
                          <span style={{ fontSize: 10, fontWeight: 700, color: info.cost_usd > 0 ? T.amber : T.teal, minWidth: 52, textAlign: "right" }}>
                            {info.cost_usd > 0 ? `$${Number(info.cost_usd).toFixed(4)}` : "Free"}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Usage table (last 20) */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.textSoft, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>
                  Recent Calls (last {Math.min(entries.length, 20)})
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                    <thead>
                      <tr style={{ background: T.grayLight }}>
                        {["Time", "Task", "Provider", "Tokens In", "Tokens Out", "Cost", "Latency"].map(h => (
                          <th key={h} style={{ padding: "5px 8px", textAlign: "left", fontWeight: 700,
                                              color: T.textSoft, borderBottom: `1px solid ${T.border}` }}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {entries.slice(0, 20).map((e, i) => {
                        const col = providerColors[e.provider] || T.gray
                        const ts = new Date(e.created_at).toLocaleTimeString()
                        return (
                          <tr key={i} style={{ borderBottom: `1px solid ${T.border}`, background: i % 2 === 0 ? "#fff" : T.grayLight + "80" }}>
                            <td style={{ padding: "4px 8px", color: T.textSoft }}>{ts}</td>
                            <td style={{ padding: "4px 8px", fontWeight: 600 }}>{e.task}</td>
                            <td style={{ padding: "4px 8px" }}>
                              <span style={{ padding: "1px 7px", borderRadius: 99, background: col + "20",
                                             color: col, fontWeight: 700, fontSize: 10 }}>{e.provider}</span>
                            </td>
                            <td style={{ padding: "4px 8px", color: T.textSoft }}>{(e.input_tokens || 0).toLocaleString()}</td>
                            <td style={{ padding: "4px 8px", color: T.textSoft }}>{(e.output_tokens || 0).toLocaleString()}</td>
                            <td style={{ padding: "4px 8px", fontWeight: 700,
                                         color: (e.cost_usd || 0) > 0 ? T.amber : T.teal }}>
                              {(e.cost_usd || 0) > 0 ? `$${Number(e.cost_usd).toFixed(5)}` : "Free"}
                            </td>
                            <td style={{ padding: "4px 8px", color: T.textSoft }}>
                              {e.latency_ms ? `${Math.round(e.latency_ms)}ms` : "—"}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                {entries.length > 20 && (
                  <div style={{ fontSize: 11, color: T.textSoft, textAlign: "center", marginTop: 6 }}>
                    +{entries.length - 20} more entries
                  </div>
                )}
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button onClick={() => refetch()} disabled={isFetching}
                  style={{ fontSize: 11, color: T.purple, background: "none", border: `1px solid ${T.border}`,
                           borderRadius: 7, padding: "4px 10px", cursor: "pointer" }}>
                  {isFetching ? "↻ Refreshing…" : "↻ Refresh"}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB: OVERVIEW
// ─────────────────────────────────────────────────────────────────────────────
const PHASE_META = [
  { n: 1, label: "Business Analysis", icon: "🏢", desc: "Crawl website, extract USPs, goals, audience" },
  { n: 2, label: "Keyword Universe",  icon: "🌐", desc: "Seed → pillar-based keyword generation" },
  { n: 3, label: "Validation",        icon: "✅", desc: "Score, filter, intent-classify keywords" },
  { n: 4, label: "Score + Cluster",   icon: "📊", desc: "Opportunity scores, grouping by theme" },
  { n: 5, label: "Tree + Top 100",    icon: "🌲", desc: "Hierarchy map, top keyword selection" },
  { n: 6, label: "Knowledge Graph",   icon: "🧠", desc: "Entity relationships, semantic linking" },
  { n: 7, label: "Internal Links",    icon: "🔗", desc: "Link recommendations between pages" },
  { n: 8, label: "Content Calendar",  icon: "📅", desc: "Scheduled publishing plan per week" },
  { n: 9, label: "Strategy",          icon: "🗺️", desc: "AI strategy, pillar plans, content priorities" },
]

// ─────────────────────────────────────────────────────────────────────────────
//  STRATEGY HEALTH SCORE — composite readiness meter
// ─────────────────────────────────────────────────────────────────────────────
function computeHealthScore(session, bizContext, strat, validatedData) {
  const bi = bizContext?.biz_intel || {}
  const scores = []

  // 1. Business intelligence (25 pts)
  let biScore = 0
  if (bi.has_website_crawl) biScore += 7
  if (bi.has_competitor_crawl) biScore += 6
  if (bi.usps?.length) biScore += 4
  if (bi.goals?.length) biScore += 4
  if (bi.audience_segments?.length) biScore += 4
  scores.push({ label: "Business Intel", score: biScore, max: 25, icon: "🧩" })

  // 2. Keyword coverage (30 pts)
  const validated = session?.validated_total || validatedData?.items?.length || 0
  const kwScore = Math.min(30, Math.round((validated / 50) * 30))
  scores.push({ label: "Keywords", score: kwScore, max: 30, icon: "🔑", detail: `${validated} validated` })

  // 3. Pillar coverage (20 pts)
  const pillars = Object.keys(bizContext?.pillar_distribution || {}).length ||
    bizContext?.profile?.pillars?.length || 0
  const pillarScore = Math.min(20, pillars * 5)
  scores.push({ label: "Pillar Coverage", score: pillarScore, max: 20, icon: "🏛️", detail: `${pillars} pillars` })

  // 4. Pipeline completion (15 pts)
  const donePh = [1,2,3,4,5,6,7,8,9].filter(n => session?.[`phase${n}_done`]).length
  const pipeScore = Math.round((donePh / 9) * 15)
  scores.push({ label: "Pipeline", score: pipeScore, max: 15, icon: "⚙️", detail: `${donePh}/9 phases` })

  // 5. Strategy completeness (10 pts)
  let stratScore = 0
  if (strat) {
    stratScore += 4
    if (strat.pillar_strategies?.length) stratScore += 2
    if (strat.quick_wins?.length) stratScore += 1
    if (strat.content_priorities?.length) stratScore += 1
    if (strat.competitive_gaps?.length) stratScore += 1
    if (strat.timeline?.length) stratScore += 1
  }
  scores.push({ label: "Strategy", score: stratScore, max: 10, icon: "🗺️", detail: strat ? "Generated" : "Not generated" })

  const total = scores.reduce((s, c) => s + c.score, 0)
  const maxTotal = scores.reduce((s, c) => s + c.max, 0)
  return { total, maxTotal, pct: Math.round((total / maxTotal) * 100), breakdown: scores }
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB: OVERVIEW
// ─────────────────────────────────────────────────────────────────────────────
function OverviewTab({ session, validatedData, pillarStats, strat, bizContext, onRunPhase9, onGoToTab, running, logs, projectId }) {
  const [showBizDetail, setShowBizDetail] = useState(false)

  const donePhasesRaw = PHASE_META.filter(p => session?.[`phase${p.n}_done`]).length
  const totalSteps = session?.mode === "expand" ? 8 : 9
  const doneSteps  = Math.min(donePhasesRaw, totalSteps)
  const pct = Math.round((doneSteps / totalSteps) * 100)

  // Pillar breakdown
  const pillarRows = useMemo(() => {
    const statsArr = pillarStats?.pillars || []
    if (statsArr.length) return statsArr
    return (strat?.priority_pillars || []).map(p => ({
      pillar: typeof p === "string" ? p : p?.pillar || "",
      count: null,
      opportunity_score: typeof p === "object" ? p?.opportunity_score : null,
    }))
  }, [pillarStats, strat])

  // Top 5 validated keywords by final_score
  const top5 = useMemo(() => {
    const items = validatedData?.items || []
    return [...items].sort((a, b) => (b.final_score || b.score || 0) - (a.final_score || a.score || 0)).slice(0, 5)
  }, [validatedData])

  const _safeHeadline = (s) => {
    if (!s) return ""
    const direct = s?.strategy_summary?.headline
    if (direct && typeof direct === "string") {
      const trimmed = direct.trimStart()
      if (!trimmed.startsWith("{") && !trimmed.startsWith("[") && direct.length < 600) return direct
      if (trimmed.startsWith("{")) {
        try {
          const parsed = JSON.parse(direct)
          const nested = parsed?.strategy_summary?.headline || parsed?.headline
          if (nested && typeof nested === "string" && !nested.trimStart().startsWith("{")) return nested
        } catch {}
      }
    }
    const exec = s?.executive_summary
    if (!exec || typeof exec !== "string") return ""
    const trimmed = exec.trimStart()
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try { const parsed = JSON.parse(exec); const n = parsed?.strategy_summary?.headline || parsed?.headline; if (n) return String(n) } catch {}
      return ""
    }
    return exec.length > 220 ? exec.slice(0, 217) + "…" : exec
  }
  const headline = _safeHeadline(strat)

  // Biz Intel summary
  const bi = bizContext?.biz_intel || {}
  const biProfile = bizContext?.profile || {}
  const biReady = !!(bi.has_website_crawl || bi.usps?.length || bi.goals?.length)

  const PILLAR_COLORS = ["#007AFF","#34C759","#FF9500","#AF52DE","#FF3B30","#5AC8FA","#FFCC00"]
  const health = useMemo(
    () => computeHealthScore(session, bizContext, strat, validatedData),
    [session, bizContext, strat, validatedData]
  )

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

      {/* ── Top stat cards ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
        {[
          { label: "Universe",   val: (session?.universe_total || 0).toLocaleString(),   color: T.purple,    icon: "🌐" },
          { label: "Validated",  val: (session?.validated_total || 0).toLocaleString(),  color: T.teal,      icon: "✅" },
          { label: "Pillars",    val: pillarRows.length || (biProfile.pillars?.length) || "—", color: T.purpleDark, icon: "🏛️" },
          { label: "Progress",   val: `${pct}%`,                                          color: pct === 100 ? T.teal : T.amber, icon: "📈" },
          { label: "Strategy",   val: session?.phase9_done ? "Ready" : "Pending",         color: session?.phase9_done ? T.teal : T.gray, icon: "🗺️" },
        ].map(s => (
          <Card key={s.label} style={{ textAlign: "center", padding: "12px 8px" }}>
            <div style={{ fontSize: 18, marginBottom: 2 }}>{s.icon}</div>
            <div style={{ fontSize: 20, fontWeight: 800, color: s.color }}>{s.val}</div>
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2, textTransform: "uppercase", letterSpacing: ".06em" }}>{s.label}</div>
          </Card>
        ))}
      </div>

      {/* ── Workflow Guide (the primary navigation aid) ── */}
      {(() => {
        const hasKw      = (session?.validated_total || 0) > 0
        const hasBi      = biReady
        const hasPhase3  = !!session?.phase3_done
        const hasPhase6  = !!session?.phase6_done
        const hasPhase9  = !!session?.phase9_done

        // Derive intelligence completion from pipeline meta (approximation from session flags)
        // Phases 1-4 = keyword pipeline; phase6 = scoring/clustering
        const hasIntel   = hasBi && hasPhase3 && hasPhase6

        // Determine the "next unlocked step" to highlight
        const steps = [
          {
            n: 1, icon: "🔑", label: "Build Keywords",
            desc: hasKw ? `${(session?.validated_total || 0).toLocaleString()} keywords validated` : "Generate and validate keyword universe (Phases 1–3)",
            done: hasKw,
            tab: "keywords",
            cta: hasKw ? "View Keywords" : "Go to Keywords",
          },
          {
            n: 2, icon: "🧠", label: "Research & Intelligence",
            desc: hasIntel
              ? "Business intelligence, questions, scoring, and clusters ready"
              : hasBi
                ? "BI ready — run question generation & clustering in Research tab"
                : "Analyze website, competitors, and build question intelligence",
            done: hasIntel,
            tab: "intelligence",
            cta: hasIntel ? "View Research" : hasBi ? "Continue Research" : "Start Research",
          },
          {
            n: 3, icon: "⚙️", label: "Configure Strategy",
            desc: hasPhase9
              ? "Strategy generated — adjust parameters to regenerate"
              : hasIntel
                ? "Research complete — set publishing cadence and generate strategy"
                : "Complete Research step first",
            done: hasPhase9,
            tab: "params",
            cta: hasPhase9 ? "Adjust Strategy" : "Configure",
            locked: !hasIntel && !hasPhase9,
          },
          {
            n: 4, icon: "🗺️", label: "Strategy & Content Plan",
            desc: hasPhase9
              ? "View strategy, weekly content plan, and generate articles"
              : "Generate strategy first",
            done: hasPhase9,
            tab: "strategy",
            cta: "View Strategy",
            locked: !hasPhase9,
          },
        ]

        // Find the first incomplete non-locked step
        const nextStep = steps.find(s => !s.done && !s.locked) || steps[steps.length - 1]

        return (
          <Card style={{ padding: "14px 18px", border: `1px solid ${T.purple}25`, background: `${T.purple}04` }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>
              Workflow — {steps.filter(s => s.done).length}/{steps.length} stages complete
            </div>
            <div style={{ display: "flex", gap: 0, alignItems: "stretch", flexWrap: "wrap" }}>
              {steps.map((step, idx) => {
                const isNext = step === nextStep
                const col = step.done ? T.teal : isNext ? T.purple : T.gray
                return (
                  <Fragment key={step.n}>
                    <div style={{
                      flex: "1 1 160px", display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 6,
                      padding: "10px 12px", borderRadius: 9, cursor: step.locked ? "default" : "pointer",
                      background: step.done ? T.teal + "10" : isNext ? T.purple + "10" : "transparent",
                      border: `1.5px solid ${step.done ? T.teal + "50" : isNext ? T.purple + "40" : T.border}`,
                      opacity: step.locked ? 0.45 : 1,
                      transition: "all .1s",
                    }}
                      onClick={() => !step.locked && onGoToTab && onGoToTab(step.tab)}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 6, width: "100%" }}>
                        <div style={{
                          width: 22, height: 22, borderRadius: "50%",
                          background: step.done ? T.teal : isNext ? T.purple : "#e5e7eb",
                          color: (step.done || isNext) ? "#fff" : T.textSoft,
                          fontSize: 11, fontWeight: 800, flexShrink: 0,
                          display: "flex", alignItems: "center", justifyContent: "center",
                        }}>
                          {step.done ? "✓" : step.n}
                        </div>
                        <span style={{ fontSize: 12, fontWeight: 700, color: col }}>{step.icon} {step.label}</span>
                        {isNext && <span style={{ marginLeft: "auto", fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 99, background: T.purple, color: "#fff" }}>NEXT</span>}
                      </div>
                      <div style={{ fontSize: 10, color: T.textSoft, lineHeight: 1.4 }}>{step.desc}</div>
                      {!step.locked && (
                        <button onClick={e => { e.stopPropagation(); onGoToTab && onGoToTab(step.tab) }}
                          style={{ marginTop: 2, padding: "3px 10px", borderRadius: 6, border: `1px solid ${col}50`,
                            background: step.done ? T.teal + "10" : isNext ? T.purple + "10" : "#f5f5f5",
                            color: col, fontSize: 10, fontWeight: 700, cursor: "pointer" }}>
                          {step.cta} →
                        </button>
                      )}
                    </div>
                    {idx < steps.length - 1 && (
                      <div style={{ width: 18, display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 14, color: T.border, flexShrink: 0 }}>→</div>
                    )}
                  </Fragment>
                )
              })}
            </div>
          </Card>
        )
      })()}

      {/* ── Phase pipeline ── */}
      <Card style={{ padding: "14px 18px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark }}>Pipeline Progress · {doneSteps}/{totalSteps} phases complete</div>
          <div style={{ fontSize: 11, color: pct === 100 ? T.teal : T.amber, fontWeight: 700 }}>{pct}%</div>
        </div>
        {/* Progress bar */}
        <div style={{ height: 5, background: T.grayLight, borderRadius: 3, overflow: "hidden", marginBottom: 12 }}>
          <div style={{ height: "100%", width: `${pct}%`, background: pct === 100 ? T.teal : T.purple, borderRadius: 3, transition: "width .5s" }} />
        </div>
        {/* Phase tiles */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(9, 1fr)", gap: 4 }}>
          {PHASE_META.map(ph => {
            if (ph.n > totalSteps) return null
            const done = !!session?.[`phase${ph.n}_done`]
            const isCurrent = !done && PHASE_META.slice(0, ph.n - 1).every(p => session?.[`phase${p.n}_done`])
            return (
              <div
                key={ph.n}
                title={`Phase ${ph.n}: ${ph.label}\n${ph.desc}`}
                style={{
                  display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                  padding: "8px 4px", borderRadius: 8,
                  background: done ? T.teal + "15" : isCurrent ? T.purple + "12" : T.grayLight,
                  border: `1px solid ${done ? T.teal + "50" : isCurrent ? T.purple + "40" : T.border}`,
                  cursor: "default",
                }}
              >
                <div style={{
                  width: 28, height: 28, borderRadius: "50%",
                  background: done ? T.teal : isCurrent ? T.purple : "#e5e7eb",
                  color: done || isCurrent ? "#fff" : T.textSoft,
                  fontSize: done ? 13 : 12, fontWeight: 800,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  boxShadow: done ? `0 0 0 2px ${T.teal}40` : isCurrent ? `0 0 0 2px ${T.purple}40` : "none",
                }}>
                  {done ? "✓" : ph.n}
                </div>
                <div style={{ fontSize: 9, fontWeight: done ? 700 : 500, color: done ? T.teal : isCurrent ? T.purple : T.textSoft, textAlign: "center", lineHeight: 1.2 }}>
                  {ph.icon}
                </div>
                <div style={{ fontSize: 9, color: done ? "#065f46" : isCurrent ? T.purpleDark : T.textSoft, textAlign: "center", lineHeight: 1.2, fontWeight: done ? 600 : 400 }}>
                  {ph.label.split(" ")[0]}
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      {/* ── Strategy Health Score ── */}
      <Card style={{ border: `1px solid ${health.pct >= 80 ? T.teal + "50" : health.pct >= 50 ? T.amber + "50" : T.red + "40"}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <div style={{ position: "relative", width: 52, height: 52, flexShrink: 0 }}>
            <svg width="52" height="52" viewBox="0 0 52 52">
              <circle cx="26" cy="26" r="22" fill="none" stroke={T.grayLight} strokeWidth="5"/>
              <circle cx="26" cy="26" r="22" fill="none"
                stroke={health.pct >= 80 ? T.teal : health.pct >= 50 ? T.amber : T.red}
                strokeWidth="5" strokeLinecap="round"
                strokeDasharray={`${Math.round(health.pct * 1.382)} ${Math.round((100 - health.pct) * 1.382)}`}
                strokeDashoffset="34.5" transform="rotate(-90 26 26)"/>
            </svg>
            <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 13, fontWeight: 800, color: health.pct >= 80 ? T.teal : health.pct >= 50 ? T.amber : T.red }}>
              {health.pct}
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: T.text }}>
              Strategy Readiness: {health.pct >= 80 ? "Excellent" : health.pct >= 60 ? "Good" : health.pct >= 40 ? "Fair" : "Needs Work"}
            </div>
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
              {health.total}/{health.maxTotal} points · {health.pct >= 80 ? "You're ready to generate a strong AI strategy" : health.pct >= 50 ? "A few more improvements would strengthen the strategy" : "Complete more pipeline phases for better results"}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {health.breakdown.map(b => {
            const p = Math.round((b.score / b.max) * 100)
            const col = p >= 80 ? T.teal : p >= 50 ? T.amber : T.red
            return (
              <div key={b.label} style={{ flex: "1 1 140px", padding: "8px 10px", background: T.grayLight, borderRadius: 9, border: `1px solid ${col}30` }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: T.text }}>{b.icon} {b.label}</span>
                  <span style={{ fontSize: 10, fontWeight: 700, color: col }}>{b.score}/{b.max}</span>
                </div>
                <div style={{ height: 3, background: "#e5e7eb", borderRadius: 2, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${p}%`, background: col, borderRadius: 2 }}/>
                </div>
                {b.detail && <div style={{ fontSize: 9, color: T.textSoft, marginTop: 3 }}>{b.detail}</div>}
              </div>
            )
          })}
        </div>
      </Card>

      {/* ── Business Intelligence Context ── */}
      <Card style={{ border: biReady ? `1px solid ${T.teal}30` : `1px solid ${T.border}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: biReady || showBizDetail ? 12 : 0 }}>
          <span style={{ fontSize: 16 }}>🧩</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark }}>Business Context Collected</div>
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 1 }}>
              Data injected into AI generation — richer context = better strategy
            </div>
          </div>
          <button onClick={() => setShowBizDetail(v => !v)}
            style={{ fontSize: 11, color: T.purple, background: "none", border: `1px solid ${T.border}`,
                     borderRadius: 6, padding: "3px 10px", cursor: "pointer" }}>
            {showBizDetail ? "Hide" : "Details"}
          </button>
        </div>

        {/* Status chips */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {[
            { label: "Website Crawled",    ok: bi.has_website_crawl },
            { label: "Competitors Analyzed", ok: bi.has_competitor_crawl },
            { label: `${bi.usps?.length || 0} USPs`,      ok: (bi.usps?.length || 0) > 0 },
            { label: `${bi.goals?.length || 0} Goals`,    ok: (bi.goals?.length || 0) > 0 },
            { label: `${bi.audience_segments?.length || 0} Audience Segments`, ok: (bi.audience_segments?.length || 0) > 0 },
            { label: `${bizContext?.pages_count || 0} Pages`,  ok: (bizContext?.pages_count || 0) > 0 },
            { label: `${bizContext?.competitors?.length || 0} Competitors`, ok: (bizContext?.competitors?.length || 0) > 0 },
            { label: "Knowledge Summary",  ok: !!bi.knowledge_summary },
            { label: "Website Summary",    ok: !!bi.website_summary },
            { label: "SEO Strategy",       ok: !!bi.seo_strategy },
          ].map(c => (
            <span key={c.label} style={{
              display: "inline-flex", alignItems: "center", gap: 4,
              padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 600,
              background: c.ok ? T.teal + "15" : T.grayLight,
              color: c.ok ? "#065f46" : T.textSoft,
              border: `1px solid ${c.ok ? T.teal + "40" : T.border}`,
            }}>
              <span>{c.ok ? "✓" : "○"}</span>
              {c.label}
            </span>
          ))}
        </div>

        {/* Detail expansion */}
        {showBizDetail && bizContext && (
          <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
            {/* Profile */}
            {(biProfile.universe || biProfile.business_type) && (
              <div style={{ padding: "10px 14px", background: T.grayLight, borderRadius: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 6 }}>Business Profile</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                  {biProfile.universe && <div style={{ fontSize: 12 }}><span style={{ color: T.textSoft }}>Universe: </span>{biProfile.universe}</div>}
                  {biProfile.business_type && <div style={{ fontSize: 12 }}><span style={{ color: T.textSoft }}>Type: </span>{biProfile.business_type}</div>}
                  {biProfile.geo_scope && <div style={{ fontSize: 12 }}><span style={{ color: T.textSoft }}>Geo: </span>{biProfile.geo_scope}</div>}
                  {biProfile.pillars?.length > 0 && <div style={{ fontSize: 12 }}><span style={{ color: T.textSoft }}>Pillars: </span>{biProfile.pillars.join(", ")}</div>}
                </div>
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {/* USPs */}
              {bi.usps?.length > 0 && (
                <div style={{ background: "#eff6ff", borderRadius: 8, padding: "10px 12px", border: `1px solid #bfdbfe` }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#1e40af", marginBottom: 6 }}>Unique Selling Points</div>
                  {bi.usps.map((u, i) => <div key={i} style={{ fontSize: 11, color: T.text, marginBottom: 3 }}>• {u}</div>)}
                </div>
              )}
              {/* Goals */}
              {bi.goals?.length > 0 && (
                <div style={{ background: "#f0fdf4", borderRadius: 8, padding: "10px 12px", border: `1px solid #bbf7d0` }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#166534", marginBottom: 6 }}>Business Goals</div>
                  {bi.goals.map((g, i) => <div key={i} style={{ fontSize: 11, color: T.text, marginBottom: 3 }}>• {g}</div>)}
                </div>
              )}
              {/* Audience segments */}
              {bi.audience_segments?.length > 0 && (
                <div style={{ background: "#faf5ff", borderRadius: 8, padding: "10px 12px", border: `1px solid #e9d5ff` }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#5b21b6", marginBottom: 6 }}>Audience Segments</div>
                  {bi.audience_segments.map((a, i) => <div key={i} style={{ fontSize: 11, color: T.text, marginBottom: 3 }}>• {a}</div>)}
                </div>
              )}
              {/* Pricing model */}
              {bi.pricing_model && (
                <div style={{ background: T.amberLight, borderRadius: 8, padding: "10px 12px", border: `1px solid ${T.amber}33` }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#b45309", marginBottom: 6 }}>Pricing Model</div>
                  <div style={{ fontSize: 12, color: T.text }}>{bi.pricing_model}</div>
                </div>
              )}
            </div>

            {/* Summaries */}
            {bi.website_summary && (
              <div style={{ padding: "10px 14px", background: T.grayLight, borderRadius: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 4 }}>Website Summary</div>
                <div style={{ fontSize: 12, color: T.text, lineHeight: 1.6 }}>{bi.website_summary}</div>
              </div>
            )}
            {bi.knowledge_summary && (
              <div style={{ padding: "10px 14px", background: T.grayLight, borderRadius: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 4 }}>Knowledge Summary</div>
                <div style={{ fontSize: 12, color: T.text, lineHeight: 1.6 }}>{bi.knowledge_summary}</div>
              </div>
            )}

            {/* Pages sample */}
            {bizContext.pages_sample?.length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.textSoft, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>
                  Pages Analyzed ({bizContext.pages_count} total)
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 6 }}>
                  {bizContext.pages_sample.map((p, i) => (
                    <div key={i} style={{ padding: "7px 10px", background: "#fff", borderRadius: 7, border: `1px solid ${T.border}`, fontSize: 11 }}>
                      {p.primary_topic && <div style={{ fontWeight: 600, color: T.text, marginBottom: 2 }}>{p.primary_topic}</div>}
                      <div style={{ color: T.textSoft }}>{[p.page_type, p.funnel_stage].filter(Boolean).join(" · ")}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Competitors */}
            {bizContext.competitors?.length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.textSoft, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>
                  Competitors Analyzed
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {bizContext.competitors.map((c, i) => (
                    <div key={i} style={{ padding: "8px 12px", background: "#fff", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 11 }}>
                      <div style={{ fontWeight: 700, color: T.red, marginBottom: 4 }}>{c.domain}</div>
                      {c.weaknesses?.length > 0 && (
                        <div style={{ color: T.textSoft }}>Weaknesses: {c.weaknesses.slice(0, 2).join(", ")}</div>
                      )}
                      {c.missed_opportunities?.length > 0 && (
                        <div style={{ color: T.teal, marginTop: 2 }}>Gaps: {c.missed_opportunities.slice(0, 2).join(", ")}</div>
                      )}
                      {c.top_keywords?.length > 0 && (
                        <div style={{ color: T.textSoft, marginTop: 2 }}>Top kws: {c.top_keywords.slice(0, 4).join(", ")}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Pillar distribution from validated keywords */}
            {bizContext.pillar_distribution && Object.keys(bizContext.pillar_distribution).length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.textSoft, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>
                  Keyword Distribution by Pillar ({bizContext.keywords_validated} validated)
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {Object.entries(bizContext.pillar_distribution).sort((a, b) => b[1] - a[1]).map(([pl, cnt], i) => {
                    const total = Object.values(bizContext.pillar_distribution).reduce((s, v) => s + v, 0) || 1
                    const p = Math.round((cnt / total) * 100)
                    const col = PILLAR_COLORS[i % PILLAR_COLORS.length]
                    return (
                      <div key={pl} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: col, flexShrink: 0 }} />
                        <div style={{ fontSize: 12, fontWeight: 500, minWidth: 160 }}>{pl}</div>
                        <div style={{ flex: 1, height: 6, background: T.grayLight, borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ height: "100%", width: `${p}%`, background: col, borderRadius: 3 }} />
                        </div>
                        <div style={{ fontSize: 11, fontWeight: 700, color: col, minWidth: 44, textAlign: "right" }}>{cnt} kw</div>
                        <div style={{ fontSize: 10, color: T.textSoft, minWidth: 32 }}>{p}%</div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* ── Pillars + top keywords side by side ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Pillar breakdown */}
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>Keyword Pillars</div>
          {pillarRows.length === 0 ? (
            <div style={{ fontSize: 12, color: T.textSoft }}>No pillar data yet. Run Phase 4+ to generate clusters.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {pillarRows.map((p, i) => {
                const total = pillarRows.reduce((s, r) => s + (r.count || 0), 0) || 1
                const pct = p.count ? Math.round((p.count / total) * 100) : null
                const col = PILLAR_COLORS[i % PILLAR_COLORS.length]
                return (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: col, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{p.pillar}</span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: col }}>
                          {p.count != null ? `${p.count} kw` : p.opportunity_score != null ? `${p.opportunity_score} opp` : ""}
                        </span>
                      </div>
                      {pct != null && (
                        <div style={{ height: 4, background: T.grayLight, borderRadius: 2, overflow: "hidden" }}>
                          <div style={{ height: "100%", width: `${pct}%`, background: col, borderRadius: 2 }} />
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        {/* Top 5 keywords */}
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>Top 5 Keywords by Score</div>
          {top5.length === 0 ? (
            <div style={{ fontSize: 12, color: T.textSoft }}>No validated keywords yet. Run Phase 3 to validate.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {top5.map((kw, i) => {
                const sc = Math.round(kw.final_score || kw.score || 0)
                return (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", background: T.grayLight, borderRadius: 7 }}>
                    <div style={{ width: 20, height: 20, borderRadius: "50%", background: scoreColor(sc), color: "#fff",
                      fontSize: 9, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      {i + 1}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{kw.keyword}</div>
                      <div style={{ fontSize: 9, color: T.textSoft }}>{kw.pillar}</div>
                    </div>
                    <div style={{ display: "flex", gap: 4, alignItems: "center", flexShrink: 0 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: scoreColor(sc) }}>{sc}</span>
                      {kw.intent && <Badge label={kw.intent} color={intentColor(kw.intent)} />}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </div>

      {/* ── AEO / AI Search readiness ── */}
      {strat?.aeo_strategy && (
        <Card style={{ border: `1px solid ${T.teal}30`, background: "linear-gradient(135deg,#f0fdf4 0%,#f8faff 100%)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 16 }}>🤖</span>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.teal }}>AI Search (AEO) Visibility Plan</div>
            <span style={{ marginLeft: "auto", fontSize: 10, padding: "2px 8px", borderRadius: 99, background: T.teal + "15", color: T.teal, fontWeight: 700 }}>
              ChatGPT · Gemini · Perplexity
            </span>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {Array.isArray(strat.aeo_strategy.ai_visibility_targets) && strat.aeo_strategy.ai_visibility_targets.map((t, i) => (
              <span key={i} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 99, background: "#fff", border: `1px solid ${T.teal}40`, color: "#065f46" }}>🎯 {t}</span>
            ))}
            {Array.isArray(strat.aeo_strategy.featured_snippet_targets) && strat.aeo_strategy.featured_snippet_targets.slice(0, 4).map((f, i) => (
              <span key={i} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 99, background: "#fffbeb", border: `1px solid ${T.amber}40`, color: "#78350f" }}>⭐ {f}</span>
            ))}
          </div>
        </Card>
      )}

      {/* ── Strategy headline + generate CTA ── */}
      <Card style={{ background: headline ? `${T.purple}06` : T.grayLight, border: `1px solid ${headline ? T.purple + "30" : T.border}` }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".06em" }}>
              {headline ? "Strategy Headline" : "No Strategy Yet"}
            </div>
            {headline ? (
              <div style={{ fontSize: 14, color: T.text, lineHeight: 1.6, fontWeight: 500 }}>{headline}</div>
            ) : (
              <div style={{ fontSize: 13, color: T.textSoft, lineHeight: 1.5 }}>
                Configure strategy parameters, complete Research, then generate your strategy.
              </div>
            )}
          </div>
          <Btn onClick={onRunPhase9} disabled={running} loading={running}
            variant={session?.phase9_done ? "outline" : "primary"} style={{ flexShrink: 0 }}>
            {session?.phase9_done ? "⚙️ Open Configure" : "⚙️ Configure Strategy"}
          </Btn>
        </div>
        {running && (
          <div style={{ marginTop: 10, fontSize: 11, color: T.textSoft, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: T.amber }} />
            Generating strategy… check the Console below for live output.
          </div>
        )}
      </Card>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB: KEYWORDS — browse, search, filter all validated keywords
// ─────────────────────────────────────────────────────────────────────────────
const INTENT_OPTS = ["all", "transactional", "informational", "commercial", "navigational"]

function KeywordsTab({ validatedData, pillarStats, bizContext }) {
  const [search, setSearch]         = useState("")
  const [pillarFilter, setPillarFilter] = useState("all")
  const [intentFilter, setIntentFilter] = useState("all")
  const [segmentFilter, setSegmentFilter] = useState("all") // all | money | growth | support | quickwins
  const [sortBy, setSortBy]         = useState("score") // score | alpha | pillar | intent
  const [page, setPage]             = useState(0)
  const PAGE_SIZE = 50

  const allItems = validatedData?.items || []
  const allPillars = useMemo(() => {
    const ps = [...new Set(allItems.map(k => k.pillar).filter(Boolean))]
    return ps.sort()
  }, [allItems])

  // Money / Growth / Support segmentation (from keywordupgrade.md spec)
  const classifyKw = (kw) => {
    const score  = kw.final_score || kw.score || 0
    const intent = (kw.intent || "").toLowerCase()
    const diff   = kw.difficulty || kw.kd || 0
    if ((intent === "transactional" || intent === "commercial") && score >= 60) return "money"
    if (score >= 60 && diff <= 35) return "quickwins"
    if (score >= 40) return "growth"
    return "support"
  }

  const segments = useMemo(() => {
    const m = { money: [], growth: [], support: [], quickwins: [] }
    allItems.forEach(k => { m[classifyKw(k)].push(k) })
    return m
  }, [allItems])

  const SEGMENT_CFG = {
    all:       { label: "All",        icon: "📋", color: T.textSoft },
    money:     { label: "Money",      icon: "💰", color: "#10b981", desc: "High commercial score + transactional intent" },
    growth:    { label: "Growth",     icon: "📈", color: T.purple,  desc: "High score, mid-competition — 3-6 month play" },
    support:   { label: "Support",    icon: "📚", color: T.amber,   desc: "Informational & long-tail — topical authority" },
    quickwins: { label: "Quick Wins", icon: "⚡",  color: T.teal,   desc: "Score ≥60 + difficulty ≤35 — target Month 1" },
  }

  const filtered = useMemo(() => {
    let items = allItems
    if (segmentFilter !== "all") items = segments[segmentFilter] || []
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      items = items.filter(k => (k.keyword || "").toLowerCase().includes(q))
    }
    if (pillarFilter !== "all") items = items.filter(k => k.pillar === pillarFilter)
    if (intentFilter !== "all") items = items.filter(k => (k.intent || "").toLowerCase() === intentFilter)
    if (sortBy === "score") items = [...items].sort((a, b) => (b.final_score || b.score || 0) - (a.final_score || a.score || 0))
    else if (sortBy === "alpha") items = [...items].sort((a, b) => (a.keyword || "").localeCompare(b.keyword || ""))
    else if (sortBy === "pillar") items = [...items].sort((a, b) => (a.pillar || "").localeCompare(b.pillar || ""))
    else if (sortBy === "intent") items = [...items].sort((a, b) => (a.intent || "").localeCompare(b.intent || ""))
    return items
  }, [allItems, segments, search, pillarFilter, intentFilter, segmentFilter, sortBy])

  const pageItems = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  const PILLAR_COLORS = ["#007AFF","#34C759","#FF9500","#AF52DE","#FF3B30","#5AC8FA","#FFCC00"]

  // Pillar distribution for mini chart
  const pillarDist = useMemo(() => {
    if (bizContext?.pillar_distribution) return bizContext.pillar_distribution
    const dist = {}
    allItems.forEach(k => { if (k.pillar) dist[k.pillar] = (dist[k.pillar] || 0) + 1 })
    return dist
  }, [allItems, bizContext])

  const pillarColorMap = useMemo(() => {
    const keys = Object.keys(pillarDist).sort()
    const map = {}
    keys.forEach((k, i) => { map[k] = PILLAR_COLORS[i % PILLAR_COLORS.length] })
    return map
  }, [pillarDist])

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

      {/* ── Summary strip ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
        {[
          { label: "Total Validated", val: allItems.length.toLocaleString(), icon: "✅", color: T.teal },
          { label: "Pillars",         val: allPillars.length, icon: "🏛️", color: T.purple },
          { label: "High Score (70+)",val: allItems.filter(k => (k.final_score || k.score || 0) >= 70).length, icon: "⭐", color: T.amber },
          { label: "Transactional",   val: allItems.filter(k => (k.intent||"").toLowerCase() === "transactional").length, icon: "🛒", color: "#10b981" },
        ].map(s => (
          <Card key={s.label} style={{ padding: "10px 14px", display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 20 }}>{s.icon}</span>
            <div>
              <div style={{ fontSize: 18, fontWeight: 800, color: s.color }}>{s.val}</div>
              <div style={{ fontSize: 10, color: T.textSoft, textTransform: "uppercase", letterSpacing: ".06em" }}>{s.label}</div>
            </div>
          </Card>
        ))}
      </div>

      {/* ── Keyword Segments (Money / Growth / Support / Quick Wins) ── */}
      {allItems.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
          {(["money","growth","support","quickwins"]).map(seg => {
            const cfg = SEGMENT_CFG[seg]
            const cnt = segments[seg].length
            const active = segmentFilter === seg
            return (
              <button key={seg} onClick={() => { setSegmentFilter(active ? "all" : seg); setPage(0) }}
                style={{
                  padding: "10px 14px", borderRadius: 10, border: `1.5px solid ${active ? cfg.color : T.border}`,
                  background: active ? cfg.color + "12" : "#fff", cursor: "pointer", textAlign: "left",
                  boxShadow: active ? `0 0 0 2px ${cfg.color}30` : T.cardShadow,
                }}>
                <div style={{ fontSize: 16, marginBottom: 3 }}>{cfg.icon}</div>
                <div style={{ fontSize: 13, fontWeight: 800, color: active ? cfg.color : T.text }}>{cnt}</div>
                <div style={{ fontSize: 11, fontWeight: 700, color: active ? cfg.color : T.textSoft }}>{cfg.label}</div>
                <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2, lineHeight: 1.3 }}>{cfg.desc}</div>
              </button>
            )
          })}
        </div>
      )}

      {/* ── Pillar distribution bar ── */}
      {Object.keys(pillarDist).length > 0 && (
        <Card style={{ padding: "12px 16px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: T.textSoft, marginBottom: 8, textTransform: "uppercase", letterSpacing: ".06em" }}>
            Distribution by Pillar
          </div>
          <div style={{ display: "flex", height: 18, borderRadius: 9, overflow: "hidden", gap: 1 }}>
            {Object.entries(pillarDist).sort((a, b) => b[1] - a[1]).map(([pl, cnt]) => {
              const total = allItems.length || 1
              const pct = (cnt / total) * 100
              const col = pillarColorMap[pl] || T.purple
              return (
                <div key={pl} title={`${pl}: ${cnt} keywords (${Math.round(pct)}%)`}
                  style={{ width: `${pct}%`, background: col, minWidth: pct > 2 ? undefined : 1 }}/>
              )
            })}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", marginTop: 6 }}>
            {Object.entries(pillarDist).sort((a, b) => b[1] - a[1]).map(([pl, cnt]) => (
              <button key={pl} onClick={() => { setPillarFilter(p => p === pl ? "all" : pl); setPage(0) }}
                style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, background: "none",
                  border: "none", cursor: "pointer", fontWeight: pillarFilter === pl ? 700 : 400,
                  color: pillarFilter === pl ? pillarColorMap[pl] : T.textSoft, padding: "2px 0" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: pillarColorMap[pl] || T.purple, display: "inline-block" }}/>
                {pl} ({cnt})
              </button>
            ))}
          </div>
        </Card>
      )}

      {/* ── Filters + Search ── */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input
          type="text" value={search} onChange={e => { setSearch(e.target.value); setPage(0) }}
          placeholder="🔍 Search keywords…"
          style={{ flex: "1 1 200px", padding: "7px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
            fontSize: 13, background: "#fff", minWidth: 160 }}
        />
        <select value={pillarFilter} onChange={e => { setPillarFilter(e.target.value); setPage(0) }}
          style={{ padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, background: "#fff" }}>
          <option value="all">All Pillars</option>
          {allPillars.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={intentFilter} onChange={e => { setIntentFilter(e.target.value); setPage(0) }}
          style={{ padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, background: "#fff" }}>
          {INTENT_OPTS.map(i => <option key={i} value={i}>{i === "all" ? "All Intents" : i}</option>)}
        </select>
        <select value={sortBy} onChange={e => setSortBy(e.target.value)}
          style={{ padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, background: "#fff" }}>
          <option value="score">Sort: Score ↓</option>
          <option value="alpha">Sort: A → Z</option>
          <option value="pillar">Sort: Pillar</option>
          <option value="intent">Sort: Intent</option>
        </select>
        {segmentFilter !== "all" && (
          <button onClick={() => { setSegmentFilter("all"); setPage(0) }}
            style={{ padding: "5px 10px", borderRadius: 7, border: `1px solid ${SEGMENT_CFG[segmentFilter]?.color}`,
              background: SEGMENT_CFG[segmentFilter]?.color + "15", color: SEGMENT_CFG[segmentFilter]?.color,
              fontSize: 11, fontWeight: 700, cursor: "pointer" }}>
            {SEGMENT_CFG[segmentFilter]?.icon} {SEGMENT_CFG[segmentFilter]?.label} ✕
          </button>
        )}
        <div style={{ fontSize: 11, color: T.textSoft, flexShrink: 0 }}>
          {filtered.length} keyword{filtered.length !== 1 ? "s" : ""}
          {(search || pillarFilter !== "all" || intentFilter !== "all" || segmentFilter !== "all") && " (filtered)"}
        </div>
      </div>

      {/* ── Keyword table ── */}
      {allItems.length === 0 ? (
        <Card style={{ textAlign: "center", padding: 48 }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🔑</div>
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>No validated keywords yet</div>
          <div style={{ fontSize: 13, color: T.textSoft }}>Run Phase 3 (Validation) in Keywords v2 to generate and validate keywords for this session.</div>
        </Card>
      ) : (
        <Card style={{ padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: T.grayLight }}>
                {["#", "Keyword", "Pillar", "Intent", "Score", "Buyer Ready"].map(h => (
                  <th key={h} style={{ padding: "9px 12px", textAlign: "left", fontSize: 10, fontWeight: 700,
                    color: T.textSoft, textTransform: "uppercase", letterSpacing: ".06em",
                    borderBottom: `1px solid ${T.border}` }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageItems.map((kw, i) => {
                const sc = Math.round(kw.final_score || kw.score || 0)
                const br = kw.buyer_readiness != null ? Math.round(kw.buyer_readiness * 100) : null
                const col = pillarColorMap[kw.pillar] || T.purple
                const rank = page * PAGE_SIZE + i + 1
                return (
                  <tr key={kw.id || i} style={{ borderBottom: `1px solid ${T.border}`, background: i % 2 === 0 ? "#fff" : "#fafafa" }}>
                    <td style={{ padding: "8px 12px", fontSize: 11, color: T.textSoft, fontWeight: 600, width: 36 }}>{rank}</td>
                    <td style={{ padding: "8px 12px" }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: T.text }}>{kw.keyword}</div>
                      {kw.relevance != null && (
                        <div style={{ fontSize: 10, color: T.textSoft, marginTop: 1 }}>
                          rel: {Math.round((kw.relevance || 0) * 100)}%
                        </div>
                      )}
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 99, background: col + "18", color: col, fontWeight: 600 }}>
                        {kw.pillar || "—"}
                      </span>
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <Badge label={kw.intent || "—"} color={intentColor(kw.intent)} />
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <div style={{ flex: 1, height: 5, background: "#e5e7eb", borderRadius: 3, overflow: "hidden", minWidth: 40 }}>
                          <div style={{ height: "100%", width: `${sc}%`, background: scoreColor(sc), borderRadius: 3 }}/>
                        </div>
                        <span style={{ fontSize: 11, fontWeight: 700, color: scoreColor(sc), minWidth: 24 }}>{sc}</span>
                      </div>
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      {br != null ? (
                        <span style={{ fontSize: 11, fontWeight: 700, color: br >= 70 ? T.teal : br >= 40 ? T.amber : T.gray }}>
                          {br}%
                        </span>
                      ) : "—"}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "10px 16px",
              borderTop: `1px solid ${T.border}`, background: T.grayLight }}>
              <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                style={{ padding: "4px 12px", borderRadius: 6, border: `1px solid ${T.border}`, background: "#fff",
                  cursor: page === 0 ? "not-allowed" : "pointer", fontSize: 12, opacity: page === 0 ? 0.4 : 1 }}>
                ← Prev
              </button>
              <span style={{ fontSize: 12, color: T.textSoft }}>
                Page {page + 1} of {totalPages} · {filtered.length} keywords
              </span>
              <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page === totalPages - 1}
                style={{ padding: "4px 12px", borderRadius: 6, border: `1px solid ${T.border}`, background: "#fff",
                  cursor: page === totalPages - 1 ? "not-allowed" : "pointer", fontSize: 12, opacity: page === totalPages - 1 ? 0.4 : 1 }}>
                Next →
              </button>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB: STRATEGY
// ─────────────────────────────────────────────────────────────────────────────
function StrategyTab({ strat, session, bizContext, onRunPhase9, running, onGoToIntelligence, onGoToParams, strategyPrereqs }) {
  const [showContextUsed, setShowContextUsed] = useState(false)
  const [showRaw, setShowRaw] = useState(false)

  const prereqs = strategyPrereqs || buildStrategyPrereqs({ bizContext })
  const prereqItems = prereqs.items || []
  const prereqReady = prereqs.readyCount || 0
  const prereqTotal = prereqs.totalCount || prereqItems.length
  const prereqsLoaded = !!prereqs.hasSnapshot
  const allPrereqsMet = !!prereqs.allPrereqsMet
  const canRunStrategy = !prereqsLoaded || allPrereqsMet

  if (!strat) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Prerequisite status */}
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.purpleDark }}>📋 Strategy Prerequisites</div>
            <span style={{ fontSize: 12, fontWeight: 700, color: allPrereqsMet ? T.teal : T.amber }}>
              {prereqsLoaded ? `${prereqReady}/${prereqTotal} ready` : "Checking…"}
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {prereqItems.map((item, i) => (
              <div key={i} style={{
                padding: "10px 14px", borderRadius: 8,
                background: item.done ? "#f0fdf4" : "#fffbeb",
                border: `1px solid ${item.done ? "#86efac" : "#fde68a"}`,
                display: "flex", alignItems: "center", gap: 8,
              }}>
                <span style={{ fontSize: 16 }}>{item.done ? "✅" : "⚠️"}</span>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: item.done ? "#166534" : "#92400e" }}>{item.label}</div>
                  <div style={{ fontSize: 11, color: T.textSoft }}>{item.desc}</div>
                </div>
              </div>
            ))}
          </div>
          {prereqsLoaded && !allPrereqsMet && (
            <div style={{ marginTop: 12, padding: "10px 14px", background: "#eff6ff", borderRadius: 8, border: `1px solid ${T.purple}30` }}>
              <div style={{ fontSize: 12, color: T.purpleDark, lineHeight: 1.5 }}>
                <strong>Required workflow:</strong> <span onClick={onGoToParams} style={{ color: T.purple, cursor: "pointer", textDecoration: "underline" }}>Configure</span> → <span onClick={onGoToIntelligence} style={{ color: T.purple, cursor: "pointer", textDecoration: "underline" }}>Research</span> → Strategy & Plan.
                Strategy generation is blocked until Research prerequisites are complete.
              </div>
            </div>
          )}
        </Card>

        <Card style={{ textAlign: "center", padding: 48 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🗺️</div>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>No strategy generated yet</div>
          <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 20 }}>
            {!prereqsLoaded
              ? "Checking Research readiness..."
              : allPrereqsMet
              ? "All prerequisites met! Configure parameters and generate your strategy."
              : "Complete the Research pipeline first, then generate your strategy from Configure."}
          </div>
          <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
            {prereqsLoaded && !allPrereqsMet && (
              <Btn onClick={onGoToIntelligence} variant="outline">🧠 Go to Research</Btn>
            )}
            <Btn onClick={onGoToParams} variant={allPrereqsMet ? "primary" : "outline"}>
              📋 {allPrereqsMet ? "Configure & Generate" : "Configure Parameters"}
            </Btn>
          </div>
        </Card>
      </div>
    )
  }

  // Recover strategy if stored data is corrupted (headline contains the full JSON blob)
  const resolvedStrat = useMemo(() => {
    if (!strat) return strat
    const headline = strat?.strategy_summary?.headline
    if (headline && typeof headline === "string" && headline.trimStart().startsWith("{")) {
      try {
        const parsed = JSON.parse(headline)
        // Verify it looks like a real strategy object
        if (parsed && typeof parsed === "object" && (parsed.strategy_summary || parsed.executive_summary || parsed.priority_pillars)) {
          return parsed
        }
      } catch {}
    }
    return strat
  }, [strat])

  const _safe = (s) => {
    if (!s) return ""
    const direct = s?.strategy_summary?.headline
    if (direct && typeof direct === "string") {
      const trimmed = direct.trimStart()
      if (!trimmed.startsWith("{") && !trimmed.startsWith("[") && direct.length < 600) return direct
      // Headline contains nested JSON (data corruption recovery) — try to parse it
      if (trimmed.startsWith("{")) {
        try {
          const parsed = JSON.parse(direct)
          const nested = parsed?.strategy_summary?.headline || parsed?.headline
          if (nested && typeof nested === "string" && !nested.trimStart().startsWith("{")) return nested
        } catch {}
      }
    }
    const exec = s?.executive_summary
    if (!exec || typeof exec !== "string") return ""
    const t = exec.trimStart()
    if (t.startsWith("{") || t.startsWith("[")) {
      try { const p = JSON.parse(exec); const n = p?.strategy_summary?.headline || p?.headline; if (n) return String(n) } catch {}
      return ""
    }
    return exec.length > 200 ? exec.slice(0, 197) + "…" : exec
  }

  const headline           = _safe(resolvedStrat)
  const biggestOpp         = resolvedStrat?.strategy_summary?.biggest_opportunity || resolvedStrat?.biggest_opportunity || ""
  const whyWeWin           = resolvedStrat?.strategy_summary?.why_we_win || resolvedStrat?.why_we_win || ""
  const positioningStmt    = resolvedStrat?.positioning_statement || resolvedStrat?.value_proposition || ""
  const executiveSummary   = (() => {
    const e = resolvedStrat?.executive_summary || ""
    if (!e || typeof e !== "string") return ""
    const t = e.trimStart()
    if (t.startsWith("{") || t.startsWith("[")) return ""
    return e
  })()
  const quickWins          = Array.isArray(resolvedStrat?.quick_wins) ? resolvedStrat.quick_wins.map(w => typeof w === "string" ? w : w?.keyword || w?.title || JSON.stringify(w)) : []
  const contentGaps        = Array.isArray(resolvedStrat?.content_gaps) ? resolvedStrat.content_gaps : []
  const compGaps           = Array.isArray(resolvedStrat?.competitive_gaps) ? resolvedStrat.competitive_gaps : Array.isArray(resolvedStrat?.competitor_gaps) ? resolvedStrat.competitor_gaps : []
  const priorityPillars    = Array.isArray(resolvedStrat?.priority_pillars) ? resolvedStrat.priority_pillars : []
  const pillarStrats       = Array.isArray(resolvedStrat?.pillar_strategies) ? resolvedStrat.pillar_strategies : Array.isArray(resolvedStrat?.pillar_strategy) ? resolvedStrat.pillar_strategy : []
  const contentPriorities  = Array.isArray(resolvedStrat?.content_priorities) ? resolvedStrat.content_priorities : []
  const monthlyThemes      = Array.isArray(resolvedStrat?.monthly_themes) ? resolvedStrat.monthly_themes : []
  const linkPlan           = resolvedStrat?.link_building_plan || ""
  const timeline           = Array.isArray(resolvedStrat?.timeline) ? resolvedStrat.timeline : []
  const keyMessages        = Array.isArray(resolvedStrat?.key_messages) ? resolvedStrat.key_messages : []
  const seoTactics         = Array.isArray(resolvedStrat?.seo_tactics) ? resolvedStrat.seo_tactics : []
  const weeklyPlan         = Array.isArray(resolvedStrat?.weekly_plan) ? resolvedStrat.weekly_plan : []
  const seoRecs            = Array.isArray(resolvedStrat?.seo_recommendations) ? resolvedStrat.seo_recommendations : []
  const aeoStrat           = resolvedStrat?.aeo_strategy || null
  const ninetyDayPlan      = Array.isArray(resolvedStrat?.['90_day_plan']) ? resolvedStrat['90_day_plan'] : (Array.isArray(resolvedStrat?.ninety_day_plan) ? resolvedStrat.ninety_day_plan : [])
  const stratConfidence    = resolvedStrat?.confidence != null ? Math.round(Number(resolvedStrat.confidence) * 100) : null
  const csPillarPlan       = Array.isArray(resolvedStrat?.content_strategy?.pillar_plan) ? resolvedStrat.content_strategy.pillar_plan : []

  const bi = bizContext?.biz_intel || {}

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

      {/* ── Context Used banner ── */}
      <div style={{ borderRadius: 10, border: `1px solid ${T.purple}30`, overflow: "hidden" }}>
        <div
          onClick={() => setShowContextUsed(v => !v)}
          style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 16px",
                   background: `${T.purple}08`, cursor: "pointer", userSelect: "none" }}
        >
          <span style={{ fontSize: 16 }}>🧩</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark }}>Context Used to Generate This Strategy</div>
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 1 }}>
              {[
                bizContext?.pages_count ? `${bizContext.pages_count} pages` : null,
                bizContext?.competitors?.length ? `${bizContext.competitors.length} competitors` : null,
                bi.usps?.length ? `${bi.usps.length} USPs` : null,
                bi.goals?.length ? `${bi.goals.length} goals` : null,
                bi.has_website_crawl ? "website crawl" : null,
                bi.has_competitor_crawl ? "competitor analysis" : null,
                bizContext?.keywords_validated ? `${bizContext.keywords_validated} validated keywords` : null,
              ].filter(Boolean).join(" · ") || "Basic session data"}
            </div>
          </div>
          <span style={{ fontSize: 11, color: T.purple, border: `1px solid ${T.purple}40`, borderRadius: 6, padding: "2px 8px" }}>
            {showContextUsed ? "Hide" : "Expand"}
          </span>
        </div>
        {showContextUsed && (
          <div style={{ padding: "12px 16px", borderTop: `1px solid ${T.purple}20`, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {/* USPs used */}
              {bi.usps?.length > 0 && (
                <div style={{ background: "#eff6ff", borderRadius: 8, padding: "8px 12px" }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#1e40af", marginBottom: 4, textTransform: "uppercase", letterSpacing: ".05em" }}>USPs Injected</div>
                  {bi.usps.map((u, i) => <div key={i} style={{ fontSize: 11, color: T.text }}>• {u}</div>)}
                </div>
              )}
              {/* Goals used */}
              {bi.goals?.length > 0 && (
                <div style={{ background: "#f0fdf4", borderRadius: 8, padding: "8px 12px" }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#166534", marginBottom: 4, textTransform: "uppercase", letterSpacing: ".05em" }}>Goals Injected</div>
                  {bi.goals.map((g, i) => <div key={i} style={{ fontSize: 11, color: T.text }}>• {g}</div>)}
                </div>
              )}
              {/* Audience */}
              {bi.audience_segments?.length > 0 && (
                <div style={{ background: "#faf5ff", borderRadius: 8, padding: "8px 12px" }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#5b21b6", marginBottom: 4, textTransform: "uppercase", letterSpacing: ".05em" }}>Audience Segments</div>
                  {bi.audience_segments.map((a, i) => <div key={i} style={{ fontSize: 11, color: T.text }}>• {a}</div>)}
                </div>
              )}
              {/* Competitors */}
              {bizContext?.competitors?.length > 0 && (
                <div style={{ background: "rgba(255,59,48,0.05)", borderRadius: 8, padding: "8px 12px" }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#b91c1c", marginBottom: 4, textTransform: "uppercase", letterSpacing: ".05em" }}>Competitors Analyzed</div>
                  {bizContext.competitors.map((c, i) => (
                    <div key={i} style={{ fontSize: 11, color: T.text, marginBottom: 2 }}>
                      <strong>{c.domain}</strong>
                      {c.weaknesses?.length > 0 && ` — weaknesses: ${c.weaknesses.slice(0, 2).join(", ")}`}
                    </div>
                  ))}
                </div>
              )}
            </div>
            {bi.website_summary && (
              <div style={{ background: T.grayLight, borderRadius: 8, padding: "8px 12px" }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 3, textTransform: "uppercase", letterSpacing: ".05em" }}>Website Summary Used</div>
                <div style={{ fontSize: 12, color: T.text, lineHeight: 1.5 }}>{bi.website_summary}</div>
              </div>
            )}
            {bi.knowledge_summary && (
              <div style={{ background: T.grayLight, borderRadius: 8, padding: "8px 12px" }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 3, textTransform: "uppercase", letterSpacing: ".05em" }}>Knowledge Summary Used</div>
                <div style={{ fontSize: 12, color: T.text, lineHeight: 1.5 }}>{bi.knowledge_summary}</div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Strategy metadata bar ── */}
      {(() => {
        const updatedAt = session?.updated_at || session?.phase9_updated_at || null
        const provider  = resolvedStrat?.ai_provider || resolvedStrat?.generated_by || resolvedStrat?.provider || null
        const kwCount   = bizContext?.keywords_validated || session?.validated_total || null
        const pillCount = Object.keys(bizContext?.pillar_distribution || {}).length || null
        if (!updatedAt && !provider && !kwCount) return null
        return (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", padding: "8px 14px",
            background: `${T.purple}06`, borderRadius: 10, border: `1px solid ${T.purple}20`,
            alignItems: "center" }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark }}>📊 Strategy snapshot</span>
            {kwCount && <span style={{ fontSize: 11, color: T.textSoft }}>Built from <strong style={{ color: T.text }}>{kwCount}</strong> validated keywords</span>}
            {pillCount && <span style={{ fontSize: 11, color: T.textSoft }}>across <strong style={{ color: T.text }}>{pillCount}</strong> pillars</span>}
            {provider && <Badge label={`AI: ${provider}`} color={T.purple} />}
            {updatedAt && (
              <span style={{ fontSize: 10, color: T.textSoft, marginLeft: "auto" }}>
                Generated {new Date(updatedAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                {" at "}{new Date(updatedAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
          </div>
        )
      })()}

      {/* ── Summary cards ── */}
      {(headline || biggestOpp || whyWeWin || positioningStmt) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {headline && (
            <Card style={{ background: `${T.purple}06`, border: `1px solid ${T.purple}30`, padding: 16, gridColumn: "1 / -1" }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: T.purpleDark, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".07em" }}>Strategy Headline</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: T.text, lineHeight: 1.5 }}>{headline}</div>
            </Card>
          )}
          {biggestOpp && (
            <Card style={{ background: `${T.teal}06`, border: `1px solid ${T.teal}30`, padding: 14 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: T.teal, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".07em" }}>Biggest Opportunity</div>
              <div style={{ fontSize: 13, color: T.text, lineHeight: 1.5 }}>{biggestOpp}</div>
            </Card>
          )}
          {whyWeWin && (
            <Card style={{ background: `${T.amber}06`, border: `1px solid ${T.amber}30`, padding: 14 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: T.amber, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".07em" }}>Why We Win</div>
              <div style={{ fontSize: 13, color: T.text, lineHeight: 1.5 }}>{whyWeWin}</div>
            </Card>
          )}
          {positioningStmt && (
            <Card style={{ background: "#faf5ff", border: `1px solid #e9d5ff`, padding: 14, gridColumn: whyWeWin || biggestOpp ? undefined : "1 / -1" }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#5b21b6", marginBottom: 6, textTransform: "uppercase", letterSpacing: ".07em" }}>Positioning Statement</div>
              <div style={{ fontSize: 13, color: T.text, lineHeight: 1.5, fontStyle: "italic" }}>{positioningStmt}</div>
            </Card>
          )}
        </div>
      )}

      {/* ── Executive summary ── */}
      {executiveSummary && (
        <Card style={{ border: `1px solid ${T.purple}20` }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>Executive Summary</div>
          <div style={{ fontSize: 13, color: T.text, lineHeight: 1.75, whiteSpace: "pre-wrap" }}>{executiveSummary}</div>
        </Card>
      )}

      {/* ── Priority pillars ── */}
      {priorityPillars.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>Priority Pillars</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
            {priorityPillars.map((p, i) => {
              const name = typeof p === "string" ? p : p?.pillar || p?.name || `Pillar ${i+1}`
              const opp  = typeof p === "object" ? (p?.opportunity_score ?? p?.score ?? null) : null
              const reason = typeof p === "object" ? (p?.reason || p?.why || "") : ""
              return (
                <div key={i} style={{ padding: "10px 14px", background: T.grayLight, borderRadius: 10, border: `1px solid ${T.border}` }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 4 }}>{name}</div>
                  {opp != null && <div style={{ fontSize: 11, color: T.teal, fontWeight: 600, marginBottom: 3 }}>Opportunity: {opp}</div>}
                  {reason && <div style={{ fontSize: 11, color: T.textSoft, lineHeight: 1.4 }}>{reason}</div>}
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── Pillar strategy details ── */}
      {pillarStrats.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>Pillar Strategy Details</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {pillarStrats.map((p, i) => {
              const name = typeof p === "string" ? p : p?.pillar || `Pillar ${i+1}`
              const obj  = typeof p === "object" ? p : {}
              return (
                <div key={i} style={{ padding: "12px 14px", background: T.grayLight, borderRadius: 10, border: `1px solid ${T.border}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>{name}</div>
                    <div style={{ display: "flex", gap: 4 }}>
                      {obj.difficulty && <Badge label={obj.difficulty} color={obj.difficulty === "low" ? T.teal : obj.difficulty === "high" ? T.red : T.amber} />}
                      {obj.target_rank && <Badge label={`#${obj.target_rank}`} color={obj.target_rank <= 3 ? T.teal : T.amber} />}
                      {obj.priority && <Badge label={`P${obj.priority}`} color={T.purple} />}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: obj.strategy ? 8 : 0 }}>
                    {obj.content_type && <span style={{ fontSize: 11, color: T.textSoft }}>Type: <strong>{obj.content_type}</strong></span>}
                    {obj.monthly_searches && <span style={{ fontSize: 11, color: T.textSoft }}>~{obj.monthly_searches} searches/mo</span>}
                    {obj.word_count && <span style={{ fontSize: 11, color: T.textSoft }}>{obj.word_count} words</span>}
                    {obj.target_keyword && <span style={{ fontSize: 11, color: T.purple, fontWeight: 600 }}>🎯 {obj.target_keyword}</span>}
                  </div>
                  {obj.strategy && <div style={{ fontSize: 12, color: T.text, lineHeight: 1.6 }}>{obj.strategy}</div>}
                  {obj.key_topics?.length > 0 && (
                    <div style={{ marginTop: 6, display: "flex", gap: 5, flexWrap: "wrap" }}>
                      {obj.key_topics.map((t, ti) => (
                        <span key={ti} style={{ fontSize: 10, padding: "1px 7px", borderRadius: 99, background: T.purple + "15", color: T.purple }}>{t}</span>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── 3-col: Quick wins | Content gaps | Competitive gaps ── */}
      {(quickWins.length > 0 || contentGaps.length > 0 || compGaps.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
          {quickWins.length > 0 && (
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 10 }}>⚡ Quick Wins ({quickWins.length})</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {quickWins.map((w, i) => {
                  const kw      = typeof w === "string" ? w : w?.keyword || w?.title || JSON.stringify(w)
                  const intent  = typeof w === "object" ? w?.intent : null
                  const ctype   = typeof w === "object" ? (w?.content_type || w?.type || w?.page_type) : null
                  const why     = typeof w === "object" ? (w?.reason || w?.why || w?.rationale || "") : ""
                  return (
                    <div key={i} style={{ padding: "7px 10px", background: `${T.teal}08`, borderRadius: 8, border: `1px solid ${T.teal}20` }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: T.text, marginBottom: intent || ctype ? 4 : 0 }}>{kw}</div>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {intent && <Badge label={intent} color={intentColor(intent)} />}
                        {ctype  && <Badge label={ctype}  color={T.amber} />}
                      </div>
                      {why && <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3, lineHeight: 1.4 }}>{why}</div>}
                    </div>
                  )
                })}
              </div>
            </Card>
          )}
          {contentGaps.length > 0 && (
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.amber, marginBottom: 10 }}>🕳️ Content Gaps ({contentGaps.length})</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {contentGaps.map((g, i) => {
                  const label = typeof g === "string" ? g : g?.gap || g?.topic || g?.keyword || JSON.stringify(g)
                  const opp   = typeof g === "object" ? (g?.opportunity || "") : ""
                  return (
                    <div key={i} style={{ padding: "6px 10px", background: `${T.amber}08`, borderRadius: 7, border: `1px solid ${T.amber}20` }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: T.text }}>{label}</div>
                      {opp && <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{opp}</div>}
                    </div>
                  )
                })}
              </div>
            </Card>
          )}
          {compGaps.length > 0 && (
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.red, marginBottom: 10 }}>🥊 Competitive Gaps ({compGaps.length})</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {compGaps.map((g, i) => {
                  const label  = typeof g === "string" ? g : g?.gap || g?.topic || g?.keyword || JSON.stringify(g)
                  const comp   = typeof g === "object" ? (g?.competitor || g?.domain || "") : ""
                  return (
                    <div key={i} style={{ padding: "6px 10px", background: "rgba(255,59,48,0.05)", borderRadius: 7, border: "1px solid rgba(255,59,48,0.15)" }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: T.text }}>{label}</div>
                      {comp && <div style={{ fontSize: 10, color: T.red, marginTop: 2 }}>vs {comp}</div>}
                    </div>
                  )
                })}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ── Key Messages ── */}
      {keyMessages.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>📣 Key Messages</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {keyMessages.map((m, i) => (
              <div key={i} style={{ padding: "8px 12px", background: `${T.purple}08`, borderRadius: 8, fontSize: 12, lineHeight: 1.5, fontStyle: "italic", border: `1px solid ${T.purple}20` }}>
                "{typeof m === "string" ? m : m?.message || JSON.stringify(m)}"
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ── Content Priorities (ordered list) ── */}
      {contentPriorities.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>📋 Content Priorities (Ordered)</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {contentPriorities.map((cp, i) => {
              const label   = typeof cp === "string" ? cp : cp?.priority || cp?.topic || cp?.title || JSON.stringify(cp)
              const why     = typeof cp === "object" ? (cp?.why || cp?.reason || "") : ""
              const effort  = typeof cp === "object" ? (cp?.effort || "") : ""
              const impact  = typeof cp === "object" ? (cp?.impact || "") : ""
              return (
                <div key={i} style={{ display: "flex", gap: 12, padding: "8px 12px", background: T.grayLight, borderRadius: 8, alignItems: "flex-start" }}>
                  <div style={{ width: 24, height: 24, borderRadius: "50%", background: T.purple, color: "#fff",
                    fontSize: 11, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}>
                    {i + 1}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 3 }}>{label}</div>
                    {why && <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 3 }}>{why}</div>}
                    <div style={{ display: "flex", gap: 8 }}>
                      {effort && <span style={{ fontSize: 10, padding: "1px 7px", borderRadius: 99, background: T.amber + "20", color: "#b45309" }}>Effort: {effort}</span>}
                      {impact && <span style={{ fontSize: 10, padding: "1px 7px", borderRadius: 99, background: T.teal + "20", color: "#065f46" }}>Impact: {impact}</span>}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── SEO Recommendations ── */}
      {seoRecs.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>📌 SEO Recommendations</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {seoRecs.map((r, i) => {
              const area     = typeof r === "string" ? r : r?.area || r?.title || ""
              const priority = typeof r === "object" ? (r?.priority || "") : ""
              const action   = typeof r === "object" ? (r?.action || r?.recommendation || "") : ""
              const impact   = typeof r === "object" ? (r?.impact || "") : ""
              const prioColor = priority === "high" ? T.red : priority === "medium" ? T.amber : T.teal
              return (
                <div key={i} style={{ display: "flex", gap: 12, padding: "10px 12px", background: T.grayLight, borderRadius: 9, alignItems: "flex-start" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99, background: prioColor + "20", color: prioColor, flexShrink: 0, marginTop: 1 }}>{priority || "info"}</div>
                  <div style={{ flex: 1 }}>
                    {area && <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{area}</div>}
                    {action && <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2, lineHeight: 1.4 }}>{action}</div>}
                    {impact && <div style={{ fontSize: 11, color: T.teal, marginTop: 3 }}>→ {impact}</div>}
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── SEO Tactics ── */}
      {seoTactics.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>🔧 SEO Tactics</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {seoTactics.map((t, i) => {
              const label = typeof t === "string" ? t : t?.tactic || t?.action || JSON.stringify(t)
              return (
                <div key={i} style={{ padding: "7px 10px", background: T.grayLight, borderRadius: 7, fontSize: 12, lineHeight: 1.4 }}>
                  🔧 {label}
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── AEO / AI Search Strategy ── */}
      {aeoStrat && (
        <Card style={{ border: `1px solid ${T.teal}33`, background: "linear-gradient(135deg,#f0fdf4 0%,#f8faff 100%)" }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 12 }}>🤖 AI Search (AEO) Strategy</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            {Array.isArray(aeoStrat.ai_visibility_targets) && aeoStrat.ai_visibility_targets.length > 0 && (
              <div style={{ background: "#fff", borderRadius: 9, padding: "10px 12px", border: `1px solid ${T.teal}22` }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: T.teal, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>AI Visibility Targets</div>
                {aeoStrat.ai_visibility_targets.map((v, i) => (
                  <div key={i} style={{ fontSize: 11, color: T.text, padding: "3px 0", borderBottom: i < aeoStrat.ai_visibility_targets.length-1 ? `1px solid ${T.border}` : "none" }}>🎯 {v}</div>
                ))}
              </div>
            )}
            {Array.isArray(aeoStrat.structured_data_plan) && aeoStrat.structured_data_plan.length > 0 && (
              <div style={{ background: "#fff", borderRadius: 9, padding: "10px 12px", border: `1px solid ${T.teal}22` }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: T.teal, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>Structured Data</div>
                {aeoStrat.structured_data_plan.map((s, i) => (
                  <div key={i} style={{ fontSize: 11, color: T.text, padding: "3px 0", borderBottom: i < aeoStrat.structured_data_plan.length-1 ? `1px solid ${T.border}` : "none" }}>📋 {s}</div>
                ))}
              </div>
            )}
            {Array.isArray(aeoStrat.featured_snippet_targets) && aeoStrat.featured_snippet_targets.length > 0 && (
              <div style={{ background: "#fff", borderRadius: 9, padding: "10px 12px", border: `1px solid ${T.teal}22` }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: T.teal, marginBottom: 6, textTransform: "uppercase", letterSpacing: ".05em" }}>Featured Snippet Targets</div>
                {aeoStrat.featured_snippet_targets.map((f, i) => (
                  <div key={i} style={{ fontSize: 11, color: T.text, padding: "3px 0", borderBottom: i < aeoStrat.featured_snippet_targets.length-1 ? `1px solid ${T.border}` : "none" }}>⭐ {f}</div>
                ))}
              </div>
            )}
          </div>
        </Card>
      )}

      {/* ── Monthly themes ── */}
      {monthlyThemes.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>📆 Monthly Themes</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
            {monthlyThemes.map((m, i) => {
              const month = typeof m === "string" ? m : m?.month || `Month ${i+1}`
              const theme = typeof m === "object" ? (m?.theme || m?.focus || "") : ""
              const kws   = typeof m === "object" && Array.isArray(m?.keywords) ? m.keywords : []
              return (
                <div key={i} style={{ padding: "10px 12px", background: `${T.purple}08`, borderRadius: 9, border: `1px solid ${T.purple}20` }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 3 }}>{month}</div>
                  {theme && <div style={{ fontSize: 11, color: T.text, marginBottom: 4 }}>{theme}</div>}
                  {kws.length > 0 && <div style={{ fontSize: 10, color: T.textSoft }}>{kws.slice(0, 3).join(", ")}</div>}
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── Link Building Plan ── */}
      {linkPlan && (
        <Card style={{ border: `1px solid ${T.purple}30` }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>🔗 Link Building Plan</div>
          {typeof linkPlan === "string" ? (
            <div style={{ fontSize: 13, color: T.text, lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{linkPlan}</div>
          ) : (
            <pre style={{ fontSize: 11, color: T.textSoft, margin: 0, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
              {JSON.stringify(linkPlan, null, 2)}
            </pre>
          )}
        </Card>
      )}

      {/* ── Execution Timeline ── */}
      {timeline.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>🗓️ Execution Timeline</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {timeline.map((t, i) => {
              const phase  = typeof t === "string" ? t : t?.phase || t?.month || t?.week || `Step ${i+1}`
              const action = typeof t === "object" ? (t?.action || t?.description || t?.focus || t?.deliverable || "") : ""
              const kws    = typeof t === "object" && Array.isArray(t?.keywords) ? t.keywords : []
              return (
                <div key={i} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                  <div style={{ width: 30, height: 30, borderRadius: "50%", background: T.purpleLight, color: T.purpleDark,
                    fontSize: 12, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}>
                    {i + 1}
                  </div>
                  <div style={{ flex: 1, paddingBottom: i < timeline.length - 1 ? 8 : 0,
                    borderBottom: i < timeline.length - 1 ? `1px solid ${T.border}` : "none" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>{phase}</div>
                    {action && <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2, lineHeight: 1.4 }}>{action}</div>}
                    {kws.length > 0 && (
                      <div style={{ marginTop: 4, display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {kws.slice(0, 5).map((k, ki) => (
                          <span key={ki} style={{ fontSize: 10, padding: "1px 7px", borderRadius: 99, background: T.purple + "15", color: T.purple }}>{k}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── 90-Day Plan ── */}
      {ninetyDayPlan.length > 0 && (
        <Card style={{ border: `1px solid ${T.purple}30` }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>📈 90-Day Plan</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(200px,1fr))", gap: 10 }}>
            {ninetyDayPlan.map((m, i) => {
              const month        = typeof m === "string" ? m : m?.month || `Month ${i+1}`
              const focus        = typeof m === "object" ? (m?.focus || "") : ""
              const deliverables = typeof m === "object" && Array.isArray(m?.deliverables) ? m.deliverables : []
              return (
                <div key={i} style={{ padding: "12px 14px", borderRadius: 9, border: `1px solid ${T.purple}25`, background: `${T.purple}06` }}>
                  <div style={{ fontSize: 12, fontWeight: 800, color: T.purpleDark, marginBottom: 4 }}>Month {typeof month === "string" && /^\d+$/.test(month) ? month : i+1}</div>
                  {focus && <div style={{ fontSize: 12, fontWeight: 600, color: T.text, marginBottom: 6 }}>{focus}</div>}
                  {deliverables.map((d, di) => (
                    <div key={di} style={{ fontSize: 11, color: T.textSoft, padding: "2px 0", borderTop: di > 0 ? `1px solid ${T.border}` : "none" }}>✓ {d}</div>
                  ))}
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── Content Strategy Pillar Plan ── */}
      {csPillarPlan.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>📗 Content Strategy — Pillar Plan</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {csPillarPlan.map((p, i) => {
              const pillar   = p?.pillar || p?.name || `Pillar ${i+1}`
              const priority = p?.priority || ""
              const types    = Array.isArray(p?.content_types) ? p.content_types : []
              const intent   = p?.target_intent || ""
              const count    = p?.estimated_articles || p?.article_count || null
              const wins     = Array.isArray(p?.quick_wins) ? p.quick_wins : []
              const prioColor = priority === "high" ? T.red : priority === "medium" ? T.amber : priority === "low" ? T.teal : T.gray
              return (
                <div key={i} style={{ padding: "10px 14px", background: T.grayLight, borderRadius: 9, border: `1px solid ${T.border}` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: T.text, flex: 1 }}>{pillar}</div>
                    {priority && <Badge label={priority} color={prioColor} />}
                    {intent && <Badge label={intent} color={T.purple} />}
                    {count && <span style={{ fontSize: 11, color: T.textSoft }}>{count} articles</span>}
                  </div>
                  {types.length > 0 && (
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: wins.length ? 6 : 0 }}>
                      {types.map((ct, ci) => <Badge key={ci} label={ct} color={T.amber} />)}
                    </div>
                  )}
                  {wins.length > 0 && (
                    <div style={{ fontSize: 11, color: T.textSoft }}>Quick wins: {wins.slice(0, 4).join(" · ")}</div>
                  )}
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── Weekly Plan preview ── */}
      {weeklyPlan.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>📅 Weekly Plan Preview (first 8 weeks)</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 8 }}>
            {weeklyPlan.slice(0, 8).map((w, i) => {
              const week    = w?.week || i + 1
              const pillar  = w?.focus_pillar || w?.pillar || ""
              const articles = Array.isArray(w?.articles) ? w.articles : []
              return (
                <div key={i} style={{ padding: "10px 12px", background: T.grayLight, borderRadius: 9, border: `1px solid ${T.border}` }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 4 }}>Wk {week}{pillar ? ` · ${pillar}` : ""}</div>
                  {articles.slice(0, 3).map((a, ai) => (
                    <div key={ai} style={{ fontSize: 11, color: T.textSoft, marginBottom: 2 }}>
                      • {typeof a === "string" ? a : a?.title || a?.keyword || "Article"}
                    </div>
                  ))}
                  {articles.length > 3 && <div style={{ fontSize: 10, color: T.textSoft }}>+{articles.length - 3} more</div>}
                </div>
              )
            })}
          </div>
          {weeklyPlan.length > 8 && <div style={{ textAlign: "center", fontSize: 11, color: T.textSoft, marginTop: 8 }}>+{weeklyPlan.length - 8} more weeks in Content Plan tab</div>}
        </Card>
      )}

      {/* ── Regenerate + raw ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 4 }}>
        <button onClick={() => setShowRaw(v => !v)} style={{ fontSize: 11, color: T.gray, background: "none",
          border: `1px solid ${T.border}`, borderRadius: 7, padding: "4px 10px", cursor: "pointer" }}>
          {showRaw ? "Hide" : "🔍 Show"} raw JSON
        </button>
        <Btn variant="outline" onClick={onRunPhase9} loading={running} disabled={!canRunStrategy}>
          {canRunStrategy ? "🔄 Regenerate Strategy" : "🧠 Complete Research First"}
        </Btn>
      </div>

      {showRaw && (
        <Card style={{ background: "#0d1117" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#475569", marginBottom: 6, letterSpacing: ".08em" }}>RAW STRATEGY JSON</div>
          <pre style={{ fontSize: 11, color: "#94a3b8", margin: 0, whiteSpace: "pre-wrap", lineHeight: 1.6, overflowX: "auto", maxHeight: 500, overflowY: "auto" }}>
            {JSON.stringify(resolvedStrat, null, 2)}
          </pre>
        </Card>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  BLOG BRIEF PANEL — inline brief for one article card
// ─────────────────────────────────────────────────────────────────────────────
function BriefPanel({ brief, onGenerateFromBrief, generating }) {
  const [chosenTitle, setChosenTitle] = useState(brief?.suggested_title || brief?.keyword || "")
  if (!brief) return null
  const sections = brief.required_sections || []
  const hooks    = brief.hook_ideas || []
  const titles   = brief.title_suggestions || []

  return (
    <div style={{ background: "#fafaff", border: `1px solid ${T.purple}33`, borderRadius: 10,
                  padding: "12px 14px", marginTop: 4, display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Intent + format row */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: "#6366f1", background: "#ede9fe",
                       padding: "2px 8px", borderRadius: 99 }}>
          {(brief.intent || "informational").toUpperCase()}
        </span>
        <span style={{ fontSize: 10, fontWeight: 600, color: T.amber, background: T.amberLight,
                       padding: "2px 8px", borderRadius: 99 }}>
          {(brief.format || "guide").toUpperCase()}
        </span>
        <span style={{ fontSize: 10, color: T.textSoft }}>~{brief.depth === "deep" ? "2000+" : brief.depth === "medium" ? "1200" : "800"} words</span>
        {brief.status === "fallback" && (
          <span style={{ fontSize: 9, color: T.gray, background: T.grayLight, padding: "1px 6px", borderRadius: 99 }}>offline</span>
        )}
      </div>

      {/* Title picker */}
      {titles.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 5, textTransform: "uppercase", letterSpacing: ".05em" }}>
            Title Angles
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {titles.slice(0, 4).map((t, i) => (
              <label key={i} style={{ display: "flex", alignItems: "flex-start", gap: 7, cursor: "pointer",
                                      fontSize: 12, color: chosenTitle === t ? T.purple : T.text, fontWeight: chosenTitle === t ? 600 : 400 }}>
                <input type="radio" name={`title-${brief.keyword}`} checked={chosenTitle === t}
                       onChange={() => setChosenTitle(t)}
                       style={{ marginTop: 2, accentColor: T.purple, flexShrink: 0 }} />
                {t}
              </label>
            ))}
          </div>
        </div>
      )}

      {/* H2 Outline */}
      {sections.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 5, textTransform: "uppercase", letterSpacing: ".05em" }}>
            Content Outline
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {sections.slice(0, 6).map((s, i) => (
              <div key={i} style={{ display: "flex", gap: 7, alignItems: "flex-start", fontSize: 11, color: T.textSoft }}>
                <span style={{ color: T.purple, fontWeight: 700, fontSize: 10, flexShrink: 0 }}>H{i === 0 ? 1 : 2}</span>
                <span>{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Hook ideas */}
      {hooks.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4, textTransform: "uppercase", letterSpacing: ".05em" }}>
            Hook Ideas
          </div>
          <div style={{ fontSize: 11, color: T.textSoft }}>
            {hooks.slice(0, 2).join(" · ")}
          </div>
        </div>
      )}

      {/* CTA */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", paddingTop: 4,
                    borderTop: `1px solid ${T.border}` }}>
        <Btn variant="primary" small disabled={generating}
             onClick={() => onGenerateFromBrief(chosenTitle || brief.keyword)}>
          {generating ? "Queuing…" : "✍️ Generate from Brief"}
        </Btn>
        <span style={{ fontSize: 10, color: T.textSoft }}>Using: {chosenTitle || brief.keyword}</span>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  BATCH BLOG SUGGESTIONS PANEL
// ─────────────────────────────────────────────────────────────────────────────
function BatchBriefPanel({ projectId, sessionId, items, onBriefsLoaded }) {
  const [open, setOpen]         = useState(false)
  const [running, setRunning]   = useState(false)
  const [phase, setPhase]       = useState("")   // progress message
  const [briefs, setBriefs]     = useState([])   // loaded briefs
  const [error, setError]       = useState("")
  const [selectedIdx, setSelectedIdx] = useState(null)
  const [aiConfig, setAiConfig] = useState(BRIEF_AI_DEFAULTS)

  const runBatch = async () => {
    if (!items.length) return
    setRunning(true); setError(""); setPhase("Preparing briefs…"); setOpen(true)
    try {
      const API = import.meta.env.VITE_API_URL || ""
      const t = localStorage.getItem("annaseo_token")

      // Take up to 20 items for batch
      const keywords = items.slice(0, 20).map(i => ({
        keyword: i.keyword || i.title || "",
        title:   i.title || i.keyword || "",
        pillar:  i.pillar || "",
      }))

      setPhase(`Generating briefs for ${keywords.length} articles…`)
      const r = await fetch(`${API}/api/ki/${projectId}/blog-briefs-batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: JSON.stringify({
          keywords,
          session_id: sessionId || "",
          ai_provider: aiConfig.ai_provider,
          custom_prompt: aiConfig.custom_prompt,
        }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      setBriefs(data.briefs || [])
      setPhase(`${data.count || 0} briefs ready`)
      if (onBriefsLoaded) onBriefsLoaded(data.briefs || [])
    } catch (e) {
      setError(String(e))
      setPhase("")
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{ border: `1px solid ${T.purple}33`, borderRadius: 10, overflow: "hidden" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
                    background: "#fafaff", cursor: "pointer" }}
           onClick={() => setOpen(o => !o)}>
        <span style={{ fontSize: 13, fontWeight: 700, color: T.purple, flex: 1 }}>📝 Blog Suggestions</span>
        {briefs.length > 0 && (
          <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 99,
                         background: T.teal + "18", color: T.teal, fontWeight: 700 }}>
            {briefs.length} briefs ready
          </span>
        )}
        <Btn variant="primary" small disabled={running}
             onClick={e => { e.stopPropagation(); runBatch() }}>
          {running ? "Running…" : briefs.length ? "↺ Refresh Briefs" : "▶ Run All Briefs"}
        </Btn>
        <span style={{ color: T.gray, fontSize: 11 }}>{open ? "▲" : "▼"}</span>
      </div>

      {/* Body */}
      {open && (
        <div style={{ padding: "12px 14px", borderTop: `1px solid ${T.border}` }}>
          {/* AI config for briefs */}
          <div style={{ marginBottom: 10 }}>
            <AITaskConfig
              config={aiConfig}
              onChange={setAiConfig}
              label="AI for all briefs"
              collapsed={true}
            />
          </div>
          {running && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: T.amber, marginBottom: 10 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: T.amber,
                             display: "inline-block", animation: "pulse 1s infinite" }} />
              {phase}
            </div>
          )}
          {error && (
            <div style={{ fontSize: 12, color: T.red, marginBottom: 10, padding: "8px 10px",
                          background: "rgba(255,59,48,0.06)", borderRadius: 7 }}>⚠ {error}</div>
          )}
          {!running && briefs.length === 0 && (
            <div style={{ fontSize: 12, color: T.textSoft, textAlign: "center", padding: "20px 0" }}>
              Click "Run All Briefs" to generate content angles, outlines, and hook ideas for your calendar items.
              <br /><span style={{ fontSize: 11, opacity: 0.7 }}>Processes up to 20 articles at once.</span>
            </div>
          )}
          {briefs.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 4 }}>
                Click a brief to expand it. Use the titles and outlines to guide your article generation.
              </div>
              {briefs.map((b, i) => (
                <div key={i} style={{ border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
                                background: selectedIdx === i ? "#fafaff" : "#fff", cursor: "pointer" }}
                       onClick={() => setSelectedIdx(selectedIdx === i ? null : i)}>
                    <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 7px", borderRadius: 99,
                                   background: T.purple + "15", color: T.purple }}>{b.intent || "info"}</span>
                    <span style={{ fontSize: 12, fontWeight: 600, flex: 1, overflow: "hidden",
                                   textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{b.keyword}</span>
                    {b.pillar && <span style={{ fontSize: 10, color: T.textSoft }}>{b.pillar}</span>}
                    <span style={{ color: T.gray, fontSize: 10 }}>{selectedIdx === i ? "▲" : "▼"}</span>
                  </div>
                  {selectedIdx === i && (
                    <div style={{ padding: "10px 12px", borderTop: `1px solid ${T.border}`, background: "#fafaff" }}>
                      {b.title_suggestions?.length > 0 && (
                        <div style={{ marginBottom: 8 }}>
                          <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4,
                                        textTransform: "uppercase", letterSpacing: ".05em" }}>Title Options</div>
                          {b.title_suggestions.slice(0, 3).map((t, ti) => (
                            <div key={ti} style={{ fontSize: 12, color: T.text, padding: "3px 0",
                                                   borderBottom: ti < 2 ? `1px solid ${T.border}` : "none" }}>
                              {t}
                            </div>
                          ))}
                        </div>
                      )}
                      {b.required_sections?.length > 0 && (
                        <div>
                          <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4,
                                        textTransform: "uppercase", letterSpacing: ".05em" }}>Outline</div>
                          {b.required_sections.slice(0, 5).map((s, si) => (
                            <div key={si} style={{ fontSize: 11, color: T.textSoft,
                                                   padding: "2px 0 2px 10px", borderLeft: `2px solid ${T.purple}44` }}>
                              {s}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ContentPlanTab({ strat, calendarData, projectId, sessionId, startDate, refetchCalendar, chooseAI, onRegenerate }) {
  const qc = useQueryClient()
  const [filter, setFilter] = useState("all")       // all | pending | generated
  const [search, setSearch]   = useState("")
  const [pillarFilter, setPillarFilter] = useState("all")
  const [aiProvider, setAiProvider] = useState("auto")
  const [genStatus, setGenStatus] = useState({})    // keyword → "pending"|"done"|"error"
  const [genError, setGenError] = useState({})      // keyword → error message string
  const [briefData, setBriefData] = useState({})    // keyword → brief object
  const [briefLoading, setBriefLoading] = useState({}) // keyword → bool
  const [openBrief, setOpenBrief] = useState({})    // keyword → bool (panel open)
  const [rebuilding, setRebuilding] = useState(false)
  const [rebuildResult, setRebuildResult] = useState(null)

  const handleRebuildCalendar = async () => {
    setRebuilding(true)
    setRebuildResult(null)
    try {
      const res = await api.rebuildCalendar(projectId, sessionId, startDate)
      const cal = res?.calendar || {}
      setRebuildResult(cal)
      await refetchCalendar()
      qc.invalidateQueries(["ssp-calendar", projectId, sessionId])
    } catch (e) {
      setRebuildResult({ error: String(e) })
    } finally {
      setRebuilding(false)
    }
  }
  const [briefAiConfig, setBriefAiConfig] = useState({}) // keyword → { ai_provider, custom_prompt }

  // Articles for this project — used to mark which items are already generated
  const { data: articlesData, refetch: refetchArticles } = useQuery({
    queryKey: ["ssp-articles", projectId],
    queryFn: async () => {
      const API = import.meta.env.VITE_API_URL || ""
      const t = localStorage.getItem("annaseo_token")
      const r = await fetch(`${API}/api/projects/${projectId}/content`, {
        headers: t ? { Authorization: `Bearer ${t}` } : {},
      })
      if (!r.ok) return []
      return r.json()
    },
    enabled: !!projectId,
    staleTime: 0,
    retry: false,
  })
  const articleList = Array.isArray(articlesData) ? articlesData : []
  const articleMap = {}
  articleList.forEach(a => { articleMap[(a.keyword || "").toLowerCase()] = a })

  const generateMut = useMutation({
    mutationFn: async ({ keyword, title, research_ai }) => {
      const API = import.meta.env.VITE_API_URL || ""
      const t = localStorage.getItem("annaseo_token")
      const r = await fetch(`${API}/api/content/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: JSON.stringify({ keyword, title, project_id: projectId, research_ai: research_ai || "auto" }),
      })
      if (!r.ok) {
        let errMsg = `HTTP ${r.status}`
        try { const j = await r.json(); errMsg = j?.detail || j?.message || errMsg } catch {}
        throw new Error(errMsg)
      }
      return r.json()
    },
    onSuccess: () => refetchArticles(),
  })

  const retryMut = useMutation({
    mutationFn: async (id) => {
      const API = import.meta.env.VITE_API_URL || ""
      const t = localStorage.getItem("annaseo_token")
      const r = await fetch(`${API}/api/content/${id}/retry`, {
        method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {},
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return r.json()
    },
    onSuccess: () => refetchArticles(),
  })

  const fetchBrief = async (item) => {
    const kw = item.keyword || item.title || ""
    if (briefData[kw] || briefLoading[kw]) {
      // Toggle panel open/closed
      setOpenBrief(o => ({ ...o, [kw]: !o[kw] }))
      return
    }
    setBriefLoading(p => ({ ...p, [kw]: true }))
    setOpenBrief(o => ({ ...o, [kw]: true }))
    const cfg = briefAiConfig[kw] || BRIEF_AI_DEFAULTS
    try {
      const API = import.meta.env.VITE_API_URL || ""
      const t = localStorage.getItem("annaseo_token")
      const r = await fetch(`${API}/api/ki/${projectId}/blog-brief`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: JSON.stringify({
          keyword: kw,
          title: item.title || kw,
          pillar: item.pillar || "",
          session_id: sessionId || "",
          ai_provider: cfg.ai_provider,
          custom_prompt: cfg.custom_prompt,
        }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      setBriefData(p => ({ ...p, [kw]: data }))
    } catch (e) {
      setBriefData(p => ({ ...p, [kw]: { keyword: kw, error: String(e) } }))
    } finally {
      setBriefLoading(p => ({ ...p, [kw]: false }))
    }
  }

  const statusColor = s => ({ draft: T.gray, generating: T.amber, review: "#8b5cf6", approved: T.teal, published: "#0f766e", failed: T.red }[s] || T.gray)

  // Build normalized item list from Phase 8 calendar or strategy weekly_plan/content_calendar
  const calItems = calendarData?.items || []
  const weeklyItems = useMemo(() => {
    if (calItems.length > 0) return []
    // Support both weekly_plan (expand mode) and content_calendar (apply mode)
    const plan = strat?.weekly_plan || strat?.content_calendar || []
    const base = startDate ? new Date(startDate) : new Date()
    const out = []
    plan.forEach(w => {
      const weekNum = w.week || w.month_number || plan.indexOf(w) + 1
      const weekDate = new Date(base)
      weekDate.setDate(weekDate.getDate() + (weekNum - 1) * 7)
      ;(w.articles || []).forEach(a => {
        out.push({
          title: typeof a === "string" ? a : (a?.title || a?.keyword || ""),
          keyword: typeof a === "string" ? a : (a?.target_keyword || a?.primary_keyword || a?.keyword || a?.title || ""),
          pillar: w.focus_pillar || w.pillar || w.focus || "General",
          article_type: typeof a === "object" ? (a?.page_type || a?.type || a?.intent || "") : "",
          week: weekNum,
          scheduled_date: weekDate.toISOString().slice(0, 10),
          word_count: typeof a === "object" ? a?.word_count : null,
        })
      })
    })
    return out
  }, [strat, calItems, startDate])

  // Primary list: Phase 8 items or weekly_plan-flattened items
  const primaryItems = calItems.length > 0 ? calItems : weeklyItems
  const pillars = [...new Set(primaryItems.map(i => i.pillar).filter(Boolean))]

  const filtered = primaryItems.filter(item => {
    const kw = (item.keyword || item.title || "").toLowerCase()
    const art = articleMap[kw]
    if (filter === "pending" && art) return false
    if (filter === "generated" && !art) return false
    if (search && !kw.includes(search.toLowerCase()) && !(item.title || "").toLowerCase().includes(search.toLowerCase())) return false
    if (pillarFilter !== "all" && item.pillar !== pillarFilter) return false
    return true
  })

  const pendingCount = primaryItems.filter(i => !articleMap[(i.keyword || i.title || "").toLowerCase()]).length
  const doneCount = primaryItems.length - pendingCount

  const handleGenerate = async (item) => {
    const kw = item.keyword || item.title || ""
    const title = item.title || kw

    // Ask which AI to use (if chooseAI is wired — always will be in normal usage)
    const picked = chooseAI ? await chooseAI(`Generate article: "${title.slice(0, 60)}"`) : "auto"
    if (!picked) return   // user cancelled

    setGenStatus(s => ({ ...s, [kw]: "pending" }))
    setGenError(s => { const n = { ...s }; delete n[kw]; return n })
    try {
      await generateMut.mutateAsync({ keyword: kw, title, research_ai: picked })
      setGenStatus(s => ({ ...s, [kw]: "done" }))
    } catch (err) {
      setGenStatus(s => ({ ...s, [kw]: "error" }))
      setGenError(s => ({ ...s, [kw]: err?.message || String(err) }))
    }
  }

  if (primaryItems.length === 0) {
    return (
      <Card style={{ textAlign: "center", padding: 48 }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>✍️</div>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>No content plan yet</div>
        <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 16 }}>
          Generate a strategy to create a content plan, or rebuild from existing data.
        </div>
        <button onClick={handleRebuildCalendar} disabled={rebuilding}
          style={{ padding: "8px 20px", borderRadius: 8, border: "none", background: T.purple, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
          {rebuilding ? "⏳ Rebuilding…" : "🔄 Rebuild Content Plan"}
        </button>
      </Card>
    )
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Sticky header — count + Regenerate + Rebuild */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: T.grayLight, borderRadius: 10, flexWrap: "wrap", position: "sticky", top: 0, zIndex: 2 }}>
        <div style={{ flex: 1, fontSize: 12, color: T.textSoft }}>
          <strong style={{ color: T.text }}>{primaryItems.length} blog ideas</strong>
          {" "}(strategy + intelligence questions + keywords)
          {rebuildResult && !rebuildResult.error && (
            <span style={{ color: T.teal, marginLeft: 8 }}>
              ✓ {rebuildResult.from_strategy || 0} strategy · {rebuildResult.from_intelligence || 0} intel · {rebuildResult.from_keywords || 0} keywords
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {onRegenerate && (
            <button onClick={() => {
              if (window.confirm("Re-run strategy generation? This will overwrite the current strategy.")) {
                onRegenerate()
              }
            }}
              style={{ padding: "5px 14px", borderRadius: 7, border: `1px solid ${T.purple}`, background: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer", color: T.purple }}>
              🔄 Regenerate Strategy
            </button>
          )}
          <button onClick={handleRebuildCalendar} disabled={rebuilding}
            style={{ padding: "5px 14px", borderRadius: 7, border: `1px solid ${T.border}`, background: "#fff", fontSize: 12, fontWeight: 600, cursor: rebuilding ? "not-allowed" : "pointer", color: T.textSoft }}>
            {rebuilding ? "⏳ Rebuilding…" : "↺ Rebuild Content Plan"}
          </button>
        </div>
      </div>

      {/* Batch Blog Suggestions panel */}
      <BatchBriefPanel
        projectId={projectId}
        sessionId={sessionId}
        items={primaryItems.slice(0, 20)}
        onBriefsLoaded={loaded => {
          const map = {}
          loaded.forEach(b => { if (b.keyword) map[b.keyword] = b })
          setBriefData(p => ({ ...p, ...map }))
        }}
      />

      {/* Controls */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        {/* Filter pills */}
        <div style={{ display: "flex", gap: 4 }}>
          {["all", "pending", "generated"].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: "5px 12px", borderRadius: 7, border: "none", fontSize: 11, fontWeight: filter === f ? 700 : 500,
              background: filter === f ? T.purple : T.grayLight,
              color: filter === f ? "#fff" : T.textSoft, cursor: "pointer",
            }}>
              {f === "all" ? `All (${primaryItems.length})` : f === "pending" ? `Pending (${pendingCount})` : `Generated (${doneCount})`}
            </button>
          ))}
        </div>

        {/* Search */}
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search titles…"
          style={{ flex: 1, minWidth: 140, padding: "5px 10px", borderRadius: 7, border: `1px solid ${T.border}`, fontSize: 12 }}
        />

        {/* Pillar filter */}
        {pillars.length > 1 && (
          <select value={pillarFilter} onChange={e => setPillarFilter(e.target.value)}
            style={{ padding: "5px 10px", borderRadius: 7, border: `1px solid ${T.border}`, fontSize: 12, cursor: "pointer" }}>
            <option value="all">All Pillars</option>
            {pillars.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        )}

        {/* AI Engine */}
        <select value={aiProvider} onChange={e => setAiProvider(e.target.value)}
          style={{ padding: "5px 10px", borderRadius: 7, border: `1px solid ${T.border}`, fontSize: 12, cursor: "pointer" }}>
          <option value="auto">🤖 Auto</option>
          <option value="groq">⚡ Groq</option>
          <option value="gemini">✨ Gemini</option>
          <option value="openai">🧠 GPT-4o</option>
          <option value="claude">🎭 Claude</option>
        </select>
      </div>

      {/* Progress bar */}
      {primaryItems.length > 0 && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: T.textSoft, marginBottom: 4 }}>
            <span>{doneCount} of {primaryItems.length} articles generated</span>
            <span>{Math.round((doneCount / primaryItems.length) * 100)}%</span>
          </div>
          <div style={{ height: 5, background: T.grayLight, borderRadius: 3, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${Math.round((doneCount / primaryItems.length) * 100)}%`,
              background: T.teal, borderRadius: 3, transition: "width .4s" }} />
          </div>
        </div>
      )}

      {/* Source label */}
      <div style={{ fontSize: 11, color: T.textSoft }}>
        {calItems.length > 0 ? `${calItems.length} articles in content calendar` : `${weeklyItems.length} items from strategy weekly plan`}
        {filter !== "all" && ` · showing ${filtered.length}`}
      </div>

      {/* Article grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(310px, 1fr))", gap: 10 }}>
        {filtered.slice(0, 80).map((item, i) => {
          const kw = item.keyword || item.title || ""
          const art = articleMap[kw.toLowerCase()]
          const gs = genStatus[kw]
          const isPending = gs === "pending"
          const genErr = genError[kw]
          const brief = briefData[kw]
          const briefOpen = openBrief[kw]
          const isBriefLoading = briefLoading[kw]
          return (
            <div key={i} style={{
              padding: "12px 14px", borderRadius: 10,
              background: art ? (art.status === "published" ? "#f0fdf4" : "#fefefe") : "#fff",
              border: `1px solid ${art ? (art.status === "published" ? T.teal + "44" : art.status === "failed" ? T.red + "44" : T.border) : T.border}`,
              boxShadow: T.cardShadow, display: "flex", flexDirection: "column", gap: 8,
            }}>
              {/* Title */}
              <div style={{ fontSize: 13, fontWeight: 600, color: T.text, lineHeight: 1.4 }}>
                {item.title || item.keyword}
              </div>

              {/* Meta badges */}
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {item.pillar && <Badge label={item.pillar} color={T.purple} />}
                {item.article_type && <Badge label={item.article_type} color={T.amber} />}
                {item.week && <span style={{ fontSize: 10, color: T.textSoft }}>Week {item.week}</span>}
                {item.scheduled_date && <span style={{ fontSize: 10, color: T.textSoft }}>{item.scheduled_date}</span>}
                {item.word_count && <span style={{ fontSize: 10, color: T.textSoft }}>{item.word_count}w</span>}
              </div>

              {/* Action row */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                {art ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 0 }}>
                    <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 5, fontWeight: 700,
                      background: statusColor(art.status) + "18", color: statusColor(art.status), flexShrink: 0 }}>
                      {art.status}
                    </span>
                    {art.seo_score > 0 && (
                      <span style={{ fontSize: 10, color: T.teal, fontWeight: 600 }}>SEO {Math.round(art.seo_score)}</span>
                    )}
                    {art.word_count > 0 && (
                      <span style={{ fontSize: 10, color: T.textSoft }}>{art.word_count}w</span>
                    )}
                    {art.status === "failed" && (
                      <button onClick={() => retryMut.mutate(art.article_id)} disabled={retryMut.isPending}
                        style={{ fontSize: 10, padding: "2px 8px", borderRadius: 5, border: `1px solid ${T.border}`,
                          background: "#fff", cursor: "pointer", color: T.textSoft }}>
                        🔄 Retry
                      </button>
                    )}
                  </div>
                ) : (
                  <div style={{ fontSize: 10, color: T.textSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                    {kw !== item.title ? kw : ""}
                  </div>
                )}

                <div style={{ display: "flex", gap: 5, flexShrink: 0 }}>
                  {/* Get Brief button — shows when article not yet generated */}
                  {!art && (
                    <button
                      onClick={() => fetchBrief(item)}
                      disabled={isBriefLoading}
                      title={briefOpen && brief ? "Hide brief" : "Get content brief"}
                      style={{
                        padding: "5px 10px", borderRadius: 7, border: `1px solid ${T.purple}44`,
                        fontSize: 11, fontWeight: 600, flexShrink: 0,
                        background: briefOpen ? T.purple + "15" : "#fff",
                        color: T.purple,
                        cursor: isBriefLoading ? "not-allowed" : "pointer",
                        opacity: isBriefLoading ? 0.5 : 1,
                      }}
                    >
                      {isBriefLoading ? "…" : briefOpen && brief ? "✕ Brief" : "📋 Brief"}
                    </button>
                  )}
                  {/* Generate button */}
                  {!art && !briefOpen && (
                    <button
                      onClick={() => handleGenerate(item)}
                      disabled={isPending}
                      style={{
                        padding: "5px 14px", borderRadius: 7, fontSize: 11, fontWeight: 700, flexShrink: 0,
                        background: isPending ? T.grayLight : gs === "error" ? "#fef2f2" : T.purple,
                        color: isPending ? T.textSoft : gs === "error" ? T.red : "#fff",
                        cursor: isPending ? "not-allowed" : "pointer",
                        border: gs === "error" ? `1px solid ${T.red}44` : "none",
                      }}
                    >
                      {isPending ? "⏳ Starting…" : gs === "done" ? "✓ Queued" : gs === "error" ? "⚠ Retry" : "✍️ Generate"}
                    </button>
                  )}
                </div>
              </div>

              {/* Per-item generation error */}
              {genErr && !isPending && (
                <div style={{ fontSize: 11, color: T.red, background: "#fef2f2", borderRadius: 6, padding: "5px 8px" }}>
                  ⚠ {genErr}
                </div>
              )}

              {/* Inline Brief Panel */}
              {briefOpen && brief && !brief.error && (
                <BriefPanel
                  brief={brief}
                  generating={isPending}
                  onGenerateFromBrief={(title) => handleGenerate({ ...item, title })}
                />
              )}
              {briefOpen && brief?.error && (
                <div style={{ fontSize: 11, color: T.red, padding: "6px 10px",
                              background: "rgba(255,59,48,0.06)", borderRadius: 7 }}>
                  ⚠ Brief failed: {brief.error}
                </div>
              )}
              {/* Per-item AI Config (only when brief is open and article not yet generated) */}
              {!art && briefOpen && (
                <AITaskConfig
                  config={briefAiConfig[kw] || BRIEF_AI_DEFAULTS}
                  onChange={v => setBriefAiConfig(p => ({ ...p, [kw]: v }))}
                  label="AI for this brief"
                  collapsed={true}
                />
              )}
            </div>
          )
        })}
      </div>

      {filtered.length > 80 && (
        <div style={{ textAlign: "center", fontSize: 12, color: T.textSoft, padding: 8 }}>
          Showing 80 of {filtered.length} items — use search or filters to narrow down.
        </div>
      )}
      {filtered.length === 0 && primaryItems.length > 0 && (
        <div style={{ textAlign: "center", padding: 24, fontSize: 13, color: T.textSoft }}>No items match filters.</div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB: LINK BUILDING
// ─────────────────────────────────────────────────────────────────────────────
function LinkBuildingTab({ linksData }) {
  const links = linksData?.links || linksData?.items || []

  if (links.length === 0) {
    return (
      <Card style={{ textAlign: "center", padding: 48 }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>🔗</div>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>No link data yet</div>
        <div style={{ fontSize: 13, color: T.textSoft }}>
          Run Phase 7 (Internal Links) in Keywords v2 to generate internal link recommendations for this session.
        </div>
      </Card>
    )
  }

  // Group by link_type
  const byType = links.reduce((acc, l) => {
    const t = l.link_type || l.type || "general"
    if (!acc[t]) acc[t] = []
    acc[t].push(l)
    return acc
  }, {})

  const typeColors = { internal: T.purple, external: T.teal, anchor: T.amber, backlink: T.red }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ fontSize: 12, color: T.textSoft }}>
        {links.length} link recommendations across {Object.keys(byType).length} types
      </div>
      {Object.entries(byType).map(([type, items]) => (
        <Card key={type}>
          <div style={{ fontSize: 12, fontWeight: 700, color: typeColors[type] || T.purpleDark, marginBottom: 12, textTransform: "capitalize" }}>
            {type} Links ({items.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {items.slice(0, 20).map((link, i) => (
              <div key={i} style={{ display: "flex", gap: 10, padding: "8px 10px", background: T.grayLight, borderRadius: 8, alignItems: "flex-start" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {(link.from_page || link.from_keyword) && <div style={{ fontSize: 11, color: T.textSoft }}>From: <strong style={{ wordBreak: "break-all" }}>{link.from_page || link.from_keyword}</strong></div>}
                  {(link.to_page || link.to_keyword) && <div style={{ fontSize: 11, color: T.textSoft }}>To: <strong style={{ wordBreak: "break-all" }}>{link.to_page || link.to_keyword}</strong></div>}
                  {link.anchor_text && <div style={{ fontSize: 12, fontWeight: 600, color: T.text, marginTop: 2 }}>"{link.anchor_text}"</div>}
                  {link.placement && <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>Placement: {link.placement}</div>}
                  {link.intent && <div style={{ fontSize: 11, color: T.textSoft }}>Intent: {link.intent}</div>}
                  {link.reason && <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2, lineHeight: 1.4 }}>{link.reason}</div>}
                </div>
                {link.strength != null && (
                  <div style={{ flexShrink: 0, fontSize: 11, fontWeight: 700, color: link.strength >= 0.7 ? T.teal : T.amber }}>
                    {Math.round(link.strength * 100)}%
                  </div>
                )}
              </div>
            ))}
            {items.length > 20 && <div style={{ fontSize: 11, color: T.textSoft, textAlign: "center" }}>+{items.length - 20} more links</div>}
          </div>
        </Card>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TREE HELPERS
// ─────────────────────────────────────────────────────────────────────────────
function TreeNode({ icon, label, type, color, depth, subtitle, expandable, collapsed, onClick, badge, badgeColor }) {
  return (
    <div
      onClick={expandable ? onClick : undefined}
      style={{
        display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
        marginBottom: 4, borderRadius: 8, cursor: expandable ? "pointer" : "default",
        background: expandable ? (collapsed ? "#fff" : `${color}08`) : "transparent",
        border: expandable ? `1px solid ${color}22` : "1px solid transparent",
        transition: "background .15s",
      }}
    >
      <span style={{ fontSize: depth <= 1 ? 18 : 14 }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: depth <= 1 ? 14 : 13, fontWeight: depth <= 2 ? 700 : 500, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {label}
          {expandable && <span style={{ fontSize: 10, color: T.gray, marginLeft: 6 }}>{collapsed ? "▶" : "▼"}</span>}
        </div>
        {subtitle && <div style={{ fontSize: 10, color: T.textSoft, marginTop: 1 }}>{subtitle}</div>}
      </div>
      {badge && (
        <span style={{ fontSize: 9, fontWeight: 800, padding: "2px 8px", borderRadius: 99,
          background: (badgeColor || color) + "18", color: badgeColor || color, flexShrink: 0 }}>
          {badge}
        </span>
      )}
    </div>
  )
}

function CadenceControl({ label, value, onChange }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
      <div style={{ fontSize: 9, fontWeight: 700, color: T.textSoft, textTransform: "uppercase" }}>{label}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <button onClick={() => onChange(Math.max(0, value - 1))}
          style={{ width: 22, height: 22, borderRadius: 6, border: `1px solid ${T.border}`, background: "#fff",
            cursor: "pointer", fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center" }}>−</button>
        <span style={{ fontSize: 13, fontWeight: 700, minWidth: 24, textAlign: "center" }}>{value}</span>
        <button onClick={() => onChange(value + 1)}
          style={{ width: 22, height: 22, borderRadius: 6, border: `1px solid ${T.border}`, background: "#fff",
            cursor: "pointer", fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center" }}>+</button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB: CONTENT MAP (Tree / Hierarchy / Cadence)
// ─────────────────────────────────────────────────────────────────────────────
function ContentTreeTab({ treeData, strat, calendarData, linksData, projectId, sessionId, onGoToStrategy, onGoToParams }) {
  const [expanded, setExpanded] = useState({})
  const [cadence, setCadence] = useState({})
  const [expandAll, setExpandAll] = useState(false)

  // API returns { tree: { universe: { ... } } }
  const universe = treeData?.tree?.universe || treeData?.universe
  const pillars = universe?.pillars || []
  const totalClusters = pillars.reduce((s, p) => s + (p.clusters?.length || 0), 0)
  const totalKeywords = pillars.reduce((s, p) =>
    s + (p.clusters || []).reduce((s2, c) => s2 + (c.keywords?.length || 0), 0), 0)
  const top100Count = pillars.reduce((s, p) =>
    s + (p.clusters || []).reduce((s2, c) => s2 + (c.keywords || []).filter(k => k.top100).length, 0), 0)

  const links = linksData?.items || linksData?.links || []
  const linksByType = links.reduce((acc, l) => {
    const t = l.link_type || "other"
    acc[t] = (acc[t] || 0) + 1
    return acc
  }, {})

  const toggle = (key) => setExpanded(e => ({ ...e, [key]: !e[key] }))

  // Initialize cadence for each pillar
  useEffect(() => {
    if (pillars.length && !Object.keys(cadence).length) {
      const init = {}
      pillars.forEach(p => { init[p.name] = { perDay: 0, perWeek: 2, perMonth: 9 } })
      setCadence(init)
    }
  }, [pillars.length])

  // Expand all / collapse all
  const handleExpandAll = () => {
    if (expandAll) {
      setExpanded({})
      setExpandAll(false)
    } else {
      const all = {}
      pillars.forEach((p, pi) => {
        all[`pillar-${pi}`] = true
        ;(p.clusters || []).forEach((_, ci) => { all[`cluster-${pi}-${ci}`] = true })
      })
      setExpanded(all)
      setExpandAll(true)
    }
  }

  const mappedPageIcon = (mp) => ({
    product_page: "🛍️", category_page: "📂", b2b_page: "🏢",
    local_page: "📍", blog_page: "📝",
  }[mp] || "📄")

  const intentColor = (i) => ({
    purchase: T.teal, informational: T.purple, commercial: T.amber,
    navigational: T.gray, local: "#10b981", comparison: "#8b5cf6",
  }[(i || "").toLowerCase()] || T.gray)

  if (!universe || !pillars.length) {
    return (
      <Card style={{ textAlign: "center", padding: 48 }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>🌳</div>
        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Content Map Not Ready</div>
        <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 20 }}>
          Run the full Research pipeline and generate Strategy to build your content tree.
          The tree shows how all your content connects — from supporting articles up to your home page.
        </div>
        <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
          {onGoToParams && <Btn onClick={onGoToParams} variant="primary">⚙️ Configure & Generate</Btn>}
          {onGoToStrategy && <Btn onClick={onGoToStrategy} variant="outline">🗺️ View Strategy</Btn>}
        </div>
      </Card>
    )
  }

  // Compute total planned cadence
  const totalPerWeek = Object.values(cadence).reduce((s, c) => s + (c.perWeek || 0), 0)
  const totalArticles = totalKeywords
  const weeksTotal = totalPerWeek > 0 ? Math.ceil(totalArticles / totalPerWeek) : 0

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

      {/* ═══ GUIDED WORKFLOW BANNER ═══ */}
      <Card style={{
        background: "linear-gradient(135deg, #eff6ff 0%, #f0fdf4 50%, #faf5ff 100%)",
        border: `1px solid ${T.purple}30`, padding: 20,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <span style={{ fontSize: 28 }}>🎯</span>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, color: T.purpleDark }}>Content Implementation Guide</div>
            <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
              Build your content <strong>top-down</strong> for maximum SEO impact.
              Start with pillar hubs, then clusters, then supporting articles. Every piece links upward to your product pages.
            </div>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
          {[
            { step: 1, icon: "🏛️", label: "Pillar Hub Pages", count: pillars.length, color: "#6366f1",
              hint: "Main authority pages per topic. These target your highest-value head terms." },
            { step: 2, icon: "📦", label: "Cluster Pages", count: totalClusters, color: "#f59e0b",
              hint: "Sub-topic pages that group related keywords. Each links up to its pillar." },
            { step: 3, icon: "📄", label: "Supporting Articles", count: totalKeywords, color: "#10b981",
              hint: "Individual SEO posts targeting specific long-tail keywords." },
            { step: 4, icon: "🔗", label: "Internal Links", count: links.length, color: "#ef4444",
              hint: "Connect every article to its cluster, every cluster to its pillar, every pillar to products." },
          ].map(s => (
            <div key={s.step} style={{
              padding: "14px 16px", borderRadius: 12, background: "#fff",
              border: `2px solid ${s.step === 1 ? s.color : T.border}`,
              position: "relative", boxShadow: s.step === 1 ? `0 0 0 3px ${s.color}22` : "none",
            }}>
              {s.step === 1 && (
                <div style={{ position: "absolute", top: -9, right: 10, fontSize: 9, fontWeight: 800,
                  padding: "2px 10px", borderRadius: 99, background: s.color, color: "#fff", letterSpacing: ".04em" }}>
                  START HERE
                </div>
              )}
              <div style={{ fontSize: 26, marginBottom: 8 }}>{s.icon}</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.text, marginBottom: 3 }}>Step {s.step}</div>
              <div style={{ fontSize: 11, fontWeight: 600, color: s.color, marginBottom: 6 }}>{s.label}</div>
              <div style={{ fontSize: 10, color: T.textSoft, lineHeight: 1.4, marginBottom: 8 }}>{s.hint}</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: s.color }}>{s.count}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* ═══ STATS BAR ═══ */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", padding: "10px 16px",
        background: T.grayLight, borderRadius: 10, alignItems: "center" }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark }}>📊 {universe.name}</span>
        <span style={{ fontSize: 11, color: T.textSoft }}>{pillars.length} pillars</span>
        <span style={{ fontSize: 11, color: T.textSoft }}>·</span>
        <span style={{ fontSize: 11, color: T.textSoft }}>{totalClusters} clusters</span>
        <span style={{ fontSize: 11, color: T.textSoft }}>·</span>
        <span style={{ fontSize: 11, color: T.textSoft }}>{totalKeywords} keywords</span>
        {top100Count > 0 && (
          <>
            <span style={{ fontSize: 11, color: T.textSoft }}>·</span>
            <span style={{ fontSize: 11, color: T.teal, fontWeight: 600 }}>⭐ {top100Count} in top 100</span>
          </>
        )}
        {links.length > 0 && (
          <>
            <span style={{ fontSize: 11, color: T.textSoft }}>·</span>
            <span style={{ fontSize: 11, color: T.purple }}>{links.length} internal links</span>
          </>
        )}
        <div style={{ marginLeft: "auto" }}>
          <button onClick={handleExpandAll} style={{
            padding: "4px 12px", borderRadius: 7, border: `1px solid ${T.border}`,
            background: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer", color: T.purpleDark,
          }}>
            {expandAll ? "▲ Collapse All" : "▼ Expand All"}
          </button>
        </div>
      </div>

      {/* ═══ TREE VISUALIZATION ═══ */}
      <Card style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "14px 18px", borderBottom: `1px solid ${T.border}`,
          background: "linear-gradient(90deg, #fafbff 0%, #f8faf8 100%)" }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.purpleDark }}>🌳 Content Hierarchy</div>
          <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
            Every article links to its cluster → cluster links to its pillar → pillar links to your product/home page.
            Click nodes to expand. ⭐ = Top 100 keyword.
          </div>
        </div>

        <div style={{ padding: "18px 20px" }}>
          {/* HOME NODE */}
          <TreeNode icon="🏠" label="Home Page" type="home" color="#1e40af" depth={0}
            subtitle="All content funnels traffic here" />

          <div style={{ marginLeft: 22, borderLeft: "2px solid #bfdbfe", paddingLeft: 18, paddingTop: 4, paddingBottom: 4 }}>
            {/* PRODUCT PAGES LEVEL */}
            <TreeNode icon="🛍️" label="Product / Service Pages" type="product" color="#059669" depth={1}
              subtitle={`Pillar hubs link here · ${Object.entries(linksByType).filter(([t]) => t === "pillar_to_product").map(([, c]) => c).reduce((a, b) => a + b, 0) || 0} product links mapped`} />

            <div style={{ marginLeft: 22, borderLeft: "2px solid #a7f3d0", paddingLeft: 18, paddingTop: 4, paddingBottom: 4 }}>
              {/* PILLAR HUBS */}
              {pillars.map((pillar, pi) => {
                const pKey = `pillar-${pi}`
                const isExpanded = expanded[pKey] !== undefined ? expanded[pKey] : (pi < 2) // first 2 expanded by default
                const clusterCount = pillar.clusters?.length || 0
                const kwCount = (pillar.clusters || []).reduce((s, c) => s + (c.keywords?.length || 0), 0)
                const top100InPillar = (pillar.clusters || []).reduce((s, c) =>
                  s + (c.keywords || []).filter(k => k.top100).length, 0)
                const pCadence = cadence[pillar.name]

                return (
                  <div key={pi} style={{ marginBottom: 2 }}>
                    <TreeNode
                      icon="🏛️" label={pillar.name} type="pillar" color="#6366f1" depth={2}
                      subtitle={`${clusterCount} clusters · ${kwCount} keywords${top100InPillar ? ` · ⭐ ${top100InPillar} top-100` : ""}`}
                      expandable collapsed={!isExpanded}
                      onClick={() => toggle(pKey)}
                      badge={pCadence?.perWeek ? `${pCadence.perWeek}/week` : null}
                      badgeColor="#6366f1"
                    />

                    {isExpanded && (
                      <div style={{ marginLeft: 22, borderLeft: "2px solid #c4b5fd", paddingLeft: 18, paddingTop: 4, paddingBottom: 4 }}>
                        {(pillar.clusters || []).map((cluster, ci) => {
                          const cKey = `cluster-${pi}-${ci}`
                          const cExpanded = expanded[cKey] || false
                          const keywords = cluster.keywords || []

                          return (
                            <div key={ci} style={{ marginBottom: 2 }}>
                              <TreeNode
                                icon="📦" label={cluster.name} type="cluster" color="#f59e0b" depth={3}
                                subtitle={`${keywords.length} keywords`}
                                expandable collapsed={!cExpanded}
                                onClick={() => toggle(cKey)}
                              />

                              {cExpanded && keywords.length > 0 && (
                                <div style={{ marginLeft: 22, borderLeft: "2px solid #fde68a", paddingLeft: 18, paddingTop: 4, paddingBottom: 4 }}>
                                  {keywords.map((kw, ki) => (
                                    <TreeNode
                                      key={ki}
                                      icon={kw.top100 ? "⭐" : mappedPageIcon(kw.mapped_page)}
                                      label={kw.name}
                                      type="keyword"
                                      color={intentColor(kw.intent)}
                                      depth={4}
                                      subtitle={[
                                        kw.intent || null,
                                        kw.mapped_page ? kw.mapped_page.replace(/_/g, " ") : null,
                                        kw.score ? `score ${Math.round(kw.score)}` : null,
                                      ].filter(Boolean).join(" · ")}
                                      badge={kw.top100 ? "TOP 100" : null}
                                      badgeColor={T.teal}
                                    />
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </Card>

      {/* ═══ PUBLISHING CADENCE PER PILLAR ═══ */}
      <Card>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.purpleDark }}>📅 Publishing Cadence</div>
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
              Set how many articles to publish per pillar. Adjust the pace for each topic independently.
            </div>
          </div>
          {totalPerWeek > 0 && (
            <div style={{ textAlign: "right", flexShrink: 0 }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: T.teal }}>{totalPerWeek}/week total</div>
              <div style={{ fontSize: 11, color: T.textSoft }}>{weeksTotal} weeks to publish all {totalArticles} articles</div>
            </div>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {pillars.map((p, i) => {
            const c = cadence[p.name] || { perDay: 0, perWeek: 2, perMonth: 9 }
            const kwCount = (p.clusters || []).reduce((s, cl) => s + (cl.keywords?.length || 0), 0)
            const weeksForPillar = c.perWeek > 0 ? Math.ceil(kwCount / c.perWeek) : "∞"

            return (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 14, padding: "14px 18px",
                background: T.grayLight, borderRadius: 12, border: `1px solid ${T.border}`,
                flexWrap: "wrap",
              }}>
                <div style={{ flex: 1, minWidth: 140 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>🏛️ {p.name}</div>
                  <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
                    {kwCount} articles · {p.clusters?.length || 0} clusters
                  </div>
                </div>

                <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                  <CadenceControl label="Per Day" value={c.perDay || 0}
                    onChange={v => setCadence(prev => ({
                      ...prev, [p.name]: { perDay: v, perWeek: Math.round(v * 7), perMonth: Math.round(v * 30) }
                    }))} />
                  <CadenceControl label="Per Week" value={c.perWeek || 0}
                    onChange={v => setCadence(prev => ({
                      ...prev, [p.name]: { perDay: +(v / 7).toFixed(1), perWeek: v, perMonth: Math.round(v * 4.3) }
                    }))} />
                  <CadenceControl label="Per Month" value={c.perMonth || 0}
                    onChange={v => setCadence(prev => ({
                      ...prev, [p.name]: { perDay: +(v / 30).toFixed(1), perWeek: Math.round(v / 4.3), perMonth: v }
                    }))} />
                </div>

                <div style={{ minWidth: 90, textAlign: "right" }}>
                  <div style={{ fontSize: 14, fontWeight: 800, color: T.teal }}>
                    {weeksForPillar === "∞" ? "∞" : `${weeksForPillar}w`}
                  </div>
                  <div style={{ fontSize: 10, color: T.textSoft }}>to complete</div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Total summary */}
        {totalPerWeek > 0 && (
          <div style={{
            marginTop: 14, padding: "14px 18px", borderRadius: 10,
            background: "linear-gradient(135deg, #f0fdf4 0%, #eff6ff 100%)",
            border: `1px solid ${T.teal}33`,
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#166534" }}>📈 Publishing Overview</div>
              <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
                At current pace: ~{Math.round(totalPerWeek * 4.3)} articles/month · all {totalArticles} articles in {weeksTotal} weeks ({Math.round(weeksTotal / 4.3)} months)
              </div>
            </div>
            <div style={{ fontSize: 10, color: T.textSoft }}>
              {Object.entries(cadence).filter(([, v]) => v.perWeek > 0).map(([name, v]) =>
                `${name}: ${v.perWeek}/wk`
              ).join(" · ")}
            </div>
          </div>
        )}
      </Card>

      {/* ═══ INTERNAL LINK MAP ═══ */}
      {links.length > 0 && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.purpleDark, marginBottom: 12 }}>🔗 Internal Link Map</div>
          <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 12 }}>
            These links connect your content hierarchy. Each link type strengthens the topical authority of your site.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 10 }}>
            {Object.entries(linksByType).map(([type, count]) => {
              const typeLabels = {
                keyword_to_pillar: { icon: "📄→🏛️", label: "Article → Pillar" },
                cluster_to_pillar: { icon: "📦→🏛️", label: "Cluster → Pillar" },
                pillar_to_product: { icon: "🏛️→🛍️", label: "Pillar → Product" },
                sibling: { icon: "📄↔📄", label: "Sibling Links" },
                cross_cluster: { icon: "📦↔📦", label: "Cross-Cluster" },
                location: { icon: "📍→📍", label: "Location Links" },
              }
              const tl = typeLabels[type] || { icon: "🔗", label: type.replace(/_/g, " ") }
              return (
                <div key={type} style={{
                  padding: "14px 14px", background: T.grayLight, borderRadius: 10, textAlign: "center",
                  border: `1px solid ${T.border}`,
                }}>
                  <div style={{ fontSize: 20, marginBottom: 6 }}>{tl.icon}</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: T.purple }}>{count}</div>
                  <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>{tl.label}</div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* ═══ NAVIGATION ═══ */}
      <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
        {onGoToStrategy && <Btn onClick={onGoToStrategy} variant="outline">🗺️ View Full Strategy</Btn>}
        {onGoToParams && <Btn onClick={onGoToParams} variant="outline">⚙️ Adjust Parameters</Btn>}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB: CONTENT PARAMETERS
// ─────────────────────────────────────────────────────────────────────────────
function ContentParametersTab({ params, setParams, onGenerate, running, hasStrategy, projectId, sessionId, pillarStats, strategyPrereqs, onGoToIntelligence }) {
  const inStyle = {
    width: "100%", padding: "8px 10px", borderRadius: 8,
    border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box",
    background: "#fff",
  }

  const setMix = (key, val) => {
    const num = Math.max(0, Math.min(100, parseInt(val) || 0))
    setParams(p => ({ ...p, content_mix: { ...p.content_mix, [key]: num } }))
  }

  const toggleDay = (day) => {
    setParams(p => {
      const days = p.publishing_cadence.includes(day)
        ? p.publishing_cadence.filter(d => d !== day)
        : [...p.publishing_cadence, day]
      return { ...p, publishing_cadence: days }
    })
  }

  const totalArticles = params.blogs_per_week * params.duration_weeks
  const estCost = (COST_EST[params.ai_provider] || 0) * 10 // approx per strategy call
  const mixTotal = (params.content_mix.informational || 0) + (params.content_mix.transactional || 0) + (params.content_mix.commercial || 0)
  const mixOk = mixTotal === 100
  const prereqs = strategyPrereqs || { items: [], readyCount: 0, totalCount: 0, allPrereqsMet: false }
  const prereqsLoaded = !!prereqs.hasSnapshot
  const missingPrereqs = (prereqs.items || []).filter(i => !i.done).map(i => i.label)
  const canGenerate = mixOk && params.publishing_cadence.length > 0 && (!prereqsLoaded || prereqs.allPrereqsMet)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 820 }}>

      {/* ── Workflow guidance ── */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, padding: "12px 16px",
        background: "linear-gradient(135deg, #eff6ff 0%, #faf5ff 100%)",
        borderRadius: 10, border: `1px solid ${T.purple}25`,
      }}>
        <span style={{ fontSize: 20 }}>📋</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark }}>Strategy Parameters</div>
          <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
            Configure your content velocity, schedule, and AI preferences. Then complete the <strong>Research</strong> pipeline before generating strategy.
          </div>
        </div>
      </div>

      <Card style={{
        border: `1px solid ${prereqs.allPrereqsMet ? "#86efac" : "#fde68a"}`,
        background: prereqs.allPrereqsMet ? "#f0fdf4" : "#fffbeb",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: prereqs.allPrereqsMet ? "#166534" : "#92400e" }}>
            🧠 Research Readiness
          </div>
          <div style={{ fontSize: 11, fontWeight: 700, color: prereqs.allPrereqsMet ? T.teal : T.amber }}>
            {prereqsLoaded ? `${prereqs.readyCount}/${prereqs.totalCount} ready` : "Checking…"}
          </div>
        </div>
        <div style={{ fontSize: 11, color: T.textSoft, marginTop: 6, lineHeight: 1.5 }}>
          {!prereqsLoaded
            ? "Loading Research readiness status..."
            : prereqs.allPrereqsMet
            ? "All stage prerequisites are complete. You can generate strategy now."
            : `Complete first: ${missingPrereqs.join(", ") || "Research steps"}.`}
        </div>
        {prereqsLoaded && !prereqs.allPrereqsMet && onGoToIntelligence && (
          <button
            onClick={onGoToIntelligence}
            style={{
              marginTop: 10, padding: "6px 10px", borderRadius: 7,
              border: `1px solid ${T.border}`, background: "#fff", color: T.purpleDark,
              cursor: "pointer", fontSize: 11, fontWeight: 600,
            }}
          >
            Open Research Tab
          </button>
        )}
      </Card>

      {/* ── Velocity + Duration ── */}
      <Card style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: T.purpleDark }}>📅 Publishing Velocity</div>
          <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 6 }}>
            Blogs per week
          </label>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <input
              type="range" min={1} max={7} step={1}
              value={params.blogs_per_week}
              onChange={e => setParams(p => ({ ...p, blogs_per_week: +e.target.value }))}
              style={{ flex: 1 }}
            />
            <span style={{ fontWeight: 800, fontSize: 22, color: T.purple, minWidth: 28, textAlign: "center" }}>
              {params.blogs_per_week}
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
            {[1,2,3,4,5,6,7].map(n => (
              <button
                key={n}
                onClick={() => setParams(p => ({ ...p, blogs_per_week: n }))}
                style={{
                  width: 28, height: 28, borderRadius: 6, border: "none",
                  background: params.blogs_per_week === n ? T.purple : T.grayLight,
                  color: params.blogs_per_week === n ? "#fff" : T.textSoft,
                  fontWeight: 700, fontSize: 12, cursor: "pointer",
                }}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: T.purpleDark }}>⏱️ Campaign Duration</div>
          <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 6 }}>
            Weeks
          </label>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <input
              type="range" min={4} max={52} step={4}
              value={params.duration_weeks}
              onChange={e => setParams(p => ({ ...p, duration_weeks: +e.target.value }))}
              style={{ flex: 1 }}
            />
            <span style={{ fontWeight: 800, fontSize: 22, color: T.purple, minWidth: 42, textAlign: "center" }}>
              {params.duration_weeks}w
            </span>
          </div>
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 6 }}>
            {[4,8,12,16,24,36,52].map(w => (
              <button
                key={w}
                onClick={() => setParams(p => ({ ...p, duration_weeks: w }))}
                style={{
                  padding: "3px 8px", borderRadius: 6, border: "none",
                  background: params.duration_weeks === w ? T.purple : T.grayLight,
                  color: params.duration_weeks === w ? "#fff" : T.textSoft,
                  fontWeight: 600, fontSize: 11, cursor: "pointer",
                }}
              >
                {w}w {w === 12 ? "(3mo)" : w === 24 ? "(6mo)" : w === 52 ? "(1yr)" : ""}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* ── Per-Pillar Blog Allocation ── */}
      {(() => {
        const pillars = pillarStats?.pillars || []
        if (!pillars.length) return null
        const pillarVelocity = params.pillar_velocity || {}
        const totalAssigned = pillars.reduce((s, p) => s + (pillarVelocity[p.pillar] || 0), 0)
        const totalArticles = params.blogs_per_week * params.duration_weeks
        const unassigned = totalArticles - totalAssigned
        const setPillarVel = (pillar, val) => {
          const num = Math.max(0, parseInt(val) || 0)
          setParams(p => ({ ...p, pillar_velocity: { ...(p.pillar_velocity || {}), [pillar]: num } }))
        }
        const autoDistribute = () => {
          const perPillar = Math.floor(totalArticles / pillars.length)
          const remainder = totalArticles - perPillar * pillars.length
          const dist = {}
          pillars.forEach((p, i) => { dist[p.pillar] = perPillar + (i < remainder ? 1 : 0) })
          setParams(pr => ({ ...pr, pillar_velocity: dist }))
        }
        return (
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark }}>🏗️ Blogs per Pillar</div>
                <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
                  Set how many articles each pillar should get over {params.duration_weeks} weeks ({totalArticles} total)
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: unassigned === 0 ? T.teal : unassigned > 0 ? T.amber : T.red }}>
                  {unassigned === 0 ? "✓ All assigned" : unassigned > 0 ? `${unassigned} unassigned` : `${Math.abs(unassigned)} over-assigned`}
                </span>
                <button onClick={autoDistribute} style={{
                  padding: "4px 10px", borderRadius: 6, border: `1px solid ${T.border}`,
                  background: T.grayLight, color: T.purpleDark, fontSize: 11, fontWeight: 600, cursor: "pointer",
                }}>
                  Auto-distribute
                </button>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
              {pillars.map((p, i) => {
                const count = pillarVelocity[p.pillar] || 0
                const kwCount = p.count || 0
                const colors = ["#6366f1","#10b981","#f59e0b","#ef4444","#8b5cf6","#06b6d4","#ec4899","#84cc16","#f97316","#14b8a6"]
                const c = colors[i % colors.length]
                return (
                  <div key={p.pillar} style={{
                    padding: "10px 12px", borderRadius: 8, border: `1px solid ${c}30`,
                    background: `${c}08`,
                  }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: c, marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {p.pillar}
                    </div>
                    <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 6 }}>{kwCount} keywords</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <input
                        type="number" min={0} max={totalArticles}
                        value={count}
                        onChange={e => setPillarVel(p.pillar, e.target.value)}
                        style={{
                          width: 52, padding: "4px 6px", borderRadius: 6,
                          border: `1px solid ${c}40`, fontSize: 14, fontWeight: 700,
                          textAlign: "center", color: c, background: "#fff",
                        }}
                      />
                      <span style={{ fontSize: 11, color: T.textSoft }}>articles</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </Card>
        )
      })()}

      {/* ── Publishing Days ── */}
      <Card>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: T.purpleDark }}>📆 Publishing Days</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {DAYS.map(day => {
            const active = params.publishing_cadence.includes(day)
            return (
              <button
                key={day}
                onClick={() => toggleDay(day)}
                style={{
                  padding: "7px 14px", borderRadius: 8, border: "none",
                  background: active ? T.purple : T.grayLight,
                  color: active ? "#fff" : T.textSoft,
                  fontWeight: 600, fontSize: 13, cursor: "pointer",
                  transition: "all .12s",
                }}
              >
                {day}
              </button>
            )
          })}
        </div>
        {params.publishing_cadence.length > 0 && (
          <div style={{ marginTop: 10, fontSize: 11, color: T.textSoft }}>
            Publishing on: {params.publishing_cadence.join(", ")}
          </div>
        )}
      </Card>

      {/* ── Content Mix ── */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark }}>🎯 Content Mix</div>
          <span style={{ fontSize: 11, fontWeight: 700, color: mixOk ? T.teal : T.red }}>
            Total: {mixTotal}% {mixOk ? "✓" : "(must = 100%)"}
          </span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
          {[
            { key: "informational", label: "Informational", color: "#3b82f6", icon: "📘", desc: "How-to, guides, education" },
            { key: "transactional", label: "Transactional",  color: "#10b981", icon: "🛒", desc: "Buy, shop, purchase intent" },
            { key: "commercial",   label: "Commercial",     color: "#8b5cf6", icon: "🔍", desc: "Best, review, compare" },
          ].map(({ key, label, color, icon, desc }) => (
            <div key={key} style={{ background: `${color}08`, borderRadius: 10, padding: "12px 14px", border: `1px solid ${color}30` }}>
              <div style={{ fontSize: 12, fontWeight: 700, color, marginBottom: 6 }}>{icon} {label}</div>
              <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 10 }}>{desc}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="range" min={0} max={100} step={5}
                  value={params.content_mix[key] || 0}
                  onChange={e => setMix(key, e.target.value)}
                  style={{ flex: 1 }}
                />
                <input
                  type="number" min={0} max={100}
                  value={params.content_mix[key] || 0}
                  onChange={e => setMix(key, e.target.value)}
                  style={{ ...inStyle, width: 56, padding: "5px 8px", textAlign: "center", fontWeight: 700, fontSize: 16, color }}
                />
                <span style={{ fontSize: 12, color: T.textSoft }}>%</span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── AI Provider ── */}
      <Card>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: T.purpleDark }}>🤖 AI Provider for Strategy</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
          {PROVIDERS.map(p => {
            const active = params.ai_provider === p.id
            return (
              <button
                key={p.id}
                onClick={() => setParams(pr => ({ ...pr, ai_provider: p.id }))}
                title={p.desc}
                style={{
                  padding: "10px 8px", borderRadius: 10,
                  border: active ? `2px solid ${p.color}` : `1px solid ${T.border}`,
                  background: active ? `${p.color}12` : "#fff",
                  cursor: "pointer", display: "flex", flexDirection: "column",
                  alignItems: "center", gap: 5, transition: "all .12s",
                }}
              >
                <span style={{ fontSize: 20 }}>{p.icon}</span>
                <span style={{ fontSize: 11, fontWeight: active ? 700 : 500, color: active ? p.color : T.textSoft }}>
                  {p.label}
                </span>
              </button>
            )
          })}
        </div>
        <div style={{ marginTop: 8, fontSize: 11, color: T.textSoft }}>
          {PROVIDERS.find(p => p.id === params.ai_provider)?.desc}
          {COST_EST[params.ai_provider] > 0 && (
            <span style={{ marginLeft: 8, color: T.amber }}>
              ≈ ${(estCost).toFixed(3)} estimated cost
            </span>
          )}
          {COST_EST[params.ai_provider] === 0 && (
            <span style={{ marginLeft: 8, color: T.teal }}> · Free</span>
          )}
        </div>
      </Card>

      {/* ── Campaign Start Date ── */}
      <Card style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, alignItems: "center" }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8, color: T.purpleDark }}>📅 Campaign Start Date</div>
          <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 8 }}>
            Used to compute actual publish dates in the Content Plan. Leave blank to use today.
          </div>
          <input
            type="date"
            value={params.start_date || ""}
            onChange={e => setParams(p => ({ ...p, start_date: e.target.value }))}
            style={{ ...inStyle, fontSize: 13 }}
          />
        </div>
        <div style={{ padding: "12px 14px", background: T.grayLight, borderRadius: 8 }}>
          <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 4 }}>Campaign window</div>
          {(() => {
            const sd = params.start_date ? new Date(params.start_date) : new Date()
            const ed = new Date(sd)
            ed.setDate(ed.getDate() + params.duration_weeks * 7)
            const fmt = d => d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
            return (
              <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>
                {fmt(sd)} → {fmt(ed)}
              </div>
            )
          })()}
          <div style={{ fontSize: 11, color: T.textSoft, marginTop: 4 }}>{params.duration_weeks} weeks · {totalArticles} articles total</div>
        </div>
      </Card>

      {/* ── Extra Prompt ── */}
      <Card>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8, color: T.purpleDark }}>
          ✍️ Strategy Focus (Optional)
        </div>
        <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 8 }}>
          Add specific instructions to guide the AI strategy — e.g. "Focus on seasonal content", "Emphasize product comparisons", "Target enterprise buyers"
        </div>
        <textarea
          value={params.extra_prompt}
          onChange={e => setParams(p => ({ ...p, extra_prompt: e.target.value }))}
          placeholder="Additional strategy guidance… (optional)"
          rows={3}
          style={{ ...inStyle, resize: "vertical", lineHeight: 1.5 }}
        />
      </Card>

      {/* ── Summary + Generate ── */}
      <div style={{
        background: "linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%)",
        borderRadius: 12, border: `1px solid ${T.purple}30`,
        padding: "18px 20px", display: "flex", alignItems: "center", gap: 20,
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: T.purpleDark, marginBottom: 4 }}>
            📊 {totalArticles} total articles
          </div>
          <div style={{ fontSize: 12, color: T.textSoft }}>
            {params.blogs_per_week}/week × {params.duration_weeks} weeks
            {params.publishing_cadence.length > 0 && ` · ${params.publishing_cadence.join(", ")}`}
            {" · "}{params.content_mix.informational}% info / {params.content_mix.transactional}% trans / {params.content_mix.commercial}% commercial
          </div>
          <div style={{ fontSize: 11, color: COST_EST[params.ai_provider] > 0 ? T.amber : T.teal, marginTop: 4 }}>
            AI: {PROVIDERS.find(p => p.id === params.ai_provider)?.label}
            {COST_EST[params.ai_provider] > 0 ? ` · ≈$${estCost.toFixed(3)}` : " · Free"}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-end" }}>
          <Btn
            onClick={onGenerate}
            loading={running}
            disabled={!canGenerate}
            style={{ padding: "10px 24px", fontSize: 14 }}
          >
            {running ? "Generating…" : hasStrategy ? "🔄 Regenerate Strategy" : "🚀 Generate Strategy"}
          </Btn>
          {!canGenerate && (
            <div style={{ fontSize: 10, color: T.red }}>
              {!mixOk
                ? "Content mix must total 100%"
                : params.publishing_cadence.length === 0
                  ? "Select at least one publishing day"
                  : prereqsLoaded
                    ? `Complete Research first: ${missingPrereqs.join(", ") || "missing prerequisites"}`
                    : "Checking Research prerequisites..."}
            </div>
          )}
        </div>
      </div>

      {/* ── AI Cost Hub ── */}
      <AICostHub projectId={projectId} sessionId={sessionId} />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB: GOALS
// ─────────────────────────────────────────────────────────────────────────────
function GoalsTab({ projectId, session, bizContext }) {
  const qc = useQueryClient()
  const bi = bizContext?.biz_intel || {}
  const biGoals = Array.isArray(bi.goals) ? bi.goals : []
  const biUsps  = Array.isArray(bi.usps) ? bi.usps : []
  const biSegs  = Array.isArray(bi.audience_segments) ? bi.audience_segments : []
  const biSeoStr = bi.seo_strategy || ""

  // Suggest a business_outcome from biz intel goals
  const suggestedOutcome = biGoals.length > 0 ? biGoals[0] : ""

  const [form, setForm] = useState({
    goal_type: "traffic",
    target_metric: 10,
    timeframe_months: 12,
    business_outcome: "",
    business_type: "ecommerce",
  })

  const { data: progress } = useQuery({
    queryKey: ["si-goal-progress", projectId],
    queryFn: async () => {
      const API = import.meta.env.VITE_API_URL || ""
      const t = localStorage.getItem("annaseo_token")
      const r = await fetch(`${API}/api/si/${projectId}/goals/progress`, {
        headers: t ? { Authorization: `Bearer ${t}` } : {},
      })
      if (!r.ok) return null
      return r.json()
    },
    enabled: !!projectId,
    retry: false,
  })

  const saveMut = useMutation({
    mutationFn: async (body) => {
      const API = import.meta.env.VITE_API_URL || ""
      const t = localStorage.getItem("annaseo_token")
      const r = await fetch(`${API}/api/si/${projectId}/goals`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: JSON.stringify(body),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return r.json()
    },
    onSuccess: () => qc.invalidateQueries(["si-goal-progress", projectId]),
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const inStyle = { width: "100%", padding: "8px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box" }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, alignItems: "flex-start" }}>

      {/* Left: Goal Form */}
      <Card>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark }}>Set Strategy Goals</div>
          {suggestedOutcome && (
            <button
              onClick={() => set("business_outcome", suggestedOutcome)}
              style={{ fontSize: 10, padding: "4px 10px", borderRadius: 7, border: `1px solid ${T.purple}40`,
                background: `${T.purple}10`, color: T.purple, cursor: "pointer", fontWeight: 600 }}>
              ✨ Pre-fill from BI
            </button>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Business Outcome</label>
            <input value={form.business_outcome} onChange={e => set("business_outcome", e.target.value)}
              placeholder="e.g., #1 online Kerala spices seller with 10K organic visits/month"
              style={inStyle} />
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Business Type</label>
            <select value={form.business_type} onChange={e => set("business_type", e.target.value)} style={inStyle}>
              {["ecommerce", "saas", "local", "content", "agency"].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Goal Type</label>
            <select value={form.goal_type} onChange={e => set("goal_type", e.target.value)} style={inStyle}>
              <option value="traffic">Organic Traffic Growth</option>
              <option value="leads">Lead Generation</option>
              <option value="revenue">Revenue from SEO</option>
              <option value="authority">Domain Authority</option>
            </select>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Target (%)</label>
              <input type="number" value={form.target_metric} onChange={e => set("target_metric", Number(e.target.value))} style={inStyle} />
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Timeframe (months)</label>
              <input type="number" value={form.timeframe_months} onChange={e => set("timeframe_months", Number(e.target.value))} style={inStyle} />
            </div>
          </div>
          <Btn onClick={() => saveMut.mutate(form)} loading={saveMut.isPending}>Save Goals</Btn>
          {saveMut.isError && <div style={{ fontSize: 12, color: T.red }}>{saveMut.error?.message}</div>}
          {saveMut.isSuccess && saveMut.data?.smart_goal?.smart_goal && (
            <div style={{ padding: 12, background: T.tealLight, borderRadius: 8, fontSize: 12, color: T.text, lineHeight: 1.5 }}>
              <strong style={{ color: T.teal }}>SMART Goal:</strong><br />{saveMut.data.smart_goal.smart_goal}
            </div>
          )}
        </div>
      </Card>

      {/* Progress */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {progress?.goal ? (
          <Card style={{ border: `1px solid ${T.teal}33` }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 10 }}>Current Goal</div>
            <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6, marginBottom: 10 }}>{progress.goal}</div>
            {progress.progress && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {Object.entries(progress.progress).map(([k, v]) => (
                  <div key={k} style={{ background: T.grayLight, borderRadius: 8, padding: "8px 10px" }}>
                    <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 2 }}>{k.replace(/_/g, " ")}</div>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>{typeof v === "number" ? v.toLocaleString() : String(v)}</div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        ) : (
          <Card style={{ textAlign: "center", padding: 32, background: T.grayLight }}>
            <div style={{ fontSize: 24, marginBottom: 8 }}>🎯</div>
            <div style={{ fontSize: 13, color: T.textSoft }}>No goals set yet. Use the form to define your SEO goal.</div>
          </Card>
        )}

        {/* Session keyword context for goal setting */}
        <Card style={{ border: `1px solid ${T.purple}30` }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>Session Context</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {[
              { label: "Validated Keywords", val: (session?.validated_total || 0).toLocaleString() },
              { label: "Universe Size", val: (session?.universe_total || 0).toLocaleString() },
              { label: "Mode", val: (session?.mode || "expand").toUpperCase() },
              { label: "Phase 9 Done", val: session?.phase9_done ? "Yes" : "No" },
            ].map(item => (
              <div key={item.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: T.textSoft }}>{item.label}</span>
                <span style={{ fontWeight: 600 }}>{item.val}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* AI Business Intelligence — discovered goals/USPs/strategy */}
        {(biGoals.length > 0 || biUsps.length > 0 || biSegs.length > 0 || biSeoStr) && (
          <Card style={{ border: `1px solid ${T.teal}33`, background: "linear-gradient(135deg,#f0fdf4 0%,#fafaff 100%)" }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 10 }}>🤖 From AI Business Intelligence</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {biGoals.length > 0 && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 4 }}>
                    Discovered Goals
                  </div>
                  {biGoals.map((g, i) => (
                    <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, color: T.text,
                      padding: "4px 0", borderTop: i > 0 ? `1px solid ${T.border}` : "none" }}>
                      <span style={{ flex: 1 }}>• {g}</span>
                      <button onClick={() => set("business_outcome", g)}
                        style={{ fontSize: 10, padding: "2px 8px", borderRadius: 5, border: `1px solid ${T.teal}40`,
                          background: `${T.teal}10`, color: T.teal, cursor: "pointer", fontWeight: 600, flexShrink: 0 }}>
                        Use
                      </button>
                    </div>
                  ))}
                </div>
              )}
              {biUsps.length > 0 && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 4 }}>
                    Key USPs
                  </div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {biUsps.slice(0, 5).map((u, i) => (
                      <span key={i} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99, background: T.teal + "15", color: T.teal }}>{u}</span>
                    ))}
                  </div>
                </div>
              )}
              {biSegs.length > 0 && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 4 }}>
                    Target Segments
                  </div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {biSegs.slice(0, 4).map((s, i) => (
                      <span key={i} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99, background: T.purple + "15", color: T.purple }}>{s}</span>
                    ))}
                  </div>
                </div>
              )}
              {biSeoStr && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 4 }}>
                    Prior SEO Strategy
                  </div>
                  <div style={{ fontSize: 11, color: T.textSoft, lineHeight: 1.5 }}>{biSeoStr.slice(0, 300)}</div>
                </div>
              )}
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  CONSOLE PANEL
// ─────────────────────────────────────────────────────────────────────────────
const BADGE_COLORS = {
  PHASE:   { bg: "#312e81", fg: "#c7d2fe" },
  API:     { bg: "#064e3b", fg: "#6ee7b7" },
  AI:      { bg: "#713f12", fg: "#fcd34d" },
  DATA:    { bg: "#1e3a5f", fg: "#93c5fd" },
  SUCCESS: { bg: "#14532d", fg: "#86efac" },
  ERROR:   { bg: "#7f1d1d", fg: "#fca5a5" },
  WARN:    { bg: "#78350f", fg: "#fcd34d" },
  INFO:    { bg: "#1e293b", fg: "#94a3b8" },
  TIMING:  { bg: "#0c4a6e", fg: "#7dd3fc" },
  PROGRESS:{ bg: "#0f2a4f", fg: "#89b4fa" },
  BROWSER: { bg: "#4a1c4a", fg: "#e879f9" },
  STEP:    { bg: "#1e3a1e", fg: "#86efac" },
}

function fmtTs(ts) {
  const d = new Date(ts)
  return d.toTimeString().slice(0, 8) + "." + String(d.getMilliseconds()).padStart(3, "0")
}

// ── Active AI indicator (shown in header while running) ──
function AIRunningBadge({ ai, step, progress }) {
  if (!ai) return null
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      background: "#713f12", border: "1px solid #92400e",
      borderRadius: 8, padding: "4px 12px", fontSize: 12, color: "#fcd34d",
      animation: "kw2Pulse 1.5s ease-in-out infinite",
    }}>
      <span style={{ fontSize: 16 }}>🤖</span>
      <span style={{ fontWeight: 700 }}>{ai}</span>
      {step && <span style={{ color: "#fde68a", fontSize: 11 }}>→ {step}</span>}
      {progress != null && (
        <span style={{ background: "#92400e", padding: "1px 6px", borderRadius: 4, fontSize: 11, fontWeight: 700 }}>
          {progress}%
        </span>
      )}
    </div>
  )
}

function ConsolePanel({ logs, onClear, onStop, onExit, running, height, onHeightChange }) {
  const scrollRef = useRef(null)
  const [filterBadge, setFilterBadge] = useState(null)
  const [filterType, setFilterType] = useState(null)
  const [search, setSearch] = useState("")
  const [expanded, setExpanded] = useState({}) // key=index, show detail inline

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs])

  const startDrag = (e) => {
    e.preventDefault()
    const startY = e.clientY
    const startH = height
    const onMove = (mv) => onHeightChange(Math.max(160, Math.min(800, startH + (startY - mv.clientY))))
    const onUp   = ()   => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp) }
    window.addEventListener("mousemove", onMove)
    window.addEventListener("mouseup", onUp)
  }

  const copyAll = () => {
    const text = logs.map(l => `[${fmtTs(l.ts)}] [${l.badge || "INFO"}] ${l.msg}${l.detail ? " // " + l.detail : ""}${l.progress != null ? ` (${l.progress}%)` : ""}`).join("\n")
    navigator.clipboard.writeText(text).catch(() => {})
  }

  const allBadges = [...new Set(logs.map(l => l.badge).filter(Boolean))]
  const errorCount = logs.filter(l => l.badge === "ERROR" || l.badge === "BROWSER").length
  const browserErrCount = logs.filter(l => l.badge === "BROWSER").length

  // AI summary derived from logs
  const aiLogs = logs.filter(l => l.badge === "AI" || l.ai)
  const latestAI = aiLogs.length ? aiLogs[aiLogs.length - 1] : null
  const progressLogs = logs.filter(l => l.progress != null)
  const currentProgress = running
    ? [...progressLogs].reverse().find(l => l.progress != null && l.progress < 100)
    : null
  const lastStepLog = [...logs].reverse().find(l => l.step != null)

  const filtered = logs.filter(l => {
    if (filterBadge && l.badge !== filterBadge) return false
    if (filterType === "errors" && l.badge !== "ERROR" && l.badge !== "BROWSER") return false
    if (filterType === "ai" && l.badge !== "AI" && !l.ai) return false
    if (filterType === "progress" && l.progress == null) return false
    if (search && !l.msg?.toLowerCase().includes(search.toLowerCase()) && !l.detail?.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  return (
    <div style={{ flexShrink: 0, background: "#080c16", borderTop: "2px solid #1e293b", display: "flex", flexDirection: "column", height }}>
      {/* Drag handle */}
      <div
        onMouseDown={startDrag}
        style={{ height: 6, cursor: "ns-resize", background: "#0d1117", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}
      >
        <div style={{ width: 50, height: 2, borderRadius: 1, background: "#1e293b" }} />
      </div>

      {/* ── Header bar ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 12px", borderBottom: "1px solid #0f172a", flexShrink: 0, flexWrap: "wrap", minHeight: 34 }}>
        {/* Title + counts */}
        <span style={{ fontSize: 10, fontWeight: 800, color: "#334155", letterSpacing: "0.12em", fontFamily: "monospace" }}>▶_ CONSOLE</span>
        <span style={{ fontSize: 10, color: "#1e3a5f", background: "#0d1117", padding: "0 6px", borderRadius: 3, fontWeight: 600 }}>{filtered.length}/{logs.length}</span>
        {errorCount > 0 && <span style={{ fontSize: 10, background: "#7f1d1d", color: "#fca5a5", padding: "0 6px", borderRadius: 3, fontWeight: 700 }}>⚠ {errorCount} err</span>}
        {browserErrCount > 0 && <span style={{ fontSize: 10, background: "#4a1c4a", color: "#e879f9", padding: "0 6px", borderRadius: 3, fontWeight: 700 }}>🌐 {browserErrCount} browser</span>}

        {/* Active AI indicator in header */}
        {running && latestAI && (
          <span style={{ fontSize: 10, background: "#3a2c00", color: "#fcd34d", padding: "1px 8px", borderRadius: 3, fontWeight: 700, animation: "kw2Pulse 1.5s infinite" }}>
            🤖 {latestAI.ai || latestAI.msg?.replace("AI provider: ", "") || "AI"}
          </span>
        )}
        {running && lastStepLog && (
          <span style={{ fontSize: 10, background: "#0f2a4f", color: "#89b4fa", padding: "1px 8px", borderRadius: 3, fontWeight: 700 }}>
            Step {lastStepLog.step}/{lastStepLog.total}
            {currentProgress && ` — ${currentProgress.progress}%`}
          </span>
        )}

        {/* Filter chips */}
        <div style={{ display: "flex", gap: 4, marginLeft: 2 }}>
          {["errors", "ai", "progress"].map(ft => (
            <button key={ft} onClick={() => setFilterType(filterType === ft ? null : ft)} style={{
              fontSize: 9, padding: "1px 7px", borderRadius: 3, border: "none", cursor: "pointer",
              background: filterType === ft ? "#1e40af" : "#111827",
              color: filterType === ft ? "#93c5fd" : "#475569", fontWeight: 700,
            }}>
              {ft === "errors" ? "⚠ ERRORS" : ft === "ai" ? "🤖 AI" : "📊 STEPS"}
            </button>
          ))}
          {allBadges.length > 2 && (
            <select value={filterBadge || ""} onChange={e => setFilterBadge(e.target.value || null)}
              style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, border: "none", background: "#111827", color: "#475569" }}>
              <option value="">ALL</option>
              {allBadges.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
          )}
        </div>

        <div style={{ flex: 1 }} />

        {/* Search */}
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="search…"
          style={{ fontSize: 10, padding: "2px 7px", borderRadius: 4, border: "none", background: "#0d1117", color: "#94a3b8", width: 90, outline: "none" }} />

        {/* Action buttons */}
        {logs.length > 0 && (
          <button onClick={copyAll} title="Copy all to clipboard"
            style={{ border: "none", background: "#0d1117", color: "#475569", fontSize: 10, padding: "2px 8px", borderRadius: 4, cursor: "pointer" }}>
            📋
          </button>
        )}
        {logs.length > 0 && (
          <button onClick={onClear} title="Clear console"
            style={{ border: "none", background: "#0d1117", color: "#475569", fontSize: 10, padding: "2px 8px", borderRadius: 4, cursor: "pointer" }}>
            🗑 Clear
          </button>
        )}
        {running && onStop && (
          <button onClick={onStop} title="Stop generation"
            style={{ border: "none", background: "#7f1d1d", color: "#fca5a5", fontSize: 10, fontWeight: 800, padding: "3px 10px", borderRadius: 4, cursor: "pointer", animation: "kw2Pulse 1.5s infinite" }}>
            ⏹ Stop
          </button>
        )}
        {onExit && (
          <button onClick={onExit} title="Close console"
            style={{ border: "none", background: "#0d1117", color: "#475569", fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 4, cursor: "pointer" }}>
            ✕
          </button>
        )}
      </div>

      {/* ── Active progress bar ── */}
      {running && currentProgress && (
        <div style={{ flexShrink: 0, padding: "4px 12px 5px", background: "#0a1628", borderBottom: "1px solid #0f172a" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
            <span style={{ fontSize: 10, color: "#89b4fa", fontWeight: 700, fontFamily: "monospace", minWidth: 34 }}>{currentProgress.progress}%</span>
            <span style={{ fontSize: 11, color: "#94a3b8", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{currentProgress.msg}</span>
            {currentProgress.step != null && (
              <span style={{ fontSize: 10, color: "#475569", flexShrink: 0 }}>
                Step {currentProgress.step}/{currentProgress.total}
              </span>
            )}
            {currentProgress.ai && (
              <span style={{ fontSize: 10, background: "#3a2c00", color: "#fcd34d", padding: "0 5px", borderRadius: 3, flexShrink: 0 }}>🤖 {currentProgress.ai}</span>
            )}
          </div>
          <div style={{ height: 5, background: "#111827", borderRadius: 3, overflow: "hidden" }}>
            <div style={{
              width: `${currentProgress.progress}%`, height: "100%",
              background: currentProgress.progress === 100
                ? "#22c55e"
                : `linear-gradient(90deg, #3b82f6 0%, #8b5cf6 ${currentProgress.progress}%, #89b4fa 100%)`,
              borderRadius: 3, transition: "width 0.5s ease",
            }} />
          </div>
        </div>
      )}

      {/* ── Log entries ── */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "4px 0", fontFamily: '"JetBrains Mono","Fira Mono",Consolas,monospace', fontSize: 11, lineHeight: 1.75 }}>
        {filtered.length === 0 ? (
          <div style={{ color: "#1e293b", padding: "16px 14px", textAlign: "center", fontSize: 12 }}>
            {logs.length === 0 ? "No events yet — generate a strategy to see live output." : "No entries match filter."}
          </div>
        ) : filtered.map((l, i) => {
          const bc = BADGE_COLORS[l.badge] || BADGE_COLORS.INFO
          const isErr  = l.badge === "ERROR" || l.badge === "BROWSER"
          const isSuc  = l.badge === "SUCCESS"
          const isPh   = l.badge === "PHASE"
          const isProg = l.progress != null
          const rowBg  = isErr ? "rgba(127,29,29,0.18)" : isSuc ? "rgba(20,83,45,0.1)" : isPh ? "rgba(49,46,129,0.15)" : isProg ? "rgba(15,42,79,0.12)" : i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.012)"
          const textCol = isErr ? "#fca5a5" : isSuc ? "#86efac" : l.badge === "WARN" ? "#fcd34d" : l.badge === "AI" ? "#fde68a" : l.badge === "TIMING" ? "#7dd3fc" : isPh ? "#c7d2fe" : isProg ? "#89b4fa" : l.badge === "BROWSER" ? "#e879f9" : "#cbd5e1"
          const isExpanded = !!expanded[i]

          return (
            <div key={i} style={{ background: rowBg }}>
              {/* Main row */}
              <div
                style={{ display: "flex", alignItems: "baseline", gap: 7, padding: "1px 14px", cursor: l.detail ? "pointer" : "default" }}
                onClick={() => l.detail && setExpanded(ex => ({ ...ex, [i]: !ex[i] }))}
              >
                {/* Timestamp */}
                <span style={{ color: "#1e3a5f", flexShrink: 0, fontSize: 9.5, userSelect: "none", fontVariantNumeric: "tabular-nums" }}>{fmtTs(l.ts)}</span>
                {/* Badge */}
                <span style={{ flexShrink: 0, fontSize: 9, fontWeight: 800, padding: "1px 6px", borderRadius: 3, background: bc.bg, color: bc.fg, letterSpacing: "0.05em", minWidth: 52, textAlign: "center" }}>
                  {l.badge || "INFO"}
                </span>
                {/* AI provider tag */}
                {l.ai && (
                  <span style={{ flexShrink: 0, fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 3, background: "#3a2c00", color: "#fcd34d" }}>
                    🤖 {l.ai}
                  </span>
                )}
                {/* Step counter */}
                {l.step != null && l.total != null && (
                  <span style={{ flexShrink: 0, fontSize: 9, color: "#475569", fontWeight: 700 }}>[{l.step}/{l.total}]</span>
                )}
                {/* Message */}
                <span style={{ color: textCol, flex: 1, wordBreak: "break-all" }}>{l.msg}</span>
                {/* Progress % */}
                {l.progress != null && (
                  <span style={{ flexShrink: 0, fontSize: 10, fontWeight: 800, color: l.progress === 100 ? "#22c55e" : "#89b4fa", minWidth: 36, textAlign: "right", fontFamily: "monospace" }}>
                    {l.progress}%
                  </span>
                )}
                {/* Inline detail toggle indicator */}
                {l.detail && !l.progress && (
                  <span style={{ color: "#334155", fontSize: 9, flexShrink: 0 }}>{isExpanded ? "▼" : "▶"}</span>
                )}
              </div>

              {/* Inline progress bar */}
              {isProg && (
                <div style={{ padding: "0 14px 4px 78px" }}>
                  <div style={{ height: 3, background: "#111827", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{
                      width: `${l.progress}%`, height: "100%",
                      background: l.progress === 100 ? "#22c55e" : "linear-gradient(90deg,#3b82f6,#8b5cf6)",
                      borderRadius: 2, transition: "width 0.5s ease",
                    }} />
                  </div>
                </div>
              )}

              {/* Expandable detail line */}
              {isProg && l.detail && (
                <div style={{ padding: "0 14px 3px 78px", fontSize: 9.5, color: "#334155" }}>// {l.detail}</div>
              )}
              {!isProg && l.detail && isExpanded && (
                <div style={{ padding: "0 14px 4px 78px", fontSize: 10, color: "#475569", borderLeft: "2px solid #1e293b", marginLeft: 14, wordBreak: "break-word" }}>
                  {l.detail}
                </div>
              )}
              {!isProg && l.detail && !isExpanded && (
                <div style={{ padding: "0 14px 1px 78px", fontSize: 9, color: "#1e3a5f", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  // {l.detail.slice(0, 120)}{l.detail.length > 120 ? "…" : ""}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
// ─────────────────────────────────────────────────────────────────────────────
//  INTELLIGENCE TAB  (Q1-Q7 modules, dedup, scoring, selection)
// ─────────────────────────────────────────────────────────────────────────────
function IntelligenceTab({ projectId, sessionId, chooseAI }) {
  const qc = useQueryClient()
  const [busy, setBusy] = useState({})
  const [actionError, setActionError] = useState("")
  const [actionNotice, setActionNotice] = useState("")
  const [lastFailedStage, setLastFailedStage] = useState(null) // for retry affordance
  const [scoringWeights, setScoringWeights] = useState(null)
  const [showWeights, setShowWeights] = useState(false)
  const [selectedIntent, setSelectedIntent] = useState(null)
  const [activeSection, setActiveSection] = useState("questions")
  const [qSearch, setQSearch] = useState("")
  const [qFilterIntent, setQFilterIntent] = useState("")
  const [expandedCluster, setExpandedCluster] = useState(null)
  const [expandMax, setExpandMax] = useState(300)
  const [showExpandConfig, setShowExpandConfig] = useState(false)
  const [pePerRound, setPePerRound] = useState(5)
  const [peMax, setPeMax] = useState(200)

  // ── Pillar round-robin expansion state ──────────────────────────────────
  const _peKey = `annaseo_pillar_exp_${sessionId}`
  const [pillarExp, setPillarExp] = useState(() => {
    try { const s = localStorage.getItem(_peKey); return s ? JSON.parse(s) : null } catch { return null }
  })
  const pillarRunningRef = useRef(false)

  const _savePillarExp = (state) => {
    try { localStorage.setItem(_peKey, JSON.stringify(state)) } catch {}
    setPillarExp(state)
  }

  const startPillarExp = async (pillars, perRound, maxTotal) => {
    const init = {
      status: "running", pillars, perRound, maxTotal,
      totalGenerated: 0, currentPillarIdx: 0, currentRound: 1,
      pillarCounts: Object.fromEntries(pillars.map(p => [p, 0])),
    }
    _savePillarExp(init)
    runPillarLoop(init)
  }

  const pausePillarExp = () => {
    pillarRunningRef.current = false
    // status will be set to "paused" inside the loop when it detects the flag
  }

  const stopPillarExp = () => {
    pillarRunningRef.current = false
    _savePillarExp(null)
  }

  const resumePillarExp = () => {
    if (!pillarExp) return
    const resumed = { ...pillarExp, status: "running" }
    _savePillarExp(resumed)
    runPillarLoop(resumed)
  }

  const runPillarLoop = async (initState) => {
    pillarRunningRef.current = true
    let s = { ...initState, status: "running" }
    _savePillarExp(s)

    while (s.totalGenerated < s.maxTotal && pillarRunningRef.current) {
      const pillar = s.pillars[s.currentPillarIdx]
      try {
        const res = await api.generateForPillar(projectId, sessionId, {
          pillar, count: s.perRound, ai_provider: "auto",
        })
        const added = res.questions_created || 0
        const nextIdx = (s.currentPillarIdx + 1) % s.pillars.length
        const nextRound = nextIdx === 0 ? s.currentRound + 1 : s.currentRound
        s = {
          ...s,
          totalGenerated: s.totalGenerated + added,
          currentPillarIdx: nextIdx,
          currentRound: nextRound,
          pillarCounts: { ...s.pillarCounts, [pillar]: (s.pillarCounts[pillar] || 0) + added },
        }
        if (s.totalGenerated >= s.maxTotal) { s = { ...s, status: "done" }; break }
        if (!pillarRunningRef.current) { s = { ...s, status: "paused" }; break }
        _savePillarExp(s)
      } catch (e) {
        s = { ...s, status: "paused", lastError: e.message || String(e) }
        break
      }
    }
    if (s.status === "running") s = { ...s, status: "done" }
    _savePillarExp(s)
    pillarRunningRef.current = false
    await refreshIntelligenceViews({
      includeClusters: false,
      includeRanked: false,
      includeSelected: false,
    })
  }

  // ── Dimension expansion state (per-seed progress) ──────────────────────
  const _deKey = `annaseo_dim_exp_${sessionId}`
  const [dimExp, setDimExp] = useState(() => {
    try { const s = localStorage.getItem(_deKey); return s ? JSON.parse(s) : null } catch { return null }
  })
  const dimRunningRef = useRef(false)

  const _saveDimExp = (state) => {
    try {
      if (state) localStorage.setItem(_deKey, JSON.stringify(state))
      else localStorage.removeItem(_deKey)
    } catch {}
    setDimExp(state)
  }

  const startDimExp = async (maxPerNode, maxTotal) => {
    let seeds
    try { const r = await api.getExpansionSeeds(projectId, sessionId); seeds = r.seeds || [] } catch { seeds = [] }
    if (!seeds.length) { setActionError("No seed questions found. Generate questions first."); return }
    const init = {
      status: "running", seeds, currentIdx: 0, totalCreated: 0,
      maxTotal, maxPerNode,
    }
    _saveDimExp(init)
    runDimLoop(init)
  }

  const pauseDimExp = () => { dimRunningRef.current = false }
  const stopDimExp  = () => { dimRunningRef.current = false; _saveDimExp(null) }
  const resumeDimExp = () => {
    if (!dimExp) return
    const resumed = { ...dimExp, status: "running", lastError: undefined }
    _saveDimExp(resumed)
    runDimLoop(resumed)
  }

  const runDimLoop = async (initState) => {
    dimRunningRef.current = true
    let s = { ...initState, status: "running" }
    _saveDimExp(s)

    while (s.currentIdx < s.seeds.length && s.totalCreated < s.maxTotal && dimRunningRef.current) {
      const seed = s.seeds[s.currentIdx]
      try {
        const res = await api.expandOneSeed(projectId, sessionId, {
          seed_id: seed.id,
          max_per_node: s.maxPerNode,
          max_total_remaining: s.maxTotal - s.totalCreated,
          ai_provider: "auto",
        })
        const added = res.questions_created || 0
        s = { ...s, currentIdx: s.currentIdx + 1, totalCreated: s.totalCreated + added }
        if (!dimRunningRef.current) { s = { ...s, status: "paused" }; break }
        _saveDimExp(s)
      } catch (e) {
        s = { ...s, status: "paused", lastError: e.message || String(e) }
        break
      }
    }
    if (s.status === "running") s = { ...s, status: "done" }
    _saveDimExp(s)
    dimRunningRef.current = false
    await refreshIntelligenceViews({
      includeClusters: false,
      includeSelected: false,
    })
  }
  // ────────────────────────────────────────────────────────────────────────

  const setSectionBusy = (key, val) => setBusy(prev => ({ ...prev, [key]: val }))
  const clearActionState = () => { setActionError(""); setActionNotice(""); setLastFailedStage(null) }
  const getErrorMessage = (error) => error?.message || String(error || "Unknown error")
  const isAnyBusy = Object.entries(busy).some(([key, val]) => key !== "_progress" && val === true)
  const hasLoopActivity = pillarExp?.status === "running" || dimExp?.status === "running"
  const shouldPollProgress = isAnyBusy || hasLoopActivity
  const formatStageResult = (key, result) => {
    if (!result || typeof result !== "object") return ""
    if (key === "questions" && typeof result.total === "number") {
      return `Generated ${result.total} questions across ${(result.modules_run || []).length || 0} modules.`
    }
    if (key === "enrich" && typeof result.enriched === "number") {
      return `Enriched ${result.enriched} questions.`
    }
    if (key === "discover" && result.dimensions) {
      const dims = Object.keys(result.dimensions || {})
      return `Discovered ${dims.length} dimensions${result.brand_name ? ` including brand: ${result.brand_name}` : ""}.`
    }
    if (key === "expand" && typeof result.questions_created === "number") {
      const rejected = result.rejected || 0
      return rejected > 0
        ? `Generated ${result.questions_created + rejected} → validated → ${result.questions_created} kept, ${rejected} rejected.`
        : `Expanded ${result.questions_created} new questions.`
    }
    if (key === "dedup" && typeof result.duplicates_removed === "number") {
      return `Removed ${result.duplicates_removed} duplicates — ${result.unique_count || 0} unique remaining.`
    }
    if (key === "cluster" && typeof result.clusters_created === "number") {
      return `Created ${result.clusters_created} clusters for ${result.questions_clustered || 0} questions.`
    }
    if (key === "score" && typeof result.scored === "number") {
      return `Scored ${result.scored} questions.`
    }
    if (key === "select" && typeof result.selected === "number") {
      return `Selected ${result.selected} questions.`
    }
    return ""
  }
  const runStage = async (key, fn) => {
    if (isAnyBusy) return null
    clearActionState()
    setSectionBusy(key, true)
    try {
      const result = await fn()
      const message = formatStageResult(key, result)
      if (message) setActionNotice(message)
      return result
    } catch (error) {
      setActionError(getErrorMessage(error))
      setLastFailedStage(key)
      return null
    } finally {
      setSectionBusy(key, false)
      setBusy(prev => ({ ...prev, _progress: null }))
      // Refresh pipeline status after every stage
      qc.invalidateQueries(["intpipeline", projectId, sessionId])
    }
  }

  const { data: questionsData, refetch: refetchQ } = useQuery({
    queryKey: ["intq", projectId, sessionId],
    queryFn: () => api.listQuestions(projectId, sessionId, { limit: 500 }),
    enabled: !!sessionId, staleTime: 30_000,
  })
  const { data: qSummary, refetch: refetchSummary } = useQuery({
    queryKey: ["intq-sum", projectId, sessionId],
    queryFn: () => api.getQuestionSummary(projectId, sessionId),
    enabled: !!sessionId,
    staleTime: shouldPollProgress ? 0 : 30_000,
    refetchInterval: shouldPollProgress ? 3_000 : false,
  })
  const { data: clustersData, refetch: refetchClusters } = useQuery({
    queryKey: ["intc", projectId, sessionId],
    queryFn: () => api.listClusters(projectId, sessionId),
    enabled: !!sessionId, staleTime: 30_000,
  })
  const { data: rankedData, refetch: refetchRanked } = useQuery({
    queryKey: ["intr", projectId, sessionId, selectedIntent],
    queryFn: () => api.getRankedQuestions(projectId, sessionId, selectedIntent ? { intent: selectedIntent } : {}),
    enabled: !!sessionId, staleTime: 30_000,
  })
  const { data: scoringConfig, refetch: refetchConfig } = useQuery({
    queryKey: ["intsc", projectId, sessionId],
    queryFn: () => api.getScoringConfig(projectId, sessionId),
    enabled: !!sessionId, staleTime: 60_000,
  })
  const { data: selectedData, refetch: refetchSelected } = useQuery({
    queryKey: ["intsel", projectId, sessionId],
    queryFn: () => api.listSelected(projectId, sessionId),
    enabled: !!sessionId, staleTime: 30_000,
  })

  const { data: expansionConfig, refetch: refetchExpansionConfig } = useQuery({
    queryKey: ["expconfig", projectId, sessionId],
    queryFn: () => api.getExpansionConfig(projectId, sessionId),
    enabled: !!sessionId, staleTime: 60_000,
  })

  // Pipeline status — single endpoint for prerequisite gating
  const { data: pipelineStatus, refetch: refetchPipeline } = useQuery({
    queryKey: ["intpipeline", projectId, sessionId],
    queryFn: () => api.getPipelineStatus(projectId, sessionId),
    enabled: !!sessionId, staleTime: 15_000,
    refetchInterval: shouldPollProgress ? 5_000 : false,
  })
  // Shorthand stage status from server (fallback to "ready" if endpoint hasn't loaded)
  const stageStatus = pipelineStatus?.stages || {}
  const isBlocked = (stage) => stageStatus[stage] === "blocked"
  const isDone    = (stage) => stageStatus[stage] === "done"

  const refreshIntelligenceViews = async ({
    includeQuestions = true,
    includeSummary = true,
    includeClusters = true,
    includeRanked = true,
    includeSelected = true,
    includePipeline = true,
    includeExpansionConfig = false,
  } = {}) => {
    const tasks = []
    if (includeQuestions) tasks.push(refetchQ())
    if (includeSummary) tasks.push(refetchSummary())
    if (includeClusters) tasks.push(refetchClusters())
    if (includeRanked) tasks.push(refetchRanked())
    if (includeSelected) tasks.push(refetchSelected())
    if (includePipeline) tasks.push(refetchPipeline())
    if (includeExpansionConfig) tasks.push(refetchExpansionConfig())
    if (tasks.length) await Promise.all(tasks)
  }

  const handleRunQuestions = async (aiOverride) => {
    const picked = aiOverride || (chooseAI ? await chooseAI("Generate research questions (Q1–Q7 modules)") : "auto")
    if (!picked) return
    await runStage("questions", async () => {
      setBusy(prev => ({ ...prev, _progress: 5 }))
      const result = await api.runQuestions(projectId, sessionId, { modules: ["Q1","Q2","Q3","Q4","Q5","Q6","Q7"], ai_provider: picked })
      setBusy(prev => ({ ...prev, _progress: 100 }))
      await refreshIntelligenceViews()
      return result
    })
  }

  const handleEnrich = async (aiOverride) => {
    const picked = aiOverride || (chooseAI ? await chooseAI("Enrich questions with intent, funnel stage, and audience tags") : "auto")
    if (!picked) return
    await runStage("enrich", async () => {
      const result = await api.enrichQuestions(projectId, sessionId, { ai_provider: picked })
      await refreshIntelligenceViews({ includeClusters: false })
      return result
    })
  }

  const handleDiscoverDimensions = async (aiOverride) => {
    const picked = aiOverride || (chooseAI ? await chooseAI("Discover audience, geo, and brand dimensions via AI") : "auto")
    if (!picked) return
    await runStage("discover", async () => {
      const result = await api.discoverDimensions(projectId, sessionId, { ai_provider: picked })
      await refreshIntelligenceViews({
        includeQuestions: false,
        includeSummary: false,
        includeClusters: false,
        includeRanked: false,
        includeSelected: false,
        includeExpansionConfig: true,
      })
      return result
    })
  }

  const handleExpand = async () => {
    setShowExpandConfig(false)
    await runStage("expand", async () => {
      const result = await api.runExpansion(projectId, sessionId, { max_depth: 1, max_per_node: 3, max_total: expandMax })
      await refreshIntelligenceViews({ includeClusters: false })
      return result
    })
  }

  const handleDedup = async () => {
    await runStage("dedup", async () => {
      const result = await api.runDedup(projectId, sessionId)
      await refreshIntelligenceViews()
      return result
    })
  }

  const handleCluster = async () => {
    await runStage("cluster", async () => {
      const result = await api.runClustering(projectId, sessionId)
      await refreshIntelligenceViews()
      return result
    })
  }

  const handleScore = async () => {
    await runStage("score", async () => {
      const result = await api.runScoring(projectId, sessionId)
      await refreshIntelligenceViews()
      return result
    })
  }

  const handleSelect = async () => {
    await runStage("select", async () => {
      const result = await api.runSelection(projectId, sessionId, { n: 100, max_per_cluster: 10 })
      await refreshIntelligenceViews({
        includeQuestions: false,
        includeSummary: false,
        includeClusters: false,
        includeRanked: false,
      })
      return result
    })
  }

  const handleSaveWeights = async () => {
    if (!scoringWeights) return
    const weightSum = Object.values(scoringWeights).reduce((sum, value) => sum + (Number(value) || 0), 0)
    if (Math.abs(weightSum - 1) > 0.001) {
      setActionError(`Scoring weights must sum to 1.0. Current total: ${weightSum.toFixed(2)}`)
      return
    }
    await runStage("weights", async () => {
      const result = await api.updateScoringConfig(projectId, sessionId, scoringWeights)
      await refetchConfig()
      setShowWeights(false)
      setActionNotice("Saved scoring weights.")
      return result
    })
  }

  const handleDeleteQuestion = async (questionId) => {
    if (!window.confirm("Delete this question from the session?")) return
    clearActionState()
    try {
      await api.deleteQuestion(projectId, sessionId, questionId)
      await refreshIntelligenceViews()
      setActionNotice("Question deleted.")
    } catch (error) {
      setActionError(getErrorMessage(error))
    }
  }

  const handleRemoveSelected = async (questionId) => {
    if (!window.confirm("Remove this question from the selected set?")) return
    clearActionState()
    try {
      await api.removeSelected(projectId, sessionId, questionId)
      await refreshIntelligenceViews({
        includeQuestions: false,
        includeSummary: false,
        includeClusters: false,
        includeRanked: false,
      })
      setActionNotice("Question removed from selection.")
    } catch (error) {
      setActionError(getErrorMessage(error))
    }
  }

  // ── Run-All pipeline ─────────────────────────────────────────────────────
  const [runAllStatus, setRunAllStatus] = useState(null) // null | "running" | "done" | "error"
  const [runAllStage, setRunAllStage] = useState("")     // current stage label
  const runAllRef = useRef(false)

  const handleRunAll = async () => {
    if (isAnyBusy || runAllStatus === "running") return

    // Ask user which AI provider to use for all stages
    const picked = chooseAI ? await chooseAI("Run full research pipeline — choose AI provider") : "auto"
    if (!picked) return   // user cancelled

    runAllRef.current = true
    setRunAllStatus("running")
    setRunAllStage("Starting…")
    clearActionState()

    const STAGES = [
      { key: "questions", label: "Step 2: Generate Questions (Q1–Q7)", fn: (ai) => handleRunQuestions(ai) },
      { key: "enrich",    label: "Step 2: Enrich Questions",           fn: (ai) => handleEnrich(ai) },
      { key: "discover",  label: "Step 3: Discover Dimensions",        fn: (ai) => handleDiscoverDimensions(ai) },
      { key: "dedup",     label: "Step 4: Deduplicate",                fn: () => handleDedup() },
      { key: "cluster",   label: "Step 4: Cluster into Topics",        fn: () => handleCluster() },
      { key: "score",     label: "Step 4: Score Questions",            fn: () => handleScore() },
      { key: "select",    label: "Step 4: Auto-Select Top Keywords",   fn: () => handleSelect() },
    ]

    try {
      for (const stage of STAGES) {
        if (!runAllRef.current) break
        setRunAllStage(stage.label)
        await stage.fn(picked)
        // stop the chain if runStage set an error
        if (actionError) break
      }
      setRunAllStatus("done")
      setRunAllStage("All stages complete ✓")
    } catch (e) {
      setRunAllStatus("error")
      setRunAllStage(`Failed: ${e?.message || String(e)}`)
    } finally {
      runAllRef.current = false
    }
  }

  const handleStopAll = () => {
    runAllRef.current = false
    pausePillarExp()
    pauseDimExp()
  }

  const questions = questionsData?.questions || []
  const clusters = clustersData?.clusters || []
  const ranked = rankedData?.questions || []
  const selected = selectedData?.selected || []
  const hasDimensions = expansionConfig?.discovered_dimensions && Object.keys(expansionConfig.discovered_dimensions || {}).length > 0
  const totalCount = pipelineStatus?.questions?.count ?? qSummary?.total ?? questions.length
  const enrichedCount = pipelineStatus?.questions?.enriched ?? qSummary?.enriched ?? questions.filter(q => q.intent).length
  const unenrichedCount = pipelineStatus?.questions?.unenriched ?? Math.max(totalCount - enrichedCount, 0)
  const uniqueCount = pipelineStatus?.dedup?.unique ?? questions.filter(q => !q.is_duplicate).length
  const scoredCount = pipelineStatus?.scoring?.scored ?? questions.filter(q => q.final_score > 0).length
  const expandedCount = pipelineStatus?.expansion?.expanded ?? questions.filter(q => (q.expansion_depth || 0) > 0).length
  const clusterCount = pipelineStatus?.clusters?.count ?? clusters.length
  const selectedCount = pipelineStatus?.selection?.count ?? selected.length
  const enrichProgress = busy.enrich ? { done: enrichedCount, total: totalCount } : null
  const dimCount = Object.keys(expansionConfig?.discovered_dimensions || {}).length
  const clusterNameById = Object.fromEntries(clusters.map(c => [c.id, c.name]))
  const renderDimensionBadge = (q) => {
    if (!q?.expansion_dimension_name || !q?.expansion_dimension_value) return null
    const isBrand = q.expansion_dimension_name === "brand_name"
    return (
      <span style={{ fontSize: 10, background: isBrand ? "#e0e7ff" : "#ede9fe", color: isBrand ? "#3730a3" : "#5b21b6", padding: "1px 6px", borderRadius: 4, fontWeight: 600 }}>
        {q.expansion_dimension_name}: {q.expansion_dimension_value}
      </span>
    )
  }

  // Intent color helper
  const intentColor = (intent) => {
    if (intent === "commercial")    return { bg: "#ede9fe", fg: "#5b21b6" }
    if (intent === "transactional") return { bg: "#fef3c7", fg: "#92400e" }
    if (intent === "informational") return { bg: "#dbeafe", fg: "#1e40af" }
    if (intent === "navigational")  return { bg: "#dcfce7", fg: "#166534" }
    return { bg: "#f1f5f9", fg: "#475569" }
  }
  const funnelColor = (stage) => {
    if (stage === "TOFU") return { bg: "#f0fdf4", fg: "#15803d" }
    if (stage === "MOFU") return { bg: "#fef9c3", fg: "#854d0e" }
    if (stage === "BOFU") return { bg: "#fee2e2", fg: "#991b1b" }
    return { bg: "#f1f5f9", fg: "#475569" }
  }
  const pillarColor = (pillar) => {
    const map = { Business: "#dbeafe", Customer: "#ede9fe", Marketing: "#fce7f3", Product: "#dcfce7", Operations: "#fef3c7" }
    const fgMap = { Business: "#1e40af", Customer: "#5b21b6", Marketing: "#9d174d", Product: "#166534", Operations: "#78350f" }
    return { bg: map[pillar] || "#f1f5f9", fg: fgMap[pillar] || "#475569" }
  }

  // Filtered questions for Questions tab
  const filteredQuestions = useMemo(() => questions.filter(q => {
    if (qSearch && !q.question_text?.toLowerCase().includes(qSearch.toLowerCase())) return false
    if (qFilterIntent && q.intent !== qFilterIntent) return false
    return true
  }), [questions, qSearch, qFilterIntent])

  const btnStyle = (c = T.purple) => ({
    padding: "7px 14px", borderRadius: 7, border: "none", cursor: "pointer",
    background: c, color: "#fff", fontSize: 12, fontWeight: 700,
    display: "flex", alignItems: "center", gap: 5,
  })
  const secBtn = (id) => ({
    padding: "5px 14px", borderRadius: 20, border: `1px solid ${activeSection === id ? T.purple : T.border}`,
    background: activeSection === id ? T.purple : "transparent",
    color: activeSection === id ? "#fff" : T.textSoft,
    cursor: "pointer", fontSize: 12, fontWeight: activeSection === id ? 700 : 400,
    transition: "all 0.15s",
  })

  // Active operation info
  const activeOp = Object.entries(busy).find(([k, v]) => k !== "_progress" && v === true)
  const opMeta = {
    questions: { label: "Generating questions across 7 modules (Q1–Q7)", what: "Creates real search queries your audience is asking" },
    enrich:    { label: enrichProgress ? `Enriching ${enrichProgress.done}/${enrichProgress.total} questions` : "Enriching questions…", what: "Adds intent (commercial/informational), funnel stage (TOFU/MOFU/BOFU), audience tags" },
    discover:  { label: "Discovering dimensions via AI…", what: "Finds geo, audience, use-case angles specific to your business" },
    expand:    { label: `Expanding to ${expandMax} questions max…`, what: `Multiplies seed questions across ${dimCount} dimensions (depth 1, max 3 per node)` },
    dedup:     { label: "Running deduplication…", what: "Removes near-duplicate questions using string similarity" },
    cluster:   { label: "Clustering into topics…", what: "Groups questions into content pillars (AI-powered)" },
    score:     { label: "Scoring all questions…", what: "Ranks by 5 weighted signals: intent, funnel, audience, novelty, business fit" },
    select:    { label: "Auto-selecting top questions…", what: "Picks best 100 with cluster diversity" },
  }

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>

      {actionError && (
        <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 10, padding: "10px 14px", color: "#991b1b", fontSize: 13, marginBottom: 16, display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ flex: 1 }}>{actionError}</span>
          {lastFailedStage && (
            <button
              onClick={() => {
                // Retry map — each stage key maps to its handler
                const retryMap = {
                  questions: handleRunQuestions,
                  enrich:    handleEnrich,
                  discover:  handleDiscoverDimensions,
                  expand:    handleExpand,
                  dedup:     handleDedup,
                  cluster:   handleCluster,
                  score:     handleScore,
                  select:    handleSelect,
                  weights:   handleSaveWeights,
                }
                const fn = retryMap[lastFailedStage]
                if (fn) fn()
              }}
              style={{ flexShrink: 0, padding: "4px 12px", borderRadius: 6, border: "1px solid #fca5a5", background: "#fff", color: "#991b1b", cursor: "pointer", fontSize: 12, fontWeight: 700 }}
            >
              ↺ Retry
            </button>
          )}
          <button onClick={clearActionState} style={{ flexShrink: 0, background: "none", border: "none", cursor: "pointer", color: "#991b1b", fontSize: 16, lineHeight: 1 }}>✕</button>
        </div>
      )}

      {actionNotice && !activeOp && (
        <div style={{ background: "#ecfeff", border: "1px solid #a5f3fc", borderRadius: 10, padding: "10px 14px", color: "#155e75", fontSize: 13, marginBottom: 16 }}>
          {actionNotice}
        </div>
      )}

      {/* ── Stats bar ── */}
      {totalCount > 0 && (
        <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
          {[
            { label: "Total", val: totalCount, color: "#6366f1" },
            { label: "Enriched", val: enrichedCount, color: T.teal, sub: `${totalCount > 0 ? Math.round(enrichedCount / totalCount * 100) : 0}%` },
            { label: "Unique", val: uniqueCount, color: "#0ea5e9" },
            { label: "Expanded", val: expandedCount, color: "#7c3aed" },
            { label: "Scored", val: scoredCount, color: "#f59e0b" },
            { label: "Clusters", val: clusterCount, color: "#f43f5e" },
            { label: "Selected", val: selectedCount, color: "#10b981" },
          ].map(({ label, val, color, sub }) => (
            <div key={label} style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: "10px 16px", textAlign: "center", minWidth: 80 }}>
              <div style={{ fontSize: 22, fontWeight: 800, color }}>{val}</div>
              <div style={{ fontSize: 10, color: T.textSoft }}>{label}</div>
              {sub && <div style={{ fontSize: 10, color, fontWeight: 600 }}>{sub}</div>}
            </div>
          ))}
        </div>
      )}

      {/* ── Run Full Pipeline card ── */}
      <div style={{
        background: runAllStatus === "running" ? "#f5f3ff" : runAllStatus === "done" ? "#f0fdf4" : runAllStatus === "error" ? "#fef2f2" : "#fff",
        border: `1.5px solid ${runAllStatus === "running" ? "#7c3aed" : runAllStatus === "done" ? T.teal : runAllStatus === "error" ? T.red : T.border}`,
        borderRadius: 12, padding: "14px 18px", marginBottom: 16,
        display: "flex", alignItems: "center", flexWrap: "wrap", gap: 12,
      }}>
        <div style={{ flex: 1, minWidth: 180 }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: T.text, marginBottom: 2 }}>
            ▶ Run Full Pipeline
          </div>
          <div style={{ fontSize: 11, color: T.textSoft }}>
            {runAllStatus === "running"
              ? <><span style={{ color: "#7c3aed", fontWeight: 600, animation: "kw2Pulse 1.5s infinite" }}>⚙ {runAllStage}</span></>
              : runAllStatus === "done" ? <span style={{ color: T.teal, fontWeight: 700 }}>✓ {runAllStage}</span>
              : runAllStatus === "error" ? <span style={{ color: T.red }}>{runAllStage}</span>
              : "Questions → Enrich → Discover → Dedup → Cluster → Score → Auto-Select (AI chooser will appear first)"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {runAllStatus === "running" ? (
            <button
              onClick={handleStopAll}
              style={{ padding: "7px 18px", borderRadius: 8, border: "none", background: T.red, color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer" }}
            >
              ■ Stop
            </button>
          ) : (
            <button
              onClick={handleRunAll}
              disabled={isAnyBusy}
              style={{
                padding: "7px 20px", borderRadius: 8, border: "none",
                background: isAnyBusy ? T.grayLight : T.purple,
                color: isAnyBusy ? T.textSoft : "#fff",
                fontSize: 13, fontWeight: 800, cursor: isAnyBusy ? "not-allowed" : "pointer",
                letterSpacing: 0.3,
              }}
            >
              {runAllStatus === "done" ? "🔄 Run Again" : runAllStatus === "error" ? "↺ Retry All" : "▶ Run Full Pipeline"}
            </button>
          )}
        </div>
      </div>

      {/* ── Workflow pipeline ── */}
      <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 12, padding: "14px 18px", marginBottom: 16 }}>

        {/* Step 1 — Pillar Round-Robin */}
        {(() => {
          const profilePillars = pipelineStatus?.profile_pillars || []
          const peRunning = pillarExp?.status === "running"
          const pePaused  = pillarExp?.status === "paused"
          const peDone    = pillarExp?.status === "done"
          const pePct     = pillarExp ? Math.min(100, Math.round((pillarExp.totalGenerated / pillarExp.maxTotal) * 100)) : 0
          if (profilePillars.length === 0) return null
          return (
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 10, fontWeight: 800, color: T.textSoft, textTransform: "uppercase", letterSpacing: 1 }}>Step 1 — Pillar Round-Robin</span>
                <span style={{ fontWeight: 400, textTransform: "none", fontSize: 11, color: T.textSoft }}>(generates questions per product pillar, cycling {profilePillars.length} pillars)</span>
                {peDone && <span style={{ fontSize: 10, background: "#dcfce7", color: "#166534", padding: "1px 7px", borderRadius: 99, fontWeight: 700 }}>✓ Done</span>}
              </div>
              {pillarExp && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: T.textSoft, marginBottom: 4 }}>
                    <span>
                      {peRunning && <><b style={{ color: "#7c3aed" }}>{pillarExp.pillars[pillarExp.currentPillarIdx]}</b>{` — Round ${pillarExp.currentRound}`}</>}
                      {pePaused && `⏸ Paused — ${pillarExp.pillars[pillarExp.currentPillarIdx]} · Round ${pillarExp.currentRound}`}
                      {peDone && `✓ Complete — ${pillarExp.totalGenerated} questions generated`}
                    </span>
                    <span style={{ fontWeight: 700, color: "#7c3aed" }}>{pillarExp.totalGenerated} / {pillarExp.maxTotal} ({pePct}%)</span>
                  </div>
                  <div style={{ height: 6, background: T.grayLight, borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${pePct}%`, background: peDone ? T.teal : "#7c3aed", borderRadius: 3, transition: "width 0.4s" }} />
                  </div>
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 6 }}>
                    {pillarExp.pillars.map((p, i) => {
                      const cnt = pillarExp.pillarCounts?.[p] || 0
                      const isActive = peRunning && i === pillarExp.currentPillarIdx
                      return (
                        <span key={p} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99, fontWeight: 600,
                          background: isActive ? "#7c3aed" : cnt > 0 ? "#ede9fe" : T.grayLight,
                          color: isActive ? "#fff" : cnt > 0 ? "#5b21b6" : T.textSoft,
                          border: isActive ? "none" : `1px solid ${T.border}` }}>
                          {p}: {cnt}
                        </span>
                      )
                    })}
                  </div>
                  {pillarExp.lastError && <div style={{ fontSize: 11, color: T.red, marginTop: 4 }}>⚠ {pillarExp.lastError}</div>}
                </div>
              )}
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                {!pillarExp ? (
                  <>
                    <button style={btnStyle("#7c3aed")} onClick={() => startPillarExp(profilePillars, pePerRound, peMax)} disabled={isAnyBusy || pillarExp?.status === "running"}>
                      🔄 Start Pillar Round-Robin
                    </button>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: T.textSoft }}>
                      <label>Per pillar:</label>
                      <select value={pePerRound} onChange={e => setPePerRound(Number(e.target.value))}
                        style={{ fontSize: 11, padding: "2px 6px", borderRadius: 5, border: `1px solid ${T.border}` }}>
                        {[3,5,7,10].map(n => <option key={n} value={n}>{n}</option>)}
                      </select>
                      <label>Max:</label>
                      <input type="range" min={50} max={500} step={50} value={peMax}
                        onChange={e => setPeMax(Number(e.target.value))} style={{ width: 90 }} />
                      <b style={{ minWidth: 28 }}>{peMax}</b>
                    </div>
                  </>
                ) : (
                  <>
                    {peRunning && <button style={btnStyle("#f59e0b")} onClick={pausePillarExp}>⏸ Pause</button>}
                    {pePaused && <button style={btnStyle("#059669")} onClick={resumePillarExp}>▶ Resume</button>}
                    {!peDone && <button style={btnStyle("#ef4444")} onClick={stopPillarExp}>■ Stop &amp; Clear</button>}
                    {(peDone || pePaused) && (
                      <button style={btnStyle("#7c3aed")} onClick={() => startPillarExp(profilePillars, pillarExp.perRound || pePerRound, pillarExp.maxTotal || peMax)}>
                        🔄 Run Again
                      </button>
                    )}
                    {peDone && <button style={{ ...btnStyle("#6b7280"), fontSize: 11 }} onClick={stopPillarExp}>✕ Clear</button>}
                  </>
                )}
              </div>
            </div>
          )
        })()}

        {/* Step 2 — Generate & Enrich */}
        <div style={{ borderTop: (pipelineStatus?.profile_pillars || []).length > 0 ? `1px solid ${T.border}` : "none", paddingTop: (pipelineStatus?.profile_pillars || []).length > 0 ? 12 : 0, marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 10, fontWeight: 800, color: T.textSoft, textTransform: "uppercase", letterSpacing: 1 }}>Step 2 — Generate &amp; Enrich</span>
            {isDone("generate") && isDone("enrich") && <span style={{ fontSize: 10, background: "#dcfce7", color: "#166534", padding: "1px 7px", borderRadius: 99, fontWeight: 700 }}>✓ Complete</span>}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <button style={btnStyle(isDone("generate") ? "#4b5563" : T.purple)} onClick={handleRunQuestions} disabled={busy.questions || isAnyBusy}>
              {busy.questions ? "⟳ Running…" : isDone("generate") ? `✓ Re-Generate (${totalCount})` : "🧠 Generate Questions (Q1–Q7)"}
            </button>
            <button
              style={btnStyle(isBlocked("enrich") ? "#94a3b8" : unenrichedCount > 0 ? T.teal : "#4b5563")}
              onClick={handleEnrich}
              disabled={busy.enrich || isAnyBusy || isBlocked("enrich")}
              title={isBlocked("enrich") ? "Generate questions first" : undefined}
            >
              {busy.enrich
                ? enrichProgress ? `⟳ Enriching ${enrichProgress.done}/${enrichProgress.total}…` : "⟳ Enriching…"
                : isBlocked("enrich") ? "✨ Enrich (needs questions)"
                : unenrichedCount > 0 ? `✨ Enrich (${unenrichedCount} pending)` : "✓ Fully Enriched"}
            </button>
            {unenrichedCount > 0 && !busy.enrich && !isBlocked("enrich") && (
              <span style={{ fontSize: 11, color: "#f59e0b" }}>⚠ {unenrichedCount} need intent/funnel tags</span>
            )}
          </div>
        </div>

        {/* Step 3 — Dimension Expand (per-seed, with progress) */}
        <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 12, marginBottom: 12 }}>
          {(() => {
            const deRunning = dimExp?.status === "running"
            const dePaused  = dimExp?.status === "paused"
            const deDone    = dimExp?.status === "done"
            const dePct     = dimExp && dimExp.seeds?.length > 0
              ? Math.min(100, Math.round((dimExp.currentIdx / dimExp.seeds.length) * 100))
              : 0
            return (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 10, fontWeight: 800, color: T.textSoft, textTransform: "uppercase", letterSpacing: 1 }}>Step 3 — Expand</span>
                  <span style={{ fontWeight: 400, textTransform: "none", fontSize: 11, color: T.textSoft }}>(multiplies questions across {dimCount || "?"} audience/geo/brand angles)</span>
                  {deDone && <span style={{ fontSize: 10, background: "#ede9fe", color: "#5b21b6", padding: "1px 7px", borderRadius: 99, fontWeight: 700 }}>✓ Expanded</span>}
                  {isDone("expand") && !dimExp && <span style={{ fontSize: 10, background: "#ede9fe", color: "#5b21b6", padding: "1px 7px", borderRadius: 99, fontWeight: 700 }}>✓ Expanded</span>}
                </div>

                {/* Discover dimensions first */}
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-start", marginBottom: 8 }}>
                  <button
                    style={btnStyle(isBlocked("discover") ? "#94a3b8" : isDone("discover") ? "#0284c7" : "#0ea5e9")}
                    onClick={handleDiscoverDimensions}
                    disabled={busy.discover || isAnyBusy || isBlocked("discover")}
                    title={isBlocked("discover") ? "Generate questions first" : undefined}
                  >
                    {busy.discover ? "⟳ Discovering…"
                      : isBlocked("discover") ? "🔍 Discover Dimensions (needs questions)"
                      : hasDimensions ? `✓ ${dimCount} Dimensions — Re-Discover`
                      : "🔍 Discover Dimensions"}
                  </button>
                  {hasDimensions && (
                    <div style={{ alignSelf: "center", fontSize: 11, color: T.textSoft }}>
                      {Object.entries(expansionConfig?.discovered_dimensions || {}).slice(0,5).map(([k, vs]) => (
                        <span key={k} style={{ marginRight: 6 }}>
                          <b>{k}</b>: {[].concat(vs).slice(0,2).join(", ")}{[].concat(vs).length > 2 ? "…" : ""}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Progress UI */}
                {dimExp && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: T.textSoft, marginBottom: 4 }}>
                      <span>
                        {deRunning && dimExp.seeds && <><b style={{ color: "#7c3aed" }}>Expanding seed {dimExp.currentIdx + 1}/{dimExp.seeds.length}:</b>{" "}{dimExp.seeds[dimExp.currentIdx]?.question?.slice(0, 60)}…</>}
                        {dePaused && `⏸ Paused at seed ${dimExp.currentIdx + 1}/${dimExp.seeds?.length || "?"}`}
                        {deDone && `✓ Done — ${dimExp.totalCreated} new questions generated`}
                      </span>
                      <span style={{ fontWeight: 700, color: "#7c3aed" }}>{dimExp.currentIdx}/{dimExp.seeds?.length || "?"} seeds ({dePct}%)</span>
                    </div>
                    <div style={{ height: 6, background: T.grayLight, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${dePct}%`, background: deDone ? T.teal : "#7c3aed", borderRadius: 3, transition: "width 0.4s" }} />
                    </div>
                    <div style={{ fontSize: 11, color: T.textSoft, marginTop: 4 }}>
                      {dimExp.totalCreated} questions generated · {dimExp.maxTotal - dimExp.totalCreated} remaining budget
                    </div>
                    {dimExp.lastError && <div style={{ fontSize: 11, color: T.red, marginTop: 4 }}>⚠ {dimExp.lastError}</div>}
                  </div>
                )}

                {/* Expand controls */}
                {hasDimensions && (
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    {!dimExp ? (
                      <>
                        <button
                          style={btnStyle(isBlocked("expand") ? "#94a3b8" : "#7c3aed")}
                          onClick={() => startDimExp(expandMax <= 50 ? 3 : Math.round(expandMax / 100), expandMax)}
                          disabled={isAnyBusy || isBlocked("expand") || !hasDimensions}
                        >
                          🚀 Expand ({totalCount} seeds → max {expandMax})
                        </button>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: T.textSoft }}>
                          <label>Max:</label>
                          <input type="range" min={50} max={1000} step={50} value={expandMax}
                            onChange={e => setExpandMax(Number(e.target.value))} style={{ width: 110 }} />
                          <b style={{ minWidth: 36 }}>{expandMax}</b>
                        </div>
                        <span style={{ fontSize: 11, color: T.textSoft }}>{dimCount} dims · est ~{Math.min(expandMax, totalCount * dimCount * 3)} new</span>
                      </>
                    ) : (
                      <>
                        {deRunning && <button style={btnStyle("#f59e0b")} onClick={pauseDimExp}>⏸ Pause</button>}
                        {dePaused && <button style={btnStyle("#059669")} onClick={resumeDimExp}>▶ Resume</button>}
                        {!deDone && <button style={btnStyle("#ef4444")} onClick={stopDimExp}>■ Stop &amp; Clear</button>}
                        {(deDone || dePaused) && (
                          <button style={btnStyle("#7c3aed")} onClick={() => startDimExp(dimExp.maxPerNode || 3, dimExp.maxTotal || expandMax)}>
                            🔄 Run Again
                          </button>
                        )}
                        {deDone && <button style={{ ...btnStyle("#6b7280"), fontSize: 11 }} onClick={stopDimExp}>✕ Clear</button>}
                      </>
                    )}
                  </div>
                )}
              </>
            )
          })()}
        </div>

        {/* Step 4 — Process */}
        <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 10, fontWeight: 800, color: T.textSoft, textTransform: "uppercase", letterSpacing: 1 }}>Step 4 — Process</span>
            {isDone("select") && <span style={{ fontSize: 10, background: "#dcfce7", color: "#166534", padding: "1px 7px", borderRadius: 99, fontWeight: 700 }}>✓ Complete</span>}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
              <button
                style={btnStyle(isBlocked("dedup") ? "#94a3b8" : isDone("dedup") ? "#4338ca" : "#6366f1")}
                onClick={handleDedup}
                disabled={busy.dedup || isAnyBusy || isBlocked("dedup")}
              >
                {busy.dedup ? "⟳ Deduplicating…" : isDone("dedup") ? `✓ Dedup (${pipelineStatus?.dedup?.unique ?? "?"} unique)` : "🔁 Dedup"}
              </button>
              {isBlocked("dedup") && <span style={{ fontSize: 10, color: "#94a3b8" }}>needs questions</span>}
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
              <button
                style={btnStyle(isBlocked("cluster") ? "#94a3b8" : isDone("cluster") ? "#b45309" : "#f59e0b")}
                onClick={handleCluster}
                disabled={busy.cluster || isAnyBusy || isBlocked("cluster")}
              >
                {busy.cluster ? "⟳ Clustering…" : isDone("cluster") ? `✓ ${clusterCount} Clusters` : `📦 Cluster${clusterCount > 0 ? ` (${clusterCount})` : ""}`}
              </button>
              {isBlocked("cluster") && <span style={{ fontSize: 10, color: "#94a3b8" }}>needs questions</span>}
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
              <button
                style={btnStyle(isBlocked("score") ? "#94a3b8" : isDone("score") ? "#9d174d" : "#ec4899")}
                onClick={handleScore}
                disabled={busy.score || isAnyBusy || isBlocked("score")}
              >
                {busy.score ? "⟳ Scoring…" : isDone("score") ? `✓ ${scoredCount} Scored` : `⭐ Score${scoredCount > 0 ? ` (${scoredCount})` : ""}`}
              </button>
              {isBlocked("score") && <span style={{ fontSize: 10, color: "#94a3b8" }}>needs clusters</span>}
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
              <button
                style={btnStyle(isBlocked("select") ? "#94a3b8" : isDone("select") ? "#065f46" : T.teal)}
                onClick={handleSelect}
                disabled={busy.select || isAnyBusy || isBlocked("select")}
              >
                {busy.select ? "⟳ Selecting…" : isDone("select") ? `✓ ${selectedCount} Selected` : `✅ Auto-Select${selectedCount > 0 ? ` (${selectedCount})` : " (top 100)"}`}
              </button>
              {isBlocked("select") && <span style={{ fontSize: 10, color: "#94a3b8" }}>needs scored questions</span>}
            </div>
            <button style={{ ...btnStyle("#64748b"), marginLeft: "auto" }} onClick={() => setShowWeights(v => !v)}>
              ⚙ Weights
            </button>
          </div>
        </div>
      </div>

      {/* ── Active operation indicator ── */}
      {activeOp && (() => {
        const meta = opMeta[activeOp[0]] || { label: activeOp[0], what: "" }
        const pct = activeOp[0] === "enrich" && enrichProgress
          ? Math.round(enrichProgress.done / Math.max(enrichProgress.total, 1) * 100)
          : busy._progress || null
        return (
          <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 10, padding: "12px 16px", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 16, animation: "kw2Spin 1s linear infinite", display: "inline-block" }}>⟳</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>{meta.label}</div>
                <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>{meta.what}</div>
              </div>
              {pct != null && <span style={{ fontWeight: 700, color: "#89b4fa", fontSize: 13 }}>{pct}%</span>}
            </div>
            {pct != null && (
              <div style={{ height: 4, background: "#1e293b", borderRadius: 2, overflow: "hidden", marginTop: 8 }}>
                <div style={{ width: `${pct}%`, height: "100%", background: "linear-gradient(90deg,#3b82f6,#a78bfa)", borderRadius: 2, transition: "width 0.5s ease" }} />
              </div>
            )}
          </div>
        )
      })()}

      {/* ── Scoring weights editor ── */}
      {showWeights && scoringConfig?.weights && (
        <div style={{ background: "#f8fafc", border: `1px solid ${T.border}`, borderRadius: 10, padding: 16, marginBottom: 16 }}>
          <div style={{ fontWeight: 700, marginBottom: 10, fontSize: 13 }}>Scoring Weights (must sum to 1.0)</div>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            {Object.entries(scoringWeights || scoringConfig.weights).map(([k, v]) => (
              <div key={k} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={{ fontSize: 11, color: T.textSoft }}>{k}</label>
                <input type="number" step="0.05" min="0" max="1" value={v}
                  onChange={e => setScoringWeights(prev => ({ ...(prev || scoringConfig.weights), [k]: parseFloat(e.target.value) }))}
                  style={{ width: 70, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 13 }} />
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: Math.abs(Object.values(scoringWeights || scoringConfig.weights).reduce((sum, value) => sum + (Number(value) || 0), 0) - 1) > 0.001 ? T.red : T.textSoft, marginTop: 8 }}>
            Total: {Object.values(scoringWeights || scoringConfig.weights).reduce((sum, value) => sum + (Number(value) || 0), 0).toFixed(2)}
          </div>
          <button style={{ ...btnStyle(), marginTop: 10 }} onClick={handleSaveWeights} disabled={busy.weights}>
            {busy.weights ? "Saving…" : "Save Weights"}
          </button>
        </div>
      )}

      {/* ── Section tabs ── */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, alignItems: "center" }}>
        {[
          { id: "questions", label: `Questions (${totalCount})` },
          { id: "ranked",    label: `Ranked (${ranked.length})` },
          { id: "clusters",  label: `Clusters (${clusterCount})` },
          { id: "selected",  label: `Selected (${selectedCount})` },
        ].map(({ id, label }) => (
          <button key={id} style={secBtn(id)} onClick={() => { setActiveSection(id); setExpandedCluster(null) }}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Questions view ── */}
      {activeSection === "questions" && (
        <div>
          {/* Search + filter bar */}
          <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center" }}>
            <input
              value={qSearch} onChange={e => setQSearch(e.target.value)}
              placeholder="Search questions…"
              style={{ flex: 1, padding: "7px 12px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13 }}
            />
            <select value={qFilterIntent} onChange={e => setQFilterIntent(e.target.value)}
              style={{ padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, color: T.textSoft }}>
              <option value="">All intent</option>
              {["informational","transactional","commercial","navigational"].map(i => (
                <option key={i} value={i}>{i}</option>
              ))}
            </select>
            <span style={{ fontSize: 12, color: T.textSoft, whiteSpace: "nowrap" }}>
              {filteredQuestions.length} of {questions.length}
            </span>
          </div>
          {filteredQuestions.length === 0 && (
            <div style={{ color: T.textSoft, fontSize: 13, padding: "24px 0", textAlign: "center" }}>
              {questions.length === 0 ? 'No questions yet — click "Generate Questions" to start.' : "No questions match filters."}
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {filteredQuestions.map(q => {
              const ic = intentColor(q.intent)
              const fc = funnelColor(q.funnel_stage)
              return (
                <div key={q.id} style={{
                  background: q.is_duplicate ? "#fffbeb" : "#fff",
                  border: `1px solid ${q.is_duplicate ? "#fde68a" : T.border}`,
                  borderRadius: 8, padding: "10px 14px",
                  display: "flex", alignItems: "flex-start", gap: 10,
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", lineHeight: 1.4, marginBottom: 6 }}>
                      {q.question_text || <span style={{ color: T.textSoft, fontStyle: "italic" }}>(no text)</span>}
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                      {q.module_id && (
                        <span style={{ fontSize: 10, background: "#f1f5f9", color: "#475569", padding: "1px 6px", borderRadius: 4, fontFamily: "monospace" }}>{q.module_id}</span>
                      )}
                      {q.intent && (
                        <span style={{ fontSize: 10, background: ic.bg, color: ic.fg, padding: "1px 7px", borderRadius: 4, fontWeight: 600 }}>{q.intent}</span>
                      )}
                      {q.funnel_stage && (
                        <span style={{ fontSize: 10, background: fc.bg, color: fc.fg, padding: "1px 7px", borderRadius: 4, fontWeight: 600 }}>{q.funnel_stage}</span>
                      )}
                      {q.audience && (
                        <span style={{ fontSize: 10, color: T.textSoft }}>{q.audience}</span>
                      )}
                      {q.final_score > 0 && (
                        <span style={{ fontSize: 10, fontWeight: 700, color: "#d97706" }}>⭐ {q.final_score.toFixed(1)}</span>
                      )}
                      {q.is_duplicate && (
                        <span style={{ fontSize: 10, background: "#fef3c7", color: "#92400e", padding: "1px 6px", borderRadius: 4 }}>DUPLICATE</span>
                      )}
                      {(q.expansion_depth || 0) > 0 && (
                        <span style={{ fontSize: 10, background: "#ede9fe", color: "#5b21b6", padding: "1px 6px", borderRadius: 4 }}>Expanded</span>
                      )}
                      {renderDimensionBadge(q)}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteQuestion(q.id)}
                    style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", fontSize: 16, padding: "2px 4px", lineHeight: 1, flexShrink: 0 }}
                    title="Delete question"
                  >✕</button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Ranked view ── */}
      {activeSection === "ranked" && (
        <div>
          {ranked.length === 0 && (
            <div style={{ color: T.textSoft, fontSize: 13, padding: "24px 0", textAlign: "center" }}>
              No scored questions yet. Run "⭐ Score" first.
            </div>
          )}
          {ranked.length > 0 && (
            <div style={{ display: "flex", gap: 6, marginBottom: 10, alignItems: "center" }}>
              <select value={selectedIntent || ""} onChange={e => setSelectedIntent(e.target.value || null)}
                style={{ padding: "6px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12 }}>
                <option value="">All intent</option>
                {["informational","transactional","commercial","navigational"].map(i => (
                  <option key={i} value={i}>{i}</option>
                ))}
              </select>
              <span style={{ fontSize: 12, color: T.textSoft }}>{ranked.length} questions ranked</span>
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {ranked.slice(0, 200).map((q, i) => {
              const ic = intentColor(q.intent)
              const fc = funnelColor(q.funnel_stage)
              const scoreWidth = typeof q.final_score === "number" ? Math.round((q.final_score / 100) * 100) : 0
              return (
                <div key={q.id} style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 8, padding: "10px 14px" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                    <div style={{ minWidth: 32, fontWeight: 800, fontSize: 15, color: i < 10 ? T.purple : T.textSoft, paddingTop: 1 }}>#{i+1}</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", lineHeight: 1.4, marginBottom: 5 }}>
                        {q.question_text || <span style={{ color: T.textSoft, fontStyle: "italic" }}>(no text)</span>}
                      </div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
                        {q.intent && <span style={{ fontSize: 10, background: ic.bg, color: ic.fg, padding: "1px 7px", borderRadius: 4, fontWeight: 600 }}>{q.intent}</span>}
                        {q.funnel_stage && <span style={{ fontSize: 10, background: fc.bg, color: fc.fg, padding: "1px 7px", borderRadius: 4, fontWeight: 600 }}>{q.funnel_stage}</span>}
                        {q.cluster_id && <span style={{ fontSize: 10, color: T.textSoft }}>cluster: {clusterNameById[q.cluster_id] || q.cluster_id?.slice(-6)}</span>}
                        {renderDimensionBadge(q)}
                      </div>
                      {/* Score bar */}
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ flex: 1, height: 4, background: "#f1f5f9", borderRadius: 2, overflow: "hidden" }}>
                          <div style={{ width: `${scoreWidth}%`, height: "100%", background: i < 10 ? "#8b5cf6" : "#d97706", borderRadius: 2 }} />
                        </div>
                        <span style={{ fontWeight: 800, fontSize: 13, color: i < 10 ? T.purple : "#d97706", minWidth: 36, textAlign: "right" }}>
                          {typeof q.final_score === "number" ? q.final_score.toFixed(1) : "–"}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Clusters view ── */}
      {activeSection === "clusters" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {clusters.length === 0 && (
            <div style={{ color: T.textSoft, fontSize: 13, padding: "24px 0", textAlign: "center" }}>
              No clusters yet. Run "📦 Cluster" first.
            </div>
          )}
          {clusters.map(c => {
            const pc = pillarColor(c.pillar)
            const clusterQs = questions.filter(q => q.cluster_id === c.id)
            const isOpen = expandedCluster === c.id
            return (
              <div key={c.id} style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, overflow: "hidden" }}>
                <div
                  style={{ padding: "12px 16px", cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }}
                  onClick={() => setExpandedCluster(isOpen ? null : c.id)}
                >
                  <span style={{ fontSize: 14, userSelect: "none" }}>{isOpen ? "▼" : "▶"}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: "#111827" }}>{c.name}</div>
                    {c.description && <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>{c.description}</div>}
                  </div>
                  <div style={{ display: "flex", gap: 10, alignItems: "center", flexShrink: 0 }}>
                    {c.pillar && <span style={{ fontSize: 11, background: pc.bg, color: pc.fg, padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>{c.pillar}</span>}
                    <span style={{ fontSize: 12, color: T.textSoft }}>{c.question_count ?? clusterQs.length} Qs</span>
                    {c.avg_score > 0 && <span style={{ fontSize: 12, fontWeight: 700, color: "#d97706" }}>⭐ {c.avg_score.toFixed(1)}</span>}
                  </div>
                </div>
                {isOpen && (
                  <div style={{ borderTop: `1px solid ${T.border}`, background: "#fafafa" }}>
                    {clusterQs.length === 0 ? (
                      <div style={{ padding: "10px 16px", color: T.textSoft, fontSize: 12 }}>No questions linked to this cluster in current view.</div>
                    ) : (
                      clusterQs.map(q => {
                        const ic = intentColor(q.intent)
                        return (
                          <div key={q.id} style={{ padding: "8px 16px", borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 8 }}>
                            <div style={{ flex: 1, fontSize: 13, color: "#111827" }}>{q.question_text || <span style={{ color: T.textSoft, fontStyle: "italic" }}>(no text)</span>}</div>
                            <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                              {renderDimensionBadge(q)}
                              {q.intent && <span style={{ fontSize: 10, background: ic.bg, color: ic.fg, padding: "1px 6px", borderRadius: 4 }}>{q.intent}</span>}
                              {q.final_score > 0 && <span style={{ fontSize: 10, fontWeight: 700, color: "#d97706" }}>⭐{q.final_score.toFixed(1)}</span>}
                            </div>
                          </div>
                        )
                      })
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ── Selected view ── */}
      {activeSection === "selected" && (
        <div>
          {selected.length === 0 && (
            <div style={{ color: T.textSoft, fontSize: 13, padding: "24px 0", textAlign: "center" }}>
              No questions selected yet. Run "✅ Auto-Select" first.
            </div>
          )}
          {selected.length > 0 && (
            <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 10 }}>
              {selected.length} questions selected · sorted by selection rank
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {selected.map((q, i) => {
              const ic = intentColor(q.intent)
              const fc = funnelColor(q.funnel_stage)
              const pc = pillarColor(q.pillar)
              return (
                <div key={q.id} style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 8, padding: "10px 14px", display: "flex", alignItems: "flex-start", gap: 12 }}>
                  <div style={{ minWidth: 30, fontWeight: 800, fontSize: 14, color: T.purple, paddingTop: 1 }}>
                    #{q.selection_rank || i+1}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", lineHeight: 1.4, marginBottom: 5 }}>
                      {q.question_text || <span style={{ color: T.textSoft, fontStyle: "italic" }}>(no text)</span>}
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {q.intent && <span style={{ fontSize: 10, background: ic.bg, color: ic.fg, padding: "1px 7px", borderRadius: 4, fontWeight: 600 }}>{q.intent}</span>}
                      {q.funnel_stage && <span style={{ fontSize: 10, background: fc.bg, color: fc.fg, padding: "1px 7px", borderRadius: 4, fontWeight: 600 }}>{q.funnel_stage}</span>}
                      {q.pillar && <span style={{ fontSize: 10, background: pc.bg, color: pc.fg, padding: "1px 7px", borderRadius: 4, fontWeight: 600 }}>{q.pillar}</span>}
                      {renderDimensionBadge(q)}
                      {q.final_score > 0 && <span style={{ fontSize: 10, fontWeight: 700, color: "#d97706" }}>⭐ {q.final_score.toFixed(1)}</span>}
                    </div>
                  </div>
                  <button
                    onClick={() => handleRemoveSelected(q.question_id)}
                    style={{ background: "none", border: `1px solid ${T.border}`, borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 11, color: T.red, flexShrink: 0 }}
                  >✕ Remove</button>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  MAIN COMPONENT
// ─────────────────────────────────────────────────────────────────────────────
export default function SessionStrategyPage({ projectId, sessionId, session, onBack, setPage }) {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState("overview")
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState([])
  const [showConsole, setShowConsole] = useState(false)
  const [consoleHeight, setConsoleHeight] = useState(280)
  const [contentParams, setContentParams] = useState(CP_DEFAULTS)
  const [activeAI, setActiveAI] = useState(null)   // { provider, step, progress }
  const abortRef = useRef(null)                     // AbortController for phase9 fetch

  // Global AI chooser — passed to any tab that triggers AI
  const { chooseAI, AIChooserModal } = useAIChooser()

  const pushLog = useCallback((msg, badge = "INFO", detail = null, extras = {}) => {
    setLogs(prev => [...prev, { msg, badge, detail, ts: Date.now(), ...extras }])
  }, [])

  // Update the most recent log entry in-place (for live progress updates)
  const updateLastLog = useCallback((msg, extras = {}) => {
    setLogs(prev => {
      if (!prev.length) return prev
      const updated = [...prev]
      updated[updated.length - 1] = { ...updated[updated.length - 1], msg, ...extras }
      return updated
    })
  }, [])

  // Capture browser-level JS errors into this console
  useEffect(() => {
    const onError = (ev) => {
      pushLog(`[JS Error] ${ev.message} — ${ev.filename?.split("/").pop() || "?"}:${ev.lineno}`, "BROWSER", null)
      setShowConsole(true)
    }
    const onRejection = (ev) => {
      const msg = ev.reason?.message || String(ev.reason) || "Unhandled rejection"
      pushLog(`[Promise] ${msg}`, "BROWSER", null)
      setShowConsole(true)
    }
    window.addEventListener("error", onError)
    window.addEventListener("unhandledrejection", onRejection)
    return () => {
      window.removeEventListener("error", onError)
      window.removeEventListener("unhandledrejection", onRejection)
    }
  }, [pushLog])

  const mode = session?.mode || "expand"
  const st = MODE_STYLE[mode] || MODE_STYLE.expand

  const sessionLabel = session?.name ||
    (Array.isArray(session?.seed_keywords) && session.seed_keywords.length
      ? session.seed_keywords.slice(0, 3).join(" · ")
      : `Session ${(sessionId || "").slice(-6)}`)

  // ── Data queries ──
  const { data: validatedData } = useQuery({
    queryKey: ["ssp-validated", projectId, sessionId],
    queryFn: () => api.getValidated(projectId, sessionId),
    enabled: !!sessionId, staleTime: 60_000, retry: false,
  })

  const { data: strategyData, refetch: refetchStrategy } = useQuery({
    queryKey: ["ssp-strategy", projectId, sessionId],
    queryFn: () => api.getStrategy(projectId, sessionId).catch(() => null),
    enabled: !!sessionId, staleTime: 0, retry: false,
  })

  const { data: calendarData, refetch: refetchCalendar } = useQuery({
    queryKey: ["ssp-calendar", projectId, sessionId],
    queryFn: () => api.getCalendar(projectId, sessionId).catch(() => null),
    enabled: !!sessionId, staleTime: 60_000, retry: false,
  })

  const { data: linksData } = useQuery({
    queryKey: ["ssp-links", projectId, sessionId],
    queryFn: () => api.getLinks(projectId, sessionId).catch(() => null),
    enabled: !!sessionId, staleTime: 60_000, retry: false,
  })

  const { data: treeData, refetch: refetchTree } = useQuery({
    queryKey: ["ssp-tree", projectId, sessionId],
    queryFn: () => api.getTree(projectId, sessionId).catch(() => null),
    enabled: !!sessionId, staleTime: 60_000, retry: false,
  })

  const { data: pillarStats } = useQuery({
    queryKey: ["ssp-pillar-stats", projectId, sessionId],
    queryFn: () => api.getPillarStats(projectId, sessionId).catch(() => null),
    enabled: !!sessionId, staleTime: 60_000, retry: false,
  })

  const { data: bizContextData } = useQuery({
    queryKey: ["ssp-biz-context", projectId, sessionId],
    queryFn: () => api.getBizContextPreview(projectId, sessionId).catch(() => null),
    enabled: !!sessionId, staleTime: 120_000, retry: false,
  })

  // Pipeline status for strategy prerequisite gating
  const { data: strategyPipelineStatus, refetch: refetchStrategyPipeline } = useQuery({
    queryKey: ["ssp-strategy-pipeline", projectId, sessionId],
    queryFn: () => api.getPipelineStatus(projectId, sessionId).catch(() => null),
    enabled: !!sessionId, staleTime: 15_000, retry: false,
  })

  const strategyPrereqs = useMemo(() => buildStrategyPrereqs({
    bizContext: bizContextData,
    validatedData,
    pipelineStatus: strategyPipelineStatus,
  }), [bizContextData, validatedData, strategyPipelineStatus])

  useEffect(() => {
    if (!sessionId) return
    if (activeTab === "params" || activeTab === "strategy") {
      refetchStrategyPipeline()
    }
  }, [activeTab, sessionId, refetchStrategyPipeline])

  // Merge strategy from query result + session._strategy
  const strat = useMemo(() => {
    if (strategyData?.strategy) return strategyData.strategy
    if (session?._strategy) return session._strategy
    return null
  }, [strategyData, session])

  // ── Run Phase 9 ──
  const handleStop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
      pushLog("━━━ Stopped by user ━━━", "PHASE")
      setActiveAI(null)
      setRunning(false)
    }
  }, [pushLog])

  const handleRunPhase9 = async () => {
    let prereqs = strategyPrereqs
    if (!prereqs.allPrereqsMet) {
      try {
        const refreshed = await refetchStrategyPipeline()
        prereqs = buildStrategyPrereqs({
          bizContext: bizContextData,
          validatedData,
          pipelineStatus: refreshed?.data || strategyPipelineStatus,
        })
      } catch {
        // If refresh fails, continue with the currently cached snapshot.
      }
    }

    if (!prereqs.allPrereqsMet) {
      const missing = (prereqs.items || []).filter(i => !i.done).map(i => i.label)
      setShowConsole(true)
      pushLog(
        `Blocked: complete Research prerequisites before Strategy (${missing.join(", ") || "missing data"})`,
        "WARN"
      )
      setActiveTab("intelligence")
      return
    }

    // Ask user which AI provider to use
    const pickedProvider = await chooseAI("Which AI should generate your strategy?")
    if (!pickedProvider) return   // user cancelled

    // Cancel any previous in-flight request
    if (abortRef.current) abortRef.current.abort()

    const controller = new AbortController()
    abortRef.current = controller

    setRunning(true)
    setShowConsole(true)
    const t0 = Date.now()
    const aiProvider = pickedProvider
    const providerInfo = PROVIDERS.find(p => p.id === aiProvider)

    // Show active AI
    setActiveAI({ provider: aiProvider, step: "Starting", progress: 0 })

    pushLog("━━━ Strategy Generation Started ━━━", "PHASE")
    pushLog(`Session: ${sessionId}`, "DATA", `project: ${projectId}`)
    pushLog(
      `AI: ${providerInfo?.label || aiProvider} ${providerInfo?.icon || "🤖"} — ${providerInfo?.desc || "cascade fallback"}`,
      "AI", null, { ai: aiProvider }
    )
    pushLog(
      `Content plan: ${contentParams.blogs_per_week} blogs/week × ${contentParams.duration_weeks} weeks = ${contentParams.blogs_per_week * contentParams.duration_weeks} articles`,
      "DATA"
    )
    const mix = contentParams.content_mix
    pushLog(
      `Content mix: ${mix?.informational ?? 60}% informational · ${mix?.transactional ?? 20}% transactional · ${mix?.commercial ?? 20}% commercial`,
      "DATA"
    )
    if (contentParams.publishing_cadence?.length) {
      pushLog(`Publishing days: ${contentParams.publishing_cadence.join(", ")}`, "DATA")
    }
    if (contentParams.extra_prompt?.trim()) {
      pushLog(`Custom guidance: "${contentParams.extra_prompt.trim()}"`, "DATA")
    }

    // Step 1 / 5 — Module 2A
    setActiveAI({ provider: aiProvider, step: "2A: Business Analysis", progress: 5 })
    pushLog("Batch 1/4 — Module 2A: Business Analysis", "PROGRESS",
      "Loading profile, biz_intel, crawled pages, competitor data", { progress: 5, step: 1, total: 4, ai: aiProvider })

    // Step 2 / 5 — Module 2B
    setActiveAI({ provider: aiProvider, step: "2B: Keyword Intelligence", progress: 20 })
    pushLog("Batch 2/4 — Module 2B: Keyword Intelligence", "PROGRESS",
      "Processing all validated keywords — intent, pillar, cluster breakdown", { progress: 20, step: 2, total: 4, ai: aiProvider })

    // Step 3 / 5 — API call (batches 3+4 run server-side: 2C + 2D)
    setActiveAI({ provider: aiProvider, step: "2C+2D: Strategy Builder + Action Map (AI calling…)", progress: 40 })
    pushLog("Batch 3+4/4 — Calling AI strategy builder…", "API",
      `POST /api/kw2/${projectId}/sessions/${sessionId}/phase9`, { progress: 40, step: 3, total: 4, ai: aiProvider })

    try {
      const result = await api.runPhase9(projectId, sessionId, contentParams, controller.signal)
      if (controller.signal.aborted) return
      abortRef.current = null

      const elapsed = ((Date.now() - t0) / 1000).toFixed(1)
      const meta = result?.meta || {}
      const modelsUsed = meta.models_used || []
      const totalTokens = meta.total_tokens || 0
      const aiUsage = meta.ai_usage || []

      // Step 4 — AI response
      setActiveAI({ provider: aiProvider, step: "2D: Action Mapping", progress: 80 })
      const modelStr = modelsUsed.length ? modelsUsed.join(", ") : aiProvider
      pushLog(`Batch 4/4 — AI response received in ${elapsed}s`, "TIMING",
        `Models: ${modelStr} · Total tokens: ${totalTokens || "unknown"}`, { progress: 80, step: 4, total: 4, ai: aiProvider })

      // Per-module token breakdown (if available)
      if (aiUsage.length) {
        aiUsage.forEach((u, idx) => {
          pushLog(
            `  ↳ ${u.step || `Module ${idx + 1}`}: ${u.model} — ${u.tokens?.toLocaleString() || 0} tokens${u.cost_usd ? ` ($${u.cost_usd})` : ""}`,
            "DATA", null, { ai: u.model }
          )
        })
      }

      if (result?.strategy) {
        const s = result.strategy
        const summary = String(s.executive_summary || "")
        if (summary) pushLog(`Summary: ${summary.slice(0, 220)}${summary.length > 220 ? "…" : ""}`, "SUCCESS", summary.length > 220 ? summary : null)
        if (Array.isArray(s.pillar_strategies) && s.pillar_strategies.length) {
          pushLog(`Pillar strategies: ${s.pillar_strategies.length} pillars generated`, "SUCCESS",
            s.pillar_strategies.map(p => p?.pillar || String(p)).join(", "))
        }
        if (Array.isArray(s.quick_wins) && s.quick_wins.length) {
          pushLog(`Quick wins: ${s.quick_wins.length} identified`, "SUCCESS",
            s.quick_wins.slice(0, 6).map(q => q?.keyword || String(q)).join(", "))
        }
        if (Array.isArray(s.content_priorities) && s.content_priorities.length) {
          pushLog(`Content priorities: ${s.content_priorities.length} items scheduled`, "SUCCESS",
            `${contentParams.blogs_per_week * contentParams.duration_weeks} total articles planned`)
        }
        if (Array.isArray(s.competitive_gaps) && s.competitive_gaps.length) {
          pushLog(`Competitive gaps: ${s.competitive_gaps.length} identified`, "INFO",
            s.competitive_gaps.slice(0, 5).join(" · "))
        }
        if (s.timeline) {
          const tl = typeof s.timeline === "object" ? JSON.stringify(s.timeline).slice(0, 180) : String(s.timeline).slice(0, 180)
          pushLog(`Timeline: ${tl}`, "INFO")
        }
        if (s.link_building_plan) {
          pushLog(`Link building: ${String(s.link_building_plan).slice(0, 150)}`, "INFO")
        }
        if (result?.version_id) pushLog(`Strategy version saved: ${result.version_id}`, "DATA")
        if (meta.provider_requested) pushLog(`Provider requested: ${meta.provider_requested} · Modules run: ${meta.modules_run || 4}/4`, "DATA")
      } else {
        pushLog("Strategy returned (no structured preview)", "WARN")
      }

      // Step 5 — Refresh + auto-rebuild content plan
      setActiveAI({ provider: aiProvider, step: "Building content plan…", progress: 90 })
      pushLog("Step 5/5 — Refreshing data & building content plan…", "STEP", null, { progress: 90, step: 5, total: 5 })
      await refetchStrategy()
      await refetchStrategyPipeline()
      qc.invalidateQueries(["kw2-hub-sessions", projectId])
      qc.invalidateQueries(["kw2-validated-hub", projectId, sessionId])

      // Auto-rebuild calendar so content plan is instantly populated
      try {
        const calResult = await api.rebuildCalendar(projectId, sessionId)
        const calMeta = calResult?.calendar || calResult || {}
        const calTotal = calMeta.from_strategy + calMeta.from_intelligence + calMeta.from_keywords || calMeta.scheduled || 0
        pushLog(
          `📅 Content plan built: ${calTotal || "?"} articles scheduled`,
          "SUCCESS",
          `Strategy: ${calMeta.from_strategy || 0} · Intelligence: ${calMeta.from_intelligence || 0} · Keywords: ${calMeta.from_keywords || 0}`,
        )
      } catch {
        // non-fatal — user can manually rebuild
      }
      await refetchCalendar()
      qc.invalidateQueries(["ssp-calendar", projectId, sessionId])

      // Log calendar rebuild info if available from phase9 meta
      const calRebuilt = result?.meta?.calendar_rebuilt
      if (calRebuilt?.scheduled) {
        pushLog(`📅 Content calendar rebuilt: ${calRebuilt.scheduled} articles scheduled`, "SUCCESS",
          calRebuilt.from_strategy ? `${calRebuilt.from_strategy} from strategy, ${calRebuilt.from_keywords || 0} extra keywords` : null)
      }

      pushLog(`━━━ Complete — ${((Date.now() - t0) / 1000).toFixed(1)}s · ${modelsUsed.join("→") || aiProvider} · ${totalTokens.toLocaleString()} tokens ━━━`,
        "PHASE", null, { progress: 100 })

      // Auto-navigate to Content Map tab to show the result
      setActiveTab("tree")
      // Fetch fresh tree data
      refetchTree()
    } catch (e) {
      if (e?.name === "AbortError") {
        // handled by handleStop
        return
      }
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1)
      pushLog(`Failed after ${elapsed}s: ${String(e?.message || e)}`, "ERROR")
      const status = e?.status || e?.response?.status
      if (status) pushLog(`HTTP ${status}`, "ERROR", e?.message)
      const body = e?.body || e?.detail
      if (body) pushLog(`Server: ${typeof body === "object" ? JSON.stringify(body).slice(0, 300) : String(body).slice(0, 300)}`, "ERROR")
    }
    abortRef.current = null
    setActiveAI(null)
    setRunning(false)
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#f8f8f9" }}>
      <style>{`
        @keyframes kw2Pulse { 0%,100%{opacity:1} 50%{opacity:0.6} }
        @keyframes kw2Spin  { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes kw2SlideIn { from{opacity:0;transform:translateY(-6px)} to{opacity:1;transform:translateY(0)} }
      `}</style>

      {/* ── HEADER ── */}
      <div style={{
        background: "#fff", borderBottom: `1px solid ${T.border}`,
        padding: "12px 24px", display: "flex", alignItems: "center", gap: 14,
        flexShrink: 0,
      }}>
        <button
          onClick={onBack}
          style={{ padding: "5px 12px", borderRadius: 7, border: `1px solid ${T.border}`, background: "transparent",
            cursor: "pointer", fontSize: 12, color: T.textSoft, fontWeight: 500 }}
        >
          ← Strategy Hub
        </button>

        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
          <span style={{ padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700,
            background: st.badgeBg, color: st.badge }}>
            {st.icon} {st.label}
          </span>
          <span style={{ fontSize: 16, fontWeight: 800, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {sessionLabel}
          </span>
          {session?.phase9_done && (
            <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 20, background: "#dcfce7", color: T.teal, fontWeight: 700, flexShrink: 0 }}>
              ✓ Strategy Ready
            </span>
          )}
        </div>

        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          {setPage && (
            <button
              onClick={() => setPage("kw2")}
              style={{ padding: "5px 12px", borderRadius: 7, border: `1px solid ${T.border}`, background: "transparent",
                cursor: "pointer", fontSize: 12, color: T.purpleDark, fontWeight: 600 }}
            >
              Open in Keywords v2 →
            </button>
          )}
          <button
            onClick={() => setActiveTab("params")}
            disabled={running}
            style={{ padding: "5px 14px", borderRadius: 7, border: "none",
              background: running ? T.grayLight : (session?.phase9_done ? T.grayLight : T.purple),
              color: running ? T.textSoft : (session?.phase9_done ? T.purpleDark : "#fff"),
              cursor: running ? "not-allowed" : "pointer", fontSize: 12, fontWeight: 700,
              opacity: running ? 0.7 : 1,
            }}
          >
            {running ? "Running…" : session?.phase9_done ? "🔄 Adjust & Regenerate" : "⚙️ Configure Strategy"}
          </button>
          {/* AI running badge — shown in header while strategy is generating */}
          {activeAI && (
            <AIRunningBadge ai={activeAI.provider} step={activeAI.step} progress={activeAI.progress} />
          )}
          <button
            onClick={() => setShowConsole(v => !v)}
            style={{
              padding: "5px 10px", borderRadius: 7,
              border: `1px solid ${showConsole ? "#334155" : T.border}`,
              background: showConsole ? "#080c16" : T.grayLight,
              color: showConsole ? "#7dd3fc" : T.textSoft,
              cursor: "pointer", fontSize: 11, fontWeight: 700, fontFamily: "monospace",
              display: "flex", alignItems: "center", gap: 5,
            }}
          >
            ⌨ Console
            {logs.length > 0 && (
              <span style={{
                background: running ? T.amber : "#334155",
                color: running ? "#000" : "#94a3b8",
                borderRadius: 9, padding: "0 5px", fontSize: 10,
              }}>
                {logs.filter(l => l.badge === "ERROR" || l.badge === "BROWSER").length > 0
                  ? `⚠ ${logs.filter(l => l.badge === "ERROR" || l.badge === "BROWSER").length}`
                  : logs.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* ── TABS ── */}
      <div style={{
        background: "#fff", borderBottom: `1px solid ${T.border}`,
        padding: "0 24px", display: "flex", gap: 2, flexShrink: 0,
      }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: "10px 16px", border: "none", cursor: "pointer", fontSize: 13,
              fontWeight: activeTab === tab.id ? 700 : 400,
              background: "transparent",
              color: activeTab === tab.id ? T.purple : T.textSoft,
              borderBottom: `2px solid ${activeTab === tab.id ? T.purple : "transparent"}`,
              borderRadius: "0",
              transition: "all .12s",
            }}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* ── CONTENT ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px", minHeight: 0 }}>
        {activeTab === "overview" && (
          <OverviewTab
            session={session}
            validatedData={validatedData}
            pillarStats={pillarStats}
            strat={strat}
            bizContext={bizContextData}
            onRunPhase9={() => setActiveTab("params")}
            onGoToTab={setActiveTab}
            running={running}
            logs={logs}
            projectId={projectId}
          />
        )}
        {activeTab === "params" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <ContentParametersTab
              params={contentParams}
              setParams={setContentParams}
              onGenerate={handleRunPhase9}
              running={running}
              hasStrategy={!!session?.phase9_done}
              projectId={projectId}
              sessionId={sessionId}
              pillarStats={pillarStats}
              strategyPrereqs={strategyPrereqs}
              onGoToIntelligence={() => setActiveTab("intelligence")}
            />
            {/* Goals section at bottom of Configure */}
            <GoalsTab projectId={projectId} session={session} bizContext={bizContextData} />
          </div>
        )}
        {activeTab === "keywords" && (
          <KeywordsTab validatedData={validatedData} pillarStats={pillarStats} bizContext={bizContextData} />
        )}
        {activeTab === "strategy" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <StrategyTab
              strat={strat} session={session} bizContext={bizContextData}
              onRunPhase9={() => handleRunPhase9()} running={running}
              onGoToIntelligence={() => setActiveTab("intelligence")}
              onGoToParams={() => setActiveTab("params")}
              strategyPrereqs={strategyPrereqs}
            />
            {/* Content Plan — always shown below strategy */}
            <ContentPlanTab strat={strat} calendarData={calendarData} projectId={projectId} sessionId={sessionId} startDate={contentParams.start_date} refetchCalendar={refetchCalendar} chooseAI={chooseAI} onRegenerate={handleRunPhase9} />
            {/* Link suggestions at bottom */}
            {linksData?.items?.length > 0 && (
              <LinkBuildingTab linksData={linksData} />
            )}
          </div>
        )}
        {activeTab === "intelligence" && (
          <IntelligenceTab projectId={projectId} sessionId={sessionId} chooseAI={chooseAI} />
        )}
        {activeTab === "tree" && (
          <ContentTreeTab
            treeData={treeData}
            strat={strat}
            calendarData={calendarData}
            linksData={linksData}
            projectId={projectId}
            sessionId={sessionId}
            onGoToStrategy={() => setActiveTab("strategy")}
            onGoToParams={() => setActiveTab("params")}
          />
        )}
      </div>

      {/* ── CONSOLE PANEL ── */}
      {showConsole && (
        <ConsolePanel
          logs={logs}
          running={running}
          onClear={() => setLogs([])}
          onStop={running ? handleStop : null}
          onExit={() => setShowConsole(false)}
          height={consoleHeight}
          onHeightChange={setConsoleHeight}
        />
      )}

      {/* Global AI chooser modal — overlays all tabs */}
      {AIChooserModal}
    </div>
  )
}
