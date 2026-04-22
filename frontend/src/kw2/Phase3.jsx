/**
 * Phase 3 — Keyword Validation (v2).
 * 6-pass filter: rule → pre-score → per-pillar AI → dedup → balance.
 * SSE streaming with per-pillar progress, smart early-stop, pre-score summary.
 */
import React, { useState, useCallback, useRef } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, ProgressBar, StatsRow, usePhaseRunner, PhaseResult, NotificationList } from "./shared"
import DataTable from "./DataTable"

const PASSES = ["rule_filter", "prescore", "ai_batch", "dedup", "balance"]
const PASS_LABELS = {
  rule_filter: "Rule Filter",
  prescore: "Pre-Score Engine",
  ai_batch: "AI Validation",
  dedup: "Semantic Dedup",
  balance: "Category Balance",
}

export default function Phase3({ projectId, sessionId, onComplete, onSwitchToReview }) {
  const { setValidatedCount, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P3")

  const [result, setResult] = useState(null)
  const [passInfo, setPassInfo] = useState({})
  const [activePass, setActivePass] = useState(null)
  const [pillarProgress, setPillarProgress] = useState({})
  const [pillarSummary, setPillarSummary] = useState(null)
  const [activePillar, setActivePillar] = useState(null)
  const [keywords, setKeywords] = useState([])
  const cancelRef = useRef(null)

  // Cleanup SSE stream on unmount
  React.useEffect(() => {
    return () => { if (cancelRef.current) cancelRef.current() }
  }, [])

  const loadKeywords = useCallback(async () => {
    try {
      const data = await api.getValidated(projectId, sessionId)
      const kws = data.items || data.keywords || data || []
      setKeywords(Array.isArray(kws) ? kws : [])
    } catch { /* ignore */ }
  }, [projectId, sessionId])

  const runStream = useCallback(async () => {
    setLoading(true)
    setError(null)
    setPassInfo({})
    setActivePass(null)
    setPillarProgress({})
    setPillarSummary(null)
    setActivePillar(null)
    setResult(null)
    log("Validating keywords (streaming)...", "info")

    cancelRef.current = api.streamPhase3(projectId, sessionId, (ev) => {
      // Pass-level events
      if (ev.type === "phase") {
        setActivePass(ev.name)
        const removed = ev.rejected || ev.removed || 0
        setPassInfo((prev) => ({ ...prev, [ev.name]: { rejected: removed, remaining: ev.remaining, accepted: ev.accepted, threshold: ev.threshold } }))
        if (ev.name === "prescore") {
          log(`[Pre-Score] ${removed} rejected (below ${ev.threshold || 45}), ${ev.remaining} sent to AI`, "progress")
        } else if (ev.name === "ai_batch") {
          log(`[AI] ${ev.accepted || 0} accepted, ${ev.rejected || 0} rejected`, "progress")
        } else {
          log(`[${PASS_LABELS[ev.name] || ev.name}] ${removed} removed, ${ev.remaining ?? "?"} remaining`, "progress")
        }
      }

      // Pillar summary (after pre-score)
      if (ev.type === "pillar_summary") {
        setPillarSummary(ev.pillars || {})
        log(`Pillars: ${Object.entries(ev.pillars || {}).map(([p, c]) => `${p}(${c})`).join(", ")}`, "info")
      }

      // Per-pillar events
      if (ev.type === "pillar_start") {
        setActivePillar(ev.pillar)
        setActivePass("ai_batch")
        setPillarProgress((prev) => ({
          ...prev,
          [ev.pillar]: { total: ev.total_batches, current: 0, accepted: 0, status: "running", keywords: ev.total_keywords },
        }))
        log(`[${ev.pillar}] Starting AI validation: ${ev.total_keywords} keywords, ${ev.total_batches} batches`, "info")
      }
      if (ev.type === "pillar_batch") {
        setPillarProgress((prev) => ({
          ...prev,
          [ev.pillar]: {
            ...prev[ev.pillar],
            current: ev.batch,
            accepted: ev.pillar_accepted,
            rate: ev.rate,
          },
        }))
        const pct = Math.round(((ev.batch || 0) / Math.max(ev.total_batches || 1, 1)) * 100)
        log(`[${ev.pillar}] Batch ${ev.batch}/${ev.total_batches} (${pct}%) · accepted ${ev.pillar_accepted}, rate ${Math.round((ev.rate || 0) * 100)}%`, "progress")
      }
      if (ev.type === "pillar_early_stop") {
        setPillarProgress((prev) => ({
          ...prev,
          [ev.pillar]: { ...prev[ev.pillar], status: "early_stop", avgRate: ev.avg_rate },
        }))
        log(`[${ev.pillar}] Early stop: avg acceptance ${Math.round((ev.avg_rate || 0) * 100)}%`, "warn")
      }
      if (ev.type === "pillar_complete") {
        setPillarProgress((prev) => ({
          ...prev,
          [ev.pillar]: { ...prev[ev.pillar], status: "done", accepted: ev.accepted, rejected: ev.rejected },
        }))
        setActivePillar(null)
        log(`[${ev.pillar}] Done: ${ev.accepted} accepted, ${ev.rejected} rejected`, "success")
      }

      // Completion
      if (ev.type === "complete") {
        setResult({ validated: ev.validated, total_rejected: ev.total_rejected, prescore_rejected: ev.prescore_rejected })
        setValidatedCount(ev.validated || 0)
        setActivePass(null)
        setActivePillar(null)
        log(`Validation complete: ${ev.validated} validated, ${ev.total_rejected || 0} total rejected`, "success")
        toast(`Validation complete: ${ev.validated} keywords passed`, "success")
      }
      if (ev.done && !ev.error) {
        setLoading(false)
        onComplete()
        loadKeywords()
      }
      if (ev.error) {
        setError("Stream error: " + (ev.message || ev.msg || "unknown"))
        log(`Stream error: ${ev.message || ev.msg || "unknown"}`, "error")
        toast("Phase 3 streaming failed", "error")
        setLoading(false)
      }
    })
  }, [projectId, sessionId])

  const runSync = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    log("Validating keywords (batch)...", "info")
    try {
      const data = await api.runPhase3(projectId, sessionId)
      const v = data.validation || {}
      setResult(v)
      setValidatedCount(v.validated_count || v.accepted || 0)
      log(`Batch complete: ${v.accepted || 0} validated`, "success")
      toast(`Validation: ${v.accepted || 0} keywords passed`, "success")
      onComplete()
      await loadKeywords()
      if (onSwitchToReview) onSwitchToReview(); else setActivePhase("REVIEW")
    } catch (e) {
      setError(e.message)
      log(`Batch failed: ${e.message}`, "error")
      toast(`Phase 3 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  const loadExisting = useCallback(async () => {
    try {
      const data = await api.getValidated(projectId, sessionId)
      if (data.count > 0) {
        setResult({ validated: data.count })
        setValidatedCount(data.count || 0)
        await loadKeywords()  // populate table on refresh — no re-run needed
      }
    } catch { /* ignore */ }
  }, [projectId, sessionId, loadKeywords])

  React.useEffect(() => { loadExisting() }, [])

  const completedPasses = PASSES.filter((p) => passInfo[p]).length
  const pillarNames = Object.keys(pillarProgress)

  return (
    <Card
      title="Phase 3: Validation & Filtering"
      actions={
        <div style={{ display: "flex", gap: 8 }}>
          <RunButton onClick={runStream} loading={loading}>Stream</RunButton>
          <RunButton onClick={runSync} loading={loading} variant="secondary">Batch</RunButton>
        </div>
      }
    >
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 10 }}>
        6-pass filter: rule-based, pre-score engine, per-pillar AI validation, semantic dedup, category balance.
      </p>

      {error && <p style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>{error}</p>}

      {/* Progress during streaming */}
      {loading && (
        <div style={{ marginBottom: 12 }}>
          <ProgressBar value={completedPasses} max={PASSES.length} label="Validation Progress" color="#8b5cf6" animated />

          {/* Pass checklist */}
          {PASSES.map((pass) => {
            const info = passInfo[pass]
            const isActive = activePass === pass
            const done = !!info
            return (
              <div key={pass} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 12, width: 150, color: done ? "#10b981" : isActive ? "#8b5cf6" : "#6b7280", fontWeight: isActive || done ? 600 : 400 }}>
                  {done ? "✓ " : isActive ? "▶ " : ""}{PASS_LABELS[pass]}
                </span>
                {done && pass === "prescore" && (
                  <>
                    <span style={{ fontSize: 11, color: "#ef4444" }}>-{info.rejected}</span>
                    <span style={{ fontSize: 11, color: "#6b7280" }}>({info.remaining} → AI)</span>
                  </>
                )}
                {done && pass !== "prescore" && <span style={{ fontSize: 11, color: "#ef4444" }}>-{info.rejected || info.removed || 0}</span>}
                {done && info.remaining != null && pass !== "prescore" && <span style={{ fontSize: 11, color: "#6b7280" }}>({info.remaining} left)</span>}
                {isActive && !done && <span style={{ fontSize: 11, color: "#8b5cf6" }}>processing...</span>}
              </div>
            )
          })}

          {/* Per-pillar progress */}
          {pillarNames.length > 0 && (
            <div style={{ marginTop: 12, padding: "10px 12px", background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 8 }}>Per-Pillar AI Validation</div>
              {pillarNames.map((pn) => {
                const pp = pillarProgress[pn]
                const isActive = activePillar === pn
                const isDone = pp.status === "done" || pp.status === "early_stop"
                return (
                  <div key={pn} style={{ marginBottom: 8 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                      <span style={{ fontSize: 12, fontWeight: isActive ? 600 : 400, color: isDone ? "#10b981" : isActive ? "#8b5cf6" : "#6b7280" }}>
                        {isDone ? "✓ " : isActive ? "▶ " : ""}{pn}
                        {pp.status === "early_stop" && <span style={{ fontSize: 10, color: "#f59e0b", marginLeft: 4 }}>(early stop)</span>}
                      </span>
                      <span style={{ fontSize: 11, color: "#6b7280" }}>
                        {pp.accepted || 0} accepted{pp.total ? ` · ${pp.current || 0}/${pp.total} batches` : ""}
                      </span>
                    </div>
                    {(isActive || isDone) && pp.total > 0 && (
                      <ProgressBar value={pp.current || 0} max={pp.total} color={isDone ? "#10b981" : "#3b82f6"} />
                    )}
                  </div>
                )
              })}
            </div>
          )}

          <style>{`@keyframes kw2pulse { 0%,100%{opacity:.4} 50%{opacity:1} }`}</style>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <>
          <StatsRow items={[
            { label: "Validated", value: result.validated || result.accepted || 0, color: "#10b981" },
            { label: "Rejected", value: result.total_rejected || 0, color: "#ef4444" },
            ...(result.prescore_rejected ? [{ label: "Pre-Score Rejected", value: result.prescore_rejected, color: "#f59e0b" }] : []),
            ...Object.entries(passInfo).map(([k, v]) => ({
              label: PASS_LABELS[k] || k, value: `-${v.rejected || v.removed || 0}`, color: "#6b7280",
            })),
          ]} />

          {/* Per-pillar summary — prefer live keywords data (includes rule_classify bypass) */}
          {(() => {
            if (keywords.length > 0) {
              // Count from actual loaded keywords: covers rule_classified + AI-accepted
              const pm = {}
              keywords.forEach((k) => { const p = k.pillar || "—"; pm[p] = (pm[p] || 0) + 1 })
              return (
                <div style={{ marginTop: 8, marginBottom: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 4 }}>Pillar Results</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {Object.entries(pm).sort((a, b) => b[1] - a[1]).map(([pn, cnt]) => (
                      <div key={pn} style={{ padding: "4px 10px", borderRadius: 6, background: "#f0fdf4", border: "1px solid #bbf7d0", fontSize: 12 }}>
                        <span style={{ fontWeight: 600 }}>{pn}</span>: {cnt} accepted
                      </div>
                    ))}
                  </div>
                </div>
              )
            }
            // Fallback to streaming pillarProgress (during or just after a run before keywords load)
            if (pillarNames.length === 0) return null
            return (
              <div style={{ marginTop: 8, marginBottom: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 4 }}>Pillar Results</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {pillarNames.map((pn) => {
                    const pp = pillarProgress[pn]
                    return (
                      <div key={pn} style={{ padding: "4px 10px", borderRadius: 6, background: "#f0fdf4", border: "1px solid #bbf7d0", fontSize: 12 }}>
                        <span style={{ fontWeight: 600 }}>{pn}</span>: {pp.accepted || 0} accepted
                        {pp.status === "early_stop" && <span style={{ color: "#f59e0b" }}> (early stop)</span>}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })()}

          {/* Validated keywords table with bulk actions */}
          {keywords.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Validated Keywords ({keywords.length})</h4>
                <button
                  onClick={loadKeywords}
                  style={{ padding: "4px 10px", borderRadius: 5, border: "1px solid #d1d5db", background: "#fff", fontSize: 11, cursor: "pointer" }}
                >
                  Refresh
                </button>
              </div>
              <DataTable
                columns={[
                  { key: "keyword", label: "Keyword", sortable: true, searchable: true },
                  { key: "pillar", label: "Pillar", sortable: true, filterable: true },
                  { key: "intent", label: "Intent", sortable: true, filterable: true, type: "badge", editable: true, options: ["commercial", "informational", "navigational"] },
                  { key: "score", label: "Score", sortable: true, type: "number" },
                  { key: "status", label: "Status", sortable: true, filterable: true, type: "badge", editable: true, options: ["approved", "rejected", "candidate"] },
                  { key: "source", label: "Source", sortable: true, filterable: true },
                ]}
                data={keywords.map((k, i) => ({
                  ...k,
                  id: k.id || `vkw_${i}`,
                  pillar: Array.isArray(k.pillars) ? k.pillars[0] || k.pillar || "—" : k.pillar || "—",
                  score: k.final_score || k.commercial_score || k.score || 0,
                }))}
                rowKey="id"
                bulkActions={[
                  { label: "Approve", color: "#10b981", action: async (ids) => {
                    await Promise.all(ids.map((id) =>
                      api.updateKeyword(projectId, sessionId, id, { status: "approved" }).catch(() => {})
                    ))
                    await loadKeywords()
                  }},
                  { label: "Reject", color: "#ef4444", confirm: "Reject selected keywords?", action: async (ids) => {
                    await Promise.all(ids.map((id) =>
                      api.updateKeyword(projectId, sessionId, id, { status: "rejected" }).catch(() => {})
                    ))
                    await loadKeywords()
                  }},
                  { label: "Delete", color: "#6b7280", confirm: "Delete selected keywords permanently?", action: async (ids) => {
                    await api.v2BulkDelete(projectId, sessionId, ids).catch(() => {})
                    await loadKeywords()
                  }},
                ]}
                onRowEdit={async (rowId, field, value) => {
                  await api.updateKeyword(projectId, sessionId, rowId, { [field]: value }).catch(() => {})
                  await loadKeywords()
                }}
                emptyText="No validated keywords loaded"
              />
            </div>
          )}

          <PhaseResult
            phaseNum={3}
            stats={[
              { label: "Validated", value: result.validated || result.accepted || 0, color: "#10b981" },
              { label: "Rejected", value: result.total_rejected || 0, color: "#ef4444" },
            ]}
            onNext={() => onSwitchToReview ? onSwitchToReview() : setActivePhase("REVIEW")}
            nextLabel="Review Keywords →"
          />
        </>
      )}

      <NotificationList notifications={notifications} title="Validation Events" />
    </Card>
  )
}
