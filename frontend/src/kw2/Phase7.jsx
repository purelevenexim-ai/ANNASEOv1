/**
 * Phase 7 — Internal Linking.
 */
import React, { useState, useCallback, useEffect } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, StatsRow, usePhaseRunner, PhaseResult, NotificationList } from "./shared"

export default function Phase7({ projectId, sessionId, onComplete }) {
  const { links, setLinks, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P7")
  const [stats, setStats] = useState(null)
  const [filterType, setFilterType] = useState("")

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    log("Generating internal link map...", "info")
    try {
      const data = await api.runPhase7(projectId, sessionId)
      setStats(data.links)
      const lData = await api.getLinks(projectId, sessionId)
      setLinks(lData.items || [])
      const total = data.links?.links || 0
      log(`Complete: ${total} internal links generated`, "success")
      toast(`Internal linking: ${total} links mapped`, "success")
      onComplete()
      setActivePhase(8)
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
      toast(`Phase 7 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  useEffect(() => {
    async function load() {
      try {
        const data = await api.getLinks(projectId, sessionId)
        if (data.items) setLinks(data.items)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  const linkTypes = [...new Set(links.map((l) => l.link_type).filter(Boolean))]
  const filtered = filterType ? links.filter((l) => l.link_type === filterType) : links

  return (
    <Card title="Phase 7: Internal Linking" actions={<RunButton onClick={run} loading={loading}>Build Link Map</RunButton>}>
      {error && <p style={{ color: "#dc2626", fontSize: 13 }}>{error}</p>}

      {stats && (
        <StatsRow items={[
          { label: "Total Links", value: stats.links || 0, color: "#10b981" },
          ...(stats.by_type
            ? Object.entries(stats.by_type).map(([t, c]) => ({ label: t, value: c, color: "#3b82f6" }))
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

      {filtered.length > 0 && (
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
              {filtered.slice(0, 50).map((l, i) => (
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
          {filtered.length > 50 && <p style={{ color: "#9ca3af", fontSize: 11, marginTop: 4 }}>Showing 50 of {filtered.length}</p>}
        </div>
      )}

      {stats && (
        <PhaseResult
          phaseNum={7}
          stats={[{ label: "Total Links", value: stats.links || 0, color: "#10b981" }]}
          onNext={() => setActivePhase(8)}
        />
      )}

      <NotificationList notifications={notifications} />
    </Card>
  )
}
