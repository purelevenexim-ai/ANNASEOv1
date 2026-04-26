/**
 * Tab 3: Score & Validate (v2)
 *
 * Changes vs v1:
 *  - Bug fix: per-pillar top-20 via getTop100(pillar) — avoids pillar-collapse after Phase 4
 *  - Phase 3 streaming mode with per-pillar progress (pillar_start/batch/complete events)
 *  - Segment panels: Money / Growth / Support with drag-drop reclassification
 *  - Score distribution chart (CSS bars, 0-20 / 20-40 / 40-60 / 60-80 / 80-100)
 *  - Quick Wins detection (score ≥ 60 AND difficulty ≤ 35)
 *  - Auto strategy recommendations
 *  - Per-pillar keyword search/filter
 *  - Manual add keyword form
 */
import React, { useMemo, useState, useEffect, useRef, useCallback } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  runPhase3, runPhase4, getValidated, deleteKeyword, rejectKeywords,
  getTop100, getProfile, streamPhase3, addKeyword,
} from "./api"
import { Card, Btn, Spinner, T, Stat, Badge, Empty, Input, ProgressBar } from "./ui"

// ── Constants ─────────────────────────────────────────────────────────────────
const TOP_N = 20
const LS_APPROVE = (sid) => `kw3:approve:${sid}`

const STOP_WORDS = new Set([
  "a", "an", "and", "or", "the", "for", "with", "to", "in", "on", "of",
  "is", "are", "from", "by", "at", "near", "vs", "online",
])

function normalizeKw(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

function inferIntent(kw) {
  const text = normalizeKw(kw.keyword || kw.term || "")
  const existing = String(kw.intent || "").toLowerCase()
  if (existing) return existing
  if (/(buy|price|wholesale|order|deal|bulk|shop|supplier)/.test(text)) return "transactional"
  if (/(best|top|quality|review|compare|vs)/.test(text)) return "commercial"
  if (/(benefits|uses|how to|what is|guide|tips)/.test(text)) return "informational"
  return "informational"
}

function intentStrength(kw) {
  const intent = inferIntent(kw)
  if (intent === "transactional") return 0.95
  if (intent === "commercial") return 0.8
  if (intent === "informational") return 0.65
  return 0.5
}

function conversionPotential(kw) {
  const text = normalizeKw(kw.keyword || kw.term || "")
  let score = 0.4
  if (/(buy|price|wholesale|order|deal|bulk|shop)/.test(text)) score += 0.4
  if (/(best|top|quality|review|compare)/.test(text)) score += 0.2
  return Math.min(1, score)
}

function semanticCluster(kw) {
  const toks = normalizeKw(kw.keyword || kw.term || "").split(" ").filter(t => t && !STOP_WORDS.has(t))
  if (toks.length === 0) return "general"
  if (toks.includes("buy") || toks.includes("price") || toks.includes("wholesale")) return "purchase intent"
  if (toks.includes("benefits") || toks.includes("uses") || toks.includes("guide")) return "education"
  if (toks.includes("best") || toks.includes("review") || toks.includes("compare")) return "evaluation"
  if (toks.includes("india") || toks.includes("kerala") || (toks.includes("near") && toks.includes("me"))) return "geo"
  return toks.slice(0, 2).join(" ")
}

function enrichKeyword(kw, modifiers = []) {
  const keyword = String(kw.keyword || kw.term || "").trim()
  const intent = inferIntent(kw)
  const diffRaw = kw.difficulty ?? kw.competition ?? 50
  const difficulty = Number.isFinite(Number(diffRaw)) ? Number(diffRaw) : 50
  const intent_strength = intentStrength(kw)
  const conversion_potential = conversionPotential(kw)
  const baseScore = Number(kw.final_score ?? kw.score ?? 0)
  const modifierBoost = modifiers.some(m => keyword.toLowerCase().includes(String(m).toLowerCase())) ? 6 : 0
  const quality_score = Math.max(
    0,
    Math.min(100, baseScore * 0.55 + intent_strength * 25 + conversion_potential * 20 + modifierBoost - difficulty * 0.12)
  )

  return {
    ...kw,
    keyword,
    intent,
    difficulty,
    intent_strength,
    conversion_potential,
    quality_score,
    final_score: kw.final_score ?? quality_score,
    cluster: kw.cluster || semanticCluster(kw),
  }
}

function selectTop20PerPillar(items, modifiers = []) {
  const dedup = new Map()
  for (const raw of items || []) {
    const k = enrichKeyword(raw, modifiers)
    const nk = normalizeKw(k.keyword)
    if (!nk) continue
    if (/(free wallpaper|image|meaning in hindi|copy paste)/.test(nk)) continue
    const prev = dedup.get(nk)
    if (!prev || (k.quality_score ?? 0) > (prev.quality_score ?? 0)) dedup.set(nk, k)
  }

  const pool = [...dedup.values()].sort((a, b) => (b.quality_score ?? 0) - (a.quality_score ?? 0))
  const intentBuckets = { informational: [], commercial: [], transactional: [] }
  for (const k of pool) {
    if (!intentBuckets[k.intent]) intentBuckets.informational.push(k)
    else intentBuckets[k.intent].push(k)
  }

  const targets = { informational: 7, commercial: 7, transactional: 6 }
  const picked = []
  for (const intent of ["transactional", "commercial", "informational"]) {
    const need = targets[intent]
    picked.push(...intentBuckets[intent].slice(0, need))
  }

  if (picked.length < TOP_N) {
    const seen = new Set(picked.map(k => normalizeKw(k.keyword)))
    for (const k of pool) {
      const nk = normalizeKw(k.keyword)
      if (seen.has(nk)) continue
      picked.push(k)
      seen.add(nk)
      if (picked.length >= TOP_N) break
    }
  }

  return picked.slice(0, TOP_N)
}

const PASSES = ["rule_filter", "prescore", "ai_batch", "dedup", "balance"]
const PASS_LABELS = {
  rule_filter: "Rule Filter",
  prescore:    "Pre-Score Engine",
  ai_batch:    "AI Validation",
  dedup:       "Semantic Dedup",
  balance:     "Category Balance",
}

// ── Segment config ────────────────────────────────────────────────────────────
const SEGMENTS = {
  money:   { label: "Money Keywords",   color: "#16a34a", bg: "#dcfce7", desc: "High commercial intent — prioritize these pages first" },
  growth:  { label: "Growth Keywords",  color: "#2563eb", bg: "#dbeafe", desc: "High volume, mid competition — invest for 3-6 month payoff" },
  support: { label: "Support Keywords", color: "#7c3aed", bg: "#ede9fe", desc: "Informational & long-tail — build topical authority" },
}

function classifyKeyword(kw) {
  const score      = kw.final_score ?? kw.score ?? kw.composite_score ?? 0
  const intent     = (kw.intent || "informational").toLowerCase()
  const commercial = kw.commercial_score ?? kw.buyer_readiness ?? 0
  if (commercial >= 0.6 && score >= 70)  return "money"
  if ((intent === "commercial" || intent === "transactional") && score >= 60) return "money"
  if (score >= 50 && commercial < 0.6)   return "growth"
  return "support"
}

function detectQuickWins(keywords) {
  return keywords
    .filter(kw => {
      const score      = kw.final_score ?? kw.score ?? 0
      const difficulty = kw.difficulty ?? kw.competition ?? 50
      return score >= 60 && difficulty <= 35
    })
    .sort((a, b) => (b.final_score ?? b.score ?? 0) - (a.final_score ?? a.score ?? 0))
    .slice(0, 10)
}

function generateRecommendations(segments, quickWins, avgScore) {
  const recs = []
  const mc = segments.money?.length || 0
  const gc = segments.growth?.length || 0
  const sc = segments.support?.length || 0
  if (mc > 0) recs.push({ icon: "💰", text: `${mc} money keywords found — create conversion-optimized pages first` })
  if (quickWins.length >= 3) recs.push({ icon: "⚡", text: `${quickWins.length} quick wins detected — low difficulty, high score. Target these in month 1` })
  if (gc > mc * 2) recs.push({ icon: "📈", text: `Heavy growth keyword pool (${gc}) — plan a content calendar for sustained traffic` })
  if (sc > mc + gc) recs.push({ icon: "📚", text: `Most keywords are informational — build topic clusters for authority first` })
  if (avgScore != null && avgScore < 50) recs.push({ icon: "⚠️", text: `Average score is low (${avgScore.toFixed(1)}) — consider refining pillars or expanding keyword discovery` })
  if (recs.length === 0) recs.push({ icon: "✅", text: "Good keyword distribution — proceed to tree building and content planning" })
  return recs
}

// ── Score Distribution Chart ──────────────────────────────────────────────────
function ScoreDistChart({ items }) {
  if (!items?.length) return null
  const dist = { "0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0 }
  items.forEach(kw => {
    const s = kw.final_score ?? kw.score ?? 0
    if (s < 20)       dist["0-20"]++
    else if (s < 40)  dist["20-40"]++
    else if (s < 60)  dist["40-60"]++
    else if (s < 80)  dist["60-80"]++
    else              dist["80-100"]++
  })
  const entries = Object.entries(dist)
  const max = Math.max(...entries.map(([, v]) => v), 1)
  const colors = { "0-20": "#ef4444", "20-40": "#f97316", "40-60": "#eab308", "60-80": "#84cc16", "80-100": "#22c55e" }
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 8 }}>Score Distribution</div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 80 }}>
        {entries.map(([range, count]) => (
          <div key={range} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center" }}>
            <span style={{ fontSize: 10, color: "#6b7280", marginBottom: 2 }}>{count}</span>
            <div style={{
              width: "100%", height: `${(count / max) * 60}px`,
              background: colors[range], borderRadius: "3px 3px 0 0", minHeight: 3,
              transition: "height 0.3s ease",
            }} />
            <span style={{ fontSize: 9, color: "#9ca3af", marginTop: 2 }}>{range}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Segment Panel ─────────────────────────────────────────────────────────────
function SegmentPanel({ segKey, keywords, onDragStart, onDragOver, onDrop, onDragEnd, isDragTarget }) {
  const [expanded, setExpanded] = useState(false)
  const seg = SEGMENTS[segKey]
  if (!keywords?.length && !isDragTarget) return null
  const shown = expanded ? keywords.slice(0, 30) : keywords.slice(0, 5)
  return (
    <div
      style={{
        marginBottom: 10, borderRadius: 8, overflow: "hidden",
        border: isDragTarget ? `2px dashed ${seg.color}` : `1px solid ${seg.color}33`,
        transition: "border 0.15s",
      }}
      onDragOver={e => { e.preventDefault(); onDragOver(segKey) }}
      onDrop={e => { e.preventDefault(); onDrop(segKey) }}
    >
      <div
        onClick={() => setExpanded(!expanded)}
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: seg.bg, cursor: "pointer" }}
      >
        <div>
          <span style={{ fontWeight: 700, color: seg.color, fontSize: 13 }}>{seg.label}</span>
          <span style={{ fontSize: 12, color: "#6b7280", marginLeft: 8 }}>{keywords.length} keywords</span>
          {isDragTarget && <span style={{ fontSize: 11, color: seg.color, marginLeft: 8, fontWeight: 600 }}>↓ Drop here</span>}
        </div>
        <span style={{ fontSize: 11, color: "#9ca3af" }}>{expanded ? "▲" : "▼"}</span>
      </div>
      <div style={{ padding: "4px 12px", fontSize: 11, color: "#6b7280", borderBottom: `1px solid ${seg.color}11` }}>
        {seg.desc}
      </div>
      {keywords.length > 0 && (
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f9fafb" }}>
              {["Keyword", "Score", "Intent", "Difficulty", "Pillar"].map(h => (
                <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontSize: 11, color: "#6b7280", fontWeight: 500 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((kw, i) => (
              <tr
                key={kw.id || i}
                draggable
                onDragStart={e => { e.dataTransfer.effectAllowed = "move"; onDragStart(kw, segKey) }}
                onDragEnd={onDragEnd}
                style={{ borderBottom: "1px solid #f3f4f6", cursor: "grab" }}
              >
                <td style={{ padding: "4px 8px" }}>
                  <span style={{ marginRight: 5, color: "#d1d5db", fontSize: 11 }}>⠿</span>
                  {kw.keyword || kw.term}
                </td>
                <td style={{ padding: "4px 8px", fontWeight: 600, color: seg.color }}>
                  {(kw.final_score ?? kw.score ?? 0).toFixed(0)}
                </td>
                <td style={{ padding: "4px 8px" }}>{kw.intent || "—"}</td>
                <td style={{ padding: "4px 8px" }}>{kw.difficulty ?? kw.competition ?? "—"}</td>
                <td style={{ padding: "4px 8px" }}>{kw.pillar || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {keywords.length > 5 && !expanded && (
        <div
          onClick={() => setExpanded(true)}
          style={{ padding: "6px 12px", fontSize: 11, color: "#3b82f6", cursor: "pointer" }}
        >
          Show {Math.min(keywords.length, 30) - 5} more…
        </div>
      )}
    </div>
  )
}

// ── Quick Wins Card ───────────────────────────────────────────────────────────
function QuickWinsCard({ keywords }) {
  if (!keywords?.length) return null
  return (
    <div style={{ marginBottom: 12, padding: 12, background: "#fffbeb", border: "1px solid #fbbf2440", borderRadius: 8 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#92400e", marginBottom: 6 }}>⚡ Quick Wins ({keywords.length})</div>
      <div style={{ fontSize: 11, color: "#78716c", marginBottom: 8 }}>High score + low difficulty — target these first for fast results.</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {keywords.map((kw, i) => (
          <span key={i} style={{ background: "#fef3c7", border: "1px solid #fbbf24", borderRadius: 12, padding: "3px 10px", fontSize: 11, color: "#92400e" }}>
            {kw.keyword || kw.term} <b>({(kw.final_score ?? kw.score ?? 0).toFixed(0)})</b>
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Recommendations Card ──────────────────────────────────────────────────────
function RecommendationsCard({ recs }) {
  if (!recs?.length) return null
  return (
    <div style={{ marginBottom: 12, padding: 12, background: "#f0fdf4", border: "1px solid #22c55e22", borderRadius: 8 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#15803d", marginBottom: 8 }}>Strategy Recommendations</div>
      {recs.map((r, i) => (
        <div key={i} style={{ fontSize: 12, color: "#374151", marginBottom: 4 }}>
          <span style={{ marginRight: 6 }}>{r.icon}</span>{r.text}
        </div>
      ))}
    </div>
  )
}

// ── Phase 3 Stream Progress Panel ─────────────────────────────────────────────
function Phase3StreamPanel({ passInfo, activePass, pillarProgress, activePillar }) {
  const completedPasses = PASSES.filter(p => passInfo[p]).length
  const pct = (completedPasses / PASSES.length) * 100
  const pillarNames = Object.keys(pillarProgress)
  return (
    <div style={{ marginBottom: 12 }}>
      <ProgressBar pct={pct} color="#8b5cf6" />
      <div style={{ marginTop: 8 }}>
        {PASSES.map(pass => {
          const info     = passInfo[pass]
          const isActive = activePass === pass
          const done     = !!info
          return (
            <div key={pass} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3, fontSize: 12 }}>
              <span style={{ width: 155, color: done ? T.success : isActive ? "#8b5cf6" : T.textSoft, fontWeight: done || isActive ? 600 : 400 }}>
                {done ? "✓ " : isActive ? "▶ " : ""}{PASS_LABELS[pass]}
              </span>
              {done && <span style={{ color: T.error, fontSize: 11 }}>-{info.rejected || info.removed || 0}</span>}
              {done && info.remaining != null && <span style={{ color: T.textSoft, fontSize: 11 }}>({info.remaining} left)</span>}
              {isActive && !done && <span style={{ color: "#8b5cf6", fontSize: 11 }}>processing…</span>}
            </div>
          )
        })}
      </div>
      {pillarNames.length > 0 && (
        <div style={{ marginTop: 12, padding: 10, background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 6 }}>Per-Pillar AI Validation</div>
          {pillarNames.map(pn => {
            const pp       = pillarProgress[pn]
            const isActive = activePillar === pn
            const isDone   = pp.status === "done" || pp.status === "early_stop"
            const barPct   = pp.total > 0 ? ((pp.current || 0) / pp.total) * 100 : 0
            return (
              <div key={pn} style={{ marginBottom: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                  <span style={{ fontSize: 12, fontWeight: isActive ? 600 : 400, color: isDone ? T.success : isActive ? "#8b5cf6" : T.textSoft }}>
                    {isDone ? "✓ " : isActive ? "▶ " : ""}{pn}
                    {pp.status === "early_stop" && <span style={{ fontSize: 10, color: T.warn, marginLeft: 4 }}>(early stop)</span>}
                  </span>
                  <span style={{ fontSize: 11, color: T.textSoft }}>
                    {pp.accepted || 0} accepted{pp.total ? ` · ${pp.current || 0}/${pp.total} batches` : ""}
                  </span>
                </div>
                {(isActive || isDone) && pp.total > 0 && (
                  <ProgressBar pct={barPct} color={isDone ? T.success : T.primary} height={5} />
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Pillar Block ───────────────────────────────────────────────────────────────
function PillarBlock({ pillar, top, picks, setPick, clearPick, hasScores, onDelete, onApproveAll, onClearAll }) {
  const [filter, setFilter] = useState("")
  const approvedHere = top.filter(i => picks[i.id] === "approved").length
  const visible = filter
    ? top.filter(i => i.keyword?.toLowerCase().includes(filter.toLowerCase()))
    : top

  return (
    <Card>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>
            {pillar} <Badge color={T.textSoft}>{top.length}</Badge>
            {approvedHere > 0 && <span>&nbsp;<Badge color={T.success}>{approvedHere} approved</Badge></span>}
          </div>
          <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>Top {top.length} by score</div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <Input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter keywords…"
            style={{ width: 160, padding: "5px 10px", fontSize: 12 }}
          />
          <Btn variant="success" onClick={onApproveAll} style={{ padding: "6px 12px", fontSize: 12 }}>✓ Approve all</Btn>
          {approvedHere > 0 && (
            <Btn variant="ghost" onClick={onClearAll} style={{ padding: "6px 12px", fontSize: 12 }}>Clear picks</Btn>
          )}
        </div>
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.border}`, color: T.textSoft, fontSize: 11, textTransform: "uppercase" }}>
            <th style={th(28)}>#</th>
            <th style={{ ...th(), textAlign: "left" }}>Keyword</th>
            <th style={th(90)}>Intent</th>
            {hasScores && <th style={th(60)}>Score</th>}
            <th style={th(66)}>Diff</th>
            <th style={th(62)}>Intent%</th>
            <th style={th(62)}>Conv%</th>
            <th style={th(200)}>Action</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((it, i) => {
            const pick = picks[it.id]
            const bg = pick === "approved" ? T.successBg : pick === "rejected" ? T.errorBg : "transparent"
            return (
              <tr key={it.id} style={{ borderBottom: `1px solid ${T.border}`, background: bg }}>
                <td style={td(28)}>{i + 1}</td>
                <td style={td()}>
                  <div style={{
                    fontWeight: pick === "approved" ? 600 : 400,
                    color: pick === "rejected" ? T.textMute : T.text,
                    textDecoration: pick === "rejected" ? "line-through" : "none",
                  }}>{it.keyword}</div>
                  {it.cluster && <div style={{ fontSize: 10, color: T.textMute }}>cluster: {it.cluster}</div>}
                </td>
                <td style={{ ...td(90), textAlign: "center" }}>
                  {it.intent && <Badge color={intentColor(it.intent)}>{it.intent}</Badge>}
                </td>
                {hasScores && (
                  <td style={{ ...td(60), textAlign: "center", fontWeight: 600, color: scoreColor(it.final_score ?? it.score) }}>
                    {(it.final_score ?? it.score) != null ? Number(it.final_score ?? it.score).toFixed(1) : "—"}
                  </td>
                )}
                <td style={{ ...td(66), textAlign: "center" }}>
                  {Number.isFinite(Number(it.difficulty)) ? Number(it.difficulty).toFixed(0) : "—"}
                </td>
                <td style={{ ...td(62), textAlign: "center" }}>
                  {Number.isFinite(Number(it.intent_strength)) ? `${Math.round(Number(it.intent_strength) * 100)}` : "—"}
                </td>
                <td style={{ ...td(62), textAlign: "center" }}>
                  {Number.isFinite(Number(it.conversion_potential)) ? `${Math.round(Number(it.conversion_potential) * 100)}` : "—"}
                </td>
                <td style={{ ...td(200), textAlign: "right" }}>
                  <Btn
                    variant={pick === "approved" ? "success" : "ghost"}
                    onClick={() => pick === "approved" ? clearPick(it.id) : setPick(it.id, "approved")}
                    style={{ padding: "4px 10px", fontSize: 11, marginRight: 4 }}
                  >{pick === "approved" ? "✓ Approved" : "Approve"}</Btn>
                  <Btn
                    variant={pick === "rejected" ? "danger" : "ghost"}
                    onClick={() => pick === "rejected" ? clearPick(it.id) : setPick(it.id, "rejected")}
                    style={{ padding: "4px 10px", fontSize: 11, marginRight: 4 }}
                  >{pick === "rejected" ? "✗ Rejected" : "Reject"}</Btn>
                  <Btn variant="ghost" onClick={() => onDelete(it.id)} style={{ padding: "4px 8px", fontSize: 11 }}>🗑</Btn>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {visible.length === 0 && filter && (
        <div style={{ textAlign: "center", padding: "12px 0", color: T.textMute, fontSize: 12 }}>
          No keywords matching "{filter}"
        </div>
      )}
    </Card>
  )
}

const th = (w) => ({ padding: "8px 10px", fontWeight: 600, textAlign: "center", ...(w ? { width: w } : {}) })
const td = (w) => ({ padding: "8px 10px", verticalAlign: "middle", ...(w ? { width: w } : {}) })

function intentColor(intent) {
  return ({
    informational: T.primary,
    commercial:    T.warn,
    transactional: T.success,
    navigational:  T.textSoft,
  })[String(intent).toLowerCase()] || T.textSoft
}

function scoreColor(score) {
  if (score == null) return T.textMute
  if (score >= 80)   return T.success
  if (score >= 60)   return T.primary
  if (score >= 40)   return T.warn
  return T.error
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function TabValidateScore({ projectId, sessionId, session, onDone }) {
  const qc = useQueryClient()

  // ── Profile (for pillar list & fallback) ──────────────────────────────────
  const profileQ = useQuery({
    queryKey: ["kw3", projectId, "profile"],
    queryFn:  () => getProfile(projectId),
    enabled:  !!projectId,
    staleTime: 30_000,
  })
  const profile = profileQ.data?.profile
  const profileModifiers = useMemo(() => {
    const mods = profile?.modifiers || profile?.manual_input?.modifiers || []
    return Array.isArray(mods) ? mods : []
  }, [profile])

  const confirmedPillars = useMemo(() => {
    const p = session?.confirmed_pillars
      || profile?.pillars
      || profile?.manual_input?.pillars
      || []
    return Array.isArray(p) ? p : []
  }, [session?.confirmed_pillars, profile])

  // ── Validated items (total count + segment data) ──────────────────────────
  const validatedQ = useQuery({
    queryKey: ["kw3", projectId, "validated", sessionId],
    queryFn:  () => getValidated(projectId, sessionId),
    enabled:  !!sessionId,
    staleTime: 5_000,
  })
  const allItems = validatedQ.data?.items || []

  // ── Per-pillar top-20 (bug fix: use getTop100 per pillar) ─────────────────
  const [pillarData, setPillarData]       = useState({})
  const [pillarDataLoading, setPillarDataLoading] = useState(false)

  const loadPillarData = useCallback(async () => {
    if (!confirmedPillars.length) return
    setPillarDataLoading(true)
    try {
      const results = await Promise.all(
        confirmedPillars.map(p => getTop100(projectId, sessionId, p))
      )
      const data = {}
      confirmedPillars.forEach((p, i) => {
        const items = results[i]?.keywords || results[i]?.items || (Array.isArray(results[i]) ? results[i] : [])
        data[p] = selectTop20PerPillar(items, profileModifiers)
      })
      setPillarData(data)
    } catch {}
    setPillarDataLoading(false)
  }, [projectId, sessionId, confirmedPillars, profileModifiers])

  useEffect(() => {
    if (sessionId && confirmedPillars.length && (session?.phase4_done || session?.phase3_done)) {
      loadPillarData()
    }
  }, [sessionId, confirmedPillars.join("|"), session?.phase4_done, session?.phase3_done]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Build display blocks ──────────────────────────────────────────────────
  const { byPillar, pillars, displayed } = useMemo(() => {
    if (Object.keys(pillarData).length > 0) {
      let count = 0
      const top = {}
      for (const [p, items] of Object.entries(pillarData)) {
        const sorted = [...items].sort((a, b) => (b.quality_score ?? b.final_score ?? b.score ?? 0) - (a.quality_score ?? a.final_score ?? a.score ?? 0))
        top[p] = sorted.slice(0, TOP_N)
        count += top[p].length
      }
      return { byPillar: top, pillars: Object.keys(top), displayed: count }
    }
    // Fallback: group allItems by pillar field
    const groups = {}
    for (const it of allItems) {
      const p = it.pillar || "(unassigned)"
      if (!groups[p]) groups[p] = []
      groups[p].push(it)
    }
    const top = {}
    let count = 0
    for (const p of Object.keys(groups)) {
      top[p] = selectTop20PerPillar(groups[p], profileModifiers)
      count += top[p].length
    }
    return { byPillar: top, pillars: Object.keys(top), displayed: count }
  }, [pillarData, allItems, profileModifiers])

  // ── Approve/reject picks ──────────────────────────────────────────────────
  const [picks, setPicks] = useState(() => {
    try { return JSON.parse(localStorage.getItem(LS_APPROVE(sessionId)) || "{}") } catch { return {} }
  })
  useEffect(() => {
    localStorage.setItem(LS_APPROVE(sessionId), JSON.stringify(picks))
  }, [picks, sessionId])

  const setPick   = (id, val) => setPicks(p => ({ ...p, [id]: val }))
  const clearPick = (id) => setPicks(p => { const n = { ...p }; delete n[id]; return n })

  // ── Phase 3 batch mutation ────────────────────────────────────────────────
  const phase3Mut = useMutation({
    mutationFn: () => runPhase3(projectId, sessionId),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ["kw3", projectId, "validated", sessionId] })
      qc.invalidateQueries({ queryKey: ["kw3", projectId, "session", sessionId] })
    },
  })

  // ── Phase 4 mutation ──────────────────────────────────────────────────────
  const phase4Mut = useMutation({
    mutationFn: () => runPhase4(projectId, sessionId),
    onSuccess:  async () => {
      qc.invalidateQueries({ queryKey: ["kw3", projectId, "validated", sessionId] })
      qc.invalidateQueries({ queryKey: ["kw3", projectId, "session", sessionId] })
      await loadPillarData()
    },
  })

  const runBatchValidateAndScore = async () => {
    if (!session?.phase3_done) await phase3Mut.mutateAsync()
    await phase4Mut.mutateAsync()
  }

  // ── Phase 3 SSE streaming ─────────────────────────────────────────────────
  const [streaming3,    setStreaming3]    = useState(false)
  const [passInfo,      setPassInfo]      = useState({})
  const [activePass,    setActivePass]    = useState(null)
  const [pillarProgress, setPillarProgress] = useState({})
  const [activePillar3, setActivePillar3] = useState(null)
  const [stream3Err,    setStream3Err]    = useState("")
  const stop3Ref = useRef(null)

  const runStream3 = () => {
    if (streaming3) return
    setStreaming3(true)
    setPassInfo({}); setActivePass(null); setPillarProgress({}); setActivePillar3(null); setStream3Err("")
    stop3Ref.current = streamPhase3(projectId, sessionId, (ev) => {
      if (ev.type === "phase") {
        setActivePass(ev.name)
        setPassInfo(prev => ({
          ...prev,
          [ev.name]: { rejected: ev.rejected || ev.removed || 0, remaining: ev.remaining, accepted: ev.accepted },
        }))
      }
      if (ev.type === "pillar_start") {
        setActivePillar3(ev.pillar)
        setActivePass("ai_batch")
        setPillarProgress(prev => ({
          ...prev,
          [ev.pillar]: { total: ev.total_batches, current: 0, accepted: 0, status: "running" },
        }))
      }
      if (ev.type === "pillar_batch") {
        setPillarProgress(prev => ({
          ...prev,
          [ev.pillar]: { ...prev[ev.pillar], current: ev.batch, accepted: ev.pillar_accepted, rate: ev.rate },
        }))
      }
      if (ev.type === "pillar_early_stop") {
        setPillarProgress(prev => ({ ...prev, [ev.pillar]: { ...prev[ev.pillar], status: "early_stop" } }))
      }
      if (ev.type === "pillar_complete") {
        setPillarProgress(prev => ({
          ...prev,
          [ev.pillar]: { ...prev[ev.pillar], status: "done", accepted: ev.accepted, rejected: ev.rejected },
        }))
        setActivePillar3(null)
      }
      if (ev.type === "complete") {
        setActivePass(null); setActivePillar3(null)
      }
      if (ev.done && !ev.error) {
        setStreaming3(false)
        qc.invalidateQueries({ queryKey: ["kw3", projectId, "validated", sessionId] })
        qc.invalidateQueries({ queryKey: ["kw3", projectId, "session", sessionId] })
      }
      if (ev.error || ev.type === "error") {
        setStreaming3(false)
        setStream3Err(ev.message || "Stream error")
      }
    })
  }
  useEffect(() => () => stop3Ref.current?.(), [])

  // ── Segment data ──────────────────────────────────────────────────────────
  const [segmentOverrides, setSegmentOverrides] = useState({})
  const [dragTarget, setDragTarget] = useState(null)
  const dragRef = useRef(null)

  const segments = useMemo(() => {
    const out = { money: [], growth: [], support: [] }
    allItems.forEach(kw => {
      const key = kw.id || kw.keyword
      const seg = segmentOverrides[key] || classifyKeyword(kw)
      out[seg].push(kw)
    })
    for (const k of Object.keys(out)) {
      out[k].sort((a, b) => (b.final_score ?? b.score ?? 0) - (a.final_score ?? a.score ?? 0))
    }
    return out
  }, [allItems, segmentOverrides])

  const quickWins = useMemo(() => detectQuickWins(allItems), [allItems])

  const avgScore = useMemo(() => {
    const scores = allItems.map(k => k.final_score ?? k.score).filter(s => s != null)
    return scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null
  }, [allItems])

  const recs = useMemo(() => {
    if (!session?.phase4_done || !allItems.length) return []
    return generateRecommendations(segments, quickWins, avgScore)
  }, [session?.phase4_done, segments, quickWins, avgScore]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Delete/reject mutations ───────────────────────────────────────────────
  const deleteMut     = useMutation({ mutationFn: (id)  => deleteKeyword(projectId, sessionId, id) })
  const rejectBulkMut = useMutation({ mutationFn: (ids) => rejectKeywords(projectId, sessionId, ids) })

  // ── Manual add keyword form ───────────────────────────────────────────────
  const [addForm, setAddForm] = useState({ show: false, keyword: "", pillar: "", intent: "informational" })
  const addMut = useMutation({
    mutationFn: (body) => addKeyword(projectId, sessionId, body),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ["kw3", projectId, "validated", sessionId] })
      setAddForm(f => ({ ...f, keyword: "", show: false }))
    },
  })

  // ── Continue flow ─────────────────────────────────────────────────────────
  const [advancing, setAdvancing] = useState(false)
  const continueWithApproved = async () => {
    const approvedIds = new Set(
      Object.entries(picks).filter(([, v]) => v === "approved").map(([k]) => k)
    )
    if (approvedIds.size === 0) { alert("Approve at least one keyword before continuing."); return }
    const visibleIds = Object.values(byPillar).flat().map(i => i.id)
    const toDelete   = visibleIds.filter(id => !approvedIds.has(id))
    if (toDelete.length > 0) {
      const ok = confirm(
        `Delete ${toDelete.length} unapproved keyword(s) and keep ${approvedIds.size} approved? This cannot be undone.`
      )
      if (!ok) return
      setAdvancing(true)
      try {
        await rejectBulkMut.mutateAsync(toDelete)
      } catch {
        for (const id of toDelete) { try { await deleteMut.mutateAsync(id) } catch {} }
      }
      setAdvancing(false)
      qc.invalidateQueries({ queryKey: ["kw3", projectId, "validated", sessionId] })
    }
    onDone?.()
  }

  const isRunning       = phase3Mut.isPending || phase4Mut.isPending
  const phase4Done      = !!session?.phase4_done
  const hasScores       = allItems.some(i => typeof (i.final_score ?? i.score) === "number")
  const approvedCount   = Object.values(picks).filter(v => v === "approved").length
  const rejectedCount   = Object.values(picks).filter(v => v === "rejected").length

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: "grid", gap: 16 }}>

      {/* ── Control card ───────────────────────────────────────────────── */}
      <Card>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>Validate & Score</div>
            <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
              6-pass validation pipeline: rule filter → pre-score → AI → dedup → balance → scoring.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Btn
              onClick={runStream3}
              disabled={streaming3 || isRunning || !session?.phase2_done}
              variant="secondary"
            >
              {streaming3
                ? <><Spinner color={T.primary} />&nbsp;Streaming validate…</>
                : "Stream Validate"}
            </Btn>
            <Btn
              onClick={runBatchValidateAndScore}
              disabled={isRunning || streaming3 || !session?.phase2_done}
            >
              {isRunning
                ? <><Spinner color="#fff" />&nbsp;{phase3Mut.isPending ? "Validating…" : "Scoring…"}</>
                : phase4Done ? "Re-run (Batch)" : "Batch Validate & Score"}
            </Btn>
            {session?.phase3_done && !phase4Done && (
              <Btn onClick={() => phase4Mut.mutate()} disabled={phase4Mut.isPending}>
                {phase4Mut.isPending ? <><Spinner color="#fff" />&nbsp;Scoring…</> : "Run Scoring →"}
              </Btn>
            )}
            {phase4Done && approvedCount > 0 && (
              <Btn variant="success" onClick={continueWithApproved} disabled={advancing}>
                {advancing
                  ? <><Spinner color="#fff" />&nbsp;Cleaning…</>
                  : `Continue with ${approvedCount} approved →`}
              </Btn>
            )}
          </div>
        </div>

        {/* Stats row 1 */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 14 }}>
          <Stat label="Validated total" value={allItems.length} />
          <Stat label="Top shown" value={displayed} color={T.primary} />
          <Stat label="Per pillar target" value={TOP_N} color={T.primary} />
          <Stat label="Approved" value={approvedCount} color={T.success} />
          <Stat label="Rejected" value={rejectedCount} color={T.error} />
          <Stat label="Phase status"
            value={phase4Done ? "Scored ✓" : session?.phase3_done ? "Validated" : "Pending"}
            color={phase4Done ? T.success : T.warn} />
        </div>

        {/* Stats row 2: segments (only after scoring) */}
        {phase4Done && allItems.length > 0 && (
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 10 }}>
            <Stat label="Money KWs"   value={segments.money.length}   color={SEGMENTS.money.color} />
            <Stat label="Growth KWs"  value={segments.growth.length}  color={SEGMENTS.growth.color} />
            <Stat label="Support KWs" value={segments.support.length} color={SEGMENTS.support.color} />
            <Stat label="Quick Wins"  value={quickWins.length}        color={T.warn} />
            {avgScore != null && <Stat label="Avg Score" value={avgScore.toFixed(1)} color={T.primary} />}
          </div>
        )}

        {!session?.phase2_done && (
          <div style={{ marginTop: 12, padding: 10, background: T.warnBg, color: T.warn, borderRadius: 7, fontSize: 12 }}>
            ⚠ Phase 2 (generate) must complete first.
          </div>
        )}
        {stream3Err && (
          <div style={{ marginTop: 10, padding: 10, background: T.errorBg, color: T.error, borderRadius: 7, fontSize: 12 }}>
            {stream3Err}
          </div>
        )}
        {(phase3Mut.error || phase4Mut.error) && (
          <div style={{ marginTop: 10, padding: 10, background: T.errorBg, color: T.error, borderRadius: 7, fontSize: 12 }}>
            {String(phase3Mut.error?.message || phase4Mut.error?.message || "Error")}
          </div>
        )}
      </Card>

      {/* ── Phase 3 streaming progress ──────────────────────────────────── */}
      {streaming3 && (
        <Card>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#8b5cf6", marginBottom: 10 }}>Validation Stream</div>
          <Phase3StreamPanel
            passInfo={passInfo}
            activePass={activePass}
            pillarProgress={pillarProgress}
            activePillar={activePillar3}
          />
          <div style={{ marginTop: 8 }}>
            <Btn
              variant="danger"
              onClick={() => { stop3Ref.current?.(); setStreaming3(false) }}
              style={{ fontSize: 12 }}
            >Stop</Btn>
            <span style={{ fontSize: 11, color: T.textSoft, marginLeft: 10 }}>
              After stream completes, click "Run Scoring →" to finish Phase 4.
            </span>
          </div>
        </Card>
      )}

      {/* ── Analytics panel (score dist + segments + quick wins + recs) ──── */}
      {phase4Done && allItems.length > 0 && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 14 }}>Keyword Analysis</div>
          <ScoreDistChart items={allItems} />
          <RecommendationsCard recs={recs} />
          <QuickWinsCard keywords={quickWins} />
          <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 8 }}>Keyword Segments</div>
          {Object.keys(segmentOverrides).length > 0 && (
            <div style={{ marginBottom: 8, padding: "5px 10px", background: T.successBg, borderRadius: 6, fontSize: 12, color: T.success }}>
              {Object.keys(segmentOverrides).length} keyword(s) manually reassigned
              <button
                onClick={() => setSegmentOverrides({})}
                style={{ marginLeft: 10, fontSize: 11, color: T.error, background: "none", border: "none", cursor: "pointer" }}
              >Reset</button>
            </div>
          )}
          {["money", "growth", "support"].map(seg => (
            <SegmentPanel
              key={seg}
              segKey={seg}
              keywords={segments[seg]}
              onDragStart={(kw, fromSeg) => { dragRef.current = { keyword: kw, fromSegment: fromSeg } }}
              onDragOver={segKey => { if (dragRef.current) setDragTarget(segKey) }}
              onDrop={toSeg => {
                if (dragRef.current && dragRef.current.fromSegment !== toSeg) {
                  const kwKey = dragRef.current.keyword.id || dragRef.current.keyword.keyword
                  setSegmentOverrides(prev => ({ ...prev, [kwKey]: toSeg }))
                }
                dragRef.current = null; setDragTarget(null)
              }}
              onDragEnd={() => { dragRef.current = null; setDragTarget(null) }}
              isDragTarget={dragTarget === seg}
            />
          ))}
        </Card>
      )}

      {/* ── Pillar blocks ────────────────────────────────────────────────── */}
      {validatedQ.isLoading || pillarDataLoading ? (
        <Card><div style={{ textAlign: "center", padding: 20 }}><Spinner /></div></Card>
      ) : allItems.length === 0 && !session?.phase3_done ? (
        <Empty
          icon="🔎"
          title="No validated keywords yet"
          hint='Click "Batch Validate &amp; Score" or "Stream Validate" to filter and rank the keyword universe.'
        />
      ) : (
        pillars.map(pillar => (
          <PillarBlock
            key={pillar}
            pillar={pillar}
            top={byPillar[pillar] || []}
            picks={picks}
            setPick={setPick}
            clearPick={clearPick}
            hasScores={hasScores}
            onDelete={id => {
              if (confirm("Permanently delete this keyword?")) {
                deleteMut.mutate(id, {
                  onSuccess: () => {
                    qc.invalidateQueries({ queryKey: ["kw3", projectId, "validated", sessionId] })
                    loadPillarData()
                  },
                })
              }
            }}
            onApproveAll={() => setPicks(p => {
              const n = { ...p }
              for (const it of (byPillar[pillar] || [])) n[it.id] = "approved"
              return n
            })}
            onClearAll={() => setPicks(p => {
              const n = { ...p }
              for (const it of (byPillar[pillar] || [])) delete n[it.id]
              return n
            })}
          />
        ))
      )}

      {/* ── Manual add keyword ───────────────────────────────────────────── */}
      {session?.phase3_done && (
        <Card>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: addForm.show ? 12 : 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>Add keyword manually</div>
            <Btn
              variant="ghost"
              onClick={() => setAddForm(f => ({ ...f, show: !f.show }))}
              style={{ fontSize: 12 }}
            >{addForm.show ? "Cancel" : "+ Add keyword"}</Btn>
          </div>
          {addForm.show && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div style={{ flex: 2, minWidth: 180 }}>
                <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 4 }}>Keyword</div>
                <Input
                  value={addForm.keyword}
                  onChange={e => setAddForm(f => ({ ...f, keyword: e.target.value }))}
                  placeholder="e.g. buy black pepper online"
                />
              </div>
              <div style={{ flex: 1, minWidth: 130 }}>
                <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 4 }}>Pillar</div>
                <select
                  value={addForm.pillar}
                  onChange={e => setAddForm(f => ({ ...f, pillar: e.target.value }))}
                  style={{ width: "100%", padding: "8px 10px", border: `1px solid ${T.border}`, borderRadius: 7, fontSize: 13 }}
                >
                  <option value="">— unassigned —</option>
                  {confirmedPillars.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div style={{ flex: 1, minWidth: 130 }}>
                <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 4 }}>Intent</div>
                <select
                  value={addForm.intent}
                  onChange={e => setAddForm(f => ({ ...f, intent: e.target.value }))}
                  style={{ width: "100%", padding: "8px 10px", border: `1px solid ${T.border}`, borderRadius: 7, fontSize: 13 }}
                >
                  {["informational", "commercial", "transactional", "navigational"].map(i => (
                    <option key={i} value={i}>{i}</option>
                  ))}
                </select>
              </div>
              <Btn
                onClick={() => {
                  if (!addForm.keyword.trim()) return
                  addMut.mutate({ keyword: addForm.keyword.trim(), pillar: addForm.pillar || null, intent: addForm.intent })
                }}
                disabled={!addForm.keyword.trim() || addMut.isPending}
              >
                {addMut.isPending ? <><Spinner color="#fff" />&nbsp;Adding…</> : "Add"}
              </Btn>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
