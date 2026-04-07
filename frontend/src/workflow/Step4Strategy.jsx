// Step 4 — Strategy & Review (Post-Pipeline)
// Two substeps:
//   A: Generate Strategy — SSE stream using real pipeline output
//   B: Review & Approve — tabbed strategy review + keyword acceptance
// Uses: POST /api/ki/{project_id}/post-pipeline-strategy

import { useState, useEffect, useRef, useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNotification } from "../store/notification"
import useWorkflowContext from "../store/workflowContext"
import { apiCall, API, T, Card, Btn, Spinner, Badge, LiveConsole } from "./shared"

function authHeaders() {
  const t = localStorage.getItem("annaseo_token")
  return t ? { Authorization: `Bearer ${t}` } : {}
}

// ─── Sub-step indicator ─────────────────────────────────────────────────────
function SubStepBar({ current, onNavigate }) {
  const steps = [
    { n: 1, label: "Generate Strategy" },
    { n: 2, label: "Review & Approve" },
  ]
  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
      {steps.map(s => (
        <button key={s.n}
          onClick={() => s.n <= current && onNavigate(s.n)}
          style={{
            padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 600,
            border: `1.5px solid ${s.n === current ? T.purple : s.n < current ? T.teal : T.border}`,
            background: s.n === current ? T.purpleLight : s.n < current ? T.tealLight : "#fff",
            color: s.n === current ? T.purple : s.n < current ? T.teal : T.textSoft,
            cursor: s.n <= current ? "pointer" : "default",
          }}>
          {s.n < current ? "✓ " : ""}{s.label}
        </button>
      ))}
    </div>
  )
}

// ─── Generate Sub-step ──────────────────────────────────────────────────────
function GenerateSubStep({ projectId, onComplete, existingStrategy }) {
  const notify = useNotification(s => s.notify)
  const ctx = useWorkflowContext()

  const [generating, setGenerating] = useState(false)
  const [logs, setLogs]             = useState([])
  const [strategy, setStrategy]     = useState(null)
  const [pipelineSummary, setPipelineSummary] = useState(null)
  const eventSourceRef = useRef(null)

  // Load completed run IDs
  const { data: runsData } = useQuery({
    queryKey: ["ki-completed-runs", projectId],
    queryFn: async () => {
      const db = await apiCall(`/api/ki/${projectId}/pipeline-runs`)
      return db?.runs || []
    },
    enabled: !!projectId,
    retry: false,
  })

  // Try loading from ctx first
  const ctxRuns = ctx.step3?.runs || []
  const runIds = ctxRuns.length > 0 ? ctxRuns : (runsData || []).filter(r => r.status === "complete" || r.status === "warning").map(r => r.run_id)

  const generate = async () => {
    if (runIds.length === 0) {
      notify("No completed pipeline runs found", "warn")
      return
    }
    setGenerating(true)
    setLogs([])
    setStrategy(null)

    try {
      const resp = await fetch(`${API}/api/ki/${projectId}/post-pipeline-strategy`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ run_ids: runIds, session_id: ctx.sessionId || "" }),
      })

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split("\n")
        buffer = lines.pop() // Keep incomplete line

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === "log") {
              setLogs(prev => [...prev, { msg: data.msg, level: data.level || "info" }])
            }
            if (data.type === "complete") {
              setStrategy(data.strategy)
              setPipelineSummary(data.pipeline_summary)
              ctx.setStep(4, { strategy: data.strategy, ai_source: data.ai_source })
              ctx.flush(projectId)
            }
          } catch (e) {}
        }
      }
    } catch (e) {
      setLogs(prev => [...prev, { msg: `Error: ${e.message}`, level: "error" }])
    }
    setGenerating(false)
  }

  // Auto-advance when strategy is ready
  useEffect(() => {
    if (strategy) {
      onComplete(strategy)
    }
  }, [strategy])

  return (
    <Card>
      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>
        Generate Strategy from Pipeline Data
      </div>
      <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 16 }}>
        AI will analyze your pipeline results — pillars, clusters, topics, calendar — and generate a comprehensive SEO + AEO strategy.
      </div>

      {/* Pipeline summary */}
      {runIds.length > 0 && (
        <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
          <Badge color={T.teal}>{runIds.length} pipeline runs</Badge>
        </div>
      )}

      {pipelineSummary && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))", gap: 8, marginBottom: 16 }}>
          {[
            { label: "Keywords", val: pipelineSummary.total_keywords },
            { label: "Pillars", val: pipelineSummary.pillars },
            { label: "Clusters", val: pipelineSummary.clusters },
            { label: "Topics", val: pipelineSummary.topics },
          ].map(s => (
            <div key={s.label} style={{ textAlign: "center", padding: 8, background: T.grayLight, borderRadius: 8 }}>
              <div style={{ fontSize: 18, fontWeight: 800 }}>{s.val || 0}</div>
              <div style={{ fontSize: 9, color: T.textSoft, textTransform: "uppercase" }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <Btn variant="primary" onClick={generate} disabled={generating || runIds.length === 0}>
          {generating ? <><Spinner /> Generating Strategy…</> : existingStrategy ? "🔄 Re-generate Strategy" : "🧠 Generate Strategy"}
        </Btn>
        {existingStrategy && !generating && (
          <span style={{ fontSize: 11, color: T.textSoft }}>A strategy already exists — re-generate to overwrite</span>
        )}
      </div>

      {logs.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <LiveConsole logs={logs} running={generating} maxHeight={200} title="STRATEGY GENERATION" />
        </div>
      )}
    </Card>
  )
}

// ─── Review Sub-step ────────────────────────────────────────────────────────
function ReviewSubStep({ projectId, strategy: initialStrategy, onGoToCalendar, onRerun }) {
  const notify = useNotification(s => s.notify)
  const [activeTab, setActiveTab] = useState("overview")
  const [strategy, setStrategy] = useState(initialStrategy)
  const [editMode, setEditMode] = useState(false)
  const [saving, setSaving] = useState(false)

  // Sync when parent updates strategy (after re-run)
  useEffect(() => { setStrategy(initialStrategy) }, [initialStrategy])

  if (!strategy) return null

  const save = async () => {
    setSaving(true)
    try {
      await apiCall(`/api/ki/${projectId}/strategy`, "PUT", { strategy })
      notify("Strategy saved", "success")
      setEditMode(false)
    } catch (e) {
      notify(`Save failed: ${e.message}`, "error")
    }
    setSaving(false)
  }

  const tabs = [
    { id: "overview",  label: "Overview" },
    { id: "pillars",   label: "Pillars" },
    { id: "seo",       label: "SEO" },
    { id: "aeo",       label: "AEO" },
    { id: "plan",      label: "90-Day Plan" },
  ]

  return (
    <div>
      {/* Tab bar + action buttons */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, borderBottom: `1px solid ${T.border}`, paddingBottom: 8 }}>
        <div style={{ display: "flex", gap: 4 }}>
          {tabs.map(tab => (
            <button key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: "6px 14px", borderRadius: "8px 8px 0 0", fontSize: 12, fontWeight: 600,
                border: "none", cursor: "pointer",
                background: activeTab === tab.id ? T.purpleLight : "transparent",
                color: activeTab === tab.id ? T.purple : T.textSoft,
                borderBottom: activeTab === tab.id ? `2px solid ${T.purple}` : "2px solid transparent",
              }}>
              {tab.label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {editMode ? (
            <>
              <Btn small onClick={() => setEditMode(false)}>Cancel</Btn>
              <Btn small variant="primary" onClick={save} disabled={saving}>
                {saving ? <><Spinner /> Saving…</> : "💾 Save"}
              </Btn>
            </>
          ) : (
            <>
              <Btn small onClick={() => setEditMode(true)}>✏️ Edit</Btn>
              {onRerun && <Btn small onClick={onRerun}>🔄 Re-generate</Btn>}
            </>
          )}
        </div>
      </div>

      {/* Tab content */}
      {activeTab === "overview" && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>Executive Summary</div>
          {editMode ? (
            <textarea
              value={strategy.executive_summary || ""}
              onChange={e => setStrategy(s => ({ ...s, executive_summary: e.target.value }))}
              style={{
                width: "100%", minHeight: 120, padding: "8px 10px", fontSize: 13, lineHeight: 1.6,
                border: `1.5px solid ${T.purple}`, borderRadius: 8, resize: "vertical",
                fontFamily: "inherit", color: T.text,
              }}
            />
          ) : (
            <p style={{ fontSize: 13, lineHeight: 1.6, color: T.text }}>
              {strategy.executive_summary || "No summary available."}
            </p>
          )}

          {strategy.content_strategy?.content_mix && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Content Mix</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {Object.entries(strategy.content_strategy.content_mix).map(([intent, pct]) => (
                  <div key={intent} style={{
                    padding: "6px 12px", borderRadius: 8, background: T.grayLight,
                    fontSize: 11,
                  }}>
                    <strong>{intent}</strong>: {editMode ? (
                      <input
                        type="number" min={0} max={100}
                        value={pct}
                        onChange={e => setStrategy(s => ({
                          ...s,
                          content_strategy: {
                            ...s.content_strategy,
                            content_mix: { ...s.content_strategy.content_mix, [intent]: Number(e.target.value) }
                          }
                        }))}
                        style={{ width: 40, border: "none", background: "transparent", fontWeight: 700, textAlign: "center" }}
                      />
                    ) : `${pct}%`}
                  </div>
                ))}
              </div>
            </div>
          )}

          {strategy.content_strategy?.content_calendar_strategy && (
            <div style={{ marginTop: 12, fontSize: 12, color: T.textSoft }}>
              <strong>Calendar:</strong>{" "}
              {editMode ? (
                <input
                  value={strategy.content_strategy.content_calendar_strategy}
                  onChange={e => setStrategy(s => ({
                    ...s,
                    content_strategy: { ...s.content_strategy, content_calendar_strategy: e.target.value }
                  }))}
                  style={{ width: "90%", border: `1px solid ${T.border}`, borderRadius: 6, padding: "2px 6px", fontSize: 12 }}
                />
              ) : strategy.content_strategy.content_calendar_strategy}
            </div>
          )}
        </Card>
      )}

      {activeTab === "pillars" && (
        <div>
          {(strategy.content_strategy?.pillar_plan || []).map((pillar, i) => (
            <Card key={i} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 14, fontWeight: 700 }}>{pillar.pillar}</span>
                <Badge color={pillar.priority === "high" ? T.red : pillar.priority === "medium" ? T.amber : T.green}>
                  {pillar.priority}
                </Badge>
                <Badge color={T.teal}>{pillar.estimated_articles || "?"} articles</Badge>
              </div>
              <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 4 }}>
                Intent: {pillar.target_intent} · Types: {(pillar.content_types || []).join(", ")}
              </div>
              {pillar.quick_wins?.length > 0 && (
                <div style={{ fontSize: 11, color: T.teal }}>
                  Quick wins: {pillar.quick_wins.join(", ")}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      {activeTab === "seo" && (
        <div>
          {(strategy.seo_recommendations || []).map((rec, i) => (
            <Card key={i} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>{rec.area}</span>
                <Badge color={rec.priority === "high" ? T.red : T.amber}>{rec.priority}</Badge>
              </div>
              <div style={{ fontSize: 12, marginBottom: 4 }}>
                {editMode ? (
                  <textarea
                    value={rec.action}
                    onChange={e => {
                      const recs = [...(strategy.seo_recommendations || [])]
                      recs[i] = { ...recs[i], action: e.target.value }
                      setStrategy(s => ({ ...s, seo_recommendations: recs }))
                    }}
                    style={{ width: "100%", minHeight: 60, padding: "4px 8px", fontSize: 12, border: `1px solid ${T.border}`, borderRadius: 6, resize: "vertical", fontFamily: "inherit" }}
                  />
                ) : rec.action}
              </div>
              <div style={{ fontSize: 11, color: T.textSoft }}>Impact: {rec.impact}</div>
            </Card>
          ))}
          {strategy.competitor_gaps?.length > 0 && (
            <Card style={{ marginTop: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Competitor Gaps</div>
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12 }}>
                {strategy.competitor_gaps.map((gap, i) => <li key={i}>{gap}</li>)}
              </ul>
            </Card>
          )}
        </div>
      )}

      {activeTab === "aeo" && strategy.aeo_strategy && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>AI Engine Optimization (AEO)</div>

          {strategy.aeo_strategy.ai_visibility_targets?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>AI Visibility Targets</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {strategy.aeo_strategy.ai_visibility_targets.map((t, i) => (
                  <Badge key={i} color={T.purple}>{t}</Badge>
                ))}
              </div>
            </div>
          )}

          {strategy.aeo_strategy.structured_data_plan?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Structured Data Plan</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {strategy.aeo_strategy.structured_data_plan.map((s, i) => (
                  <Badge key={i} color={T.teal}>{s}</Badge>
                ))}
              </div>
            </div>
          )}

          {strategy.aeo_strategy.featured_snippet_targets?.length > 0 && (
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Featured Snippet Targets</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {strategy.aeo_strategy.featured_snippet_targets.map((t, i) => (
                  <Badge key={i} color={T.amber}>{t}</Badge>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {activeTab === "plan" && (
        <div>
          {(strategy["90_day_plan"] || []).map((month, i) => (
            <Card key={i} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: "50%", display: "flex",
                  alignItems: "center", justifyContent: "center",
                  background: T.purpleLight, color: T.purple, fontSize: 12, fontWeight: 700,
                }}>
                  {month.month}
                </div>
                <span style={{ fontSize: 14, fontWeight: 700 }}>{month.focus}</span>
              </div>
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12 }}>
                {(month.deliverables || []).map((d, j) => <li key={j}>{d}</li>)}
              </ul>
            </Card>
          ))}
        </div>
      )}

      {/* Bottom actions */}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
        {editMode && (
          <Btn variant="primary" onClick={save} disabled={saving}>
            {saving ? <><Spinner /> Saving…</> : "💾 Save Changes"}
          </Btn>
        )}
        {onGoToCalendar && (
          <Btn variant="teal" onClick={onGoToCalendar}>
            View Content Calendar →
          </Btn>
        )}
      </div>
    </div>
  )
}

// ─── Main Component ──────────────────────────────────────────────────────────
export default function Step4Strategy({ projectId, onBack, onGoToCalendar }) {
  const ctx = useWorkflowContext()
  const [sub, setSub]           = useState(1)
  const [strategy, setStrategy] = useState(null)

  // Load: context first, then API fallback
  useEffect(() => {
    if (ctx.step4?.strategy) {
      setStrategy(ctx.step4.strategy)
      setSub(2)
      return
    }
    // Try loading from DB
    if (projectId) {
      apiCall(`/api/ki/${projectId}/saved-strategy`).then(res => {
        if (res?.found && res.strategy) {
          setStrategy(res.strategy)
          ctx.setStep(4, { strategy: res.strategy })
          setSub(2)
        }
      }).catch(() => {})
    }
  }, [])

  return (
    <div>
      <SubStepBar current={sub} onNavigate={setSub} />

      {sub === 1 && (
        <GenerateSubStep
          projectId={projectId}
          existingStrategy={strategy}
          onComplete={(strat) => {
            setStrategy(strat)
            setSub(2)
          }}
        />
      )}

      {sub === 2 && (
        <ReviewSubStep
          projectId={projectId}
          strategy={strategy}
          onGoToCalendar={onGoToCalendar}
          onRerun={() => setSub(1)}
        />
      )}

      <div style={{ display: "flex", justifyContent: "flex-start", marginTop: 16 }}>
        <Btn onClick={onBack}>← Back to Pipeline</Btn>
      </div>
    </div>
  )
}
