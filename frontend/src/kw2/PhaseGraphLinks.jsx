/**
 * PhaseGraphLinks — merged Phase6 (Knowledge Graph) + Phase7 (Internal Linking).
 * Two sections with independent run buttons.
 * onComplete fires after Phase 7 (internal links) completes.
 */
import React, { useState, useCallback, useEffect } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, StatsRow, usePhaseRunner, PhaseResult, NotificationList } from "./shared"

export default function PhaseGraphLinks({ projectId, sessionId, onComplete }) {
  const { graph, setGraph, links, setLinks, setActivePhase } = useKw2Store()

  // Phase 6 state
  const p6 = usePhaseRunner("P6")
  const [graphStats, setGraphStats] = useState(null)

  // Phase 7 state
  const p7 = usePhaseRunner("P7")
  const [linkStats, setLinkStats] = useState(null)
  const [filterType, setFilterType] = useState("")

  // Load existing data on mount
  useEffect(() => {
    async function load() {
      try {
        const gData = await api.getGraph(projectId, sessionId)
        if (gData.graph && Object.keys(gData.graph).length) setGraph(gData.graph)
      } catch { /* ignore */ }
      try {
        const lData = await api.getLinks(projectId, sessionId)
        if (lData.items) setLinks(lData.items)
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
    } catch (e) {
      p6.setError(e.message)
      p6.log(`Failed: ${e.message}`, "error")
      p6.toast(`Phase 6 failed: ${e.message}`, "error")
    }
    p6.setLoading(false)
  }, [projectId, sessionId])

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
      setActivePhase(8)
    } catch (e) {
      p7.setError(e.message)
      p7.log(`Failed: ${e.message}`, "error")
      p7.toast(`Phase 7 failed: ${e.message}`, "error")
    }
    p7.setLoading(false)
  }, [projectId, sessionId])

  const edgeTypes = graph ? Object.entries(graph) : []
  const linkTypes = [...new Set(links.map((l) => l.link_type).filter(Boolean))]
  const filteredLinks = filterType ? links.filter((l) => l.link_type === filterType) : links

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

      {/* ── Section A: Knowledge Graph ─────────────────────────────────── */}
      <Card
        title="Phase 6: Knowledge Graph"
        actions={<RunButton onClick={runGraph} loading={p6.loading}>Build Graph</RunButton>}
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

      {/* ── Section B: Internal Linking ────────────────────────────────── */}
      <Card
        title="Phase 7: Internal Linking"
        actions={<RunButton onClick={runLinks} loading={p7.loading}>Build Link Map</RunButton>}
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
            onNext={() => setActivePhase(8)}
          />
        )}

        <NotificationList notifications={p7.notifications} />
      </Card>
    </div>
  )
}
