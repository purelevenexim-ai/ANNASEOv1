/**
 * Phase 4 — Scoring + Clustering + Keyword Segmentation.
 *
 * Features:
 *  - Composite scoring with multi-signal breakdown
 *  - Score distribution chart (CSS bar chart)
 *  - Keyword segments: Money / Growth / Support
 *  - Quick Wins detection
 *  - Auto strategy recommendations
 */
import React, { useState, useCallback, useMemo, useRef, useEffect } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, StatsRow, usePhaseRunner, PhaseResult, NotificationList } from "./shared"

// ── Segment thresholds ──────────────────────────────────────────────────────
const SEGMENTS = {
  money:   { label: "Money",   color: "#16a34a", bg: "#dcfce7", desc: "High commercial + high score — prioritize content now" },
  growth:  { label: "Growth",  color: "#2563eb", bg: "#dbeafe", desc: "High volume, mid competition — invest for 3-6 month payoff" },
  support: { label: "Support", color: "#7c3aed", bg: "#ede9fe", desc: "Informational & long-tail — build topical authority" },
}

function classifyKeyword(kw) {
  const score = kw.score ?? kw.composite_score ?? 0
  const intent = (kw.intent || "informational").toLowerCase()
  const commercial = kw.commercial_score ?? kw.buyer_readiness ?? 0

  if (commercial >= 0.6 && score >= 70) return "money"
  if ((intent === "commercial" || intent === "transactional") && score >= 60) return "money"
  if (score >= 50 && commercial < 0.6) return "growth"
  return "support"
}

function detectQuickWins(keywords) {
  return keywords
    .filter(kw => {
      const score = kw.score ?? kw.composite_score ?? 0
      const difficulty = kw.difficulty ?? kw.competition ?? 50
      return score >= 60 && difficulty <= 35
    })
    .sort((a, b) => (b.score ?? b.composite_score ?? 0) - (a.score ?? a.composite_score ?? 0))
    .slice(0, 10)
}

function generateRecommendations(segments, quickWins, stats) {
  const recs = []
  const moneyCount = segments.money?.length || 0
  const growthCount = segments.growth?.length || 0
  const supportCount = segments.support?.length || 0

  if (moneyCount > 0) {
    recs.push({ icon: "💰", text: `${moneyCount} money keywords found — create conversion-optimized pages first` })
  }
  if (quickWins.length >= 5) {
    recs.push({ icon: "⚡", text: `${quickWins.length} quick wins detected — low difficulty, high score. Target these in month 1` })
  }
  if (growthCount > moneyCount * 2) {
    recs.push({ icon: "📈", text: `Heavy growth keyword pool (${growthCount}) — plan a content calendar for sustained traffic` })
  }
  if (supportCount > (moneyCount + growthCount)) {
    recs.push({ icon: "📚", text: `Most keywords are support/informational — build topic clusters for authority` })
  }
  if (stats?.avg_score < 50) {
    recs.push({ icon: "⚠️", text: `Average score is low (${stats.avg_score?.toFixed(1)}) — consider refining pillars or expanding keyword discovery` })
  }
  if (recs.length === 0) {
    recs.push({ icon: "✅", text: "Good keyword distribution — proceed to tree building and content planning" })
  }
  return recs
}

// ── Score Distribution Bar Chart (pure CSS) ─────────────────────────────────

function ScoreDistChart({ distribution }) {
  if (!distribution || !Object.keys(distribution).length) return null
  const entries = Object.entries(distribution).sort(([a], [b]) => a.localeCompare(b))
  const max = Math.max(...entries.map(([, v]) => v), 1)
  const colors = ["#ef4444", "#f97316", "#eab308", "#84cc16", "#22c55e", "#14b8a6", "#3b82f6", "#6366f1", "#8b5cf6", "#a855f7"]

  return (
    <div style={{ marginBottom: 16 }}>
      <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: "#374151" }}>Score Distribution</h4>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 100, padding: "0 4px" }}>
        {entries.map(([range, count], i) => (
          <div key={range} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center" }}>
            <span style={{ fontSize: 10, color: "#6b7280", marginBottom: 2 }}>{count}</span>
            <div style={{
              width: "100%",
              height: `${(count / max) * 80}px`,
              background: colors[i % colors.length],
              borderRadius: "3px 3px 0 0",
              minHeight: 4,
              transition: "height 0.3s ease"
            }} />
            <span style={{ fontSize: 9, color: "#9ca3af", marginTop: 2, whiteSpace: "nowrap" }}>{range}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Keyword Segment Panel ───────────────────────────────────────────────────

function SegmentPanel({ segmentKey, keywords, onDragStart, onDragOver, onDrop, onDragEnd, isDragTarget }) {
  const [expanded, setExpanded] = useState(false)
  const seg = SEGMENTS[segmentKey]
  if (!keywords?.length && !isDragTarget) return null

  const shown = expanded ? keywords.slice(0, 25) : keywords.slice(0, 5)

  return (
    <div
      style={{
        marginBottom: 12, borderRadius: 8, overflow: "hidden",
        border: isDragTarget ? `2px dashed ${seg.color}` : `1px solid ${seg.color}22`,
        transition: "border 0.15s",
      }}
      onDragOver={(e) => { e.preventDefault(); onDragOver(segmentKey) }}
      onDrop={(e) => { e.preventDefault(); onDrop(segmentKey) }}
    >
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "8px 12px", background: seg.bg, cursor: "pointer",
        }}
      >
        <div>
          <span style={{ fontWeight: 600, color: seg.color, fontSize: 13 }}>{seg.label}</span>
          <span style={{ fontSize: 12, color: "#6b7280", marginLeft: 8 }}>{keywords.length} keywords</span>
          {isDragTarget && <span style={{ fontSize: 11, color: seg.color, marginLeft: 8, fontWeight: 600 }}>↓ Drop here</span>}
        </div>
        <span style={{ fontSize: 11, color: "#9ca3af" }}>{expanded ? "▲" : "▼"}</span>
      </div>
      <div style={{ padding: "6px 12px", fontSize: 11, color: "#6b7280", borderBottom: `1px solid ${seg.color}11` }}>
        {seg.desc}
      </div>
      {keywords.length > 0 && (
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f9fafb" }}>
              <th style={thStyle}>Keyword</th>
              <th style={thStyle}>Score</th>
              <th style={thStyle}>Intent</th>
              <th style={thStyle}>Difficulty</th>
              <th style={thStyle}>Pillar</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((kw, i) => (
              <tr
                key={kw.id || i}
                draggable
                onDragStart={(e) => { e.dataTransfer.effectAllowed = "move"; onDragStart(kw, segmentKey) }}
                onDragEnd={onDragEnd}
                style={{ borderBottom: "1px solid #f3f4f6", cursor: "grab" }}
              >
                <td style={{ ...tdStyle, userSelect: "none" }}>
                  <span style={{ marginRight: 5, color: "#d1d5db", fontSize: 11 }}>⠿</span>
                  {kw.keyword || kw.term}
                </td>
                <td style={{ ...tdStyle, fontWeight: 600, color: seg.color }}>{(kw.score ?? kw.composite_score ?? 0).toFixed(0)}</td>
                <td style={tdStyle}>{kw.intent || "—"}</td>
                <td style={tdStyle}>{kw.difficulty ?? kw.competition ?? "—"}</td>
                <td style={tdStyle}>{kw.pillar || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {keywords.length > 5 && !expanded && (
        <div style={{ padding: "6px 12px", fontSize: 11, color: "#3b82f6", cursor: "pointer" }} onClick={() => setExpanded(true)}>
          Show {Math.min(keywords.length, 25) - 5} more...
        </div>
      )}
    </div>
  )
}

const thStyle = { textAlign: "left", padding: "4px 8px", fontSize: 11, color: "#6b7280", fontWeight: 500 }
const tdStyle = { padding: "4px 8px", fontSize: 12 }

// ── Quick Wins Card ─────────────────────────────────────────────────────────

function QuickWinsCard({ keywords }) {
  if (!keywords?.length) return null
  return (
    <div style={{ marginBottom: 16, padding: 12, background: "#fffbeb", border: "1px solid #fbbf2422", borderRadius: 8 }}>
      <h4 style={{ fontSize: 13, fontWeight: 600, color: "#92400e", marginBottom: 8 }}>⚡ Quick Wins ({keywords.length})</h4>
      <p style={{ fontSize: 11, color: "#78716c", marginBottom: 8 }}>High score + low difficulty — target these first for fast results.</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {keywords.map((kw, i) => (
          <span key={i} style={{
            background: "#fef3c7", border: "1px solid #fbbf24", borderRadius: 12,
            padding: "3px 10px", fontSize: 11, color: "#92400e"
          }}>
            {kw.keyword || kw.term} <b>({(kw.score ?? kw.composite_score ?? 0).toFixed(0)})</b>
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Recommendations Card ────────────────────────────────────────────────────

function RecommendationsCard({ recommendations }) {
  if (!recommendations?.length) return null
  return (
    <div style={{ marginBottom: 16, padding: 12, background: "#f0fdf4", border: "1px solid #22c55e22", borderRadius: 8 }}>
      <h4 style={{ fontSize: 13, fontWeight: 600, color: "#15803d", marginBottom: 8 }}>Strategy Recommendations</h4>
      {recommendations.map((r, i) => (
        <div key={i} style={{ fontSize: 12, color: "#374151", marginBottom: 4 }}>
          <span style={{ marginRight: 6 }}>{r.icon}</span>{r.text}
        </div>
      ))}
    </div>
  )
}

// ── Main Component ──────────────────────────────────────────────────────────

export default function Phase4({ projectId, sessionId, onComplete, onNext, autoRun, hideRunButton }) {
  const { setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P4")
  const [result, setResult] = useState(null)
  const [keywords, setKeywords] = useState([])
  const [segmentOverrides, setSegmentOverrides] = useState({})
  const [dragTarget, setDragTarget] = useState(null)
  const dragRef = useRef(null)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    log("Scoring + clustering keywords...", "info")
    try {
      const data = await api.runPhase4(projectId, sessionId)
      setResult(data)

      // Fetch validated keywords for segmentation
      try {
        const vData = await api.getValidated(projectId, sessionId)
        setKeywords(vData.keywords || vData || [])
      } catch { /* scored data in result is enough */ }

      const scored = data.scoring?.scored || 0
      const clusters = data.clustering?.clusters || 0
      log(`Complete: ${scored} scored, ${clusters} clusters formed`, "success")
      toast(`Scoring complete: ${scored} keywords into ${clusters} clusters`, "success")
      onComplete()
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
      toast(`Phase 4 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  // ── Computed segments + quick wins + recs ─────────────────────────────

  const handleDragStart = useCallback((kw, fromSeg) => {
    dragRef.current = { keyword: kw, fromSegment: fromSeg }
  }, [])

  const handleDragOver = useCallback((segKey) => {
    if (dragRef.current) setDragTarget(segKey)
  }, [])

  const handleDrop = useCallback((toSeg) => {
    if (!dragRef.current) return
    const { keyword, fromSegment } = dragRef.current
    if (fromSegment !== toSeg) {
      const kwKey = keyword.id || keyword.keyword || keyword.term
      setSegmentOverrides((prev) => ({ ...prev, [kwKey]: toSeg }))
    }
    dragRef.current = null
    setDragTarget(null)
  }, [])

  const handleDragEnd = useCallback(() => {
    dragRef.current = null
    setDragTarget(null)
  }, [])

  const segments = useMemo(() => {
    const kws = Array.isArray(keywords) ? keywords : []
    const out = { money: [], growth: [], support: [] }
    kws.forEach(kw => {
      const kwKey = kw.id || kw.keyword || kw.term
      const seg = segmentOverrides[kwKey] || classifyKeyword(kw)
      out[seg].push(kw)
    })
    for (const key of Object.keys(out)) {
      out[key].sort((a, b) => (b.score ?? b.composite_score ?? 0) - (a.score ?? a.composite_score ?? 0))
    }
    return out
  }, [keywords, segmentOverrides])

  const quickWins = useMemo(() => detectQuickWins(Array.isArray(keywords) ? keywords : []), [keywords])
  const recommendations = useMemo(
    () => result ? generateRecommendations(segments, quickWins, result.scoring) : [],
    [result, segments, quickWins]
  )

  // autoRun: respond to prop changes — Phase4 is on the default tab so it's pre-mounted
  // when Run All fires. Empty [] would not re-fire when autoRun changes false→true.
  useEffect(() => { if (autoRun) run() }, [autoRun]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card title="Phase 4: Score & Cluster" actions={hideRunButton ? null : <RunButton onClick={run} loading={loading}>Score + Cluster</RunButton>}>
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 10 }}>
        Composite scoring (relevance, intent, volume, commercial, buyer readiness) + semantic clustering + keyword segmentation.
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

          <StatsRow items={[
            { label: "Money KWs", value: segments.money.length, color: SEGMENTS.money.color },
            { label: "Growth KWs", value: segments.growth.length, color: SEGMENTS.growth.color },
            { label: "Support KWs", value: segments.support.length, color: SEGMENTS.support.color },
            { label: "Quick Wins", value: quickWins.length, color: "#d97706" },
          ]} />

          <ScoreDistChart distribution={result.scoring?.score_distribution} />

          <RecommendationsCard recommendations={recommendations} />
          <QuickWinsCard keywords={quickWins} />

          {/* Keyword Segments — drag keywords between sections */}
          {Object.keys(segmentOverrides).length > 0 && (
            <div style={{ marginBottom: 8, padding: "6px 10px", background: "#f0fdf4", borderRadius: 6, fontSize: 12, color: "#15803d" }}>
              {Object.keys(segmentOverrides).length} keyword{Object.keys(segmentOverrides).length > 1 ? "s" : ""} manually reassigned
              <button onClick={() => setSegmentOverrides({})} style={{ marginLeft: 10, fontSize: 11, color: "#dc2626", background: "none", border: "none", cursor: "pointer" }}>Reset</button>
            </div>
          )}
          {["money", "growth", "support"].map(seg => (
            <SegmentPanel
              key={seg}
              segmentKey={seg}
              keywords={segments[seg]}
              onDragStart={handleDragStart}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              onDragEnd={handleDragEnd}
              isDragTarget={dragTarget === seg}
            />
          ))}

          <PhaseResult
            phaseNum={4}
            stats={[
              { label: "Scored", value: result.scoring?.scored || 0, color: "#3b82f6" },
              { label: "Clusters", value: result.clustering?.clusters || 0, color: "#8b5cf6" },
              { label: "Money", value: segments.money.length, color: "#16a34a" },
              { label: "Quick Wins", value: quickWins.length, color: "#d97706" },
            ]}
            onNext={onNext || (() => setActivePhase(5))}
          />
        </>
      )}

      <NotificationList notifications={notifications} />
    </Card>
  )
}
