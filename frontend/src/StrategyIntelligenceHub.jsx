// StrategyIntelligenceHub.jsx — 7-Phase SEO Strategy Dashboard
// Framework: Semrush + Ahrefs Orchard Strategy + Backlinko 2026
// Phases: Goals → Research → Intent/Briefs → Scoring → Quick Wins → Links → Updates → Blueprints

import { useState, useEffect, useCallback, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { StrategyTab } from "./kw2/shared"
import SessionStrategyPage from "./kw2/SessionStrategyPage"
import Kw2PromptStudio from "./kw2/Kw2PromptStudio"
import BlueprintCard from "./components/BlueprintCard"

const API = import.meta.env.VITE_API_URL || ""
function authHeaders() {
  const t = localStorage.getItem("annaseo_token")
  return t ? { Authorization: `Bearer ${t}` } : {}
}
async function apiFetch(url, opts = {}) {
  const r = await fetch(`${API}${url}`, { headers: { "Content-Type": "application/json", ...authHeaders() }, ...opts })
  if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d?.detail || `HTTP ${r.status}`) }
  return r.json()
}

const T = {
  purple: "#007AFF", purpleLight: "rgba(0,122,255,0.1)", purpleDark: "#0040DD",
  teal: "#34C759", tealLight: "rgba(52,199,89,0.1)",
  red: "#FF3B30", amber: "#FF9500", amberLight: "rgba(255,149,0,0.1)",
  gray: "#8E8E93", grayLight: "#F2F2F7", border: "rgba(60,60,67,0.12)",
  text: "#000000", textSoft: "rgba(60,60,67,0.55)",
  cardShadow: "0 1px 2px rgba(0,0,0,0.05), 0 0 0 0.5px rgba(0,0,0,0.07)",
}

const KW3_ACTIVE_TAB = "kw3:activeTab"
const KW3_ACTIVE_SESSION = "kw3:activeSession"

function inferKw3Tab(session, fallback = "business") {
  if (!session) return fallback
  if (session.phase9_done || session.phase8_done || session.phase7_done || session.phase6_done || session.phase5_done || session._strategy) {
    return "strategy"
  }
  if (session.phase4_done || session.phase3_done || session.phase2_done || (session.validated_total || 0) > 0 || (session.universe_total || 0) > 0) {
    return "validate"
  }
  if (session.phase1_done) return "generate"
  return fallback
}

function openKw3Route(setPage, session = null, tab = null) {
  try {
    const sessionId = session?.id || session?.session_id || ""
    if (sessionId) localStorage.setItem(KW3_ACTIVE_SESSION, sessionId)
    if (tab) localStorage.setItem(KW3_ACTIVE_TAB, tab)
    else if (session) localStorage.setItem(KW3_ACTIVE_TAB, inferKw3Tab(session))
  } catch {}
  if (typeof setPage === "function") setPage("kw3")
}

function Card({ children, style = {} }) {
  return <div style={{ background: "#fff", borderRadius: 13, boxShadow: T.cardShadow, padding: 18, ...style }}>{children}</div>
}
function Btn({ children, onClick, disabled, loading, variant = "primary", small, style = {} }) {
  const base = { padding: small ? "5px 12px" : "8px 18px", borderRadius: 9, fontWeight: 600,
    cursor: (disabled || loading) ? "not-allowed" : "pointer", opacity: (disabled || loading) ? 0.6 : 1,
    fontSize: small ? 12 : 13, transition: "opacity .15s", border: "none" }
  const v = { primary: { background: T.purple, color: "#fff" }, teal: { background: T.teal, color: "#fff" },
    outline: { background: T.grayLight, color: T.text },
    danger: { background: "rgba(255,59,48,0.1)", color: T.red },
    ghost: { background: "transparent", color: T.gray } }
  return <button onClick={onClick} disabled={disabled || loading} style={{ ...base, ...v[variant], ...style }}>{loading ? "..." : children}</button>
}
function Badge({ label, color = T.purple }) {
  return <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 99, fontSize: 10, fontWeight: 600, background: color + "18", color }}>{label}</span>
}
function Stat({ label, value, color = T.purple, sub }) {
  return (
    <div style={{ textAlign: "center", padding: "8px 12px" }}>
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: 9, color: T.gray, marginTop: 1 }}>{sub}</div>}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  PHASE COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

const PHASES = [
  { id: "overview",     label: "Overview",           icon: "📊" },
  { id: "keywords",     label: "Keywords",           icon: "🔑" },
  { id: "analysis",     label: "Analysis",           icon: "🔍" },
  { id: "strategy",     label: "Strategy",           icon: "🗺️" },
  { id: "content",      label: "Content Hub",        icon: "✍️" },
  { id: "links",        label: "Link Building",      icon: "🔗" },
  { id: "blueprints",   label: "Blueprints",         icon: "🎯" },
]

// ── Keyword Pillars Phase (from Keyword Workflow) ────────────────────────────
function KeywordPillarsPhase({ projectId, setPage, kw2Session }) {
  const [openPillar, setOpenPillar] = useState(null)
  const [showBrief, setShowBrief] = useState(false)
  const [selected, setSelected] = useState(new Set()) // Set of "pillar|keyword"
  const [editModal, setEditModal] = useState(null)    // { pillar, keyword, score, intent }
  const [editValue, setEditValue] = useState("")
  const [deleteConfirm, setDeleteConfirm] = useState(null) // "pillar|keyword" key
  const [hoveredRow, setHoveredRow] = useState(null)
  const [kwView, setKwView] = useState("session") // "session" | "pipeline"
  const queryClient = useQueryClient()

  // KW2 session keyword data (when session is active)
  const sessionStrategy = kw2Session?._strategy || null
  const sessionPillars = sessionStrategy?.priority_pillars || []
  const sessionPillarStrategy = sessionStrategy?.pillar_strategy || []
  const hasSessionData = !!kw2Session && (sessionPillars.length > 0 || sessionPillarStrategy.length > 0)

  // Merge priority_pillars + pillar_strategy for rich display
  const sessionKwMap = (() => {
    const map = {}
    sessionPillarStrategy.forEach((p, i) => {
      const name = typeof p === "string" ? p : p?.pillar || p?.name || `Pillar ${i + 1}`
      map[name] = typeof p === "object" ? p : { pillar: name }
    })
    sessionPillars.forEach(p => {
      const name = typeof p === "string" ? p : p?.pillar || p?.name || ""
      if (name && !map[name]) map[name] = typeof p === "object" ? p : { pillar: name }
    })
    return map
  })()

  const sessionLabel = kw2Session?.name ||
    (Array.isArray(kw2Session?.seed_keywords) && kw2Session.seed_keywords.length
      ? kw2Session.seed_keywords.slice(0, 3).join(" · ")
      : kw2Session ? `Session ${(kw2Session.id || "").slice(-6)}` : null)

  // ── Fetch KW2 session validated keywords (session-scoped view) ──
  const { data: validatedData, isLoading: validatedLoading } = useQuery({
    queryKey: ["kw2-validated-hub", projectId, kw2Session?.id],
    queryFn: () => apiFetch(`/api/kw2/${projectId}/sessions/${kw2Session.id}/validated`),
    enabled: !!kw2Session?.id && !!projectId,
    staleTime: 30_000,
    retry: false,
  })

  // Extended kw2 business profile (has business_locations, audience, languages, cultural_context, etc.)
  const { data: kw2ProfileData } = useQuery({
    queryKey: ["kw2-profile-hub", projectId],
    queryFn: () => apiFetch(`/api/kw2/${projectId}/profile`).catch(() => null),
    enabled: !!projectId,
    staleTime: 60_000,
    retry: false,
  })
  // BI intel for goals, pricing_model, usps, audience_segments
  const { data: biIntelData } = useQuery({
    queryKey: ["kw2-bi-intel-hub", projectId, kw2Session?.id],
    queryFn: () => apiFetch(`/api/kw2/${projectId}/sessions/${kw2Session.id}/biz-intel`).catch(() => null),
    enabled: !!kw2Session?.id && !!projectId,
    staleTime: 60_000,
    retry: false,
  })
  // Group by pillar for expandable view
  const sessionValidPillarMap = (() => {
    const items = validatedData?.items || []
    const map = {}
    items.forEach(kw => {
      const p = (kw.pillar || "Uncategorized").trim()
      if (!map[p]) map[p] = []
      map[p].push(kw)
    })
    return map
  })()
  const sessionValidPillars = Object.keys(sessionValidPillarMap).sort()
  const [openSessionPillar, setOpenSessionPillar] = useState(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId,
    staleTime: 60_000,
    retry: false,
  })

  const brief = data?.brief
  const pillarMap = brief?.keywords_json || {}
  const pillars = Object.keys(pillarMap)
  const ctx = brief?.context_json || {}

  const intentColor = (intent) => {
    const m = { informational: "#3b82f6", transactional: "#10b981", navigational: "#f59e0b", commercial: "#8b5cf6" }
    return m[intent?.toLowerCase()] || "#6b7280"
  }

  const toggleSelect = (pillar, keyword) => {
    const key = `${pillar}|${keyword}`
    const newSet = new Set(selected)
    if (newSet.has(key)) {
      newSet.delete(key)
    } else {
      newSet.add(key)
    }
    setSelected(newSet)
  }

  const selectAllInPillar = (pillar) => {
    const kws = pillarMap[pillar] || []
    const newSet = new Set(selected)
    const allSelected = kws.every(k => newSet.has(`${pillar}|${k.keyword}`))
    kws.forEach(k => {
      const key = `${pillar}|${k.keyword}`
      if (allSelected) {
        newSet.delete(key)
      } else {
        newSet.add(key)
      }
    })
    setSelected(newSet)
  }

  const deleteSelected = async () => {
    if (selected.size === 0) return
    const items = Array.from(selected).map(s => {
      const [pillar, ...rest] = s.split('|')
      return { pillar, keyword: rest.join('|') }
    })
    try {
      const r = await apiFetch(`/api/ki/${projectId}/keyword-delete`, {
        method: 'POST',
        body: JSON.stringify({ items }),
      })
      if (r.success) {
        setSelected(new Set())
        setDeleteConfirm(null)
        refetch()
      }
    } catch (e) {
      console.error(e)
    }
  }

  const deleteSingle = async (pillar, keyword) => {
    try {
      const r = await apiFetch(`/api/ki/${projectId}/keyword-delete`, {
        method: 'POST',
        body: JSON.stringify({ items: [{ pillar, keyword }] }),
      })
      if (r.success) {
        setDeleteConfirm(null)
        const key = `${pillar}|${keyword}`
        const ns = new Set(selected)
        ns.delete(key)
        setSelected(ns)
        refetch()
      }
    } catch (e) {
      console.error(e)
    }
  }

  const saveEdit = async () => {
    if (!editModal || !editValue.trim()) return
    const newKeyword = editValue.trim()
    if (newKeyword === editModal.keyword) { setEditModal(null); return }
    try {
      const r = await apiFetch(`/api/ki/${projectId}/keyword-update`, {
        method: 'POST',
        body: JSON.stringify({
          pillar: editModal.pillar,
          old_keyword: editModal.keyword,
          new_keyword: newKeyword,
          intent: editModal.intent,
          score: editModal.score,
        }),
      })
      if (r.success) { setEditModal(null); refetch() }
    } catch (e) {
      console.error(e)
    }
  }

  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 60, color: T.textSoft }}>
        <div style={{ fontSize: 24, marginBottom: 12 }}>⏳</div>
        <div style={{ fontSize: 13 }}>Loading keyword pillars…</div>
      </div>
    )
  }

  if (!brief) {
    return (
      <div style={{ textAlign: "center", padding: 60 }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🔑</div>
        <div style={{ fontSize: 16, fontWeight: 700, color: T.text, marginBottom: 8 }}>
          No Keyword Pillars Yet
        </div>
        <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 20, maxWidth: 420, margin: "0 auto 20px" }}>
          Complete the Keyword Pipeline, accept keywords, then use "Send to Strategy Hub"
          from the Keyword Intelligence Dashboard to push your pillars here.
        </div>
        {setPage && (
          <button
            onClick={() => openKw3Route(setPage, kw2Session, "business")}
            style={{
              padding: "8px 20px", borderRadius: 8, border: "none",
              background: T.purple, color: "#fff", cursor: "pointer",
              fontWeight: 600, fontSize: 13,
            }}
          >
            → Go to Keywords
          </button>
        )}
      </div>
    )
  }

  return (
    <div>
      {/* ── Session scope banner ── */}
      {kw2Session && (
        <div style={{
          background: `${T.teal}08`, border: `1px solid ${T.teal}33`,
          borderRadius: 10, padding: "10px 14px", marginBottom: 16,
          display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
        }}>
          <span style={{ fontSize: 18 }}>📌</span>
          <div style={{ flex: 1 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: T.teal }}>Scoped to: </span>
            <span style={{ fontSize: 12, color: T.text, fontWeight: 500 }}>{sessionLabel}</span>
            {kw2Session.phase9_done && <span style={{ marginLeft: 8, fontSize: 10, padding: "1px 6px", borderRadius: 6, background: "#dcfce7", color: T.teal, fontWeight: 700 }}>✓ Strategy done</span>}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              onClick={() => setKwView("session")}
              style={{ padding: "4px 10px", borderRadius: 6, border: "none", cursor: "pointer", fontSize: 11, fontWeight: 600,
                background: kwView === "session" ? T.teal : T.grayLight, color: kwView === "session" ? "#fff" : T.gray }}
            >Session Keywords</button>
            <button
              onClick={() => setKwView("pipeline")}
              style={{ padding: "4px 10px", borderRadius: 6, border: "none", cursor: "pointer", fontSize: 11, fontWeight: 600,
                background: kwView === "pipeline" ? T.purple : T.grayLight, color: kwView === "pipeline" ? "#fff" : T.gray }}
            >All Pipeline Keywords</button>
          </div>
        </div>
      )}

      {/* ── Session keyword view ── */}
      {kw2Session && kwView === "session" && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>Session Keywords</h2>
            <div style={{ display: "flex", gap: 8 }}>
              <span style={{ fontSize: 12, color: T.textSoft, padding: "4px 0" }}>
                {sessionValidPillars.length > 0
                  ? `${sessionValidPillars.length} pillars · ${(validatedData?.count || 0).toLocaleString()} keywords`
                  : Object.keys(sessionKwMap).length > 0
                    ? `${Object.keys(sessionKwMap).length} pillars from Phase 9`
                    : "No keywords yet"}
              </span>
              {setPage && (
                <button onClick={() => openKw3Route(setPage, kw2Session, "validate")} style={{ padding: "5px 12px", borderRadius: 6, border: "none",
                  background: T.purple, color: "#fff", cursor: "pointer", fontWeight: 600, fontSize: 12 }}>
                  Open in Keywords V3 →
                </button>
              )}
            </div>
          </div>

          {/* Session stats bar */}
          {(validatedData?.count > 0 || Object.keys(sessionKwMap).length > 0) && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 14 }}>
              {[
                { label: "Pillars", val: sessionValidPillars.length || Object.keys(sessionKwMap).length, color: T.purple },
                { label: "Validated", val: (validatedData?.count || 0).toLocaleString(), color: T.teal },
                { label: "Universe", val: (kw2Session.universe_total || 0).toLocaleString(), color: T.amber },
                { label: "Phase 9", val: kw2Session.phase9_done ? "✓ Done" : "Pending", color: kw2Session.phase9_done ? T.teal : T.gray },
              ].map(s => (
                <Card key={s.label} style={{ padding: "8px 12px", textAlign: "center" }}>
                  <div style={{ fontSize: typeof s.val === "number" ? 20 : 13, fontWeight: 700, color: s.color }}>{s.val}</div>
                  <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{s.label}</div>
                </Card>
              ))}
            </div>
          )}

          {/* Validated keywords by pillar (expandable) */}
          {validatedLoading && (
            <div style={{ textAlign: "center", padding: 20, color: T.textSoft, fontSize: 12 }}>Loading session keywords…</div>
          )}

          {!validatedLoading && sessionValidPillars.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>
                📋 Validated Keywords by Pillar
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {sessionValidPillars.map(pillar => {
                  const kws = sessionValidPillarMap[pillar] || []
                  const isOpen = openSessionPillar === pillar
                  return (
                    <div key={pillar} style={{ border: `1px solid ${T.border}`, borderRadius: 10, overflow: "hidden", background: "#fff" }}>
                      <div
                        onClick={() => setOpenSessionPillar(isOpen ? null : pillar)}
                        style={{
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          padding: "10px 14px", cursor: "pointer",
                          background: isOpen ? `${T.purple}08` : "transparent",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <div style={{ width: 7, height: 7, borderRadius: "50%", background: T.teal, flexShrink: 0 }} />
                          <span style={{ fontWeight: 700, fontSize: 13, color: T.text }}>{pillar}</span>
                          <span style={{ fontSize: 10, fontWeight: 700, color: "#fff",
                            background: T.purple, borderRadius: 10, padding: "1px 8px" }}>
                            {kws.length} keywords
                          </span>
                        </div>
                        <span style={{ fontSize: 14, color: T.textSoft }}>{isOpen ? "▲" : "▼"}</span>
                      </div>
                      {isOpen && (
                        <div style={{ maxHeight: 360, overflowY: "auto" }}>
                          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                            <thead>
                              <tr style={{ background: "#f8f9fa", borderBottom: `1px solid ${T.border}` }}>
                                <th style={{ padding: "6px 14px", textAlign: "left", fontWeight: 600, color: T.textSoft }}>#</th>
                                <th style={{ padding: "6px 10px", textAlign: "left", fontWeight: 600, color: T.textSoft }}>Keyword</th>
                                <th style={{ padding: "6px 10px", textAlign: "center", fontWeight: 600, color: T.textSoft, width: 70 }}>Score</th>
                                <th style={{ padding: "6px 14px", textAlign: "center", fontWeight: 600, color: T.textSoft, width: 110 }}>Intent</th>
                              </tr>
                            </thead>
                            <tbody>
                              {kws.map((kw, idx) => {
                                const sc = kw.score != null ? Math.round(kw.score) : null
                                const iColor = ((i) => {
                                  const m = { informational: "#3b82f6", transactional: "#10b981", navigational: "#f59e0b", commercial: "#8b5cf6" }
                                  return m[(i || "").toLowerCase()] || "#6b7280"
                                })(kw.intent)
                                return (
                                  <tr key={kw.id || idx} style={{ borderBottom: `1px solid ${T.border}08`, background: idx % 2 ? "#fafafa" : "#fff" }}>
                                    <td style={{ padding: "5px 14px", color: T.textSoft, textAlign: "center", fontSize: 11 }}>{idx + 1}</td>
                                    <td style={{ padding: "5px 10px", fontWeight: 500 }}>{kw.keyword}</td>
                                    <td style={{ padding: "5px 10px", textAlign: "center" }}>
                                      {sc != null && sc > 0 ? (
                                        <span style={{ fontWeight: 700, color: sc >= 70 ? "#16a34a" : sc >= 50 ? "#d97706" : "#6b7280" }}>{sc}</span>
                                      ) : <span style={{ color: T.textSoft }}>—</span>}
                                    </td>
                                    <td style={{ padding: "5px 14px", textAlign: "center" }}>
                                      {kw.intent ? (
                                        <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 8,
                                          background: iColor + "20", color: iColor, fontWeight: 600 }}>
                                          {kw.intent}
                                        </span>
                                      ) : <span style={{ color: T.textSoft }}>—</span>}
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
            </div>
          )}

          {/* Phase 9 strategy pillar summary when available */}
          {!validatedLoading && Object.keys(sessionKwMap).length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>
                🗺️ Strategy Pillar Summary (Phase 9)
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 10 }}>
                {Object.entries(sessionKwMap).map(([pillarName, pillarData], i) => {
                  const monthly = pillarData?.monthly_searches
                  const rank = pillarData?.target_rank
                  const diff = pillarData?.difficulty
                  const ctype = pillarData?.content_type
                  return (
                    <Card key={pillarName + i} style={{ padding: "10px 12px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: T.text, lineHeight: 1.3, flex: 1, marginRight: 8 }}>{pillarName}</div>
                        {rank && (
                          <div style={{ fontSize: 16, fontWeight: 800, color: rank <= 3 ? T.teal : T.amber, flexShrink: 0 }}>#{rank}</div>
                        )}
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {ctype && <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 8, background: T.purpleLight, color: T.purpleDark, fontWeight: 600 }}>{ctype}</span>}
                        {monthly && <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 8, background: T.amberLight, color: T.amber, fontWeight: 600 }}>{monthly}/mo</span>}
                        {diff && <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 8,
                          background: diff === "low" ? "#dcfce7" : diff === "high" ? "#fee2e2" : "#fef9c3",
                          color: diff === "low" ? T.teal : diff === "high" ? T.red : "#a16207",
                          fontWeight: 600 }}>{diff}</span>}
                      </div>
                    </Card>
                  )
                })}
              </div>
            </div>
          )}

          {/* Empty state — no keywords in session */}
          {!validatedLoading && sessionValidPillars.length === 0 && Object.keys(sessionKwMap).length === 0 && (
            <Card style={{ padding: 28, textAlign: "center" }}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>⚠️</div>
              <div style={{ fontSize: 13, color: T.textSoft }}>
                {kw2Session.universe_total > 0
                  ? `This session has ${kw2Session.universe_total.toLocaleString()} universe keywords. Run Phase 3 to validate them.`
                  : "No keywords in this session yet. Run Phase 2 to generate the keyword universe."}
              </div>
              {setPage && (
                <button onClick={() => openKw3Route(setPage, kw2Session, kw2Session.universe_total > 0 ? "validate" : "generate")} style={{ marginTop: 12, padding: "6px 18px", borderRadius: 8, border: "none",
                  background: T.purple, color: "#fff", cursor: "pointer", fontWeight: 600, fontSize: 12 }}>
                  Continue in Keywords V3 →
                </button>
              )}
            </Card>
          )}

          {/* Content calendar from strategy */}
          {sessionStrategy?.content_calendar?.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>Content Calendar from Strategy</div>
              <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 4 }}>
                {sessionStrategy.content_calendar.slice(0, 4).map((month, i) => (
                  <div key={i} style={{ minWidth: 200, background: "#f8f9fa", borderRadius: 10, padding: 12, flexShrink: 0, border: `1px solid ${T.border}` }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>
                      {month.month} — {month.focus_pillar}
                    </div>
                    {(month.articles || []).slice(0, 3).map((a, j) => (
                      <div key={j} style={{ background: "#fff", borderRadius: 6, padding: "5px 8px", marginBottom: 3, fontSize: 11, border: `0.5px solid ${T.border}` }}>
                        <div style={{ fontWeight: 600, marginBottom: 1 }}>{a.title}</div>
                        <div style={{ color: T.textSoft, fontSize: 10 }}>{a.type} · {a.word_count || 1500} words</div>
                      </div>
                    ))}
                    {(month.articles || []).length > 3 && (
                      <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4 }}>+{month.articles.length - 3} more</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Pipeline / KI data view ── */}
      {(!kw2Session || kwView === "pipeline") && (
      <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Keyword Pillars</h2>
          <p style={{ margin: 0, fontSize: 13, color: T.textSoft }}>
            Confirmed keywords from Keyword Pipeline · Sent {brief.sent_at ? new Date(brief.sent_at).toLocaleString() : ""}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => refetch()}
            style={{ padding: "5px 12px", borderRadius: 6, border: `1px solid ${T.border}`,
              background: "transparent", cursor: "pointer", fontSize: 12, color: T.textSoft }}
          >
            ↺ Refresh
          </button>
          {setPage && (
            <button
              onClick={() => openKw3Route(setPage, kw2Session, kw2Session ? inferKw3Tab(kw2Session, "validate") : "validate")}
              style={{ padding: "5px 12px", borderRadius: 6, border: "none",
                background: T.purple, color: "#fff", cursor: "pointer", fontWeight: 600, fontSize: 12 }}
            >
              ← Back to Keywords
            </button>
          )}
        </div>
      </div>

      {/* Stats bar */}
      {(() => {
        const kw2Profile = kw2ProfileData?.profile || {}
        const biIntel = biIntelData?.profile || biIntelData || {}
        const extCtx = { ...ctx }
        // Augment ctx with kw2 profile fields (take kw2 value if ctx empty)
        if (!extCtx.usp && kw2Profile.usp) extCtx.usp = kw2Profile.usp
        if (!extCtx.usp && kw2Profile.manual_input?.usp) extCtx.usp = kw2Profile.manual_input.usp
        const bizType = extCtx.business_type || kw2Profile.business_type || "—"
        const targLocs = extCtx.target_locations?.length > 0 ? extCtx.target_locations : (kw2Profile.target_locations || kw2Profile.manual_input?.target_locations || [])
        const confidence = (kw2Profile.confidence_score || 0) * 100

        return (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16 }}>
              {[
                { label: "Pillars", val: pillars.length, color: T.purple },
                { label: "Total Keywords", val: brief.total_keywords, color: T.teal },
                { label: "Business Type", val: bizType, color: T.purpleDark },
                { label: "Markets", val: targLocs.length || "—", color: T.amber },
              ].map(s => (
                <Card key={s.label} style={{ padding: "10px 14px", textAlign: "center" }}>
                  <div style={{ fontSize: s.label === "Business Type" || s.label === "Markets" ? 13 : 22,
                    fontWeight: 800, color: s.color, lineHeight: 1.2 }}>{s.val}</div>
                  <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3, textTransform: "uppercase", letterSpacing: ".06em" }}>{s.label}</div>
                </Card>
              ))}
            </div>

            {/* Context chips — full profile context */}
            <Card style={{ marginBottom: 14, padding: "10px 14px" }}>
              <div style={{ fontSize: 10, fontWeight: 600, color: T.textSoft, marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.4 }}>
                Business Profile Context
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                {extCtx.usp && (
                  <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12,
                    background: T.purpleLight, color: T.purpleDark, fontWeight: 600 }}>
                    💡 {extCtx.usp.slice(0, 60)}{extCtx.usp.length > 60 ? "…" : ""}
                  </span>
                )}
                {targLocs.slice(0, 6).map(loc => (
                  <span key={loc} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12,
                    background: "#f0fdf4", color: T.teal, fontWeight: 500 }}>
                    📍 {loc}
                  </span>
                ))}
                {(kw2Profile.business_locations || kw2Profile.manual_input?.business_locations || []).slice(0, 3).map(loc => (
                  <span key={loc} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12,
                    background: "rgba(52,199,89,0.06)", color: "#059669", fontWeight: 500 }}>
                    🏢 {loc}
                  </span>
                ))}
                {(extCtx.products || kw2Profile.product_catalog || []).slice(0, 5).map(p => (
                  <span key={p} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12,
                    background: T.amberLight, color: T.amber, fontWeight: 500 }}>
                    📦 {p}
                  </span>
                ))}
                {(kw2Profile.audience || extCtx.target_audience?.split(",").map(s => s.trim()).filter(Boolean) || []).slice(0, 4).map(a => (
                  <span key={a} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12,
                    background: "rgba(139,92,246,0.1)", color: "#7c3aed", fontWeight: 500 }}>
                    👥 {a}
                  </span>
                ))}
                {(kw2Profile.manual_input?.languages || extCtx.languages || []).slice(0, 3).map(l => (
                  <span key={l} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12,
                    background: "rgba(14,165,233,0.1)", color: "#0284c7", fontWeight: 500 }}>
                    🌐 {l}
                  </span>
                ))}
                {(kw2Profile.negative_scope || []).slice(0, 4).map(ns => (
                  <span key={ns} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12,
                    background: "rgba(239,68,68,0.08)", color: T.red, fontWeight: 500 }}>
                    🚫 {ns}
                  </span>
                ))}
              </div>
              {/* BI Intel row */}
              {(biIntel.goals?.length > 0 || biIntel.pricing_model || biIntel.usps?.length > 0) && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 8, paddingTop: 8, borderTop: `1px solid ${T.border}` }}>
                  {(biIntel.goals || []).slice(0, 4).map(g => (
                    <span key={g} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12,
                      background: "rgba(0,122,255,0.08)", color: T.purple, fontWeight: 600 }}>
                      🎯 {g}
                    </span>
                  ))}
                  {biIntel.pricing_model && (
                    <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12,
                      background: "rgba(16,185,129,0.08)", color: T.teal, fontWeight: 500 }}>
                      💰 {biIntel.pricing_model}
                    </span>
                  )}
                  {(biIntel.usps || []).slice(0, 3).map(u => (
                    <span key={u} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12,
                      background: "rgba(127,119,221,0.1)", color: "#6d28d9", fontWeight: 500 }}>
                      ✨ {u.slice(0, 40)}{u.length > 40 ? "…" : ""}
                    </span>
                  ))}
                </div>
              )}
              {confidence > 0 && (
                <div style={{ marginTop: 8, fontSize: 10, color: confidence >= 80 ? T.teal : confidence >= 60 ? T.amber : T.red }}>
                  Profile confidence: {Math.round(confidence)}%{confidence < 60 ? " ⚠️ Consider re-running Phase 1" : ""}
                </div>
              )}
            </Card>
          </>
        )
      })()}

      {/* Pillar keyword cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
        {pillars.map(pillar => {
          const kws = pillarMap[pillar] || []
          const isOpen = openPillar === pillar
          const intentDist = kws.reduce((acc, k) => {
            acc[k.intent] = (acc[k.intent] || 0) + 1; return acc
          }, {})
          return (
            <Card key={pillar} style={{ padding: 0, overflow: "hidden" }}>
              <div
                onClick={() => setOpenPillar(isOpen ? null : pillar)}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "12px 16px", cursor: "pointer",
                  background: isOpen ? `${T.purple}10` : "transparent",
                  borderBottom: isOpen ? `1px solid ${T.purple}20` : "none",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: T.purple, flexShrink: 0 }} />
                  <span style={{ fontWeight: 700, fontSize: 14, color: T.text }}>{pillar}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#fff",
                    background: T.purple, borderRadius: 10, padding: "1px 8px" }}>
                    {kws.length} keywords
                  </span>
                  {/* Intent distribution pills */}
                  {Object.entries(intentDist).slice(0, 3).map(([intent, count]) => (
                    <span key={intent} style={{
                      fontSize: 9, padding: "1px 6px", borderRadius: 8,
                      background: intentColor(intent) + "20", color: intentColor(intent), fontWeight: 600,
                    }}>
                      {intent} ({count})
                    </span>
                  ))}
                </div>
                <span style={{ fontSize: 16, color: T.textSoft }}>{isOpen ? "▲" : "▼"}</span>
              </div>

              {isOpen && (
                <div>
                  {/* Keyword table */}
                  <div style={{ maxHeight: 520, overflowY: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                      <thead>
                        <tr style={{
                          background: "#f8f9fa", borderBottom: `2px solid ${T.border}`,
                          position: "sticky", top: 0, zIndex: 2,
                        }}>
                          <th style={{ padding: "10px 16px", width: 44, textAlign: "center" }}>
                            {/* Select-all custom checkbox */}
                            <div
                              onClick={() => selectAllInPillar(pillar)}
                              title="Select all"
                              style={{
                                width: 18, height: 18, borderRadius: 4, cursor: "pointer", margin: "0 auto",
                                border: `2px solid ${kws.length > 0 && kws.every(k => selected.has(`${pillar}|${k.keyword}`)) ? T.purple : "#c4c2c0"}`,
                                background: kws.length > 0 && kws.every(k => selected.has(`${pillar}|${k.keyword}`)) ? T.purple : "#fff",
                                display: "flex", alignItems: "center", justifyContent: "center",
                              }}
                            >
                              {kws.length > 0 && kws.every(k => selected.has(`${pillar}|${k.keyword}`)) && (
                                <span style={{ color: "#fff", fontSize: 10, fontWeight: 700, lineHeight: 1 }}>✓</span>
                              )}
                            </div>
                          </th>
                          <th style={{ padding: "10px 6px", width: 32, fontSize: 11, fontWeight: 600, color: T.textSoft, textAlign: "center" }}>#</th>
                          <th style={{ padding: "10px 12px", textAlign: "left", fontSize: 11, fontWeight: 600, color: T.textSoft, textTransform: "uppercase", letterSpacing: ".05em" }}>Keyword</th>
                          <th style={{ padding: "10px 12px", textAlign: "center", fontSize: 11, fontWeight: 600, color: T.textSoft, width: 76, textTransform: "uppercase", letterSpacing: ".05em" }}>Score</th>
                          <th style={{ padding: "10px 12px", textAlign: "center", fontSize: 11, fontWeight: 600, color: T.textSoft, width: 120, textTransform: "uppercase", letterSpacing: ".05em" }}>Intent</th>
                          <th style={{ padding: "10px 16px", textAlign: "right", fontSize: 11, fontWeight: 600, color: T.textSoft, width: 100 }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {kws.map((kw, idx) => {
                          const rowKey = `${pillar}|${kw.keyword}`
                          const isSelected = selected.has(rowKey)
                          const isConfirmDel = deleteConfirm === rowKey
                          const isHovered = hoveredRow === rowKey
                          const sc = kw.score != null ? Math.round(kw.score) : null
                          return (
                            <tr
                              key={kw.keyword + idx}
                              onMouseEnter={() => setHoveredRow(rowKey)}
                              onMouseLeave={() => setHoveredRow(null)}
                              onClick={(e) => {
                                if (e.target.closest('[data-nosel]')) return
                                toggleSelect(pillar, kw.keyword)
                              }}
                              style={{
                                borderBottom: `1px solid ${T.border}`,
                                borderLeft: `3px solid ${isSelected ? T.purple : "transparent"}`,
                                background: isSelected ? `${T.purple}0D` : isHovered ? "#f8f7ff" : idx % 2 === 0 ? "#fff" : "#fafafa",
                                cursor: "pointer",
                                transition: "background 0.1s",
                              }}
                            >
                              {/* Custom checkbox */}
                              <td style={{ padding: "12px 16px", textAlign: "center" }}>
                                <div style={{
                                  width: 18, height: 18, borderRadius: 4, margin: "0 auto",
                                  border: `2px solid ${isSelected ? T.purple : "#c4c2c0"}`,
                                  background: isSelected ? T.purple : "#fff",
                                  display: "flex", alignItems: "center", justifyContent: "center",
                                  flexShrink: 0,
                                }}>
                                  {isSelected && <span style={{ color: "#fff", fontSize: 10, fontWeight: 700, lineHeight: 1 }}>✓</span>}
                                </div>
                              </td>
                              {/* Index */}
                              <td style={{ padding: "12px 6px", color: T.textSoft, fontSize: 11, textAlign: "center" }}>{idx + 1}</td>
                              {/* Keyword */}
                              <td style={{ padding: "12px 12px", color: T.text, fontWeight: 500, fontSize: 13 }}>{kw.keyword}</td>
                              {/* Score badge */}
                              <td style={{ padding: "12px 12px", textAlign: "center" }}>
                                {sc != null && sc > 0 ? (
                                  <span style={{
                                    display: "inline-block", padding: "3px 9px", borderRadius: 10,
                                    fontSize: 12, fontWeight: 700,
                                    background: sc >= 70 ? "#dcfce7" : sc >= 50 ? "#fef3c7" : "#f3f4f6",
                                    color: sc >= 70 ? "#16a34a" : sc >= 50 ? "#d97706" : "#6b7280",
                                  }}>{sc}</span>
                                ) : <span style={{ color: "#c0bdb8", fontSize: 11 }}>—</span>}
                              </td>
                              {/* Intent badge */}
                              <td style={{ padding: "12px 12px", textAlign: "center" }}>
                                {kw.intent ? (
                                  <span style={{
                                    fontSize: 10, padding: "3px 8px", borderRadius: 8,
                                    background: intentColor(kw.intent) + "20",
                                    color: intentColor(kw.intent), fontWeight: 600,
                                  }}>{kw.intent}</span>
                                ) : <span style={{ color: "#c0bdb8" }}>—</span>}
                              </td>
                              {/* Actions */}
                              <td style={{ padding: "12px 16px", textAlign: "right" }} data-nosel="1">
                                {isConfirmDel ? (
                                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                                    <span style={{ fontSize: 11, color: T.red, fontWeight: 600 }}>Delete?</span>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); deleteSingle(pillar, kw.keyword) }}
                                      style={{ padding: "3px 10px", borderRadius: 5, border: "none", background: T.red, color: "#fff", cursor: "pointer", fontSize: 11, fontWeight: 700 }}
                                    >Yes</button>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); setDeleteConfirm(null) }}
                                      style={{ padding: "3px 10px", borderRadius: 5, border: `1px solid ${T.border}`, background: "#fff", color: T.textSoft, cursor: "pointer", fontSize: 11 }}
                                    >No</button>
                                  </span>
                                ) : (isHovered || isSelected) ? (
                                  <span style={{ display: "inline-flex", gap: 6 }}>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); setEditModal({ pillar, keyword: kw.keyword, score: kw.score, intent: kw.intent }); setEditValue(kw.keyword) }}
                                      title="Edit keyword"
                                      style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${T.purple}40`, background: T.purpleLight, color: T.purpleDark, cursor: "pointer", fontSize: 12, fontWeight: 600 }}
                                    >✎ Edit</button>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); setDeleteConfirm(rowKey) }}
                                      title="Delete keyword"
                                      style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${T.red}30`, background: "#fff0f0", color: T.red, cursor: "pointer", fontSize: 12, fontWeight: 600 }}
                                    >🗑</button>
                                  </span>
                                ) : null}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Bulk action bar — appears at bottom when items selected */}
                  {selected.size > 0 && (
                    <div style={{
                      padding: "12px 20px",
                      background: T.purpleDark,
                      display: "flex", alignItems: "center", gap: 14, justifyContent: "space-between",
                      borderTop: `2px solid ${T.purple}`,
                    }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>
                        {selected.size} keyword{selected.size !== 1 ? "s" : ""} selected
                      </span>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button
                          onClick={deleteSelected}
                          style={{ padding: "7px 18px", borderRadius: 7, border: "none", background: "#ef4444", color: "#fff", cursor: "pointer", fontWeight: 700, fontSize: 12 }}
                        >
                          🗑 Delete Selected
                        </button>
                        <button
                          onClick={() => setSelected(new Set())}
                          style={{ padding: "7px 14px", borderRadius: 7, border: "1px solid rgba(255,255,255,0.3)", background: "transparent", color: "rgba(255,255,255,0.85)", cursor: "pointer", fontSize: 12 }}
                        >
                          ✕ Deselect All
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </Card>
          )
        })}
      </div>

      {/* Blog Content Clusters */}
      {ctx.content_clusters?.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          {/* Section header */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: T.text }}>📝 Blog Content Clusters</div>
            <span style={{ fontSize: 11, color: T.textSoft, background: "#f3f4f6", padding: "2px 10px", borderRadius: 8, fontWeight: 500 }}>
              {ctx.content_clusters.length} clusters &nbsp;·&nbsp; {ctx.content_clusters.reduce((s, c) => s + c.total, 0)} keywords mapped
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {ctx.content_clusters.map((cluster, idx) => {
              const ACCENT = ["#8b5cf6","#10b981","#3b82f6","#f59e0b","#ef4444","#06b6d4","#ec4899","#14b8a6","#6366f1"]
              const color = ACCENT[idx % ACCENT.length]
              const CV_COLOR = {
                "highest commercial value": "#10b981",
                "high commercial value": "#3b82f6",
                "mid funnel": "#8b5cf6",
                "brand awareness": "#6366f1",
                "local intent": "#06b6d4",
                "seasonal opportunity": "#f59e0b",
                "consideration stage": "#ec4899",
                "long-tail opportunity": "#14b8a6",
              }
              const cvColor = CV_COLOR[cluster.commercial_value] || T.textSoft

              return (
                <Card key={cluster.id} style={{ padding: 0, borderLeft: `4px solid ${color}`, overflow: "hidden" }}>
                  {/* Cluster header */}
                  <div style={{
                    padding: "10px 16px 8px",
                    background: color + "08",
                    borderBottom: `1px solid ${color}20`,
                    display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 6,
                  }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                        <span style={{ fontSize: 11, fontWeight: 800, color, textTransform: "uppercase", letterSpacing: ".06em" }}>
                          Cluster {idx + 1}
                        </span>
                        <span style={{ fontSize: 13, fontWeight: 700, color: T.text }}>— {cluster.name}</span>
                        {cluster.commercial_value && (
                          <span style={{
                            fontSize: 10, padding: "2px 8px", borderRadius: 10,
                            background: cvColor + "18", color: cvColor, fontWeight: 600,
                          }}>
                            {cluster.commercial_value}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 12, color: T.textSoft }}>
                        📄 <span style={{ fontStyle: "italic", fontWeight: 600, color: T.text }}>Blog: &quot;{cluster.blog_title}&quot;</span>
                      </div>
                    </div>
                    <span style={{
                      fontSize: 11, fontWeight: 700, background: color + "18", color,
                      padding: "2px 10px", borderRadius: 10, whiteSpace: "nowrap",
                    }}>
                      {cluster.total} keyword{cluster.total !== 1 ? "s" : ""}
                    </span>
                  </div>

                  {/* Keywords table */}
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: "#f8f9fa" }}>
                          <th style={{ padding: "5px 14px", textAlign: "left", fontWeight: 600, color: T.textSoft, width: 28 }}>#</th>
                          <th style={{ padding: "5px 10px", textAlign: "left", fontWeight: 600, color: T.textSoft }}>Keyword</th>
                          <th style={{ padding: "5px 10px", textAlign: "center", fontWeight: 600, color: T.textSoft, width: 64 }}>Score</th>
                          <th style={{ padding: "5px 14px", textAlign: "center", fontWeight: 600, color: T.textSoft, width: 100 }}>Intent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cluster.keywords.map((kw, ki) => {
                          const kwObj = typeof kw === "object" ? kw : { keyword: kw, score: 0, intent: "" }
                          const intentColor = (i) => {
                            const m = { informational: "#3b82f6", transactional: "#10b981", navigational: "#f59e0b", commercial: "#8b5cf6" }
                            return m[(i || "").split("|")[0].toLowerCase()] || "#6b7280"
                          }
                          const sc = kwObj.score ? Math.round(kwObj.score) : null
                          return (
                            <tr key={kwObj.keyword + ki} style={{ borderTop: `1px solid ${T.border}`, background: ki % 2 === 0 ? "transparent" : "#fafafa" }}>
                              <td style={{ padding: "5px 14px", color: T.textSoft, textAlign: "center" }}>{ki + 1}</td>
                              <td style={{ padding: "5px 10px", color: T.text, fontWeight: 500 }}>{kwObj.keyword}</td>
                              <td style={{ padding: "5px 10px", textAlign: "center" }}>
                                {sc ? (
                                  <span style={{
                                    fontWeight: 700, fontSize: 12,
                                    color: sc >= 70 ? "#10b981" : sc >= 50 ? "#f59e0b" : T.textSoft,
                                  }}>{sc}</span>
                                ) : <span style={{ color: T.textSoft }}>—</span>}
                              </td>
                              <td style={{ padding: "5px 14px", textAlign: "center" }}>
                                {kwObj.intent ? (
                                  <span style={{
                                    fontSize: 10, padding: "2px 7px", borderRadius: 8,
                                    background: intentColor(kwObj.intent) + "20",
                                    color: intentColor(kwObj.intent), fontWeight: 600,
                                  }}>{kwObj.intent}</span>
                                ) : <span style={{ color: T.textSoft }}>—</span>}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )
            })}
          </div>
        </div>
      )}

      {/* AI Pillar Strategy Brief */}
      {brief.brief_text && (
        <Card style={{ border: `1px solid ${T.purple}30` }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: T.purpleDark }}>
              🤖 AI Pillar Strategy Brief
            </div>
            <button
              onClick={() => setShowBrief(!showBrief)}
              style={{ padding: "4px 12px", borderRadius: 6, border: `1px solid ${T.purple}40`,
                background: showBrief ? T.purple : "transparent",
                color: showBrief ? "#fff" : T.purpleDark, cursor: "pointer", fontSize: 12, fontWeight: 600 }}
            >
              {showBrief ? "Hide Brief" : "Show Brief"}
            </button>
          </div>

          {!showBrief && (
            <div style={{ fontSize: 12, color: T.textSoft, fontStyle: "italic" }}>
              {brief.brief_text.slice(0, 200)}…
            </div>
          )}

          {showBrief && (
            <div style={{
              fontSize: 13, lineHeight: 1.7, color: T.text,
              whiteSpace: "pre-wrap", maxHeight: 600, overflowY: "auto",
              padding: "12px 16px", background: "#fafbfc", borderRadius: 8,
              border: `1px solid ${T.border}`,
            }}>
              {brief.brief_text}
            </div>
          )}
        </Card>
      )}
      </div>
      )}

      {/* Edit keyword modal — always render outside conditionals */}
      {editModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 1000,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div style={{
            background: "#fff", borderRadius: 16, padding: 28, width: 400, maxWidth: "90vw",
            boxShadow: "0 12px 40px rgba(0,0,0,0.25)",
          }}>
            <div style={{ fontWeight: 700, fontSize: 17, color: T.text, marginBottom: 4 }}>Edit Keyword</div>
            <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 20 }}>
              Pillar: <strong style={{ color: T.purpleDark }}>{editModal.pillar}</strong>
            </div>
            <label style={{ fontSize: 12, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 6, textTransform: "uppercase", letterSpacing: ".04em" }}>
              Keyword Text
            </label>
            <input
              type="text"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") saveEdit(); if (e.key === "Escape") setEditModal(null) }}
              autoFocus
              style={{
                width: "100%", padding: "11px 14px", borderRadius: 8,
                border: `2px solid ${T.purple}50`, fontSize: 14, fontFamily: "inherit",
                boxSizing: "border-box", outline: "none",
              }}
            />
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 6, marginBottom: 20 }}>
              Original: &quot;{editModal.keyword}&quot;
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={saveEdit}
                style={{ flex: 1, padding: "10px 0", borderRadius: 8, border: "none", background: T.purple, color: "#fff", cursor: "pointer", fontWeight: 700, fontSize: 13 }}
              >Save Changes</button>
              <button
                onClick={() => setEditModal(null)}
                style={{ padding: "10px 22px", borderRadius: 8, border: `1px solid ${T.border}`, background: "#fff", color: T.textSoft, cursor: "pointer", fontSize: 13 }}
              >Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  ANALYSIS PHASE — Merged Research + Scoring + Quick Wins (3 tabs)
// ═══════════════════════════════════════════════════════════════════════════════

function AnalysisPhase({ projectId, strategy, kw2Session }) {
  const [tab, setTab] = useState("research")

  // Old KI pipeline brief (fallback for when no KW2 session is active)
  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId && !kw2Session, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief
  const kwCtx = kwBrief?.context_json || {}

  // KW2 session validated keywords — used when a session is active
  const { data: sessionValidatedData } = useQuery({
    queryKey: ["analysis-session-kw", projectId, kw2Session?.id],
    queryFn: () => apiFetch(`/api/kw2/${projectId}/sessions/${kw2Session.id}/validated`),
    enabled: !!kw2Session?.id,
    staleTime: 60_000,
    retry: false,
  })

  // Build allKws/pillars/clusters from KW2 session data or fallback to KI pipeline
  const { clusters, allKws, pillars } = (() => {
    if (kw2Session && sessionValidatedData?.items) {
      const items = sessionValidatedData.items
      // Group by pillar for pillar breakdown
      const pillarMap = {}
      items.forEach(k => {
        const p = k.pillar || "General"
        if (!pillarMap[p]) pillarMap[p] = []
        pillarMap[p].push(k)
      })
      return {
        clusters: [],  // KW2 doesn't use blog clusters in analysis tab
        allKws: items,
        pillars: Object.entries(pillarMap),
      }
    }
    const kws = Object.values(kwBrief?.keywords_json || {}).flat()
    return {
      clusters: kwCtx.content_clusters || [],
      allKws: kws,
      pillars: Object.entries(kwBrief?.keywords_json || {}),
    }
  })()

  const [showLHF, setShowLHF] = useState(false)
  const { data: lhfData } = useQuery({
    queryKey: ["si-lhf", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/low-hanging-fruit`),
    enabled: !!projectId && showLHF, retry: false,
  })

  const scoredKws = allKws.filter(k => (k.score || 0) > 0).sort((a, b) => (b.score || 0) - (a.score || 0))
  const highScore = scoredKws.filter(k => k.score >= 70)
  const medScore = scoredKws.filter(k => k.score >= 50 && k.score < 70)
  const lowScore = scoredKws.filter(k => k.score < 50 && k.score > 0)

  const intentDist = {}
  const sourceDist = {}
  allKws.forEach(k => {
    const i = k.intent || "unknown"
    const s = k.source || "crawl"
    intentDist[i] = (intentDist[i] || 0) + 1
    sourceDist[s] = (sourceDist[s] || 0) + 1
  })

  const tabs = [
    { id: "research", label: "Research", icon: "🔍" },
    { id: "scoring", label: "Scoring", icon: "⚡" },
    { id: "quickwins", label: "Quick Wins", icon: "🍎" },
  ]

  const scoreColor = s => s >= 70 ? T.teal : s >= 50 ? T.amber : T.red
  const intentColor = i => ({ transactional: T.teal, commercial: T.amber, informational: T.purple, navigational: T.gray }[i] || T.gray)

  return (
    <div>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Keyword Analysis</h2>
      <p style={{ margin: "0 0 14px", fontSize: 13, color: T.textSoft }}>
        {kw2Session
          ? `Session: "${kw2Session.name || kw2Session.id.slice(-6)}" · ${allKws.length} validated keywords · ${pillars.length} pillars`
          : `Research insights, scoring, and quick-win opportunities from your ${allKws.length} keywords.`
        }
      </p>

      {/* Session strategy highlights */}
      {kw2Session?._strategy && (
        <div style={{ marginBottom: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {/* Quick wins from session */}
          {(kw2Session._strategy.quick_wins || []).length > 0 && (
            <Card style={{ border: `1px solid ${T.teal}33` }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 8 }}>
                🍎 Quick Wins · {kw2Session.name || "Active Session"}
              </div>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {(kw2Session._strategy.quick_wins || []).slice(0, 5).map((w, i) => (
                  <li key={i} style={{ fontSize: 12, marginBottom: 5, lineHeight: 1.4 }}>
                    {typeof w === "string" ? w : w?.keyword || w?.title || JSON.stringify(w)}
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {/* Competitor gaps from session */}
          {(kw2Session._strategy.competitive_gaps || kw2Session._strategy.competitor_gaps || []).length > 0 && (
            <Card style={{ border: `1px solid ${T.amber}33` }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.amber, marginBottom: 8 }}>
                ⚡ Competitor Gaps · {kw2Session.name || "Active Session"}
              </div>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {(kw2Session._strategy.competitive_gaps || kw2Session._strategy.competitor_gaps || []).slice(0, 5).map((g, i) => (
                  <li key={i} style={{ fontSize: 12, marginBottom: 5, lineHeight: 1.4 }}>
                    {typeof g === "string" ? g : g?.gap || g?.topic || g?.title || JSON.stringify(g)}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}

      {/* Tab bar */}
      <div style={{ display: "flex", gap: 4, marginBottom: 16, borderBottom: `1px solid ${T.border}`, paddingBottom: 2 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: "6px 14px", border: "none", cursor: "pointer", fontSize: 12, fontWeight: tab === t.id ? 700 : 400,
            background: tab === t.id ? T.purpleLight : "transparent", color: tab === t.id ? T.purpleDark : T.textSoft,
            borderRadius: "6px 6px 0 0", borderBottom: tab === t.id ? `2px solid ${T.purple}` : "2px solid transparent",
          }}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ── RESEARCH TAB ── */}
      {tab === "research" && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8, marginBottom: 16 }}>
            {[
              { label: "Total Keywords", val: allKws.length, color: T.purpleDark },
              { label: "Pillars", val: pillars.length, color: T.teal },
              { label: kw2Session ? "Universe" : "Blog Clusters", val: kw2Session ? (kw2Session.universe_total || 0).toLocaleString() : clusters.length, color: T.amber },
              { label: kw2Session ? "Validated" : "AI Suggested", val: kw2Session ? (kw2Session.validated_total || 0).toLocaleString() : (kwCtx.ai_suggested_count || 0), color: T.purple },
              { label: kw2Session ? "Mode" : "Brand", val: kw2Session ? (kw2Session.mode || "expand").toUpperCase() : (kwCtx.brand_name || "—"), color: T.purpleDark },
            ].map((s, i) => (
              <Card key={i} style={{ textAlign: "center", padding: "8px 6px" }}>
                <div style={{ fontSize: typeof s.val === "number" ? 18 : 12, fontWeight: 700, color: s.color }}>{s.val}</div>
                <div style={{ fontSize: 9, color: T.textSoft, marginTop: 2 }}>{s.label}</div>
              </Card>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {/* Intent Distribution */}
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>Intent Distribution</div>
              {Object.entries(intentDist).sort((a, b) => b[1] - a[1]).map(([intent, count]) => (
                <div key={intent} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <div style={{ width: 80, fontSize: 11, fontWeight: 500, textTransform: "capitalize" }}>{intent}</div>
                  <div style={{ flex: 1, background: T.grayLight, borderRadius: 4, height: 16, overflow: "hidden" }}>
                    <div style={{ width: `${Math.round(count / allKws.length * 100)}%`, height: "100%",
                      background: intentColor(intent), borderRadius: 4 }} />
                  </div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, width: 30 }}>{count}</div>
                </div>
              ))}
            </Card>

            {/* Source Distribution */}
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>Source Distribution</div>
              {Object.entries(sourceDist).sort((a, b) => b[1] - a[1]).map(([source, count]) => (
                <div key={source} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <div style={{ width: 80, fontSize: 11, fontWeight: 500, textTransform: "capitalize" }}>{source.replace("_", " ")}</div>
                  <div style={{ flex: 1, background: T.grayLight, borderRadius: 4, height: 16, overflow: "hidden" }}>
                    <div style={{ width: `${Math.round(count / allKws.length * 100)}%`, height: "100%",
                      background: T.teal, borderRadius: 4 }} />
                  </div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, width: 30 }}>{count}</div>
                </div>
              ))}
            </Card>
          </div>

          {/* Pillar breakdown */}
          <Card style={{ marginTop: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>Pillar Keyword Breakdown</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
              {pillars.slice(0, 12).map(([pillar, kws]) => (
                <div key={pillar} style={{ background: T.grayLight, borderRadius: 8, padding: "8px 10px" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 4 }}>{pillar} ({kws.length})</div>
                  <div style={{ fontSize: 10, color: T.textSoft }}>{kws.slice(0, 3).map(k => k.keyword).join(" · ")}{kws.length > 3 ? " ..." : ""}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* ── SCORING TAB ── */}
      {tab === "scoring" && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 16 }}>
            {[
              { label: "All Keywords", val: allKws.length, color: T.purpleDark },
              { label: "High ≥70", val: highScore.length, color: T.teal },
              { label: "Medium 50-69", val: medScore.length, color: T.amber },
              { label: "Low <50", val: lowScore.length, color: T.red },
            ].map((s, i) => (
              <Card key={i} style={{ textAlign: "center", padding: "8px 6px" }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: s.color }}>{s.val}</div>
                <div style={{ fontSize: 9, color: T.textSoft, marginTop: 2 }}>{s.label}</div>
              </Card>
            ))}
          </div>

          <Card>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>Scored Keywords</div>
            <div style={{ maxHeight: 480, overflowY: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}`, position: "sticky", top: 0, background: "#fff", zIndex: 1 }}>
                    <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Keyword</th>
                    <th style={{ textAlign: "center", padding: "6px 8px", fontWeight: 600, width: 60 }}>Score</th>
                    <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Pillar</th>
                    <th style={{ textAlign: "center", padding: "6px 8px", fontWeight: 600 }}>Intent</th>
                    <th style={{ textAlign: "center", padding: "6px 8px", fontWeight: 600 }}>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {scoredKws.slice(0, 100).map((k, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${T.border}08`, background: i % 2 ? T.grayLight : "transparent" }}>
                      <td style={{ padding: "5px 8px", fontWeight: 500 }}>{k.keyword}</td>
                      <td style={{ padding: "5px 8px", textAlign: "center" }}>
                        <Badge label={String(Math.round(k.score))} color={scoreColor(k.score)} />
                      </td>
                      <td style={{ padding: "5px 8px", color: T.textSoft, fontSize: 11 }}>{k._pillar || "—"}</td>
                      <td style={{ padding: "5px 8px", textAlign: "center" }}>
                        <Badge label={k.intent || "—"} color={intentColor(k.intent)} />
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "center", fontSize: 11, color: T.textSoft }}>{k.source || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* ── QUICK WINS TAB ── */}
      {tab === "quickwins" && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 16 }}>
            {[
              { label: "🏆 High-Score (≥60)", val: scoredKws.filter(k => k.score >= 60).length, color: T.teal },
              { label: "📦 Value Clusters", val: clusters.filter(c => c.commercial_value?.includes("high") || c.commercial_value?.includes("highest")).length, color: T.amber },
              { label: "🏷️ Brand Keywords", val: allKws.filter(k => k.source === "brand").length, color: T.purple },
              { label: "🤖 AI Suggested", val: kwCtx.ai_suggested_count || 0, color: T.purpleDark },
            ].map((s, i) => (
              <Card key={i} style={{ textAlign: "center", padding: "8px 6px" }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: s.color }}>{s.val}</div>
                <div style={{ fontSize: 9, color: T.textSoft, marginTop: 2 }}>{s.label}</div>
              </Card>
            ))}
          </div>

          {/* Top keyword opportunities */}
          <Card style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 10 }}>Top Keyword Opportunities (Score ≥ 60)</div>
            <div style={{ maxHeight: 300, overflowY: "auto" }}>
              {scoredKws.filter(k => k.score >= 60).slice(0, 20).map((k, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 50px 80px 70px", gap: 8, alignItems: "center",
                  padding: "5px 8px", background: i % 2 ? T.grayLight : "transparent", borderRadius: 4 }}>
                  <div style={{ fontSize: 12, fontWeight: 500 }}>{k.keyword}</div>
                  <Badge label={String(Math.round(k.score))} color={scoreColor(k.score)} />
                  <Badge label={k.intent || "—"} color={intentColor(k.intent)} />
                  <div style={{ fontSize: 10, color: T.textSoft }}>{k.source || "crawl"}</div>
                </div>
              ))}
            </div>
          </Card>

          {/* High-value clusters */}
          <Card style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.amber, marginBottom: 10 }}>High-Value Content Clusters</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {clusters.filter(c => c.commercial_value?.includes("high") || c.commercial_value?.includes("highest")).map((c, i) => (
                <div key={i} style={{ background: T.amberLight, borderRadius: 8, padding: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: T.amber }}>{c.name}</div>
                  <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{c.blog_title}</div>
                  <div style={{ fontSize: 10, color: T.amber, marginTop: 4 }}>{c.total} keywords · {(c.blog_topics || []).length} topics</div>
                </div>
              ))}
            </div>
          </Card>

          {/* Low-hanging fruit collapsible */}
          <Card>
            <div style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
              onClick={() => setShowLHF(!showLHF)}>
              <span style={{ fontSize: 10 }}>{showLHF ? "▼" : "▶"}</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark }}>Low-Hanging Fruit (from GSC data)</span>
            </div>
            {showLHF && lhfData && (
              <div style={{ marginTop: 10, maxHeight: 300, overflowY: "auto" }}>
                {(lhfData.categories || []).map((cat, ci) => (
                  <div key={ci} style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 4 }}>
                      {cat.name} ({(cat.keywords || []).length})
                    </div>
                    {(cat.keywords || []).slice(0, 5).map((k, ki) => (
                      <div key={ki} style={{ fontSize: 11, padding: "3px 0", color: T.textSoft }}>
                        {k.keyword} — position #{k.position} · +{k.traffic_uplift || 0} traffic
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  STRATEGY PHASE — Goals + AI Strategy Roadmap (merged)
// ═══════════════════════════════════════════════════════════════════════════════

function StrategyPhase({ projectId, setPage, selectedSessionId, setSelectedSessionId, kw2Sessions = [] }) {
  const qc = useQueryClient()
  const [generating, setGenerating] = useState(false)
  const [logs, setLogs] = useState([])
  const [genError, setGenError] = useState("")
  const [showGoals, setShowGoals] = useState(false)
  const [goalForm, setGoalForm] = useState({ goal_type: "traffic", target_metric: 10, timeframe_months: 24, business_outcome: "", business_type: "ecommerce" })

  // Use lifted session state; fall back to local if props not provided
  const [localSessionId, setLocalSessionId] = useState(null)
  const selectedKw2SessionId = selectedSessionId !== undefined ? selectedSessionId : localSessionId
  const setSelectedKw2SessionId = setSelectedSessionId || setLocalSessionId

  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief
  const kwCtx = kwBrief?.context_json || {}
  const clusters = kwCtx.content_clusters || []
  const allKws = Object.values(kwBrief?.keywords_json || {}).flat()

  // Use sessions from parent hub (kw2Sessions prop); no duplicate query
  const kw2Loading = false
  const refetchSessions = () => {} // handled at hub level

  const { data: latestStrategy, refetch } = useQuery({
    queryKey: ["latest-strategy-hub", projectId],
    queryFn: async () => {
      const r = await fetch(`${API}/api/strategy/${projectId}/latest`, { headers: authHeaders() })
      if (!r.ok) return null
      const d = await r.json()
      return d?.meta?.has_data ? d : null
    },
    enabled: !!projectId, retry: false,
  })
  const legacyStrat = latestStrategy?.strategy || latestStrategy?.result_json?.strategy || null

  // kw2Sessions comes from the hub prop (already processed with _strategy)
  const kw2Completed = kw2Sessions.filter((s) => s.phase9_done || s._strategy)
  // selectedKw2Session searches ALL sessions so in-progress ones can also be selected
  const selectedKw2Session = kw2Sessions.find((s) => s.id === selectedKw2SessionId) || null

  const { data: selectedKw2Strategy } = useQuery({
    queryKey: ["kw2-session-strategy", projectId, selectedKw2SessionId],
    queryFn: () => apiFetch(`/api/kw2/${projectId}/sessions/${selectedKw2SessionId}/strategy`),
    enabled: !!projectId && !!selectedKw2SessionId,
    retry: false,
  })

  const strat = selectedKw2Strategy?.strategy || selectedKw2Session?._strategy || legacyStrat

  useEffect(() => {
    if (!kw2Completed.length) {
      if (selectedKw2SessionId) setSelectedKw2SessionId(null)
      return
    }
    if (!selectedKw2SessionId || !kw2Completed.some((s) => s.id === selectedKw2SessionId)) {
      setSelectedKw2SessionId(kw2Completed[0].id)
    }
  }, [kw2Completed, selectedKw2SessionId])

  const setGoals = useMutation({
    mutationFn: (body) => apiFetch(`/api/si/${projectId}/goals`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => { qc.invalidateQueries(["si-goal-progress", projectId]); setShowGoals(false) },
  })
  const { data: progress } = useQuery({
    queryKey: ["si-goal-progress", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/goals/progress`),
    enabled: !!projectId, retry: false,
  })

  const set = (k, v) => setGoalForm(f => ({ ...f, [k]: v }))
  const inStyle = { width: "100%", padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box" }

  const sessionLabel = (s) => {
    if (!s) return ""
    if (s.name) return s.name
    if (Array.isArray(s.seed_keywords) && s.seed_keywords.length) return s.seed_keywords.join(", ")
    return `Session ${(s.id || "").slice(-6)}`
  }
  const phaseDoneCount = (s) => [1,2,3,4,5,6,7,8,9].filter((i) => s?.[`phase${i}_done`]).length
  const shortDate = (v) => {
    if (!v) return "-"
    const d = new Date(v)
    return Number.isNaN(d.getTime()) ? "-" : d.toLocaleDateString()
  }
  const normTopic = (v) => {
    const raw = String(v || "").trim().replace(/[\s_\-]+/g, " ")
    if (!raw) return ""
    return raw.length > 42 ? `${raw.slice(0, 39)}...` : raw
  }
  const getSessionTopics = (s) => {
    const fromPriority = (s?._strategy?.priority_pillars || []).map((p) => {
      if (typeof p === "string") return p
      return p?.pillar || p?.name || p?.topic || ""
    })
    const fromPillarStrategy = (s?._strategy?.pillar_strategy || []).map((p) => {
      if (typeof p === "string") return p
      return p?.pillar || p?.name || p?.topic || ""
    })
    const fromCalendar = (s?._strategy?.content_calendar || []).map((c) => c?.focus_pillar || c?.pillar || "")
    const fromWeekly = (s?._strategy?.weekly_plan || []).map((w) => w?.focus_pillar || w?.pillar || "")
    const fromSession = [
      s?.pillar,
      s?.topic,
      Array.isArray(s?.seed_keywords) ? s.seed_keywords[0] : "",
    ]
    const seen = new Set()
    const out = []
    for (const t of [...fromPriority, ...fromPillarStrategy, ...fromCalendar, ...fromWeekly, ...fromSession]) {
      const label = normTopic(t)
      if (!label) continue
      const k = label.toLowerCase()
      if (seen.has(k)) continue
      seen.add(k)
      out.push(label)
      if (out.length >= 4) break
    }
    return out.length ? out : ["General"]
  }
  // Group ALL sessions (in-progress + completed) so every keyword research is visible
  const topicBySessionId = new Map(kw2Sessions.map((s) => [s.id, getSessionTopics(s)]))
  const groupedByTopicMap = kw2Sessions.reduce((acc, s) => {
    const key = topicBySessionId.get(s.id)?.[0] || "General"
    if (!acc[key]) acc[key] = []
    acc[key].push(s)
    return acc
  }, {})
  const topicGroups = Object.entries(groupedByTopicMap)
    .map(([topic, sessions]) => ({ topic, sessions }))
    .sort((a, b) => {
      // Completed-strategy groups first, then groups with selected session, then by size
      const aHasDone = a.sessions.some((s) => s.phase9_done || s._strategy) ? 1 : 0
      const bHasDone = b.sessions.some((s) => s.phase9_done || s._strategy) ? 1 : 0
      if (aHasDone !== bHasDone) return bHasDone - aHasDone
      const aHasSelected = a.sessions.some((s) => s.id === selectedKw2SessionId) ? 1 : 0
      const bHasSelected = b.sessions.some((s) => s.id === selectedKw2SessionId) ? 1 : 0
      if (aHasSelected !== bHasSelected) return bHasSelected - aHasSelected
      if (a.sessions.length !== b.sessions.length) return b.sessions.length - a.sessions.length
      return a.topic.localeCompare(b.topic)
    })

  const routeToPage = (page) => {
    if (typeof setPage === "function") setPage(page)
  }
  const openKw3Session = (s, tab = null) => {
    if (!s) return
    setSelectedKw2SessionId(s.id)
    openKw3Route(setPage, s, tab)
  }
  const openCalendar = (s) => {
    setSelectedKw2SessionId(s.id)
    routeToPage("blogs")
  }
  const openContentHub = (s) => {
    setSelectedKw2SessionId(s.id)
    routeToPage("content")
  }

  const startGeneration = async () => {
    setGenerating(true); setLogs([]); setGenError("")
    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/generate-stream`, {
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({}),
      })
      if (!res.ok) { const d = await res.json().catch(() => ({})); setGenError(d?.detail || `HTTP ${res.status}`); setGenerating(false); return }
      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ""
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split("\n"); buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const ev = JSON.parse(line.slice(6).trim())
            if (ev.type === "log") setLogs(prev => [...prev.slice(-199), { msg: ev.msg, level: ev.level }])
            else if (ev.type === "complete") { setGenerating(false); refetch() }
            else if (ev.type === "error") { setGenError(ev.msg || "Failed"); setGenerating(false) }
          } catch {}
        }
      }
      setGenerating(false); refetch()
    } catch (e) { setGenError(String(e)); setGenerating(false) }
  }

  const levelColor = l => l === "success" ? T.teal : l === "error" ? T.red : l === "warn" ? T.amber : "#0f0"
  const confColor = c => c >= 80 ? T.teal : c >= 50 ? T.amber : T.red

  const executiveSummary = strat?.executive_summary || strat?.strategy_summary?.headline || "Strategy generated."
  const contentCalendar = strat?.content_calendar || (strat?.weekly_plan || []).map((w) => ({
    month: `Week ${w.week || "-"}`,
    focus_pillar: w.focus_pillar || w.pillar || "General",
    articles: (w.articles || []).map((a) => {
      if (typeof a === "string") return { title: a, type: "article", word_count: null }
      return {
        title: a?.title || a?.keyword || "Untitled",
        type: a?.type || a?.intent || "article",
        word_count: a?.word_count || null,
      }
    }),
  }))
  const quickWins = (strat?.quick_wins || []).map((w) => {
    if (typeof w === "string") return w
    return w?.keyword || w?.title || JSON.stringify(w)
  })
  const pillarStrategy = strat?.pillar_strategy || (strat?.priority_pillars || []).map((p) => {
    if (typeof p === "string") {
      return { pillar: p, content_type: "priority", monthly_searches: "-", target_rank: null, difficulty: "medium" }
    }
    return {
      pillar: p?.pillar || p?.name || "Untitled",
      content_type: "priority",
      monthly_searches: p?.opportunity_score ?? "-",
      target_rank: null,
      difficulty: "medium",
    }
  })
  // competitive_gaps = engine field name; content_gaps / competitor_gaps = AI-generated field names
  const competitorGaps = (strat?.competitor_gaps || strat?.competitive_gaps || strat?.content_gaps || []).map((g) => {
    if (typeof g === "string") return g
    return g?.gap || g?.topic || g?.title || JSON.stringify(g)
  })
  const kpis = Array.isArray(strat?.kpis) ? strat.kpis : []
  const aeoTactics = (strat?.aeo_tactics || []).map((t) => (typeof t === "string" ? t : JSON.stringify(t)))

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>SEO Strategy & Roadmap</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSoft }}>
            Set goals, generate an AI strategy, and get a complete ranking roadmap.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn small variant="outline" onClick={() => setShowGoals(!showGoals)}>
            {showGoals ? "Hide Goals" : "Set Goals"}
          </Btn>
          <Btn small variant="primary" onClick={startGeneration} disabled={generating}>
            {generating ? "Generating..." : kw2Completed.length ? "Generate Legacy Strategy" : strat ? "Regenerate" : "Generate Strategy"}
          </Btn>
        </div>
      </div>

      {/* Goals input */}
      {showGoals && (
        <Card style={{ marginBottom: 16, border: `1px solid ${T.purple}33` }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 12 }}>Strategy Goals</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Business Outcome (2 years)</label>
              <input value={goalForm.business_outcome} onChange={e => set("business_outcome", e.target.value)}
                placeholder="e.g., #1 online Kerala spices seller with 10K organic visits/month" style={inStyle} />
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Business Type</label>
              <select value={goalForm.business_type} onChange={e => set("business_type", e.target.value)} style={inStyle}>
                {["ecommerce","saas","local","content","agency"].map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Goal Type</label>
              <select value={goalForm.goal_type} onChange={e => set("goal_type", e.target.value)} style={inStyle}>
                <option value="traffic">Organic Traffic Growth</option>
                <option value="leads">Lead Generation</option>
                <option value="revenue">Revenue from SEO</option>
                <option value="authority">Domain Authority</option>
              </select>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Target (%)</label>
                <input type="number" value={goalForm.target_metric} onChange={e => set("target_metric", Number(e.target.value))} style={inStyle} />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Months</label>
                <input type="number" value={goalForm.timeframe_months} onChange={e => set("timeframe_months", Number(e.target.value))} style={inStyle} />
              </div>
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <Btn small onClick={() => setGoals.mutate(goalForm)} loading={setGoals.isPending}>Save Goals</Btn>
          </div>
        </Card>
      )}

      {/* Context strip */}
      {kwBrief && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8, marginBottom: 16 }}>
          {[
            { label: "Keywords", val: allKws.length, color: T.purpleDark },
            { label: "Clusters", val: clusters.length, color: T.teal },
            { label: "Brand", val: kwCtx.brand_name || "—", color: kwCtx.brand_name ? T.purpleDark : T.gray },
            { label: "AI Keywords", val: kwCtx.ai_suggested_count || 0, color: T.amber },
            { label: "Goal", val: progress?.goal ? "Set" : "Not set", color: progress?.goal ? T.teal : T.gray },
          ].map((s, i) => (
            <Card key={i} style={{ textAlign: "center", padding: "8px 6px" }}>
              <div style={{ fontSize: typeof s.val === "number" ? 18 : 12, fontWeight: 700, color: s.color }}>{s.val}</div>
              <div style={{ fontSize: 9, color: T.textSoft, marginTop: 2 }}>{s.label}</div>
            </Card>
          ))}
        </div>
      )}

      {/* KW2 session grouping + per-session cards */}
      <Card style={{ marginBottom: 16, border: `1px solid ${T.teal}33` }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: T.teal }}>Keyword Research Sessions (Project Group)</div>
            <div style={{ fontSize: 11, color: T.textSoft }}>
              All keyword research for this project is grouped here. Select a session card to view its Phase 9 strategy.
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Badge label={`${kw2Sessions.length} session${kw2Sessions.length !== 1 ? "s" : ""} · ${kw2Completed.length} with strategy`} color={T.teal} />
            <Btn small variant="outline" onClick={() => refetchSessions()}>↺ Refresh</Btn>
          </div>
        </div>

        {kw2Loading ? (
          <div style={{ fontSize: 12, color: T.textSoft, padding: "6px 0" }}>Loading keyword research sessions...</div>
        ) : kw2Sessions.length === 0 ? (
          <div style={{ fontSize: 12, color: T.textSoft, padding: "6px 0" }}>
            No keyword research sessions yet.{" "}
            {setPage && <button onClick={() => openKw3Route(setPage, null, "business")} style={{ color: T.teal, background: "none", border: "none", cursor: "pointer", fontWeight: 600, fontSize: 12, padding: 0 }}>Start one in Keywords V3 →</button>}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {topicGroups.map((g) => (
              <div key={g.topic} style={{ border: `1px solid ${T.border}`, borderRadius: 10, padding: 10, background: "#fff" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark }}>Pillar / Topic · {g.topic}</div>
                  <Badge label={`${g.sessions.length} session${g.sessions.length !== 1 ? "s" : ""}`} color={T.purpleDark} />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 10 }}>
                  {g.sessions.map((s) => {
                    const selected = selectedKw2SessionId === s.id
                    const hasStrategy = s.phase9_done || !!s._strategy
                    const title = sessionLabel(s)
                    const phasesDone = phaseDoneCount(s)
                    const summary = hasStrategy
                      ? (s._strategy?.strategy_summary?.headline || s._strategy?.executive_summary || "Strategy ready")
                      : `${phasesDone}/9 phases complete — run Phase 9 to generate strategy`
                    const sessionTopics = topicBySessionId.get(s.id) || []
                    return (
                      <div
                        key={s.id}
                        onClick={() => setSelectedKw2SessionId(s.id)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            setSelectedKw2SessionId(s.id)
                          }
                        }}
                        style={{
                          textAlign: "left",
                          borderRadius: 10,
                          border: selected
                            ? `2px solid ${hasStrategy ? T.teal : T.amber}`
                            : `1px solid ${T.border}`,
                          background: selected
                            ? (hasStrategy ? `${T.teal}14` : `${T.amber}0d`)
                            : "#fff",
                          padding: "10px 12px",
                          cursor: "pointer",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>{title}</div>
                          <Badge
                            label={hasStrategy ? "Strategy Ready" : `${phasesDone}/9 phases`}
                            color={hasStrategy ? T.teal : T.amber}
                          />
                        </div>
                        <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 6 }}>
                          {(s.mode || "brand").toUpperCase()} · {shortDate(s.created_at)}
                        </div>
                        <div style={{ display: "flex", gap: 6, marginBottom: 6, flexWrap: "wrap" }}>
                          <Badge label={`${s.universe_total || 0} universe`} color={T.purple} />
                          <Badge label={`${s.validated_total || 0} validated`} color={T.amber} />
                          {hasStrategy && sessionTopics.slice(0, 2).map((topic) => (
                            <Badge key={`${s.id}-${topic}`} label={topic} color={T.purpleDark} />
                          ))}
                        </div>
                        {/* Phase progress dots for in-progress sessions */}
                        {!hasStrategy && (
                          <div style={{ display: "flex", gap: 4, marginBottom: 6, alignItems: "center" }}>
                            {[1,2,3,4,5,6,7,8,9].map((i) => (
                              <div key={i} style={{
                                width: 7, height: 7, borderRadius: "50%",
                                background: s[`phase${i}_done`] ? T.teal : T.border,
                                flexShrink: 0,
                              }} title={`Phase ${i}`} />
                            ))}
                            <span style={{ fontSize: 9, color: T.textSoft, marginLeft: 4 }}>{phasesDone}/9</span>
                          </div>
                        )}
                        <div style={{ fontSize: 11, color: T.textSoft, lineHeight: 1.4, marginBottom: 8 }}>
                          {String(summary).slice(0, 120)}{String(summary).length > 120 ? "..." : ""}
                        </div>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          <Btn
                            small
                            variant={hasStrategy ? "outline" : "primary"}
                            onClick={(e) => { e.stopPropagation(); openKw3Session(s) }}
                          >
                            {hasStrategy ? "Open in Keywords V3" : "Continue in Keywords V3 →"}
                          </Btn>
                          {hasStrategy && (
                            <>
                              <Btn small variant="outline" onClick={(e) => { e.stopPropagation(); openCalendar(s) }}>Open Calendar</Btn>
                              <Btn small variant="outline" onClick={(e) => { e.stopPropagation(); openContentHub(s) }}>Open Content Hub</Btn>
                            </>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Generation console */}
      {(generating || logs.length > 0) && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            {generating && <div style={{ width: 8, height: 8, borderRadius: "50%", background: T.purple, animation: "pulse 1.2s infinite" }} />}
            <div style={{ fontSize: 12, fontWeight: 600 }}>{generating ? "Generating strategy..." : "Generation complete"}</div>
          </div>
          <div style={{ background: "#0d0d0d", borderRadius: 8, padding: 10, height: 120,
            overflowY: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.6 }}>
            {logs.map((l, i) => <div key={i} style={{ color: levelColor(l.level) }}>→ {l.msg}</div>)}
          </div>
        </Card>
      )}
      {genError && <Card style={{ marginBottom: 16, background: "#FEF2F2", border: "1px solid #FCA5A5" }}>
        <div style={{ fontSize: 12, color: T.red }}>Error: {genError}</div>
      </Card>}

      {/* Empty state — contextual based on whether a session is selected */}
      {!strat && !generating && (
        selectedKw2Session && !selectedKw2Session.phase9_done ? (
          <Card style={{ textAlign: "center", padding: 32, marginBottom: 14 }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>🚀</div>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
              Phase 9 not yet complete for &ldquo;{sessionLabel(selectedKw2Session)}&rdquo;
            </div>
            <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 16 }}>
              Complete Phase 9 in Keywords V3 to generate the AI strategy for this session.
              The card above will automatically update when ready.
            </div>
            <Btn variant="primary" onClick={() => openKw3Session(selectedKw2Session)}>Continue in Keywords V3 →</Btn>
          </Card>
        ) : (
          <Card style={{ textAlign: "center", padding: 40 }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🗺️</div>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>No strategy generated yet</div>
            <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 16 }}>
              Complete all phases in Keywords V3 to generate an AI strategy for your keyword research sessions.
            </div>
            {setPage && <Btn variant="outline" onClick={() => openKw3Route(setPage, null, "business")}>Go to Keywords V3 →</Btn>}
          </Card>
        )
      )}

      {/* Strategy display */}
      {strat && !generating && (
        <div>
          {/* Executive summary */}
          <div style={{ display: "flex", gap: 14, marginBottom: 14 }}>
            <Card style={{ flex: 1, background: T.purpleLight, border: `1px solid ${T.purple}33` }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 6 }}>EXECUTIVE SUMMARY</div>
              {selectedKw2Session && (
                <div style={{ marginBottom: 6 }}>
                  <Badge label={`Source: KW2 · ${sessionLabel(selectedKw2Session)}`} color={T.teal} />
                </div>
              )}
              <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6 }}>{executiveSummary}</div>
            </Card>
            {strat.strategy_confidence > 0 && (
              <div style={{ width: 100, flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                background: confColor(strat.strategy_confidence) + "18", border: `1px solid ${confColor(strat.strategy_confidence)}33`,
                borderRadius: 12, padding: 14 }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: confColor(strat.strategy_confidence) }}>{strat.strategy_confidence}%</div>
                <div style={{ fontSize: 10, color: confColor(strat.strategy_confidence) }}>Confidence</div>
              </div>
            )}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
            {/* Pillar strategy */}
            {pillarStrategy.length > 0 && (
              <Card>
                <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>PILLAR STRATEGY</div>
                {pillarStrategy.slice(0, 8).map((p, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "6px 8px", background: T.grayLight, borderRadius: 8, marginBottom: 5 }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600 }}>{p.pillar}</div>
                      <div style={{ fontSize: 10, color: T.textSoft, marginTop: 1 }}>{p.content_type || "priority"} · {p.monthly_searches ?? "-"}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 14, fontWeight: 700, color: p.target_rank ? ((p.target_rank || 99) <= 3 ? T.teal : T.amber) : T.gray }}>
                        {p.target_rank ? `#${p.target_rank}` : "-"}
                      </div>
                      <div style={{ fontSize: 10, color: p.difficulty === "low" ? T.teal : p.difficulty === "high" ? T.red : T.amber }}>{p.difficulty || "medium"}</div>
                    </div>
                  </div>
                ))}
              </Card>
            )}

            {/* Quick wins + AEO */}
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {quickWins.length > 0 && (
                <Card>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 8 }}>QUICK WINS</div>
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {quickWins.map((w, i) => <li key={i} style={{ fontSize: 12, marginBottom: 4, lineHeight: 1.4 }}>{w}</li>)}
                  </ul>
                </Card>
              )}
              {aeoTactics.length > 0 && (
                <Card>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>AEO TACTICS</div>
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {aeoTactics.slice(0, 4).map((t, i) => <li key={i} style={{ fontSize: 12, marginBottom: 4 }}>🤖 {t}</li>)}
                  </ul>
                </Card>
              )}
            </div>
          </div>

          {/* Content calendar */}
          {contentCalendar.length > 0 && (
            <Card style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>
                CONTENT ROADMAP · {strat.recommended_posting_frequency || "2+/week"}
              </div>
              <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 4 }}>
                {contentCalendar.slice(0, 8).map((month, i) => (
                  <div key={i} style={{ minWidth: 200, background: T.grayLight, borderRadius: 8, padding: 10, flexShrink: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 6 }}>{month.month} — {month.focus_pillar}</div>
                    {(month.articles || []).slice(0, 3).map((a, j) => (
                      <div key={j} style={{ background: "#fff", borderRadius: 6, padding: "5px 8px", marginBottom: 3,
                        fontSize: 11, border: `0.5px solid ${T.border}` }}>
                        <div style={{ fontWeight: 600 }}>{a.title}</div>
                        <div style={{ color: T.textSoft, fontSize: 10 }}>{a.type} · {a.word_count || 1500}w</div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Competitor gaps + KPIs */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {competitorGaps.length > 0 && (
              <Card>
                <div style={{ fontSize: 12, fontWeight: 700, color: T.amber, marginBottom: 8 }}>COMPETITOR GAPS</div>
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {competitorGaps.map((g, i) => <li key={i} style={{ fontSize: 12, marginBottom: 4 }}>⚡ {g}</li>)}
                </ul>
              </Card>
            )}
            {kpis.length > 0 && (
              <Card>
                <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>KPIs</div>
                {kpis.map((kpi, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12 }}>
                    <div style={{ fontWeight: 500 }}>{kpi.metric || kpi.kpi || "Metric"}</div>
                    <div style={{ color: T.teal, fontWeight: 600 }}>{kpi.target || kpi.goal || "-"}</div>
                  </div>
                ))}
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  CONTENT HUB PHASE — 15 blog topics per cluster, generate, manage lifecycle
// ═══════════════════════════════════════════════════════════════════════════════

// Step progress indicator for articles being generated via the 10-step pipeline
function PipelineProgress({ articleId }) {
  const { data, isLoading } = useQuery({
    queryKey: ["pipeline", articleId],
    queryFn: () => apiFetch(`/api/content/${articleId}/pipeline`),
    refetchInterval: (q) => q.state.data?.status === "generating" ? 4000 : false,
    enabled: !!articleId,
    retry: false,
  })

  if (isLoading || !data) return null
  const steps = data.steps || []
  if (!steps.length) return null

  const doneCount = steps.filter(s => s.status === "done").length
  const running = steps.find(s => s.status === "running")
  const pct = Math.round((doneCount / 10) * 100)

  return (
    <div style={{ marginTop: 6 }}>
      {/* Progress bar */}
      <div style={{ height: 4, borderRadius: 4, background: T.border, overflow: "hidden", marginBottom: 4 }}>
        <div style={{ height: "100%", width: `${pct}%`, background: T.teal, borderRadius: 4, transition: "width 0.6s" }} />
      </div>
      {/* Step dots */}
      <div style={{ display: "flex", gap: 3, marginBottom: 3 }}>
        {steps.map(s => (
          <div key={s.step} title={`Step ${s.step}: ${s.name}${s.summary ? " — " + s.summary : ""}`}
            style={{
              width: 18, height: 18, borderRadius: "50%", fontSize: 9, fontWeight: 700,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: s.status === "done" ? T.teal : s.status === "running" ? T.amber : s.status === "error" ? T.red : T.border,
              color: s.status === "pending" ? T.textSoft : "#fff",
              animation: s.status === "running" ? "pulse 1.4s infinite" : "none",
            }}>
            {s.status === "done" ? "✓" : s.status === "error" ? "!" : s.step}
          </div>
        ))}
      </div>
      {/* Current step name */}
      {running && (
        <div style={{ fontSize: 10, color: T.amber, fontStyle: "italic" }}>
          Step {running.step}/10: {running.name}…
        </div>
      )}
      {doneCount === 10 && (
        <div style={{ fontSize: 10, color: T.teal, fontWeight: 600 }}>All 10 steps complete — saving…</div>
      )}
    </div>
  )
}

// ── Phase8ContentQueue — shows Phase 8 scheduled items with generate buttons ──
function Phase8ContentQueue({ items, articleMap, generateMut, retryMut, statusColor, intentColor, genKeyword, setGenKeyword, sessionLabel }) {
  const [filter, setFilter] = useState("all")        // all | pending | generated
  const [search, setSearch] = useState("")
  const [pillarFilter, setPillarFilter] = useState("all")
  const [generating, setGenerating] = useState({})   // track per-item loading

  const pillars = [...new Set(items.map(i => i.pillar).filter(Boolean))]

  const filtered = items.filter(item => {
    const kw = (item.keyword || item.title || "").toLowerCase()
    const art = articleMap[kw]
    const hasSome = !!art
    if (filter === "pending" && hasSome) return false
    if (filter === "generated" && !hasSome) return false
    if (search && !kw.includes(search.toLowerCase())) return false
    if (pillarFilter !== "all" && item.pillar !== pillarFilter) return false
    return true
  })

  const pendingCount = items.filter(i => !articleMap[(i.keyword || i.title || "").toLowerCase()]).length
  const doneCount = items.length - pendingCount

  const handleGenerate = async (item) => {
    const kw = item.keyword || item.title || ""
    const title = item.title || item.keyword || ""
    setGenerating(g => ({ ...g, [kw]: true }))
    try {
      await generateMut.mutateAsync({ keyword: kw, title })
    } finally {
      setGenerating(g => ({ ...g, [kw]: false }))
    }
  }

  return (
    <div style={{ marginBottom: 24 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark }}>
            ✍️ Phase 8 Content Queue · {sessionLabel}
          </div>
          <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
            {items.length} scheduled articles · {doneCount} generated · {pendingCount} pending
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {["all", "pending", "generated"].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: "4px 10px", borderRadius: 6, border: "none", fontSize: 11, fontWeight: filter === f ? 700 : 500,
              background: filter === f ? T.purple : T.grayLight,
              color: filter === f ? "#fff" : T.textSoft, cursor: "pointer",
            }}>{f.charAt(0).toUpperCase() + f.slice(1)}</button>
          ))}
        </div>
      </div>

      {/* Filters row */}
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search titles…"
          style={{ flex: 1, padding: "6px 10px", borderRadius: 7, border: `1px solid ${T.border}`, fontSize: 12 }}
        />
        {pillars.length > 0 && (
          <select value={pillarFilter} onChange={e => setPillarFilter(e.target.value)}
            style={{ padding: "6px 10px", borderRadius: 7, border: `1px solid ${T.border}`, fontSize: 12, cursor: "pointer" }}>
            <option value="all">All Pillars</option>
            {pillars.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        )}
      </div>

      {/* Progress bar */}
      <div style={{ height: 4, background: T.grayLight, borderRadius: 2, overflow: "hidden", marginBottom: 12 }}>
        <div style={{ height: "100%", width: `${Math.round((doneCount / items.length) * 100)}%`,
          background: T.teal, borderRadius: 2, transition: "width .3s" }} />
      </div>

      {/* Item grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 8 }}>
        {filtered.slice(0, 60).map((item, i) => {
          const kw = item.keyword || item.title || ""
          const art = articleMap[kw.toLowerCase()]
          const isGen = generating[kw] || (generateMut.isPending && !generating[kw] && false)
          return (
            <div key={i} style={{
              padding: "10px 12px", borderRadius: 9,
              background: art ? (art.status === "published" ? "#f0fdf4" : art.status === "failed" ? "#fff5f5" : "#fefefe") : "#fff",
              border: `1px solid ${art ? (art.status === "published" ? T.teal + "44" : art.status === "failed" ? T.red + "44" : T.border) : T.border}`,
              boxShadow: T.cardShadow,
              display: "flex", flexDirection: "column", gap: 6,
            }}>
              {/* Title */}
              <div style={{ fontSize: 12, fontWeight: 600, color: T.text, lineHeight: 1.4 }}>
                {item.title || item.keyword}
              </div>

              {/* Meta */}
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {item.pillar && <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 4,
                  background: T.purpleLight, color: T.purpleDark, fontWeight: 600 }}>{item.pillar}</span>}
                {item.article_type && <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 4,
                  background: T.amberLight, color: T.amber, fontWeight: 600 }}>{item.article_type}</span>}
                {item.scheduled_date && <span style={{ fontSize: 10, color: T.textSoft }}>{item.scheduled_date}</span>}
              </div>

              {/* Action */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 2 }}>
                {art ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 5, fontWeight: 700,
                      background: statusColor(art.status) + "18", color: statusColor(art.status) }}>
                      {art.status}
                    </span>
                    {art.seo_score > 0 && <span style={{ fontSize: 10, color: T.teal, fontWeight: 600 }}>SEO {Math.round(art.seo_score)}</span>}
                    {art.status === "failed" && (
                      <button onClick={() => retryMut.mutate(art.article_id)} disabled={retryMut.isPending}
                        style={{ fontSize: 10, padding: "2px 7px", borderRadius: 5, border: `1px solid ${T.border}`,
                          background: "#fff", color: T.textSoft, cursor: "pointer" }}>
                        🔄 Retry
                      </button>
                    )}
                  </div>
                ) : (
                  <div style={{ fontSize: 10, color: T.textSoft }}>{kw}</div>
                )}
                {!art && (
                  <button
                    onClick={() => handleGenerate(item)}
                    disabled={isGen || generateMut.isPending}
                    style={{
                      padding: "4px 12px", borderRadius: 6, border: "none", fontSize: 11, fontWeight: 700,
                      background: (isGen || generateMut.isPending) ? T.grayLight : T.purple,
                      color: (isGen || generateMut.isPending) ? T.textSoft : "#fff",
                      cursor: (isGen || generateMut.isPending) ? "not-allowed" : "pointer",
                      flexShrink: 0,
                    }}
                  >
                    {isGen ? "Starting…" : "Generate"}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {filtered.length > 60 && (
        <div style={{ textAlign: "center", fontSize: 12, color: T.textSoft, marginTop: 10 }}>
          Showing 60 of {filtered.length} items. Use search / filter to narrow down.
        </div>
      )}
      {filtered.length === 0 && (
        <div style={{ textAlign: "center", padding: 24, fontSize: 13, color: T.textSoft }}>
          No items match your filters.
        </div>
      )}
    </div>
  )
}

function ContentHubPhase({ projectId, kw2Session }) {
  const qc = useQueryClient()
  const [openCluster, setOpenCluster] = useState(null)
  const [addTopicIdx, setAddTopicIdx] = useState(null) // cluster index for add-topic form
  const [addForm, setAddForm] = useState({ title: "", target_keyword: "", intent: "informational" })
  const [genKeyword, setGenKeyword] = useState("")
  const [selectedArticle, setSelectedArticle] = useState(null)
  const [aiProvider, setAiProvider] = useState("auto") // AI provider for topic generation
  const [nTopics, setNTopics] = useState(25) // number of topics to generate

  const { data: kwBriefData, refetch: refetchBrief } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief

  // KW2 session clusters — used when a session is active (expand-mode)
  const { data: sessionClustersData } = useQuery({
    queryKey: ["session-clusters-hub", projectId, kw2Session?.id],
    queryFn: () => apiFetch(`/api/kw2/${projectId}/sessions/${kw2Session.id}/expand/clusters`).catch(() => null),
    enabled: !!kw2Session?.id && kw2Session.mode === "expand",
    staleTime: 120_000, retry: false,
  })

  // Phase 8 calendar items for active session — shown as content queue with generate buttons
  const { data: phase8CalData } = useQuery({
    queryKey: ["session-phase8-cal", projectId, kw2Session?.id],
    queryFn: () => apiFetch(`/api/kw2/${projectId}/sessions/${kw2Session.id}/calendar`).catch(() => null),
    enabled: !!kw2Session?.id,
    staleTime: 120_000, retry: false,
  })
  const phase8Items = phase8CalData?.items || []

  // Clusters: session clusters > KI pipeline clusters (always loaded as fallback)
  const sessionClusters = sessionClustersData?.clusters || []
  const kiClusters = kwBrief?.context_json?.content_clusters || []
  const clusters = kw2Session
    ? (sessionClusters.length ? sessionClusters : kiClusters)
    : kiClusters
  const topicsExpanded = kw2Session
    ? (sessionClusters.length > 0 || (kwBrief?.context_json?.topics_expanded || false))
    : (kwBrief?.context_json?.topics_expanded || false)
  const totalTopics = clusters.reduce((s, c) => s + (c.blog_topics || []).length, 0)

  const { data: articles, isLoading: loadingArticles } = useQuery({
    queryKey: ["articles", projectId],
    queryFn: () => apiFetch(`/api/projects/${projectId}/content`),
    enabled: !!projectId, retry: false,
  })
  const articleList = articles || []
  const articleMap = {}
  articleList.forEach(a => { articleMap[a.keyword?.toLowerCase()] = a })

  const generateMut = useMutation({
    mutationFn: ({ keyword, title }) => apiFetch("/api/content/generate", {
      method: "POST", body: JSON.stringify({ keyword, title, project_id: projectId }),
    }),
    onSuccess: () => { qc.invalidateQueries(["articles", projectId]); setGenKeyword("") },
  })

  const approveMut = useMutation({
    mutationFn: (id) => apiFetch(`/api/content/${id}/approve`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries(["articles", projectId]),
  })

  const retryMut = useMutation({
    mutationFn: (id) => apiFetch(`/api/content/${id}/retry`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries(["articles", projectId]),
  })

  const addTopicMut = useMutation({
    mutationFn: ({ clusterIndex, body }) => apiFetch(`/api/ki/${projectId}/cluster/${clusterIndex}/add-topic`, {
      method: "POST", body: JSON.stringify(body),
    }),
    onSuccess: () => { refetchBrief(); setAddTopicIdx(null); setAddForm({ title: "", target_keyword: "", intent: "informational" }) },
  })

  const regenMut = useMutation({
    mutationFn: (clusterIndex) => apiFetch(`/api/ki/${projectId}/cluster/${clusterIndex}/regenerate-topics`, {
      method: "POST",
      body: JSON.stringify({ provider: aiProvider, n_topics: nTopics }),
    }),
    onSuccess: () => refetchBrief(),
  })

  const scoreColor = s => s >= 70 ? T.teal : s >= 40 ? T.amber : T.red
  const avgScore = (scores) => {
    if (!scores || !Object.keys(scores).length) return 0
    const vals = Object.values(scores).filter(v => typeof v === "number" && v > 0)
    return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : 0
  }
  const diffColor = d => d === "low" ? T.teal : d === "high" ? T.red : T.amber
  const intentColor = i => ({ transactional: T.teal, commercial: T.amber, informational: T.purple, navigational: T.gray }[i] || T.gray)
  const statusColor = s => ({ draft: T.gray, generating: T.amber, review: T.purple, approved: T.teal, published: T.purpleDark, failed: T.red }[s] || T.gray)
  const statusCounts = articleList.reduce((acc, a) => { acc[a.status] = (acc[a.status] || 0) + 1; return acc }, {})
  const inStyle = { width: "100%", padding: "6px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, boxSizing: "border-box" }

  // AI Provider options
  const AI_PROVIDERS = [
    { value: "auto", label: "🤖 Auto (Best Available)" },
    { value: "groq", label: "⚡ Groq (Fast)" },
    { value: "gemini", label: "✨ Gemini Free" },
    { value: "gemini_paid", label: "✨ Gemini Pro" },
    { value: "openai", label: "🧠 OpenAI GPT-4o" },
    { value: "claude", label: "🎭 Claude" },
    { value: "ollama", label: "🦙 Ollama (Local)" },
  ]

  // Session content calendar — normalize weekly_plan → content_calendar format
  const sessionCalendar = (() => {
    if (!kw2Session?._strategy) return []
    // Try content_calendar field first
    const raw = kw2Session._strategy.content_calendar
    if (Array.isArray(raw) && raw.length > 0) return raw
    // Fall back to weekly_plan and normalize to {month, focus_pillar, articles}
    return (kw2Session._strategy.weekly_plan || []).map(w => ({
      month: `Week ${w.week || "?"}`,
      focus_pillar: w.focus_pillar || w.pillar || "General",
      articles: w.articles || [],
    }))
  })()
  const sessionPillars = kw2Session?._strategy?.pillar_strategy || kw2Session?._strategy?.priority_pillars || []
  const sessionLabel = kw2Session?.name ||
    (Array.isArray(kw2Session?.seed_keywords) && kw2Session.seed_keywords.length
      ? kw2Session.seed_keywords.slice(0, 2).join(" · ") : "")

  return (
    <div>
      {/* AI Provider selector bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14, padding: "10px 14px",
        background: `${T.purple}06`, borderRadius: 10, border: `1px solid ${T.purple}22`, flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, textTransform: "uppercase" }}>AI Engine:</span>
        <select
          value={aiProvider}
          onChange={e => setAiProvider(e.target.value)}
          style={{ fontSize: 12, padding: "4px 10px", borderRadius: 7, border: `1px solid ${T.border}`,
            background: "#fff", color: T.text, fontWeight: 500, cursor: "pointer" }}
        >
          {AI_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <span style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, textTransform: "uppercase", marginLeft: 12 }}>Topics per cluster:</span>
        <select
          value={nTopics}
          onChange={e => setNTopics(Number(e.target.value))}
          style={{ fontSize: 12, padding: "4px 10px", borderRadius: 7, border: `1px solid ${T.border}`,
            background: "#fff", color: T.text, fontWeight: 500, cursor: "pointer" }}
        >
          {[10, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200].map(n => <option key={n} value={n}>{n} topics</option>)}
        </select>
        <span style={{ fontSize: 11, color: T.textSoft, marginLeft: "auto" }}>
          Used for "Generate Topics" on each cluster
        </span>
      </div>

      {/* ── PHASE 8 CONTENT QUEUE (when session active) ─────────────────────── */}
      {kw2Session && phase8Items.length > 0 && (
        <Phase8ContentQueue
          items={phase8Items}
          articleMap={articleMap}
          generateMut={generateMut}
          retryMut={retryMut}
          statusColor={statusColor}
          intentColor={intentColor}
          genKeyword={genKeyword}
          setGenKeyword={setGenKeyword}
          sessionLabel={sessionLabel}
        />
      )}

      {/* Session calendar from strategy weekly_plan (when no Phase 8 data) */}
      {kw2Session && sessionCalendar.length > 0 && phase8Items.length === 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: T.teal, marginBottom: 10 }}>
            📅 Session Content Plan · {sessionLabel}
          </div>
          <div style={{ display: "flex", gap: 12, overflowX: "auto", paddingBottom: 4 }}>
            {sessionCalendar.map((month, i) => (
              <div key={i} style={{ minWidth: 220, borderRadius: 10, border: `1px solid ${T.border}`,
                padding: 12, background: "#fff", flexShrink: 0, boxShadow: T.cardShadow }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>
                  {month.month} — {month.focus_pillar}
                </div>
                {(month.articles || []).map((a, j) => {
                  const kw = typeof a === "string" ? a : (a?.target_keyword || a?.keyword || "")
                  const title = typeof a === "string" ? a : (a?.title || a?.keyword || "")
                  const art = articleMap[kw?.toLowerCase()]
                  return (
                    <div key={j} style={{ padding: "6px 8px", borderRadius: 7,
                      background: art ? T.tealLight : "#f8f9fa", marginBottom: 4, fontSize: 11,
                      border: `0.5px solid ${art ? T.teal + "30" : T.border}` }}>
                      <div style={{ fontWeight: 600, lineHeight: 1.3, marginBottom: 4 }}>{title}</div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span style={{ color: T.textSoft, fontSize: 10 }}>
                          {typeof a === "object" && a?.type ? `${a.type} · ` : ""}
                          {typeof a === "object" && a?.word_count ? `${a.word_count}w` : ""}
                        </span>
                        {art ? (
                          <Badge label={art.status} color={statusColor(art.status)} />
                        ) : kw && (
                          <button
                            onClick={() => generateMut.mutate({ keyword: kw, title })}
                            disabled={generateMut.isPending}
                            style={{ fontSize: 10, padding: "2px 8px", borderRadius: 5, border: "none",
                              background: T.purple, color: "#fff", cursor: "pointer", fontWeight: 600 }}
                          >
                            Generate
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>Content Hub</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSoft }}>
            {clusters.length} clusters · {totalTopics} blog topics · {articleList.length} articles
          </p>
        </div>
      </div>

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 6, marginBottom: 16 }}>
        {[
          { label: "Clusters", val: clusters.length, color: T.purpleDark },
          { label: "Topics", val: totalTopics, color: T.teal },
          { label: "Articles", val: articleList.length, color: T.amber },
          ...["draft", "generating", "published"].map(s => ({
            label: s.charAt(0).toUpperCase() + s.slice(1), val: statusCounts[s] || 0, color: statusColor(s),
          })),
        ].map((s, i) => (
          <Card key={i} style={{ textAlign: "center", padding: "6px 4px" }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: s.color }}>{s.val}</div>
            <div style={{ fontSize: 8, color: T.textSoft, marginTop: 1 }}>{s.label}</div>
          </Card>
        ))}
      </div>

      {/* Quick generate */}
      <Card style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input value={genKeyword} onChange={e => setGenKeyword(e.target.value)}
            placeholder="Enter keyword to generate article..." onKeyDown={e => { if (e.key === "Enter" && genKeyword.trim()) generateMut.mutate({ keyword: genKeyword.trim(), title: "" }) }}
            style={{ flex: 1, padding: "8px 12px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13 }} />
          <Btn small onClick={() => genKeyword.trim() && generateMut.mutate({ keyword: genKeyword.trim(), title: "" })}
            loading={generateMut.isPending} disabled={!genKeyword.trim()}>Generate</Btn>
        </div>
        {generateMut.isSuccess && <div style={{ color: T.teal, fontSize: 11, marginTop: 4 }}>Article generation started!</div>}
        {generateMut.isError && <div style={{ color: T.red, fontSize: 11, marginTop: 4 }}>{generateMut.error?.message || "Failed"}</div>}
      </Card>

      {/* No topics yet */}
      {clusters.length > 0 && !topicsExpanded && totalTopics === 0 && (
        <Card style={{ textAlign: "center", padding: 24, marginBottom: 14, background: T.amberLight, border: `1px solid ${T.amber}30` }}>
          <div style={{ fontSize: 13, color: T.amber, fontWeight: 600, marginBottom: 4 }}>
            Topics not expanded yet
          </div>
          <div style={{ fontSize: 12, color: T.textSoft }}>
            Re-sync your keyword brief to generate 15 AI blog topics per cluster.
          </div>
        </Card>
      )}

      {/* Cluster accordion */}
      {clusters.map((cluster, ci) => {
        const topics = cluster.blog_topics || []
        const isOpen = openCluster === ci
        const generatedCount = topics.filter(t => articleMap[t.target_keyword?.toLowerCase()]).length

        return (
          <Card key={ci} style={{ marginBottom: 8, border: isOpen ? `1px solid ${T.purple}40` : undefined }}>
            {/* Cluster header */}
            <div style={{ display: "flex", alignItems: "center", cursor: "pointer", gap: 10 }}
              onClick={() => setOpenCluster(isOpen ? null : ci)}>
              <span style={{ fontSize: 10, color: T.textSoft }}>{isOpen ? "▼" : "▶"}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark }}>
                  {cluster.name}
                </div>
                <div style={{ fontSize: 11, color: T.textSoft, marginTop: 1 }}>
                  {topics.length} topics · {cluster.total || cluster.keywords?.length || 0} keywords · {cluster.commercial_value}
                </div>
              </div>
              <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                {generatedCount > 0 && (
                  <Badge label={`${generatedCount} generated`} color={T.teal} />
                )}
                <Badge label={`${topics.length} topics`} color={topics.length >= 10 ? T.teal : T.amber} />
              </div>
            </div>

            {/* Expanded: topics list */}
            {isOpen && (
              <div style={{ marginTop: 12 }}>
                {topics.length === 0 ? (
                  <div style={{ fontSize: 12, color: T.textSoft, padding: "10px 0" }}>
                    No topics yet. Re-sync brief or click "Regenerate" to expand.
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {topics.map((topic, ti) => {
                      const article = articleMap[topic.target_keyword?.toLowerCase()]
                      const avg = avgScore(topic.scores)
                      return (
                        <div key={ti} style={{ display: "flex", alignItems: "flex-start", gap: 10,
                          padding: "8px 10px", borderRadius: 8, background: article ? T.tealLight : T.grayLight,
                          border: `1px solid ${article ? T.teal + "30" : T.border}` }}>
                          <div style={{ width: 22, height: 22, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 10, fontWeight: 700, background: avg > 0 ? scoreColor(avg) + "20" : T.grayLight,
                            color: avg > 0 ? scoreColor(avg) : T.gray, flexShrink: 0, marginTop: 2 }}>
                            {avg > 0 ? avg : ti + 1}
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 12, fontWeight: 600, color: T.text, lineHeight: 1.3 }}>{topic.title}</div>
                            <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap", alignItems: "center" }}>
                              <Badge label={topic.target_keyword} color={T.purple} />
                              <Badge label={topic.intent} color={intentColor(topic.intent)} />
                              <Badge label={topic.difficulty} color={diffColor(topic.difficulty)} />
                              {topic.word_count && <span style={{ fontSize: 9, color: T.textSoft }}>{topic.word_count}w</span>}
                              {topic.custom && <Badge label="custom" color={T.amber} />}
                            </div>
                            {/* Scores row */}
                            {topic.scores && Object.keys(topic.scores).length > 0 && (
                              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                                {[
                                  { k: "business_value", l: "Biz" },
                                  { k: "relevance", l: "Rel" },
                                  { k: "ranking_feasibility", l: "Rank" },
                                  { k: "content_uniqueness", l: "Uniq" },
                                ].map(s => topic.scores[s.k] > 0 && (
                                  <span key={s.k} style={{ fontSize: 9, color: scoreColor(topic.scores[s.k]), fontWeight: 600 }}>
                                    {s.l}: {topic.scores[s.k]}
                                  </span>
                                ))}
                              </div>
                            )}
                            {topic.ranking_rationale && (
                              <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3, lineHeight: 1.3, fontStyle: "italic" }}>
                                {topic.ranking_rationale}
                              </div>
                            )}
                          </div>
                          <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
                            {article ? (
                              <>
                                <Badge label={article.status} color={statusColor(article.status)} />
                                {article.status === "failed" && (
                                  <Btn small variant="outline" onClick={(e) => {
                                    e.stopPropagation()
                                    retryMut.mutate(article.article_id)
                                  }} loading={retryMut.isPending}>🔄 Retry</Btn>
                                )}
                                {article.status === "generating" && (
                                  <div style={{ width: 160 }}><PipelineProgress articleId={article.article_id} /></div>
                                )}
                              </>
                            ) : (
                              <Btn small variant="outline" onClick={(e) => {
                                e.stopPropagation()
                                generateMut.mutate({ keyword: topic.target_keyword, title: topic.title })
                              }} loading={generateMut.isPending && genKeyword === topic.target_keyword}>
                                Generate
                              </Btn>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* Add topic form */}
                {addTopicIdx === ci ? (
                  <div style={{ marginTop: 10, padding: 10, background: T.purpleLight, borderRadius: 8 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>Add Custom Topic</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                      <input value={addForm.title} onChange={e => setAddForm(f => ({ ...f, title: e.target.value }))}
                        placeholder="Blog post title" style={inStyle} />
                      <input value={addForm.target_keyword} onChange={e => setAddForm(f => ({ ...f, target_keyword: e.target.value }))}
                        placeholder="Target keyword" style={inStyle} />
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <select value={addForm.intent} onChange={e => setAddForm(f => ({ ...f, intent: e.target.value }))} style={{ ...inStyle, width: "auto" }}>
                        {["informational", "commercial", "transactional", "navigational"].map(v => <option key={v} value={v}>{v}</option>)}
                      </select>
                      <Btn small onClick={() => addForm.title.trim() && addTopicMut.mutate({ clusterIndex: ci, body: addForm })}
                        loading={addTopicMut.isPending}>Add & Score</Btn>
                      <Btn small variant="outline" onClick={() => setAddTopicIdx(null)}>Cancel</Btn>
                    </div>
                  </div>
                ) : (
                  <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                    <Btn small variant="outline" onClick={() => setAddTopicIdx(ci)}>+ Add Topic</Btn>
                    <Btn small variant="outline" onClick={() => regenMut.mutate(ci)}
                      loading={regenMut.isPending}>🔄 Generate {nTopics} Topics</Btn>
                  </div>
                )}
              </div>
            )}
          </Card>
        )
      })}

      {/* Articles section */}
      {articleList.length > 0 && (
        <Card style={{ marginTop: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>Generated Articles ({articleList.length})</div>
          <div style={{ maxHeight: 350, overflowY: "auto" }}>
            {articleList.map((a, i) => (
              <div key={a.id || i} style={{ padding: "6px 8px", borderRadius: 6,
                borderBottom: i < articleList.length - 1 ? `1px solid ${T.border}08` : "none",
                cursor: "pointer", background: selectedArticle === a.article_id ? T.purpleLight : (i % 2 ? T.grayLight : "transparent") }}
                onClick={() => setSelectedArticle(selectedArticle === a.article_id ? null : a.article_id)}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{a.title || a.keyword}</div>
                  <Badge label={a.status} color={statusColor(a.status)} />
                </div>
                <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>
                  {a.keyword} · {a.word_count || 0} words
                  {a.seo_score > 0 && ` · SEO ${Math.round(a.seo_score)}`}
                  {a.eeat_score > 0 && ` · E-E-A-T ${Math.round(a.eeat_score)}`}
                </div>
                {selectedArticle === a.article_id && a.status === "draft" && (
                  <div style={{ marginTop: 6 }}>
                    <Btn small variant="teal" onClick={(e) => { e.stopPropagation(); approveMut.mutate(a.article_id) }}
                      loading={approveMut.isPending}>Approve</Btn>
                  </div>
                )}
                {a.status === "failed" && (
                  <div style={{ marginTop: 4 }}>
                    <Btn small variant="outline" onClick={(e) => { e.stopPropagation(); retryMut.mutate(a.article_id) }}
                      loading={retryMut.isPending}>🔄 Retry</Btn>
                  </div>
                )}
                {a.status === "generating" && (
                  <PipelineProgress articleId={a.article_id} />
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

// ── Kw Session Card (used by KwSessionsOverview) ─────────────────────────────

const KW_SESSION_MODE_STYLE = {
  brand:  { bg: "#eff6ff", border: "#bfdbfe", badge: "#1e40af", badgeBg: "#dbeafe", icon: "🏢", label: "Brand Analysis" },
  expand: { bg: "#f0fdf4", border: "#bbf7d0", badge: "#166534", badgeBg: "#dcfce7", icon: "🌱", label: "Expand" },
  review: { bg: "#faf5ff", border: "#e9d5ff", badge: "#5b21b6", badgeBg: "#ede9fe", icon: "🔍", label: "Review" },
  v2:     { bg: "#f0fdfa", border: "#99f6e4", badge: "#0f766e", badgeBg: "#ccfbf1", icon: "⚡", label: "Smart Workflow" },
}

const KW_PHASE_KEYS = [1, 2, 3, 4, 5, 6, 7, 8, 9]

function KwSessionCard({ session, projectId, setPage, isSelected, onSelect, onDevelop }) {
  const st = KW_SESSION_MODE_STYLE[session.mode] || KW_SESSION_MODE_STYLE.brand

  const label = session.name ||
    (Array.isArray(session.seed_keywords) && session.seed_keywords.length
      ? session.seed_keywords.slice(0, 3).join(" · ")
      : `Session ${(session.id || "").slice(-6)}`)

  const donePhasesCount = KW_PHASE_KEYS.filter(i => session[`phase${i}_done`]).length
  const totalSteps = session.mode === "expand" ? 8 : 9

  // Use pre-parsed strategy from hub (session._strategy), no fetch needed
  const strat = session._strategy || null

  // Safely extract headline — executive_summary may contain raw JSON if AI fallback fired
  const _safeHeadline = (s) => {
    if (!s) return ""
    const direct = s?.strategy_summary?.headline
    if (direct && typeof direct === "string" && direct.length < 400 && !direct.trimStart().startsWith("{")) return direct
    const exec = s?.executive_summary
    if (!exec || typeof exec !== "string") return ""
    const trimmed = exec.trimStart()
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        const parsed = JSON.parse(exec)
        const nested = parsed?.strategy_summary?.headline || parsed?.headline
        if (nested && typeof nested === "string") return nested
      } catch {}
      return "" // don't show raw JSON blobs
    }
    return exec.length > 200 ? exec.slice(0, 197) + "…" : exec
  }

  const headline  = _safeHeadline(strat)
  const quickWins = (strat?.quick_wins || []).slice(0, 3).map(w => typeof w === "string" ? w : w?.keyword || "")
  const nextArts  = (() => {
    const plan = strat?.weekly_plan || []
    const arts = []
    for (const w of plan) {
      for (const a of (w.articles || [])) {
        if (arts.length >= 2) break
        arts.push(typeof a === "string" ? a : (a?.title || a?.keyword || ""))
      }
      if (arts.length >= 2) break
    }
    return arts
  })()

  // Pillar stats — lazy loaded when session has enough phases
  const { data: pillarStats } = useQuery({
    queryKey: ["kw-pillar-stats", projectId, session.id],
    queryFn: async () => {
      try { return await apiFetch(`/api/kw2/${projectId}/sessions/${session.id}/pillar-stats`) }
      catch { return null }
    },
    enabled: !!session.phase3_done,
    staleTime: 120_000,
    retry: false,
  })
  const pillarRows = pillarStats?.pillars || (strat?.priority_pillars || []).map(p => ({
    pillar: typeof p === "string" ? p : p?.pillar || "",
    count: typeof p === "object" ? p?.count : null,
    opportunity_score: typeof p === "object" ? p?.opportunity_score : null,
  }))

  return (
    <div style={{
      borderRadius: 14,
      border: isSelected ? `2px solid ${st.badge}` : `1px solid ${st.border}`,
      background: st.bg,
      overflow: "hidden",
      boxShadow: isSelected ? `0 0 0 3px ${st.badge}22, ${T.cardShadow}` : T.cardShadow,
      transition: "border .15s, box-shadow .15s",
      display: "flex",
      flexDirection: "column",
      maxHeight: 520,
    }}>
      {/* ── Header ── */}
      <div style={{ padding: "14px 16px 12px", overflowY: "auto", flex: 1 }}>
        {/* Mode badge + strategy ready */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4,
            padding: "2px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700,
            background: st.badgeBg, color: st.badge }}>
            {st.icon} {st.label}
          </span>
          {session.phase9_done && (
            <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 20,
              background: "#dcfce7", color: T.teal, fontWeight: 700 }}>
              ✓ Strategy Ready
            </span>
          )}
        </div>

        {/* Session name */}
        <div style={{ fontSize: 15, fontWeight: 700, color: "#111827", lineHeight: 1.3,
          marginBottom: 8, wordBreak: "break-word" }}>
          {label}
        </div>

        {/* Keyword counts */}
        <div style={{ display: "flex", gap: 16, marginBottom: 8 }}>
          <div>
            <span style={{ fontSize: 17, fontWeight: 800, color: st.badge }}>{(session.universe_total || 0).toLocaleString()}</span>
            <span style={{ fontSize: 10, color: T.textSoft, marginLeft: 4 }}>universe</span>
          </div>
          <div>
            <span style={{ fontSize: 17, fontWeight: 800, color: (session.validated_total || 0) > 0 ? T.teal : "#9ca3af" }}>
              {(session.validated_total || 0).toLocaleString()}
            </span>
            <span style={{ fontSize: 10, color: T.textSoft, marginLeft: 4 }}>validated</span>
          </div>
        </div>

        {/* Phase dots */}
        <div style={{ display: "flex", gap: 3, alignItems: "center", marginBottom: 10 }}>
          {KW_PHASE_KEYS.map(i => (
            <div key={i} style={{
              width: 9, height: 9, borderRadius: "50%",
              background: session[`phase${i}_done`] ? T.teal : "#e5e7eb",
              boxShadow: session[`phase${i}_done`] ? `0 0 0 1px ${T.teal}44` : "none",
            }} title={`Phase ${i}`} />
          ))}
          <span style={{ fontSize: 10, color: T.gray, marginLeft: 4 }}>
            {donePhasesCount}/{totalSteps}
          </span>
        </div>

        {/* Pillars (if available) */}
        {pillarRows.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4, textTransform: "uppercase", letterSpacing: ".05em" }}>
              Keyword Pillars
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {pillarRows.slice(0, 4).map((p, i) => (
                <span key={i} style={{ fontSize: 10, padding: "2px 7px", borderRadius: 6,
                  background: "#fff", border: `1px solid ${st.border}`, color: st.badge, fontWeight: 600 }}>
                  {p.pillar}{p.count != null ? ` (${p.count})` : p.opportunity_score != null ? ` · ${p.opportunity_score}` : ""}
                </span>
              ))}
              {pillarRows.length > 4 && (
                <span style={{ fontSize: 10, color: T.textSoft }}>+{pillarRows.length - 4} more</span>
              )}
            </div>
          </div>
        )}

        {/* Strategy headline */}
        {headline && (
          <div style={{ padding: "7px 10px", background: `${T.purple}08`, borderRadius: 8,
            border: `1px solid ${T.purple}20`, marginBottom: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: T.purpleDark, marginBottom: 3 }}>Strategy Headline</div>
            <div style={{ fontSize: 11, color: T.text, lineHeight: 1.5 }}>{headline}</div>
          </div>
        )}

        {/* Quick wins */}
        {quickWins.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4, textTransform: "uppercase", letterSpacing: ".05em" }}>
              Quick Wins
            </div>
            {quickWins.map((w, i) => (
              <div key={i} style={{ fontSize: 11, color: T.text, padding: "2px 0", lineHeight: 1.4 }}>
                → {w}
              </div>
            ))}
          </div>
        )}

        {/* Next articles */}
        {nextArts.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4, textTransform: "uppercase", letterSpacing: ".05em" }}>
              Up Next
            </div>
            {nextArts.map((a, i) => (
              <div key={i} style={{ fontSize: 11, color: T.purpleDark, padding: "2px 0", lineHeight: 1.4, fontWeight: 500 }}>
                ✍️ {a}
              </div>
            ))}
          </div>
        )}

        {!session.phase9_done && !strat && (
          <div style={{ fontSize: 11, color: T.gray, fontStyle: "italic", marginBottom: 8 }}>
            Complete Phase 9 to generate a strategy for this session
          </div>
        )}
      </div>

      {/* ── Action buttons ── */}
      <div style={{ padding: "10px 14px", borderTop: `1px solid ${st.border}`,
        background: "#fff", display: "flex", flexDirection: "column", gap: 6, marginTop: "auto" }}>

        {/* Develop Strategy → */}
        {onDevelop && (
          <button
            onClick={() => onDevelop(session.id)}
            style={{
              width: "100%", padding: "8px 0", borderRadius: 8, border: "none",
              background: T.purple, color: "#fff",
              fontWeight: 700, fontSize: 12, cursor: "pointer", transition: "opacity .12s",
            }}
          >
            🗺️ Open Strategy →
          </button>
        )}

        <div style={{ display: "flex", gap: 6 }}>
          {/* Set Active */}
          {onSelect && (
            <button
              onClick={() => onSelect(isSelected ? null : session.id)}
              style={{
                flex: 1, padding: "6px 0", borderRadius: 7, border: "none",
                background: isSelected ? T.teal : `${T.teal}18`,
                color: isSelected ? "#fff" : T.teal,
                fontWeight: 700, fontSize: 11, cursor: "pointer", transition: "all .12s",
              }}
            >
              {isSelected ? "✓ Active" : "Set Active"}
            </button>
          )}

          {/* Go to Research */}
          {setPage && (
            <button
              onClick={() => openKw3Route(setPage, session)}
              style={{
                flex: 1, padding: "6px 0", borderRadius: 7,
                border: `1px solid ${st.border}`,
                background: "transparent", color: st.badge,
                fontWeight: 600, fontSize: 11, cursor: "pointer",
              }}
            >
              Research →
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── KwSessionsOverview ────────────────────────────────────────────────────────

function KwSessionsOverview({ projectId, setPage, kw2Sessions = [], selectedSessionId, onSelectSession, onNavigate, onDevelop }) {
  const sessions = kw2Sessions
  const qc = useQueryClient()
  const [showNewPanel, setShowNewPanel] = useState(false)
  const [newForm, setNewForm] = useState({ name: "", mode: "expand", seeds: "" })
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)

  const handleCreate = async () => {
    setCreating(true)
    setCreateError(null)
    try {
      const seeds = newForm.seeds.split(",").map(s => s.trim()).filter(Boolean)
      const created = await apiFetch(`/api/kw2/${projectId}/sessions`, {
        method: "POST",
        body: JSON.stringify({ name: newForm.name || undefined, mode: newForm.mode, seed_keywords: seeds }),
      })
      const createdSession = created?.session || created || null
      const createdSessionId = created?.session_id || created?.id || created?.session?.id || ""
      qc.invalidateQueries(["kw2-hub-sessions", projectId])
      setShowNewPanel(false)
      setNewForm({ name: "", mode: "expand", seeds: "" })
      if (createdSessionId && onSelectSession) onSelectSession(createdSessionId)
      openKw3Route(setPage, createdSessionId ? { ...createdSession, id: createdSessionId } : null, "business")
    } catch (e) {
      setCreateError(e.message || "Failed to create session")
    }
    setCreating(false)
  }
  const inStyle = { width: "100%", padding: "8px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box" }

  const totalUniverse = sessions.reduce((s, x) => s + (x.universe_total || 0), 0)
  const totalValidated = sessions.reduce((s, x) => s + (x.validated_total || 0), 0)
  const completedCount = sessions.filter(s => s.phase9_done || s._strategy).length

  if (sessions.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 60 }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🔬</div>
        <div style={{ fontSize: 16, fontWeight: 700, color: T.text, marginBottom: 8 }}>
          No keyword research sessions yet
        </div>
        <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 20, maxWidth: 380, margin: "0 auto 20px" }}>
          Run keyword research to build your strategy foundation.
          Each session generates a full SEO strategy document.
        </div>
        {setPage && (
          <button
            onClick={() => openKw3Route(setPage, null, "business")}
            style={{
              padding: "9px 22px", borderRadius: 9, border: "none",
              background: T.purple, color: "#fff", cursor: "pointer",
              fontWeight: 700, fontSize: 13,
            }}
          >
            → Start Keyword Research
          </button>
        )}
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>Keyword Research Sessions</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSoft }}>
            {sessions.length} session{sessions.length !== 1 ? "s" : ""} · select a card to scope all Strategy tabs to that session
          </p>
        </div>
        {setPage && (
          <button
            onClick={() => setShowNewPanel(true)}
            style={{
              padding: "6px 14px", borderRadius: 7, border: `1px solid ${T.border}`,
              background: "#fff", color: T.purpleDark, cursor: "pointer",
              fontWeight: 600, fontSize: 12,
            }}
          >
            + New Keyword Research
          </button>
        )}
      </div>

      {/* Combined card — aggregated across all sessions */}
      {sessions.length > 1 && (
        <div style={{
          borderRadius: 12, border: `2px dashed ${T.purple}44`,
          background: `${T.purple}05`, padding: 16, marginBottom: 18,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
            <span style={{ fontSize: 22 }}>📊</span>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.purpleDark }}>All Sessions Combined</div>
              <div style={{ fontSize: 11, color: T.textSoft }}>
                Aggregated view across all {sessions.length} keyword research sessions for this project
              </div>
            </div>
            <button
              onClick={() => onSelectSession && onSelectSession(null)}
              style={{
                marginLeft: "auto", padding: "5px 12px", borderRadius: 7, border: `1px solid ${T.purple}44`,
                background: !selectedSessionId ? T.purple : "transparent",
                color: !selectedSessionId ? "#fff" : T.purpleDark,
                fontWeight: 600, fontSize: 11, cursor: "pointer",
              }}
            >
              {!selectedSessionId ? "● Active" : "Set Active"}
            </button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
            {[
              { label: "Total Sessions", val: sessions.length, color: T.purple },
              { label: "With Strategy", val: completedCount, color: T.teal },
              { label: "Combined Universe", val: totalUniverse.toLocaleString(), color: T.purpleDark },
              { label: "Combined Validated", val: totalValidated.toLocaleString(), color: T.teal },
            ].map(s => (
              <div key={s.label} style={{ background: "#fff", borderRadius: 8, padding: "10px 12px", textAlign: "center", boxShadow: T.cardShadow }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.val}</div>
                <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4, textTransform: "uppercase", letterSpacing: ".05em" }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Individual session cards */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: 16,
      }}>
        {sessions.map(s => (
          <KwSessionCard
            key={s.id}
            session={s}
            projectId={projectId}
            setPage={setPage}
            isSelected={selectedSessionId === s.id}
            onSelect={onSelectSession}
            onDevelop={onDevelop}
          />
        ))}
      </div>

      {/* ── New session side panel ── */}
      {showNewPanel && (
        <div style={{ position: "fixed", inset: 0, zIndex: 900, display: "flex" }}>
          {/* Backdrop */}
          <div style={{ flex: 1, background: "rgba(0,0,0,0.3)" }} onClick={() => setShowNewPanel(false)} />
          {/* Panel */}
          <div style={{ width: 380, background: "#fff", boxShadow: "-4px 0 24px rgba(0,0,0,0.12)",
            display: "flex", flexDirection: "column", overflowY: "auto" }}>
            <div style={{ padding: "20px 20px 14px", borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: T.text }}>New Keyword Research</div>
              <button onClick={() => setShowNewPanel(false)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: T.textSoft }}>✕</button>
            </div>
            <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14, flex: 1 }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 5 }}>
                  Session Name (optional)
                </label>
                <input
                  value={newForm.name}
                  onChange={e => setNewForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="e.g., Cardamom Expansion Q3"
                  style={inStyle}
                />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 5 }}>
                  Research Mode
                </label>
                <select value={newForm.mode} onChange={e => setNewForm(f => ({ ...f, mode: e.target.value }))} style={inStyle}>
                  <option value="expand">🌱 Expand — grow keyword universe</option>
                  <option value="brand">🏢 Brand — brand keyword analysis</option>
                  <option value="v2">⚡ Smart v2 — full AI workflow</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 5 }}>
                  Seed Keywords
                </label>
                <textarea
                  value={newForm.seeds}
                  onChange={e => setNewForm(f => ({ ...f, seeds: e.target.value }))}
                  placeholder="cardamom, Kerala spices, buy cardamom online"
                  rows={4}
                  style={{ ...inStyle, resize: "vertical", lineHeight: 1.6 }}
                />
                <div style={{ fontSize: 11, color: T.textSoft, marginTop: 4 }}>Separate with commas</div>
              </div>

              {createError && <div style={{ fontSize: 12, color: T.red }}>{createError}</div>}

              <button
                onClick={handleCreate}
                disabled={creating}
                style={{ padding: "10px", borderRadius: 9, border: "none",
                  background: creating ? T.grayLight : T.purple,
                  color: creating ? T.textSoft : "#fff",
                  fontWeight: 700, fontSize: 13, cursor: creating ? "not-allowed" : "pointer" }}
              >
                {creating ? "Creating…" : "Create & Start Research →"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Overview ─────────────────────────────────────────────────────────────────
function OverviewPhase({ projectId, strategy, onNavigate }) {
  const summary = strategy || {}
  const goals = summary.goals || {}
  const briefs = summary.seo_briefs || []
  const lhf = summary.low_hanging_fruit || []
  const updates = summary.content_updates || []
  const phase = summary.status || "draft"

  const phaseColors = { draft: T.gray, in_progress: T.amber, finalized: T.teal, locked: T.purpleDark }

  // Keyword pillars brief summary
  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId,
    retry: false,
    staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief

  // Derive metrics from keyword pillars brief
  const totalKeywords = kwBrief?.total_keywords || 0
  const totalPillars  = kwBrief?.pillar_count  || 0
  const scoredKeywords = (() => {
    if (!kwBrief?.keywords_json) return 0
    return Object.values(kwBrief.keywords_json).flat().filter(k => (k.score || 0) > 0).length
  })()
  const contentClusters = kwBrief?.context_json?.content_clusters?.length || 0

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>Strategy Overview</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSoft }}>
            6-phase SEO strategy — Keywords → Analysis → Strategy → Content → Links
          </p>
        </div>
        <Badge label={phase.toUpperCase()} color={phaseColors[phase] || T.gray} />
      </div>

      {/* Keyword pillars quick-access banner */}
      {kwBrief ? (
        <Card style={{ marginBottom: 16, padding: "12px 16px",
          background: `linear-gradient(135deg, ${T.purple}12, ${T.teal}08)`,
          border: `1px solid ${T.purple}30`, cursor: "pointer" }}
          onClick={() => onNavigate("kw3")}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 22 }}>🔑</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark }}>
                Keyword Pillars Available — {kwBrief.total_keywords} keywords · {kwBrief.pillar_count} pillar{kwBrief.pillar_count !== 1 ? "s" : ""}
              </div>
              <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
                {kwBriefData.pillars?.slice(0, 4).join(" · ")}{(kwBriefData.pillars?.length || 0) > 4 ? " +" + (kwBriefData.pillars.length - 4) + " more" : ""}
                {contentClusters > 0 ? ` · ${contentClusters} blog clusters` : ""} · Includes AI strategy brief
              </div>
            </div>
            <span style={{ fontSize: 11, color: T.purple, fontWeight: 600 }}>View Pillars →</span>
          </div>
        </Card>
      ) : (
        <Card style={{ marginBottom: 16, padding: "10px 16px",
          background: T.grayLight, border: `1px dashed ${T.border}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 16 }}>🔑</span>
            <div style={{ fontSize: 12, color: T.textSoft }}>
              No keyword pillars yet. Complete the Keyword Pipeline and click "Send to Strategy Hub".
            </div>
          </div>
        </Card>
      )}

      {/* KPI strip */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8 }}>
          <Stat label="Keywords" value={totalKeywords || "—"} color={totalKeywords ? T.purpleDark : T.gray} />
          <Stat label="Scored" value={scoredKeywords || "—"} color={scoredKeywords ? T.purple : T.gray} />
          <Stat label="Pillars" value={totalPillars || "—"} color={totalPillars ? T.teal : T.gray} />
          <Stat label="Blog Clusters" value={contentClusters || "—"} color={contentClusters ? T.amber : T.gray} />
          <Stat label="Quick Wins" value={lhf.length || "—"} color={lhf.length ? T.amber : T.gray} />
          <Stat label="Goal" value={goals.smart_goal ? "Set" : "—"} color={goals.smart_goal ? T.teal : T.gray} />
        </div>
      </Card>

      {/* Phase progress cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
        {[
          { phase: "keywords",  icon: "🔑", label: "Keywords",      done: totalKeywords > 0,              desc: totalKeywords > 0 ? `${totalKeywords} kws · ${totalPillars} pillars` : "No keywords yet" },
          { phase: "analysis",  icon: "🔍", label: "Analysis",      done: scoredKeywords > 0,             desc: scoredKeywords > 0 ? `${scoredKeywords} scored · ${lhf.length} quick wins` : "Run pipeline first" },
          { phase: "strategy",  icon: "🗺️", label: "Strategy",      done: !!strategy?.pillar_strategy,    desc: strategy?.pillar_strategy ? "Roadmap ready" : "Generate strategy" },
          { phase: "content",   icon: "✍️", label: "Content Hub",    done: contentClusters > 0,            desc: contentClusters > 0 ? `${contentClusters} clusters` : "No content yet" },
          { phase: "links",     icon: "🔗", label: "Link Building",  done: false,                          desc: "Internal + external links" },
        ].map(p => (
          <Card key={p.phase} style={{ cursor: "pointer", borderLeft: `3px solid ${p.done ? T.teal : T.border}`, padding: "10px 12px" }}
            onClick={() => onNavigate(p.phase)}>
            <div style={{ fontSize: 12, fontWeight: 700, color: p.done ? T.teal : T.purpleDark, marginBottom: 3 }}>
              {p.icon} {p.done ? "✓ " : ""}{p.label}
            </div>
            <div style={{ fontSize: 10, color: T.textSoft, lineHeight: 1.4 }}>{p.desc}</div>
          </Card>
        ))}
      </div>
    </div>
  )
}

// ── Phase 1: Goals ──────────────────────────────────────────────────────────
function GoalsPhase({ projectId }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ goal_type: "traffic", target_metric: 10, timeframe_months: 6, business_outcome: "", business_type: "content" })

  const { data: progress, isLoading: loadingProgress } = useQuery({
    queryKey: ["si-goal-progress", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/goals/progress`),
    enabled: !!projectId, retry: false,
  })

  const setGoals = useMutation({
    mutationFn: (body) => apiFetch(`/api/si/${projectId}/goals`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries(["si-goal-progress", projectId]),
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const inStyle = { width: "100%", padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box" }

  return (
    <div>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Phase 1: Goal Setting & Benchmarks</h2>
      <p style={{ margin: "0 0 20px", fontSize: 13, color: T.textSoft }}>
        Define SMART goals and benchmark your current SEO performance. Based on Ahrefs "Plan" step and Backlinko Step 1.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Goal form */}
        <Card>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 12 }}>Set Your Goal</div>
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Business Outcome</label>
            <input value={form.business_outcome} onChange={e => set("business_outcome", e.target.value)}
              placeholder="e.g., Get 50 new customers/month from organic search" style={inStyle} />
          </div>
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Goal Type</label>
            <select value={form.goal_type} onChange={e => set("goal_type", e.target.value)} style={inStyle}>
              <option value="traffic">Organic Traffic Growth</option>
              <option value="leads">Lead Generation</option>
              <option value="revenue">Revenue from SEO</option>
              <option value="local_visibility">Local Visibility</option>
              <option value="authority">Domain Authority</option>
            </select>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Growth Target (%)</label>
              <input type="number" value={form.target_metric} onChange={e => set("target_metric", Number(e.target.value))} style={inStyle} />
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Timeframe (months)</label>
              <input type="number" value={form.timeframe_months} onChange={e => set("timeframe_months", Number(e.target.value))} style={inStyle} />
            </div>
          </div>
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Business Type</label>
            <select value={form.business_type} onChange={e => set("business_type", e.target.value)} style={inStyle}>
              <option value="ecommerce">E-commerce</option>
              <option value="saas">SaaS / Software</option>
              <option value="local">Local Business</option>
              <option value="content">Content / Publisher</option>
              <option value="agency">Agency / Services</option>
            </select>
          </div>
          <Btn onClick={() => setGoals.mutate(form)} loading={setGoals.isPending}>
            Set SMART Goal
          </Btn>
          {setGoals.isError && <div style={{ color: T.red, fontSize: 12, marginTop: 8 }}>{setGoals.error.message}</div>}
        </Card>

        {/* Results / Progress */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {setGoals.data && (
            <Card style={{ background: T.tealLight, border: `1px solid ${T.teal}33` }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: T.teal, marginBottom: 8 }}>SMART Goal Set</div>
              <div style={{ fontSize: 13, lineHeight: 1.5, color: T.text }}>{setGoals.data.smart_goal?.smart_goal}</div>
              {setGoals.data.focus_areas?.content_priority && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, marginBottom: 4 }}>Focus Areas:</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {setGoals.data.focus_areas.content_priority.map((f, i) =>
                      <Badge key={i} label={f} color={T.purple} />
                    )}
                  </div>
                </div>
              )}
            </Card>
          )}

          {setGoals.data?.benchmark && (
            <Card>
              <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 10 }}>Current Benchmark</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {Object.entries(setGoals.data.benchmark).map(([k, v]) => (
                  <div key={k} style={{ background: T.grayLight, borderRadius: 8, padding: 8 }}>
                    <div style={{ fontSize: 10, color: T.textSoft }}>{k.replace(/_/g, " ")}</div>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>{typeof v === "number" ? v.toLocaleString() : v || "—"}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {progress?.progress && (
            <Card>
              <div style={{ fontWeight: 700, fontSize: 13, color: T.amber, marginBottom: 8 }}>Goal Progress</div>
              <div style={{ fontSize: 13 }}>{progress.goal}</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 10 }}>
                {Object.entries(progress.progress).map(([k, v]) => (
                  <div key={k} style={{ background: T.grayLight, borderRadius: 8, padding: 8 }}>
                    <div style={{ fontSize: 10, color: T.textSoft }}>{k.replace(/_/g, " ")}</div>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>{typeof v === "number" ? v.toLocaleString() : String(v)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Phase 2: Research ───────────────────────────────────────────────────────
function ResearchPhase({ projectId }) {
  const qc = useQueryClient()
  const [seeds, setSeeds] = useState("")
  const [platforms, setPlatforms] = useState(["google", "youtube", "reddit"])
  const [showSISection, setShowSISection] = useState(false)

  // Keyword pillars brief — primary data source
  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief
  const kwCtx = kwBrief?.context_json || {}
  const allKws = Object.values(kwBrief?.keywords_json || {}).flat()
  const pillarsKw = kwBrief?.keywords_json || {}
  const brandName = kwCtx.brand_name || ""

  const intentDist = allKws.reduce((acc, k) => {
    const i = k.intent || "informational"; acc[i] = (acc[i] || 0) + 1; return acc
  }, {})
  const sourceDist = allKws.reduce((acc, k) => {
    const s = k.source || "crawl"; acc[s] = (acc[s] || 0) + 1; return acc
  }, {})

  const { data: insights } = useQuery({
    queryKey: ["si-insights", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/research/insights`),
    enabled: !!projectId, retry: false,
  })

  const research = useMutation({
    mutationFn: (body) => apiFetch(`/api/si/${projectId}/research`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries(["si-strategy", projectId]),
  })

  const togglePlatform = (p) => setPlatforms(ps => ps.includes(p) ? ps.filter(x => x !== p) : [...ps, p])

  const intentColor = { informational: T.purple, transactional: T.teal, commercial: T.amber, navigational: T.gray, brand: T.purpleDark }

  return (
    <div>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Phase 2: Keyword Research Summary</h2>
      <p style={{ margin: "0 0 20px", fontSize: 13, color: T.textSoft }}>
        Full keyword universe from pipeline crawl, AI expansion, and brand analysis. Multi-platform research available below.
      </p>

      {/* ── Keyword Research Summary from Pipeline ── */}
      {kwBrief ? (
        <div style={{ marginBottom: 20 }}>

          {/* Stats row */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, marginBottom: 14 }}>
            {[
              { label: "Total Keywords", val: allKws.length, color: T.purpleDark },
              { label: "Keyword Pillars", val: Object.keys(pillarsKw).length, color: T.purple },
              { label: "Blog Clusters", val: kwCtx.content_clusters?.length || 0, color: T.teal },
              { label: "AI Suggested", val: kwCtx.ai_suggested_count || 0, color: T.amber },
              { label: "Brand Name", val: brandName || "—", color: brandName ? T.purpleDark : T.gray },
            ].map((s, i) => (
              <Card key={i} style={{ textAlign: "center", padding: "10px 8px" }}>
                <div style={{ fontSize: typeof s.val === "number" ? 20 : 14, fontWeight: 700, color: s.color }}>{s.val}</div>
                <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{s.label}</div>
              </Card>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
            {/* Intent distribution */}
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>Search Intent Distribution</div>
              {Object.entries(intentDist).sort((a,b) => b[1]-a[1]).map(([intent, count]) => (
                <div key={intent} style={{ marginBottom: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: intentColor[intent] || T.gray, textTransform: "capitalize" }}>{intent}</span>
                    <span style={{ fontSize: 11, fontWeight: 700 }}>{count} keywords</span>
                  </div>
                  <div style={{ height: 6, background: T.grayLight, borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${Math.round((count / allKws.length) * 100)}%`,
                      background: intentColor[intent] || T.gray, borderRadius: 3 }} />
                  </div>
                </div>
              ))}
            </Card>

            {/* Source distribution + pillar list */}
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>Keyword Sources</div>
              {Object.entries(sourceDist).sort((a,b) => b[1]-a[1]).map(([src, count]) => (
                <div key={src} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "5px 0", borderBottom: `1px solid ${T.border}08`, fontSize: 12 }}>
                  <span style={{ textTransform: "capitalize", color: T.textSoft }}>{src.replace(/_/g," ")}</span>
                  <Badge label={`${count}`} color={src === "brand" ? T.purpleDark : src === "ai_suggested" ? T.amber : T.purple} />
                </div>
              ))}
              {brandName && (
                <div style={{ marginTop: 8, padding: "6px 8px", background: T.purpleLight, borderRadius: 6, fontSize: 11 }}>
                  <span style={{ fontWeight: 600, color: T.purpleDark }}>Brand detected: </span>
                  <span>{brandName}</span>
                </div>
              )}
            </Card>
          </div>

          {/* Pillar keyword breakdown */}
          <Card>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>Pillar Keyword Breakdown</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
              {Object.entries(pillarsKw).map(([pillar, kws]) => (
                <div key={pillar} style={{ background: T.grayLight, borderRadius: 8, padding: "8px 10px" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 4 }}>{pillar}</div>
                  <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 4 }}>{kws.length} keywords</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                    {kws.slice(0, 3).map((k, i) => (
                      <span key={i} style={{ fontSize: 9, background: "#fff", border: `0.5px solid ${T.border}`, borderRadius: 4, padding: "1px 5px", color: T.text }}>{k.keyword}</span>
                    ))}
                    {kws.length > 3 && <span style={{ fontSize: 9, color: T.textSoft }}>+{kws.length - 3} more</span>}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      ) : (
        <Card style={{ marginBottom: 20, padding: 24, textAlign: "center", background: T.grayLight }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>🔍</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 4 }}>No keyword research yet</div>
          <div style={{ fontSize: 12, color: T.textSoft }}>Complete the Keyword Pipeline and click "Send to Strategy Hub" to see your research.</div>
        </Card>
      )}

      {/* ── Multi-Platform Research (SI Engine) ── */}
      <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
        <button onClick={() => setShowSISection(!showSISection)} style={{
          background: "none", border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600,
          color: T.purpleDark, marginBottom: 12, display: "flex", alignItems: "center", gap: 6,
        }}>
          {showSISection ? "▾" : "▸"} Multi-Platform Research (Additional Expansion)
        </button>

        {showSISection && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <Card>
              <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 12 }}>Research Settings</div>
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Seed Keywords (comma-separated)</label>
                <textarea value={seeds} onChange={e => setSeeds(e.target.value)}
                  placeholder="organic turmeric, spice blends, healthy cooking"
                  style={{ width: "100%", padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, height: 60, resize: "vertical", boxSizing: "border-box" }} />
              </div>
              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 6 }}>Platforms</label>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {[
                    { id: "google", label: "🔍 Google", color: T.purple },
                    { id: "youtube", label: "▶ YouTube", color: T.red },
                    { id: "reddit", label: "💬 Reddit", color: T.amber },
                    { id: "ai", label: "🤖 AI Tools", color: T.teal },
                  ].map(p => (
                    <button key={p.id} onClick={() => togglePlatform(p.id)} style={{
                      padding: "5px 12px", borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: "pointer",
                      background: platforms.includes(p.id) ? p.color + "18" : T.grayLight,
                      color: platforms.includes(p.id) ? p.color : T.gray,
                      border: `1px solid ${platforms.includes(p.id) ? p.color + "33" : T.border}`,
                    }}>{p.label}</button>
                  ))}
                </div>
              </div>
              <Btn onClick={() => research.mutate({
                seed_keywords: seeds.split(",").map(s => s.trim()).filter(Boolean),
                platforms,
              })} loading={research.isPending}>
                Run Research
              </Btn>
              {research.isError && <div style={{ color: T.red, fontSize: 12, marginTop: 8 }}>{research.error.message}</div>}
            </Card>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {research.data && (
                <Card style={{ background: T.tealLight, border: `1px solid ${T.teal}33` }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: T.teal, marginBottom: 8 }}>Research Complete</div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    <Stat label="Total Keywords" value={research.data.total_keywords} color={T.purpleDark} />
                    <Stat label="New Found" value={research.data.new_keywords} color={T.teal} />
                    <Stat label="Google" value={research.data.google_count} />
                    <Stat label="YouTube" value={research.data.youtube_count} color={T.red} />
                    <Stat label="Reddit" value={research.data.reddit_count} color={T.amber} />
                    <Stat label="AI Topics" value={research.data.ai_count} color={T.teal} />
                  </div>
                </Card>
              )}
              {insights && (
                <Card>
                  <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 8 }}>Customer Insight Questions</div>
                  <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 8 }}>Answer these to improve keyword research quality:</div>
                  {(insights.questions || []).map((q, i) => (
                    <div key={i} style={{ fontSize: 12, marginBottom: 6, padding: "6px 8px", background: T.grayLight, borderRadius: 6 }}>
                      {i + 1}. {q}
                    </div>
                  ))}
                </Card>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Phase 3: Intent & Briefs ───────────────────────────────────────────────
function IntentBriefsPhase({ projectId, strategy }) {
  const qc = useQueryClient()
  const keywords = strategy?.keywords || []
  const [showSISection, setShowSISection] = useState(false)
  const [openCluster, setOpenCluster] = useState(null)

  // Keyword pillars brief — primary data source for clusters
  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief
  const kwCtx = kwBrief?.context_json || {}
  const blogClusters = kwCtx.content_clusters || []
  const allKws = Object.values(kwBrief?.keywords_json || {}).flat()

  const analyzeIntent = useMutation({
    mutationFn: (body) => apiFetch(`/api/si/${projectId}/intent`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries(["si-strategy", projectId]),
  })

  const generateBriefs = useMutation({
    mutationFn: (body) => apiFetch(`/api/si/${projectId}/briefs`, { method: "POST", body: JSON.stringify(body || {}) }),
    onSuccess: () => qc.invalidateQueries(["si-strategy", projectId]),
  })

  const kwMap = analyzeIntent.data?.keyword_map || strategy?.keyword_map || []
  const briefs = generateBriefs.data?.briefs || strategy?.seo_briefs || []

  const intentColor = (i) => ({ informational: T.purple, transactional: T.teal, commercial: T.amber, navigational: T.gray, brand: T.purpleDark }[i] || T.gray)
  const commercialColor = (v) => ({ high: T.teal, medium: T.amber, low: T.gray }[v] || T.gray)

  return (
    <div>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Phase 3: Content Briefs & Intent Mapping</h2>
      <p style={{ margin: "0 0 20px", fontSize: 13, color: T.textSoft }}>
        Blog cluster briefs from your keyword pillars — ready-to-publish content plan. Each cluster targets a distinct search intent.
      </p>

      {/* ── Blog Cluster Content Briefs ── */}
      {blogClusters.length > 0 ? (
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark }}>
              Content Briefs · {blogClusters.length} clusters
            </div>
            <div style={{ fontSize: 11, color: T.textSoft }}>
              {allKws.length} total keywords mapped to clusters
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {blogClusters.map((cluster, i) => {
              const isOpen = openCluster === i
              const kws = cluster.keywords || []
              const informationalKws = kws.filter(k => (k.score || 0) > 0).sort((a,b) => (b.score||0)-(a.score||0))
              return (
                <div key={i} style={{ border: `1px solid ${T.border}`, borderRadius: 10,
                  borderLeft: `3px solid ${commercialColor(cluster.commercial_value)}`, background: "#fff" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "12px 16px", cursor: "pointer" }}
                    onClick={() => setOpenCluster(isOpen ? null : i)}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: T.text }}>{cluster.name}</span>
                        <Badge label={`${cluster.commercial_value || "medium"} value`} color={commercialColor(cluster.commercial_value)} />
                        <Badge label={`${kws.length} keywords`} color={T.purple} />
                      </div>
                      <div style={{ fontSize: 11, color: T.textSoft, fontStyle: "italic", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {cluster.blog_title}
                      </div>
                    </div>
                    <span style={{ fontSize: 14, color: T.textSoft, marginLeft: 12 }}>{isOpen ? "▾" : "▸"}</span>
                  </div>

                  {isOpen && (
                    <div style={{ padding: "0 16px 14px", borderTop: `1px solid ${T.border}08` }}>
                      {/* Blog title + content outline */}
                      <div style={{ marginBottom: 12, padding: "10px 12px", background: T.purpleLight, borderRadius: 8 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: T.purpleDark, marginBottom: 4 }}>SUGGESTED BLOG TITLE</div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{cluster.blog_title}</div>
                      </div>

                      {/* Content writing checklist */}
                      <div style={{ marginBottom: 12 }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 6 }}>CONTENT BRIEF CHECKLIST</div>
                        {[
                          "Introduction: Address the main search intent clearly",
                          `Primary keyword: ${kws[0]?.keyword || cluster.name} — use in title, H1, first paragraph`,
                          "Cover all sub-topics in the keyword cluster",
                          "Add FAQs for featured snippet opportunities",
                          "Include real examples, data, or expert quotes (E-E-A-T)",
                          "Add internal links to related pillar pages",
                          "Target: 1,500–2,500 words for informational; 800–1,200 for commercial",
                          "Meta description: 150–160 chars with primary keyword",
                        ].map((item, j) => (
                          <div key={j} style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 5, fontSize: 12 }}>
                            <span style={{ color: T.teal, fontSize: 13, flexShrink: 0 }}>☐</span>
                            <span style={{ color: T.text }}>{item}</span>
                          </div>
                        ))}
                      </div>

                      {/* Keywords for this cluster */}
                      <div>
                        <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 6 }}>
                          TARGET KEYWORDS ({kws.length})
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                          {kws.map((k, j) => (
                            <div key={j} style={{ display: "flex", alignItems: "center", gap: 4, padding: "3px 8px",
                              background: T.grayLight, borderRadius: 6, fontSize: 11, border: `0.5px solid ${T.border}` }}>
                              <span>{k.keyword || k}</span>
                              {k.score > 0 && <span style={{ fontWeight: 700, color: k.score >= 70 ? T.teal : k.score >= 50 ? T.amber : T.gray }}>
                                {k.score}
                              </span>}
                              {k.intent && <Badge label={k.intent} color={intentColor(k.intent)} />}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <Card style={{ marginBottom: 20, padding: 24, textAlign: "center", background: T.grayLight }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>📝</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 4 }}>No content clusters yet</div>
          <div style={{ fontSize: 12, color: T.textSoft }}>Complete the Keyword Pipeline and click "Send to Strategy Hub" to generate content briefs.</div>
        </Card>
      )}

      {/* ── SI Engine Intent Analysis (collapsible) ── */}
      <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
        <button onClick={() => setShowSISection(!showSISection)} style={{
          background: "none", border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600,
          color: T.purpleDark, marginBottom: 12, display: "flex", alignItems: "center", gap: 6,
        }}>
          {showSISection ? "▾" : "▸"} AI Intent Analysis & SEO Briefs (Advanced)
        </button>

        {showSISection && (
          <div>
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              <Btn onClick={() => analyzeIntent.mutate({ keywords: keywords.slice(0, 30) })}
                loading={analyzeIntent.isPending} variant="outline">
                Analyze Intent ({keywords.length} keywords)
              </Btn>
              <Btn onClick={() => generateBriefs.mutate({})}
                loading={generateBriefs.isPending} variant="teal">
                Generate Briefs
              </Btn>
            </div>

            {analyzeIntent.isError && <div style={{ color: T.red, fontSize: 12, marginBottom: 10 }}>{analyzeIntent.error.message}</div>}

            {kwMap.length > 0 && (
              <Card style={{ marginBottom: 16 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 10 }}>
                  Keyword Map ({kwMap.length} keywords)
                </div>
                <div style={{ maxHeight: 300, overflowY: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                        <th style={{ textAlign: "left", padding: "6px 8px", color: T.textSoft, fontWeight: 600 }}>Keyword</th>
                        <th style={{ textAlign: "left", padding: "6px 8px", color: T.textSoft, fontWeight: 600 }}>Intent</th>
                        <th style={{ textAlign: "left", padding: "6px 8px", color: T.textSoft, fontWeight: 600 }}>Format</th>
                        <th style={{ textAlign: "center", padding: "6px 8px", color: T.textSoft, fontWeight: 600 }}>Biz Potential</th>
                        <th style={{ textAlign: "center", padding: "6px 8px", color: T.textSoft, fontWeight: 600 }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {kwMap.map((kw, i) => (
                        <tr key={i} style={{ borderBottom: `1px solid ${T.border}08` }}>
                          <td style={{ padding: "6px 8px", fontWeight: 500 }}>{kw.keyword}</td>
                          <td style={{ padding: "6px 8px" }}>
                            <Badge label={kw.intent} color={intentColor(kw.intent)} />
                          </td>
                          <td style={{ padding: "6px 8px", color: T.textSoft }}>{kw.content_format}</td>
                          <td style={{ padding: "6px 8px", textAlign: "center" }}>
                            <span style={{ fontWeight: 700, color: kw.business_potential >= 2 ? T.teal : kw.business_potential >= 1 ? T.amber : T.gray }}>
                              {kw.business_potential}/3
                            </span>
                          </td>
                          <td style={{ padding: "6px 8px", textAlign: "center" }}>
                            <Badge label={kw.status} color={kw.status === "rejected" ? T.red : T.gray} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}

            {briefs.length > 0 && (
              <Card>
                <div style={{ fontWeight: 700, fontSize: 13, color: T.teal, marginBottom: 10 }}>
                  SEO Briefs ({briefs.length})
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {briefs.map((b, i) => <BriefCard key={i} brief={b} />)}
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function BriefCard({ brief }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ border: `1px solid ${T.border}`, borderRadius: 8, padding: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
        onClick={() => setOpen(!open)}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{brief.keyword || brief.title}</div>
          <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
            {brief.intent} · {brief.content_format} · {brief.target_word_count || "1500+"} words
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {brief.business_potential_label && <Badge label={brief.business_potential_label} color={T.teal} />}
          <span style={{ fontSize: 14 }}>{open ? "▾" : "▸"}</span>
        </div>
      </div>
      {open && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${T.border}` }}>
          {brief.title_suggestions?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft }}>Title Ideas:</div>
              {brief.title_suggestions.map((t, i) => <div key={i} style={{ fontSize: 12, marginTop: 2 }}>• {t}</div>)}
            </div>
          )}
          {brief.required_sections?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft }}>Required Sections:</div>
              {brief.required_sections.map((s, i) => <div key={i} style={{ fontSize: 12, marginTop: 2 }}>• {s}</div>)}
            </div>
          )}
          {brief.eeat && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft }}>E-E-A-T Requirements:</div>
              <div style={{ fontSize: 12, marginTop: 2 }}>{JSON.stringify(brief.eeat)}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Phase 4: Scoring ─────────────────────────────────────────────────────────
function ScoringPhase({ projectId, strategy }) {
  const qc = useQueryClient()
  const [sortBy, setSortBy] = useState("score")
  const [showSISection, setShowSISection] = useState(false)

  // Keyword pillars brief — primary scoring data
  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief
  const allKws = Object.entries(kwBrief?.keywords_json || {}).flatMap(([pillar, kws]) =>
    kws.map(k => ({ ...k, pillar }))
  )
  const scoredKws = allKws.filter(k => (k.score || 0) > 0)
  const sorted = [...scoredKws].sort((a, b) => {
    if (sortBy === "score") return (b.score || 0) - (a.score || 0)
    if (sortBy === "alpha") return (a.keyword || "").localeCompare(b.keyword || "")
    return 0
  })

  const high   = scoredKws.filter(k => k.score >= 70).length
  const medium = scoredKws.filter(k => k.score >= 50 && k.score < 70).length
  const low    = scoredKws.filter(k => k.score < 50).length

  const scoreKws = useMutation({
    mutationFn: () => apiFetch(`/api/si/${projectId}/score`, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: () => qc.invalidateQueries(["si-strategy", projectId]),
  })
  const siScored = scoreKws.data?.scored_keywords || strategy?.scored_keywords || []

  const scoreColor = s => s >= 70 ? T.teal : s >= 50 ? T.amber : T.gray
  const intentColor = (i) => ({ informational: T.purple, transactional: T.teal, commercial: T.amber, navigational: T.gray, brand: T.purpleDark }[i] || T.gray)

  return (
    <div>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Phase 4: Keyword Scoring & Prioritization</h2>
      <p style={{ margin: "0 0 20px", fontSize: 13, color: T.textSoft }}>
        All keywords scored by opportunity, relevance, and commercial value. Sort and prioritize your keyword targets.
      </p>

      {/* ── kwBrief scored keywords ── */}
      {scoredKws.length > 0 ? (
        <div style={{ marginBottom: 20 }}>
          {/* Score distribution */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10, marginBottom: 14 }}>
            {[
              { label: "All Keywords", val: allKws.length, color: T.purpleDark },
              { label: "High Score (70+)", val: high, color: T.teal },
              { label: "Medium (50–69)", val: medium, color: T.amber },
              { label: "Low (<50)", val: low, color: T.gray },
            ].map((s, i) => (
              <Card key={i} style={{ textAlign: "center", padding: "10px 8px",
                borderTop: `3px solid ${s.color}` }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.val}</div>
                <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{s.label}</div>
              </Card>
            ))}
          </div>

          {/* Sortable controls */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
            <span style={{ fontSize: 11, color: T.textSoft }}>Sort by:</span>
            {[["score", "Score ↓"], ["alpha", "A–Z"]].map(([val, label]) => (
              <button key={val} onClick={() => setSortBy(val)} style={{
                padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: "pointer",
                background: sortBy === val ? T.purpleDark : T.grayLight,
                color: sortBy === val ? "#fff" : T.gray,
                border: `1px solid ${sortBy === val ? T.purpleDark : T.border}`,
              }}>{label}</button>
            ))}
          </div>

          {/* Scored keyword table */}
          <Card>
            <div style={{ maxHeight: 480, overflowY: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}`, position: "sticky", top: 0, background: "#fff" }}>
                    <th style={{ textAlign: "left", padding: "8px 8px", color: T.textSoft, fontWeight: 600 }}>Keyword</th>
                    <th style={{ textAlign: "center", padding: "8px 6px", color: T.textSoft, fontWeight: 600 }}>Score</th>
                    <th style={{ textAlign: "left", padding: "8px 6px", color: T.textSoft, fontWeight: 600 }}>Pillar</th>
                    <th style={{ textAlign: "left", padding: "8px 6px", color: T.textSoft, fontWeight: 600 }}>Intent</th>
                    <th style={{ textAlign: "left", padding: "8px 6px", color: T.textSoft, fontWeight: 600 }}>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((kw, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${T.border}08`,
                      background: i % 2 === 0 ? "#fff" : T.grayLight + "60" }}>
                      <td style={{ padding: "6px 8px", fontWeight: 500 }}>{kw.keyword}</td>
                      <td style={{ padding: "6px 6px", textAlign: "center" }}>
                        <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 6,
                          fontSize: 11, fontWeight: 700, background: scoreColor(kw.score) + "18",
                          color: scoreColor(kw.score), border: `1px solid ${scoreColor(kw.score)}33` }}>
                          {kw.score}
                        </span>
                      </td>
                      <td style={{ padding: "6px 6px", fontSize: 11, color: T.textSoft }}>{kw.pillar}</td>
                      <td style={{ padding: "6px 6px" }}>
                        {kw.intent && <Badge label={kw.intent} color={intentColor(kw.intent)} />}
                      </td>
                      <td style={{ padding: "6px 6px", fontSize: 10, color: T.textSoft, textTransform: "capitalize" }}>
                        {(kw.source || "crawl").replace(/_/g," ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      ) : (
        <Card style={{ marginBottom: 20, padding: 24, textAlign: "center", background: T.grayLight }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>⚡</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 4 }}>No scored keywords yet</div>
          <div style={{ fontSize: 12, color: T.textSoft }}>Run the Keyword Pipeline with scoring mode to see keyword scores here.</div>
        </Card>
      )}

      {/* ── SI Engine Scoring ── */}
      <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
        <button onClick={() => setShowSISection(!showSISection)} style={{
          background: "none", border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600,
          color: T.purpleDark, marginBottom: 12, display: "flex", alignItems: "center", gap: 6,
        }}>
          {showSISection ? "▾" : "▸"} P7++ Composite Scoring Engine (Advanced)
        </button>

        {showSISection && (
          <div>
            <div style={{ marginBottom: 16, display: "flex", gap: 12, alignItems: "center" }}>
              <Btn onClick={() => scoreKws.mutate()} loading={scoreKws.isPending}>
                Score All Keywords
              </Btn>
              {scoreKws.data?.total > 0 && (
                <div style={{ display: "flex", gap: 12 }}>
                  <Badge label={`${scoreKws.data?.critical || 0} Critical`} color={T.red} />
                  <Badge label={`${scoreKws.data?.high || 0} High`} color={T.amber} />
                  <Badge label={`${scoreKws.data?.medium || 0} Medium`} color={T.purple} />
                  <Badge label={`${scoreKws.data?.low || 0} Low`} color={T.gray} />
                </div>
              )}
            </div>
            {scoreKws.isError && <div style={{ color: T.red, fontSize: 12, marginBottom: 10 }}>{scoreKws.error.message}</div>}

            {siScored.length > 0 && (
              <Card>
                <div style={{ maxHeight: 400, overflowY: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ borderBottom: `1px solid ${T.border}`, position: "sticky", top: 0, background: "#fff" }}>
                        <th style={{ textAlign: "left", padding: "8px 8px", color: T.textSoft }}>Keyword</th>
                        <th style={{ textAlign: "center", padding: "8px 8px", color: T.textSoft }}>Score</th>
                        <th style={{ textAlign: "center", padding: "8px 8px", color: T.textSoft }}>Priority</th>
                        <th style={{ textAlign: "center", padding: "8px 8px", color: T.textSoft }}>Biz</th>
                        <th style={{ textAlign: "center", padding: "8px 8px", color: T.textSoft }}>Traffic</th>
                        <th style={{ textAlign: "center", padding: "8px 8px", color: T.textSoft }}>Gap</th>
                        <th style={{ textAlign: "center", padding: "8px 8px", color: T.textSoft }}>Ease</th>
                      </tr>
                    </thead>
                    <tbody>
                      {siScored.map((kw, i) => (
                        <tr key={i} style={{ borderBottom: `1px solid ${T.border}08` }}>
                          <td style={{ padding: "6px 8px", fontWeight: 500 }}>{kw.keyword}</td>
                          <td style={{ padding: "6px 8px", textAlign: "center", fontWeight: 700 }}>
                            {(kw.composite_score || 0).toFixed(1)}
                          </td>
                          <td style={{ padding: "6px 8px", textAlign: "center" }}>
                            <Badge label={kw.priority} color={{ critical: T.red, high: T.amber, medium: T.purple, low: T.gray }[kw.priority] || T.gray} />
                          </td>
                          <td style={{ padding: "6px 8px", textAlign: "center" }}>{(kw.business_potential || 0).toFixed(1)}</td>
                          <td style={{ padding: "6px 8px", textAlign: "center" }}>{(kw.traffic_score || 0).toFixed(1)}</td>
                          <td style={{ padding: "6px 8px", textAlign: "center" }}>{(kw.competitor_gap || 0).toFixed(1)}</td>
                          <td style={{ padding: "6px 8px", textAlign: "center" }}>{(kw.content_ease || 0).toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Phase 5: Quick Wins (Low-Hanging Fruit) ────────────────────────────────
function QuickWinsPhase({ projectId }) {
  const [showSISection, setShowSISection] = useState(false)

  // Keyword pillars brief — top scored keywords = quick wins
  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief
  const kwCtx = kwBrief?.context_json || {}
  const allKws = Object.entries(kwBrief?.keywords_json || {}).flatMap(([pillar, kws]) =>
    kws.map(k => ({ ...k, pillar }))
  )

  // Quick wins = top-scored (≥60) transactional & commercial keywords
  const quickWins = allKws
    .filter(k => (k.score || 0) >= 60)
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 20)

  // Cluster quick wins = high commercial value blog clusters
  const clusters = kwCtx.content_clusters || []
  const highValueClusters = clusters.filter(c => c.commercial_value === "high")

  // Brand keywords = quick navigational wins
  const brandKws = allKws.filter(k => k.source === "brand").slice(0, 5)

  const { data: lhfData, isLoading: lhfLoading } = useQuery({
    queryKey: ["si-lhf", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/low-hanging-fruit`),
    enabled: !!projectId && showSISection,
  })
  const opportunities = lhfData?.opportunities || []
  const categories = lhfData?.categories || {}

  const scoreColor = s => s >= 80 ? T.teal : s >= 60 ? T.amber : T.gray
  const intentColor = (i) => ({ informational: T.purple, transactional: T.teal, commercial: T.amber, navigational: T.gray, brand: T.purpleDark }[i] || T.gray)

  return (
    <div>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Phase 5: Quick Wins</h2>
      <p style={{ margin: "0 0 20px", fontSize: 13, color: T.textSoft }}>
        Highest-opportunity keywords and content targets — ranked by score. Start with these for fastest results.
      </p>

      {quickWins.length > 0 || highValueClusters.length > 0 || brandKws.length > 0 ? (
        <div style={{ marginBottom: 20 }}>

          {/* Summary stats */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16 }}>
            {[
              { label: "High-Score Keywords", val: quickWins.length, color: T.teal, icon: "🏆" },
              { label: "High-Value Clusters", val: highValueClusters.length, color: T.amber, icon: "📦" },
              { label: "Brand Keywords", val: brandKws.length, color: T.purpleDark, icon: "🏷️" },
              { label: "AI Suggested", val: kwCtx.ai_suggested_count || 0, color: T.purple, icon: "🤖" },
            ].map((s, i) => (
              <Card key={i} style={{ textAlign: "center", padding: "10px 8px", borderTop: `3px solid ${s.color}` }}>
                <div style={{ fontSize: 18, marginBottom: 2 }}>{s.icon}</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.val}</div>
                <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{s.label}</div>
              </Card>
            ))}
          </div>

          {/* Top keyword quick wins */}
          {quickWins.length > 0 && (
            <Card style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>
                Top Keyword Opportunities (Score ≥ 60)
              </div>
              <div style={{ maxHeight: 340, overflowY: "auto" }}>
                {quickWins.map((kw, i) => (
                  <div key={i} style={{
                    display: "grid", gridTemplateColumns: "1fr 60px auto auto",
                    alignItems: "center", gap: 8, padding: "7px 6px",
                    borderBottom: i < quickWins.length - 1 ? `1px solid ${T.border}08` : "none",
                    background: i % 2 === 0 ? "#fff" : T.grayLight + "50",
                  }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600 }}>{kw.keyword}</div>
                      <div style={{ fontSize: 10, color: T.textSoft, marginTop: 1 }}>{kw.pillar}</div>
                    </div>
                    <div style={{ textAlign: "center" }}>
                      <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 6,
                        fontSize: 12, fontWeight: 700, background: scoreColor(kw.score) + "18",
                        color: scoreColor(kw.score), border: `1px solid ${scoreColor(kw.score)}33` }}>
                        {kw.score}
                      </span>
                    </div>
                    <Badge label={kw.intent || "—"} color={intentColor(kw.intent)} />
                    <Badge label={(kw.source || "crawl").replace(/_/g," ")} color={T.gray} />
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* High-value blog clusters */}
          {highValueClusters.length > 0 && (
            <Card style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.amber, marginBottom: 10 }}>
                High-Value Content Targets
              </div>
              {highValueClusters.map((c, i) => (
                <div key={i} style={{ padding: "8px 10px", borderRadius: 8, background: T.amberLight,
                  border: `1px solid ${T.amber}30`, marginBottom: 6 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.text }}>{c.name}</div>
                  <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2, fontStyle: "italic" }}>{c.blog_title}</div>
                  <div style={{ fontSize: 10, color: T.amber, marginTop: 3 }}>{(c.keywords || []).length} keywords · high commercial value</div>
                </div>
              ))}
            </Card>
          )}

          {/* Brand keywords */}
          {brandKws.length > 0 && (
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>
                Brand Keyword Targets (Navigational)
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {brandKws.map((k, i) => (
                  <div key={i} style={{ padding: "4px 10px", background: T.purpleLight,
                    borderRadius: 6, fontSize: 12, fontWeight: 500, color: T.purpleDark,
                    border: `0.5px solid ${T.purple}33` }}>
                    {k.keyword}
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 10, color: T.textSoft, marginTop: 8 }}>
                Brand keywords bring direct navigational traffic. Optimize landing pages for these.
              </div>
            </Card>
          )}
        </div>
      ) : (
        <Card style={{ marginBottom: 20, padding: 24, textAlign: "center", background: T.grayLight }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🍎</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 4 }}>No quick wins yet</div>
          <div style={{ fontSize: 12, color: T.textSoft }}>Complete the Keyword Pipeline with scoring to see high-opportunity keywords.</div>
        </Card>
      )}

      {/* ── SI Engine LHF (collapsible) ── */}
      <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
        <button onClick={() => setShowSISection(!showSISection)} style={{
          background: "none", border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600,
          color: T.purpleDark, marginBottom: 12, display: "flex", alignItems: "center", gap: 6,
        }}>
          {showSISection ? "▾" : "▸"} Low-Hanging Fruit — Ranking Position Data
        </button>

        {showSISection && (
          <div>
            {lhfLoading && <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 10 }}>Loading position data...</div>}

            {Object.keys(categories).length > 0 && (
              <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
                {Object.entries(categories).map(([cat, items]) => (
                  <Card key={cat} style={{ flex: 1, borderLeft: `3px solid ${cat === "striking_distance" ? T.teal : cat === "page_one" ? T.amber : T.purple}` }}>
                    <div style={{ fontSize: 20, fontWeight: 700, color: T.text }}>{items.length}</div>
                    <div style={{ fontSize: 11, color: T.textSoft, textTransform: "capitalize" }}>{cat.replace(/_/g, " ")}</div>
                  </Card>
                ))}
              </div>
            )}

            {opportunities.length > 0 && (
              <Card>
                <div style={{ maxHeight: 400, overflowY: "auto" }}>
                  {opportunities.map((opp, i) => (
                    <div key={i} style={{
                      display: "grid", gridTemplateColumns: "2fr 80px 80px 1fr 80px",
                      alignItems: "center", padding: "8px 8px",
                      borderBottom: i < opportunities.length - 1 ? `1px solid ${T.border}08` : "none",
                    }}>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 600 }}>{opp.keyword}</div>
                        {opp.url && <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{opp.url}</div>}
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: opp.current_position <= 3 ? T.teal : T.amber }}>
                          #{opp.current_position}
                        </div>
                        <div style={{ fontSize: 9, color: T.textSoft }}>Position</div>
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: T.teal }}>+{opp.traffic_uplift || "?"}</div>
                        <div style={{ fontSize: 9, color: T.textSoft }}>Est. Uplift</div>
                      </div>
                      <div style={{ fontSize: 11, color: T.textSoft }}>
                        {(opp.recommendations || []).slice(0, 2).join(" · ")}
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <Badge label={opp.category || "optimize"} color={T.teal} />
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {!lhfLoading && opportunities.length === 0 && (
              <div style={{ fontSize: 12, color: T.textSoft, padding: "10px 0" }}>
                No position-based quick wins found. Connect Google Search Console for ranking data.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Phase 6: Link Building ────────────────────────────────────────────────
function LinkBuildingPhase({ projectId, kw2Session }) {
  const qc = useQueryClient()

  // Session link building plan (if active session has strategy)
  const sessionLinkPlan = kw2Session?._strategy?.link_building_plan || null
  const sessionLabel = kw2Session?.name ||
    (Array.isArray(kw2Session?.seed_keywords) && kw2Session.seed_keywords.length
      ? kw2Session.seed_keywords.slice(0, 2).join(" · ") : null)

  const { data: plan } = useQuery({
    queryKey: ["si-link-plan", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/link-building/plan`),
    enabled: !!projectId, retry: false,
  })

  const { data: moneyPages } = useQuery({
    queryKey: ["si-money-pages", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/link-building/money-pages`),
    enabled: !!projectId, retry: false,
  })

  const { data: internalGaps } = useQuery({
    queryKey: ["si-internal-gaps", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/link-building/internal-gaps`),
    enabled: !!projectId, retry: false,
  })

  const { data: oppsData } = useQuery({
    queryKey: ["si-link-opps", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/link-building/opportunities`),
    enabled: !!projectId, retry: false,
  })

  // Keyword brief for cluster-based linking
  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief
  const clusters = kwBrief?.context_json?.content_clusters || []
  const allKws = Object.values(kwBrief?.keywords_json || {}).flat()

  const opportunities = oppsData?.opportunities || []
  const pages = moneyPages?.money_pages || []
  const gaps = internalGaps?.gaps || []

  return (
    <div>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Link Building</h2>
      <p style={{ margin: "0 0 16px", fontSize: 13, color: T.textSoft }}>
        Internal linking from clusters, competitor link gaps, money pages, and tracked link opportunities.
      </p>

      {/* Session link building plan */}
      {sessionLinkPlan && (
        <Card style={{ marginBottom: 16, border: `1px solid ${T.purple}33`, background: `${T.purple}04` }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>
            🔗 AI Link Strategy · {sessionLabel || "Active Session"}
          </div>
          {typeof sessionLinkPlan === "string" ? (
            <p style={{ fontSize: 12, color: T.text, lineHeight: 1.6, margin: 0 }}>{sessionLinkPlan}</p>
          ) : Array.isArray(sessionLinkPlan) ? (
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {sessionLinkPlan.map((item, i) => (
                <li key={i} style={{ fontSize: 12, marginBottom: 5, lineHeight: 1.4 }}>
                  {typeof item === "string" ? item : item?.strategy || item?.tactic || JSON.stringify(item)}
                </li>
              ))}
            </ul>
          ) : (
            <div>
              {sessionLinkPlan.outreach_targets && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, marginBottom: 4 }}>Outreach Targets</div>
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {(sessionLinkPlan.outreach_targets || []).slice(0, 5).map((t, i) => (
                      <li key={i} style={{ fontSize: 12, marginBottom: 3 }}>{t}</li>
                    ))}
                  </ul>
                </div>
              )}
              {sessionLinkPlan.strategies && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, marginBottom: 4 }}>Strategies</div>
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {(sessionLinkPlan.strategies || []).slice(0, 5).map((s, i) => (
                      <li key={i} style={{ fontSize: 12, marginBottom: 3 }}>
                        {typeof s === "string" ? s : s?.name || JSON.stringify(s)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        {/* Link Building Plan */}
        {plan && (
          <Card>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 10 }}>Link Building Plan</div>
            {(plan.strategies || []).map((s, i) => (
              <div key={i} style={{ padding: "8px 0", borderBottom: i < plan.strategies.length - 1 ? `1px solid ${T.border}08` : "none" }}>
                <div style={{ fontSize: 12, fontWeight: 600 }}>{s.name}</div>
                <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>{s.description}</div>
                <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                  <Badge label={s.difficulty || "medium"} color={s.difficulty === "easy" ? T.teal : s.difficulty === "hard" ? T.red : T.amber} />
                  <Badge label={s.impact || "medium"} color={T.purple} />
                </div>
              </div>
            ))}
          </Card>
        )}

        {/* Money Pages */}
        <Card>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.teal, marginBottom: 10 }}>Money Pages ({pages.length})</div>
          {pages.length === 0 ? (
            <div style={{ fontSize: 12, color: T.textSoft }}>No money pages detected yet</div>
          ) : (
            <div style={{ maxHeight: 250, overflowY: "auto" }}>
              {pages.map((p, i) => (
                <div key={i} style={{ padding: "6px 0", borderBottom: `1px solid ${T.border}08`, fontSize: 12 }}>
                  <div style={{ fontWeight: 600 }}>{p.keyword}</div>
                  <div style={{ color: T.textSoft, marginTop: 2 }}>{p.url} · Position #{p.position}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Internal Link Gaps */}
      {gaps.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.amber, marginBottom: 10 }}>
            Internal Linking Gaps ({gaps.length})
          </div>
          <div style={{ maxHeight: 200, overflowY: "auto" }}>
            {gaps.map((g, i) => (
              <div key={i} style={{ fontSize: 12, padding: "6px 0", borderBottom: `1px solid ${T.border}08` }}>
                <span style={{ fontWeight: 600 }}>{g.source_title || g.source_url}</span>
                {" → "}
                <span style={{ color: T.teal }}>{g.target_title || g.target_url}</span>
                <span style={{ color: T.textSoft }}> (anchor: {g.suggested_anchor || "auto"})</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Cluster-Based Internal Linking */}
      {clusters.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 10 }}>
            Cluster Internal Linking Map ({clusters.length} clusters)
          </div>
          <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 10 }}>
            Each content cluster should interlink its articles to the pillar page. Build hub-and-spoke link structures.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {clusters.slice(0, 10).map((c, i) => {
              const kws = c.keywords || []
              return (
                <div key={i} style={{ background: T.grayLight, borderRadius: 8, padding: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 4 }}>
                    {c.name}
                  </div>
                  <div style={{ fontSize: 10, color: T.teal, marginBottom: 6 }}>
                    Pillar → {c.blog_title}
                  </div>
                  <div style={{ fontSize: 10, color: T.textSoft }}>
                    {kws.slice(0, 4).map(k => k.keyword).join(" · ")}
                    {kws.length > 4 && ` +${kws.length - 4} more`}
                  </div>
                  <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
                    <Badge label={`${kws.length} kws`} color={T.purple} />
                    <Badge label={c.commercial_value || "medium"} color={c.commercial_value === "high" ? T.teal : T.amber} />
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Tracked Opportunities */}
      {opportunities.length > 0 && (
        <Card>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 10 }}>
            Tracked Opportunities ({opportunities.length})
          </div>
          <div style={{ maxHeight: 250, overflowY: "auto" }}>
            {opportunities.map((o, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "6px 0", borderBottom: `1px solid ${T.border}08` }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 500 }}>{o.prospect_url}</div>
                  <div style={{ fontSize: 11, color: T.textSoft }}>{o.strategy} → {o.target_page}</div>
                </div>
                <Badge label={o.status} color={o.status === "won" ? T.teal : o.status === "contacted" ? T.amber : T.gray} />
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

// ── Phase 7: Content Updates ─────────────────────────────────────────────────
function ContentUpdatesPhase({ projectId }) {
  const [showAuditSection, setShowAuditSection] = useState(false)
  const [publishedSet, setPublishedSet] = useState(new Set())

  // Keyword pillars brief — content plan
  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief
  const kwCtx = kwBrief?.context_json || {}
  const clusters = kwCtx.content_clusters || []
  const brandName = kwCtx.brand_name || ""

  const { data: audit, isLoading: loadingAudit } = useQuery({
    queryKey: ["si-audit", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/content-audit`),
    enabled: !!projectId && showAuditSection,
  })

  const { data: consolidation } = useQuery({
    queryKey: ["si-consolidation", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/content-consolidation`),
    enabled: !!projectId && showAuditSection, retry: false,
  })

  const updates = audit?.updates_needed || []
  const candidates = consolidation?.candidates || []
  const tierColor = (t) => ({ optimization: T.teal, upgrade: T.amber, rewrite: T.red }[t] || T.gray)
  const commercialColor = (v) => ({ high: T.teal, medium: T.amber, low: T.gray }[v] || T.gray)
  const togglePublished = (id) => setPublishedSet(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })

  return (
    <div>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Phase 7: Content Publishing Plan</h2>
      <p style={{ margin: "0 0 20px", fontSize: 13, color: T.textSoft }}>
        Content roadmap based on your keyword clusters. Track publishing progress and plan rewrites for existing content.
      </p>

      {/* ── Content publishing roadmap from clusters ── */}
      {clusters.length > 0 ? (
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: T.purpleDark }}>
              Content Publishing Roadmap · {clusters.length} articles
            </div>
            <div style={{ fontSize: 11, color: T.textSoft }}>
              {publishedSet.size} of {clusters.length} published
            </div>
          </div>

          {/* Progress bar */}
          <div style={{ height: 8, background: T.grayLight, borderRadius: 4, marginBottom: 16, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${clusters.length > 0 ? Math.round((publishedSet.size / clusters.length) * 100) : 0}%`,
              background: T.teal, borderRadius: 4, transition: "width .3s" }} />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
            {clusters.map((cluster, i) => {
              const done = publishedSet.has(i)
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 12,
                  padding: "10px 14px", borderRadius: 10, border: `1px solid ${done ? T.teal + "40" : T.border}`,
                  background: done ? T.tealLight : "#fff", cursor: "pointer" }}
                  onClick={() => togglePublished(i)}>
                  <div style={{ width: 22, height: 22, borderRadius: 5, flexShrink: 0,
                    border: `2px solid ${done ? T.teal : T.border}`,
                    background: done ? T.teal : "#fff",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    color: "#fff", fontSize: 13, fontWeight: 700 }}>
                    {done ? "✓" : ""}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: done ? 700 : 600,
                      color: done ? T.teal : T.text,
                      textDecoration: done ? "line-through" : "none" }}>
                      {cluster.blog_title}
                    </div>
                    <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>
                      {cluster.name} · {(cluster.keywords || []).length} keywords
                    </div>
                  </div>
                  <Badge label={`${cluster.commercial_value || "medium"} value`} color={commercialColor(cluster.commercial_value)} />
                </div>
              )
            })}
          </div>

          {/* Brand content note */}
          {brandName && (
            <Card style={{ background: T.purpleLight, border: `1px solid ${T.purple}30`, marginBottom: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 6 }}>
                Brand Content Plan — {brandName}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {[
                  `About ${brandName} page — who we are, our mission, authenticity`,
                  `${brandName} products page — full product range with keywords`,
                  `${brandName} reviews / testimonials page — social proof`,
                  `${brandName} wholesale / bulk orders page — B2B keywords`,
                  `Contact ${brandName} page — local SEO + contact info`,
                ].map((item, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, fontSize: 12, color: T.text }}>
                    <span style={{ color: T.purple, flexShrink: 0 }}>☐</span>
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      ) : (
        <Card style={{ marginBottom: 20, padding: 24, textAlign: "center", background: T.grayLight }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>♻️</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 4 }}>No content plan yet</div>
          <div style={{ fontSize: 12, color: T.textSoft }}>Complete the Keyword Pipeline and click "Send to Strategy Hub" to generate your content roadmap.</div>
        </Card>
      )}

      {/* ── Existing content audit (collapsible) ── */}
      <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
        <button onClick={() => setShowAuditSection(!showAuditSection)} style={{
          background: "none", border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600,
          color: T.purpleDark, marginBottom: 12, display: "flex", alignItems: "center", gap: 6,
        }}>
          {showAuditSection ? "▾" : "▸"} Existing Content Audit & Consolidation
        </button>

        {showAuditSection && (
          <div>
            {loadingAudit && <div style={{ fontSize: 13, color: T.textSoft }}>Auditing content...</div>}

            {audit?.summary && (
              <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
                {["optimization", "upgrade", "rewrite"].map(tier => (
                  <Card key={tier} style={{ flex: 1, borderLeft: `3px solid ${tierColor(tier)}` }}>
                    <div style={{ fontSize: 20, fontWeight: 700, color: T.text }}>{audit.summary[tier] || 0}</div>
                    <div style={{ fontSize: 11, color: T.textSoft, textTransform: "capitalize" }}>{tier}</div>
                  </Card>
                ))}
                <Card style={{ flex: 1, borderLeft: `3px solid ${T.gray}` }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: T.text }}>{audit.summary?.total || 0}</div>
                  <div style={{ fontSize: 11, color: T.textSoft }}>Total Pages</div>
                </Card>
              </div>
            )}

            {updates.length > 0 && (
              <Card style={{ marginBottom: 16 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 10 }}>
                  Updates Needed ({updates.length})
                </div>
                <div style={{ maxHeight: 350, overflowY: "auto" }}>
                  {updates.map((u, i) => (
                    <div key={i} style={{
                      display: "grid", gridTemplateColumns: "2fr 100px 1fr",
                      alignItems: "center", padding: "8px 0",
                      borderBottom: `1px solid ${T.border}08`,
                    }}>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 600 }}>{u.title || u.url}</div>
                        {u.url && u.title && <div style={{ fontSize: 10, color: T.textSoft }}>{u.url}</div>}
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <Badge label={u.update_type} color={tierColor(u.update_type)} />
                      </div>
                      <div style={{ fontSize: 11, color: T.textSoft }}>
                        {(u.actions || []).slice(0, 2).join(" · ")}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {candidates.length > 0 && (
              <Card>
                <div style={{ fontWeight: 700, fontSize: 13, color: T.amber, marginBottom: 10 }}>
                  Consolidation Candidates ({candidates.length})
                </div>
                <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 10 }}>
                  These pages overlap and should be merged for stronger ranking signals.
                </div>
                {candidates.map((c, i) => (
                  <div key={i} style={{ padding: "8px 0", borderBottom: `1px solid ${T.border}08` }}>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>Group: {c.keyword}</div>
                    <div style={{ marginTop: 4 }}>
                      {(c.pages || []).map((p, j) => (
                        <div key={j} style={{ fontSize: 11, color: T.textSoft, marginLeft: 12 }}>• {p}</div>
                      ))}
                    </div>
                  </div>
                ))}
              </Card>
            )}

            {!loadingAudit && updates.length === 0 && (
              <div style={{ fontSize: 12, color: T.textSoft, padding: "10px 0" }}>
                No existing content needing updates yet. Publish your cluster articles first!
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  2-YEAR STRATEGY ROADMAP PHASE — AI-generated roadmap with strategy input
// ═══════════════════════════════════════════════════════════════════════════════

function RoadmapPhase({ projectId, setPage }) {
  const qc = useQueryClient()
  const [generating, setGenerating] = useState(false)
  const [logs, setLogs] = useState([])
  const [genError, setGenError] = useState("")
  const [showGoals, setShowGoals] = useState(false)
  const [goalForm, setGoalForm] = useState({ goal_type: "traffic", target_metric: 10, timeframe_months: 24, business_outcome: "", business_type: "ecommerce" })

  // Keyword brief for context
  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief
  const kwCtx = kwBrief?.context_json || {}
  const clusters = kwCtx.content_clusters || []
  const allKws = Object.values(kwBrief?.keywords_json || {}).flat()

  // Latest strategy result
  const { data: latestStrategy, isLoading, refetch } = useQuery({
    queryKey: ["latest-strategy-hub", projectId],
    queryFn: async () => {
      const r = await fetch(`${API}/api/strategy/${projectId}/latest`, { headers: authHeaders() })
      if (!r.ok) return null
      const d = await r.json()
      return d?.meta?.has_data ? d : null
    },
    enabled: !!projectId, retry: false,
  })
  const strategy = latestStrategy?.strategy || latestStrategy?.result_json?.strategy || null

  // Goals
  const setGoals = useMutation({
    mutationFn: (body) => apiFetch(`/api/si/${projectId}/goals`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => { qc.invalidateQueries(["si-goal-progress", projectId]); setShowGoals(false) },
  })
  const { data: progress } = useQuery({
    queryKey: ["si-goal-progress", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/goals/progress`),
    enabled: !!projectId, retry: false,
  })

  const set = (k, v) => setGoalForm(f => ({ ...f, [k]: v }))
  const inStyle = { width: "100%", padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box" }

  const startGeneration = async () => {
    setGenerating(true); setLogs([]); setGenError("")
    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/generate-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({}),
      })
      if (!res.ok) { const d = await res.json().catch(() => ({})); setGenError(d?.detail || `HTTP ${res.status}`); setGenerating(false); return }
      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ""
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split("\n"); buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const ev = JSON.parse(line.slice(6).trim())
            if (ev.type === "log") setLogs(prev => [...prev.slice(-199), { msg: ev.msg, level: ev.level }])
            else if (ev.type === "complete") { setGenerating(false); refetch() }
            else if (ev.type === "error") { setGenError(ev.msg || "Failed"); setGenerating(false) }
          } catch {}
        }
      }
      setGenerating(false); refetch()
    } catch (e) { setGenError(String(e)); setGenerating(false) }
  }

  const levelColor = l => l === "success" ? T.teal : l === "error" ? T.red : l === "warn" ? T.amber : "#0f0"
  const confColor = c => c >= 80 ? T.teal : c >= 50 ? T.amber : T.red

  // Derive roadmap quarters from strategy
  const contentCalendar = strategy?.content_calendar || []
  const quickWins = strategy?.quick_wins || []
  const pillarStrategy = strategy?.pillar_strategy || []
  const competitorGaps = strategy?.competitor_gaps || []
  const kpis = strategy?.kpis || []
  const aeoTactics = strategy?.aeo_tactics || []

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>2-Year SEO Strategy Roadmap</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSoft }}>
            AI-powered strategy targeting Top 5 in Google & AI search. Based on your keywords, clusters, and business goals.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn small variant="outline" onClick={() => setShowGoals(!showGoals)}>
            {showGoals ? "Hide Goals" : "Set Goals"}
          </Btn>
          <Btn small variant="primary" onClick={startGeneration} disabled={generating}>
            {generating ? "Generating..." : strategy ? "Regenerate Roadmap" : "Generate 2-Year Roadmap"}
          </Btn>
        </div>
      </div>

      {/* Strategy Input — Goals */}
      {showGoals && (
        <Card style={{ marginBottom: 16, border: `1px solid ${T.purple}33` }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.purpleDark, marginBottom: 12 }}>Strategy Goals & Input</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Business Outcome (2 years)</label>
              <input value={goalForm.business_outcome} onChange={e => set("business_outcome", e.target.value)}
                placeholder="e.g., Become #1 online Kerala spices seller with 10K organic visits/month" style={inStyle} />
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Business Type</label>
              <select value={goalForm.business_type} onChange={e => set("business_type", e.target.value)} style={inStyle}>
                <option value="ecommerce">E-commerce</option>
                <option value="saas">SaaS</option>
                <option value="local">Local Business</option>
                <option value="content">Content / Publisher</option>
                <option value="agency">Agency / Services</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Goal Type</label>
              <select value={goalForm.goal_type} onChange={e => set("goal_type", e.target.value)} style={inStyle}>
                <option value="traffic">Organic Traffic Growth</option>
                <option value="leads">Lead Generation</option>
                <option value="revenue">Revenue from SEO</option>
                <option value="authority">Domain Authority</option>
              </select>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Growth Target (%)</label>
                <input type="number" value={goalForm.target_metric} onChange={e => set("target_metric", Number(e.target.value))} style={inStyle} />
              </div>
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }}>Months</label>
                <input type="number" value={goalForm.timeframe_months} onChange={e => set("timeframe_months", Number(e.target.value))} style={inStyle} />
              </div>
            </div>
          </div>
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <Btn small onClick={() => setGoals.mutate(goalForm)} loading={setGoals.isPending}>Save Goals</Btn>
            {setGoals.isSuccess && <span style={{ fontSize: 11, color: T.teal, fontWeight: 600, alignSelf: "center" }}>Saved</span>}
          </div>
        </Card>
      )}

      {/* Context summary from keyword brief */}
      {kwBrief && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8, marginBottom: 16 }}>
          {[
            { label: "Keywords", val: allKws.length, color: T.purpleDark },
            { label: "Clusters", val: clusters.length, color: T.teal },
            { label: "Brand", val: kwCtx.brand_name || "—", color: kwCtx.brand_name ? T.purpleDark : T.gray },
            { label: "AI Keywords", val: kwCtx.ai_suggested_count || 0, color: T.amber },
            { label: "Goal", val: progress?.goal ? "Set" : "Not set", color: progress?.goal ? T.teal : T.gray },
          ].map((s, i) => (
            <Card key={i} style={{ textAlign: "center", padding: "8px 6px" }}>
              <div style={{ fontSize: typeof s.val === "number" ? 18 : 12, fontWeight: 700, color: s.color }}>{s.val}</div>
              <div style={{ fontSize: 9, color: T.textSoft, marginTop: 2 }}>{s.label}</div>
            </Card>
          ))}
        </div>
      )}

      {/* Generation console */}
      {(generating || logs.length > 0) && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            {generating && <div style={{ width: 8, height: 8, borderRadius: "50%", background: T.purple, animation: "pulse 1.2s infinite" }} />}
            <div style={{ fontSize: 12, fontWeight: 600 }}>{generating ? "Generating roadmap..." : "Generation complete"}</div>
          </div>
          <div style={{ background: "#0d0d0d", borderRadius: 8, padding: 10, height: 130,
            overflowY: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.6 }}>
            {logs.map((l, i) => <div key={i} style={{ color: levelColor(l.level) }}>→ {l.msg}</div>)}
          </div>
        </Card>
      )}
      {genError && <Card style={{ marginBottom: 16, background: "#FEF2F2", border: "1px solid #FCA5A5" }}>
        <div style={{ fontSize: 12, color: T.red }}>Error: {genError}</div>
      </Card>}

      {/* No strategy yet */}
      {!strategy && !generating && (
        <Card style={{ textAlign: "center", padding: 40 }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🗺️</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: T.text, marginBottom: 6 }}>No strategy roadmap yet</div>
          <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 16 }}>
            {kwBrief
              ? "Your keyword data is ready. Click 'Generate 2-Year Roadmap' to create an AI strategy."
              : "Complete the Keyword Pipeline first, then click 'Generate 2-Year Roadmap'."}
          </div>
          <Btn variant="primary" onClick={startGeneration}>Generate 2-Year Roadmap</Btn>
        </Card>
      )}

      {/* Strategy Roadmap */}
      {strategy && !generating && (
        <div>
          {/* Executive Summary */}
          <div style={{ display: "flex", gap: 14, marginBottom: 14 }}>
            <Card style={{ flex: 1, background: T.purpleLight, border: `1px solid ${T.purple}33` }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 6 }}>EXECUTIVE SUMMARY</div>
              <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6 }}>
                {strategy.executive_summary || "Strategy generated successfully."}
              </div>
            </Card>
            {strategy.strategy_confidence > 0 && (
              <div style={{ width: 100, flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                background: confColor(strategy.strategy_confidence) + "18", border: `1px solid ${confColor(strategy.strategy_confidence)}33`,
                borderRadius: 12, padding: 14 }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: confColor(strategy.strategy_confidence) }}>
                  {strategy.strategy_confidence}%
                </div>
                <div style={{ fontSize: 10, color: confColor(strategy.strategy_confidence) }}>Confidence</div>
              </div>
            )}
          </div>

          {/* SEO Goals */}
          {strategy.seo_goals && (
            <Card style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>RANKING GOALS (2 YEARS)</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
                {[
                  { icon: "🔍", label: "Google Target", val: strategy.seo_goals.google_target },
                  { icon: "🤖", label: "AI Search", val: strategy.seo_goals.ai_search_target },
                  { icon: "📈", label: "Monthly Traffic", val: strategy.seo_goals.monthly_traffic_target },
                ].map((g, i) => (
                  <div key={i} style={{ background: T.grayLight, borderRadius: 8, padding: 10, textAlign: "center" }}>
                    <div style={{ fontSize: 20, marginBottom: 4 }}>{g.icon}</div>
                    <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 4 }}>{g.label}</div>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>{g.val || "—"}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
            {/* Pillar Strategy */}
            {pillarStrategy.length > 0 && (
              <Card>
                <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>PILLAR STRATEGY</div>
                {pillarStrategy.slice(0, 8).map((p, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "8px 10px", background: T.grayLight, borderRadius: 8, marginBottom: 6 }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600 }}>{p.pillar}</div>
                      <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>
                        {p.content_type} · {p.monthly_searches || "??"} searches/mo
                        {p.ai_snippet_opportunity && " · 🤖 AI snippet"}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 14, fontWeight: 700, color: (p.target_rank || 99) <= 3 ? T.teal : T.amber }}>
                        #{p.target_rank}
                      </div>
                      <div style={{ fontSize: 10, color: p.difficulty === "low" ? T.teal : p.difficulty === "high" ? T.red : T.amber }}>
                        {p.difficulty}
                      </div>
                    </div>
                  </div>
                ))}
              </Card>
            )}

            {/* Quick Wins + AEO */}
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {quickWins.length > 0 && (
                <Card>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 8 }}>QUICK WINS (MONTH 1-3)</div>
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {quickWins.map((w, i) => <li key={i} style={{ fontSize: 12, marginBottom: 6, lineHeight: 1.4 }}>{w}</li>)}
                  </ul>
                </Card>
              )}
              {aeoTactics.length > 0 && (
                <Card>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>AEO TACTICS (AI Search)</div>
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {aeoTactics.slice(0, 4).map((t, i) => <li key={i} style={{ fontSize: 12, marginBottom: 6, lineHeight: 1.4 }}>🤖 {t}</li>)}
                  </ul>
                </Card>
              )}
            </div>
          </div>

          {/* Content Calendar / Quarterly Roadmap */}
          {contentCalendar.length > 0 && (
            <Card style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>
                QUARTERLY CONTENT ROADMAP · {strategy.recommended_posting_frequency || "2+ articles/week"}
              </div>
              <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 4 }}>
                {contentCalendar.slice(0, 8).map((month, i) => (
                  <div key={i} style={{ minWidth: 200, background: T.grayLight, borderRadius: 8, padding: 10, flexShrink: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>
                      {month.month} — {month.focus_pillar}
                    </div>
                    {(month.articles || []).slice(0, 3).map((a, j) => (
                      <div key={j} style={{ background: "#fff", borderRadius: 6, padding: "6px 8px", marginBottom: 4,
                        fontSize: 11, border: `0.5px solid ${T.border}` }}>
                        <div style={{ fontWeight: 600, marginBottom: 2 }}>{a.title}</div>
                        <div style={{ color: T.textSoft }}>{a.type} · {a.word_count || 1500} words</div>
                        {a.target_keyword && <div style={{ color: T.purple, fontSize: 10 }}>{a.target_keyword}</div>}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Competitor Gaps + KPIs */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {competitorGaps.length > 0 && (
              <Card>
                <div style={{ fontSize: 12, fontWeight: 700, color: T.amber, marginBottom: 8 }}>COMPETITOR GAPS</div>
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {competitorGaps.map((g, i) => <li key={i} style={{ fontSize: 12, marginBottom: 5 }}>⚡ {g}</li>)}
                </ul>
              </Card>
            )}
            {kpis.length > 0 && (
              <Card>
                <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>2-YEAR KPIs</div>
                {kpis.map((kpi, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 12 }}>
                    <div style={{ fontWeight: 500 }}>{kpi.metric}</div>
                    <div style={{ color: T.teal, fontWeight: 600 }}>{kpi.target}</div>
                  </div>
                ))}
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  CONTENT CREATION PHASE — Generate articles from blog cluster briefs
// ═══════════════════════════════════════════════════════════════════════════════

function ContentCreationPhase({ projectId }) {
  const qc = useQueryClient()
  const [genKeyword, setGenKeyword] = useState("")
  const [selectedArticle, setSelectedArticle] = useState(null)

  // Blog clusters from keyword brief
  const { data: kwBriefData } = useQuery({
    queryKey: ["kw-strategy-brief", projectId],
    queryFn: () => apiFetch(`/api/ki/${projectId}/keyword-strategy-brief`),
    enabled: !!projectId, retry: false, staleTime: 60_000,
  })
  const kwBrief = kwBriefData?.brief
  const clusters = kwBrief?.context_json?.content_clusters || []

  // Existing articles
  const { data: articles, isLoading: loadingArticles } = useQuery({
    queryKey: ["articles", projectId],
    queryFn: () => apiFetch(`/api/projects/${projectId}/content`),
    enabled: !!projectId, retry: false,
  })
  const articleList = articles || []

  // Generate article
  const generateMut = useMutation({
    mutationFn: (keyword) => apiFetch("/api/content/generate", {
      method: "POST", body: JSON.stringify({ keyword, project_id: projectId }),
    }),
    onSuccess: () => { qc.invalidateQueries(["articles", projectId]); setGenKeyword("") },
  })

  // Approve article
  const approveMut = useMutation({
    mutationFn: (id) => apiFetch(`/api/content/${id}/approve`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries(["articles", projectId]),
  })

  const retryMut = useMutation({
    mutationFn: (id) => apiFetch(`/api/content/${id}/retry`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries(["articles", projectId]),
  })

  const statusColor = s => ({ draft: T.gray, generating: T.amber, review: T.purple, approved: T.teal, published: T.purpleDark, failed: T.red }[s] || T.gray)
  const statusCounts = articleList.reduce((acc, a) => { acc[a.status] = (acc[a.status] || 0) + 1; return acc }, {})

  return (
    <div>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Content Creation</h2>
      <p style={{ margin: "0 0 20px", fontSize: 13, color: T.textSoft }}>
        Generate SEO-optimized articles from your keyword clusters. Each cluster is a ready-to-write content brief.
      </p>

      {/* Article lifecycle strip */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {["draft", "generating", "review", "approved", "published", "failed"].map(s => (
          <div key={s} style={{ flex: 1, textAlign: "center", padding: "8px 4px", borderRadius: 8,
            background: statusColor(s) + "12", border: `1px solid ${statusColor(s)}25` }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: statusColor(s) }}>{statusCounts[s] || 0}</div>
            <div style={{ fontSize: 9, color: T.textSoft, textTransform: "capitalize", marginTop: 2 }}>{s}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Left: Generate from clusters */}
        <div>
          {/* Quick generate */}
          <Card style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>Generate Article</div>
            <div style={{ display: "flex", gap: 8 }}>
              <input value={genKeyword} onChange={e => setGenKeyword(e.target.value)}
                placeholder="Enter keyword or select from clusters below..."
                style={{ flex: 1, padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box" }} />
              <Btn small onClick={() => genKeyword.trim() && generateMut.mutate(genKeyword.trim())}
                loading={generateMut.isPending} disabled={!genKeyword.trim()}>
                Generate
              </Btn>
            </div>
            {generateMut.isError && <div style={{ color: T.red, fontSize: 11, marginTop: 6 }}>{generateMut.error.message}</div>}
            {generateMut.isSuccess && <div style={{ color: T.teal, fontSize: 11, marginTop: 6 }}>Article generation started!</div>}
          </Card>

          {/* Cluster briefs */}
          {clusters.length > 0 && (
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>
                Content Briefs from Clusters ({clusters.length})
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {clusters.map((c, i) => {
                  const primaryKw = (c.keywords || [])[0]?.keyword || c.name
                  const alreadyGenerated = articleList.some(a =>
                    a.keyword?.toLowerCase() === primaryKw.toLowerCase()
                  )
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 10,
                      padding: "8px 10px", borderRadius: 8, background: alreadyGenerated ? T.tealLight : T.grayLight,
                      border: `1px solid ${alreadyGenerated ? T.teal + "30" : T.border}` }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: T.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {c.blog_title}
                        </div>
                        <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>
                          {c.name} · {(c.keywords || []).length} keywords · {c.commercial_value}
                        </div>
                      </div>
                      {alreadyGenerated ? (
                        <Badge label="Generated" color={T.teal} />
                      ) : (
                        <Btn small variant="outline" onClick={() => {
                          setGenKeyword(primaryKw)
                          generateMut.mutate(primaryKw)
                        }} loading={generateMut.isPending && genKeyword === primaryKw}>
                          Create
                        </Btn>
                      )}
                    </div>
                  )
                })}
              </div>
            </Card>
          )}
        </div>

        {/* Right: Article list */}
        <div>
          <Card>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>
              Articles ({articleList.length})
            </div>
            {loadingArticles ? (
              <div style={{ fontSize: 12, color: T.textSoft }}>Loading articles...</div>
            ) : articleList.length === 0 ? (
              <div style={{ textAlign: "center", padding: 24, color: T.textSoft }}>
                <div style={{ fontSize: 24, marginBottom: 6 }}>✍️</div>
                <div style={{ fontSize: 12 }}>No articles yet. Generate from a cluster brief or keyword.</div>
              </div>
            ) : (
              <div style={{ maxHeight: 500, overflowY: "auto" }}>
                {articleList.map((a, i) => (
                  <div key={a.id || i} style={{ padding: "8px 0",
                    borderBottom: i < articleList.length - 1 ? `1px solid ${T.border}08` : "none",
                    cursor: "pointer", background: selectedArticle === a.id ? T.purpleLight : "transparent",
                    borderRadius: 6 }}
                    onClick={() => setSelectedArticle(selectedArticle === a.id ? null : a.id)}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{a.title || a.keyword}</div>
                      <Badge label={a.status} color={statusColor(a.status)} />
                    </div>
                    <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>
                      {a.keyword} · {a.word_count || 0} words
                      {a.seo_score > 0 && ` · SEO ${a.seo_score}`}
                    </div>
                    {selectedArticle === a.id && (
                      <div style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${T.border}` }}>
                        <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
                          {a.seo_score > 0 && <Badge label={`SEO ${a.seo_score}`} color={a.seo_score >= 80 ? T.teal : T.amber} />}
                          {a.eeat_score > 0 && <Badge label={`E-E-A-T ${a.eeat_score}`} color={a.eeat_score >= 80 ? T.teal : T.amber} />}
                          {a.geo_score > 0 && <Badge label={`GEO ${a.geo_score}`} color={a.geo_score >= 80 ? T.teal : T.amber} />}
                        </div>
                        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                          {a.status === "review" && (
                            <Btn small variant="teal" onClick={(e) => { e.stopPropagation(); approveMut.mutate(a.id) }}
                              loading={approveMut.isPending}>Approve</Btn>
                          )}
                          {a.status === "failed" && (
                            <Btn small variant="outline" onClick={(e) => { e.stopPropagation(); retryMut.mutate(a.id) }}
                              loading={retryMut.isPending}>🔄 Retry</Btn>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  STRATEGY RESULTS PHASE — Shows AI-generated strategy plan
// ═══════════════════════════════════════════════════════════════════════════════

function StrategyResultsPhase({ projectId, setPage }) {
  const qc = useQueryClient()
  const [generating, setGenerating] = useState(false)
  const [logs, setLogs] = useState([])
  const [genError, setGenError] = useState("")
  const scrollRef = { current: null }

  const { data: latestStrategy, isLoading, refetch } = useQuery({
    queryKey: ["latest-strategy-hub", projectId],
    queryFn: async () => {
      const r = await fetch(`${API}/api/strategy/${projectId}/latest`, { headers: authHeaders() })
      if (!r.ok) return null
      const d = await r.json()
      return d?.meta?.has_data ? d : null
    },
    enabled: !!projectId,
    retry: false,
  })

  const strategy = latestStrategy?.strategy || latestStrategy?.result_json?.strategy || null
  const meta = latestStrategy?.meta || {}

  const startGeneration = async () => {
    setGenerating(true)
    setLogs([])
    setGenError("")

    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/generate-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({}),
      })

      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        setGenError(d?.detail || `HTTP ${res.status}`)
        setGenerating(false)
        return
      }

      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ""
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          try {
            const ev = JSON.parse(raw)
            if (ev.type === "log") {
              setLogs(prev => [...prev.slice(-199), { msg: ev.msg, level: ev.level }])
            } else if (ev.type === "complete") {
              setGenerating(false)
              refetch()
            } else if (ev.type === "error") {
              setGenError(ev.msg || "Generation failed")
              setGenerating(false)
            }
          } catch { /* ignore */ }
        }
      }
      setGenerating(false)
      refetch()
    } catch (e) {
      setGenError(String(e))
      setGenerating(false)
    }
  }

  const levelColor = l => l === "success" ? T.teal : l === "error" ? T.red : l === "warn" ? T.amber : "#0f0"
  const confColor = c => c >= 80 ? T.teal : c >= 50 ? T.amber : T.red

  if (isLoading) return <div style={{ color: T.gray, padding: 20 }}>Loading strategy...</div>

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>Strategy Results</h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSoft }}>
            AI-generated SEO/AEO strategy — targeting Top 5 in Google & AI search
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {setPage && (
            <Btn small variant="outline" onClick={() => setPage("strategy")}>Edit Profile</Btn>
          )}
          <Btn small variant="primary" onClick={startGeneration} disabled={generating}>
            {generating ? "Generating..." : strategy ? "Regenerate" : "Generate Strategy"}
          </Btn>
        </div>
      </div>

      {/* Generation console */}
      {(generating || logs.length > 0) && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            {generating && <div style={{ width: 8, height: 8, borderRadius: "50%", background: T.purple, animation: "pulse 1.2s infinite" }} />}
            <div style={{ fontSize: 12, fontWeight: 600 }}>{generating ? "Generating strategy..." : "Generation complete"}</div>
          </div>
          <div ref={el => scrollRef.current = el} style={{
            background: "#0d0d0d", borderRadius: 8, padding: 10, height: 160,
            overflowY: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.6,
          }}>
            {logs.map((l, i) => <div key={i} style={{ color: levelColor(l.level) }}>→ {l.msg}</div>)}
          </div>
        </Card>
      )}

      {genError && (
        <Card style={{ marginBottom: 16, background: "#FEF2F2", border: "1px solid #FCA5A5" }}>
          <div style={{ fontSize: 12, color: T.red }}>Error: {genError}</div>
        </Card>
      )}

      {/* No strategy yet */}
      {!strategy && !generating && (
        <Card style={{ textAlign: "center", padding: 40 }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>📊</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: T.text, marginBottom: 6 }}>No strategy generated yet</div>
          <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 16 }}>
            {setPage
              ? "Set up your business profile first, then generate an AI strategy."
              : "Click 'Generate Strategy' to create your SEO/AEO plan."}
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
            {setPage && <Btn variant="outline" onClick={() => setPage("strategy")}>Setup Profile</Btn>}
            <Btn variant="primary" onClick={startGeneration}>Generate Strategy</Btn>
          </div>
        </Card>
      )}

      {/* Strategy results display */}
      {strategy && !generating && (
        <div>
          {/* Confidence + Executive Summary */}
          <div style={{ display: "flex", gap: 14, marginBottom: 14 }}>
            <Card style={{ flex: 1, background: T.purpleLight, border: `1px solid ${T.purple}33` }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 6 }}>EXECUTIVE SUMMARY</div>
              <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6 }}>
                {strategy.executive_summary || "Strategy generated successfully."}
              </div>
            </Card>
            {strategy.strategy_confidence > 0 && (
              <div style={{ width: 100, flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                background: confColor(strategy.strategy_confidence) + "18", border: `1px solid ${confColor(strategy.strategy_confidence)}33`,
                borderRadius: 12, padding: 14 }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: confColor(strategy.strategy_confidence) }}>
                  {strategy.strategy_confidence}%
                </div>
                <div style={{ fontSize: 10, color: confColor(strategy.strategy_confidence) }}>AI Confidence</div>
              </div>
            )}
          </div>

          {/* SEO Goals */}
          {strategy.seo_goals && (
            <Card style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>RANKING GOALS</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
                {[
                  { icon: "🔍", label: "Google Target", val: strategy.seo_goals.google_target },
                  { icon: "🤖", label: "AI Search Target", val: strategy.seo_goals.ai_search_target },
                  { icon: "📈", label: "Monthly Traffic", val: strategy.seo_goals.monthly_traffic_target },
                ].map((g, i) => (
                  <div key={i} style={{ background: T.grayLight, borderRadius: 8, padding: 10, textAlign: "center" }}>
                    <div style={{ fontSize: 20, marginBottom: 4 }}>{g.icon}</div>
                    <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 4 }}>{g.label}</div>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>{g.val || "—"}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
            {/* Pillar Strategy */}
            {strategy.pillar_strategy?.length > 0 && (
              <Card>
                <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>PILLAR STRATEGY</div>
                {strategy.pillar_strategy.slice(0, 8).map((p, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "8px 10px", background: T.grayLight, borderRadius: 8, marginBottom: 6 }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600 }}>{p.pillar}</div>
                      <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>
                        {p.content_type} · {p.monthly_searches || "??"} searches/mo
                        {p.ai_snippet_opportunity && " · 🤖 AI snippet"}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 14, fontWeight: 700, color: (p.target_rank || 99) <= 3 ? T.teal : T.amber }}>
                        #{p.target_rank}
                      </div>
                      <div style={{ fontSize: 10, color: p.difficulty === "low" ? T.teal : p.difficulty === "high" ? T.red : T.amber }}>
                        {p.difficulty}
                      </div>
                    </div>
                  </div>
                ))}
              </Card>
            )}

            {/* Quick Wins + AEO */}
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {strategy.quick_wins?.length > 0 && (
                <Card>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 8 }}>QUICK WINS</div>
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {strategy.quick_wins.map((w, i) => (
                      <li key={i} style={{ fontSize: 12, marginBottom: 6, lineHeight: 1.4 }}>{w}</li>
                    ))}
                  </ul>
                </Card>
              )}
              {strategy.aeo_tactics?.length > 0 && (
                <Card>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>AEO TACTICS (AI Search)</div>
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {strategy.aeo_tactics.slice(0, 4).map((t, i) => (
                      <li key={i} style={{ fontSize: 12, marginBottom: 6, lineHeight: 1.4 }}>🤖 {t}</li>
                    ))}
                  </ul>
                </Card>
              )}
            </div>
          </div>

          {/* Content Calendar */}
          {strategy.content_calendar?.length > 0 && (
            <Card style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 10 }}>
                CONTENT CALENDAR · {strategy.recommended_posting_frequency || "2+ articles/week"}
              </div>
              <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 4 }}>
                {strategy.content_calendar.slice(0, 4).map((month, i) => (
                  <div key={i} style={{ minWidth: 200, background: T.grayLight, borderRadius: 8, padding: 10, flexShrink: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>
                      {month.month} — {month.focus_pillar}
                    </div>
                    {(month.articles || []).slice(0, 3).map((a, j) => (
                      <div key={j} style={{ background: "#fff", borderRadius: 6, padding: "6px 8px", marginBottom: 4,
                        fontSize: 11, border: `0.5px solid ${T.border}` }}>
                        <div style={{ fontWeight: 600, marginBottom: 2 }}>{a.title}</div>
                        <div style={{ color: T.textSoft }}>{a.type} · {a.word_count || 1500} words</div>
                        {a.target_keyword && <div style={{ color: T.purple, fontSize: 10 }}>{a.target_keyword}</div>}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Competitor Gaps + KPIs */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {strategy.competitor_gaps?.length > 0 && (
              <Card>
                <div style={{ fontSize: 12, fontWeight: 700, color: T.amber, marginBottom: 8 }}>COMPETITOR GAPS</div>
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {strategy.competitor_gaps.map((g, i) => (
                    <li key={i} style={{ fontSize: 12, marginBottom: 5 }}>⚡ {g}</li>
                  ))}
                </ul>
              </Card>
            )}
            {strategy.kpis?.length > 0 && (
              <Card>
                <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>KPIs TO TRACK</div>
                {strategy.kpis.map((kpi, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 12 }}>
                    <div style={{ fontWeight: 500 }}>{kpi.metric}</div>
                    <div style={{ color: T.teal, fontWeight: 600 }}>{kpi.target}</div>
                  </div>
                ))}
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  BLUEPRINT ENGINE PHASE — Strategy V2 blueprint generation with live console
// ═══════════════════════════════════════════════════════════════════════════════

const ANGLE_COLORS_BP = {
  informational: { bg: "#dbeafe", text: "#1d4ed8", label: "Informational" },
  transactional:  { bg: "#dcfce7", text: "#15803d", label: "Transactional" },
  commercial:     { bg: "#f3e8ff", text: "#7e22ce", label: "Commercial" },
  navigational:   { bg: "#fef9c3", text: "#854d0e", label: "Navigational" },
  comparison:     { bg: "#fee2e2", text: "#b91c1c", label: "Comparison" },
  listicle:       { bg: "#ffedd5", text: "#9a3412", label: "Listicle" },
}

function KwPhaseRow({ kw, state }) {
  const phase = state?.phase || "pending"
  const isDone   = phase === "done"
  const isActive = phase === "blueprints" || phase === "angles" || phase === "qa"
  const isPending = phase === "pending" || phase === "classify"

  const phaseMeta = {
    pending:    { color: "#9ca3af", label: "Pending",           icon: "·" },
    classify:   { color: "#2563eb", label: "Classifying…",      icon: "⟳" },
    angles:     { color: "#7c3aed", label: "Generating angles…", icon: "⟳" },
    blueprints: { color: "#0284c7",
                  label: state?.blueprintsDone > 0
                    ? `Blueprints ${state.blueprintsDone}/${state.blueprintsTotal || "?"}`
                    : "Building blueprints…",
                  icon: "⟳" },
    qa:         { color: "#d97706", label: "QA scoring…",        icon: "⟳" },
    done:       { color: "#16a34a",
                  label: `✓ ${state?.blueprintsDone || 0} blueprint${state?.blueprintsDone !== 1 ? "s" : ""}${state?.avgScore ? ` · avg ${state.avgScore}` : ""}`,
                  icon: "✓" },
  }

  const meta = phaseMeta[phase] || phaseMeta.pending
  const fillPct = isDone ? 100
    : isActive && state?.blueprintsTotal > 0
      ? Math.round((state.blueprintsDone / state.blueprintsTotal) * 100)
      : isActive ? 40
      : 0

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "7px 12px", borderRadius: 8, background: isDone ? "#f0fdf4" : isActive ? "#eff6ff" : "#f9fafb",
      border: `1px solid ${isDone ? "#bbf7d0" : isActive ? "#bfdbfe" : "#e5e7eb"}`,
    }}>
      <span style={{ fontWeight: 700, fontSize: 13, color: meta.color, width: 14, textAlign: "center" }}>
        {meta.icon}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3, gap: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#111827", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{kw}</span>
          <span style={{ fontSize: 11, color: meta.color, whiteSpace: "nowrap", flexShrink: 0 }}>{meta.label}</span>
        </div>
        <div style={{ height: 4, background: "#e5e7eb", borderRadius: 2, overflow: "hidden" }}>
          <div style={{
            height: "100%", borderRadius: 2,
            background: isDone ? "#16a34a" : isActive ? "#3b82f6" : "#e5e7eb",
            width: `${fillPct}%`,
            transition: "width 0.4s ease",
          }} />
        </div>
      </div>
      {state?.intent && (
        <span style={{ fontSize: 10, color: "#6b7280", flexShrink: 0, background: "#f3f4f6", padding: "1px 6px", borderRadius: 8 }}>
          {state.intent}
        </span>
      )}
    </div>
  )
}

function SSELogPanel({ events }) {
  const bottomRef = useRef(null)
  useEffect(() => {
    setTimeout(() => {
      if (bottomRef.current) bottomRef.current.scrollIntoView({ behavior: "smooth" })
    }, 0)
  }, [events.length])
  
  // Determine text color based on event type
  const getEventColor = (evt) => {
    if (evt.step === "error") return "#ff7b72"
    if (evt.step === "done" || evt.step === "all_done" || evt.step === "keyword_done") return "#3fb950"
    if (evt.step === "fix" || evt.step === "fix_done") return "#ffa657"
    if (evt.step?.startsWith("blueprint_")) return "#58a6ff"
    if (evt.step === "qa" && evt.status === "done") return "#3fb950"
    return "#c9d1d9"
  }
  
  return (
    <div style={{
      background: "#0d1117", borderRadius: 8, padding: "12px",
      fontFamily: "'SF Mono', 'Fira Code', monospace", fontSize: 11, lineHeight: 1.8,
      maxHeight: 380, overflowY: "auto", color: "#8b949e",
      border: "1px solid #30363d",
      marginTop: 12
    }}>
      {events.length === 0 ? (
        <span style={{ color: "#555" }}>⏳ Waiting for generation to start…</span>
      ) : (
        <div>
          {events.map((e, i) => (
            <div key={i} style={{ display: "flex", gap: 10 }}>
              <span style={{ color: "#484f58", minWidth: 32, textAlign: "right", userSelect: "none", flexShrink: 0 }}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <span style={{
                color: getEventColor(e),
                flex: 1,
                wordBreak: "break-word",
                whiteSpace: "pre-wrap"
              }}>
                {e.msg || JSON.stringify(e).slice(0, 100)}
              </span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}

function FilterChipBP({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding: "4px 12px", borderRadius: 999, fontSize: 12, cursor: "pointer",
      border: "1px solid " + (active ? "#3b82f6" : "#d1d5db"),
      background: active ? "#3b82f6" : "#fff",
      color: active ? "#fff" : "#374151",
      transition: "all .15s",
    }}>{label}</button>
  )
}

function BlueprintEnginePhase({ projectId, setPage, kw2Session, preloadedGoals }) {
  const sessionId = kw2Session?.id || kw2Session?.session_id || ""

  // ── step: "input" | "generating" | "results" ─────────────────────────────
  const [step, setStep]           = useState("input")
  const [keywordsText, setKwText] = useState("")
  const [fetchingKws, setFetchingKws] = useState(false)
  const [showGoalsForm, setShowGoalsForm] = useState(false)
  const [businessGoals, setBusinessGoals] = useState({
    targetAudience: preloadedGoals?.target_audience || "",
    businessOutcome: preloadedGoals?.business_outcome || "traffic",
    timeframe: preloadedGoals?.timeframe || "12_months",
  })

  // generation state
  const [sseEvents,   setSseEvents]   = useState([])   // raw event log for SSEConsole
  const [liveCards,   setLiveCards]   = useState([])   // blueprints arriving live
  const [genError,    setGenError]    = useState(null)
  const [kwProgress,  setKwProgress]  = useState({})   // per-keyword state machine
  const [totalExpected, setTotalExpected] = useState(1)
  const [totalDone,   setTotalDone]   = useState(0)
  const [showConsole, setShowConsole] = useState(false)
  const abortRef = useRef(null)
  const currentKwRef = useRef("")  // tracks active keyword; most events lack a keyword field

  // results state
  const [blueprints,   setBlueprints]   = useState([])
  const [angleFilter,  setAngleFilter]  = useState("all")
  const [minScore,     setMinScore]     = useState(0)

  // load existing blueprints when session changes
  useEffect(() => {
    if (!projectId) return
    const sid = sessionId ? `&session_id=${sessionId}` : ""
    fetch(`${API}/api/strategy-v2/${projectId}/blueprints?limit=50${sid}`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => {
        const list = data.blueprints || []
        if (list.length > 0) { setBlueprints(list); setStep("results") }
      })
      .catch(() => {})
  }, [projectId, sessionId])

  // auto-fill keywords from hub session
  async function fetchSessionKeywords() {
    if (!sessionId) return
    setFetchingKws(true)
    try {
      const r = await fetch(`${API}/api/kw2/${projectId}/sessions/${sessionId}/validated`, { headers: authHeaders() })
      if (!r.ok) throw new Error("Failed")
      const data = await r.json()
      const kws = (data.items || []).map(k => typeof k === "string" ? k : k.keyword).filter(Boolean)
      setKwText(kws.slice(0, 10).join("\n"))
    } catch { /* silent */ } finally { setFetchingKws(false) }
  }

  function fmtEvtMsg(evt) {
    const t = evt.step || evt.type || evt.event
    if (t === "classify")     return evt.status === "done"
      ? `[${evt.keyword}] classified → ${evt.intent}`
      : `[${evt.keyword}] classifying intent…`
    if (t === "context")      return `Context: ${evt.kw2_enriched ? `KW2 enriched (${evt.pillars} pillars)` : "no KW2 enrichment"}`
    if (t === "angles")       return evt.status === "done"
      ? `[${evt.keyword || ""}] ${evt.count} angles generated`
      : `[${evt.keyword || ""}] generating angles…`
    if (t === "blueprints")   return `Starting ${evt.total || "?"} blueprints in parallel…`
    if (t && t.startsWith("blueprint_")) return `Blueprint ${t.split("_")[1]}: "${evt.title || "?"}" — ${evt.status}`
    if (t === "fix")          return `[auto-fix] "${evt.title}" — score before: ${evt.score_before}`
    if (t === "fix_done")     return `[auto-fix] done — score → ${evt.score_after}`
    if (t === "qa")           return `QA scoring ${evt.count || ""} blueprints… ${evt.status || ""}`
    if (t === "done")         return `✓ ${evt.keyword} — ${evt.blueprints} blueprints (${evt.elapsed}s)`
    if (t === "keyword_done") return `✓ ${evt.keyword} complete — ${(evt.blueprints || []).length} blueprints ready`
    if (t === "all_done")     return `✅ All done — ${evt.total_blueprints} total blueprints`
    if (t === "error")        return `✗ Error: ${evt.message || evt.error}`
    return JSON.stringify(evt).slice(0, 120)
  }

  async function startGeneration() {
    const keywords = keywordsText.split("\n").map(k => k.trim()).filter(Boolean).slice(0, 10)
    if (keywords.length === 0) return

    const initKwProgress = {}
    keywords.forEach(kw => {
      initKwProgress[kw] = { phase: "classify", intent: "", angleCount: 0, blueprintsDone: 0, blueprintsTotal: 0, scores: [], avgScore: 0 }
    })

    setStep("generating")
    setShowConsole(true)  // Show console by default during generation
    setSseEvents([])
    setLiveCards([])
    setGenError(null)
    setKwProgress(initKwProgress)
    setTotalExpected(keywords.length)
    setTotalDone(0)

    try {
      const controller = new AbortController()
      abortRef.current = controller

      const resp = await fetch(`${API}/api/strategy-v2/${projectId}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ keywords, session_id: sessionId, goals: businessGoals }),
        signal: controller.signal,
      })
      if (!resp.ok) throw new Error(await resp.text() || `HTTP ${resp.status}`)

      const reader  = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer    = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          let evt
          try { evt = JSON.parse(raw) } catch { continue }
          handleStreamEvent(evt)
        }
      }
    } catch (e) {
      if (e.name === "AbortError") { setStep("input"); return }
      setGenError(e.message || "Unknown error")
    }
  }

  function handleStreamEvent(evt) {
    const step = evt.step || evt.type || evt.event
    // push to SSE console
    setSseEvents(prev => [...prev, { ...evt, timestamp: Date.now(), msg: fmtEvtMsg(evt) }])

    if (step === "classify") {
      if (evt.status === "running") {
        currentKwRef.current = evt.keyword   // set before any other events arrive
      } else if (evt.status === "done") {
        setKwProgress(prev => ({
          ...prev,
          [evt.keyword]: { ...(prev[evt.keyword] || {}), phase: "angles", intent: evt.intent },
        }))
      }
    } else if (step === "angles") {
      const kw = currentKwRef.current
      if (evt.status === "done" && kw) {
        const count = evt.count || 0
        setKwProgress(prev => ({
          ...prev,
          [kw]: { ...(prev[kw] || {}), phase: "blueprints", angleCount: count, blueprintsTotal: count },
        }))
      }
    } else if (step && step.startsWith("blueprint_")) {
      // blueprint_1, blueprint_2, … — update the keyword currently in "blueprints" phase
      setKwProgress(prev => {
        const updated = { ...prev }
        Object.keys(updated).forEach(kw => {
          if (updated[kw].phase === "blueprints") {
            updated[kw] = { ...updated[kw], blueprintsDone: (updated[kw].blueprintsDone || 0) + 1 }
          }
        })
        return updated
      })
    } else if (step === "qa") {
      const kw = currentKwRef.current
      if (kw && evt.status === "running") {
        setKwProgress(prev => ({
          ...prev,
          [kw]: { ...(prev[kw] || {}), phase: "qa" },
        }))
      }
    } else if (step === "keyword_done") {
      const all = evt.blueprints || []
      setLiveCards(prev => [...prev, ...all])
      setTotalDone(prev => prev + 1)
      setKwProgress(prev => ({
        ...prev,
        [evt.keyword]: { ...(prev[evt.keyword] || {}), phase: "done", blueprintsDone: all.length },
      }))
    } else if (step === "all_done") {
      setLiveCards(prev => {
        setBlueprints(prev)
        return prev
      })
      setTimeout(() => setStep("results"), 500)
    } else if (step === "error") {
      setGenError(evt.message || evt.error || "Generation failed")
    }
  }

  function cancelGeneration() { abortRef.current?.abort() }

  // derived
  const kwList      = keywordsText.split("\n").map(k => k.trim()).filter(Boolean).slice(0, 10)
  const pct         = Math.min(100, Math.round((totalDone / Math.max(1, totalExpected)) * 100))
  const angleTypes  = ["all", ...new Set(blueprints.map(b => b.angle_type).filter(Boolean))]
  const filtered    = blueprints.filter(b => {
    const matchAngle = angleFilter === "all" || b.angle_type === angleFilter
    const score = b.qa_overall_score ?? b.qa_score?.overall ?? b.score ?? 0
    return matchAngle && score >= minScore
  })

  // ── styles ────────────────────────────────────────────────────────────────
  const cardS = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 16, boxShadow: "0 1px 3px rgba(0,0,0,.04)" }
  const inputS = { width: "100%", padding: "8px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13, boxSizing: "border-box" }
  const labelS = { fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 5 }

  // ── STEP: INPUT ──────────────────────────────────────────────────────────
  if (step === "input") return (
    <div style={{ maxWidth: 700 }}>
      <div style={cardS}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 4 }}>
          🎯 Blueprint Engine
        </div>
        <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 18 }}>
          Transform keywords into uniquely-angled, high-quality content blueprints. Each keyword gets classified, angle-mapped, and developed into ready-to-generate briefs.
        </div>

        {/* Keywords input */}
        <div style={{ marginBottom: 16 }}>
          <label style={labelS}>Keywords (one per line, max 10)</label>
          <textarea
            style={{ ...inputS, resize: "vertical", minHeight: 110 }}
            placeholder={"best cinnamon supplement\norganic turmeric powder\nblack pepper extract benefits"}
            value={keywordsText}
            onChange={e => setKwText(e.target.value)}
          />
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 4 }}>
            <span style={{ fontSize: 11, color: "#9ca3af" }}>
              {kwList.length} / 10 keywords
            </span>
            {sessionId && (
              <button
                onClick={fetchSessionKeywords}
                disabled={fetchingKws}
                style={{ fontSize: 11, padding: "3px 10px", borderRadius: 6, border: "1px solid #d1d5db", background: "#f9fafb", cursor: "pointer", color: "#374151" }}
              >
                {fetchingKws ? "Loading…" : "↓ Pull from active session"}
              </button>
            )}
          </div>
        </div>

        {/* Business Goals (collapsible) */}
        <div style={{ marginBottom: 16 }}>
          <button
            onClick={() => setShowGoalsForm(v => !v)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              background: showGoalsForm ? "#eff6ff" : "#f9fafb",
              border: `1px solid ${showGoalsForm ? "#bfdbfe" : "#e5e7eb"}`,
              borderRadius: 7, padding: "6px 12px", fontSize: 12, fontWeight: 600,
              color: showGoalsForm ? "#1d4ed8" : "#374151", cursor: "pointer",
            }}
          >
            <span>🎯</span>
            <span>Business Goals & Context {showGoalsForm ? "▲" : "▼"}</span>
            {(businessGoals.businessOutcome !== "traffic" || businessGoals.targetAudience) && (
              <span style={{ background: "#2563eb", color: "#fff", fontSize: 10, padding: "1px 6px", borderRadius: 10, fontWeight: 700 }}>set</span>
            )}
          </button>
          {showGoalsForm && (
            <div style={{ marginTop: 8, padding: "14px 16px", border: "1px solid #bfdbfe", borderRadius: 8, background: "#f8faff" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={labelS}>Business Outcome</label>
                  <select
                    style={inputS}
                    value={businessGoals.businessOutcome}
                    onChange={e => setBusinessGoals(g => ({ ...g, businessOutcome: e.target.value }))}
                  >
                    <option value="traffic">Drive Organic Traffic</option>
                    <option value="leads">Generate B2B Leads</option>
                    <option value="sales">Direct eCommerce Sales</option>
                    <option value="authority">Establish Brand Authority</option>
                    <option value="awareness">Brand Awareness</option>
                  </select>
                </div>
                <div>
                  <label style={labelS}>Timeframe</label>
                  <select
                    style={inputS}
                    value={businessGoals.timeframe}
                    onChange={e => setBusinessGoals(g => ({ ...g, timeframe: e.target.value }))}
                  >
                    <option value="3_months">3 months</option>
                    <option value="6_months">6 months</option>
                    <option value="12_months">12 months</option>
                    <option value="24_months">24 months</option>
                  </select>
                </div>
              </div>
              <div style={{ marginTop: 12 }}>
                <label style={labelS}>Target Audience <span style={{ fontWeight: 400, color: "#9ca3af" }}>(optional)</span></label>
                <input
                  style={inputS}
                  placeholder="e.g. Health-conscious adults 25-45 looking for natural supplements"
                  value={businessGoals.targetAudience}
                  onChange={e => setBusinessGoals(g => ({ ...g, targetAudience: e.target.value }))}
                />
              </div>
              {kw2Session && (
                <div style={{ marginTop: 8, fontSize: 11, color: "#4b5563", background: "#e0f2fe", padding: "6px 10px", borderRadius: 6 }}>
                  💡 Session context (brand voice, competitors, USPs) will be automatically injected from <strong>{kw2Session.name || "active session"}</strong>.
                </div>
              )}
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button
            onClick={startGeneration}
            disabled={kwList.length === 0}
            style={{
              background: kwList.length === 0 ? "#e5e7eb" : "#2563eb",
              color: kwList.length === 0 ? "#9ca3af" : "#fff",
              border: "none", borderRadius: 7, padding: "9px 22px", fontSize: 13, fontWeight: 700, cursor: kwList.length === 0 ? "not-allowed" : "pointer",
            }}
          >
            Generate Blueprints →
          </button>
          {blueprints.length > 0 && (
            <button
              onClick={() => setStep("results")}
              style={{ background: "#f3f4f6", color: "#374151", border: "1px solid #d1d5db", borderRadius: 7, padding: "8px 16px", fontSize: 13, cursor: "pointer" }}
            >
              View existing ({blueprints.length})
            </button>
          )}
        </div>
      </div>
    </div>
  )

  // ── STEP: GENERATING ─────────────────────────────────────────────────────
  if (step === "generating") return (
    <div style={{ maxWidth: 820 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#111827" }}>Generating Blueprints…</div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
            {totalDone} / {totalExpected} blueprints • {pct}% complete
          </div>
        </div>
        <button
          onClick={cancelGeneration}
          style={{ background: "#fef2f2", color: "#dc2626", border: "1px solid #fecaca", borderRadius: 7, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
        >
          Cancel
        </button>
      </div>

      {/* Overall progress bar */}
      <div style={{ marginBottom: 18 }}>
        <div style={{ height: 10, background: "#e5e7eb", borderRadius: 5, overflow: "hidden" }}>
          <div style={{
            height: "100%", background: pct === 100 ? "#16a34a" : "#2563eb",
            width: `${pct}%`, borderRadius: 5,
            transition: "width 0.5s ease",
          }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
          <span style={{ fontSize: 11, color: "#6b7280" }}>Progress</span>
          <span style={{ fontSize: 11, fontWeight: 700, color: pct === 100 ? "#16a34a" : "#2563eb" }}>{pct}%</span>
        </div>
      </div>

      {/* Error */}
      {genError && (
        <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", marginBottom: 14 }}>
          <span style={{ fontSize: 13, color: "#dc2626", fontWeight: 600 }}>Error: </span>
          <span style={{ fontSize: 13, color: "#991b1b" }}>{genError}</span>
          <button onClick={() => setStep("input")} style={{ marginLeft: 12, fontSize: 12, color: "#dc2626", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>← Back</button>
        </div>
      )}

      {/* Per-keyword progress rows */}
      <div style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
          Keyword Pipeline
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {Object.entries(kwProgress).map(([kw, state]) => (
            <KwPhaseRow key={kw} kw={kw} state={state} />
          ))}
        </div>
      </div>

      {/* Live blueprint cards */}
      {liveCards.length > 0 && (
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
            Ready Blueprints ({liveCards.length})
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: 14 }}>
            {liveCards.map((bp, i) => (
              <BlueprintCard key={bp.id || i} blueprint={bp} projectId={projectId} onContentStarted={() => {}} setPage={setPage} />
            ))}
          </div>
        </div>
      )}

      {/* SSE Console toggle */}
      <div style={{ marginTop: 20, borderTop: "1px solid #e5e7eb", paddingTop: 14 }}>
        <button
          onClick={() => setShowConsole(v => !v)}
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: showConsole ? "#1f2937" : "#6b7280",
            background: showConsole ? "#eff6ff" : "transparent",
            border: `1px solid ${showConsole ? "#3b82f6" : "#d1d5db"}`,
            borderRadius: 6,
            padding: "6px 12px",
            cursor: "pointer",
            marginBottom: showConsole ? 12 : 0,
            transition: "all .15s",
          }}
        >
          {showConsole ? "▼ Live Console" : "▶ Show Live Console"} ({sseEvents.length})
        </button>
        {showConsole && (
          <SSELogPanel events={sseEvents} />
        )}
      </div>
    </div>
  )

  // ── STEP: RESULTS ────────────────────────────────────────────────────────
  return (
    <div>
      {/* Results header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
        <div>
          <span style={{ fontSize: 15, fontWeight: 700, color: "#111827" }}>
            {filtered.length} Blueprint{filtered.length !== 1 ? "s" : ""}
          </span>
          {blueprints.length !== filtered.length && (
            <span style={{ fontSize: 12, color: "#6b7280", marginLeft: 8 }}>
              (filtered from {blueprints.length})
            </span>
          )}
        </div>
        <button
          onClick={() => { setStep("input"); setBlueprints([]); setLiveCards([]) }}
          style={{ fontSize: 12, padding: "6px 14px", borderRadius: 7, border: "1px solid #d1d5db", background: "#f9fafb", cursor: "pointer", color: "#374151" }}
        >
          + New Generation
        </button>
      </div>

      {/* Filter bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", flex: 1 }}>
          {angleTypes.map(a => (
            <FilterChipBP
              key={a}
              label={a === "all" ? "All angles" : a.replace(/_/g, " ")}
              active={angleFilter === a}
              onClick={() => setAngleFilter(a)}
            />
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, color: "#6b7280", whiteSpace: "nowrap" }}>Min score</span>
          <input
            type="range" min={0} max={100} step={5} value={minScore}
            onChange={e => setMinScore(+e.target.value)}
            style={{ width: 80 }}
          />
          <span style={{ fontSize: 12, fontWeight: 700, color: "#374151", minWidth: 24 }}>{minScore}</span>
        </div>
      </div>

      {/* Blueprint grid */}
      {filtered.length === 0 ? (
        <div style={{ textAlign: "center", padding: "40px 20px", color: "#6b7280" }}>
          <div style={{ fontSize: 32, marginBottom: 10 }}>📋</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>No blueprints match the filter</div>
          <div style={{ fontSize: 12 }}>Try adjusting the angle filter or lowering the minimum score.</div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: 16 }}>
          {filtered.map((bp, i) => (
            <BlueprintCard key={bp.id || i} blueprint={bp} projectId={projectId} onContentStarted={() => {}} setPage={setPage} />
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MAIN HUB COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function StrategyIntelligenceHub({ projectId, setPage, initialTab }) {
  const [activePhase, setActivePhase] = useState(initialTab || "overview")
  const [selectedSessionId, setSelectedSessionId] = useState(null)
  const [strategySessionId, setStrategySessionId] = useState(null)
  const [showPromptStudio, setShowPromptStudio] = useState(false)

  // ── Shared KW2 sessions query (passed to all phases) ──
  const { data: kw2SessionsData, refetch: refetchHubSessions } = useQuery({
    queryKey: ["kw2-hub-sessions", projectId],
    queryFn: () => apiFetch(`/api/kw2/${projectId}/sessions/list`),
    enabled: !!projectId,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    refetchInterval: 20_000,
  })
  const kw2Sessions = (kw2SessionsData?.sessions || []).map(s => {
    let _strategy = null
    const raw = s?.strategy_json
    if (raw) { try { _strategy = typeof raw === "string" ? JSON.parse(raw) : raw } catch {} }
    return { ...s, _strategy }
  })
  const selectedSession = kw2Sessions.find(s => s.id === selectedSessionId) || null

  // Auto-select first completed session when none chosen
  useEffect(() => {
    if (selectedSessionId) return
    const done = kw2Sessions.filter(s => s.phase9_done || s._strategy)
    if (done.length > 0) setSelectedSessionId(done[0].id)
  }, [kw2Sessions.length]) // eslint-disable-line

  const hubSessionLabel = (s) => {
    if (!s) return ""
    if (s.name) return s.name
    if (Array.isArray(s.seed_keywords) && s.seed_keywords.length) return s.seed_keywords.slice(0, 3).join(" · ")
    return `Session ${(s.id || "").slice(-6)}`
  }

  // Load strategy context
  const { data: strategy, isLoading } = useQuery({
    queryKey: ["si-strategy", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}`).catch(() => null),
    enabled: !!projectId,
    retry: false,
  })

  // Load goals for blueprint pre-population
  const { data: goalProgress } = useQuery({
    queryKey: ["si-goal-progress", projectId],
    queryFn: () => apiFetch(`/api/si/${projectId}/goals/progress`).catch(() => null),
    enabled: !!projectId,
    retry: false,
    staleTime: 60_000,
  })
  const bpPreloadedGoals = (() => {
    const g = goalProgress?.goals || strategy?.goals || null
    if (!g) return null
    return {
      business_outcome: g.goal_type || g.business_outcome || "traffic",
      target_audience: g.target_audience || "",
      timeframe: g.timeframe_months ? `${g.timeframe_months}_months` : "12_months",
    }
  })()

  // Auto-init strategy if none exists
  const initMut = useMutation({
    mutationFn: () => apiFetch(`/api/si/${projectId}/init`, { method: "POST", body: JSON.stringify({}) }),
  })

  useEffect(() => {
    if (!isLoading && !strategy && projectId && !initMut.isPending && !initMut.isSuccess) {
      initMut.mutate()
    }
  }, [isLoading, strategy, projectId])

  if (!projectId) {
    return (
      <div style={{ padding: 32, textAlign: "center", color: T.textSoft }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>🧠</div>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>Select a project</div>
        <div style={{ fontSize: 13 }}>Choose a project from the sidebar to start your SEO strategy.</div>
      </div>
    )
  }

  // When a session strategy page is open, render it full-screen
  if (strategySessionId) {
    const stratSession = kw2Sessions.find(s => s.id === strategySessionId) || null
    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
        <SessionStrategyPage
          projectId={projectId}
          sessionId={strategySessionId}
          session={stratSession}
          onBack={() => setStrategySessionId(null)}
          setPage={setPage}
        />
      </div>
    )
  }

  return (
    <div style={{ display: "flex", height: "100%" }}>
      {showPromptStudio && (
        <Kw2PromptStudio filterPhases={[2]} onClose={() => setShowPromptStudio(false)} />
      )}
      {/* Phase sidebar */}
      <div style={{ width: 180, borderRight: `1px solid ${T.border}`, background: "#fefefe", flexShrink: 0, padding: "12px 0" }}>
        <div style={{ padding: "4px 14px 12px", fontSize: 11, fontWeight: 700, color: T.purpleDark, textTransform: "uppercase", letterSpacing: 0.5 }}>
          Strategy Phases
        </div>
        {PHASES.map(p => (
          <button key={p.id} onClick={() => setActivePhase(p.id)} style={{
            display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "8px 14px",
            border: "none", cursor: "pointer", fontSize: 12, fontWeight: activePhase === p.id ? 700 : 400,
            background: activePhase === p.id ? T.purpleLight : "transparent",
            color: activePhase === p.id ? T.purpleDark : T.gray,
            borderLeft: `3px solid ${activePhase === p.id ? T.purple : "transparent"}`,
            textAlign: "left",
          }}>
            <span>{p.icon}</span>
            <span>{p.label}</span>
          </button>
        ))}
      </div>

      {/* Right panel: context bar + content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
        {/* ── SESSION CONTEXT BAR ────────────────────────────────────────── */}
        {kw2Sessions.length > 0 && (
          <div style={{
            padding: "7px 20px",
            borderBottom: `1px solid ${T.border}`,
            background: selectedSession ? `${T.purple}05` : "#fefefe",
            display: "flex", alignItems: "center", gap: 10, flexShrink: 0,
            flexWrap: "wrap",
          }}>
            <span style={{ fontSize: 10, color: T.textSoft, fontWeight: 700, textTransform: "uppercase", letterSpacing: .05 }}>Active Session:</span>
            <select
              value={selectedSessionId || ""}
              onChange={e => setSelectedSessionId(e.target.value || null)}
              style={{
                fontSize: 12, padding: "3px 8px", borderRadius: 6,
                border: `1px solid ${T.border}`, background: "#fff",
                color: T.text, fontWeight: 500, maxWidth: 300, cursor: "pointer",
              }}
            >
              <option value="">— All Sessions —</option>
              {kw2Sessions.map(s => {
                const done = [1,2,3,4,5,6,7,8,9].filter(i => s[`phase${i}_done`]).length
                return (
                  <option key={s.id} value={s.id}>
                    {hubSessionLabel(s)} {s.phase9_done ? "✓" : `(${done}/9)`}
                  </option>
                )
              })}
            </select>
            {selectedSession && (
              <>
                <span style={{ fontSize: 11, color: T.teal, fontWeight: 600 }}>
                  {(selectedSession.validated_total || 0).toLocaleString()} validated
                  {" · "}
                  {(selectedSession.universe_total || 0).toLocaleString()} universe
                </span>
                {selectedSession.phase9_done && (
                  <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 8, background: "#dcfce7", color: T.teal, fontWeight: 700 }}>✓ Strategy Ready</span>
                )}
              </>
            )}
            <button
              onClick={() => refetchHubSessions()}
              style={{ marginLeft: "auto", fontSize: 11, padding: "2px 8px", borderRadius: 5, border: `1px solid ${T.border}`, background: "transparent", cursor: "pointer", color: T.textSoft }}
            >↺</button>
            <button
              onClick={() => setShowPromptStudio(true)}
              style={{ fontSize: 11, padding: "3px 10px", borderRadius: 5, border: `1px solid ${T.border}`, background: "transparent", cursor: "pointer", color: T.textSoft, fontWeight: 500 }}
            >🧪 Prompts</button>
          </div>
        )}

        {/* Main content */}
        <div style={{ flex: 1, padding: "20px 24px", overflowY: "auto" }}>
          {activePhase === "overview"    && <KwSessionsOverview projectId={projectId} setPage={setPage} kw2Sessions={kw2Sessions} selectedSessionId={selectedSessionId} onSelectSession={setSelectedSessionId} onNavigate={setActivePhase} onDevelop={setStrategySessionId} />}
          {activePhase === "keywords"    && <KeywordPillarsPhase projectId={projectId} setPage={setPage} kw2Session={selectedSession} />}
          {activePhase === "analysis"    && <AnalysisPhase projectId={projectId} strategy={strategy} kw2Session={selectedSession} />}
          {activePhase === "strategy"    && <StrategyPhase projectId={projectId} setPage={setPage} selectedSessionId={selectedSessionId} setSelectedSessionId={setSelectedSessionId} kw2Sessions={kw2Sessions} />}
          {activePhase === "content"     && <ContentHubPhase projectId={projectId} kw2Session={selectedSession} />}
          {activePhase === "links"       && <LinkBuildingPhase projectId={projectId} kw2Session={selectedSession} />}
          {activePhase === "goals"       && <GoalsPhase projectId={projectId} />}
          {activePhase === "blueprints"  && <BlueprintEnginePhase projectId={projectId} setPage={setPage} kw2Session={selectedSession} preloadedGoals={bpPreloadedGoals} />}
        </div>
      </div>
    </div>
  )
}
