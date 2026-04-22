/**
 * Phase 5 — Content Tree & Top 100
 * 🌳 Tree  : SVG top-down circles + L-shape connectors (reference-image style)
 * 🕸 Graph : force-directed SVG
 * 🔍 Audit : per-pillar keyword review + safe deletion (never deletes top 100)
 * 📋 Table : standard keyword table
 */
import React, { useState, useCallback, useEffect, useRef, useMemo } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, KeywordTable, StatsRow, usePhaseRunner, PhaseResult, NotificationList } from "./shared"
import ConfirmModal from "./ConfirmModal"

/* ── Palette ─────────────────────────────────────────────────────── */
const PC = ["#6366f1","#10b981","#f59e0b","#ef4444","#8b5cf6","#ec4899",
            "#06b6d4","#84cc16","#f97316","#14b8a6","#fb7185","#a78bfa","#34d399","#60a5fa"]
const PAGE_CLR = { product_page:"#ef4444", category_page:"#f97316",
                   b2b_page:"#8b5cf6", blog_page:"#06b6d4", local_page:"#84cc16" }
const ICHIP = {
  purchase:      { bg:"#dcfce7", fg:"#166534" },
  wholesale:     { bg:"#ede9fe", fg:"#5b21b6" },
  transactional: { bg:"#dcfce7", fg:"#166534" },
  commercial:    { bg:"#fef9c3", fg:"#713f12" },
  informational: { bg:"#f3f4f6", fg:"#374151" },
  navigational:  { bg:"#dbeafe", fg:"#1e40af" },
}

function IntentChip({ intent, small }) {
  const s = ICHIP[intent] || { bg:"#f3f4f6", fg:"#374151" }
  return (
    <span style={{ padding: small ? "0 4px" : "1px 7px", borderRadius: 8,
      background: s.bg, color: s.fg, fontSize: small ? 7.5 : 9, fontWeight: 600, whiteSpace: "nowrap" }}>
      {intent || "—"}
    </span>
  )
}

/* ══════════════════════════════════════════════════════════════════
   TREE LAYOUT ENGINE — subtree-width algorithm
   Each node gets .x and .y in pixel space.
══════════════════════════════════════════════════════════════════ */
const LEVEL_H = 112
const LEAF_W  = { universe:80, pillar:116, cluster:86, keyword:54 }
const NODE_R  = { universe:28, pillar:22,  cluster:14, keyword:7  }
const PAD     = 32

function subtreeW(node, exp) {
  if (!node.children?.length || !exp[node.id]) return LEAF_W[node.type] ?? 64
  return node.children.reduce((s, c) => s + subtreeW(c, exp), 0)
}

function layoutNodes(node, depth, left, exp) {
  node.y = depth * LEVEL_H + 56
  const w = subtreeW(node, exp)
  if (!exp[node.id] || !node.children?.length) {
    node.x = left + w / 2
    node.w = w
    return
  }
  let cl = left
  for (const c of node.children) {
    layoutNodes(c, depth + 1, cl, exp)
    cl += c.w
  }
  node.x = (node.children[0].x + node.children[node.children.length - 1].x) / 2
  node.w = cl - left
}

function collectVisible(root, exp) {
  const nodes = [], edges = []
  function walk(n) {
    nodes.push(n)
    if (exp[n.id] && n.children?.length)
      for (const c of n.children) { edges.push({ f: n, t: c }); walk(c) }
  }
  walk(root)
  return { nodes, edges }
}

function getAllIds(node, acc = {}) {
  acc[node.id] = true
  ;(node.children || []).forEach(c => getAllIds(c, acc))
  return acc
}

/* Convert API tree → internal node graph */
function buildNodes(apiTree) {
  if (!apiTree?.universe) return null
  const u = apiTree.universe
  const root = { id:"u0", type:"universe", label:u.name, color:"#1e40af", data:u, children:[] }
  ;(u.pillars || []).forEach((p, pi) => {
    const color = PC[pi % PC.length]
    const pn = { id:`p${pi}`, type:"pillar", label:p.name, color, data:p, children:[] }
    ;(p.clusters || []).forEach((c, ci) => {
      const cn = { id:`p${pi}c${ci}`, type:"cluster", label:c.name, color, data:c, children:[] }
      const sorted = [...(c.keywords || [])].sort((a, b) => (b.score || 0) - (a.score || 0))
      sorted.slice(0, 8).forEach((kw, ki) => {
        cn.children.push({
          id: `p${pi}c${ci}k${ki}`, type:"keyword",
          label: kw.name || kw.keyword || "",
          color: kw.top100 ? "#f59e0b" : "#94a3b8",
          data: kw, children: [],
        })
      })
      pn.children.push(cn)
    })
    root.children.push(pn)
  })
  return root
}

/* ══════════════════════════════════════════════════════════════════
   SVG TREE CANVAS
══════════════════════════════════════════════════════════════════ */
function TreeCanvas({ apiTree }) {
  const [exp, setExp]   = useState({ u0: true })
  const [sel, setSel]   = useState(null)

  // Reset on new tree data
  useEffect(() => { setExp({ u0: true }); setSel(null) }, [apiTree])

  const rootTemplate = useMemo(() => buildNodes(apiTree), [apiTree])

  const layout = useMemo(() => {
    if (!rootTemplate) return { nodes:[], edges:[], w:420, h:220 }
    // Rebuild fresh objects, then layout (avoids stale mutation)
    const root = buildNodes(apiTree)
    layoutNodes(root, 0, PAD, exp)
    const { nodes, edges } = collectVisible(root, exp)
    const maxX = nodes.reduce((m, n) => Math.max(m, n.x + NODE_R[n.type] + 30), 420)
    const maxY = nodes.reduce((m, n) => Math.max(m, n.y), 0)
    return { nodes, edges, w: maxX + PAD, h: maxY + 80 }
  }, [rootTemplate, exp, apiTree])

  const toggle = useCallback(node => {
    if (!node.children?.length) return
    setExp(e => ({ ...e, [node.id]: !e[node.id] }))
  }, [])

  if (!rootTemplate) return (
    <p style={{ color:"#9ca3af", fontSize:13, padding:12 }}>
      Click "Build Tree" to generate.
    </p>
  )

  const u = apiTree.universe
  const totalKws = (u.pillars||[]).reduce((n,p)=>n+(p.clusters||[]).reduce((m,c)=>m+(c.keywords?.length||0),0),0)
  const top100c  = (u.pillars||[]).reduce((n,p)=>n+(p.clusters||[]).reduce((m,c)=>m+(c.keywords||[]).filter(k=>k.top100).length,0),0)

  return (
    <div>
      {/* Stats + controls */}
      <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:12, flexWrap:"wrap" }}>
        {[["🌐",`${u.pillars?.length||0} pillars`,"#6366f1"],["📦",`${totalKws} keywords`,"#10b981"],["★",`${top100c} top-100`,"#f59e0b"]].map(([ic,lb,c])=>(
          <span key={lb} style={{ padding:"3px 10px", borderRadius:8, background:c+"15", color:c,
            fontSize:11, fontWeight:700, border:`1px solid ${c}30` }}>{ic} {lb}</span>
        ))}
        <div style={{ display:"flex", gap:5, marginLeft:"auto" }}>
          {[
            ["Expand Pillars","#3b82f6", () => { const ids={u0:true}; rootTemplate.children?.forEach(p=>{ids[p.id]=true}); setExp(ids); setSel(null) }],
            ["Expand All","#8b5cf6", () => { setExp(getAllIds(rootTemplate)); setSel(null) }],
            ["Collapse","#9ca3af",   () => { setExp({u0:true}); setSel(null) }],
          ].map(([lb,c,fn])=>(
            <button key={lb} onClick={fn} style={{ padding:"3px 10px", borderRadius:5,
              fontSize:11, fontWeight:600, background:c, color:"#fff", border:"none", cursor:"pointer" }}>
              {lb}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display:"flex", gap:10, alignItems:"flex-start" }}>
        {/* SVG */}
        <div style={{ flex:1, overflowX:"auto", overflowY:"auto", maxHeight:600,
          background:"#f8fafc", borderRadius:12, border:"1px solid #e5e7eb",
          padding:"8px 4px", boxShadow:"inset 0 2px 8px rgba(0,0,0,.04)" }}>
          <svg width={layout.w} height={layout.h} style={{ display:"block" }}>
            <defs>
              <radialGradient id="uniG" cx="38%" cy="35%">
                <stop offset="0%" stopColor="#93c5fd" />
                <stop offset="100%" stopColor="#1d4ed8" />
              </radialGradient>
              {/* Arrow markers per pillar color */}
              {PC.map((c, i) => (
                <marker key={`am${i}`} id={`am${i}`} markerWidth={8} markerHeight={8} refX={4} refY={4} orient="auto">
                  <polygon points="0 0, 8 4, 0 8" fill={c+"99"} />
                </marker>
              ))}
              <marker id="amBlue" markerWidth={8} markerHeight={8} refX={4} refY={4} orient="auto">
                <polygon points="0 0, 8 4, 0 8" fill="#93c5fd" />
              </marker>
              <marker id="amGray" markerWidth={7} markerHeight={7} refX={3.5} refY={3.5} orient="auto">
                <polygon points="0 0, 7 3.5, 0 7" fill="#cbd5e1" />
              </marker>
            </defs>

            {/* L-shaped connector lines */}
            {layout.edges.map((e, i) => {
              const { f, t } = e
              const fr = NODE_R[f.type], tr = NODE_R[t.type]
              const fy  = f.y + fr + 1
              const ty  = t.y - tr - 6
              const mid = fy + (ty - fy) * 0.5
              let stroke, markerId, sw
              if (f.type === "universe") {
                stroke = "#93c5fd"; markerId = "url(#amBlue)"; sw = 2.2
              } else if (f.type === "pillar") {
                const pi = parseInt(f.id.replace("p",""))
                stroke = PC[pi % PC.length] + "77"; markerId = `url(#am${pi % PC.length})`; sw = 1.6
              } else {
                stroke = "#cbd5e1"; markerId = "url(#amGray)"; sw = 1.1
              }
              return (
                <path key={i}
                  d={`M ${f.x},${fy} L ${f.x},${mid} L ${t.x},${mid} L ${t.x},${ty}`}
                  stroke={stroke} strokeWidth={sw} fill="none"
                  markerEnd={markerId} strokeLinecap="round" />
              )
            })}

            {/* Nodes */}
            {layout.nodes.map(node => (
              <SvgNode key={node.id} node={node}
                isOpen={!!exp[node.id]}
                isSelected={sel?.id === node.id}
                onToggle={toggle}
                onSelect={setSel} />
            ))}
          </svg>
        </div>

        {/* Info panel */}
        {sel && <InfoPanel node={sel} onClose={() => setSel(null)} />}
      </div>
    </div>
  )
}

/* Individual SVG node */
function SvgNode({ node, isOpen, isSelected, onToggle, onSelect }) {
  const r = NODE_R[node.type]
  const hasKids = node.children?.length > 0

  if (node.type === "keyword") {
    const isTop = node.data?.top100
    return (
      <g onClick={() => onSelect(node)} style={{ cursor:"pointer" }}>
        <circle cx={node.x} cy={node.y} r={r + 1}
          fill={isTop ? "#fffbeb" : "#f8fafc"}
          stroke={isTop ? "#f59e0b" : "#94a3b8"}
          strokeWidth={isTop ? 2 : 1.2} />
        {isTop && (
          <text x={node.x} y={node.y + 3.5} textAnchor="middle" fontSize={7} fill="#d97706">★</text>
        )}
        <title>{node.label}</title>
        <text x={node.x} y={node.y + r + 11} textAnchor="middle" fontSize={7.5} fill="#475569">
          {node.label.length > 12 ? node.label.slice(0,10)+"…" : node.label}
        </text>
      </g>
    )
  }

  if (node.type === "universe") {
    return (
      <g onClick={() => { onToggle(node); onSelect(node) }} style={{ cursor:"pointer" }}>
        <circle cx={node.x} cy={node.y} r={r + 7} fill="#dbeafe44" stroke="#93c5fd" strokeWidth={1} />
        <circle cx={node.x} cy={node.y} r={r} fill="url(#uniG)" stroke="#1e40af" strokeWidth={2.5}
          style={{ filter:"drop-shadow(0 2px 10px rgba(29,78,216,.45))" }} />
        <text x={node.x} y={node.y + 7} textAnchor="middle" fontSize={20}>🌐</text>
        <text x={node.x} y={node.y + r + 14} textAnchor="middle" fontSize={11} fontWeight={700} fill="#1e40af">
          {node.label.length > 20 ? node.label.slice(0,18)+"…" : node.label}
        </text>
      </g>
    )
  }

  if (node.type === "pillar") {
    const kwCount = (node.data?.clusters||[]).reduce((s,c)=>s+(c.keywords?.length||0),0)
    const top100c = (node.data?.clusters||[]).reduce((s,c)=>s+(c.keywords||[]).filter(k=>k.top100).length,0)
    const words = node.label.split(/\s+/)
    const line1 = words.slice(0,2).join(" ")
    const line2 = words.length > 2 ? words.slice(2).join(" ") : ""
    const glow  = isSelected
      ? `drop-shadow(0 0 10px ${node.color}bb)`
      : `drop-shadow(0 2px 6px ${node.color}44)`
    return (
      <g onClick={() => { onToggle(node); onSelect(node) }} style={{ cursor:"pointer" }}>
        {/* Glow ring */}
        <circle cx={node.x} cy={node.y} r={r+7} fill={node.color+"0f"}
          stroke={node.color+"30"} strokeWidth={1.5} />
        {/* Main circle */}
        <circle cx={node.x} cy={node.y} r={r}
          fill={isOpen ? node.color+"28" : "#fff"}
          stroke={node.color} strokeWidth={isSelected ? 3.2 : 2.6}
          style={{ filter:glow, transition:"all .15s" }} />
        {/* Text inside */}
        <text x={node.x} y={line2 ? node.y-1 : node.y+4} textAnchor="middle"
          fontSize={9.5} fontWeight={800} fill={node.color}>
          {line1.length > 10 ? line1.slice(0,9)+"…" : line1}
        </text>
        {line2 && (
          <text x={node.x} y={node.y+10} textAnchor="middle" fontSize={8} fontWeight={700} fill={node.color}>
            {line2.length > 10 ? line2.slice(0,9)+"…" : line2}
          </text>
        )}
        {/* Count badge */}
        <circle cx={node.x+r+8} cy={node.y-r-2} r={10} fill={node.color}
          style={{ filter:`drop-shadow(0 1px 4px ${node.color}99)` }} />
        <text x={node.x+r+8} y={node.y-r+2} textAnchor="middle"
          fontSize={kwCount > 99 ? 6.5 : 8} fontWeight={700} fill="#fff">
          {kwCount > 99 ? "99+" : kwCount}
        </text>
        {/* Label below */}
        <text x={node.x} y={node.y+r+14} textAnchor="middle"
          fontSize={9.5} fontWeight={700} fill="#1e293b">
          {node.label.length>16 ? node.label.slice(0,15)+"…" : node.label}
        </text>
        {/* Stars + expand arrow */}
        <text x={node.x} y={node.y+r+26} textAnchor="middle"
          fontSize={8.5} fill={node.color+"dd"}>
          {top100c > 0 ? `★${top100c}  ` : ""}{hasKids ? (isOpen ? "▲" : "▼") : ""}
        </text>
      </g>
    )
  }

  if (node.type === "cluster") {
    const kwCount = node.data?.keywords?.length || 0
    const top100c = (node.data?.keywords||[]).filter(k=>k.top100).length
    return (
      <g onClick={() => { onToggle(node); onSelect(node) }} style={{ cursor:"pointer" }}>
        <circle cx={node.x} cy={node.y} r={r+2}
          fill={isOpen ? node.color+"18" : "#f8fafc"}
          stroke={node.color+"99"} strokeWidth={isSelected ? 2.2 : 1.8} />
        {/* Badge */}
        <circle cx={node.x+r+4} cy={node.y-r} r={7.5} fill={node.color} />
        <text x={node.x+r+4} y={node.y-r+3.5} textAnchor="middle"
          fontSize={kwCount > 9 ? 6.5 : 7.5} fontWeight={700} fill="#fff">{kwCount}</text>
        {/* Label */}
        <text x={node.x} y={node.y+r+11} textAnchor="middle"
          fontSize={8.5} fontWeight={500} fill="#374151">
          {node.label.length>14 ? node.label.slice(0,12)+"…" : node.label}
        </text>
        {top100c > 0 && (
          <text x={node.x} y={node.y+r+21} textAnchor="middle" fontSize={7.5} fill="#f59e0b">★{top100c}</text>
        )}
        {hasKids && (
          <text x={node.x} y={node.y+r+(top100c>0?31:21)} textAnchor="middle"
            fontSize={7.5} fill={node.color}>{isOpen ? "▲" : "▼"}</text>
        )}
      </g>
    )
  }

  return null
}

/* Info panel — shown on right when a node is clicked */
function InfoPanel({ node, onClose }) {
  if (!node) return null
  const c    = node.color || "#374151"
  const data = node.data  || {}
  return (
    <div style={{ width:250, flexShrink:0, padding:14, borderRadius:12,
      border:`1.5px solid ${c}33`, background:"#fff",
      boxShadow:`0 4px 20px ${c}22`, maxHeight:580, overflowY:"auto" }}>
      {/* Header */}
      <div style={{ display:"flex", gap:6, alignItems:"flex-start", marginBottom:10 }}>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:9, fontWeight:800, color:c, textTransform:"uppercase", letterSpacing:0.8, marginBottom:2 }}>
            {node.type}
          </div>
          <div style={{ fontSize:13, fontWeight:700, color:"#0f172a", lineHeight:1.3 }}>{node.label}</div>
        </div>
        <button onClick={onClose} style={{ background:"none", border:"none", cursor:"pointer",
          color:"#9ca3af", fontSize:18, lineHeight:1, paddingTop:1 }}>×</button>
      </div>

      {/* Pillar panel */}
      {node.type === "pillar" && (() => {
        const clusters = data.clusters || []
        const allKws   = clusters.flatMap(cl => cl.keywords || [])
        const byIntent = {}
        allKws.forEach(k => { const i = k.intent||"unknown"; byIntent[i]=(byIntent[i]||0)+1 })
        return (
          <>
            <div style={{ display:"flex", gap:5, flexWrap:"wrap", marginBottom:10 }}>
              {[
                [`${allKws.length} kws`, c],
                [`★ ${allKws.filter(k=>k.top100).length}`, "#f59e0b"],
                [`${clusters.length} clusters`, c],
              ].map(([l,col])=>(
                <span key={l} style={{ padding:"2px 8px", borderRadius:8,
                  background:col+"18", color:col, fontSize:10, fontWeight:700 }}>{l}</span>
              ))}
            </div>
            <div style={{ fontSize:10, fontWeight:700, color:"#9ca3af", marginBottom:5 }}>INTENT BREAKDOWN</div>
            {Object.entries(byIntent).sort((a,b)=>b[1]-a[1]).map(([int,cnt])=>(
              <div key={int} style={{ display:"flex", gap:6, alignItems:"center", marginBottom:4 }}>
                <IntentChip intent={int} />
                <span style={{ fontSize:11, color:"#374151", minWidth:16 }}>{cnt}</span>
                <div style={{ flex:1, height:4, borderRadius:2, background:"#f3f4f6", overflow:"hidden" }}>
                  <div style={{ width:`${(cnt/Math.max(allKws.length,1))*100}%`,
                    height:"100%", background:c+"77", borderRadius:2 }} />
                </div>
              </div>
            ))}
          </>
        )
      })()}

      {/* Cluster panel */}
      {node.type === "cluster" && (() => {
        const kws = [...(data.keywords||[])].sort((a,b)=>(b.score||0)-(a.score||0))
        return (
          <>
            <div style={{ fontSize:11, color:"#6b7280", marginBottom:8 }}>
              {kws.length} keywords · {kws.filter(k=>k.top100).length} top-100
            </div>
            <div style={{ maxHeight:380, overflowY:"auto" }}>
              {kws.map((kw,i) => (
                <div key={i} style={{ display:"flex", gap:5, padding:"3px 0",
                  borderBottom:"1px solid #f3f4f6", fontSize:11, alignItems:"center",
                  opacity:kw.top100 ? 1 : 0.55 }}>
                  <span style={{ width:12, color:"#f59e0b", fontSize:9 }}>{kw.top100?"★":"·"}</span>
                  <span style={{ flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                    {kw.name||kw.keyword}
                  </span>
                  <IntentChip intent={kw.intent} small />
                  <span style={{ color:"#9ca3af", fontSize:9, minWidth:26, textAlign:"right" }}>
                    {(kw.score||0).toFixed(1)}
                  </span>
                </div>
              ))}
            </div>
          </>
        )
      })()}

      {/* Keyword panel */}
      {node.type === "keyword" && (() => {
        const kw       = data
        const pageLabel = (kw.mapped_page||"").replace(/_page$/,"")
        return (
          <div style={{ display:"flex", flexDirection:"column", gap:7, fontSize:12 }}>
            {kw.top100 && (
              <div style={{ padding:"4px 10px", borderRadius:6, background:"#fef9c3",
                color:"#92400e", fontWeight:700, fontSize:11 }}>★ Top 100 Keyword</div>
            )}
            {kw.intent && (
              <div style={{ display:"flex", gap:6, alignItems:"center" }}>
                <span style={{ fontSize:10, color:"#9ca3af" }}>Intent</span>
                <IntentChip intent={kw.intent} />
              </div>
            )}
            {kw.score != null && (
              <div>Score: <strong style={{ color:c }}>{(kw.score||0).toFixed(2)}</strong></div>
            )}
            {pageLabel && (
              <div>Page: <strong style={{ color:"#6366f1" }}>{pageLabel}</strong></div>
            )}
          </div>
        )
      })()}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════
   GRAPH VIEW — force-directed SVG
══════════════════════════════════════════════════════════════════ */
function GraphView({ tree }) {
  const svgRef  = useRef(null)
  const animRef = useRef(null)
  const nRef    = useRef([])
  const eRef    = useRef([])
  const dragRef = useRef(null)
  const [tick, setTick] = useState(0)
  const W = 1000, H = 580

  useEffect(() => {
    if (!tree?.universe) return
    const nodes = [], edges = []
    const u = tree.universe
    nodes.push({ id:"u0", label:u.name, type:"universe", color:"#1e40af",
      r:30, x:W/2, y:54, vx:0, vy:0, fx:W/2, fy:54 })
    ;(u.pillars||[]).forEach((p, pi) => {
      const pid = "p"+pi, c = PC[pi % PC.length]
      const kwCount = (p.clusters||[]).reduce((n,cl)=>n+(cl.keywords?.length||0),0)
      nodes.push({ id:pid, label:p.name, type:"pillar", color:c, r:20,
        x: 50 + pi*((W-100)/Math.max((u.pillars.length-1),1)),
        y: 130 + (pi%2)*24, vx:0, vy:0, badge:kwCount })
      edges.push({ from:"u0", to:pid, color:c+"55" })
      ;(p.clusters||[]).forEach((cl, ci) => {
        const cid = pid+"c"+ci, kwLen = (cl.keywords||[]).length
        nodes.push({ id:cid, label:cl.name, type:"cluster", color:c+"99", r:10,
          x: nodes[nodes.length-1].x + (ci - (p.clusters.length-1)/2)*38,
          y: 250 + Math.random()*30, vx:0, vy:0, badge:kwLen })
        edges.push({ from:pid, to:cid, color:c+"44" })
        ;(cl.keywords||[]).slice(0,4).forEach((kw, ki) => {
          const kid = cid+"k"+ki
          nodes.push({ id:kid, label:kw.name||kw.keyword||"", type:"keyword",
            color: kw.top100 ? "#f59e0b" : "#d1d5db", r:4,
            x: nodes[nodes.length-1].x + (ki-2)*16,
            y: 380 + Math.random()*50, vx:0, vy:0 })
          edges.push({ from:cid, to:kid, color:"#e5e7eb" })
        })
      })
    })
    const nm = {}; nodes.forEach(n => { nm[n.id] = n })
    nRef.current = nodes; eRef.current = edges
    setTick(1)

    let running = true
    const BANDS = { universe:54, pillar:140, cluster:280, keyword:410 }
    function step() {
      if (!running) return
      const ns = nRef.current, es = eRef.current
      ns.forEach(n => {
        if (n.fx != null) return
        n.vx += (W/2 - n.x)*0.0004
        n.vy += (H/2 - n.y)*0.0004
      })
      for (let i = 0; i < ns.length; i++) {
        for (let j = i+1; j < ns.length; j++) {
          const a = ns[i], b = ns[j]
          let dx = b.x-a.x, dy = b.y-a.y
          let d = Math.sqrt(dx*dx+dy*dy) || 1
          const minD = (a.r+b.r)*3.2
          if (d < minD) {
            const f = (minD-d)/d*0.38
            if (!a.fx) { a.vx -= dx*f; a.vy -= dy*f }
            if (!b.fx) { b.vx += dx*f; b.vy += dy*f }
          }
        }
      }
      es.forEach(e => {
        const a = nm[e.from], b = nm[e.to]; if (!a||!b) return
        let dx=b.x-a.x, dy=b.y-a.y, d=Math.sqrt(dx*dx+dy*dy)||1
        const f=(d-80)/d*0.018
        if (!a.fx) { a.vx+=dx*f; a.vy+=dy*f }
        if (!b.fx) { b.vx-=dx*f; b.vy-=dy*f }
      })
      ns.forEach(n => {
        if (n.fx != null) return
        n.vy += (BANDS[n.type] - n.y)*0.028
        n.vx *= 0.82; n.vy *= 0.82
        n.x += n.vx; n.y += n.vy
        n.x = Math.max(n.r+4, Math.min(W-n.r-4, n.x))
        n.y = Math.max(n.r+4, Math.min(H-n.r-4, n.y))
      })
      setTick(t => t+1)
      animRef.current = requestAnimationFrame(step)
    }
    animRef.current = requestAnimationFrame(step)
    const timer = setTimeout(() => { running = false }, 4000)
    return () => { running = false; cancelAnimationFrame(animRef.current); clearTimeout(timer) }
  }, [tree])

  const onDown  = nid => e => {
    e.preventDefault()
    const n = nRef.current.find(x => x.id === nid)
    if (n) { dragRef.current = n; n.fx = n.x; n.fy = n.y }
  }
  const onMove = e => {
    if (!dragRef.current || !svgRef.current) return
    const r = svgRef.current.getBoundingClientRect()
    dragRef.current.fx = e.clientX - r.left
    dragRef.current.fy = e.clientY - r.top
    dragRef.current.x  = dragRef.current.fx
    dragRef.current.y  = dragRef.current.fy
  }
  const onUp = () => {
    if (dragRef.current && dragRef.current.type !== "universe") {
      dragRef.current.fx = null; dragRef.current.fy = null
    }
    dragRef.current = null
  }

  const nodes = nRef.current, edges = eRef.current
  const nm = {}; nodes.forEach(n => { nm[n.id] = n })

  if (!tree?.universe) return <p style={{ color:"#9ca3af", fontSize:13 }}>No tree data.</p>
  return (
    <svg ref={svgRef} width={W} height={H}
      style={{ background:"#fafafa", borderRadius:10, border:"1px solid #e5e7eb",
        display:"block", margin:"0 auto" }}
      onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}>
      {edges.map((e,i) => {
        const a=nm[e.from], b=nm[e.to]; if(!a||!b) return null
        return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={e.color} strokeWidth={1.5} />
      })}
      {nodes.map(n => (
        <g key={n.id} onMouseDown={onDown(n.id)} style={{ cursor:"grab" }}>
          <circle cx={n.x} cy={n.y} r={n.r} fill="#fff" stroke={n.color}
            strokeWidth={n.type==="keyword" ? 1.5 : 2.5} />
          {n.type==="universe"  && <text x={n.x} y={n.y+6}  textAnchor="middle" fontSize={20}>🌐</text>}
          {n.type==="pillar"    && <text x={n.x} y={n.y+4}  textAnchor="middle" fontSize={9}  fontWeight={700} fill={n.color}>{n.label.slice(0,5)}</text>}
          {n.type==="cluster"   && <text x={n.x} y={n.y+3}  textAnchor="middle" fontSize={7}  fontWeight={600} fill="#374151">{n.badge||""}</text>}
          {(n.type==="pillar"||n.type==="universe") && (
            <text x={n.x} y={n.y+n.r+11} textAnchor="middle" fontSize={8.5} fontWeight={n.type==="pillar" ? 700 : 600} fill="#374151">
              {n.label.length>18 ? n.label.slice(0,16)+"…" : n.label}
            </text>
          )}
          {n.type==="cluster" && (
            <text x={n.x} y={n.y+n.r+9} textAnchor="middle" fontSize={6.5} fill="#9ca3af">
              {n.label.length>14 ? n.label.slice(0,12)+"…" : n.label}
            </text>
          )}
        </g>
      ))}
      {/* Legend */}
      <g transform="translate(12,12)">
        {[
          {c:"#1e40af",l:"Universe",r:7},{c:"#6366f1",l:"Pillar",r:5},
          {c:"#9ca3af",l:"Cluster",r:4},{c:"#f59e0b",l:"★ Top-100",r:3},{c:"#d1d5db",l:"Keyword",r:3},
        ].map((it,i) => (
          <g key={i} transform={`translate(0,${i*16})`}>
            <circle cx={it.r} cy={6} r={it.r} fill="#fff" stroke={it.c} strokeWidth={2} />
            <text x={18} y={9} fontSize={8.5} fill="#6b7280">{it.l}</text>
          </g>
        ))}
      </g>
    </svg>
  )
}

/* ══════════════════════════════════════════════════════════════════
   AUDIT VIEW — per-pillar keyword review + safe deletion
   Rules: top 100 NEVER deleted. Only rank 101+ can be selected.
══════════════════════════════════════════════════════════════════ */
function AuditView({ projectId, sessionId, tree, onRefresh }) {
  const [validated, setValidated] = useState([])
  const [loading, setLoading]     = useState(false)
  const [selected, setSelected]   = useState(new Set())
  const [deleting, setDeleting]   = useState(false)
  const [openPillar, setOpenPillar] = useState(null)
  const [scoreThresh, setScoreThresh] = useState(1.0)
  const [error, setError]         = useState(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  useEffect(() => {
    setLoading(true)
    api.getValidated(projectId, sessionId)
      .then(d => setValidated(d.keywords || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId, sessionId])

  // Group by pillar, sorted by score desc
  const byPillar = useMemo(() => {
    const map = {}
    ;[...validated]
      .sort((a, b) => (b.final_score || 0) - (a.final_score || 0))
      .forEach((kw, rank) => {
        const p = kw.pillar || "Unassigned"
        if (!map[p]) map[p] = []
        map[p].push({ ...kw, globalRank: rank + 1 })
      })
    return map
  }, [validated])

  // Per-pillar top-100 determination
  const top100IdsPerPillar = useMemo(() => {
    const ids = new Set()
    Object.values(byPillar).forEach(kws => {
      kws.forEach((kw, i) => { if (i < 100) ids.add(kw.id) })
    })
    return ids
  }, [byPillar])

  const toggle = id => {
    if (top100IdsPerPillar.has(id)) return  // protected
    setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  }

  const selectBelowThreshold = pillar => {
    const kws = byPillar[pillar] || []
    kws.forEach((kw, i) => {
      if (i >= 100 && (kw.final_score || 0) < scoreThresh) {
        setSelected(s => new Set([...s, kw.id]))
      }
    })
  }

  const handleDelete = useCallback(async () => {
    const ids = [...selected]
    if (!ids.length) return
    const protected_ = ids.filter(id => top100IdsPerPillar.has(id))
    if (protected_.length) { setError("Cannot delete top-100 keywords."); return }
    setShowDeleteConfirm(true)
  }, [selected, top100IdsPerPillar])

  const confirmDeleteAction = useCallback(async () => {
    setShowDeleteConfirm(false)
    const ids = [...selected]
    if (!ids.length) return
    setDeleting(true)
    try {
      await api.rejectKeywords(projectId, sessionId, ids)
      setValidated(v => v.filter(kw => !ids.includes(kw.id)))
      setSelected(new Set())
      onRefresh?.()
    } catch (e) { setError(e.message) }
    setDeleting(false)
  }, [selected, top100IdsPerPillar, projectId, sessionId])

  if (loading) return <p style={{ color:"#9ca3af", fontSize:13 }}>Loading keywords...</p>

  const pillars = Object.keys(byPillar).sort()
  const totalAbove = Object.values(byPillar).reduce((n, kws) => n + kws.filter((_,i)=>i<100).length, 0)
  const totalBelow = validated.length - totalAbove

  return (
    <div>
      <ConfirmModal
        open={showDeleteConfirm}
        title={`Delete ${selected.size} keyword(s)?`}
        message="This will permanently delete the selected keywords below top-100. Top-100 keywords are protected and will NOT be deleted."
        confirmLabel="Delete"
        danger
        onConfirm={confirmDeleteAction}
        onCancel={() => setShowDeleteConfirm(false)}
      />
      {error && (
        <div style={{ padding:"8px 12px", borderRadius:6, background:"#fee2e2",
          color:"#dc2626", fontSize:12, marginBottom:10 }}>{error}</div>
      )}

      {/* Stats bar */}
      <div style={{ display:"flex", gap:10, marginBottom:12, flexWrap:"wrap", alignItems:"center" }}>
        {[
          [`${validated.length} total`,  "#3b82f6"],
          [`★ ${totalAbove} top-100`,   "#f59e0b"],
          [`${totalBelow} below-100`,   "#9ca3af"],
          [`${selected.size} selected`, "#ef4444"],
        ].map(([l,c])=>(
          <span key={l} style={{ padding:"3px 10px", borderRadius:8, background:c+"15", color:c,
            fontSize:11, fontWeight:700 }}>{l}</span>
        ))}
        <div style={{ marginLeft:"auto", display:"flex", gap:8, alignItems:"center" }}>
          <label style={{ fontSize:11, color:"#6b7280" }}>
            Score below:&nbsp;
            <input type="number" step={0.5} min={0} max={10} value={scoreThresh}
              onChange={e => setScoreThresh(parseFloat(e.target.value)||0)}
              style={{ width:52, padding:"2px 4px", borderRadius:4, border:"1px solid #d1d5db",
                fontSize:11, textAlign:"center" }} />
          </label>
          {selected.size > 0 && (
            <button onClick={handleDelete} disabled={deleting}
              style={{ padding:"5px 14px", borderRadius:6, fontSize:12, fontWeight:700,
                background: deleting ? "#d1d5db" : "#ef4444", color:"#fff", border:"none",
                cursor: deleting ? "wait" : "pointer" }}>
              {deleting ? "Deleting…" : `🗑 Delete ${selected.size} keywords`}
            </button>
          )}
        </div>
      </div>

      <div style={{ fontSize:11, color:"#f59e0b", background:"#fffbeb", padding:"6px 12px",
        borderRadius:6, marginBottom:12, border:"1px solid #fde68a" }}>
        ★ <strong>Top-100 keywords are permanently protected</strong> — they cannot be selected or deleted.
        Only keywords ranked 101+ per pillar (dimmed) can be removed.
      </div>

      {/* Per-pillar tables */}
      {pillars.map(pillar => {
        const kws = byPillar[pillar] || []
        const isOpen = openPillar === pillar
        const belowCount = kws.filter((_,i)=>i>=100).length
        const belowLowScore = kws.filter((kw,i)=>i>=100 && (kw.final_score||0)<scoreThresh).length
        const color = PC[pillars.indexOf(pillar) % PC.length]
        return (
          <div key={pillar} style={{ marginBottom:8, border:`1px solid ${color}33`,
            borderRadius:8, overflow:"hidden" }}>
            {/* Pillar header */}
            <div onClick={() => setOpenPillar(isOpen ? null : pillar)}
              style={{ display:"flex", alignItems:"center", gap:10, padding:"8px 14px",
                background: isOpen ? color+"12" : "#fafafa", cursor:"pointer",
                userSelect:"none", transition:"background .15s" }}>
              <span style={{ fontSize:8 }}>{isOpen ? "▼" : "▶"}</span>
              <span style={{ fontWeight:700, fontSize:13, color }}>🎯 {pillar}</span>
              <span style={{ fontSize:11, color:"#374151" }}>{kws.length} keywords</span>
              <span style={{ fontSize:10, color:"#9ca3af" }}>
                ★{kws.filter((_,i)=>i<100).length} top · {belowCount} below-100
              </span>
              {belowLowScore > 0 && (
                <span style={{ marginLeft:"auto", fontSize:10, color:"#ef4444",
                  fontWeight:600, background:"#fee2e2", padding:"1px 8px", borderRadius:6 }}>
                  {belowLowScore} low-score
                </span>
              )}
              {isOpen && belowLowScore > 0 && (
                <button onClick={e => { e.stopPropagation(); selectBelowThreshold(pillar) }}
                  style={{ padding:"2px 10px", borderRadius:5, fontSize:10, fontWeight:600,
                    background:"#f97316", color:"#fff", border:"none", cursor:"pointer" }}
                  title={`Select rank 101+ keywords with score < ${scoreThresh}`}>
                  Auto-select low-score
                </button>
              )}
            </div>

            {/* Keyword table */}
            {isOpen && (
              <div style={{ overflowX:"auto" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", fontSize:11 }}>
                  <thead>
                    <tr style={{ background:"#f9fafb" }}>
                      <th style={{ padding:"5px 8px", width:28, fontSize:9, color:"#9ca3af" }}>✓</th>
                      <th style={{ padding:"5px 8px", width:32, fontSize:9, color:"#9ca3af" }}>#</th>
                      <th style={{ padding:"5px 8px", textAlign:"left", fontSize:9, color:"#9ca3af" }}>Keyword</th>
                      <th style={{ padding:"5px 8px", fontSize:9, color:"#9ca3af" }}>Intent</th>
                      <th style={{ padding:"5px 8px", textAlign:"right", fontSize:9, color:"#9ca3af" }}>Score</th>
                      <th style={{ padding:"5px 8px", textAlign:"right", fontSize:9, color:"#9ca3af" }}>Src</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kws.map((kw, rank) => {
                      const isProtected = rank < 100
                      const isSel = selected.has(kw.id)
                      const isLow = !isProtected && (kw.final_score||0) < scoreThresh
                      return (
                        <tr key={kw.id}
                          onClick={() => !isProtected && toggle(kw.id)}
                          style={{
                            borderBottom:"1px solid #f3f4f6",
                            background: isSel ? "#fee2e224" : "transparent",
                            opacity: isProtected ? 1 : 0.62,
                            cursor: isProtected ? "default" : "pointer",
                            transition:"background .1s",
                          }}>
                          <td style={{ padding:"4px 8px", textAlign:"center" }}>
                            {isProtected
                              ? <span style={{ fontSize:10, color:"#f59e0b" }}>★</span>
                              : <input type="checkbox" checked={isSel} onChange={()=>toggle(kw.id)}
                                  style={{ cursor:"pointer", accentColor:"#ef4444" }} />
                            }
                          </td>
                          <td style={{ padding:"4px 8px", color:"#9ca3af", fontSize:10, textAlign:"right" }}>{rank+1}</td>
                          <td style={{ padding:"4px 8px" }}>
                            {kw.keyword}
                            {isLow && <span style={{ marginLeft:6, fontSize:9, color:"#ef4444" }}>⚠ low</span>}
                          </td>
                          <td style={{ padding:"4px 8px", textAlign:"center" }}>
                            <IntentChip intent={kw.intent} small />
                          </td>
                          <td style={{ padding:"4px 8px", textAlign:"right",
                            fontWeight:isProtected?700:400,
                            color: (kw.final_score||0) >= 2 ? "#10b981" : "#f97316" }}>
                            {(kw.final_score||0).toFixed(2)}
                          </td>
                          <td style={{ padding:"4px 8px", textAlign:"right", fontSize:9, color:"#9ca3af" }}>
                            {kw.source?.slice(0,4)||"—"}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════
   PHASE 5 MAIN
══════════════════════════════════════════════════════════════════ */
export default function Phase5({ projectId, sessionId, onComplete, onNext, autoRun, hideRunButton }) {
  const { top100, setTop100, tree, setTree, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P5")
  const [viewMode, setViewMode] = useState("tree")
  const [pillarFilter, setPillarFilter] = useState("")
  const [explanation, setExplanation] = useState(null)

  const run = useCallback(async () => {
    setLoading(true); setError(null)
    log("Building content tree + selecting top 100…", "info")
    try {
      const data = await api.runPhase5(projectId, sessionId)
      setTree(data.tree)
      const t100 = await api.getTop100(projectId, sessionId)
      setTop100(t100.items || [])
      const cnt = (t100.items||[]).length
      log(`Complete: ${cnt} top keywords selected`, "success")
      toast(`Content tree built — ${cnt} keywords`, "success")
      onComplete()
    } catch (e) {
      setError(e.message); log(`Failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  useEffect(() => { if (autoRun) run() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    async function load() {
      try {
        const t = await api.getTree(projectId, sessionId)
        if (t.tree && Object.keys(t.tree).length) setTree(t.tree)
        const t100 = await api.getTop100(projectId, sessionId)
        if (t100.items) setTop100(t100.items)
      } catch {}
    }
    load()
  }, [])

  const handleExplain = useCallback(async kwId => {
    try {
      setExplanation({ loading: true, id: kwId })
      const d = await api.explainKeyword(projectId, sessionId, kwId)
      setExplanation({ text: d.explanation, id: kwId })
    } catch {
      setExplanation({ text: "Failed to load explanation.", id: kwId })
    }
  }, [projectId, sessionId])

  const pillars     = [...new Set(top100.map(k => k.pillar).filter(Boolean))]
  const filtered    = pillarFilter ? top100.filter(k => k.pillar === pillarFilter) : top100

  const VIEW_TABS = [
    ["tree",  "🌳", "Tree View"],
    ["graph", "🕸", "Graph View"],
    ["audit", "🔍", "Keyword Audit"],
    ["table", "📋", "Table View"],
  ]

  return (
    <Card title="Phase 5: Content Tree & Top 100"
      actions={hideRunButton ? null : <RunButton onClick={run} loading={loading}>Build Tree</RunButton>}>

      {error && <p style={{ color:"#dc2626", fontSize:13 }}>{error}</p>}

      {top100.length > 0 && (
        <StatsRow items={[
          { label:"Top Keywords", value:top100.length, color:"#3b82f6" },
          { label:"Pillars",      value:pillars.length, color:"#10b981" },
        ]} />
      )}

      {/* View toggle */}
      {(tree || top100.length > 0) && (
        <div style={{ display:"flex", gap:6, marginBottom:14, flexWrap:"wrap" }}>
          {VIEW_TABS.map(([mode, icon, label]) => (
            <button key={mode} onClick={() => setViewMode(mode)} style={{
              padding:"5px 14px", borderRadius:7, fontSize:12, fontWeight:600, cursor:"pointer",
              border: viewMode===mode ? "2px solid #3b82f6" : "1px solid #d1d5db",
              background: viewMode===mode ? "#eff6ff" : "#fff",
              color: viewMode===mode ? "#1e40af" : "#6b7280",
            }}>{icon} {label}</button>
          ))}
        </div>
      )}

      {tree && viewMode === "tree" && (
        <div style={{ marginBottom:16, padding:"4px 0" }}>
          <TreeCanvas apiTree={tree} />
        </div>
      )}

      {tree && viewMode === "graph" && (
        <div style={{ marginBottom:16, overflowX:"auto" }}>
          <GraphView tree={tree} />
        </div>
      )}

      {viewMode === "audit" && (
        <div style={{ marginBottom:16 }}>
          <AuditView
            projectId={projectId}
            sessionId={sessionId}
            tree={tree}
            onRefresh={onComplete}
          />
        </div>
      )}

      {viewMode === "table" && (
        <>
          {pillars.length > 1 && (
            <div style={{ marginBottom:8 }}>
              <select value={pillarFilter} onChange={e => setPillarFilter(e.target.value)}
                style={{ padding:"4px 8px", borderRadius:4, border:"1px solid #d1d5db", fontSize:12 }}>
                <option value="">All pillars ({top100.length})</option>
                {pillars.map(p => (
                  <option key={p} value={p}>{p} ({top100.filter(k=>k.pillar===p).length})</option>
                ))}
              </select>
            </div>
          )}
          {(() => {
            const warned = filtered.filter(k => k.spot_check_warning)
            if (!warned.length) return null
            return (
              <div style={{ marginBottom:8, padding:"7px 12px", borderRadius:6,
                background:"#fef3c7", border:"1px solid #fde68a",
                color:"#92400e", fontSize:12, fontWeight:500 }}>
                ⚠ Quality advisory: {warned.length} keyword{warned.length > 1 ? "s" : ""} in the top-100
                may match negative-scope patterns. Hover the "⚠ review" badge to see details.
                These keywords are not removed — this is advisory only.
              </div>
            )
          })()}
          <KeywordTable keywords={filtered} onExplain={handleExplain} />
        </>
      )}

      {explanation && (
        <div style={{ marginTop:8, padding:8, background:"#f9fafb", borderRadius:6, fontSize:13 }}>
          {explanation.loading ? "Loading explanation…" : explanation.text}
        </div>
      )}

      {top100.length > 0 && !hideRunButton && (
        <PhaseResult phaseNum={5}
          stats={[
            { label:"Top Keywords", value:top100.length, color:"#3b82f6" },
            { label:"Pillars",      value:pillars.length, color:"#10b981" },
          ]}
          onNext={onNext || (() => setActivePhase(6))} />
      )}

      <NotificationList notifications={notifications} />
    </Card>
  )
}
