// Step 5 — Pipeline Runner
// Select pillars and run the 20-phase content pipeline for accepted keywords.
// Monitors each run via SSE. When all runs complete → "Next: Final Review →"

import { useState, useEffect, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNotification } from "../store/notification"
import useWorkflowContext from "../store/workflowContext"
import { apiCall, T, Card, Btn, Spinner, LiveConsole } from "./shared"

const API = import.meta.env.VITE_API_URL || ""

export default function Step5Pipeline({ projectId, onComplete, onBack }) {
  const notify   = useNotification(s => s.notify)
  const ctx      = useWorkflowContext()
  const sessionId = ctx.sessionId

  const [pipelineMode, setPipelineMode]     = useState("select")  // select | running | done
  const [selectedPillars, setSelectedPillars] = useState([])
  const [pipelineLogs, setPipelineLogs]     = useState([])
  const [pipelineRuns, setPipelineRuns]     = useState([])
  const [error, setError]                   = useState("")
  const sseRef = useRef({})

  const addLog = (msg, level = "info") =>
    setPipelineLogs(prev => [...prev.slice(-499), { msg, level }])

  // Get pillar data with per-pillar accepted counts
  const { data: pillarData } = useQuery({
    queryKey: ["ki-pillars-step5", projectId, sessionId],
    queryFn:  () => apiCall(`/api/ki/${projectId}/universe/${sessionId}/by-pillar`),
    enabled:  !!sessionId,
  })

  // Derive ALL pillars from all sources (must come before useEffects that use them)
  const universePillarList = pillarData?.pillars || []
  const pillarMap = Object.fromEntries(universePillarList.map(p => [p.pillar, p]))

  const strategyPillars = (ctx.step3?.strategy_json?.pillar_strategy || [])
    .map(p => p.pillar)
    .filter(Boolean)

  const step1Seeds = ctx.step1?.pillars || []

  // Merge: universe first (has accepted counts), then strategy, then step1
  const allPillarNames = [
    ...universePillarList.map(p => p.pillar),
    ...strategyPillars,
    ...step1Seeds,
  ].filter(Boolean)
  // Deduplicate preserving order, case-insensitive
  const _seen = new Set()
  const allPillars = allPillarNames.filter(p => {
    const key = p.toLowerCase()
    if (_seen.has(key)) return false
    _seen.add(key)
    return true
  })

  const acceptedCount = universePillarList.reduce((sum, p) => sum + (p.accepted || 0), 0)

  // Pre-select all pillars once available
  useEffect(() => {
    if (allPillars.length && !selectedPillars.length) {
      setSelectedPillars(allPillars)
    }
  }, [universePillarList.length, strategyPillars.length, step1Seeds.length])

  // Cleanup SSE + poll timer on unmount
  const pollRef = useRef(null)
  useEffect(() => () => {
    Object.values(sseRef.current).forEach(es => es?.close())
    if (pollRef.current) clearInterval(pollRef.current)
  }, [])

  // ── Poll run status from DB every 5s as fallback ──────────────────────────
  useEffect(() => {
    if (pipelineMode !== "running" || !pipelineRuns.length) return
    pollRef.current = setInterval(async () => {
      try {
        for (const run of pipelineRuns) {
          if (run.status === "complete" || run.status === "error") continue
          const data = await apiCall(`/api/runs/${run.run_id}`)
          if (!data) continue
          const dbStatus = data.status
          const currentPhase = data.current_phase || ""
          const newStatus = dbStatus === "complete" || dbStatus === "warning"
            ? "complete" : dbStatus === "error" || dbStatus === "failed"
            ? "error" : dbStatus
          setPipelineRuns(prev =>
            prev.map(r => r.run_id === run.run_id
              ? { ...r, status: newStatus, currentPhase }
              : r
            )
          )
          if (newStatus === "complete") addLog(`✓ ${run.pillar} completed`, "success")
          if (newStatus === "error") addLog(`✗ ${run.pillar} failed: ${data.error || ""}`, "error")
        }
      } catch {}
    }, 5000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [pipelineMode, pipelineRuns.length])

  // Check if all runs have settled
  const allRunsDone = pipelineRuns.length > 0 &&
    pipelineRuns.every(r => r.status === "complete" || r.status === "error")

  useEffect(() => {
    if (allRunsDone && pipelineMode === "running") {
      setPipelineMode("done")
    }
  }, [pipelineRuns])

  // ── SSE watcher per run ────────────────────────────────────────────────────
  const startSSE = (runId) => {
    if (sseRef.current[runId]) return
    const es = new EventSource(`${API}/api/runs/${runId}/stream`)
    es.addEventListener("message", (e) => {
      try {
        const payload = JSON.parse(e.data)
        if (payload.type === "phase_log") {
          const { phase, status: phs } = payload
          if (phs === "starting") addLog(`▶ ${phase} starting…`, "info")
          if (phs === "complete") addLog(
            `✓ ${phase} complete${payload.output_count != null ? ` (${payload.output_count} items)` : ""}`,
            "success"
          )
          if (phs === "error") addLog(`✗ ${phase} error: ${payload.msg || ""}`, "error")
        }
        if (payload.type === "run_complete" || payload.type === "done") {
          addLog(`Pipeline run complete for ${runId}`, "success")
          setPipelineRuns(prev => prev.map(r => r.run_id === runId ? { ...r, status: "complete" } : r))
          es.close()
          notify("Pipeline run complete", "success")
        }
        if (payload.type === "run_error") {
          addLog(`Run failed: ${payload.error || payload.msg || "unknown"}`, "error")
          setPipelineRuns(prev => prev.map(r => r.run_id === runId ? { ...r, status: "error" } : r))
          es.close()
        }
      } catch {}
    })
    es.addEventListener("error", () => es.close())
    sseRef.current[runId] = es
  }

  // ── Launch pipeline ────────────────────────────────────────────────────────
  const launchPipeline = async () => {
    if (!selectedPillars.length) {
      setError("Select at least one pillar to run the pipeline")
      return
    }
    setError("")
    addLog(`Launching pipeline for ${selectedPillars.length} pillar(s)…`, "info")
    try {
      const r = await apiCall(`/api/ki/${projectId}/run-pipeline`, "POST", {
        session_id:        sessionId,
        selected_pillars:  selectedPillars,
        sequential:        false,
      })
      if (r?.runs) {
        setPipelineRuns(r.runs.map(run => ({ ...run, status: "queued" })))
        setPipelineMode("running")
        r.runs.forEach(run => startSSE(run.run_id))
        addLog(`${r.runs.length} run(s) queued`, "success")
        notify(`Pipeline started — ${r.runs.length} run(s)`, "success")
      } else {
        setError("Failed to start pipeline — no runs returned")
      }
    } catch (e) {
      const msg = e.message || String(e)
      setError(msg)
      addLog("Pipeline failed to start: " + msg, "error")
      notify("Pipeline failed: " + msg, "error")
    }
  }

  if (!sessionId) {
    return (
      <Card>
        <div style={{ fontSize: 14, color: T.gray, textAlign: "center", padding: 30 }}>
          No session found — complete earlier steps first.
        </div>
        <div style={{ display: "flex", justifyContent: "center", marginTop: 12 }}>
          <Btn onClick={onBack}>← Back</Btn>
        </div>
      </Card>
    )
  }

  return (
    <div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <Card>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>Step 5 — Pipeline Runner</div>
            <div style={{ fontSize: 12, color: T.textSoft }}>
              Run the 20-phase content pipeline for your accepted keywords.
              {acceptedCount > 0 && <span> <strong>{acceptedCount}</strong> keywords accepted.</span>}
            </div>
          </div>
          {pipelineMode === "select" && (
            <Btn onClick={onBack} small>← Back</Btn>
          )}
        </div>

        {/* Pillar selector */}
        {pipelineMode === "select" && (
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
              Select pillars to process ({allPillars.length} available):
            </div>
            {allPillars.length === 0 ? (
              <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 14 }}>
                No pillars found — complete Steps 1–3 first to discover pillars.
              </div>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
                {allPillars.map(p => {
                  const info       = pillarMap[p]
                  const isSelected = selectedPillars.includes(p)
                  const inUniverse = !!info
                  return (
                    <button
                      key={p}
                      onClick={() => setSelectedPillars(prev =>
                        prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]
                      )}
                      style={{
                        padding: "7px 14px", borderRadius: 8, fontSize: 12, cursor: "pointer",
                        border:  `1px solid ${isSelected ? T.teal : T.border}`,
                        background: isSelected ? T.tealLight : "#fff",
                        color:  isSelected ? T.teal : T.text,
                        fontWeight: isSelected ? 600 : 400,
                      }}
                    >
                      {p}
                      {info && (
                        <span style={{ marginLeft: 6, fontSize: 10, color: isSelected ? T.teal : T.textSoft }}>
                          ({info.accepted || 0}✓{info.total ? `/${info.total}` : ""})
                        </span>
                      )}
                      {!inUniverse && (
                        <span style={{ marginLeft: 4, fontSize: 10, color: T.textSoft }}>(strategy)</span>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <Btn small onClick={() => setSelectedPillars(allPillars)}>Select All ({allPillars.length})</Btn>
              <Btn small onClick={() => setSelectedPillars([])}>Clear</Btn>
              <Btn variant="teal" onClick={launchPipeline} disabled={!selectedPillars.length}>
                Launch Pipeline ({selectedPillars.length} selected) →
              </Btn>
            </div>
          </div>
        )}

        {/* Running / done state */}
        {(pipelineMode === "running" || pipelineMode === "done") && (
          <div>
            {/* Run status chips */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
              {pipelineRuns.map(run => {
                const statusColor = run.status === "complete" ? "#065f46"
                                  : run.status === "error"    ? "#991b1b"
                                  : run.status === "running"  ? "#1e40af"
                                  : T.text
                const statusBg    = run.status === "complete" ? "#d1fae5"
                                  : run.status === "error"    ? "#fee2e2"
                                  : run.status === "running"  ? "#dbeafe"
                                  : T.grayLight
                const displayStatus = run.status === "running" && run.currentPhase
                  ? `running ${run.currentPhase}`
                  : run.status
                return (
                  <div key={run.run_id} style={{
                    padding: "6px 12px", borderRadius: 8, fontSize: 12,
                    background: statusBg, color: statusColor,
                    border: `1px solid ${T.border}`,
                    display: "flex", alignItems: "center", gap: 6,
                  }}>
                    {(run.status === "queued" || run.status === "running") && <Spinner />}
                    <span style={{ fontWeight: 600 }}>{run.pillar}</span>: {displayStatus}
                  </div>
                )
              })}
            </div>

            <LiveConsole
              logs={pipelineLogs}
              running={pipelineMode === "running"}
              title="PIPELINE CONSOLE"
            />

            {pipelineMode === "done" && (
              <div style={{ marginTop: 16, display: "flex", gap: 10, alignItems: "center" }}>
                <div style={{ fontSize: 13, color: T.green, fontWeight: 600 }}>
                  ✓ All pipeline runs complete
                </div>
                <Btn variant="teal" onClick={onComplete}>
                  Next: Final Review →
                </Btn>
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ padding: "8px 12px", background: "#fee2e2", borderRadius: 8, marginTop: 10, fontSize: 12, color: "#991b1b" }}>
            {error}
          </div>
        )}
      </Card>
    </div>
  )
}
