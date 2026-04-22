/**
 * PhaseDeliver — merged Phase7 (Internal Links) + Phase8 (Calendar) + Phase9 (Strategy).
 * Single "Run All" button executes all 3 phases sequentially.
 * Tabs are for navigation only; run logic is orchestrated by the parent.
 * onComplete fires after Strategy finishes (pipeline complete).
 */
import React, { useState, useCallback, useEffect, useRef } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, StatsRow, usePhaseRunner, PhaseResult, NotificationList } from "./shared"
import Phase8 from "./Phase8"
import Phase9 from "./Phase9"

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

/* ── Phase7 Links Section (extracted from PhaseGraphLinks) ─────────── */

function LinksSection({ projectId, sessionId, onComplete, autoRun, hideRunButton }) {
  const { links, setLinks } = useKw2Store()
  const p7 = usePhaseRunner("P7")
  const [linkStats, setLinkStats] = useState(null)
  const [filterType, setFilterType] = useState("")

  useEffect(() => {
    async function load() {
      try {
        const lData = await api.getLinks(projectId, sessionId)
        if (lData.items) setLinks(lData.items)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  const runLinks = useCallback(async () => {
    p7.setLoading(true)
    p7.setError(null)
    p7.log("Generating internal link map...", "info")
    try {
      const data = await api.runPhase7(projectId, sessionId)
      setLinkStats(data.links)
      const lData = await api.getLinks(projectId, sessionId)
      setLinks(lData.items || [])
      const total = data.links?.links || 0
      p7.log(`Complete: ${total} internal links generated`, "success")
      p7.toast(`Internal linking: ${total} links mapped`, "success")
      onComplete()
    } catch (e) {
      p7.setError(e.message)
      p7.log(`Failed: ${e.message}`, "error")
      p7.toast(`Phase 7 failed: ${e.message}`, "error")
    }
    p7.setLoading(false)
  }, [projectId, sessionId])

  // autoRun: respond to prop changes — LinksSection is on the default tab so it's pre-mounted
  // when Run All fires. Empty [] would not re-fire when autoRun changes false→true.
  useEffect(() => { if (autoRun) runLinks() }, [autoRun]) // eslint-disable-line react-hooks/exhaustive-deps

  const linkTypes = [...new Set(links.map((l) => l.link_type).filter(Boolean))]
  const filteredLinks = filterType ? links.filter((l) => l.link_type === filterType) : links

  return (
    <Card
      title="Internal Linking"
      actions={hideRunButton ? null : <RunButton onClick={runLinks} loading={p7.loading}>Build Link Map</RunButton>}
    >
      {p7.error && <p style={{ color: "#dc2626", fontSize: 13 }}>{p7.error}</p>}

      {linkStats && (
        <StatsRow items={[
          { label: "Total Links", value: linkStats.links || 0, color: "#10b981" },
          ...(linkStats.by_type
            ? Object.entries(linkStats.by_type).map(([t, c]) => ({ label: t, value: c, color: "#3b82f6" }))
            : []),
        ]} />
      )}

      {linkTypes.length > 0 && (
        <select
          style={{ padding: "4px 8px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 12, marginBottom: 8 }}
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          <option value="">All types ({links.length})</option>
          {linkTypes.map((t) => (
            <option key={t} value={t}>{t} ({links.filter((l) => l.link_type === t).length})</option>
          ))}
        </select>
      )}

      {filteredLinks.length > 0 && (
        <div style={{ maxHeight: 300, overflow: "auto", fontSize: 12 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #e5e7eb" }}>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>From</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>To</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Anchor</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Type</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Placement</th>
              </tr>
            </thead>
            <tbody>
              {filteredLinks.slice(0, 50).map((l, i) => (
                <tr key={l.id || i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                  <td style={{ padding: "4px 6px", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis" }}>{l.from_page}</td>
                  <td style={{ padding: "4px 6px", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis" }}>{l.to_page}</td>
                  <td style={{ padding: "4px 6px" }}>{l.anchor_text}</td>
                  <td style={{ padding: "4px 6px" }}><Badge>{l.link_type}</Badge></td>
                  <td style={{ padding: "4px 6px", color: "#6b7280" }}>{l.placement}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredLinks.length > 50 && (
            <p style={{ color: "#9ca3af", fontSize: 11, marginTop: 4 }}>Showing 50 of {filteredLinks.length}</p>
          )}
        </div>
      )}

      {linkStats && (
        <PhaseResult
          phaseNum={7}
          stats={[{ label: "Total Links", value: linkStats.links || 0, color: "#10b981" }]}
          onNext={null}
        />
      )}

      <NotificationList notifications={p7.notifications} />
    </Card>
  )
}

/* ── Persistent run state helpers ──────────────────────────────────────── */

const _lsKeyDEL  = (sid) => `kw2_del_run_${sid}`
const _saveRunDEL = (sid, rs, ps, cs) => {
  try { localStorage.setItem(_lsKeyDEL(sid), JSON.stringify({ runStep: rs, pendingStep: ps, completedSteps: cs })) } catch {}
}
const _loadRunDEL = (sid) => {
  try { const s = JSON.parse(localStorage.getItem(_lsKeyDEL(sid)) || "null"); if (s && typeof s === "object") return s } catch {}
  return {}
}
const _clearRunDEL = (sid) => { try { localStorage.removeItem(_lsKeyDEL(sid)) } catch {} }

/* ── Step tab with status indicator ─────────────────────────────────────── */

function StepTabBtnDel({ icon, label, step, tab: activeTab, runStep, pendingStep, completedSteps, onSelect }) {
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

const _BTN_DEL = {
  pause:  { padding: "5px 12px", borderRadius: 6, border: "1px solid #fcd34d", background: "#fffbeb",  color: "#92400e", fontSize: 12, cursor: "pointer", fontWeight: 600 },
  stop:   { padding: "5px 12px", borderRadius: 6, border: "1px solid #fca5a5", background: "#fff1f2",  color: "#b91c1c", fontSize: 12, cursor: "pointer", fontWeight: 600 },
  resume: { padding: "5px 14px", borderRadius: 6, border: "none",              background: "#10b981",  color: "#fff",    fontSize: 12, cursor: "pointer", fontWeight: 700 },
  rerun:  { padding: "5px 12px", borderRadius: 6, border: "1px solid #c7d2fe", background: "#eef2ff",  color: "#3730a3", fontSize: 12, cursor: "pointer", fontWeight: 600 },
  clear:  { padding: "5px 12px", borderRadius: 6, border: "1px solid #d1d5db", background: "#f9fafb",  color: "#374151", fontSize: 12, cursor: "pointer" },
}

/* ── Main PhaseDeliver Component ───────────────────────────────────── */

export default function PhaseDeliver({ projectId, sessionId, onComplete }) {
  // Restore persisted state — survives page refresh
  const [runStep,        setRunStep]        = useState(() => _loadRunDEL(sessionId).runStep || null)
  const [pendingStep,    setPendingStep]    = useState(() => _loadRunDEL(sessionId).pendingStep || null)
  const [completedSteps, setCompletedSteps] = useState(() => {
    const s = _loadRunDEL(sessionId); return Array.isArray(s.completedSteps) ? s.completedSteps : []
  })
  const [tab, setTab] = useState(() => {
    const s = _loadRunDEL(sessionId); return s.runStep || s.pendingStep || "links"
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
    _saveRunDEL(sessionId, runStep, pendingStep, completedSteps)
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

  const onLinksDone    = useCallback(() => _advanceOrHalt("links",    "calendar", false), [_advanceOrHalt])
  const onCalendarDone = useCallback(() => _advanceOrHalt("calendar", "strategy", false), [_advanceOrHalt])
  const onStrategyDone = useCallback(() => _advanceOrHalt("strategy", null,       true),  [_advanceOrHalt])

  // ── User action handlers ──
  const handleRunAll = useCallback(() => {
    pauseRef.current = false; stopRef.current = false
    setPauseRequested(false); setStopRequested(false)
    setCompletedSteps([]); setPendingStep(null); setRunStep("links")
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
    _clearRunDEL(sessionId)
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
          <StepTabBtnDel icon="🔗" label="Links"    step="links"    {...tabProps} />
          <StepTabBtnDel icon="📅" label="Calendar" step="calendar" {...tabProps} />
          <StepTabBtnDel icon="📋" label="Strategy" step="strategy" {...tabProps} />
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
                <button onClick={handlePause} style={_BTN_DEL.pause}>⏸ Pause</button>
              )}
              {!stopRequested && (
                <button onClick={handleStop} style={_BTN_DEL.stop}>⏹ Stop</button>
              )}
            </>
          ) : paused ? (
            <>
              <span style={{ fontSize: 11, color: "#d97706", fontWeight: 600, whiteSpace: "nowrap" }}>
                ⏸ Paused — next: {pendingStep}
              </span>
              <button onClick={handleResume} style={_BTN_DEL.resume}>▶ Resume from {pendingStep}</button>
              <button onClick={handleRunAll} style={_BTN_DEL.rerun}>↺ Re-run All</button>
              <button onClick={handleClear}  style={_BTN_DEL.clear}>✕ Clear</button>
            </>
          ) : (
            <>
              <RunButton onClick={handleRunAll}>
                {allDone ? "↺ Re-run All" : "▶ Run All"}
              </RunButton>
              {completedSteps.length > 0 && !allDone && (
                <button onClick={handleClear} style={_BTN_DEL.clear}>✕ Clear</button>
              )}
            </>
          )}
        </div>
        <style>{`@keyframes kw2spin { to { transform: rotate(360deg) } }`}</style>
      </div>

      {tab === "links" && (
        <LinksSection
          projectId={projectId} sessionId={sessionId}
          onComplete={onLinksDone}
          autoRun={runStep === "links"} hideRunButton
        />
      )}
      {tab === "calendar" && (
        <Phase8
          projectId={projectId} sessionId={sessionId}
          onComplete={onCalendarDone} onNext={onCalendarDone}
          autoRun={runStep === "calendar"} hideRunButton
        />
      )}
      {tab === "strategy" && (
        <Phase9
          projectId={projectId} sessionId={sessionId}
          onComplete={onStrategyDone}
          autoRun={runStep === "strategy"} hideRunButton
        />
      )}
    </div>
  )
}
