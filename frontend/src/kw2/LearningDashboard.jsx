/**
 * LearningDashboard — Phase 12 Real AI Learning Engine UI
 *
 * Sections:
 *  1. Run Learning Pipeline button + status
 *  2. Strategy State (content mix % + cluster priorities)
 *  3. ROI Table (revenue, cost, profit, roi_score, decision badge)
 *  4. Pattern Memory (top patterns per cluster + title type)
 *  5. Decisions Log (scale / kill / optimize with override)
 *  6. Record Performance form (revenue, cost, conversions, etc.)
 */
import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import * as api from "./api"

// ── Theme ──────────────────────────────────────────────────────────────────────
const T = {
  bg:       "#f8fafc",
  card:     "#ffffff",
  border:   "#e2e8f0",
  purple:   "#7c3aed",
  teal:     "#0d9488",
  green:    "#16a34a",
  red:      "#dc2626",
  amber:    "#d97706",
  blue:     "#2563eb",
  text:     "#1e293b",
  soft:     "#64748b",
  scale:    "#16a34a",
  optimize: "#d97706",
  kill:     "#dc2626",
  fade:     "#94a3b8",
  maintain: "#2563eb",
}

const DECISION_COLORS = {
  scale:    { bg: "#dcfce7", color: "#16a34a", label: "🚀 Scale" },
  optimize: { bg: "#fef3c7", color: "#d97706", label: "⚙️ Optimize" },
  kill:     { bg: "#fee2e2", color: "#dc2626", label: "🗑 Kill" },
  fade:     { bg: "#f1f5f9", color: "#64748b", label: "📉 Fade" },
  maintain: { bg: "#dbeafe", color: "#2563eb", label: "✅ Maintain" },
}

function badge(decision) {
  const d = DECISION_COLORS[decision] || DECISION_COLORS.optimize
  return (
    <span style={{
      background: d.bg, color: d.color, fontWeight: 700, fontSize: 11,
      padding: "2px 8px", borderRadius: 12, whiteSpace: "nowrap",
    }}>
      {d.label}
    </span>
  )
}

function Card({ title, children, style = {} }) {
  return (
    <div style={{
      background: T.card, border: `1px solid ${T.border}`, borderRadius: 12,
      padding: "18px 20px", marginBottom: 16, ...style,
    }}>
      {title && <div style={{ fontWeight: 700, fontSize: 14, color: T.text, marginBottom: 12 }}>{title}</div>}
      {children}
    </div>
  )
}

function StatBox({ label, value, color = T.purple, sub = "" }) {
  return (
    <div style={{
      background: T.card, border: `1px solid ${T.border}`, borderRadius: 10,
      padding: "12px 16px", textAlign: "center", minWidth: 100,
    }}>
      <div style={{ fontSize: 22, fontWeight: 800, color }}>{value}</div>
      <div style={{ fontSize: 11, color: T.soft }}>{label}</div>
      {sub && <div style={{ fontSize: 10, color: T.soft, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

// ── Mix bar ────────────────────────────────────────────────────────────────────
const INTENT_COLORS = {
  transactional: "#7c3aed",
  commercial:    "#2563eb",
  informational: "#0d9488",
  navigational:  "#d97706",
}

function ContentMixBar({ mix }) {
  if (!mix || !Object.keys(mix).length) return <div style={{ color: T.soft, fontSize: 12 }}>No data</div>
  const entries = Object.entries(mix).sort((a, b) => b[1] - a[1])
  return (
    <div>
      <div style={{ display: "flex", height: 20, borderRadius: 8, overflow: "hidden", marginBottom: 8 }}>
        {entries.map(([intent, pct]) => (
          <div key={intent} style={{
            width: `${pct * 100}%`,
            background: INTENT_COLORS[intent] || "#94a3b8",
            transition: "width 0.4s",
          }} title={`${intent}: ${(pct * 100).toFixed(0)}%`} />
        ))}
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {entries.map(([intent, pct]) => (
          <div key={intent} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: INTENT_COLORS[intent] || "#94a3b8" }} />
            <span style={{ color: T.soft }}>{intent}</span>
            <span style={{ fontWeight: 700, color: T.text }}>{(pct * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Record Performance Form ────────────────────────────────────────────────────
function RecordPerformanceForm({ projectId, sessionId, titles }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    content_title_id: "",
    tracked_date: new Date().toISOString().slice(0, 10),
    google_position: 0,
    organic_clicks: 0,
    impressions: 0,
    ctr: 0,
    conversions: 0,
    revenue: 0,
    cost: 0,
    bounce_rate: 0,
    time_on_page_seconds: 0,
    data_source: "manual",
  })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState("")

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const num = (k) => (e) => set(k, parseFloat(e.target.value) || 0)
  const int = (k) => (e) => set(k, parseInt(e.target.value) || 0)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.content_title_id) return setMsg("Select a content title first")
    setSaving(true); setMsg("")
    try {
      await api.recordPerformanceV2(projectId, sessionId, form)
      setMsg("✓ Performance recorded")
      qc.invalidateQueries(["learning-roi", projectId, sessionId])
    } catch (err) {
      setMsg("Error: " + err.message)
    } finally {
      setSaving(false)
    }
  }

  const inp = { padding: "5px 10px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12, width: "100%" }

  return (
    <form onSubmit={handleSubmit}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={{ fontSize: 11, color: T.soft }}>Content Title</label>
          <select style={inp} value={form.content_title_id} onChange={e => set("content_title_id", e.target.value)}>
            <option value="">— select title —</option>
            {(titles || []).map(t => (
              <option key={t.id} value={t.id}>{t.title?.slice(0, 70)}</option>
            ))}
          </select>
        </div>
        {[
          ["Date", "tracked_date", "date"],
          ["Position", "google_position", "number"],
          ["Clicks", "organic_clicks", "number"],
          ["Impressions", "impressions", "number"],
          ["CTR (0-1)", "ctr", "number"],
          ["Conversions", "conversions", "number"],
          ["Revenue (₹/$)", "revenue", "number"],
          ["Cost (₹/$)", "cost", "number"],
          ["Bounce Rate (0-1)", "bounce_rate", "number"],
          ["Time on Page (s)", "time_on_page_seconds", "number"],
        ].map(([label, key, type]) => (
          <div key={key}>
            <label style={{ fontSize: 11, color: T.soft }}>{label}</label>
            <input
              type={type}
              step="any"
              style={inp}
              value={form[key]}
              onChange={type === "date"
                ? e => set(key, e.target.value)
                : key.includes("clicks") || key.includes("impressions") || key.includes("conversions") || key.includes("seconds")
                  ? int(key) : num(key)}
            />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <button type="submit" disabled={saving}
          style={{ padding: "7px 18px", borderRadius: 8, border: "none", background: T.purple, color: "#fff", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>
          {saving ? "Saving…" : "Record Performance"}
        </button>
        {msg && <span style={{ fontSize: 12, color: msg.startsWith("✓") ? T.green : T.red }}>{msg}</span>}
      </div>
    </form>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function LearningDashboard({ projectId, sessionId }) {
  const qc = useQueryClient()
  const [runMsg, setRunMsg] = useState(null)
  const [running, setRunning] = useState(false)
  const [overriding, setOverriding] = useState({}) // entity_id → true
  const [activeSection, setActiveSection] = useState("strategy")

  // Data queries
  const { data: stratState, refetch: refetchState } = useQuery({
    queryKey: ["learning-state", projectId, sessionId],
    queryFn: () => api.getLearningStrategyState(projectId, sessionId),
    refetchOnWindowFocus: false,
  })

  const { data: patternsData, refetch: refetchPatterns } = useQuery({
    queryKey: ["learning-patterns", projectId, sessionId],
    queryFn: () => api.getLearningPatterns(projectId, sessionId),
    refetchOnWindowFocus: false,
  })

  const { data: roiData, refetch: refetchROI } = useQuery({
    queryKey: ["learning-roi", projectId, sessionId],
    queryFn: () => api.getLearningROI(projectId, sessionId),
    refetchOnWindowFocus: false,
  })

  const { data: decisionsData, refetch: refetchDecisions } = useQuery({
    queryKey: ["learning-decisions", projectId, sessionId],
    queryFn: () => api.getLearningDecisions(projectId, sessionId),
    refetchOnWindowFocus: false,
  })

  const { data: titlesData } = useQuery({
    queryKey: ["kw2-titles", projectId, sessionId],
    queryFn: () => api.listTitles(projectId, sessionId),
    refetchOnWindowFocus: false,
  })

  const refetchAll = () => {
    refetchState(); refetchPatterns(); refetchROI(); refetchDecisions()
  }

  const handleRunLearning = async () => {
    setRunning(true); setRunMsg(null)
    try {
      const result = await api.runLearning(projectId, sessionId)
      if (result?.ok === false) {
        setRunMsg({ type: "warn", text: result.reason || "Learning skipped" })
      } else {
        setRunMsg({
          type: "success",
          text: `✓ Pipeline complete — ${result.patterns_saved} patterns, ${result.decisions_made} decisions, ${result.expansion_candidates?.length || 0} expand candidates`,
        })
        refetchAll()
      }
    } catch (err) {
      setRunMsg({ type: "error", text: "Error: " + err.message })
    } finally {
      setRunning(false)
    }
  }

  const handleOverride = async (entityId, newDecision) => {
    setOverriding(o => ({ ...o, [entityId]: true }))
    try {
      await api.overrideDecision(projectId, sessionId, {
        entity_id: entityId,
        new_decision: newDecision,
        reason: "Human override",
      })
      refetchDecisions()
    } finally {
      setOverriding(o => ({ ...o, [entityId]: false }))
    }
  }

  const patterns = patternsData?.patterns || []
  const roi = roiData?.items || []
  const roiSummary = roiData?.summary || {}
  const decisions = decisionsData?.decisions || []
  const decisionsSummary = decisionsData?.summary || {}
  const state = stratState || {}
  const contentMix = state.content_mix || {}
  const clusterPriorities = Array.isArray(state.cluster_priorities) ? state.cluster_priorities : []
  const expansionCandidates = Array.isArray(state.expansion_candidates) ? state.expansion_candidates : []
  const roi_summary_state = state.roi_summary || {}
  const titles = titlesData?.titles || []

  const secStyle = (id) => ({
    padding: "5px 14px", borderRadius: 7, border: `1px solid ${T.border}`,
    background: activeSection === id ? T.purple : "transparent",
    color: activeSection === id ? "#fff" : T.soft,
    cursor: "pointer", fontSize: 12, fontWeight: activeSection === id ? 700 : 400,
  })

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>

      {/* Header + Run button */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.text }}>🧠 Learning Engine</div>
          <div style={{ fontSize: 12, color: T.soft, marginTop: 2 }}>
            Data → Pattern Extraction → ROI → Decisions → Strategy
          </div>
        </div>
        <button
          onClick={handleRunLearning}
          disabled={running}
          style={{
            padding: "10px 22px", borderRadius: 9, border: "none",
            background: running ? "#a78bfa" : T.purple,
            color: "#fff", fontWeight: 800, cursor: "pointer", fontSize: 14,
            marginLeft: "auto",
          }}
        >
          {running ? "Running Pipeline…" : "▶ Run Learning Pipeline"}
        </button>
      </div>

      {runMsg && (
        <div style={{
          marginBottom: 16, padding: "10px 16px", borderRadius: 8,
          background: runMsg.type === "success" ? "#dcfce7" : runMsg.type === "warn" ? "#fef3c7" : "#fee2e2",
          color: runMsg.type === "success" ? T.green : runMsg.type === "warn" ? T.amber : T.red,
          fontSize: 13, fontWeight: 600,
        }}>
          {runMsg.text}
        </div>
      )}

      {/* ROI summary stats */}
      {(roi_summary_state.tracked_content > 0 || roiSummary.tracked_content > 0) && (
        <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
          {[
            ["Revenue", `₹${(roi_summary_state.total_revenue || roiSummary.total_revenue || 0).toLocaleString()}`, T.green],
            ["Profit", `₹${(roi_summary_state.total_profit || roiSummary.total_profit || 0).toLocaleString()}`, T.teal],
            ["Avg ROI", `${(roi_summary_state.avg_roi || roiSummary.avg_roi || 0).toFixed(1)}×`, T.purple],
            ["🚀 Scale", roi_summary_state.scale_count ?? roiSummary.scale_count ?? 0, T.green],
            ["⚙️ Optimize", roi_summary_state.optimize_count ?? roiSummary.optimize_count ?? 0, T.amber],
            ["🗑 Kill", roi_summary_state.kill_count ?? roiSummary.kill_count ?? 0, T.red],
          ].map(([label, val, color]) => (
            <StatBox key={label} label={label} value={val} color={color} />
          ))}
        </div>
      )}

      {/* Section nav */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {[["strategy", "📊 Strategy State"], ["roi", "💰 ROI Table"], ["patterns", "🔬 Patterns"], ["decisions", "⚡ Decisions"], ["record", "📥 Record Data"]].map(([id, label]) => (
          <button key={id} style={secStyle(id)} onClick={() => setActiveSection(id)}>{label}</button>
        ))}
      </div>

      {/* ── Strategy State ── */}
      {activeSection === "strategy" && (
        <>
          <Card title="Content Mix (Data-Driven)">
            {Object.keys(contentMix).length ? (
              <ContentMixBar mix={contentMix} />
            ) : (
              <div style={{ color: T.soft, fontSize: 13 }}>Run the learning pipeline to generate a data-driven content mix.</div>
            )}
          </Card>

          <Card title={`Cluster Priorities (${clusterPriorities.length})`}>
            {clusterPriorities.length ? (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: `2px solid ${T.border}` }}>
                    {["Rank", "Cluster", "Score", "Revenue", "Conversions", "Action", "Expand ×"].map(h => (
                      <th key={h} style={{ textAlign: "left", padding: "6px 10px", color: T.soft, fontWeight: 600 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {clusterPriorities.map((c) => (
                    <tr key={c.cluster_name} style={{ borderBottom: `1px solid ${T.border}` }}>
                      <td style={{ padding: "7px 10px", fontWeight: 700, color: T.soft }}>#{c.rank}</td>
                      <td style={{ padding: "7px 10px", fontWeight: 600, color: T.text }}>{c.cluster_name}</td>
                      <td style={{ padding: "7px 10px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <div style={{ width: 50, height: 6, borderRadius: 3, background: T.border }}>
                            <div style={{ width: `${(c.cluster_score * 100).toFixed(0)}%`, height: "100%", borderRadius: 3, background: c.cluster_score > 0.7 ? T.green : c.cluster_score > 0.4 ? T.amber : T.red }} />
                          </div>
                          <span>{(c.cluster_score * 100).toFixed(0)}%</span>
                        </div>
                      </td>
                      <td style={{ padding: "7px 10px" }}>₹{(c.revenue || 0).toLocaleString()}</td>
                      <td style={{ padding: "7px 10px" }}>{c.conversions || 0}</td>
                      <td style={{ padding: "7px 10px" }}>
                        <span style={{
                          padding: "2px 8px", borderRadius: 8, fontSize: 11, fontWeight: 700,
                          background: c.action === "expand" ? "#dcfce7" : c.action === "reduce" ? "#fee2e2" : "#dbeafe",
                          color: c.action === "expand" ? T.green : c.action === "reduce" ? T.red : T.blue,
                        }}>
                          {c.action === "expand" ? "🚀 Expand" : c.action === "reduce" ? "📉 Reduce" : "✅ Maintain"}
                        </span>
                      </td>
                      <td style={{ padding: "7px 10px", fontWeight: 700, color: T.purple }}>{c.expansion_factor}×</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div style={{ color: T.soft, fontSize: 13 }}>Run the learning pipeline to see cluster priorities.</div>
            )}
          </Card>

          {expansionCandidates.length > 0 && (
            <Card title="🔥 Expansion Candidates (High-ROI Clusters to Scale Now)">
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {expansionCandidates.map(c => (
                  <div key={c.cluster_name} style={{
                    background: "#dcfce7", color: T.green, padding: "6px 14px",
                    borderRadius: 20, fontSize: 12, fontWeight: 700,
                  }}>
                    🚀 {c.cluster_name} ({c.expansion_factor}×)
                  </div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}

      {/* ── ROI Table ── */}
      {activeSection === "roi" && (
        <Card title={`ROI Analysis (${roi.length} tracked pieces)`}>
          {roi.length ? (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: `2px solid ${T.border}` }}>
                    {["Title", "Cluster", "Revenue", "Cost", "Profit", "ROI Score", "Conversions", "Avg CTR", "Decision"].map(h => (
                      <th key={h} style={{ textAlign: "left", padding: "6px 8px", color: T.soft, fontWeight: 600, whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {roi.map((item) => {
                    const isScale = item.roi_score > 3
                    const isKill = item.roi_score < 1
                    return (
                      <tr key={item.content_title_id} style={{ borderBottom: `1px solid ${T.border}` }}>
                        <td style={{ padding: "7px 8px", maxWidth: 200 }}>
                          <div style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 180 }} title={item.title}>
                            {item.title}
                          </div>
                          <div style={{ fontSize: 10, color: T.soft }}>{item.intent}</div>
                        </td>
                        <td style={{ padding: "7px 8px", color: T.soft }}>{item.cluster_name}</td>
                        <td style={{ padding: "7px 8px", fontWeight: 600, color: T.green }}>₹{item.total_revenue.toLocaleString()}</td>
                        <td style={{ padding: "7px 8px", color: T.soft }}>₹{item.total_cost.toLocaleString()}</td>
                        <td style={{ padding: "7px 8px", fontWeight: 600, color: item.profit >= 0 ? T.green : T.red }}>
                          {item.profit >= 0 ? "" : "−"}₹{Math.abs(item.profit).toLocaleString()}
                        </td>
                        <td style={{ padding: "7px 8px" }}>
                          <span style={{
                            fontWeight: 800, fontSize: 14,
                            color: isScale ? T.green : isKill ? T.red : T.amber,
                          }}>
                            {item.roi_score.toFixed(1)}×
                          </span>
                        </td>
                        <td style={{ padding: "7px 8px" }}>{item.total_conversions}</td>
                        <td style={{ padding: "7px 8px", color: T.soft }}>{(item.avg_ctr * 100).toFixed(2)}%</td>
                        <td style={{ padding: "7px 8px" }}>
                          {badge(isScale ? "scale" : isKill ? "kill" : "optimize")}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: T.soft, fontSize: 13 }}>No ROI data yet. Record performance metrics and run the learning pipeline.</div>
          )}
        </Card>
      )}

      {/* ── Patterns ── */}
      {activeSection === "patterns" && (
        <Card title={`Pattern Memory (${patterns.length} patterns)`}>
          {patterns.length ? (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: `2px solid ${T.border}` }}>
                    {["Cluster", "Title Type", "Score", "Confidence", "Sample", "Avg CTR", "Avg Conv.", "Avg Revenue", "Best Length", "Best Intent"].map(h => (
                      <th key={h} style={{ textAlign: "left", padding: "6px 8px", color: T.soft, fontWeight: 600, whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {patterns.map((p) => (
                    <tr key={p.id} style={{ borderBottom: `1px solid ${T.border}` }}>
                      <td style={{ padding: "7px 8px", fontWeight: 600, color: T.text }}>{p.cluster_name}</td>
                      <td style={{ padding: "7px 8px" }}>
                        <code style={{ background: "#f1f5f9", padding: "1px 6px", borderRadius: 4, fontSize: 11 }}>{p.title_type}</code>
                      </td>
                      <td style={{ padding: "7px 8px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                          <div style={{ width: 40, height: 6, borderRadius: 3, background: T.border }}>
                            <div style={{ width: `${(p.pattern_score * 100).toFixed(0)}%`, height: "100%", borderRadius: 3, background: T.purple }} />
                          </div>
                          <span style={{ fontWeight: 700, color: T.purple }}>{(p.pattern_score * 100).toFixed(0)}</span>
                        </div>
                      </td>
                      <td style={{ padding: "7px 8px", color: p.confidence > 0.7 ? T.green : p.confidence > 0.4 ? T.amber : T.red }}>
                        {(p.confidence * 100).toFixed(0)}%
                      </td>
                      <td style={{ padding: "7px 8px", color: T.soft }}>{p.sample_size}</td>
                      <td style={{ padding: "7px 8px" }}>{(p.avg_ctr * 100).toFixed(2)}%</td>
                      <td style={{ padding: "7px 8px" }}>{p.avg_conversions?.toFixed(2)}</td>
                      <td style={{ padding: "7px 8px", color: T.green }}>₹{(p.avg_revenue || 0).toLocaleString()}</td>
                      <td style={{ padding: "7px 8px", color: T.soft }}>{p.best_length ? `${p.best_length}w` : "—"}</td>
                      <td style={{ padding: "7px 8px" }}>
                        {p.best_intent && (
                          <span style={{ background: "#f1f5f9", padding: "1px 6px", borderRadius: 4, fontSize: 11, color: INTENT_COLORS[p.best_intent] || T.soft }}>
                            {p.best_intent}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ color: T.soft, fontSize: 13 }}>No patterns extracted yet. Run learning pipeline after recording performance data.</div>
          )}
        </Card>
      )}

      {/* ── Decisions ── */}
      {activeSection === "decisions" && (
        <>
          {/* Summary */}
          {Object.keys(decisionsSummary).length > 0 && (
            <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
              {Object.entries(decisionsSummary).filter(([, v]) => v > 0).map(([k, v]) => {
                const d = DECISION_COLORS[k] || DECISION_COLORS.optimize
                return (
                  <div key={k} style={{ background: d.bg, color: d.color, padding: "8px 16px", borderRadius: 8, fontWeight: 700, fontSize: 13 }}>
                    {d.label} × {v}
                  </div>
                )
              })}
            </div>
          )}

          <Card title={`AI Decisions Log (${decisions.length})`}>
            {decisions.length ? (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: `2px solid ${T.border}` }}>
                      {["Type", "Entity", "Decision", "Reason", "ROI", "Confidence", "Override"].map(h => (
                        <th key={h} style={{ textAlign: "left", padding: "6px 8px", color: T.soft, fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {decisions.map((d) => (
                      <tr key={d.id || d.entity_id} style={{ borderBottom: `1px solid ${T.border}`, opacity: d.overridden ? 0.6 : 1 }}>
                        <td style={{ padding: "7px 8px" }}>
                          <span style={{ fontSize: 10, color: T.soft, textTransform: "uppercase" }}>{d.entity_type}</span>
                        </td>
                        <td style={{ padding: "7px 8px", maxWidth: 200 }}>
                          <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 180 }} title={d.entity_label}>
                            {d.entity_label}
                          </div>
                        </td>
                        <td style={{ padding: "7px 8px" }}>{badge(d.decision)}</td>
                        <td style={{ padding: "7px 8px", color: T.soft, maxWidth: 220, fontSize: 11 }}>{d.reason}</td>
                        <td style={{ padding: "7px 8px", fontWeight: 700, color: d.roi_score > 3 ? T.green : d.roi_score < 1 ? T.red : T.amber }}>
                          {typeof d.roi_score === "number" ? d.roi_score.toFixed(2) : "—"}
                        </td>
                        <td style={{ padding: "7px 8px", color: T.soft }}>{(d.confidence * 100).toFixed(0)}%</td>
                        <td style={{ padding: "7px 8px" }}>
                          {d.overridden ? (
                            <span style={{ fontSize: 10, color: T.soft }}>Overridden</span>
                          ) : (
                            <select
                              disabled={overriding[d.entity_id]}
                              onChange={e => e.target.value && handleOverride(d.entity_id, e.target.value)}
                              defaultValue=""
                              style={{ fontSize: 11, padding: "2px 4px", borderRadius: 4, border: `1px solid ${T.border}` }}
                            >
                              <option value="">Override…</option>
                              {["scale", "optimize", "kill"].filter(x => x !== d.decision).map(x => (
                                <option key={x} value={x}>{x}</option>
                              ))}
                            </select>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div style={{ color: T.soft, fontSize: 13 }}>No decisions yet. Run the learning pipeline after recording performance data.</div>
            )}
          </Card>
        </>
      )}

      {/* ── Record Performance ── */}
      {activeSection === "record" && (
        <Card title="Record Content Performance">
          <div style={{ fontSize: 12, color: T.soft, marginBottom: 14 }}>
            Enter real performance data for published content. Revenue + cost enables the ROI engine.
            Data from GSC, analytics platforms, or order tracking.
          </div>
          <RecordPerformanceForm projectId={projectId} sessionId={sessionId} titles={titles} />
        </Card>
      )}
    </div>
  )
}
