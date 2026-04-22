/**
 * KeywordGraph — Interactive force-directed graph of keyword relationships.
 * Uses react-force-graph-2d for rendering.
 */
import React, { useRef, useCallback, useMemo } from "react"
import ForceGraph2D from "react-force-graph-2d"

const GROUP_COLORS = {
  purchase:      "#ef4444",
  wholesale:     "#a855f7",
  commercial:    "#f59e0b",
  informational: "#6b7280",
  navigational:  "#3b82f6",
}

const PILLAR_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#14b8a6", "#f97316", "#06b6d4", "#84cc16",
]

export default function KeywordGraph({ data, width = 600, height = 500, onNodeClick }) {
  const graphRef = useRef()

  // Assign colors: pillar-based for nodes
  const pillarIndex = useMemo(() => {
    const map = {}
    let idx = 0
    ;(data?.nodes || []).forEach(n => {
      if (n.group && !(n.group in map)) {
        map[n.group] = PILLAR_COLORS[idx % PILLAR_COLORS.length]
        idx++
      }
    })
    return map
  }, [data])

  const nodeColor = useCallback((node) => {
    if (node.intent && GROUP_COLORS[node.intent]) return GROUP_COLORS[node.intent]
    return pillarIndex[node.group] || "#9ca3af"
  }, [pillarIndex])

  const nodeLabel = useCallback((node) => {
    let label = node.id
    if (node.intent) label += ` (${node.intent})`
    if (node.score) label += ` — score: ${node.score}`
    return label
  }, [])

  const handleClick = useCallback((node) => {
    if (onNodeClick) onNodeClick(node)
    if (graphRef.current) {
      graphRef.current.centerAt(node.x, node.y, 400)
      graphRef.current.zoom(2, 400)
    }
  }, [onNodeClick])

  if (!data || !data.nodes || data.nodes.length === 0) {
    return (
      <div style={{ padding: 20, color: "#9ca3af", textAlign: "center" }}>
        No graph data. Run Intelligence Pipeline first.
      </div>
    )
  }

  return (
    <ForceGraph2D
      ref={graphRef}
      graphData={data}
      width={width}
      height={height}
      nodeLabel={nodeLabel}
      nodeColor={nodeColor}
      nodeRelSize={4}
      nodeVal={node => node.top100 ? 3 : 1}
      linkColor={() => "rgba(156,163,175,0.3)"}
      linkWidth={link => Math.max(0.5, (link.similarity || 0) * 2)}
      onNodeClick={handleClick}
      cooldownTicks={100}
      nodeCanvasObjectMode={() => "after"}
      nodeCanvasObject={(node, ctx, globalScale) => {
        if (globalScale < 1.5) return
        const label = node.id.length > 25 ? node.id.slice(0, 22) + "..." : node.id
        const fontSize = 10 / globalScale
        ctx.font = `${fontSize}px Sans-Serif`
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        ctx.fillStyle = "#374151"
        ctx.fillText(label, node.x, node.y + 6)
      }}
    />
  )
}
