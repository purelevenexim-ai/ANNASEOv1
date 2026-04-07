/**
 * Phase 4 — Scoring + Clustering.
 */
import React, { useState, useCallback } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, StatsRow, usePhaseRunner, PhaseResult, NotificationList, ConsolePanel } from "./shared"

export default function Phase4({ projectId, sessionId, onComplete }) {
  const { setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P4")
  const [result, setResult] = useState(null)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    log("Scoring + clustering keywords...", "info")
    try {
      const data = await api.runPhase4(projectId, sessionId)
      setResult(data)
      const scored = data.scoring?.scored || 0
      const clusters = data.clustering?.clusters || 0
      log(`Complete: ${scored} scored, ${clusters} clusters formed`, "success")
      toast(`Scoring complete: ${scored} keywords into ${clusters} clusters`, "success")
      onComplete()
      setActivePhase(5)
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
      toast(`Phase 4 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  return (
    <Card title="Phase 4: Score & Cluster" actions={<RunButton onClick={run} loading={loading}>Score + Cluster</RunButton>}>
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 10 }}>
        Composite scoring (relevance, intent, volume, commercial, buyer readiness) + semantic clustering.
      </p>

      {error && <p style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>{error}</p>}

      {result && (
        <>
          <StatsRow items={[
            { label: "Keywords Scored", value: result.scoring?.scored || 0, color: "#3b82f6" },
            { label: "Avg Score", value: (result.scoring?.avg_score || 0).toFixed(1), color: "#10b981" },
            { label: "Clusters", value: result.clustering?.clusters || 0, color: "#8b5cf6" },
            { label: "Unclustered", value: result.clustering?.unclustered || 0, color: "#6b7280" },
          ]} />
          {result.scoring?.score_distribution && (
            <div style={{ marginBottom: 8, fontSize: 12 }}>
              <strong>Distribution:</strong>
              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                {Object.entries(result.scoring.score_distribution).map(([range, count]) => (
                  <span key={range} style={{ background: "#f3f4f6", padding: "2px 8px", borderRadius: 4 }}>{range}: {count}</span>
                ))}
              </div>
            </div>
          )}
          <PhaseResult
            phaseNum={4}
            stats={[
              { label: "Scored", value: result.scoring?.scored || 0, color: "#3b82f6" },
              { label: "Clusters", value: result.clustering?.clusters || 0, color: "#8b5cf6" },
            ]}
            onNext={() => setActivePhase(5)}
          />
        </>
      )}

      <NotificationList notifications={notifications} />
      <ConsolePanel filterBadge="P4" />
    </Card>
  )
}
