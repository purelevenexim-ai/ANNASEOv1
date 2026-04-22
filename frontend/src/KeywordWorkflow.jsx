// ============================================================================
// ANNASEO — Keyword Workflow Orchestrator  (src/KeywordWorkflow.jsx)
// 3-step linear wizard:
//   1. Setup  → 2. Discovery  → 3. Pipeline (P1-P14)
// After pipeline: confirmed keywords are sent to Strategy Hub (sidebar)
//
// Data flow: WorkflowContext (Zustand) → ctx.step1/2/3
// Session checkpoint: ctx.flush() → DB after each step completion
// ============================================================================

import { useState, useEffect, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import DebugPanel from "./components/DebugPanel"
import useWorkflowContext from "./store/workflowContext"
import { apiCall, T, Card, Btn, Spinner } from "./workflow/shared"

import Step1Setup        from "./workflow/Step1Setup"
import Step2Discovery    from "./workflow/Step2Discovery"
import Step3Pipeline     from "./workflow/Step3Pipeline"

// ─── Steps config ─────────────────────────────────────────────────────────────
const STEPS = [
  { n: 1, label: "Setup",     desc: "Business profile & pillars" },
  { n: 2, label: "Discovery", desc: "Find keywords" },
  { n: 3, label: "Pipeline",  desc: "Process & structure" },
]

// Map backend stage names to step numbers
const STAGE_TO_STEP = {
  input:     1,
  setup:     1,
  research:  2,
  discovery: 2,
  review:    3,
  pipeline:  3,
  clusters:  3,
  strategy:  3,
  calendar:  3,
}

// ─── AI Provider config ──────────────────────────────────────────────────────
const KW_AI_PROVIDERS = [
  { value: "groq",        label: "⚡ Groq",       desc: "Llama 3.3-70b · fastest" },
  { value: "gemini_free", label: "💎 Gemini",     desc: "gemini-2.0-flash · free" },
  { value: "gemini_paid", label: "💎 Gemini Pro", desc: "gemini-pro · paid" },
  { value: "ollama",      label: "🦙 Local",      desc: "mistral-7b · offline" },
  { value: "anthropic",   label: "🧠 Claude",     desc: "claude-sonnet" },
  { value: "openai_paid", label: "🤖 ChatGPT",    desc: "gpt-4o" },
]

function AiProviderPicker({ value, onChange }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, whiteSpace: "nowrap" }}>🤖 AI:</span>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          fontSize: 11, padding: "4px 10px", borderRadius: 7,
          border: `1.5px solid ${T.border}`, background: "#fff",
          cursor: "pointer", fontWeight: 600, color: T.text, minWidth: 160,
        }}
      >
        {KW_AI_PROVIDERS.map(p => (
          <option key={p.value} value={p.value}>{p.label} — {p.desc}</option>
        ))}
      </select>
    </div>
  )
}

// ─── Breadcrumb ────────────────────────────────────────────────────────────────
function StepBreadcrumb({ step, maxReached, onNavigate, aiProvider, onAiChange }) {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: 24, overflowX: "auto", gap: 12 }}>
      <div style={{ flex: 1, display: "flex", alignItems: "center" }}>
      {STEPS.map((s, i) => {
        const done    = s.n < step
        const current = s.n === step
        const canGo   = s.n <= maxReached
        return (
          <div key={s.n} style={{ display: "flex", alignItems: "center", flex: i < STEPS.length - 1 ? 1 : "none" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
              <button
                onClick={() => canGo && onNavigate(s.n)}
                disabled={!canGo}
                style={{
                  width: 34, height: 34, borderRadius: "50%",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 13, fontWeight: 700, border: "none", cursor: canGo ? "pointer" : "default",
                  background: done ? T.teal : current ? T.purple : T.grayLight,
                  color: (done || current) ? "#fff" : T.gray,
                  transition: "background 0.2s",
                }}
              >
                {done ? "✓" : s.n}
              </button>
              <div style={{ marginTop: 4, textAlign: "center" }}>
                <div style={{ fontSize: 11, fontWeight: current ? 700 : 500, color: current ? T.purple : T.text }}>
                  {s.label}
                </div>
                <div style={{ fontSize: 10, color: T.textSoft }}>{s.desc}</div>
              </div>
            </div>
            {i < STEPS.length - 1 && (
              <div style={{
                flex: 1, height: 2, marginBottom: 18, marginLeft: 6, marginRight: 6,
                background: done ? T.teal : T.grayLight, transition: "background 0.3s",
              }}/>
            )}
          </div>
        )
      })}
      </div>
      <div style={{ flexShrink: 0 }}>
        <AiProviderPicker value={aiProvider} onChange={onAiChange} />
      </div>
    </div>
  )
}

// ─── Per-pillar keyword cards ───────────────────────────────────────────────────
function PillarKeywordCards({ projectId }) {
  const [openPillar, setOpenPillar] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ["ki-final-keywords", projectId],
    queryFn:  () => apiCall(`/api/ki/${projectId}/final-keywords`),
    enabled:  !!projectId,
    staleTime: 60_000,
  })

  if (isLoading) return (
    <div style={{ textAlign: "center", padding: 20, color: T.textSoft, fontSize: 13 }}>
      <Spinner /> Loading final keywords…
    </div>
  )

  const pillars = data?.pillars || []
  if (pillars.length === 0) return (
    <div style={{ padding: 16, color: T.textSoft, fontSize: 13, textAlign: "center" }}>
      No accepted keywords yet. Run the pipeline and accept keywords to see results here.
    </div>
  )

  const intentColor = (intent) => {
    const m = { informational: "#3b82f6", transactional: "#10b981", navigational: "#f59e0b", commercial: "#8b5cf6" }
    return m[intent?.toLowerCase()] || "#6b7280"
  }

  return (
    <div style={{ marginTop: 20 }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: T.text }}>
        ✅ Final Confirmed Keywords by Pillar
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {pillars.map(p => {
          const isOpen = openPillar === p.pillar
          return (
            <Card key={p.pillar} style={{ padding: 0, overflow: "hidden" }}>
              {/* Pillar header (always visible, click to expand) */}
              <div
                onClick={() => setOpenPillar(isOpen ? null : p.pillar)}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "12px 16px", cursor: "pointer",
                  background: isOpen ? `${T.teal}12` : "transparent",
                  borderBottom: isOpen ? `1px solid ${T.teal}30` : "none",
                  transition: "background 0.2s",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{
                    width: 8, height: 8, borderRadius: "50%",
                    background: T.teal, flexShrink: 0,
                  }} />
                  <span style={{ fontWeight: 700, fontSize: 14, color: T.text }}>{p.pillar}</span>
                  <span style={{
                    fontSize: 11, fontWeight: 700, color: "#fff",
                    background: T.teal, borderRadius: 10, padding: "1px 8px",
                  }}>{p.count} keywords</span>
                </div>
                <span style={{ fontSize: 16, color: T.textSoft }}>{isOpen ? "▲" : "▼"}</span>
              </div>

              {/* Keyword list (collapsible) */}
              {isOpen && (
                <div style={{ maxHeight: 420, overflowY: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ background: "#f8f9fa", borderBottom: `1px solid ${T.border}` }}>
                        <th style={{ padding: "6px 12px", textAlign: "left", fontWeight: 600, color: T.textSoft, width: 36 }}>#</th>
                        <th style={{ padding: "6px 12px", textAlign: "left", fontWeight: 600, color: T.textSoft }}>Keyword</th>
                        <th style={{ padding: "6px 8px", textAlign: "center", fontWeight: 600, color: T.textSoft, width: 60 }}>Score</th>
                        <th style={{ padding: "6px 8px", textAlign: "center", fontWeight: 600, color: T.textSoft, width: 90 }}>Intent</th>
                        <th style={{ padding: "6px 8px", textAlign: "center", fontWeight: 600, color: T.textSoft, width: 80 }}>Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {p.keywords.map((kw, idx) => (
                        <tr key={kw.keyword + idx} style={{
                          borderBottom: `1px solid ${T.border}`,
                          background: idx % 2 === 0 ? "transparent" : "#fafafa",
                        }}>
                          <td style={{ padding: "5px 12px", color: T.textSoft, textAlign: "center" }}>{idx + 1}</td>
                          <td style={{ padding: "5px 12px", color: T.text, fontWeight: 500 }}>{kw.keyword}</td>
                          <td style={{ padding: "5px 8px", textAlign: "center" }}>
                            <span style={{
                              fontWeight: 700, fontSize: 12,
                              color: (kw.ai_score || 0) >= 70 ? T.green : (kw.ai_score || 0) >= 50 ? T.amber : T.textSoft,
                            }}>{kw.ai_score ? Math.round(kw.ai_score) : "—"}</span>
                          </td>
                          <td style={{ padding: "5px 8px", textAlign: "center" }}>
                            {kw.intent && (
                              <span style={{
                                fontSize: 10, padding: "2px 6px", borderRadius: 8,
                                background: intentColor(kw.intent) + "20",
                                color: intentColor(kw.intent), fontWeight: 600,
                              }}>{kw.intent}</span>
                            )}
                          </td>
                          <td style={{ padding: "5px 8px", textAlign: "center", color: T.textSoft, fontSize: 11 }}>
                            {kw.source || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )
        })}
      </div>
    </div>
  )
}

// ─── Knowledge Graph Visualization ──────────────────────────────────────────
function KnowledgeGraphView({ projectId }) {
  const [expanded, setExpanded] = useState({})
  const [showGraph, setShowGraph] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ["knowledge-graph", projectId],
    queryFn:  () => apiCall(`/api/projects/${projectId}/knowledge-graph`),
    enabled:  !!projectId,
    staleTime: 120_000,
  })

  if (isLoading) return (
    <div style={{ textAlign: "center", padding: 20, color: T.textSoft, fontSize: 13 }}>
      <Spinner /> Loading knowledge graph…
    </div>
  )

  const tree = data
  if (!tree || !tree.children || tree.children.length === 0) return null

  const totalPillars = tree.children.length
  const totalKeywords = tree.total_keywords || tree.children.reduce((sum, p) =>
    sum + (p.children || []).reduce((s2, c) => s2 + (c.children || []).length, 0), 0)

  const intentIcon = (intent) => {
    const m = { transactional: "💰", commercial: "📊", informational: "📖", local: "📍", navigational: "🔗" }
    return m[intent] || "🔑"
  }

  const togglePillar = (idx) => setExpanded(prev => ({ ...prev, [idx]: !prev[idx] }))

  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>
          🌐 Knowledge Graph
        </div>
        <button
          onClick={() => setShowGraph(!showGraph)}
          style={{
            padding: "4px 12px", borderRadius: 6, border: `1px solid ${T.border}`,
            background: showGraph ? T.purple : "transparent",
            color: showGraph ? "#fff" : T.text, cursor: "pointer", fontSize: 12, fontWeight: 600,
          }}
        >
          {showGraph ? "Hide Graph" : "Show Graph"}
        </button>
      </div>

      {/* Summary stats */}
      <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
        <Card style={{ padding: "8px 14px", textAlign: "center", flex: 1 }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.purple }}>{totalPillars}</div>
          <div style={{ fontSize: 10, color: T.textSoft, textTransform: "uppercase" }}>Pillars</div>
        </Card>
        <Card style={{ padding: "8px 14px", textAlign: "center", flex: 1 }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.teal }}>{totalKeywords}</div>
          <div style={{ fontSize: 10, color: T.textSoft, textTransform: "uppercase" }}>Keywords</div>
        </Card>
        <Card style={{ padding: "8px 14px", textAlign: "center", flex: 1 }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.amber }}>
            {tree.children.reduce((sum, p) => sum + (p.children || []).length, 0)}
          </div>
          <div style={{ fontSize: 10, color: T.textSoft, textTransform: "uppercase" }}>Clusters</div>
        </Card>
      </div>

      {showGraph && (
        <Card style={{ padding: 16, marginBottom: 16, background: "#fafbfc" }}>
          {/* Tree view */}
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10, color: T.text }}>
            📌 {tree.name}
          </div>
          {tree.children.map((pillar, pi) => {
            const isOpen = expanded[pi]
            const clusterCount = (pillar.children || []).length
            const kwCount = (pillar.children || []).reduce((s, c) => s + (c.children || []).length, 0)
            return (
              <div key={pi} style={{ marginBottom: 6 }}>
                <div
                  onClick={() => togglePillar(pi)}
                  style={{
                    display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
                    background: isOpen ? `${T.purple}12` : "#fff",
                    border: `1px solid ${isOpen ? T.purple + "40" : T.border}`,
                    borderRadius: 8, cursor: "pointer", transition: "all 0.2s",
                  }}
                >
                  <span style={{ fontSize: 14 }}>🏛️</span>
                  <span style={{ fontWeight: 700, fontSize: 13, color: T.text, flex: 1 }}>
                    {pillar.name || pillar.keyword}
                  </span>
                  <span style={{
                    fontSize: 10, padding: "2px 8px", borderRadius: 8,
                    background: T.purple + "20", color: T.purple, fontWeight: 600,
                  }}>
                    {clusterCount} clusters · {kwCount} kw
                  </span>
                  <span style={{ fontSize: 12, color: T.textSoft }}>{isOpen ? "▲" : "▼"}</span>
                </div>
                {isOpen && (pillar.children || []).map((cluster, ci) => (
                  <div key={ci} style={{ marginLeft: 24, marginTop: 4 }}>
                    <div style={{
                      fontSize: 12, fontWeight: 600, color: T.teal, padding: "4px 8px",
                      borderLeft: `3px solid ${T.teal}`, background: `${T.teal}08`,
                      borderRadius: "0 6px 6px 0", marginBottom: 2,
                    }}>
                      📂 {cluster.name} ({(cluster.children || []).length} topics)
                    </div>
                    {(cluster.children || []).map((topic, ti) => (
                      <div key={ti} style={{
                        marginLeft: 20, padding: "3px 8px", fontSize: 11,
                        color: T.text, display: "flex", alignItems: "center", gap: 6,
                      }}>
                        <span>{intentIcon(topic.intent)}</span>
                        <span style={{ fontWeight: 500 }}>{topic.name || topic.topic}</span>
                        {topic.intent && (
                          <span style={{
                            fontSize: 9, padding: "1px 5px", borderRadius: 6,
                            background: T.textSoft + "20", color: T.textSoft,
                          }}>{topic.intent}</span>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )
          })}
        </Card>
      )}
    </div>
  )
}

// ─── Send Confirmed Keywords to Strategy Hub ────────────────────────────────
function SendToStrategyHub({ projectId, onGoToStrategy }) {
  const qc = useQueryClient()
  const [sending, setSending] = useState(false)
  const [sent, setSent]       = useState(false)
  const [error, setError]     = useState(null)
  const [logs, setLogs]       = useState([])

  // Check if already sent
  const { data: briefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn:  () => apiCall(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled:  !!projectId,
    staleTime: 60_000,
  })
  const alreadySent = !!(briefData?.brief && !briefData?.error)

  const handleSend = useCallback(async () => {
    setSending(true)
    setError(null)
    setLogs(["Collecting confirmed keywords…"])

    try {
      const res = await apiCall(`/api/ki/${projectId}/send-to-strategy`, "POST")
      if (res?.success) {
        setLogs(prev => [
          ...prev,
          `✅ Sent ${res.total_keywords} keywords across ${res.pillar_count} pillars`,
          "🤖 Generating AI pillar summary…",
          "✅ Pillar summary ready",
          "📤 Strategy Hub updated",
        ])
        setSent(true)
        qc.invalidateQueries(["kw-strategy-brief", projectId])
      } else {
        setError(res?.error || res?.detail || "Failed to send keywords")
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setSending(false)
    }
  }, [projectId, qc])

  if (alreadySent || sent) {
    return (
      <Card style={{
        marginTop: 20, padding: "14px 18px",
        background: `linear-gradient(135deg, ${T.teal}10, ${T.purple}08)`,
        border: `1px solid ${T.teal}40`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 22 }}>✅</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: T.text }}>
              Keywords sent to Strategy Hub
            </div>
            <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
              {briefData?.total_keywords
                ? `${briefData.total_keywords} keywords across ${briefData.pillar_count} pillars with AI summary`
                : "Confirmed keywords & AI pillar summary available in Strategy Hub"}
            </div>
          </div>
          <Btn variant="teal" small onClick={onGoToStrategy}>
            Go to Strategy Hub →
          </Btn>
          <Btn small onClick={handleSend} disabled={sending}>
            {sending ? "Updating…" : "↺ Re-sync"}
          </Btn>
        </div>
        {briefData?.sent_at && (
          <div style={{ fontSize: 10, color: T.textSoft, marginTop: 6 }}>
            Last synced: {new Date(briefData.sent_at).toLocaleString()}
          </div>
        )}
      </Card>
    )
  }

  return (
    <Card style={{ marginTop: 20, padding: "16px 18px", border: `1px solid ${T.purple}30` }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
        <span style={{ fontSize: 24, marginTop: 2 }}>🚀</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: T.text, marginBottom: 4 }}>
            Send to Strategy Hub
          </div>
          <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 10, lineHeight: 1.5 }}>
            Push your confirmed keywords, pillar structure, business context, and an AI-generated
            ~1000-word pillar brief to the Strategy Hub for AI planning and content strategy.
          </div>

          {logs.length > 0 && (
            <div style={{
              background: "#f8f9fa", borderRadius: 8, padding: "8px 12px",
              marginBottom: 10, fontFamily: "monospace", fontSize: 11,
              maxHeight: 100, overflowY: "auto",
            }}>
              {logs.map((l, i) => (
                <div key={i} style={{ color: l.startsWith("✅") ? T.teal : l.startsWith("🤖") ? T.purple : T.textSoft }}>
                  {l}
                </div>
              ))}
            </div>
          )}

          {error && (
            <div style={{
              color: T.red, fontSize: 12, marginBottom: 8,
              padding: "6px 10px", background: "#fff0f0", borderRadius: 6,
            }}>
              ⚠ {error}
            </div>
          )}
        </div>

        <Btn
          variant="primary"
          onClick={handleSend}
          loading={sending}
          disabled={sending}
          style={{ flexShrink: 0, minWidth: 140 }}
        >
          {sending ? "Sending…" : "📤 Send to Strategy"}
        </Btn>
      </div>
    </Card>
  )
}

// ─── Dashboard (shown when project already has keywords) ───────────────────────
function KeywordDashboard({ projectId, onGoToStep, onStartFresh, onBack, onGoToStrategy, onGoToContent }) {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["ki-dashboard", projectId],
    queryFn:  () => apiCall(`/api/ki/${projectId}/dashboard`),
    enabled:  !!projectId,
  })

  if (isLoading) return (
    <div style={{ textAlign: "center", padding: 40, color: T.textSoft }}>
      <Spinner />
      <div style={{ fontSize: 13, marginTop: 10 }}>Loading keyword intelligence…</div>
    </div>
  )
  if (!data?.has_keywords) return null

  const { stats, session_id, session_created, stage } = data
  const stageStep = STAGE_TO_STEP[stage] || 2
  const isComplete = (stats.accepted || 0) > 0

  return (
    <div>
      {/* Workflow complete banner — shown when keywords are accepted */}
      {isComplete ? (
        <Card style={{ marginBottom: 14, background: `linear-gradient(135deg, #ecfdf5, #f0fdf4)`, border: `1.5px solid #6ee7b7` }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: T.teal, marginBottom: 2 }}>
                ✓ Keyword Research Complete
              </div>
              <div style={{ fontSize: 12, color: T.textSoft }}>
                {stats.accepted} keywords accepted · Ready for content creation
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {onGoToContent && (
                <button
                  onClick={onGoToContent}
                  style={{
                    padding: "8px 18px", borderRadius: 8, border: "none",
                    background: T.teal, color: "#fff", cursor: "pointer",
                    fontSize: 13, fontWeight: 600, transition: "opacity 0.2s",
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.opacity = "0.85"}
                  onMouseLeave={(e) => e.currentTarget.style.opacity = "1"}
                >
                  → Go to Content
                </button>
              )}
              {onGoToStrategy && (
                <Btn small onClick={onGoToStrategy}>Strategy Hub</Btn>
              )}
            </div>
          </div>
        </Card>
      ) : (
        // In-progress top bar
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <button
            onClick={() => onGoToStep(stageStep, session_id)}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "6px 12px", borderRadius: 7, border: `1px solid ${T.border}`,
              background: T.teal, color: "#fff", cursor: "pointer", fontSize: 13,
              fontWeight: 500, transition: "opacity 0.2s",
            }}
            onMouseEnter={(e) => e.currentTarget.style.opacity = "0.9"}
            onMouseLeave={(e) => e.currentTarget.style.opacity = "1"}
          >
            ← Continue Pipeline
          </button>
          <div style={{ flex: 1 }} />
          <Btn small onClick={() => refetch()}>⟳ Refresh</Btn>
          <Btn small onClick={onStartFresh}>+ New Session</Btn>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: T.text }}>Keyword Overview</div>
        <div style={{ display: "flex", gap: 6 }}>
          <Btn small onClick={() => refetch()}>⟳ Refresh</Btn>
          <Btn small onClick={onStartFresh}>+ New Session</Btn>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 8, marginBottom: 14 }}>
        {[
          { label: "Total",     val: stats.total    || 0, color: T.text },
          { label: "Pending",   val: stats.pending  || 0, color: T.amber },
          { label: "Accepted",  val: stats.accepted || 0, color: T.green },
          { label: "Rejected",  val: stats.rejected || 0, color: T.red },
          { label: "Quick Wins",val: stats.quick_wins || 0, color: T.teal },
        ].map(s => (
          <Card key={s.label} style={{ padding: "10px 12px", textAlign: "center" }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.val}</div>
            <div style={{ fontSize: 9, color: T.textSoft, marginTop: 3, textTransform: "uppercase", letterSpacing: ".06em" }}>{s.label}</div>
          </Card>
        ))}
      </div>

      {!isComplete && (
        <div style={{ display: "flex", gap: 8, marginBottom: 4 }}>
          <Btn variant="teal" onClick={() => onGoToStep(stageStep, session_id)}>
            Continue from {stage || "where I left off"} →
          </Btn>
          <Btn onClick={onStartFresh}>Start New Session</Btn>
        </div>
      )}

      {/* Per-pillar accepted keyword cards */}
      <PillarKeywordCards projectId={projectId} />

      {/* Send to Strategy Hub */}
      <SendToStrategyHub projectId={projectId} onGoToStrategy={onGoToStrategy} />

      {/* Knowledge Graph / System Graph visualization */}
      <KnowledgeGraphView projectId={projectId} />
    </div>
  )
}

// ─── Main Orchestrator ─────────────────────────────────────────────────────────
export default function KeywordWorkflow({ projectId, onGoToCalendar, setPage }) {
  const ctx = useWorkflowContext()
  const [step, setStep]               = useState(1)
  const [maxReached, setMaxReached]   = useState(1)
  const [skipDashboard, setSkipDashboard] = useState(false)
  const [aiProvider, setAiProvider]   = useState("groq")

  // Dashboard check
  const { data: dashData, isLoading: dashLoading } = useQuery({
    queryKey: ["ki-dashboard", projectId],
    queryFn:  () => apiCall(`/api/ki/${projectId}/dashboard`),
    enabled:  !!projectId,
    staleTime: 30_000,
  })

  // Restore session on mount
  useEffect(() => {
    if (!projectId) return
    if (ctx.sessionId) return

    apiCall(`/api/ki/${projectId}/latest-session`).then(session => {
      if (session?.session_id) {
        ctx.loadFromSession(projectId, session.session_id).then(() => {
          const s = STAGE_TO_STEP[session.stage] || 1
          setStep(s)
          setMaxReached(s)
        })
      }
    }).catch(() => {})
  }, [projectId])

  const navigateTo = (n) => {
    setStep(n)
  }

  const advanceStep = () => {
    const next = step + 1
    setStep(next)
    setMaxReached(prev => Math.max(prev, next))
    apiCall(`/api/ki/${projectId}/workflow/advance`, "POST").catch(() => {})
  }

  const handleStep1Done = ({ sessionId }) => {
    if (sessionId && !ctx.sessionId) ctx.setSession(sessionId)
    advanceStep()
  }

  const showDashboard = !skipDashboard && step === 1 && dashData?.has_keywords === true

  if (dashLoading && step === 1 && !skipDashboard) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: 40, textAlign: "center" }}>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <Spinner />
        <div style={{ fontSize: 13, marginTop: 12, color: T.textSoft }}>Loading…</div>
      </div>
    )
  }

  if (showDashboard) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <KeywordDashboard
          projectId={projectId}
          onGoToStep={(s, sid) => {
            if (sid) ctx.loadFromSession(projectId, sid)
            setStep(s)
            setMaxReached(prev => Math.max(prev, s))
          }}
          onStartFresh={() => {
            ctx.reset()
            setStep(1)
            setMaxReached(1)
            setSkipDashboard(true)
          }}
          onBack={() => {
            setSkipDashboard(true)
          }}
          onGoToStrategy={() => setPage && setPage("strategy-hub")}
          onGoToContent={() => setPage && setPage("content")}
        />
        <DebugPanel />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <StepBreadcrumb
        step={step}
        maxReached={maxReached}
        onNavigate={navigateTo}
        aiProvider={aiProvider}
        onAiChange={setAiProvider}
      />

      {step === 1 && (
        <Step1Setup
          projectId={projectId}
          onComplete={handleStep1Done}
          aiProvider={aiProvider}
        />
      )}
      {step === 2 && (
        <Step2Discovery
          projectId={projectId}
          onComplete={advanceStep}
          onBack={() => setStep(1)}
          aiProvider={aiProvider}
        />
      )}
      {step === 3 && (
        <Step3Pipeline
          projectId={projectId}
          onComplete={() => {
            // Pipeline done — go back to dashboard which shows confirmed results
            setSkipDashboard(false)
            setStep(1)
          }}
          onBack={() => setStep(2)}
          aiProvider={aiProvider}
        />
      )}

      <DebugPanel />
    </div>
  )
}
