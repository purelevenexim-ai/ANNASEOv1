/**
 * Phase 3 — Keyword Validation.
 * 4-pass filter: rule-based → AI batch → semantic dedup → category balance.
 * SSE streaming with per-pass progress, notifications and debug console.
 */
import React, { useState, useCallback, useRef } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, ProgressBar, StatsRow, usePhaseRunner, PhaseResult, NotificationList, ConsolePanel } from "./shared"

const PASSES = ["rule_filter", "ai_batch", "dedup", "balance"]
const PASS_LABELS = {
  rule_filter: "Rule Filter",
  ai_batch: "AI Batch Review",
  dedup: "Semantic Dedup",
  balance: "Category Balance",
}

export default function Phase3({ projectId, sessionId, onComplete }) {
  const { setValidatedCount, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P3")

  const [result, setResult] = useState(null)
  const [passInfo, setPassInfo] = useState({})
  const [activePass, setActivePass] = useState(null)
  const [aiBatch, setAiBatch] = useState({ current: 0, total: 0 })
  const cancelRef = useRef(null)

  const runStream = useCallback(async () => {
    setLoading(true)
    setError(null)
    setPassInfo({})
    setActivePass(null)
    setAiBatch({ current: 0, total: 0 })
    setResult(null)
    log("Validating keywords (streaming)...", "info")

    cancelRef.current = api.streamPhase3(projectId, sessionId, (ev) => {
      if (ev.type === "phase") {
        setActivePass(ev.name)
        if (ev.name === "ai_batch" && ev.total_batches) {
          setAiBatch({ current: ev.batch || 0, total: ev.total_batches })
          log(`[AI Batch] Batch ${ev.batch}/${ev.total_batches}, ${ev.accepted_so_far || 0} accepted`, "progress")
        } else {
          const removed = ev.rejected || ev.removed || 0
          setPassInfo((prev) => ({ ...prev, [ev.name]: { rejected: removed, remaining: ev.remaining } }))
          log(`[${PASS_LABELS[ev.name] || ev.name}] ${removed} removed, ${ev.remaining ?? "?"} remaining`, "progress")
        }
      }
      if (ev.type === "complete") {
        setResult({ validated: ev.validated, total_rejected: ev.total_rejected })
        setValidatedCount(ev.validated || 0)
        setActivePass(null)
        log(`Validation complete: ${ev.validated} validated, ${ev.total_rejected || 0} total rejected`, "success")
        toast(`Validation complete: ${ev.validated} keywords passed`, "success")
      }
      if (ev.done && !ev.error) {
        setLoading(false)
        onComplete()
      }
      if (ev.error) {
        setError("Stream error: " + (ev.message || "unknown"))
        log(`Stream error: ${ev.message || "unknown"}`, "error")
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
      setValidatedCount(v.validated_count || v.validated || 0)
      log(`Batch complete: ${v.validated_count || v.validated || 0} validated`, "success")
      toast(`Validation: ${v.validated_count || v.validated || 0} keywords passed`, "success")
      onComplete()
      setActivePhase("REVIEW")
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
      }
    } catch { /* ignore */ }
  }, [projectId, sessionId])

  React.useEffect(() => { loadExisting() }, [])

  const completedPasses = PASSES.filter((p) => passInfo[p]).length

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
        4-pass filter: rule-based, AI batch validation, TF-IDF semantic dedup, category balance.
      </p>

      {error && <p style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>{error}</p>}

      {/* Progress during streaming */}
      {loading && (
        <div style={{ marginBottom: 12 }}>
          <ProgressBar value={completedPasses} max={PASSES.length} label="Validation Progress" color="#8b5cf6" animated />

          {activePass === "ai_batch" && aiBatch.total > 0 && (
            <ProgressBar
              value={aiBatch.current}
              max={aiBatch.total}
              label={`AI Batch Review (${aiBatch.current}/${aiBatch.total})`}
              color="#3b82f6"
            />
          )}

          {PASSES.map((pass) => {
            const info = passInfo[pass]
            const isActive = activePass === pass
            const done = !!info
            return (
              <div key={pass} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 12, width: 140, color: done ? "#10b981" : isActive ? "#8b5cf6" : "#6b7280", fontWeight: isActive || done ? 600 : 400 }}>
                  {done ? "✓ " : isActive ? "▶ " : ""}{PASS_LABELS[pass]}
                </span>
                {done && <span style={{ fontSize: 11, color: "#ef4444" }}>-{info.rejected}</span>}
                {done && info.remaining != null && <span style={{ fontSize: 11, color: "#6b7280" }}>({info.remaining} left)</span>}
                {isActive && !done && <span style={{ fontSize: 11, color: "#8b5cf6" }}>processing...</span>}
              </div>
            )
          })}
          <style>{`@keyframes kw2pulse { 0%,100%{opacity:.4} 50%{opacity:1} }`}</style>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <>
          <StatsRow items={[
            { label: "Validated", value: result.validated || result.validated_count || 0, color: "#10b981" },
            { label: "Rejected", value: result.total_rejected || 0, color: "#ef4444" },
            ...Object.entries(passInfo).map(([k, v]) => ({
              label: PASS_LABELS[k] || k, value: `-${v.rejected}`, color: "#6b7280",
            })),
          ]} />
          <PhaseResult
            phaseNum={3}
            stats={[
              { label: "Validated", value: result.validated || result.validated_count || 0, color: "#10b981" },
              { label: "Rejected", value: result.total_rejected || 0, color: "#ef4444" },
            ]}
            onNext={() => setActivePhase("REVIEW")}
            nextLabel="Review Keywords →"
          />
        </>
      )}

      <NotificationList notifications={notifications} title="Validation Events" />
      <ConsolePanel filterBadge="P3" />
    </Card>
  )
}
