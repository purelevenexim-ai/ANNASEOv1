/**
 * PhaseScoreTree — merged Phase4 (Score) + Phase5 (Tree) + Phase6 (Graph).
 * Single "Run All" button executes all 3 phases sequentially.
 * Tabs are for navigation only; run logic is orchestrated by the parent.
 * onComplete fires after the Graph phase finishes.
 */
import React, { useState, useCallback, useEffect, useRef } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, StatsRow, usePhaseRunner, PhaseResult, NotificationList } from "./shared"
import Phase4 from "./Phase4"
import Phase5 from "./Phase5"

const TAB_STYLE = (active) => ({
  padding: "8px 20px",
  border: "none",
  borderBottom: active ? "3px solid #8b5cf6" : "3px solid transparent",
  background: "none",
  cursor: "pointer",
  fontSize: 14,
  fontWeight: active ? 700 : 400,
  color: active ? "#8b5cf6" : "#6b7280",
  transition: "color 150ms, border-color 150ms",
})

/* ── Phase6 Graph Section ────────────────────────────────────────── */

function GraphSection({ projectId, sessionId, onComplete, autoRun, hideRunButton }) {
  const { graph, setGraph } = useKw2Store()
  const p6 = usePhaseRunner("P6")
  const [graphStats, setGraphStats] = useState(null)

  useEffect(() => {
    async function load() {
      try {
        const gData = await api.getGraph(projectId, sessionId)
        if (gData.graph && Object.keys(gData.graph).length) setGraph(gData.graph)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  const runGraph = useCallback(async () => {
    p6.setLoading(true)
    p6.setError(null)
    p6.log("Building knowledge graph...", "info")
    try {
      const data = await api.runPhase6(projectId, sessionId)
      setGraphStats(data.graph)
      const gData = await api.getGraph(projectId, sessionId)
      setGraph(gData.graph)
      const edges = data.graph?.edges || 0
      p6.log(`Complete: ${edges} edges, ${data.graph?.pillars || 0} pillars, ${data.graph?.clusters || 0} clusters`, "success")
      p6.toast(`Knowledge graph: ${edges} edges created`, "success")
      onComplete()
    } catch (e) {
      p6.setError(e.message)
      p6.log(`Failed: ${e.message}`, "error")
      p6.toast(`Phase 6 failed: ${e.message}`, "error")
    }
    p6.setLoading(false)
  }, [projectId, sessionId])

  useEffect(() => { if (autoRun) runGraph() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const edgeTypes = graph ? Object.entries(graph) : []

  return (
    <Card
      title="Knowledge Graph"
      actions={hideRunButton ? null : <RunButton onClick={runGraph} loading={p6.loading}>Build Graph</RunButton>}
    >
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 8 }}>
        Builds edges: keyword→cluster, sibling, cluster→pillar, pillar→universe, cross-cluster.
      </p>

      {p6.error && <p style={{ color: "#dc2626", fontSize: 13 }}>{p6.error}</p>}

      {graphStats && (
        <StatsRow items={[
          { label: "Total Edges", value: graphStats.edges || 0, color: "#10b981" },
          { label: "Pillars", value: graphStats.pillars || 0, color: "#3b82f6" },
          { label: "Clusters", value: graphStats.clusters || 0, color: "#8b5cf6" },
        ]} />
      )}

      {edgeTypes.length > 0 && (
        <div style={{ fontSize: 13, marginTop: 8 }}>
          {edgeTypes.map(([type, edges]) => (
            <div key={type} style={{ marginBottom: 8 }}>
              <Badge color="blue">{type}</Badge>
              <span style={{ marginLeft: 8, color: "#6b7280" }}>{edges.length} edges</span>
              <div style={{ marginLeft: 16, fontSize: 12, color: "#9ca3af", maxHeight: 80, overflow: "auto" }}>
                {edges.slice(0, 5).map((e, i) => (
                  <div key={i}>{e.from} → {e.to}</div>
                ))}
                {edges.length > 5 && <div>...and {edges.length - 5} more</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {graphStats && (
        <PhaseResult
          phaseNum={6}
          stats={[
            { label: "Edges", value: graphStats.edges || 0, color: "#10b981" },
            { label: "Pillars", value: graphStats.pillars || 0, color: "#3b82f6" },
            { label: "Clusters", value: graphStats.clusters || 0, color: "#8b5cf6" },
          ]}
          onNext={null}
        />
      )}

      <NotificationList notifications={p6.notifications} />
    </Card>
  )
}

/* ── Persistent run state helpers ──────────────────────────────────────── */

const _lsKeyST   = (sid) => `kw2_st_run_${sid}`
const _saveRunST  = (sid, rs, ps, cs) => {
  try { localStorage.setItem(_lsKeyST(sid), JSON.stringify({ runStep: rs, pendingStep: ps, completedSteps: cs })) } catch {}
}
const _loadRunST  = (sid) => {
  try { const s = JSON.parse(localStorage.getItem(_lsKeyST(sid)) || "null"); if (s && typeof s === "object") return s } catch {}
  return {}
}
const _clearRunST = (sid) => { try { localStorage.removeItem(_lsKeyST(sid)) } catch {} }

/* ── Step tab with status indicator ─────────────────────────────────────── */

function StepTabBtn({ icon, label, step, tab: activeTab, runStep, pendingStep, completedSteps, onSelect }) {
  const active    = activeTab === step
  const isRunning = runStep === step
  const isPending = pendingStep === step
  const isDone    = completedSteps.includes(step) && !isRunning
  return (
    <button
      onClick={() => onSelect(step)}
      style={{
        padding: "8px 18px", border: "none",
        borderBottom: active ? "3px solid #8b5cf6" : "3px solid transparent",
        background: "none", cursor: "pointer", fontSize: 14,
        fontWeight: active ? 700 : 400,
        color: active ? "#8b5cf6" : isDone ? "#059669" : "#6b7280",
        transition: "color 150ms, border-color 150ms",
        display: "flex", alignItems: "center", gap: 4,
      }}
    >
      <span>{icon}</span>
      <span>{label}</span>
      {isDone    && <span style={{ color: "#10b981", fontSize: 11 }}>✓</span>}
      {isRunning && <span style={{ display: "inline-block", width: 10, height: 10, border: "2px solid rgba(59,130,246,.3)", borderTop: "2px solid #3b82f6", borderRadius: "50%", animation: "kw2spin .7s linear infinite" }} />}
      {isPending && <span style={{ color: "#f59e0b", fontSize: 11 }}>⏸</span>}
    </button>
  )
}

const _BTN_ST = {
  pause:  { padding: "5px 12px", borderRadius: 6, border: "1px solid #fcd34d", background: "#fffbeb",  color: "#92400e", fontSize: 12, cursor: "pointer", fontWeight: 600 },
  stop:   { padding: "5px 12px", borderRadius: 6, border: "1px solid #fca5a5", background: "#fff1f2",  color: "#b91c1c", fontSize: 12, cursor: "pointer", fontWeight: 600 },
  resume: { padding: "5px 14px", borderRadius: 6, border: "none",              background: "#10b981",  color: "#fff",    fontSize: 12, cursor: "pointer", fontWeight: 700 },
  rerun:  { padding: "5px 12px", borderRadius: 6, border: "1px solid #c7d2fe", background: "#eef2ff",  color: "#3730a3", fontSize: 12, cursor: "pointer", fontWeight: 600 },
  clear:  { padding: "5px 12px", borderRadius: 6, border: "1px solid #d1d5db", background: "#f9fafb",  color: "#374151", fontSize: 12, cursor: "pointer" },
}

/* ── Main PhaseScoreTree Component ──────────────────────────────────── */

export default function PhaseScoreTree({ projectId, sessionId, onComplete }) {
  // Restore persisted state — survives page refresh
  const [runStep,        setRunStep]        = useState(() => _loadRunST(sessionId).runStep || null)
  const [pendingStep,    setPendingStep]    = useState(() => _loadRunST(sessionId).pendingStep || null)
  const [completedSteps, setCompletedSteps] = useState(() => {
    const s = _loadRunST(sessionId); return Array.isArray(s.completedSteps) ? s.completedSteps : []
  })
  const [tab, setTab] = useState(() => {
    const s = _loadRunST(sessionId); return s.runStep || s.pendingStep || "score"
  })

  // Pause/Stop: refs (not persisted — refresh re-runs current step from scratch, which is correct)
  const pauseRef = useRef(false)
  const stopRef  = useRef(false)
  const [pauseRequested, setPauseRequested] = useState(false)
  const [stopRequested,  setStopRequested]  = useState(false)

  const running = runStep !== null
  const paused  = !running && pendingStep !== null
  const allDone = completedSteps.length === 3 && !running && !paused

  // Persist whenever state changes
  useEffect(() => {
    _saveRunST(sessionId, runStep, pendingStep, completedSteps)
  }, [sessionId, runStep, pendingStep, completedSteps])

  // Auto-switch tab when the running step advances
  useEffect(() => { if (runStep) setTab(runStep) }, [runStep])

  // ── Shared advance / halt logic called by each phase's onComplete ──
  const _advanceOrHalt = useCallback((doneStep, nextStep, isLast) => {
    const wasStopped = stopRef.current
    const wasPaused  = pauseRef.current
    pauseRef.current = false
    stopRef.current  = false
    setPauseRequested(false)
    setStopRequested(false)
    setCompletedSteps(prev => prev.includes(doneStep) ? prev : [...prev, doneStep])
    if (wasStopped) { setRunStep(null); setPendingStep(null);         return }
    if (wasPaused)  { setRunStep(null); setPendingStep(nextStep);      return }
    if (isLast)     { setRunStep(null); setPendingStep(null); onComplete(); return }
    setRunStep(nextStep)
  }, [onComplete])

  const onScoreDone = useCallback(() => _advanceOrHalt("score", "tree",  false), [_advanceOrHalt])
  const onTreeDone  = useCallback(() => _advanceOrHalt("tree",  "graph", false), [_advanceOrHalt])
  const onGraphDone = useCallback(() => _advanceOrHalt("graph", null,    true),  [_advanceOrHalt])

  // ── User action handlers ──
  const handleRunAll = useCallback(() => {
    pauseRef.current = false; stopRef.current = false
    setPauseRequested(false); setStopRequested(false)
    setCompletedSteps([]); setPendingStep(null); setRunStep("score")
  }, [])

  const handleResume = useCallback(() => {
    if (!pendingStep) return
    pauseRef.current = false; stopRef.current = false
    setPauseRequested(false); setStopRequested(false)
    const next = pendingStep; setPendingStep(null); setRunStep(next)
  }, [pendingStep])

  const handlePause = useCallback(() => { pauseRef.current = true; setPauseRequested(true) }, [])
  const handleStop  = useCallback(() => { stopRef.current  = true; setStopRequested(true)  }, [])

  const handleClear = useCallback(() => {
    pauseRef.current = false; stopRef.current = false
    setPauseRequested(false); setStopRequested(false)
    setRunStep(null); setPendingStep(null); setCompletedSteps([])
    _clearRunST(sessionId)
  }, [sessionId])

  const tabProps = { tab, runStep, pendingStep, completedSteps, onSelect: (s) => { if (!running) setTab(s) } }

  return (
    <div>
      {/* ── Tab bar + pipeline controls ──────────────────────────────────── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        borderBottom: "1px solid #e5e7eb", marginBottom: 16, background: "#fff",
        borderRadius: "8px 8px 0 0", padding: "0 10px 0 0", flexWrap: "wrap", gap: 4,
      }}>
        <div style={{ display: "flex" }}>
          <StepTabBtn icon="📊" label="Score" step="score" {...tabProps} />
          <StepTabBtn icon="🌳" label="Tree"  step="tree"  {...tabProps} />
          <StepTabBtn icon="🕸" label="Graph" step="graph" {...tabProps} />
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
          {running ? (
            <>
              <span style={{ fontSize: 11, color: "#6b7280", whiteSpace: "nowrap" }}>
                {stopRequested  ? "⏹ Stopping after this step…"
                  : pauseRequested ? "⏸ Pausing after this step…"
                  : `Running ${runStep}…`}
              </span>
              {!pauseRequested && !stopRequested && (
                <button onClick={handlePause} style={_BTN_ST.pause}>⏸ Pause</button>
              )}
              {!stopRequested && (
                <button onClick={handleStop} style={_BTN_ST.stop}>⏹ Stop</button>
              )}
            </>
          ) : paused ? (
            <>
              <span style={{ fontSize: 11, color: "#d97706", fontWeight: 600, whiteSpace: "nowrap" }}>
                ⏸ Paused — next: {pendingStep}
              </span>
              <button onClick={handleResume} style={_BTN_ST.resume}>▶ Resume from {pendingStep}</button>
              <button onClick={handleRunAll} style={_BTN_ST.rerun}>↺ Re-run All</button>
              <button onClick={handleClear}  style={_BTN_ST.clear}>✕ Clear</button>
            </>
          ) : (
            <>
              <RunButton onClick={handleRunAll}>
                {allDone ? "↺ Re-run All" : "▶ Run All"}
              </RunButton>
              {completedSteps.length > 0 && !allDone && (
                <button onClick={handleClear} style={_BTN_ST.clear}>✕ Clear</button>
              )}
            </>
          )}
        </div>
        <style>{`@keyframes kw2spin { to { transform: rotate(360deg) } }`}</style>
      </div>

      {tab === "score" && (
        <Phase4
          projectId={projectId} sessionId={sessionId}
          onComplete={onScoreDone} onNext={onScoreDone}
          autoRun={runStep === "score"} hideRunButton
        />
      )}
      {tab === "tree" && (
        <Phase5
          projectId={projectId} sessionId={sessionId}
          onComplete={onTreeDone} onNext={onTreeDone}
          autoRun={runStep === "tree"} hideRunButton
        />
      )}
      {tab === "graph" && (
        <GraphSection
          projectId={projectId} sessionId={sessionId}
          onComplete={onGraphDone}
          autoRun={runStep === "graph"} hideRunButton
        />
      )}
    </div>
  )
}

