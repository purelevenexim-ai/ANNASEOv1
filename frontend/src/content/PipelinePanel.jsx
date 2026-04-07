import { useState, useEffect, useRef, useCallback } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { T, api, Badge } from "../App"
import { AI_PROVIDERS_BASE, _buildProviders } from "./NewArticleModal"
import { usePipelineQuery } from "../hooks/usePipelineQuery"

// ── Step definitions for the 11-step pipeline ─────────────────────────────────
export const STEP_DEFS = [
  { n: 1,  label: "Research",       icon: "🔍", desc: "Crawling competitor pages & Wikipedia" },
  { n: 2,  label: "Structure",      icon: "📐", desc: "Building headings, FAQ & outline" },
  { n: 3,  label: "Verify",         icon: "✅", desc: "Verifying structure relevance" },
  { n: 4,  label: "Internal Links", icon: "🔗", desc: "Planning internal link strategy" },
  { n: 5,  label: "References",     icon: "📚", desc: "Adding Wikipedia references" },
  { n: 6,  label: "Draft",          icon: "✍️", desc: "Writing full article content" },
  { n: 7,  label: "Review",         icon: "🔎", desc: "AI quality review" },
  { n: 8,  label: "Issues",         icon: "🛠",  desc: "Running 53-rule compliance checks" },
  { n: 9,  label: "Redevelop",      icon: "🚀", desc: "Rewriting to fix all issues" },
  { n: 10, label: "Score",          icon: "📊", desc: "53-rule quality scoring" },
  { n: 11, label: "Quality Loop",   icon: "🔄", desc: "Iterating until score ≥ 75%" },
]

// ── AI helpers ────────────────────────────────────────────────────────────────
const _normalizeProviderId = (v) => {
  const aliases = { claude: "anthropic", chatgpt: "openai_paid", openai: "openai_paid", gemini: "gemini_free" }
  return aliases[v] || v
}
function _getProviderColor(value) {
  const nv = _normalizeProviderId(value)
  const all = [...AI_PROVIDERS_BASE.free, ...AI_PROVIDERS_BASE.paid, ...AI_PROVIDERS_BASE.other]
  const f = all.find(p => p.value === nv)
  if (f) return f.color
  if (nv?.startsWith("ollama_remote")) return "#059669"
  return "#9ca3af"
}
function _getProviderLabel(value) {
  const nv = _normalizeProviderId(value)
  const all = [...AI_PROVIDERS_BASE.free, ...AI_PROVIDERS_BASE.paid, ...AI_PROVIDERS_BASE.other]
  const f = all.find(p => p.value === nv)
  if (f) return f.label
  if (nv?.startsWith("ollama_remote")) return "Ollama Remote"
  return nv || "Skip"
}

// ── Inline AI Selector (grouped with health indicators) ──────────────────────
function AISelect({ value, onChange, disabled, providers, healthData }) {
  const nv = _normalizeProviderId(value)
  const groups = providers || AI_PROVIDERS_BASE
  const color = _getProviderColor(nv)
  const hIcon = (v) => {
    const h = healthData?.[v]
    if (!h) return ""
    return h.status === "ok" ? " ✓" : h.status === "rate_limited" ? " ⚠" : " ✕"
  }
  return (
    <select value={nv || "skip"} onChange={e => onChange(e.target.value)} disabled={disabled}
      style={{
        fontSize: 10, padding: "3px 6px", borderRadius: 5,
        border: `1.5px solid ${color}40`, background: `${color}0a`, color,
        cursor: disabled ? "default" : "pointer", fontWeight: 600,
        outline: "none", opacity: disabled ? 0.5 : 1, minWidth: 100,
      }}>
      <optgroup label="Free Tier">
        {groups.free.map(o => <option key={o.value} value={o.value}>{o.label}{hIcon(o.value)}</option>)}
      </optgroup>
      <optgroup label="Paid Tier">
        {groups.paid.map(o => <option key={o.value} value={o.value}>{o.label}{hIcon(o.value)}</option>)}
      </optgroup>
      <optgroup label="Other">
        {groups.other.map(o => <option key={o.value} value={o.value}>{o.label}{hIcon(o.value)}</option>)}
      </optgroup>
    </select>
  )
}

// ── Health Status Badge ───────────────────────────────────────────────────────
function HealthBadge({ status }) {
  if (!status) return null
  const cfg = {
    ok:           { bg: "#10b98115", c: "#10b981", t: "Ready" },
    rate_limited: { bg: "#ef444420", c: "#ef4444", t: "Rate Limited" },
    error:        { bg: "#ef444420", c: "#ef4444", t: "Error" },
    no_key:       { bg: "#9ca3af20", c: "#9ca3af", t: "No Key" },
  }
  const s = cfg[status] || cfg.error
  return (
    <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 99, background: s.bg, color: s.c, fontWeight: 700 }}>
      {s.t}
    </span>
  )
}

// ── Live pipeline progress (full panel) ──────────────────────────────────────
function PipelineProgress({ articleId, onComplete }) {
  const qc = useQueryClient()
  // Bug #2 — shared hook (all consumers share one in-flight request via React Query)
  const { data, isLoading } = usePipelineQuery(articleId)

  const [healthData, setHealthData] = useState(null)
  const [healthLoading, setHealthLoading] = useState(false)
  const [expandedStep, setExpandedStep] = useState(null)
  const [ollamaServers, setOllamaServers] = useState([])

  // Fetch remote ollama servers
  useEffect(() => {
    api.get("/api/settings/ollama-servers").then(s => setOllamaServers(s || [])).catch(() => {})
  }, [])

  // Build dynamic AI provider list
  const aiProviders = _buildProviders(ollamaServers)

  // Auto-expand the running or paused step
  useEffect(() => {
    const steps = data?.steps || []
    const running = steps.find(s => s.status === "running")
    const paused = steps.find(s => s.status === "paused")
    if (running) setExpandedStep(running.step)
    else if (paused) setExpandedStep(paused.step)
  }, [data?.steps])

  // Bug #3 — only fire onComplete on transition FROM "generating" to something else
  const prevStatusRef = useRef(null)
  useEffect(() => {
    const prev = prevStatusRef.current
    prevStatusRef.current = data?.status
    if (prev === "generating" && data?.status && data.status !== "generating") {
      qc.invalidateQueries(["articles"])
      if (onComplete) onComplete()
    }
  }, [data?.status]) // eslint-disable-line

  // Bug #4 — use /api/ai/status (cache-read, zero live API calls) for health check
  const runHealthCheck = useCallback(async (force = false) => {
    setHealthLoading(true)
    try {
      const endpoint = force ? "/api/ai/health?force=true" : "/api/ai/status"
      const res = await api.get(endpoint)
      setHealthData(res)
    } catch (_) {}
    setHealthLoading(false)
  }, [])

  useEffect(() => { runHealthCheck() }, []) // eslint-disable-line

  // Mutations
  const continuePipeline = useMutation({
    mutationFn: (auto) => api.post(`/api/content/${articleId}/pipeline/continue`, { auto }),
    onSuccess: () => qc.invalidateQueries(["pipeline", articleId]),
  })
  const cancelPipeline = useMutation({
    mutationFn: () => api.post(`/api/content/${articleId}/pipeline/cancel`),
    onSuccess: () => qc.invalidateQueries(["pipeline", articleId]),
  })
  const pausePipeline = useMutation({
    mutationFn: () => api.post(`/api/content/${articleId}/pipeline/pause`),
    onSuccess: () => qc.invalidateQueries(["pipeline", articleId]),
  })
  const updateStepAI = useMutation({
    mutationFn: (payload) => api.post(`/api/content/${articleId}/pipeline/update-step`, payload),
    onSuccess: () => qc.invalidateQueries(["pipeline", articleId]),
  })
  const rerunStep = useMutation({
    mutationFn: (payload) => api.post(`/api/content/${articleId}/pipeline/rerun-step`, payload),
    onSuccess: () => qc.invalidateQueries(["pipeline", articleId]),
  })

  const steps = data?.steps || []
  const logs = data?.logs || []
  const ruleResults = data?.rule_results || null
  const isPaused = data?.is_paused || false
  const stepMode = data?.step_mode || "auto"
  const doneCount = steps.filter(s => s.status === "done").length
  const errorCount = steps.filter(s => s.status === "error").length
  const runningStep = steps.find(s => s.status === "running")
  const pausedStep = steps.find(s => s.status === "paused")
  const totalSteps = STEP_DEFS.length
  const pct = Math.round((doneCount / totalSteps) * 100)

  return (
    <div style={{ padding: 20, maxWidth: 620, margin: "0 auto", width: "100%" }}>

      {/* ── Header row ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <div style={{
          width: 36, height: 36, borderRadius: "50%", flexShrink: 0,
          background: isPaused ? `${T.purple}15` : `${T.amber}15`,
          border: `2px solid ${isPaused ? T.purple : T.amber}40`,
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16,
          animation: isPaused ? "none" : "pulse 1.5s infinite",
        }}>{isPaused ? "⏸" : "✍️"}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>
            {isPaused ? "Pipeline Paused" : "Generating Article"}
          </div>
          <div style={{ fontSize: 10, color: T.textSoft }}>
            Step {doneCount + (runningStep || pausedStep ? 1 : 0)} of {totalSteps} · {pct}% complete
            {errorCount > 0 && <span style={{ color: "#ef4444", marginLeft: 4 }}>· {errorCount} error{errorCount > 1 ? "s" : ""}</span>}
          </div>
        </div>
        {/* Step-by-Step / Auto toggle */}
        {stepMode === "auto" && !isPaused ? (
          <button onClick={() => pausePipeline.mutate()} disabled={pausePipeline.isPending}
            style={{ fontSize: 9, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.purple}40`, background: `${T.purple}08`, cursor: "pointer", color: T.purple, fontWeight: 600, flexShrink: 0 }}>
            ⏸ Step-by-Step
          </button>
        ) : isPaused ? (
          <button onClick={() => continuePipeline.mutate(true)} disabled={continuePipeline.isPending}
            style={{ fontSize: 9, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.amber}40`, background: `${T.amber}08`, cursor: "pointer", color: T.amber, fontWeight: 600, flexShrink: 0 }}>
            ⏩ Switch to Auto
          </button>
        ) : null}
        <button onClick={() => runHealthCheck(true)} disabled={healthLoading}
          style={{ fontSize: 9, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`, background: "transparent", cursor: "pointer", color: T.textSoft, flexShrink: 0 }}>
          {healthLoading ? "..." : "↻ Health"}
        </button>
      </div>

      {/* ── Progress bar ── */}
      <div style={{ height: 5, background: `${T.gray}12`, borderRadius: 99, overflow: "hidden", marginBottom: 14 }}>
        <div style={{
          height: "100%", borderRadius: 99, width: `${pct}%`,
          background: isPaused ? T.purple : `linear-gradient(90deg, ${T.teal}, ${T.amber})`,
          transition: "width 0.8s ease",
        }} />
      </div>

      {/* ── Health status strip ── */}
      {healthData && (
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 12,
          padding: "5px 8px", borderRadius: 6, background: "#f8fafc", border: `1px solid ${T.border}`,
        }}>
          {Object.entries(healthData).map(([key, info]) => (
            <span key={key} style={{
              fontSize: 9, padding: "2px 6px", borderRadius: 4,
              background: info.status === "ok" ? "#10b98108" : info.status === "rate_limited" ? "#f59e0b08" : "#ef444408",
              color: info.status === "ok" ? "#10b981" : info.status === "rate_limited" ? "#f59e0b" : "#ef4444",
              fontWeight: 600,
            }}>
              {_getProviderLabel(key)} {info.status === "ok" ? "✓" : info.status === "rate_limited" ? "⚠" : "✕"}
            </span>
          ))}
        </div>
      )}

      {/* ── Step cards ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {STEP_DEFS.map(def => {
          const s = steps.find(st => st.step === def.n)
          const isDone = s?.status === "done"
          const isRunning = s?.status === "running"
          const isError = s?.status === "error"
          const isPausedStep = s?.status === "paused"
          const isPending = !s || s.status === "pending"
          const isExpanded = expandedStep === def.n
          const routing = s?.ai_routing || {}
          const stepLogs = logs.filter(l => l.step === def.n)

          const stepAccent = isDone ? T.teal : isRunning ? T.amber : isError ? "#ef4444" : isPausedStep ? T.purple : T.gray

          return (
            <div key={def.n} style={{
              borderRadius: 8, overflow: "hidden",
              background: isPausedStep ? `${T.purple}06` : isDone ? `${T.teal}04` : isRunning ? `${T.amber}05` : isError ? "#ef444405" : "#fafafa",
              border: `1px solid ${isPausedStep ? T.purple + "30" : isDone ? T.teal + "18" : isRunning ? T.amber + "30" : isError ? "#ef444420" : T.border}`,
              opacity: isPending ? 0.35 : 1,
              transition: "all 0.25s ease",
            }}>
              {/* ── Step header (clickable) ── */}
              <div
                onClick={() => !isPending && setExpandedStep(isExpanded ? null : def.n)}
                style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "7px 10px",
                  cursor: isPending ? "default" : "pointer",
                }}
              >
                {/* Number circle */}
                <div style={{
                  width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: isDone || isError ? 10 : 9, fontWeight: 700,
                  background: stepAccent + (isPending ? "20" : ""),
                  ...(isPending ? {} : { background: stepAccent, color: "#fff" }),
                  animation: isRunning ? "pulse 1.2s infinite" : "none",
                }}>
                  {isDone ? "✓" : isRunning ? "⟳" : isError ? "✕" : isPausedStep ? "⏸" : def.n}
                </div>

                {/* Label + desc */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: stepAccent }}>
                      {def.icon} {def.label}
                    </span>
                    {isRunning && <span style={{ fontSize: 7, padding: "1px 4px", borderRadius: 99, background: T.amber, color: "#fff", fontWeight: 700, animation: "pulse 1s infinite" }}>RUNNING</span>}
                    {isPausedStep && <span style={{ fontSize: 7, padding: "1px 4px", borderRadius: 99, background: T.purple, color: "#fff", fontWeight: 700 }}>PAUSED</span>}
                    {isError && <span style={{ fontSize: 7, padding: "1px 4px", borderRadius: 99, background: "#ef4444", color: "#fff", fontWeight: 700 }}>ERROR</span>}
                  </div>
                  {isDone && s?.summary ? (
                    <div style={{ fontSize: 9, color: T.textSoft, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.summary}</div>
                  ) : isError && s?.summary ? (
                    <div style={{ fontSize: 9, color: "#ef4444", marginTop: 1 }}>{s.summary.slice(0, 60)}</div>
                  ) : null}
                </div>

                {/* AI badge on header */}
                {routing.first && routing.first !== "skip" && !isPending && (
                  <span style={{
                    fontSize: 8, padding: "1px 6px", borderRadius: 99, flexShrink: 0,
                    background: `${_getProviderColor(routing.first)}10`,
                    color: _getProviderColor(routing.first),
                    border: `1px solid ${_getProviderColor(routing.first)}25`,
                    fontWeight: 600,
                  }}>{_getProviderLabel(routing.first)}</span>
                )}

                {/* Log count */}
                {stepLogs.length > 0 && (
                  <span style={{ fontSize: 8, color: T.textSoft, flexShrink: 0 }}>
                    {stepLogs.filter(l => l.level === "error").length > 0 && (
                      <span style={{ color: "#ef4444", marginRight: 2 }}>✕{stepLogs.filter(l => l.level === "error").length}</span>
                    )}
                    {stepLogs.length}
                  </span>
                )}

                {!isPending && <span style={{ fontSize: 9, color: T.textSoft }}>{isExpanded ? "▾" : "▸"}</span>}
              </div>

              {/* ── Expanded body ── */}
              {isExpanded && (
                <div style={{ borderTop: `1px solid ${T.border}`, padding: "10px 12px" }}>

                  {/* AI Chain — 3 rows */}
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 9, fontWeight: 700, color: T.textSoft, marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>AI Chain</div>
                    <div style={{ display: "grid", gridTemplateColumns: "54px 1fr", rowGap: 4, alignItems: "center" }}>
                      <span style={{ fontSize: 9, color: T.text, fontWeight: 500 }}>Primary</span>
                      <AISelect value={routing.first} disabled={isDone}
                        providers={aiProviders} healthData={healthData}
                        onChange={v => updateStepAI.mutate({ step: def.n, first: v })} />
                      <span style={{ fontSize: 9, color: T.textSoft }}>Fallback 1</span>
                      <AISelect value={routing.second} disabled={isDone}
                        providers={aiProviders} healthData={healthData}
                        onChange={v => updateStepAI.mutate({ step: def.n, second: v })} />
                      <span style={{ fontSize: 9, color: T.textSoft }}>Fallback 2</span>
                      <AISelect value={routing.third} disabled={isDone}
                        providers={aiProviders} healthData={healthData}
                        onChange={v => updateStepAI.mutate({ step: def.n, third: v })} />
                    </div>
                  </div>

                  {/* Per-step console logs */}
                  {stepLogs.length > 0 && (
                    <div style={{
                      background: "#0f1117", borderRadius: 6, overflow: "hidden",
                      maxHeight: 150, overflowY: "auto", marginBottom: 8,
                      fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
                      fontSize: 9, lineHeight: 1.5,
                    }}>
                      {stepLogs.map((entry, i) => {
                        const ts = entry.ts ? new Date(entry.ts).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }) : ""
                        const level = entry.level || "info"
                        const lColor = { error: "#ef4444", warn: "#f59e0b", warning: "#f59e0b", success: "#10b981", info: "#6b7280" }[level] || "#6b7280"
                        return (
                          <div key={i} style={{
                            padding: "2px 8px", display: "flex", gap: 5,
                            borderLeft: `2px solid ${lColor}`,
                            background: level === "error" ? "#ef44440a" : "transparent",
                          }}>
                            <span style={{ color: "#555", flexShrink: 0, minWidth: 46 }}>{ts}</span>
                            <span style={{ color: level === "error" ? "#fca5a5" : level === "warn" || level === "warning" ? "#fde047" : level === "success" ? "#86efac" : "#9ca3af", wordBreak: "break-word" }}>
                              {entry.msg}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {/* ── Action buttons (BELOW each step) ── */}
                  {isPausedStep && data?.status === "generating" && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", paddingTop: 2 }}>
                      <button onClick={() => continuePipeline.mutate(false)} disabled={continuePipeline.isPending}
                        style={{ fontSize: 10, fontWeight: 600, padding: "5px 14px", borderRadius: 6, border: "none", cursor: "pointer", background: T.teal, color: "#fff" }}>
                        ▶ Continue Step
                      </button>
                      <button onClick={() => continuePipeline.mutate(true)} disabled={continuePipeline.isPending}
                        style={{ fontSize: 10, fontWeight: 600, padding: "5px 14px", borderRadius: 6, border: "none", cursor: "pointer", background: T.amber, color: "#fff" }}>
                        ⏩ Run All
                      </button>
                      <button onClick={() => cancelPipeline.mutate()} disabled={cancelPipeline.isPending}
                        style={{ fontSize: 10, fontWeight: 500, padding: "5px 12px", borderRadius: 6, border: `1px solid #ef444430`, cursor: "pointer", background: "#ef444408", color: "#ef4444" }}>
                        ✕ Cancel
                      </button>
                    </div>
                  )}

                  {(isDone || isError) && data?.status === "generating" && isPaused && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", paddingTop: 2 }}>
                      <button onClick={() => rerunStep.mutate({ step: def.n, step_mode: "pause" })}
                        disabled={rerunStep.isPending}
                        style={{ fontSize: 10, fontWeight: 600, padding: "5px 14px", borderRadius: 6, border: `1px solid ${T.amber}30`, cursor: "pointer", background: `${T.amber}08`, color: T.amber }}>
                        🔄 Re-run from here
                      </button>
                      <button onClick={() => cancelPipeline.mutate()} disabled={cancelPipeline.isPending}
                        style={{ fontSize: 10, fontWeight: 500, padding: "5px 12px", borderRadius: 6, border: `1px solid #ef444430`, cursor: "pointer", background: "#ef444408", color: "#ef4444" }}>
                        ✕ Cancel
                      </button>
                    </div>
                  )}

                  {isPending && (
                    <div style={{ fontSize: 9, color: "#888", fontStyle: "italic" }}>Waiting…</div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ── Rule results ── */}
      {ruleResults && (
        <div style={{
          marginTop: 12, padding: 12, borderRadius: 8,
          background: `${ruleResults.percentage >= 65 ? T.teal : ruleResults.percentage >= 45 ? T.amber : "#dc2626"}06`,
          border: `1px solid ${ruleResults.percentage >= 65 ? T.teal : ruleResults.percentage >= 45 ? T.amber : "#dc2626"}20`,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              fontSize: 22, fontWeight: 700, lineHeight: 1,
              color: ruleResults.percentage >= 65 ? T.teal : ruleResults.percentage >= 45 ? T.amber : "#dc2626",
            }}>{ruleResults.percentage}%</div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.text }}>Rules Compliance</div>
              <div style={{ fontSize: 9, color: T.textSoft }}>
                {ruleResults.summary?.passed_count}/{ruleResults.summary?.total_rules} rules · {ruleResults.total_earned}/{ruleResults.max_possible} pts
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Pipeline Console — real-time log viewer ───────────────────────────────────
const LOG_COLORS = { error: "#dc2626", warn: "#d97706", info: "#6b7280", success: "#16a34a" }
const LOG_BG = { error: "#fef2f2", warn: "#fefce8", info: "transparent", success: "#f0fdf4" }
const LOG_ICONS = { error: "✕", warn: "⚠", info: "·", success: "✓" }

function PipelineConsole({ articleId }) {
  const consoleRef = useRef(null)
  const [expanded, setExpanded] = useState(true)
  const [filter, setFilter] = useState("all") // all | error | warn | success

  // Bug #2 — shared hook
  const { data } = usePipelineQuery(articleId)

  const logs = data?.logs || []
  const filtered = filter === "all" ? logs : logs.filter(l => l.level === filter || (filter === "warn" && l.level === "warning"))
  const errorCount = logs.filter(l => l.level === "error").length
  const warnCount = logs.filter(l => l.level === "warn" || l.level === "warning").length

  // Auto-scroll to bottom
  useEffect(() => {
    if (consoleRef.current && expanded) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight
    }
  }, [filtered.length, expanded])

  return (
    <div style={{
      borderTop: `1px solid ${T.border}`, background: "#0f1117",
      flexShrink: 0, display: "flex", flexDirection: "column",
      maxHeight: expanded ? 280 : 32, minHeight: 32,
      transition: "max-height 0.25s ease",
    }}>
      {/* Console header */}
      <div
        onClick={() => setExpanded(v => !v)}
        style={{
          padding: "6px 14px", display: "flex", alignItems: "center", gap: 8,
          cursor: "pointer", background: "#1a1d27", borderBottom: expanded ? "1px solid #2a2d37" : "none",
          flexShrink: 0,
        }}
      >
        <span style={{ fontSize: 10, fontWeight: 700, color: "#8b8fa3", letterSpacing: 0.5, textTransform: "uppercase" }}>
          Console
        </span>
        {errorCount > 0 && (
          <span style={{ fontSize: 9, fontWeight: 700, color: "#dc2626", background: "#fef2f220", borderRadius: 99, padding: "1px 6px" }}>
            {errorCount} error{errorCount > 1 ? "s" : ""}
          </span>
        )}
        {warnCount > 0 && (
          <span style={{ fontSize: 9, fontWeight: 700, color: "#d97706", background: "#fefce820", borderRadius: 99, padding: "1px 6px" }}>
            {warnCount} warn
          </span>
        )}
        <span style={{ fontSize: 9, color: "#6b7280", marginLeft: "auto" }}>
          {logs.length} entries
        </span>
        <span style={{ fontSize: 10, color: "#6b7280" }}>{expanded ? "▾" : "▴"}</span>
      </div>

      {expanded && (
        <>
          {/* Filter bar */}
          <div style={{ padding: "4px 14px", display: "flex", gap: 4, background: "#15171f", flexShrink: 0 }}>
            {[
              { key: "all", label: "All" },
              { key: "error", label: "Errors", color: "#dc2626" },
              { key: "warn", label: "Warnings", color: "#d97706" },
              { key: "success", label: "Success", color: "#16a34a" },
            ].map(f => (
              <button key={f.key} onClick={() => setFilter(f.key)} style={{
                fontSize: 9, padding: "2px 8px", borderRadius: 4, border: "none", cursor: "pointer",
                background: filter === f.key ? (f.color || "#6b7280") + "30" : "transparent",
                color: filter === f.key ? (f.color || "#e2e8f0") : "#6b7280",
                fontWeight: filter === f.key ? 600 : 400,
              }}>{f.label}</button>
            ))}
          </div>

          {/* Log entries */}
          <div
            ref={consoleRef}
            style={{
              flex: 1, overflowY: "auto", padding: "6px 14px",
              fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
              fontSize: 11, lineHeight: 1.6,
            }}
          >
            {filtered.length === 0 ? (
              <div style={{ color: "#4b5563", padding: "8px 0", fontStyle: "italic" }}>
                {logs.length === 0 ? "Waiting for pipeline events..." : "No matching entries"}
              </div>
            ) : filtered.map((entry, i) => {
              const ts = entry.ts ? new Date(entry.ts).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }) : ""
              const level = entry.level || "info"
              return (
                <div key={i} style={{
                  display: "flex", gap: 8, padding: "1px 0",
                  background: level === "error" ? "#dc26260a" : level === "warn" || level === "warning" ? "#d977060a" : level === "success" ? "#16a34a0a" : "transparent",
                  borderRadius: 2,
                }}>
                  <span style={{ color: "#4b5563", flexShrink: 0, minWidth: 58 }}>{ts}</span>
                  <span style={{ color: LOG_COLORS[level] || "#6b7280", flexShrink: 0, width: 12, textAlign: "center" }}>
                    {LOG_ICONS[level] || "·"}
                  </span>
                  {entry.step > 0 && (
                    <span style={{ color: "#6366f1", flexShrink: 0, minWidth: 20 }}>S{entry.step}</span>
                  )}
                  <span style={{ color: level === "error" ? "#fca5a5" : level === "warn" ? "#fde047" : level === "success" ? "#86efac" : "#9ca3af" }}>
                    {entry.msg}
                  </span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

// ── Full-page Pipeline Logs View (used in editor "Logs" tab) ──────────────────
export function PipelineLogsView({ articleId, storedLogs }) {
  const consoleRef = useRef(null)
  const [filter, setFilter] = useState("all")

  // Bug #2 — shared hook
  const { data } = usePipelineQuery(articleId)

  const pipelineLogs = data?.logs || []
  const allLogs = pipelineLogs.length > 0 ? pipelineLogs : (storedLogs || [])
  const filtered = filter === "all" ? allLogs : allLogs.filter(l => l.level === filter || (filter === "warn" && l.level === "warning"))
  const errorCount = allLogs.filter(l => l.level === "error").length
  const successCount = allLogs.filter(l => l.level === "success").length

  // Final score from pipeline data
  const steps = data?.steps || []
  const scoreStep = steps.find(s => s.step === 10 || s.step === 11)
  const finalScore = scoreStep?.result?.score ?? scoreStep?.result?.percentage ?? null

  useEffect(() => {
    if (consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight
  }, [filtered.length])

  const copyLogs = () => {
    const text = allLogs.map(l => {
      const ts = l.ts ? new Date(l.ts).toLocaleTimeString("en-US", { hour12: false }) : ""
      return `[${ts}] ${l.level?.toUpperCase() || "INFO"} S${l.step || "-"} ${l.msg}`
    }).join("\n")
    navigator.clipboard.writeText(text).catch(() => {})
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, background: "#0f1117", borderRadius: 10, overflow: "hidden" }}>
      {/* Header */}
      <div style={{ padding: "8px 14px", borderBottom: "1px solid #2a2d37", display: "flex", alignItems: "center", gap: 8, background: "#1a1d27", flexShrink: 0 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#e2e8f0" }}>Pipeline Logs</span>
        {finalScore !== null && (
          <span style={{ fontSize: 10, fontWeight: 700,
            color: finalScore >= 75 ? "#10b981" : finalScore >= 50 ? "#f59e0b" : "#ef4444",
            background: finalScore >= 75 ? "#10b98120" : finalScore >= 50 ? "#f59e0b20" : "#ef444420",
            borderRadius: 99, padding: "2px 8px" }}>
            Score: {finalScore}%
          </span>
        )}
        <span style={{ fontSize: 9, color: "#6b7280" }}>{allLogs.length} entries</span>
        {errorCount > 0 && <span style={{ fontSize: 9, fontWeight: 700, color: "#dc2626", background: "#dc262620", borderRadius: 99, padding: "1px 6px" }}>{errorCount} errors</span>}
        <span style={{ flex: 1 }} />
        <button onClick={copyLogs} style={{ fontSize: 9, padding: "3px 8px", borderRadius: 4, border: "1px solid #4b5563", background: "transparent", color: "#9ca3af", cursor: "pointer" }}>
          📋 Copy Logs
        </button>
      </div>
      {/* Filter bar */}
      <div style={{ padding: "4px 14px", display: "flex", gap: 4, background: "#15171f", flexShrink: 0 }}>
        {[
          { key: "all", label: `All (${allLogs.length})` },
          { key: "error", label: `Errors (${errorCount})`, color: "#dc2626" },
          { key: "warn", label: "Warnings", color: "#d97706" },
          { key: "success", label: `Success (${successCount})`, color: "#16a34a" },
        ].map(f => (
          <button key={f.key} onClick={() => setFilter(f.key)} style={{
            fontSize: 9, padding: "2px 8px", borderRadius: 4, border: "none", cursor: "pointer",
            background: filter === f.key ? (f.color || "#6b7280") + "30" : "transparent",
            color: filter === f.key ? (f.color || "#e2e8f0") : "#6b7280",
            fontWeight: filter === f.key ? 600 : 400,
          }}>{f.label}</button>
        ))}
      </div>
      {/* Log entries */}
      <div ref={consoleRef} style={{ flex: 1, overflowY: "auto", padding: "6px 14px", fontFamily: "'JetBrains Mono', 'Fira Code', monospace", fontSize: 11, lineHeight: 1.6 }}>
        {filtered.length === 0 ? (
          <div style={{ color: "#4b5563", padding: "16px 0", textAlign: "center" }}>
            {allLogs.length === 0 ? "No pipeline logs yet — generate an article first" : "No matching entries"}
          </div>
        ) : filtered.map((entry, i) => {
          const ts = entry.ts ? new Date(entry.ts).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }) : ""
          const level = entry.level || "info"
          return (
            <div key={i} style={{ display: "flex", gap: 8, padding: "2px 0", borderBottom: "1px solid #1a1d2780",
              background: level === "error" ? "#dc26260a" : level === "success" ? "#16a34a0a" : "transparent" }}>
              <span style={{ color: "#4b5563", flexShrink: 0, minWidth: 58 }}>{ts}</span>
              <span style={{ color: LOG_COLORS[level] || "#6b7280", flexShrink: 0, width: 12, textAlign: "center" }}>{LOG_ICONS[level] || "·"}</span>
              {entry.step > 0 && <span style={{ color: "#6366f1", flexShrink: 0, minWidth: 20 }}>S{entry.step}</span>}
              <span style={{ color: level === "error" ? "#fca5a5" : level === "warn" ? "#fde047" : level === "success" ? "#86efac" : "#9ca3af", wordBreak: "break-word" }}>
                {entry.msg}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── PipelinePanel — generating view (PipelineProgress + PipelineConsole) ─────
export default function PipelinePanel({ articleId, onComplete }) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "#F2F2F7" }}>
      {/* Pipeline steps */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        <PipelineProgress articleId={articleId} onComplete={onComplete} />
      </div>
      {/* Console log panel */}
      <PipelineConsole articleId={articleId} />
    </div>
  )
}
