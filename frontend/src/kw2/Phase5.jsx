/**
 * Phase 5 — Content Tree + Top 100 Selection.
 */
import React, { useState, useCallback, useEffect } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, KeywordTable, StatsRow, usePhaseRunner, PhaseResult, NotificationList, ConsolePanel } from "./shared"

const INTENT_COLORS = {
  purchase: "#10b981", wholesale: "#8b5cf6", transactional: "#10b981",
  commercial: "#f59e0b", informational: "#9ca3af", navigational: "#3b82f6",
}

function TreeNode({ node, depth = 0 }) {
  const defaultOpen = depth <= 1  // universe and pillar open by default
  const [open, setOpen] = useState(defaultOpen)
  const [hover, setHover] = useState(false)

  const children = node.pillars || node.clusters || node.keywords || []
  const hasChildren = children.length > 0

  const NODE_STYLES = {
    universe: { icon: "🌐", color: "#3b82f6", fontWeight: 700, fontSize: 15 },
    pillar:   { icon: "🎯", color: "#10b981", fontWeight: 600, fontSize: 14 },
    cluster:  { icon: "📦", color: "#8b5cf6", fontWeight: 500, fontSize: 13 },
    keyword:  { icon: "🔑", color: "#f59e0b", fontWeight: 400, fontSize: 12 },
  }
  const s = NODE_STYLES[node.type] || NODE_STYLES.keyword

  return (
    <div style={{ marginLeft: depth * 18 }}>
      <div
        onClick={() => hasChildren && setOpen((v) => !v)}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{
          display: "flex", alignItems: "center", gap: 5,
          padding: "3px 6px", borderRadius: 5, cursor: hasChildren ? "pointer" : "default",
          background: hover ? "#f3f4f6" : "transparent",
          transition: "background 150ms",
          userSelect: "none",
        }}
      >
        <span style={{ fontSize: 10, color: "#9ca3af", width: 10 }}>
          {hasChildren ? (open ? "▼" : "▶") : "·"}
        </span>
        <span style={{ fontSize: 13 }}>{s.icon}</span>
        <span style={{ fontWeight: s.fontWeight, fontSize: s.fontSize, color: s.color }}>
          {node.name}
        </span>
        {node.intent && (
          <span style={{
            fontSize: 10, padding: "1px 5px", borderRadius: 3,
            background: INTENT_COLORS[node.intent] || "#9ca3af", color: "#fff", fontWeight: 500,
          }}>
            {node.intent}
          </span>
        )}
        {typeof node.score === "number" && (
          <span style={{ fontSize: 10, color: "#9ca3af", marginLeft: 2 }}>
            {node.score.toFixed(2)}
          </span>
        )}
        {node.mapped_page && (
          <a
            href={node.mapped_page}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            title={node.mapped_page}
            style={{ fontSize: 10, color: "#3b82f6", marginLeft: 2 }}
          >
            🔗
          </a>
        )}
        {hasChildren && (
          <span style={{ fontSize: 10, color: "#d1d5db", marginLeft: "auto" }}>
            {children.length}
          </span>
        )}
      </div>
      {open && hasChildren && (
        <div style={{ borderLeft: "1px dashed #e5e7eb", marginLeft: 16, paddingLeft: 2 }}>
          {children.map((child, i) => (
            <TreeNode key={i} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

function KeywordTree({ tree }) {
  if (!tree || !tree.universe) {
    return <p style={{ color: "#9ca3af", fontSize: 13 }}>No tree data. Run Phase 5 first.</p>
  }
  return (
    <div style={{ maxHeight: 480, overflowY: "auto", padding: "8px 0" }}>
      <TreeNode node={tree.universe} depth={0} />
    </div>
  )
}

export default function Phase5({ projectId, sessionId, onComplete }) {
  const { top100, setTop100, tree, setTree, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P5")
  const [explanation, setExplanation] = useState(null)
  const [pillarFilter, setPillarFilter] = useState("")

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    log("Building content tree + selecting top 100...", "info")
    try {
      const data = await api.runPhase5(projectId, sessionId)
      setTree(data.tree)
      const t100 = await api.getTop100(projectId, sessionId)
      setTop100(t100.items || [])
      const count = (t100.items || []).length
      log(`Complete: ${count} top keywords selected`, "success")
      toast(`Content tree built — ${count} keywords selected`, "success")
      onComplete()
      setActivePhase(6)
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
      toast(`Phase 5 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  useEffect(() => {
    async function load() {
      try {
        const t = await api.getTree(projectId, sessionId)
        if (t.tree && Object.keys(t.tree).length) setTree(t.tree)
        const t100 = await api.getTop100(projectId, sessionId)
        if (t100.items) setTop100(t100.items)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  const handleExplain = useCallback(async (keywordId) => {
    try {
      setExplanation({ loading: true, id: keywordId })
      const data = await api.explainKeyword(projectId, sessionId, keywordId)
      setExplanation({ text: data.explanation, id: keywordId })
    } catch {
      setExplanation({ text: "Failed to load explanation.", id: keywordId })
    }
  }, [projectId, sessionId])

  const pillars = [...new Set(top100.map((kw) => kw.pillar).filter(Boolean))]
  const filtered = pillarFilter ? top100.filter((kw) => kw.pillar === pillarFilter) : top100

  return (
    <Card title="Phase 5: Content Tree & Top 100" actions={<RunButton onClick={run} loading={loading}>Build Tree</RunButton>}>
      {error && <p style={{ color: "#dc2626", fontSize: 13 }}>{error}</p>}

      {top100.length > 0 && (
        <StatsRow items={[
          { label: "Top Keywords", value: top100.length, color: "#3b82f6" },
          { label: "Pillars", value: pillars.length, color: "#10b981" },
        ]} />
      )}

      {tree && (
        <div style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 12, fontWeight: 600, color: "#6b7280", marginBottom: 6 }}>
            Keyword Universe Tree — click pillars/clusters to expand
          </p>
          <KeywordTree tree={tree} />
        </div>
      )}

      {pillars.length > 1 && (
        <div style={{ marginBottom: 8 }}>
          <select
            style={{ padding: "4px 8px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 12 }}
            value={pillarFilter}
            onChange={(e) => setPillarFilter(e.target.value)}
          >
            <option value="">All pillars ({top100.length})</option>
            {pillars.map((p) => (
              <option key={p} value={p}>{p} ({top100.filter((kw) => kw.pillar === p).length})</option>
            ))}
          </select>
        </div>
      )}

      <KeywordTable keywords={filtered} onExplain={handleExplain} />

      {explanation && (
        <div style={{ marginTop: 8, padding: 8, background: "#f9fafb", borderRadius: 6, fontSize: 13 }}>
          {explanation.loading ? "Loading explanation..." : explanation.text}
        </div>
      )}

      {top100.length > 0 && (
        <PhaseResult
          phaseNum={5}
          stats={[
            { label: "Top Keywords", value: top100.length, color: "#3b82f6" },
            { label: "Pillars", value: pillars.length, color: "#10b981" },
          ]}
          onNext={() => setActivePhase(6)}
        />
      )}

      <NotificationList notifications={notifications} />
      <ConsolePanel filterBadge="P5" />
    </Card>
  )
}
