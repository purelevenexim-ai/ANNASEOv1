/**
 * PhaseExpand (v2) — Keyword Expansion + Cluster Review.
 *
 * Combines old Phase2 (generate) + Phase3 (validate) into a single super-phase.
 * SSE layers: seeds, rules, suggest, competitor, ai_expand, filter, normalize, validate, cluster
 */
import React, { useState, useCallback, useEffect, useRef } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, StatsRow, usePhaseRunner, ProgressBar, Badge, Spinner, NotificationList } from "./shared"
import DataTable from "./DataTable"

// ── Layer config ────────────────────────────────────────────────────────────

const EXPAND_LAYERS = [
  { key: "seeds", label: "Seed Keywords", icon: "🌱" },
  { key: "rules", label: "Rule Expansion", icon: "📐" },
  { key: "suggest", label: "Suggestions", icon: "💡" },
  { key: "competitor", label: "Competitor Mining", icon: "🔍" },
  { key: "ai_expand", label: "AI Expansion", icon: "🤖" },
  { key: "filter", label: "Filtering", icon: "🔽" },
  { key: "normalize", label: "Normalization", icon: "🔧" },
  { key: "validate", label: "Validation", icon: "✅" },
  { key: "cluster", label: "Clustering", icon: "📊" },
]

const PILLAR_COLORS = [
  "#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ef4444",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
]

function pillarColor(index) {
  return PILLAR_COLORS[index % PILLAR_COLORS.length]
}

// ── Cluster Review Sub-component ────────────────────────────────────────────

function ClusterReview({ clusters, pillars, onApprove, onReject, loading }) {
  const [activePillar, setActivePillar] = useState(null)
  const [selected, setSelected] = useState({})

  useEffect(() => {
    if (pillars?.length && !activePillar) setActivePillar(pillars[0])
  }, [pillars])

  const filtered = (clusters || []).filter(
    (c) => !activePillar || c.pillar === activePillar
  )

  const toggleCluster = (id) => {
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  const toggleAll = (checked) => {
    const next = {}
    filtered.forEach((c) => { next[c.id] = checked })
    setSelected((prev) => ({ ...prev, ...next }))
  }

  const selectedIds = Object.entries(selected).filter(([, v]) => v).map(([k]) => k)

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Cluster Review</h4>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            onClick={() => onApprove(selectedIds)}
            disabled={!selectedIds.length || loading}
            style={{
              padding: "5px 12px", borderRadius: 5, border: "none",
              background: selectedIds.length ? "#10b981" : "#d1d5db",
              color: "#fff", fontSize: 12, fontWeight: 600, cursor: selectedIds.length ? "pointer" : "not-allowed",
            }}
          >
            Approve ({selectedIds.length})
          </button>
          <button
            onClick={() => onReject(selectedIds)}
            disabled={!selectedIds.length || loading}
            style={{
              padding: "5px 12px", borderRadius: 5, border: "none",
              background: selectedIds.length ? "#ef4444" : "#d1d5db",
              color: "#fff", fontSize: 12, fontWeight: 600, cursor: selectedIds.length ? "pointer" : "not-allowed",
            }}
          >
            Reject ({selectedIds.length})
          </button>
        </div>
      </div>

      {/* Pillar tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 12, flexWrap: "wrap" }}>
        {(pillars || []).map((p, i) => (
          <button
            key={p}
            onClick={() => setActivePillar(p)}
            style={{
              padding: "5px 12px", borderRadius: 5, fontSize: 12, fontWeight: 500,
              border: activePillar === p ? `2px solid ${pillarColor(i)}` : "1px solid #e5e7eb",
              background: activePillar === p ? `${pillarColor(i)}15` : "#fff",
              color: activePillar === p ? pillarColor(i) : "#6b7280",
              cursor: "pointer",
            }}
          >
            {p}
          </button>
        ))}
      </div>

      {/* Select all */}
      <div style={{ marginBottom: 8 }}>
        <label style={{ fontSize: 12, color: "#6b7280", cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
          <input
            type="checkbox"
            onChange={(e) => toggleAll(e.target.checked)}
            checked={filtered.length > 0 && filtered.every((c) => selected[c.id])}
          />
          Select all in {activePillar || "view"}
        </label>
      </div>

      {/* Cluster cards */}
      {filtered.length === 0 && (
        <p style={{ fontSize: 13, color: "#9ca3af" }}>No clusters for this pillar.</p>
      )}
      {filtered.map((cluster) => (
        <div
          key={cluster.id}
          style={{
            border: selected[cluster.id] ? "2px solid #3b82f6" : "1px solid #e5e7eb",
            borderRadius: 8, padding: 12, marginBottom: 8,
            background: selected[cluster.id] ? "#eff6ff" : "#fff",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <input
              type="checkbox"
              checked={!!selected[cluster.id]}
              onChange={() => toggleCluster(cluster.id)}
            />
            <span style={{ fontWeight: 600, fontSize: 13 }}>{cluster.name || cluster.label || `Cluster ${cluster.id}`}</span>
            <Badge color="blue">{cluster.pillar}</Badge>
            <span style={{ fontSize: 11, color: "#9ca3af" }}>{(cluster.keywords || []).length} keywords</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, paddingLeft: 24 }}>
            {(cluster.keywords || []).slice(0, 20).map((kw, i) => (
              <span
                key={i}
                style={{
                  background: "#f3f4f6", border: "1px solid #e5e7eb", borderRadius: 10,
                  padding: "2px 8px", fontSize: 11, color: "#374151",
                }}
              >
                {typeof kw === "string" ? kw : kw.keyword || kw.term}
              </span>
            ))}
            {(cluster.keywords || []).length > 20 && (
              <span style={{ fontSize: 11, color: "#9ca3af" }}>+{cluster.keywords.length - 20} more</span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Manual Keyword Add Form ─────────────────────────────────────────────────

function AddKeywordForm({ projectId, sessionId, pillars, onAdded }) {
  const [keyword, setKeyword] = useState("")
  const [selectedPillars, setSelectedPillars] = useState([])
  const [adding, setAdding] = useState(false)

  const handleAdd = async () => {
    if (!keyword.trim()) return
    setAdding(true)
    try {
      await api.v2AddKeyword(projectId, sessionId, keyword.trim(), selectedPillars)
      setKeyword("")
      setSelectedPillars([])
      if (onAdded) onAdded()
    } catch (e) {
      console.error("Add keyword failed:", e)
    }
    setAdding(false)
  }

  return (
    <div style={{ marginTop: 16, padding: 12, background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>
      <h4 style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 600 }}>Add Manual Keyword</h4>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label style={{ fontSize: 11, color: "#6b7280", display: "block", marginBottom: 3 }}>Keyword</label>
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="Enter keyword..."
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            style={{
              width: "100%", padding: "6px 10px", borderRadius: 5, border: "1px solid #d1d5db",
              fontSize: 13, outline: "none",
            }}
          />
        </div>
        <div style={{ minWidth: 150 }}>
          <label style={{ fontSize: 11, color: "#6b7280", display: "block", marginBottom: 3 }}>Pillars</label>
          <select
            multiple
            value={selectedPillars}
            onChange={(e) => setSelectedPillars(Array.from(e.target.selectedOptions, (o) => o.value))}
            style={{
              width: "100%", padding: "4px 6px", borderRadius: 5, border: "1px solid #d1d5db",
              fontSize: 12, minHeight: 50,
            }}
          >
            {(pillars || []).map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <button
          onClick={handleAdd}
          disabled={adding || !keyword.trim()}
          style={{
            padding: "6px 16px", borderRadius: 5, border: "none",
            background: keyword.trim() ? "#3b82f6" : "#d1d5db",
            color: "#fff", fontWeight: 600, fontSize: 13,
            cursor: keyword.trim() ? "pointer" : "not-allowed",
          }}
        >
          {adding ? "Adding..." : "Add"}
        </button>
      </div>
    </div>
  )
}

// ── Keyword Pillar Move ─────────────────────────────────────────────────────

function KeywordPillarMove({ projectId, sessionId, pillars, keywords, onMoved }) {
  const [selectedKw, setSelectedKw] = useState("")
  const [targetPillar, setTargetPillar] = useState("")
  const [moving, setMoving] = useState(false)

  const handleMove = async () => {
    if (!selectedKw || !targetPillar) return
    setMoving(true)
    try {
      await api.v2MoveKeywordPillar(projectId, sessionId, selectedKw, [targetPillar])
      setSelectedKw("")
      setTargetPillar("")
      if (onMoved) onMoved()
    } catch (e) {
      console.error("Move keyword failed:", e)
    }
    setMoving(false)
  }

  const allKws = (keywords || []).slice(0, 200)

  return (
    <div style={{ marginTop: 12, padding: 12, background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>
      <h4 style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 600 }}>Move Keyword to Pillar</h4>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label style={{ fontSize: 11, color: "#6b7280", display: "block", marginBottom: 3 }}>Keyword</label>
          <select
            value={selectedKw}
            onChange={(e) => setSelectedKw(e.target.value)}
            style={{ width: "100%", padding: "6px 10px", borderRadius: 5, border: "1px solid #d1d5db", fontSize: 12 }}
          >
            <option value="">Select keyword...</option>
            {allKws.map((kw) => (
              <option key={kw.id || kw.keyword} value={kw.id}>
                {kw.keyword || kw.term} ({kw.pillar || "unassigned"})
              </option>
            ))}
          </select>
        </div>
        <div style={{ minWidth: 140 }}>
          <label style={{ fontSize: 11, color: "#6b7280", display: "block", marginBottom: 3 }}>Target Pillar</label>
          <select
            value={targetPillar}
            onChange={(e) => setTargetPillar(e.target.value)}
            style={{ width: "100%", padding: "6px 10px", borderRadius: 5, border: "1px solid #d1d5db", fontSize: 12 }}
          >
            <option value="">Select pillar...</option>
            {(pillars || []).map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <button
          onClick={handleMove}
          disabled={moving || !selectedKw || !targetPillar}
          style={{
            padding: "6px 16px", borderRadius: 5, border: "none",
            background: selectedKw && targetPillar ? "#8b5cf6" : "#d1d5db",
            color: "#fff", fontWeight: 600, fontSize: 13,
            cursor: selectedKw && targetPillar ? "pointer" : "not-allowed",
          }}
        >
          {moving ? "Moving..." : "Move"}
        </button>
      </div>
    </div>
  )
}

// ── Main Component ──────────────────────────────────────────────────────────

export default function PhaseExpand({ projectId, sessionId, onComplete }) {
  const { aiProvider, setActivePhase, goNextPhase } = useKw2Store()
  const { loading, setLoading, streamLoading, setStreamLoading, error, setError, notifications, log, toast } = usePhaseRunner("Expand")

  const [layerStatus, setLayerStatus] = useState({})
  const [progress, setProgress] = useState({ current: 0, total: EXPAND_LAYERS.length })
  const [expandDone, setExpandDone] = useState(false)
  const [clusters, setClusters] = useState([])
  const [pillars, setPillars] = useState([])
  const [allKeywords, setAllKeywords] = useState([])
  const [stats, setStats] = useState(null)
  const [reviewLoading, setReviewLoading] = useState(false)
  const closeRef = useRef(null)

  const loadClusters = useCallback(async () => {
    try {
      const data = await api.v2ExpandClusters(projectId, sessionId)
      setClusters(data.clusters || [])
      setPillars(data.pillars || [...new Set((data.clusters || []).map((c) => c.pillar).filter(Boolean))])
      setAllKeywords(data.keywords || [])
      setStats(data.stats || null)
    } catch (e) {
      log(`Failed to load clusters: ${e.message}`, "error")
    }
  }, [projectId, sessionId])

  const runStream = useCallback(async () => {
    setStreamLoading(true)
    setError(null)
    setExpandDone(false)
    setLayerStatus({})
    setProgress({ current: 0, total: EXPAND_LAYERS.length })
    log("Starting keyword expansion (streaming)...", "info")

    const close = api.v2ExpandStream(projectId, sessionId, (evt) => {
      if (evt.error) {
        setError(evt.message || "Expansion failed")
        log(`Error: ${evt.message}`, "error")
        setStreamLoading(false)
        return
      }

      if (evt.layer || evt.step) {
        const layer = evt.layer || evt.step
        setLayerStatus((prev) => ({ ...prev, [layer]: evt.status || "running" }))
        if (evt.status === "complete" || evt.status === "done") {
          setProgress((prev) => ({ ...prev, current: Math.min(prev.current + 1, prev.total) }))
        }
        log(`${layer}: ${evt.message || evt.status || "processing"}`, evt.status === "error" ? "error" : "progress")
      }

      if (evt.count || evt.keywords_added) {
        log(`+${evt.count || evt.keywords_added} keywords`, "info")
      }

      if (evt.done) {
        setStreamLoading(false)
        setExpandDone(true)
        setProgress((prev) => ({ ...prev, current: prev.total }))
        log("Expansion complete!", "success")
        toast("Keyword expansion finished", "success")
        loadClusters()
      }
    }, { aiProvider })

    closeRef.current = close
  }, [projectId, sessionId, aiProvider])

  const runSync = useCallback(async () => {
    setLoading(true)
    setError(null)
    log("Running keyword expansion (sync)...", "info")
    try {
      const data = await api.v2Expand(projectId, sessionId)
      setExpandDone(true)
      setStats(data.stats || null)
      log(`Expansion complete: ${data.total || "?"} keywords`, "success")
      toast("Expansion complete", "success")
      await loadClusters()
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  const handleApprove = useCallback(async (ids) => {
    if (!ids.length) return
    setReviewLoading(true)
    try {
      await api.v2ExpandReview(projectId, sessionId, ids, [])
      log(`Approved ${ids.length} clusters`, "success")
      toast(`Approved ${ids.length} clusters`)
      await loadClusters()
    } catch (e) {
      log(`Approve failed: ${e.message}`, "error")
    }
    setReviewLoading(false)
  }, [projectId, sessionId])

  const handleReject = useCallback(async (ids) => {
    if (!ids.length) return
    setReviewLoading(true)
    try {
      await api.v2ExpandReview(projectId, sessionId, [], ids)
      log(`Rejected ${ids.length} clusters`, "success")
      toast(`Rejected ${ids.length} clusters`)
      await loadClusters()
    } catch (e) {
      log(`Reject failed: ${e.message}`, "error")
    }
    setReviewLoading(false)
  }, [projectId, sessionId])

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => { if (closeRef.current) closeRef.current() }
  }, [])

  const isRunning = loading || streamLoading

  return (
    <Card
      title="Expand — Keyword Discovery & Clustering"
      actions={
        <div style={{ display: "flex", gap: 6 }}>
          <RunButton onClick={runStream} loading={streamLoading} disabled={loading}>
            Stream Expand
          </RunButton>
          <RunButton onClick={runSync} loading={loading} disabled={streamLoading} variant="secondary">
            Sync
          </RunButton>
        </div>
      }
    >
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>
        Discovers keywords via seeds, rules, suggestions, competitor mining, and AI expansion.
        Then filters, normalizes, validates, and clusters them by pillar.
      </p>

      {error && <p style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>⚠ {error}</p>}

      {/* SSE Progress */}
      {(streamLoading || expandDone) && (
        <div style={{ marginBottom: 16 }}>
          <ProgressBar
            value={progress.current}
            max={progress.total}
            label="Expansion Progress"
            color="#3b82f6"
            animated={streamLoading}
          />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {EXPAND_LAYERS.map((layer) => {
              const status = layerStatus[layer.key]
              const bg = status === "complete" || status === "done"
                ? "#dcfce7"
                : status === "running"
                  ? "#dbeafe"
                  : status === "error"
                    ? "#fee2e2"
                    : "#f3f4f6"
              const fg = status === "complete" || status === "done"
                ? "#166534"
                : status === "running"
                  ? "#1e40af"
                  : status === "error"
                    ? "#991b1b"
                    : "#9ca3af"
              return (
                <span
                  key={layer.key}
                  style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    padding: "3px 10px", borderRadius: 12, fontSize: 11,
                    background: bg, color: fg, fontWeight: status === "running" ? 600 : 400,
                  }}
                >
                  {layer.icon} {layer.label}
                  {status === "running" && <span className="kw2-spin" style={{ display: "inline-block", width: 10, height: 10, border: "2px solid #93c5fd", borderTop: "2px solid #3b82f6", borderRadius: "50%" }} />}
                  {(status === "complete" || status === "done") && " ✓"}
                </span>
              )
            })}
            <style>{`.kw2-spin { animation: kw2spin .7s linear infinite; } @keyframes kw2spin { to { transform: rotate(360deg) } }`}</style>
          </div>
        </div>
      )}

      {/* Stats */}
      {stats && (
        <StatsRow items={[
          { label: "Total Keywords", value: stats.total_keywords || stats.total || 0, color: "#3b82f6" },
          { label: "Clusters", value: stats.cluster_count || clusters.length, color: "#8b5cf6" },
          { label: "Pillars", value: pillars.length, color: "#10b981" },
          { label: "Avg/Cluster", value: stats.avg_per_cluster ? stats.avg_per_cluster.toFixed(1) : "—", color: "#f59e0b" },
        ]} />
      )}

      {/* Cluster review */}
      {expandDone && clusters.length > 0 && (
        <ClusterReview
          clusters={clusters}
          pillars={pillars}
          onApprove={handleApprove}
          onReject={handleReject}
          loading={reviewLoading}
        />
      )}

      {/* Manual keyword add */}
      {expandDone && (
        <AddKeywordForm
          projectId={projectId}
          sessionId={sessionId}
          pillars={pillars}
          onAdded={loadClusters}
        />
      )}

      {/* Keyword pillar move */}
      {expandDone && allKeywords.length > 0 && (
        <KeywordPillarMove
          projectId={projectId}
          sessionId={sessionId}
          pillars={pillars}
          keywords={allKeywords}
          onMoved={loadClusters}
        />
      )}

      {/* All keywords table with bulk actions */}
      {expandDone && allKeywords.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: "#374151" }}>All Keywords</h4>
          <DataTable
            columns={[
              { key: "keyword", label: "Keyword", sortable: true, searchable: true },
              { key: "intent", label: "Intent", sortable: true, filterable: true, type: "badge", editable: true, options: ["commercial", "informational", "navigational"] },
              { key: "role", label: "Role", sortable: true, filterable: true, type: "badge", editable: true, options: ["pillar", "supporting", "bridge"] },
              { key: "status", label: "Status", sortable: true, filterable: true, type: "badge", editable: true, options: ["candidate", "approved", "rejected"] },
              { key: "final_score", label: "Score", sortable: true, type: "number", decimals: 2 },
              { key: "ai_relevance", label: "Relevance", sortable: true, type: "number", decimals: 2 },
            ]}
            data={allKeywords.map((kw, i) => ({ ...kw, id: kw.id || `kw_${i}` }))}
            rowKey="id"
            bulkActions={[
              { label: "Approve", color: "#10b981", action: async (ids) => {
                try {
                  await api.v2BulkApprove(projectId, sessionId, ids, "approve")
                  loadClusters()
                } catch {}
              }},
              { label: "Reject", color: "#ef4444", action: async (ids) => {
                try {
                  await api.v2BulkApprove(projectId, sessionId, ids, "reject")
                  loadClusters()
                } catch {}
              }},
              { label: "Delete", color: "#6b7280", confirm: "Delete selected keywords?", action: async (ids) => {
                try {
                  await api.v2BulkDelete(projectId, sessionId, ids)
                  loadClusters()
                } catch {}
              }},
            ]}
            onRowEdit={async (rowId, field, value) => {
              try {
                await api.v2BulkUpdate(projectId, sessionId, [rowId], { [field]: value })
                loadClusters()
              } catch {}
            }}
          />
        </div>
      )}

      {/* Complete action */}
      {expandDone && (
        <div style={{ marginTop: 16, padding: "10px 16px", background: "#f0fdf4", borderRadius: 8, border: "1px solid #86efac", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 18 }}>✓</span>
            <span style={{ fontWeight: 600, color: "#166534", fontSize: 14 }}>Expand Complete</span>
          </div>
          <button
            onClick={async () => {
              try { await api.updatePhaseStatus(projectId, sessionId, "expand", "done") } catch { /* non-fatal */ }
              if (onComplete) onComplete()
              const next = goNextPhase("EXPAND")
              setActivePhase(next || "ORGANIZE")
            }}
            style={{
              background: "#10b981", color: "#fff", border: "none",
              borderRadius: 6, padding: "6px 16px", fontWeight: 600,
              fontSize: 13, cursor: "pointer",
            }}
          >
            Continue to Organize →
          </button>
        </div>
      )}

      <NotificationList notifications={notifications} />
    </Card>
  )
}
