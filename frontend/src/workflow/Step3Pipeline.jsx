// Step 3 — Pipeline (P1-P14 Split-View)
// Left panel: Live console (40%) — scrolling phase log
// Right panel: Phase result cards (60%) — 14 cards that fill as phases complete
// Features: execution mode toggle, pillar selection, per-pillar tabs, continue button

import { useState, useEffect, useRef, useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNotification } from "../store/notification"
import useWorkflowContext from "../store/workflowContext"
import { apiCall, API, T, Card, Btn, Spinner, Badge } from "./shared"

function authHeaders() {
  const t = localStorage.getItem("annaseo_token")
  return t ? { Authorization: `Bearer ${t}` } : {}
}

// ─── Phase metadata ─────────────────────────────────────────────────────────
const PHASES = [
  { id: "P1",  name: "Seed Validation",     group: "Collection", color: "#0d9488" },
  { id: "P2",  name: "Keyword Expansion",    group: "Collection", color: "#0d9488" },
  { id: "P3",  name: "Normalization",        group: "Collection", color: "#0d9488" },
  { id: "P4",  name: "Entity Detection",     group: "Analysis",   color: "#06b6d4" },
  { id: "P5",  name: "Intent Classification",group: "Analysis",   color: "#06b6d4" },
  { id: "P6",  name: "SERP Analysis",        group: "Analysis",   color: "#06b6d4" },
  { id: "P7",  name: "Opportunity Scoring",  group: "Scoring",    color: "#d97706" },
  { id: "P8",  name: "Topic Detection",      group: "Scoring",    color: "#d97706" },
  { id: "P9",  name: "Cluster Formation",    group: "Scoring",    color: "#d97706" },
  { id: "P10", name: "Pillar Identification",group: "Scoring",    color: "#d97706" },
  { id: "P11", name: "Knowledge Graph",      group: "Structure",  color: "#ea580c" },
  { id: "P12", name: "Internal Links",       group: "Structure",  color: "#ea580c" },
  { id: "P13", name: "Content Calendar",     group: "Planning",   color: "#3b82f6" },
  { id: "P14", name: "Deduplication",        group: "Planning",   color: "#3b82f6" },
]

const GROUP_ORDER = ["Collection", "Analysis", "Scoring", "Structure", "Planning"]

// ─── Mini table helper ───────────────────────────────────────────────────────
function MiniTable({ cols, rows, maxRows = 20 }) {
  if (!rows?.length) return null
  const shown = rows.slice(0, maxRows)
  return (
    <table style={{ width: "100%", fontSize: 10, borderCollapse: "collapse", marginTop: 6 }}>
      <thead>
        <tr>
          {cols.map(c => (
            <th key={c} style={{
              textAlign: "left", padding: "2px 8px", fontWeight: 700,
              color: T.textSoft, borderBottom: `1px solid ${T.border}`, whiteSpace: "nowrap",
            }}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {shown.map((row, i) => (
          <tr key={i} style={{ background: i % 2 === 0 ? "transparent" : "#f8fafc" }}>
            {row.map((cell, j) => (
              <td key={j} style={{ padding: "2px 8px", color: T.text, wordBreak: "break-word" }}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ─── Phase detail panel ──────────────────────────────────────────────────────
function PhaseDetailPanel({ phaseId, summary, sampleData }) {
  if (!summary && !sampleData) return null

  const s = summary || {}

  // P5 intent distribution
  if (phaseId === "P5" && s.intent_distribution) {
    const rows = Object.entries(s.intent_distribution).map(([k, v]) => [
      k, v, `${Math.round((v / (s.classified_count || 1)) * 100)}%`
    ])
    return <MiniTable cols={["Intent", "Count", "Share"]} rows={rows} />
  }

  // P7 top keywords
  if (phaseId === "P7" && s.top_5_keywords) {
    return (
      <div>
        <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4 }}>
          Top Keywords (avg score: {s.avg_score ?? "—"})
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {s.top_5_keywords.map((kw, i) => (
            <span key={i} style={{
              padding: "2px 8px", borderRadius: 10, background: T.tealLight,
              color: T.teal, fontSize: 10, fontWeight: 600,
            }}>{kw}</span>
          ))}
        </div>
      </div>
    )
  }

  // P8 topics
  if (phaseId === "P8" && s.topics?.length) {
    return <MiniTable
      cols={["Topic", "Keywords"]}
      rows={s.topics.map(t => [t.name, t.size ?? t.keyword_count ?? "—"])}
    />
  }

  // P9 clusters
  if (phaseId === "P9" && s.clusters?.length) {
    return <MiniTable
      cols={["Cluster", "Keywords"]}
      rows={s.clusters.map(c => [c.name, c.keyword_count ?? "—"])}
    />
  }

  // P10 pillars
  if (phaseId === "P10" && s.pillars?.length) {
    return <MiniTable
      cols={["Pillar", "Clusters", "Keywords"]}
      rows={s.pillars.map(p => [p.name, p.cluster_count ?? "—", p.keyword_count ?? "—"])}
    />
  }

  // P13 calendar
  if (phaseId === "P13") {
    return (
      <div style={{ fontSize: 11, color: T.text }}>
        <strong>{s.calendar_entries ?? "?"}</strong> articles scheduled
        {s.date_range && <span style={{ color: T.textSoft }}> · {s.date_range}</span>}
      </div>
    )
  }

  // P2 / P3 — sample keyword list
  if (s.sample?.length) {
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
        {s.sample.slice(0, 30).map((kw, i) => (
          <span key={i} style={{
            padding: "1px 6px", borderRadius: 8, background: T.grayLight,
            fontSize: 10, color: T.text,
          }}>{kw}</span>
        ))}
      </div>
    )
  }

  // Generic: show summary key/values
  const pairs = Object.entries(s).filter(([k, v]) => typeof v !== "object")
  if (pairs.length) {
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
        {pairs.map(([k, v]) => (
          <span key={k} style={{ fontSize: 10, color: T.textSoft }}>
            <strong>{k.replace(/_/g, " ")}:</strong> {String(v)}
          </span>
        ))}
      </div>
    )
  }
  return null
}

// ─── Phase Card ─────────────────────────────────────────────────────────────
function PhaseCard({ phase, data, runId }) {
  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  const status = data?.status || "pending"
  // Use detail if fetched, fall back to streamed data
  const summary = detail?.result_summary || data?.result_summary || {}

  const statusBadge = {
    pending:  { icon: "⏳", color: T.gray,  label: "Pending" },
    starting: { icon: "▶",  color: T.amber, label: "Running" },
    complete: { icon: "✓",  color: T.green, label: "Done" },
    error:    { icon: "✗",  color: T.red,   label: "Error" },
    paused:   { icon: "⏸",  color: T.amber, label: "Paused" },
  }[status] || { icon: "⏳", color: T.gray, label: status }

  const isActive = status === "starting"
  const isDone = status === "complete"

  const handleExpand = async () => {
    const next = !expanded
    setExpanded(next)
    if (next && !detail && runId) {
      setLoadingDetail(true)
      try {
        const d = await apiCall(`/api/runs/${runId}/phase/${phase.id}/detail`)
        if (d && d.status !== "not_found") setDetail(d)
      } catch (e) { /* silent */ }
      setLoadingDetail(false)
    }
  }

  // Compact summary text for collapsed state
  const summaryText = (() => {
    if (!isDone || !Object.keys(summary).length) return null
    if (summary.expanded_count)     return `${summary.expanded_count} keywords expanded`
    if (summary.normalized_count)   return `${summary.normalized_count} keywords`
    if (summary.classified_count)   return `${summary.classified_count} classified`
    if (summary.scored_count)       return `${summary.scored_count} scored · avg ${summary.avg_score}`
    if (summary.topic_count)        return `${summary.topic_count} topics`
    if (summary.cluster_count)      return `${summary.cluster_count} clusters`
    if (summary.pillar_count)       return `${summary.pillar_count} pillars`
    if (summary.calendar_entries)   return `${summary.calendar_entries} articles`
    if (summary.deduplicated_count) return `${summary.deduplicated_count} after dedup`
    if (summary.link_count)         return `${summary.link_count} links`
    if (summary.graph_nodes)        return `${summary.graph_nodes} graph nodes`
    if (summary.entity_count)       return `${summary.entity_count} entities`
    if (summary.serp_analyzed_count) return `${summary.serp_analyzed_count} SERP analyzed`
    return null
  })()

  return (
    <div style={{
      border: `1px solid ${isActive ? phase.color + "60" : isDone ? T.green + "40" : T.border}`,
      borderRadius: 8, padding: "8px 10px", marginBottom: 6,
      background: isActive ? phase.color + "08" : isDone ? T.greenLight : "#fff",
      transition: "all 0.3s",
      opacity: status === "pending" ? 0.5 : 1,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: isDone ? "pointer" : "default" }}
        onClick={() => isDone && handleExpand()}>
        <span style={{
          width: 22, height: 22, borderRadius: "50%", display: "flex",
          alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700,
          background: statusBadge.color + "20", color: statusBadge.color,
        }}>
          {isActive ? <span style={{ animation: "spin 0.7s linear infinite", display: "inline-block" }}>◌</span> : statusBadge.icon}
        </span>
        <div style={{ flex: 1 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: T.text }}>{phase.id}</span>
          <span style={{ fontSize: 11, color: T.textSoft, marginLeft: 6 }}>{phase.name}</span>
        </div>
        <Badge color={phase.color}>{phase.group}</Badge>
        {data?.elapsed_ms != null && (
          <span style={{ fontSize: 10, color: T.textSoft }}>{(data.elapsed_ms / 1000).toFixed(1)}s</span>
        )}
        {data?.output_count != null && (
          <Badge color={T.teal}>{data.output_count} items</Badge>
        )}
        {isDone && <span style={{ fontSize: 10, color: T.textSoft }}>{expanded ? "▲" : "▼"}</span>}
      </div>

      {/* Collapsed summary */}
      {isDone && summaryText && !expanded && (
        <div style={{ marginTop: 3, paddingLeft: 30, fontSize: 10, color: T.textSoft }}>
          {summaryText}
        </div>
      )}

      {/* Expanded detail */}
      {expanded && isDone && (
        <div style={{
          marginTop: 8, paddingLeft: 30, paddingTop: 8,
          borderTop: `1px solid ${T.border}`,
        }}>
          {loadingDetail && (
            <div style={{ fontSize: 11, color: T.textSoft }}>Loading detail…</div>
          )}
          {!loadingDetail && (
            <PhaseDetailPanel
              phaseId={phase.id}
              summary={summary}
              sampleData={detail?.result_sample || data?.result_sample}
            />
          )}
          {data?.msg && (
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 6 }}>{data.msg}</div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Live Console (dark console for left panel) ─────────────────────────────
const LOG_COLOR = { success: "#10b981", warn: "#f59e0b", error: "#ef4444", info: "#64748b" }
const LOG_ICON  = { success: "✓", warn: "⚠", error: "✗", info: "›" }

function PipelineConsole({ logs, running }) {
  const ref = useRef(null)
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [logs])

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{
        fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#64748b",
        marginBottom: 5, display: "flex", alignItems: "center", gap: 8,
      }}>
        PIPELINE LOG
        {running && <span style={{
          width: 7, height: 7, borderRadius: "50%", background: "#10b981",
          display: "inline-block", animation: "lcPulse 1.2s ease-in-out infinite",
        }}/>}
      </div>
      <div ref={ref} style={{
        flex: 1, background: "#0f172a", borderRadius: 8, padding: "10px 12px",
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace", fontSize: 11, lineHeight: 1.65,
        overflowY: "auto", border: "1px solid #1e293b", minHeight: 300,
      }}>
        {logs.map((l, i) => (
          <div key={i} style={{ display: "flex", gap: 6, alignItems: "flex-start", marginBottom: 1 }}>
            <span style={{ color: l.color || LOG_COLOR[l.level] || "#64748b", minWidth: 10 }}>
              {LOG_ICON[l.level] || "›"}
            </span>
            {l.phase && (
              <span style={{ color: l.color || "#475569", fontSize: 9, minWidth: 28, fontWeight: 600 }}>
                {l.phase}
              </span>
            )}
            <span style={{ color: l.color || LOG_COLOR[l.level] || "#94a3b8", flex: 1, wordBreak: "break-word" }}>
              {l.msg}
            </span>
          </div>
        ))}
        {running && (
          <div style={{ color: "#334155", marginTop: 4, animation: "lcBlink 1s step-end infinite" }}>█</div>
        )}
      </div>
    </div>
  )
}

// ─── Main Component ──────────────────────────────────────────────────────────
export default function Step3Pipeline({ projectId, onComplete, onBack, aiProvider = "groq" }) {
  const notify = useNotification(s => s.notify)
  const ctx = useWorkflowContext()

  const [mode, setMode]               = useState("select")  // select | running | done
  const [executionMode, setExecutionMode] = useState("continuous")
  const [selectedPillars, setSelectedPillars] = useState([])
  const [runs, setRuns]               = useState([])         // [{run_id, pillar, status}]
  const [activePillar, setActivePillar] = useState(null)
  const [phaseLogs, setPhaseLogs]     = useState([])         // for console
  const [phaseResults, setPhaseResults] = useState({})       // {P1: {status, ...}, P2: ...}
  const [pausedGroup, setPausedGroup] = useState(null)       // group name if paused
  const [starting, setStarting]       = useState(false)

  // SSE refs
  const eventSourceRef = useRef(null)

  // Load available pillars
  const { data: pillarData } = useQuery({
    queryKey: ["ki-pipeline-pillars", projectId],
    queryFn: async () => {
      const session = await apiCall(`/api/ki/${projectId}/latest-session`)
      if (!session?.session_id) return { pillars: [] }
      const rows = await apiCall(`/api/ki/${projectId}/session/${session.session_id}/accepted-pillars`)
      return { pillars: rows?.pillars || [], session_id: session.session_id }
    },
    enabled: !!projectId && mode === "select",
    retry: false,
  })

  const availablePillars = pillarData?.pillars || []

  // ── Start pipeline ────────────────────────────────────────────────────
  const startPipeline = async () => {
    if (selectedPillars.length === 0) {
      notify("Select at least one pillar", "warn")
      return
    }
    setStarting(true)
    try {
      const res = await apiCall(`/api/ki/${projectId}/run-pipeline`, "POST", {
        session_id: pillarData?.session_id || ctx.sessionId,
        selected_pillars: selectedPillars,
        execution_mode: executionMode,
        max_phase: "P14",
        preferred_provider: aiProvider,
      })

      const newRuns = (res.runs || []).map(r => ({ ...r, status: "queued" }))
      setRuns(newRuns)
      setMode("running")
      setPhaseLogs([])
      setPhaseResults({})

      // Start SSE for first run
      if (newRuns.length > 0) {
        setActivePillar(newRuns[0].pillar)
        connectSSE(newRuns[0].run_id)
      }

      ctx.setStep(3, { runs: newRuns.map(r => r.run_id) })
      ctx.flush(projectId)
    } catch (e) {
      notify(`Pipeline start failed: ${e.message}`, "error")
    }
    setStarting(false)
  }

  // ── SSE Connection ────────────────────────────────────────────────────
  const connectSSE = useCallback((runId) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const url = `${API}/api/runs/${runId}/stream`
    const es = new EventSource(url)
    eventSourceRef.current = es

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === "phase_log") {
          // Add to console log
          setPhaseLogs(prev => [...prev, {
            phase: data.phase,
            msg: data.msg || `${data.phase}: ${data.status}`,
            level: data.status === "error" ? "error" : data.status === "complete" ? "success" : "info",
            color: data.color ? `${data.color}` : undefined,
          }])

          // Update phase results
          if (data.phase && data.phase.startsWith("P")) {
            setPhaseResults(prev => ({
              ...prev,
              [data.phase]: {
                ...prev[data.phase],
                ...data,
              },
            }))
          }

          // Check for group pause
          if (data.status === "paused" && data.phase?.startsWith("GROUP_")) {
            const group = data.phase.replace("GROUP_", "").toLowerCase()
            setPausedGroup(group.charAt(0).toUpperCase() + group.slice(1))
          }
        }

        if (data.type === "group_pause") {
          setPausedGroup(data.group)
          setPhaseLogs(prev => [...prev, {
            phase: "PAUSE",
            msg: `⏸ ${data.group} group complete — click Continue to proceed`,
            level: "warn",
          }])
        }

        if (data.type === "run_complete" || data.type === "complete") {
          setPhaseLogs(prev => [...prev, {
            phase: "DONE",
            msg: `✓ Pipeline complete (${data.status})`,
            level: "success",
          }])
          setRuns(prev => prev.map(r => r.run_id === runId ? { ...r, status: data.status || "complete" } : r))
          // Check if all runs done
          checkAllRunsDone(runId)
        }

        if (data.type === "run_error" || data.type === "error") {
          setPhaseLogs(prev => [...prev, {
            phase: "ERROR",
            msg: `✗ Pipeline error: ${data.error}`,
            level: "error",
          }])
          setRuns(prev => prev.map(r => r.run_id === runId ? { ...r, status: "error" } : r))
        }
      } catch (e) {
        // Parse error, ignore
      }
    }

    es.onerror = () => {
      // SSE disconnected — fall back to polling
      es.close()
      startPolling(runId)
    }
  }, [])

  // ── Polling fallback ──────────────────────────────────────────────────
  const pollRef = useRef(null)
  const startPolling = useCallback((runId) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const res = await apiCall(`/api/runs/${runId}/phase-results`)
        if (res?.phases) {
          setPhaseResults(prev => ({ ...prev, ...res.phases }))
        }
      } catch (e) {
        // ignore
      }
    }, 3000)
  }, [])

  // Check if all runs are complete
  const checkAllRunsDone = useCallback((justFinishedId) => {
    setRuns(prev => {
      const updated = prev.map(r => r.run_id === justFinishedId ? { ...r, status: "complete" } : r)
      const allDone = updated.every(r => r.status === "complete" || r.status === "error" || r.status === "warning")
      if (allDone) {
        setMode("done")
        if (eventSourceRef.current) eventSourceRef.current.close()
        if (pollRef.current) clearInterval(pollRef.current)
      }
      // Switch to next unfinished run
      const nextRun = updated.find(r => r.status === "queued" || r.status === "running")
      if (nextRun && nextRun.run_id !== justFinishedId) {
        setActivePillar(nextRun.pillar)
        connectSSE(nextRun.run_id)
      }
      return updated
    })
  }, [connectSSE])

  // ── Continue group (step-by-step mode) ────────────────────────────────
  const continueGroup = async (action = "continue") => {
    const activeRun = runs.find(r => r.pillar === activePillar)
    if (!activeRun) return
    const labels = { continue: "▶ Continuing", skip: "⏭ Skipping next group", stop: "⏹ Stopping pipeline" }
    try {
      await apiCall(`/api/runs/${activeRun.run_id}/continue-group`, "POST", { group: pausedGroup, action })
      setPausedGroup(null)
      setPhaseLogs(prev => [...prev, { phase: "RESUME", msg: `${labels[action] || labels.continue}…`, level: action === "stop" ? "warn" : "info" }])
    } catch (e) {
      const msg = e.message?.includes("<html") ? "Server temporarily unavailable — retrying…" : e.message
      notify(`Continue failed: ${msg}`, "error")
      // Auto-retry once after 3s for transient 502/503
      setTimeout(async () => {
        try {
          await apiCall(`/api/runs/${activeRun.run_id}/continue-group`, "POST", { group: pausedGroup, action })
          setPausedGroup(null)
          setPhaseLogs(prev => [...prev, { phase: "RESUME", msg: `${labels[action] || labels.continue}…`, level: "info" }])
        } catch (e2) { /* silent retry fail */ }
      }, 3000)
    }
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close()
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  // Switch active pillar SSE
  const switchPillar = (pillar) => {
    setActivePillar(pillar)
    const run = runs.find(r => r.pillar === pillar)
    if (run) {
      setPhaseLogs([])
      setPhaseResults({})
      if (run.status === "queued" || run.status === "running") {
        connectSSE(run.run_id)
      } else {
        // Load from DB
        apiCall(`/api/runs/${run.run_id}/phase-results`).then(res => {
          if (res?.phases) setPhaseResults(res.phases)
        }).catch(() => {})
      }
    }
  }

  // ── RENDER: Pillar Selection ──────────────────────────────────────────
  if (mode === "select") {
    return (
      <div>
        <Card style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>
            Keyword Pipeline — P1 to P14
          </div>
          <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 16 }}>
            Process your keywords through 14 phases: expansion, scoring, clustering, pillar identification, and content calendar.
          </div>

          {/* Execution Mode Toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <span style={{ fontSize: 12, fontWeight: 600 }}>Execution Mode:</span>
            {["continuous", "step_by_step"].map(m => (
              <label key={m} style={{
                display: "flex", alignItems: "center", gap: 4, padding: "4px 12px",
                borderRadius: 8, fontSize: 11, cursor: "pointer",
                background: executionMode === m ? T.purpleLight : T.grayLight,
                border: `1px solid ${executionMode === m ? T.purple : T.border}`,
              }}>
                <input type="radio" name="execMode" value={m}
                  checked={executionMode === m}
                  onChange={() => setExecutionMode(m)}
                  style={{ display: "none" }} />
                {m === "continuous" ? "⚡ Continuous" : "🔄 Step by Step"}
              </label>
            ))}
          </div>

          {/* Pillar Selection */}
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Select Pillars to Process</div>

          {availablePillars.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: T.textSoft }}>
              No accepted pillars found. Complete Discovery step first with at least 5 accepted keywords.
            </div>
          ) : (
            <>
              <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
                <Btn small onClick={() => setSelectedPillars(availablePillars.map(p => p.keyword || p))}>
                  Select All ({availablePillars.length})
                </Btn>
                <Btn small onClick={() => setSelectedPillars([])}>Clear</Btn>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {availablePillars.map(p => {
                  const name = p.keyword || p
                  const selected = selectedPillars.includes(name)
                  return (
                    <button key={name}
                      onClick={() => setSelectedPillars(prev =>
                        selected ? prev.filter(x => x !== name) : [...prev, name]
                      )}
                      style={{
                        padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 500,
                        cursor: "pointer", border: `1.5px solid ${selected ? T.purple : T.border}`,
                        background: selected ? T.purpleLight : "#fff", color: selected ? T.purple : T.text,
                        transition: "all 0.15s",
                      }}>
                      {selected && "✓ "}{name}
                    </button>
                  )
                })}
              </div>
            </>
          )}
        </Card>

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 12 }}>
          <Btn onClick={onBack}>← Back to Discovery</Btn>
          <Btn variant="primary" onClick={startPipeline}
            disabled={starting || selectedPillars.length === 0}>
            {starting ? <><Spinner /> Starting…</> : `Run Pipeline (${selectedPillars.length} pillars) →`}
          </Btn>
        </div>
      </div>
    )
  }

  // ── RENDER: Pipeline Running / Done (Split View) ──────────────────────
  const isRunning = mode === "running"
  const activeRun = runs.find(r => r.pillar === activePillar)

  return (
    <div>
      <style>{`
        @keyframes spin    { to { transform: rotate(360deg); } }
        @keyframes lcPulse { 0%,100%{opacity:1} 50%{opacity:.3} }
        @keyframes lcBlink { 0%,100%{opacity:1} 50%{opacity:0} }
      `}</style>

      {/* Top bar: pillar tabs + status */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        {runs.length > 1 && runs.map(r => (
          <button key={r.run_id}
            onClick={() => switchPillar(r.pillar)}
            style={{
              padding: "5px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600,
              border: `1.5px solid ${r.pillar === activePillar ? T.purple : T.border}`,
              background: r.pillar === activePillar ? T.purpleLight : "#fff",
              color: r.pillar === activePillar ? T.purple : T.text,
              cursor: "pointer",
            }}>
            {r.pillar}
            {r.status === "complete" && " ✓"}
            {r.status === "error" && " ✗"}
            {(r.status === "queued" || r.status === "running") && " ⟳"}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        {pausedGroup && (
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <Btn variant="teal" onClick={() => continueGroup("continue")}>
              ▶ Continue → {pausedGroup}
            </Btn>
            <Btn onClick={() => continueGroup("skip")} style={{ background: "#fef3c7", border: "1px solid #f59e0b", color: "#92400e", fontSize: 11 }}>
              ⏭ Skip Next
            </Btn>
            <Btn onClick={() => continueGroup("stop")} style={{ background: "#fee2e2", border: "1px solid #ef4444", color: "#991b1b", fontSize: 11 }}>
              ⏹ Stop Here
            </Btn>
          </div>
        )}
        {mode === "done" && (
          <Badge color={T.green}>All runs complete</Badge>
        )}
      </div>

      {/* Split view */}
      <div style={{ display: "grid", gridTemplateColumns: "40% 60%", gap: 12, minHeight: 500 }}>
        {/* LEFT: Console */}
        <PipelineConsole logs={phaseLogs} running={isRunning} />

        {/* RIGHT: Phase Cards */}
        <div style={{ overflowY: "auto", maxHeight: 600 }}>
          <div style={{
            fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#64748b",
            marginBottom: 8,
          }}>
            PHASE RESULTS — {activePillar || ""}
          </div>

          {GROUP_ORDER.map(group => (
            <div key={group} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                {group}
              </div>
              {PHASES.filter(p => p.group === group).map(phase => (
                <PhaseCard
                  key={phase.id}
                  phase={phase}
                  data={phaseResults[phase.id]}
                  runId={runs.find(r => r.pillar === activePillar)?.run_id}
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Bottom bar */}
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16 }}>
        <Btn onClick={onBack}>← Back to Discovery</Btn>
        {mode === "done" && (
          <Btn variant="primary" onClick={onComplete}>
            Continue to Strategy →
          </Btn>
        )}
      </div>
    </div>
  )
}
