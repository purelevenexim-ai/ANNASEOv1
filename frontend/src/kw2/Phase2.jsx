/**
 * Phase 2 — Keyword Universe Generation.
 * 5-layer pipeline: seeds → rules → suggest → competitor → AI expand.
 * SSE streaming with per-layer progress bars, notifications, debug console.
 */
import React, { useState, useCallback, useRef } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, ProgressBar, StatsRow, usePhaseRunner, PhaseResult, NotificationList, ConsolePanel } from "./shared"

const LAYERS = ["seeds", "rules", "suggest", "competitor", "ai_expand"]
const LAYER_LABELS = {
  seeds: "Seed Keywords",
  rules: "Rule Templates",
  suggest: "Google Suggest",
  competitor: "Competitor Crawl",
  ai_expand: "AI Expansion",
}

export default function Phase2({ projectId, sessionId, onComplete }) {
  const { setUniverseCount, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P2")

  const [result, setResult] = useState(null)
  const [layerCounts, setLayerCounts] = useState({})
  const [activeLayer, setActiveLayer] = useState(null)
  const cancelRef = useRef(null)

  const runStream = useCallback(async () => {
    setLoading(true)
    setError(null)
    setLayerCounts({})
    setActiveLayer(null)
    setResult(null)
    log("Generating keyword universe (streaming)...", "info")

    cancelRef.current = api.streamPhase2(projectId, sessionId, (ev) => {
      if (ev.type === "progress") {
        setActiveLayer(ev.source)
        // IMPORTANT: suggest + ai_expand emit multiple events (one per pillar)
        // so we ACCUMULATE instead of overwrite
        setLayerCounts((prev) => ({
          ...prev,
          [ev.source]: (prev[ev.source] || 0) + (ev.count || 0),
        }))
        log(`[${LAYER_LABELS[ev.source] || ev.source}] +${ev.count} keywords${ev.pillar ? ` (${ev.pillar})` : ""}`, "progress")
      }
      if (ev.type === "complete") {
        setResult({ total: ev.total, rejected: ev.rejected })
        setUniverseCount(ev.total || 0)
        setActiveLayer(null)
        log(`Universe complete: ${ev.total} generated, ${ev.rejected || 0} rejected`, "success")
        toast(`Keyword universe: ${ev.total} keywords generated`, "success")
      }
      if (ev.done && !ev.error) {
        setLoading(false)
        onComplete()
      }
      if (ev.error) {
        setError("Stream error: " + (ev.message || "unknown"))
        log(`Stream error: ${ev.message || "unknown"}`, "error")
        toast("Phase 2 streaming failed", "error")
        setLoading(false)
      }
    })
  }, [projectId, sessionId])

  const runSync = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    log("Generating keyword universe (batch)...", "info")
    try {
      const data = await api.runPhase2(projectId, sessionId)
      const u = data.universe || {}
      setResult(u)
      setUniverseCount(u.total || 0)
      if (u.sources) setLayerCounts(u.sources)
      log(`Batch complete: ${u.total || 0} keywords, ${u.rejected || 0} rejected`, "success")
      toast(`Keyword universe: ${u.total || 0} keywords generated`, "success")
      onComplete()
      setActivePhase(3)
    } catch (e) {
      setError(e.message)
      log(`Batch failed: ${e.message}`, "error")
      toast(`Phase 2 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  const loadExisting = useCallback(async () => {
    try {
      const data = await api.getUniverse(projectId, sessionId)
      if (data.count > 0) {
        setResult({ total: data.count })
        setUniverseCount(data.count || 0)
      }
    } catch { /* ignore */ }
  }, [projectId, sessionId])

  React.useEffect(() => { loadExisting() }, [])

  const completedLayers = LAYERS.filter((l) => layerCounts[l] > 0).length

  return (
    <Card
      title="Phase 2: Keyword Universe"
      actions={
        <div style={{ display: "flex", gap: 8 }}>
          <RunButton onClick={runStream} loading={loading}>Stream</RunButton>
          <RunButton onClick={runSync} loading={loading} variant="secondary">Batch</RunButton>
        </div>
      }
    >
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 10 }}>
        5-layer pipeline: seeds, rule templates, Google Suggest, competitor crawl, and AI expansion.
      </p>

      {error && <p style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>{error}</p>}

      {/* Live progress during streaming */}
      {loading && (
        <div style={{ marginBottom: 12 }}>
          <ProgressBar value={completedLayers} max={LAYERS.length} label="Overall Progress" color="#10b981" animated />
          {LAYERS.map((layer) => {
            const count = layerCounts[layer] || 0
            const isActive = activeLayer === layer
            return (
              <div key={layer} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 12, width: 130, color: isActive ? "#3b82f6" : "#6b7280", fontWeight: isActive ? 600 : 400 }}>
                  {LAYER_LABELS[layer]}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ height: 6, background: "#e5e7eb", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{
                      height: "100%",
                      width: count > 0 ? "100%" : isActive ? "60%" : "0%",
                      background: count > 0 ? "#10b981" : isActive ? "#3b82f6" : "#e5e7eb",
                      borderRadius: 3,
                      transition: "width 300ms ease",
                      animation: isActive && !count ? "kw2pulse 1.5s ease infinite" : "none",
                    }} />
                  </div>
                </div>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#374151", width: 50, textAlign: "right" }}>
                  {count > 0 ? count : isActive ? "..." : ""}
                </span>
              </div>
            )
          })}
          <style>{`@keyframes kw2pulse { 0%,100%{opacity:.4} 50%{opacity:1} }`}</style>
        </div>
      )}

      {/* Results after completion */}
      {result && !loading && (
        <>
          <StatsRow items={[
            { label: "Total Generated", value: result.total || 0, color: "#10b981" },
            { label: "Rejected (dupes)", value: result.rejected || 0, color: "#ef4444" },
            ...Object.entries(layerCounts).map(([k, v]) => ({
              label: LAYER_LABELS[k] || k, value: v, color: "#3b82f6",
            })),
          ]} />
          <PhaseResult
            phaseNum={2}
            stats={[
              { label: "Total Keywords", value: result.total || 0, color: "#10b981" },
              { label: "Rejected", value: result.rejected || 0, color: "#ef4444" },
            ]}
            onNext={() => setActivePhase(3)}
          />
        </>
      )}

      <NotificationList notifications={notifications} title="Generation Events" />
      <ConsolePanel filterBadge="P2" />
    </Card>
  )
}
