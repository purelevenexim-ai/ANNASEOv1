/**
 * PhaseOrganize (v2) — Scoring, Clustering, Relations, Top-100.
 *
 * Interactive keyword graph + score dashboard + top-100 table.
 * SSE steps: scoring, clustering, cluster_validation, relations, top100, persist
 */
import React, { useState, useCallback, useEffect, useRef, useMemo } from "react"
import ForceGraph2D from "react-force-graph-2d"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, StatsRow, usePhaseRunner, ProgressBar, Badge, Spinner, NotificationList } from "./shared"
import DataTable from "./DataTable"

// ── Constants ───────────────────────────────────────────────────────────────

const ORGANIZE_STEPS = [
  { key: "scoring", label: "Scoring", icon: "📊" },
  { key: "clustering", label: "Clustering", icon: "🧩" },
  { key: "cluster_validation", label: "Validation", icon: "✅" },
  { key: "relations", label: "Relations", icon: "🔗" },
  { key: "top100", label: "Top 100", icon: "🏆" },
  { key: "persist", label: "Saving", icon: "💾" },
]

const PILLAR_COLORS = [
  "#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ef4444",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
]

const EDGE_COLORS = {
  sibling: "#3b82f6",
  cross_cluster: "#10b981",
  cross_pillar: "#f59e0b",
}

const INTENT_COLORS = {
  informational: "#3b82f6",
  commercial: "#f59e0b",
  transactional: "#10b981",
  navigational: "#8b5cf6",
}

function getPillarColor(pillar, pillarList) {
  const idx = (pillarList || []).indexOf(pillar)
  return PILLAR_COLORS[idx >= 0 ? idx % PILLAR_COLORS.length : 0]
}

// ── Intent Pie Chart (CSS-based) ────────────────────────────────────────────

function IntentPie({ distribution }) {
  if (!distribution || !Object.keys(distribution).length) return null
  const entries = Object.entries(distribution)
  const total = entries.reduce((s, [, v]) => s + v, 0)
  if (!total) return null

  let cumulative = 0
  const segments = entries.map(([intent, count]) => {
    const pct = (count / total) * 100
    const start = cumulative
    cumulative += pct
    return { intent, count, pct, start }
  })

  const gradientParts = segments.map((s) => {
    const color = INTENT_COLORS[s.intent] || "#9ca3af"
    return `${color} ${s.start}% ${s.start + s.pct}%`
  })

  return (
    <div style={{ marginBottom: 16 }}>
      <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: "#374151" }}>Intent Distribution</h4>
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div
          style={{
            width: 120, height: 120, borderRadius: "50%",
            background: `conic-gradient(${gradientParts.join(", ")})`,
            flexShrink: 0,
          }}
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {segments.map((s) => (
            <div key={s.intent} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
              <span style={{
                width: 10, height: 10, borderRadius: 2, flexShrink: 0,
                background: INTENT_COLORS[s.intent] || "#9ca3af",
              }} />
              <span style={{ color: "#374151", fontWeight: 500 }}>{s.intent}</span>
              <span style={{ color: "#9ca3af" }}>{s.count} ({s.pct.toFixed(1)}%)</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Node Detail Panel ───────────────────────────────────────────────────────

function NodeDetail({ node, onClose }) {
  if (!node) return null
  return (
    <div style={{
      position: "absolute", top: 12, right: 12, width: 280,
      background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8,
      padding: 14, boxShadow: "0 4px 12px rgba(0,0,0,.1)", zIndex: 10,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontWeight: 600, fontSize: 14 }}>{node.keyword || node.label || node.id}</span>
        <button onClick={onClose} style={{ border: "none", background: "none", cursor: "pointer", fontSize: 16, color: "#9ca3af" }}>×</button>
      </div>
      <div style={{ fontSize: 12, color: "#6b7280", display: "flex", flexDirection: "column", gap: 4 }}>
        {node.pillar && <div><b>Pillar:</b> {node.pillar}</div>}
        {node.score != null && <div><b>Score:</b> {Number(node.score).toFixed(1)}</div>}
        {node.intent && <div><b>Intent:</b> {node.intent}</div>}
        {node.cluster && <div><b>Cluster:</b> {node.cluster}</div>}
        {node.volume != null && <div><b>Volume:</b> {Number(node.volume).toLocaleString()}</div>}
        {node.difficulty != null && <div><b>Difficulty:</b> {node.difficulty}</div>}
        {node.top100 && <Badge color="yellow">Top 100</Badge>}
      </div>
    </div>
  )
}

// ── Graph Component ─────────────────────────────────────────────────────────

function KeywordGraph({ graphData, pillarList, filters, onNodeClick }) {
  const graphRef = useRef()
  const containerRef = useRef()
  const [dimensions, setDimensions] = useState({ width: 700, height: 450 })

  useEffect(() => {
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect()
      setDimensions({ width: Math.max(rect.width - 4, 400), height: 450 })
    }
  }, [])

  const filteredData = useMemo(() => {
    if (!graphData?.nodes) return { nodes: [], links: [] }

    let nodes = graphData.nodes
    if (filters.pillar) nodes = nodes.filter((n) => n.pillar === filters.pillar)
    if (filters.intent) nodes = nodes.filter((n) => n.intent === filters.intent)
    if (filters.top100Only) nodes = nodes.filter((n) => n.top100)

    const nodeIds = new Set(nodes.map((n) => n.id))
    const links = (graphData.edges || graphData.links || []).filter(
      (e) => nodeIds.has(e.source?.id || e.source) && nodeIds.has(e.target?.id || e.target)
    )

    return { nodes, links }
  }, [graphData, filters])

  const nodeCanvasObject = useCallback((node, ctx) => {
    const size = Math.max(3, Math.min(12, (node.score || 30) / 10))
    const color = getPillarColor(node.pillar, pillarList)

    // Gold ring for top100
    if (node.top100) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 2.5, 0, 2 * Math.PI)
      ctx.strokeStyle = "#f59e0b"
      ctx.lineWidth = 2
      ctx.stroke()
    }

    ctx.beginPath()
    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()

    // Label for larger nodes
    if (size > 5) {
      ctx.font = "3px sans-serif"
      ctx.textAlign = "center"
      ctx.fillStyle = "#374151"
      ctx.fillText(node.keyword || node.label || "", node.x, node.y + size + 5)
    }
  }, [pillarList])

  return (
    <div ref={containerRef} style={{ position: "relative", border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden", background: "#fafafa" }}>
      <ForceGraph2D
        ref={graphRef}
        graphData={filteredData}
        width={dimensions.width}
        height={dimensions.height}
        nodeCanvasObject={nodeCanvasObject}
        linkColor={(link) => EDGE_COLORS[link.type || link.relation] || "#d1d5db"}
        linkWidth={1}
        linkDirectionalParticles={0}
        onNodeClick={(node) => onNodeClick(node)}
        cooldownTicks={80}
        nodeLabel={(n) => `${n.keyword || n.label || n.id} (${n.pillar || "?"})`}
      />
    </div>
  )
}

// ── Top 100 Table ───────────────────────────────────────────────────────────

function Top100Table({ data, pillarList }) {
  const [activePillar, setActivePillar] = useState(null)
  const pillars = [...new Set((data || []).map((kw) => kw.pillar).filter(Boolean))]
  const filtered = activePillar ? (data || []).filter((kw) => kw.pillar === activePillar) : (data || [])

  return (
    <div style={{ marginTop: 16 }}>
      <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Top 100 Keywords</h4>
      <div style={{ display: "flex", gap: 4, marginBottom: 10, flexWrap: "wrap" }}>
        <button
          onClick={() => setActivePillar(null)}
          style={{
            padding: "4px 10px", borderRadius: 5, fontSize: 11, border: !activePillar ? "2px solid #3b82f6" : "1px solid #e5e7eb",
            background: !activePillar ? "#eff6ff" : "#fff", color: !activePillar ? "#3b82f6" : "#6b7280",
            cursor: "pointer", fontWeight: !activePillar ? 600 : 400,
          }}
        >
          All ({(data || []).length})
        </button>
        {pillars.map((p, i) => {
          const count = (data || []).filter((kw) => kw.pillar === p).length
          return (
            <button
              key={p}
              onClick={() => setActivePillar(p)}
              style={{
                padding: "4px 10px", borderRadius: 5, fontSize: 11,
                border: activePillar === p ? `2px solid ${getPillarColor(p, pillarList)}` : "1px solid #e5e7eb",
                background: activePillar === p ? `${getPillarColor(p, pillarList)}15` : "#fff",
                color: activePillar === p ? getPillarColor(p, pillarList) : "#6b7280",
                cursor: "pointer", fontWeight: activePillar === p ? 600 : 400,
              }}
            >
              {p} ({count})
            </button>
          )
        })}
      </div>
      <div style={{ overflowX: "auto", maxHeight: 400 }}>
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #e5e7eb", background: "#f9fafb" }}>
              <th style={thStyle}>#</th>
              <th style={thStyle}>Keyword</th>
              <th style={thStyle}>Pillar</th>
              <th style={thStyle}>Score</th>
              <th style={thStyle}>Intent</th>
              <th style={thStyle}>Cluster</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((kw, i) => (
              <tr key={kw.id || i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={tdStyle}>{i + 1}</td>
                <td style={{ ...tdStyle, fontWeight: 500 }}>{kw.keyword || kw.term}</td>
                <td style={tdStyle}>
                  <Badge color="blue">{kw.pillar || "—"}</Badge>
                </td>
                <td style={{ ...tdStyle, fontWeight: 600, color: "#3b82f6" }}>
                  {(kw.score ?? kw.final_score ?? 0).toFixed(1)}
                </td>
                <td style={tdStyle}>{kw.intent || "—"}</td>
                <td style={{ ...tdStyle, fontSize: 11, color: "#6b7280" }}>{kw.cluster || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const thStyle = { textAlign: "left", padding: "6px 10px", fontSize: 11, color: "#6b7280", fontWeight: 600 }
const tdStyle = { padding: "5px 10px", fontSize: 12 }

// ── Cluster Breakdown ───────────────────────────────────────────────────────

function ClusterBreakdown({ summary }) {
  const clusters = summary?.clusters || summary?.cluster_breakdown || []
  if (!clusters.length) return null

  return (
    <div style={{ marginTop: 16 }}>
      <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Cluster Breakdown</h4>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {clusters.slice(0, 30).map((c, i) => (
          <div key={c.id || c.name || i} style={{
            padding: "8px 12px", borderRadius: 8, border: "1px solid #e5e7eb",
            background: "#f9fafb", minWidth: 120,
          }}>
            <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 2 }}>{c.name || c.label || `Cluster ${i + 1}`}</div>
            <div style={{ fontSize: 11, color: "#6b7280" }}>{c.count || c.size || 0} keywords</div>
            {c.pillar && <Badge color="blue">{c.pillar}</Badge>}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Component ──────────────────────────────────────────────────────────

export default function PhaseOrganize({ projectId, sessionId, onComplete }) {
  const { aiProvider, setActivePhase, goNextPhase } = useKw2Store()
  const { loading, setLoading, streamLoading, setStreamLoading, error, setError, notifications, log, toast } = usePhaseRunner("Organize")

  const [stepStatus, setStepStatus] = useState({})
  const [progress, setProgress] = useState({ current: 0, total: ORGANIZE_STEPS.length })
  const [done, setDone] = useState(false)
  const [summary, setSummary] = useState(null)
  const [graphData, setGraphData] = useState(null)
  const [top100, setTop100] = useState([])
  const [pillarList, setPillarList] = useState([])
  const [selectedNode, setSelectedNode] = useState(null)
  const [graphFilters, setGraphFilters] = useState({ pillar: null, intent: null, top100Only: false })
  const closeRef = useRef(null)

  const loadResults = useCallback(async () => {
    try {
      const [summaryData, graphRes, top100Data] = await Promise.all([
        api.v2OrganizeSummary(projectId, sessionId).catch(() => null),
        api.v2Graph(projectId, sessionId).catch(() => null),
        api.v2Top100(projectId, sessionId).catch(() => null),
      ])
      if (summaryData) setSummary(summaryData)
      if (graphRes) {
        setGraphData(graphRes)
        const pillars = [...new Set((graphRes.nodes || []).map((n) => n.pillar).filter(Boolean))]
        setPillarList(pillars)
      }
      if (top100Data) setTop100(Array.isArray(top100Data) ? top100Data : top100Data.keywords || [])
    } catch (e) {
      log(`Failed to load results: ${e.message}`, "error")
    }
  }, [projectId, sessionId])

  const runStream = useCallback(async () => {
    setStreamLoading(true)
    setError(null)
    setDone(false)
    setStepStatus({})
    setProgress({ current: 0, total: ORGANIZE_STEPS.length })
    log("Starting organize (streaming)...", "info")

    const close = api.v2OrganizeStream(projectId, sessionId, (evt) => {
      if (evt.error) {
        setError(evt.message || "Organize failed")
        log(`Error: ${evt.message}`, "error")
        setStreamLoading(false)
        return
      }

      if (evt.step || evt.layer) {
        const step = evt.step || evt.layer
        setStepStatus((prev) => ({ ...prev, [step]: evt.status || "running" }))
        if (evt.status === "complete" || evt.status === "done") {
          setProgress((prev) => ({ ...prev, current: Math.min(prev.current + 1, prev.total) }))
        }
        log(`${step}: ${evt.message || evt.status || "processing"}`, evt.status === "error" ? "error" : "progress")
      }

      if (evt.done) {
        setStreamLoading(false)
        setDone(true)
        setProgress((prev) => ({ ...prev, current: prev.total }))
        log("Organize complete!", "success")
        toast("Organize finished", "success")
        loadResults()
      }
    }, aiProvider)

    closeRef.current = close
  }, [projectId, sessionId, aiProvider])

  const runSync = useCallback(async () => {
    setLoading(true)
    setError(null)
    log("Running organize (sync)...", "info")
    try {
      await api.v2Organize(projectId, sessionId, { ai_provider: aiProvider })
      setDone(true)
      log("Organize complete", "success")
      toast("Organize complete", "success")
      await loadResults()
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId, aiProvider])

  // Load existing results on mount (e.g. when revisiting the phase)
  useEffect(() => { loadResults() }, [loadResults])

  useEffect(() => {
    return () => { if (closeRef.current) closeRef.current() }
  }, [])

  const isRunning = loading || streamLoading

  // Extract intent distribution from summary
  const intentDist = summary?.intent_distribution || summary?.intents || null

  return (
    <Card
      title="Organize — Score, Cluster & Relate"
      actions={
        <div style={{ display: "flex", gap: 6 }}>
          <RunButton onClick={runStream} loading={streamLoading} disabled={loading}>
            Stream Organize
          </RunButton>
          <RunButton onClick={runSync} loading={loading} disabled={streamLoading} variant="secondary">
            Sync
          </RunButton>
        </div>
      }
    >
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>
        Scores keywords, validates clusters, builds relations, and selects the Top 100.
      </p>

      {error && <p style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>⚠ {error}</p>}

      {/* SSE Progress */}
      {(streamLoading || done) && (
        <div style={{ marginBottom: 16 }}>
          <ProgressBar
            value={progress.current}
            max={progress.total}
            label="Organize Progress"
            color="#8b5cf6"
            animated={streamLoading}
          />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {ORGANIZE_STEPS.map((step) => {
              const status = stepStatus[step.key]
              const bg = status === "complete" || status === "done"
                ? "#dcfce7"
                : status === "running"
                  ? "#ede9fe"
                  : status === "error"
                    ? "#fee2e2"
                    : "#f3f4f6"
              const fg = status === "complete" || status === "done"
                ? "#166534"
                : status === "running"
                  ? "#6b21a8"
                  : status === "error"
                    ? "#991b1b"
                    : "#9ca3af"
              return (
                <span
                  key={step.key}
                  style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    padding: "3px 10px", borderRadius: 12, fontSize: 11,
                    background: bg, color: fg, fontWeight: status === "running" ? 600 : 400,
                  }}
                >
                  {step.icon} {step.label}
                  {status === "running" && <span className="kw2-spin" style={{ display: "inline-block", width: 10, height: 10, border: "2px solid #c4b5fd", borderTop: "2px solid #8b5cf6", borderRadius: "50%" }} />}
                  {(status === "complete" || status === "done") && " ✓"}
                </span>
              )
            })}
            <style>{`.kw2-spin { animation: kw2spin .7s linear infinite; } @keyframes kw2spin { to { transform: rotate(360deg) } }`}</style>
          </div>
        </div>
      )}

      {/* Summary Stats */}
      {summary && (
        <StatsRow items={[
          { label: "Keywords", value: summary.total_keywords || summary.total || 0, color: "#3b82f6" },
          { label: "Clusters", value: summary.cluster_count || summary.clusters?.length || 0, color: "#8b5cf6" },
          { label: "Top 100", value: top100.length, color: "#f59e0b" },
          { label: "Avg Score", value: summary.avg_score ? Number(summary.avg_score).toFixed(1) : "—", color: "#10b981" },
        ]} />
      )}

      {/* Intent Distribution */}
      {intentDist && <IntentPie distribution={intentDist} />}

      {/* Graph */}
      {graphData && graphData.nodes?.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Keyword Graph</h4>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {/* Pillar filter */}
              <select
                value={graphFilters.pillar || ""}
                onChange={(e) => setGraphFilters((f) => ({ ...f, pillar: e.target.value || null }))}
                style={{ padding: "3px 8px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 11 }}
              >
                <option value="">All Pillars</option>
                {pillarList.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              {/* Intent filter */}
              <select
                value={graphFilters.intent || ""}
                onChange={(e) => setGraphFilters((f) => ({ ...f, intent: e.target.value || null }))}
                style={{ padding: "3px 8px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 11 }}
              >
                <option value="">All Intents</option>
                {Object.keys(INTENT_COLORS).map((i) => <option key={i} value={i}>{i}</option>)}
              </select>
              {/* Top100 toggle */}
              <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "#6b7280", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={graphFilters.top100Only}
                  onChange={(e) => setGraphFilters((f) => ({ ...f, top100Only: e.target.checked }))}
                />
                Top 100 only
              </label>
            </div>
          </div>

          {/* Graph legend */}
          <div style={{ display: "flex", gap: 12, marginBottom: 8, fontSize: 11, color: "#6b7280", flexWrap: "wrap" }}>
            <span><b>Edges:</b></span>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 14, height: 3, background: EDGE_COLORS.sibling, display: "inline-block" }} /> Sibling
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 14, height: 3, background: EDGE_COLORS.cross_cluster, display: "inline-block" }} /> Cross-cluster
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 14, height: 3, background: EDGE_COLORS.cross_pillar, display: "inline-block" }} /> Cross-pillar
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 10, height: 10, border: "2px solid #f59e0b", borderRadius: "50%", display: "inline-block" }} /> Top 100
            </span>
          </div>

          <div style={{ position: "relative" }}>
            <KeywordGraph
              graphData={graphData}
              pillarList={pillarList}
              filters={graphFilters}
              onNodeClick={setSelectedNode}
            />
            <NodeDetail node={selectedNode} onClose={() => setSelectedNode(null)} />
          </div>
        </div>
      )}

      {/* Top 100 Table */}
      {top100.length > 0 && <Top100Table data={top100} pillarList={pillarList} />}

      {/* Top 100 — DataTable with bulk actions */}
      {top100.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: "#374151" }}>Top 100 — Actions</h4>
          <DataTable
            columns={[
              { key: "keyword", label: "Keyword", sortable: true, searchable: true },
              { key: "final_score", label: "Score", sortable: true, type: "number", decimals: 2 },
              { key: "intent", label: "Intent", sortable: true, filterable: true, type: "badge", editable: true, options: ["commercial", "informational", "navigational"] },
              { key: "role", label: "Role", sortable: true, filterable: true, type: "badge" },
              { key: "pillar", label: "Pillar", sortable: true, filterable: true },
              { key: "status", label: "Status", sortable: true, filterable: true, type: "badge", editable: true, options: ["candidate", "approved", "rejected"] },
            ]}
            data={top100.map((kw, i) => ({
              ...kw,
              id: kw.id || `top_${i}`,
              pillar: Array.isArray(kw.pillars) ? kw.pillars[0] || "—" : kw.pillar || "—",
            }))}
            rowKey="id"
            bulkActions={[
              { label: "Approve", color: "#10b981", action: async (ids) => {
                try {
                  await api.v2BulkApprove(projectId, sessionId, ids, "approve")
                  loadResults()
                } catch {}
              }},
              { label: "Reject", color: "#ef4444", action: async (ids) => {
                try {
                  await api.v2BulkApprove(projectId, sessionId, ids, "reject")
                  loadResults()
                } catch {}
              }},
            ]}
            onRowEdit={async (rowId, field, value) => {
              try {
                await api.v2BulkUpdate(projectId, sessionId, [rowId], { [field]: value })
                loadResults()
              } catch {}
            }}
          />
        </div>
      )}

      {/* Cluster Breakdown */}
      {summary && <ClusterBreakdown summary={summary} />}

      {/* Complete action */}
      {done && (
        <div style={{ marginTop: 16, padding: "10px 16px", background: "#f0fdf4", borderRadius: 8, border: "1px solid #86efac", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 18 }}>✓</span>
            <span style={{ fontWeight: 600, color: "#166534", fontSize: 14 }}>Organize Complete</span>
          </div>
          <button
            onClick={async () => {
              try { await api.updatePhaseStatus(projectId, sessionId, "organize", "done") } catch { /* non-fatal */ }
              if (onComplete) onComplete()
              const next = goNextPhase("ORGANIZE")
              setActivePhase(next || "APPLY")
            }}
            style={{
              background: "#10b981", color: "#fff", border: "none",
              borderRadius: 6, padding: "6px 16px", fontWeight: 600,
              fontSize: 13, cursor: "pointer",
            }}
          >
            Continue to Apply →
          </button>
        </div>
      )}

      <NotificationList notifications={notifications} />

    </Card>
  )
}
