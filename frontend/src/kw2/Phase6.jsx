/**
 * Phase 6 — Knowledge Graph.
 */
import React, { useState, useCallback, useEffect } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, StatsRow, usePhaseRunner, PhaseResult, NotificationList, ConsolePanel } from "./shared"

export default function Phase6({ projectId, sessionId, onComplete }) {
  const { graph, setGraph, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P6")
  const [stats, setStats] = useState(null)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    log("Building knowledge graph...", "info")
    try {
      const data = await api.runPhase6(projectId, sessionId)
      setStats(data.graph)
      const gData = await api.getGraph(projectId, sessionId)
      setGraph(gData.graph)
      const edges = data.graph?.edges || 0
      log(`Complete: ${edges} edges, ${data.graph?.pillars || 0} pillars, ${data.graph?.clusters || 0} clusters`, "success")
      toast(`Knowledge graph: ${edges} edges created`, "success")
      onComplete()
      setActivePhase(7)
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
      toast(`Phase 6 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  useEffect(() => {
    async function load() {
      try {
        const data = await api.getGraph(projectId, sessionId)
        if (data.graph && Object.keys(data.graph).length) setGraph(data.graph)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  const edgeTypes = graph ? Object.entries(graph) : []

  return (
    <Card title="Phase 6: Knowledge Graph" actions={<RunButton onClick={run} loading={loading}>Build Graph</RunButton>}>
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 8 }}>
        Builds edges: keyword→cluster, sibling, cluster→pillar, pillar→universe, cross-cluster.
      </p>

      {error && <p style={{ color: "#dc2626", fontSize: 13 }}>{error}</p>}

      {stats && (
        <StatsRow items={[
          { label: "Total Edges", value: stats.edges || 0, color: "#10b981" },
          { label: "Pillars", value: stats.pillars || 0, color: "#3b82f6" },
          { label: "Clusters", value: stats.clusters || 0, color: "#8b5cf6" },
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

      {stats && (
        <PhaseResult
          phaseNum={6}
          stats={[
            { label: "Edges", value: stats.edges || 0, color: "#10b981" },
            { label: "Pillars", value: stats.pillars || 0, color: "#3b82f6" },
            { label: "Clusters", value: stats.clusters || 0, color: "#8b5cf6" },
          ]}
          onNext={() => setActivePhase(7)}
        />
      )}

      <NotificationList notifications={notifications} />
      <ConsolePanel filterBadge="P6" />
    </Card>
  )
}
