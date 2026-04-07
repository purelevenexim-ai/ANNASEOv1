// Step 2 — Keyword Discovery (Overhauled)
// Part A: Crawl user + competitor sites → extract products (pillar keywords), reviews, competitor pillars
// Part B: SSE research stream → live console (6 sources: cross-multiply, user, site-crawl, competitor, google, wikipedia)
// Part C: Inline results table with filters, pagination, source badges
// Reads: WorkflowContext.step1 (pillars, supports, urls, intent)
// Output: keyword_universe_items rows in DB + ctx.step2.keyword_count

import { useState, useRef, useEffect, useCallback } from "react"
import { useNotification } from "../store/notification"
import useWorkflowContext from "../store/workflowContext"
import { T, Card, Btn, Badge, Spinner, LiveConsole, SEASONAL_PRESETS, SOURCE_COLORS, intentColor } from "./shared"

const API = import.meta.env.VITE_API_URL || ""
const PAGE_SIZE = 50

function authHeaders() {
  const token = localStorage.getItem("annaseo_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ─── Deduplicate keyword list by name (case-insensitive) ─────────────────────
function dedup(items) {
  const seen = new Set()
  return items.filter(item => {
    const key = (typeof item === "string" ? item : item.name || "").toLowerCase().trim()
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

// ─── AI Provider selector ─────────────────────────────────────────────────────
const AI_PROVIDERS = [
  { value: "groq",        label: "⚡ Groq",         desc: "llama-3.3-70b · fastest" },
  { value: "gemini_free", label: "💎 Gemini",        desc: "gemini-2.0-flash · free" },
  { value: "gemini_paid", label: "💎 Gemini Paid",   desc: "gemini-pro · paid" },
  { value: "ollama",      label: "🦙 Ollama",        desc: "mistral-7b · local" },
  { value: "anthropic",   label: "🧠 Claude",        desc: "claude-sonnet" },
  { value: "openai_paid", label: "🤖 ChatGPT",       desc: "gpt-4o" },
]

function AiProviderSelect({ value, onChange, label = "AI for scoring:" }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {label && <span style={{ fontSize: 11, color: T.textSoft, fontWeight: 600, whiteSpace: "nowrap" }}>{label}</span>}
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          fontSize: 11, padding: "4px 10px", borderRadius: 7,
          border: `1.5px solid ${T.border}`, background: "#fff",
          cursor: "pointer", fontWeight: 500, color: T.text,
          minWidth: 160,
        }}
      >
        {AI_PROVIDERS.map(p => (
          <option key={p.value} value={p.value}>{p.label} — {p.desc}</option>
        ))}
      </select>
    </div>
  )
}

// ─── Editable Chip List ───────────────────────────────────────────────────────
function ChipList({ items, onRemove, onUpdate, onMove, onMarkBad, moveLabel, label, color = T.teal, emptyText }) {
  const [editIdx, setEditIdx] = useState(-1)
  const [editVal, setEditVal] = useState("")

  const startEdit = (idx) => { setEditIdx(idx); setEditVal(items[idx]?.name || items[idx]) }
  const commitEdit = () => {
    if (editVal.trim() && editIdx >= 0) onUpdate(editIdx, editVal.trim())
    setEditIdx(-1)
  }

  // Tier badge config
  const tierBadge = (item) => {
    if (typeof item !== "object") return null
    const tier = item.pillar_tier
    const score = item.final_score
    if (tier === "product" || score >= 100) return { label: "★ 100", bg: "#d97706", title: "Confirmed product (score 100)" }
    if (tier === "thematic" || (score >= 45 && score <= 55)) return { label: "◈ 50", bg: "#2563eb", title: "Thematic category keyword (score 50)" }
    if (score != null && score > 0) return { label: Math.round(score), bg: "#6b7280", title: `Score: ${Math.round(score)}` }
    return null
  }

  return (
    <div>
      {label && <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 6, color: T.textSoft }}>{label}</div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {items.length === 0 && (
          <span style={{ fontSize: 11, color: T.textSoft, fontStyle: "italic" }}>{emptyText || "None found"}</span>
        )}
        {items.map((item, idx) => {
          const name = typeof item === "string" ? item : item.name
          const source = typeof item === "object" ? item.source : null
          const score = typeof item === "object" ? item.final_score : null
          const isGood = typeof item === "object" ? item.is_good !== false : true
          if (editIdx === idx) {
            return (
              <input key={idx} autoFocus value={editVal} onChange={e => setEditVal(e.target.value)}
                onBlur={commitEdit} onKeyDown={e => e.key === "Enter" && commitEdit()}
                style={{ padding: "3px 8px", borderRadius: 6, border: `1px solid ${color}`, fontSize: 11, width: 140 }} />
            )
          }
          return (
            <span key={idx} style={{
              display: "inline-flex", alignItems: "center", gap: 3,
              padding: "3px 8px", borderRadius: 6, fontSize: 11, fontWeight: 500,
              background: (isGood ? color : "#b91c1c") + "18",
              color: isGood ? color : "#b91c1c",
              cursor: "default",
              border: `1px solid ${color}33`,
            }}>
              {/* Keyword text — click to edit */}
              <span onClick={() => startEdit(idx)} title="Click to edit" style={{ cursor: "pointer" }}>{name}</span>
              {/* Compact source label: show only domain or short tag */}
              {source && (
                <span style={{ fontSize: 9, opacity: 0.5 }}>
                  ({source.replace(/^competitor:https?:\/\//, "").replace(/^https?:\/\//, "").replace(/\/.*/,"").slice(0,18)})
                </span>
              )}
              {/* Tier / score badge */}
              {(() => { const b = tierBadge(item); return b ? (
                <span title={b.title} style={{
                  fontSize: 9, fontWeight: 700, padding: "1px 4px", borderRadius: 3,
                  background: b.bg, color: "#fff", marginLeft: 1, letterSpacing: 0.3,
                }}>{b.label}</span>
              ) : null })()} 
              {/* Move button */}
              {onMove && (
                <span onClick={() => onMove(idx)} title={moveLabel || "Move"}
                  style={{ cursor: "pointer", opacity: 0.6, fontSize: 10, fontWeight: 700, padding: "0 1px" }}>
                  {moveLabel === "→ Pillar" ? "↑" : "↓"}
                </span>
              )}
              {/* Mark as bad */}
              {onMarkBad && (
                <span onClick={() => onMarkBad(idx)} title="Mark as bad"
                  style={{ cursor: "pointer", opacity: 0.55, fontSize: 10, color: "#dc2626", padding: "0 1px" }}>
                  ✕
                </span>
              )}
              {/* Delete */}
              <span onClick={() => onRemove(idx)} title="Delete"
                style={{ cursor: "pointer", opacity: 0.45, fontWeight: 700, fontSize: 11, padding: "0 1px" }}>×</span>
            </span>
          )
        })}
      </div>
    </div>
  )
}

// ─── Add-item input ───────────────────────────────────────────────────────────
function AddInput({ onAdd, placeholder }) {
  const [val, setVal] = useState("")
  const submit = () => { if (val.trim()) { onAdd(val.trim()); setVal("") } }
  return (
    <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
      <input value={val} onChange={e => setVal(e.target.value)}
        onKeyDown={e => e.key === "Enter" && submit()} placeholder={placeholder}
        style={{ flex: 1, padding: "5px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 11 }} />
      <Btn small onClick={submit}>+ Add</Btn>
    </div>
  )
}

// ─── Grouped Supporting Keywords Table ────────────────────────────────────────
function SupportingTable({ items, pillars, onRemove, onUpdate, onMove, onMarkBad, onBulkRemove, onBulkBad, stage, color = "#d97706" }) {
  const [selected, setSelected] = useState(new Set())
  const [filterPillar, setFilterPillar] = useState("all")
  const [editIdx, setEditIdx] = useState(-1)
  const [editVal, setEditVal] = useState("")

  // Group items by pillar, sort by score desc within each group
  const grouped = {}
  const pillarNames = []
  items.forEach((item, idx) => {
    const name = typeof item === "string" ? item : item.name
    const pillar = (typeof item === "object" ? item.pillar : "") || "uncategorized"
    if (!grouped[pillar]) { grouped[pillar] = []; pillarNames.push(pillar) }
    grouped[pillar].push({ ...item, _idx: idx, name })
  })
  // Sort each group by score desc
  for (const key of Object.keys(grouped)) {
    grouped[key].sort((a, b) => (b.final_score || 0) - (a.final_score || 0))
  }
  // Sort pillar groups by name, but put "uncategorized" last
  pillarNames.sort((a, b) => a === "uncategorized" ? 1 : b === "uncategorized" ? -1 : a.localeCompare(b))

  const filteredPillars = filterPillar === "all" ? pillarNames : pillarNames.filter(p => p === filterPillar)
  const allVisibleIdxs = filteredPillars.flatMap(p => (grouped[p] || []).map(it => it._idx))
  const allSelected = allVisibleIdxs.length > 0 && allVisibleIdxs.every(i => selected.has(i))

  const toggleAll = () => {
    if (allSelected) setSelected(new Set())
    else setSelected(new Set(allVisibleIdxs))
  }
  const toggle = (idx) => setSelected(prev => {
    const next = new Set(prev)
    next.has(idx) ? next.delete(idx) : next.add(idx)
    return next
  })

  const doBulkDelete = () => { if (selected.size > 0) { onBulkRemove([...selected]); setSelected(new Set()) } }
  const doBulkBad = () => { if (selected.size > 0) { onBulkBad([...selected]); setSelected(new Set()) } }

  const startEdit = (idx, name) => { setEditIdx(idx); setEditVal(name) }
  const commitEdit = () => {
    if (editVal.trim() && editIdx >= 0) onUpdate(editIdx, editVal.trim())
    setEditIdx(-1)
  }

  const scoreColor = (s) => s >= 70 ? "#059669" : s >= 40 ? "#d97706" : "#dc2626"

  return (
    <div>
      {/* Filter + Bulk toolbar */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
        <select value={filterPillar} onChange={e => { setFilterPillar(e.target.value); setSelected(new Set()) }}
          style={{ padding: "4px 8px", borderRadius: 6, border: `1px solid #ddd`, fontSize: 11 }}>
          <option value="all">All Pillars ({items.length})</option>
          {pillarNames.map(p => <option key={p} value={p}>{p} ({(grouped[p] || []).length})</option>)}
        </select>
        {selected.size > 0 && (
          <>
            <span style={{ fontSize: 11, fontWeight: 600, color: "#007AFF" }}>{selected.size} selected</span>
            <button onClick={doBulkDelete} style={{
              padding: "3px 10px", borderRadius: 5, fontSize: 10, fontWeight: 600,
              background: "#fee2e2", color: "#991b1b", border: "1px solid #fecaca", cursor: "pointer",
            }}>× Delete selected</button>
            <button onClick={doBulkBad} style={{
              padding: "3px 10px", borderRadius: 5, fontSize: 10, fontWeight: 600,
              background: "#fef3c7", color: "#92400e", border: "1px solid #fde68a", cursor: "pointer",
            }}>✕ Mark bad</button>
            <button onClick={() => {
              [...selected].forEach(idx => onMove(idx))
              setSelected(new Set())
            }} style={{
              padding: "3px 10px", borderRadius: 5, fontSize: 10, fontWeight: 600,
              background: "rgba(0,122,255,0.1)", color: "#0040DD", border: "1px solid rgba(0,122,255,0.2)", cursor: "pointer",
            }}>↑ Move to Pillar</button>
          </>
        )}
      </div>

      {filteredPillars.length === 0 && (
        <div style={{ fontSize: 11, color: "#999", fontStyle: "italic", padding: 8 }}>No supporting keywords found</div>
      )}

      {filteredPillars.map(pillar => {
        const group = grouped[pillar] || []
        if (group.length === 0) return null
        return (
          <div key={pillar} style={{ marginBottom: 12 }}>
            <div style={{
              fontSize: 11, fontWeight: 700, padding: "4px 8px", borderRadius: "6px 6px 0 0",
              background: color + "18", color, display: "flex", alignItems: "center", gap: 6,
            }}>
              <span>{pillar}</span>
              <span style={{ fontSize: 9, fontWeight: 400, opacity: 0.7 }}>({group.length} keywords)</span>
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr style={{ background: "#f9fafb", borderBottom: "1px solid #e5e7eb" }}>
                  <th style={{ width: 28, padding: "4px 6px" }}>
                    <input type="checkbox" checked={group.every(it => selected.has(it._idx))}
                      onChange={() => {
                        const groupIdxs = group.map(it => it._idx)
                        const allIn = groupIdxs.every(i => selected.has(i))
                        setSelected(prev => {
                          const next = new Set(prev)
                          groupIdxs.forEach(i => allIn ? next.delete(i) : next.add(i))
                          return next
                        })
                      }} />
                  </th>
                  <th style={{ padding: "4px 6px", textAlign: "left" }}>Keyword</th>
                  <th style={{ padding: "4px 6px", width: 60 }}>Score</th>
                  <th style={{ padding: "4px 6px", width: 80 }}>Intent</th>
                  <th style={{ padding: "4px 6px", width: 70 }}>Source</th>
                  <th style={{ padding: "4px 6px", width: 90 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {group.map((item) => {
                  const score = item.final_score || 0
                  return (
                    <tr key={item._idx} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "3px 6px" }}>
                        <input type="checkbox" checked={selected.has(item._idx)} onChange={() => toggle(item._idx)} />
                      </td>
                      <td style={{ padding: "3px 6px" }}>
                        {editIdx === item._idx ? (
                          <input autoFocus value={editVal} onChange={e => setEditVal(e.target.value)}
                            onBlur={commitEdit} onKeyDown={e => e.key === "Enter" && commitEdit()}
                            style={{ padding: "2px 6px", borderRadius: 4, border: "1px solid #ddd", fontSize: 11, width: "100%" }} />
                        ) : (
                          <span onClick={() => startEdit(item._idx, item.name)} style={{ cursor: "pointer" }} title="Click to edit">
                            {item.name}
                          </span>
                        )}
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "center", fontWeight: 700, color: scoreColor(score) }}>
                        {Math.round(score)}
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "center" }}>
                        {item.intent && <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 3, background: intentColor(item.intent) + "18", color: intentColor(item.intent), fontWeight: 600 }}>{item.intent}</span>}
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "center", fontSize: 9, opacity: 0.6 }}>
                        {(item.source || "").replace(/^competitor:https?:\/\//, "").replace(/^https?:\/\//, "").replace(/\/.*/, "").slice(0, 14)}
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "center" }}>
                        <span onClick={() => onMove(item._idx)} title="Move to Pillar" style={{ cursor: "pointer", fontSize: 10, marginRight: 4, color: "#007AFF" }}>↑</span>
                        <span onClick={() => onMarkBad(item._idx)} title="Mark bad" style={{ cursor: "pointer", fontSize: 10, marginRight: 4, color: "#dc2626" }}>✕</span>
                        <span onClick={() => onRemove(item._idx)} title="Delete" style={{ cursor: "pointer", fontSize: 11, color: "#999", fontWeight: 700 }}>×</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )
      })}
    </div>
  )
}

export default function Step2Discovery({ projectId, onComplete, onBack }) {
  const notify = useNotification(s => s.notify)
  const ctx = useWorkflowContext()

  const step1 = ctx.step1 || {}
  const pillars        = step1.pillars || []
  const businessIntent = step1.intent || ["mixed"]

  // ── URL state: prefers workflow context, falls back to saved profile ────────
  const [customerUrl, setCustomerUrl]       = useState(step1.customerUrl || "")
  const [competitorUrls, setCompetitorUrls] = useState(step1.competitorUrls || [])

  useEffect(() => {
    // If context already has the URL, no need to fetch
    if (step1.customerUrl) return
    fetch(`${API}/api/ki/${projectId}/profile`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(profile => {
        if (!profile) return
        if (profile.website_url) setCustomerUrl(profile.website_url)
        if (Array.isArray(profile.competitor_urls) && profile.competitor_urls.length > 0) {
          setCompetitorUrls(profile.competitor_urls)
        }
      })
      .catch(() => {}) // silently ignore network errors
  }, [projectId]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Crawl context state ─────────────────────────────────────────────────────
  const [crawlStatus, setCrawlStatus] = useState(null) // null | crawling | done | error
  const [competitorCrawlStatus, setCompetitorCrawlStatus] = useState(null) // null | crawling | done | error
  const [crawlProducts, setCrawlProducts]         = useState([])
  const [crawlSupportingKws, setCrawlSupportingKws] = useState([])
  const [crawlReviews, setCrawlReviews]           = useState([])
  const [crawlReviewThemes, setCrawlReviewThemes] = useState([])
  const [crawlCompPillars, setCrawlCompPillars]   = useState([])
  const [crawlCompSupportingKws, setCrawlCompSupportingKws] = useState([])
  const [crawlErrors, setCrawlErrors]             = useState([])
  const [businessProfile, setBusinessProfile]     = useState(null)
  const [pageBreakdown, setPageBreakdown]         = useState({})

  // ── Top ranking state ───────────────────────────────────────────────────────
  const [scoringStatus, setScoringStatus] = useState(null) // null | running | done | error
  const [topByPillar, setTopByPillar] = useState({})
  const [scoringSummary, setScoringSummary] = useState(null)

  // ── AI Validation state ────────────────────────────────────────────────────
  const [aiValidateStatus, setAiValidateStatus] = useState(null) // null | running | done | error
  const [aiValidateResult, setAiValidateResult] = useState(null)
  const [universeData, setUniverseData] = useState(null)       // Stage 4: Keyword Universe
  const [clusterData, setClusterData] = useState(null)         // Stage 5: AI Score & Cluster

  // ── Extra context form ──────────────────────────────────────────────────────
  const [manualProducts, setManualProducts]       = useState("")
  const [reviewAreas, setReviewAreas]             = useState("")
  const [seasonalEvents, setSeasonalEvents]       = useState([])

  // ── AI Provider selector ───────────────────────────────────────────────────
  const [discoveryAiProvider, setDiscoveryAiProvider] = useState("groq")

  // ── Stream state ────────────────────────────────────────────────────────────
  const [status, setStatus]     = useState(null)  // null | running | completed | failed
  const [logs, setLogs]         = useState([])
  const [summary, setSummary]   = useState(null)
  const [error, setError]       = useState("")
  const abortRef                = useRef(null)

  // ── Global engine console (collects logs from ALL stages) ─────────────────
  const [globalLogs, setGlobalLogs] = useState([])
  const glog = useCallback((msg, level = "info", extra = {}) => {
    setGlobalLogs(prev => [...prev.slice(-999), { msg, level, ts: Date.now(), ...extra }])
  }, [])

  // ── Abort SSE stream on unmount to prevent memory leaks ────────────────────
  useEffect(() => {
    return () => { abortRef.current?.abort() }
  }, [])

  // ── Results state ───────────────────────────────────────────────────────────
  const [results, setResults]   = useState([])
  const [resultTotal, setResultTotal] = useState(0)
  const [resultStats, setResultStats] = useState({})
  const [pillarCards, setPillarCards] = useState([])     // pillar card view data
  const [expandedPillars, setExpandedPillars] = useState(new Set())
  const [mergedCrawlCards, setMergedCrawlCards] = useState([])   // combined Stage 1+2 pillar cards
  const [mergedExpanded, setMergedExpanded] = useState(new Set())
  const [showCrawlDetail, setShowCrawlDetail] = useState(false)  // toggle crawler keyword list when combined is visible
  const [stage5Collapsed, setStage5Collapsed] = useState(false)  // collapse Stage 5 cluster view
  const [combinedCollapsed, setCombinedCollapsed] = useState(false) // collapse combined keyword card

  // ── Cascading stage tracker: results only show on the LATEST completed stage ─
  // Stage 1 = crawl done, Stage 2 = competitor done + merged, Stage 3 = discovery done,
  // Stage 4 = universe done, Stage 5 = AI scored, Stage 6 = strategy run
  const highestStage = (() => {
    if (scoringSummary?.good || clusterData) return 5   // Stage 5 done
    if (universeData) return 4                          // Stage 4 done
    if (status === "completed") return 3                // Stage 3 done
    if (mergedCrawlCards.length > 0) return 2           // Combined crawl done
    if (crawlStatus === "done") return 1                // Stage 1 done
    return 0
  })()
  const [mergingCrawl, setMergingCrawl] = useState(false)
  const [mergedTotal, setMergedTotal] = useState(0)
  const [mergedDropped, setMergedDropped] = useState(0)
  const [filterPillar, setFilterPillar] = useState("all")
  const [filterIntent, setFilterIntent] = useState("all")
  const [filterSource, setFilterSource] = useState("all")
  const [filterType, setFilterType]     = useState("all")
  const [sortBy, setSortBy]           = useState("score_desc")
  const [resultPage, setResultPage]   = useState(0)
  const [loadingResults, setLoadingResults] = useState(false)
  const [viewMode, setViewMode]       = useState("cards") // "cards" | "table"
  const [selectedKws, setSelectedKws] = useState(new Set())   // selected keyword item_ids
  const [bulkLoading, setBulkLoading] = useState(false)
  const [renamingPillar, setRenamingPillar] = useState(null)   // { old: "name" }
  const [renameValue, setRenameValue] = useState("")
  const [addPillarMode, setAddPillarMode] = useState(false)
  const [newPillarName, setNewPillarName] = useState("")
  const [rescoreTarget, setRescoreTarget] = useState(null)     // pillar name or "all"
  const [movingTo, setMovingTo] = useState(null)               // pillar name to move selected kws to

  // ── AI Prompts state ────────────────────────────────────────────────────────
  const [prompts, setPrompts] = useState({})
  const [promptsLoaded, setPromptsLoaded] = useState(false)
  const [editingPrompt, setEditingPrompt] = useState(null)   // prompt_type key
  const [promptDraft, setPromptDraft] = useState("")
  const [promptSaving, setPromptSaving] = useState(false)
  const [promptImproving, setPromptImproving] = useState(false)

  // Load prompts on mount
  useEffect(() => {
    if (!projectId) return
    fetch(`${API}/api/ki/${projectId}/prompts`, { headers: authHeaders() })
      .then(r => r.json())
      .then(data => { setPrompts(data); setPromptsLoaded(true) })
      .catch(() => setPromptsLoaded(true))
  }, [projectId])

  const toggleSeasonal = (v) =>
    setSeasonalEvents(prev => prev.includes(v) ? prev.filter(x => x !== v) : [...prev, v])

  const reviewAction = async (stage, keyword, action, newKeyword = "") => {
    try {
      await fetch(`${API}/api/ki/${projectId}/crawl-review/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ stage, keyword, action, new_keyword: newKeyword }),
      })
    } catch {
      // Best-effort persistence; UI state is still updated locally.
    }
  }

  // ── Save / Load full curated state ─────────────────────────────────────────
  const [saveStatus, setSaveStatus] = useState(null) // null | saving | saved | error

  const serializeList = (list) =>
    list.map(item => typeof item === "string"
      ? { name: item, source: "manual" }
      : item
    )

  // Save crawl state — accepts optional override data to avoid React state timing issues
  const saveState = async (overrideData) => {
    setSaveStatus("saving")
    try {
      const payload = overrideData
        ? {
            pillar_keywords:       serializeList(overrideData.pillar_keywords   || crawlProducts),
            supporting_keywords:   serializeList(overrideData.supporting_keywords || crawlSupportingKws),
            competitor_pillars:    serializeList(overrideData.competitor_pillars  || crawlCompPillars),
            competitor_supporting: serializeList(overrideData.competitor_supporting || crawlCompSupportingKws),
          }
        : {
            pillar_keywords:       serializeList(crawlProducts),
            supporting_keywords:   serializeList(crawlSupportingKws),
            competitor_pillars:    serializeList(crawlCompPillars),
            competitor_supporting: serializeList(crawlCompSupportingKws),
          }
      const res = await fetch(`${API}/api/ki/${projectId}/crawl-save-state`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error("Save failed")
      setSaveStatus("saved")
      notify("Crawl state saved", "success")
      setTimeout(() => setSaveStatus(null), 3000)
    } catch (e) {
      setSaveStatus("error")
      notify("Save failed: " + String(e), "error")
      setTimeout(() => setSaveStatus(null), 3000)
    }
  }

  const loadSavedState = async () => {
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/crawl-saved-state`, {
        headers: authHeaders(),
      })
      if (!res.ok) return
      const data = await res.json()
      if (!data.found) return
      const s = data.state || {}
      const toItems = (arr, defaultIntent = "informational") => (arr || []).map(x => {
        const item = typeof x === "string" ? { name: x, source: "manual" } : x
        return {
          name: item.name || "",
          source: item.source || "manual",
          intent: item.intent || defaultIntent,
          final_score: item.final_score ?? 0,
          is_good: item.is_good !== false,
          ...item,
        }
      })
      if ((s.pillar_keywords || []).length > 0) {
        setCrawlProducts(dedup(toItems(s.pillar_keywords, "purchase")))
        setCrawlSupportingKws(dedup(toItems(s.supporting_keywords, "informational")))
        setCrawlStatus("done")
      }
      if ((s.competitor_pillars || []).length > 0) {
        setCrawlCompPillars(dedup(toItems(s.competitor_pillars, "purchase")))
        setCrawlCompSupportingKws(dedup(toItems(s.competitor_supporting, "informational")))
        setCompetitorCrawlStatus("done")
      }
      // Restore merged crawl view if any crawl data exists
      if ((s.pillar_keywords || []).length > 0 || (s.competitor_pillars || []).length > 0) {
        try {
          await mergeCrawlKeywords({
            pillar_keywords: s.pillar_keywords || [],
            supporting_keywords: s.supporting_keywords || [],
            competitor_pillars: s.competitor_pillars || [],
            competitor_supporting: s.competitor_supporting || [],
          })
        } catch (_e) { /* ignore */ }
      }
    } catch {
      // Silently ignore — saved state is optional
    }
  }

  // Auto-load saved state on mount
  useEffect(() => {
    loadSavedState()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  // ── Stage 1: Crawl customer website only ───────────────────────────────────
  const doCustomerCrawl = async () => {
    setCrawlStatus("crawling")
    setCrawlErrors([])
    glog("Stage 1: Crawling your website...", "info")
    const crawlSteps = [
      "Discovering site pages...",
      "Crawling product pages...",
      "Analyzing page content with AI...",
      "Extracting keywords from pages...",
      "Running Google Suggest enrichment...",
      "Scoring & classifying keywords...",
      "Almost done — finalizing results...",
    ]
    let stepIdx = 0
    const heartbeat = setInterval(() => {
      if (stepIdx < crawlSteps.length) {
        glog(crawlSteps[stepIdx], "info")
        stepIdx++
      } else {
        glog("Still processing — large sites take longer...", "info")
      }
    }, 8000)
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/intelligent-crawl`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          customer_url: customerUrl,
          existing_pillars: pillars,
        }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d?.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()

      const prods = dedup((data.pillar_keywords || []).map(p => ({
        name: p.keyword,
        source: p.source || "site_crawl",
        intent: p.intent || "purchase",
        final_score: p.final_score ?? p.relevance_score ?? 0,
        is_good: p.is_good !== false,
        pillar_tier: p.pillar_tier || "",
      })))
      setCrawlProducts(prods)

      const supKws = dedup((data.supporting_keywords || []).map(kw => ({
        name: kw.keyword,
        pillar: kw.pillar || "",
        source: kw.source || "site_crawl",
        intent: kw.intent || "informational",
        final_score: kw.final_score ?? 0,
        is_good: kw.is_good !== false,
      })))
      setCrawlSupportingKws(supKws)

      setBusinessProfile(data.business_profile || null)
      setPageBreakdown(data.page_breakdown || {})
      setCrawlReviews([])
      setCrawlReviewThemes([])
      setCrawlErrors(data.errors || [])
      setCrawlStatus("done")
      clearInterval(heartbeat)
      glog(`Stage 1 complete — ${prods.length} pillars, ${supKws.length} supporting keywords`, "success")
      notify(`Customer crawl complete — ${prods.length} pillars, ${supKws.length} supporting`, "success")
      // Auto-save with direct data (React state hasn't flushed yet)
      try { await saveState({ pillar_keywords: prods, supporting_keywords: supKws }) } catch (_e) { console.warn("Auto-save after customer crawl failed:", _e) }
      // Merge crawl keywords to universe DB
      try { await mergeCrawlKeywords({ pillar_keywords: prods, supporting_keywords: supKws }) } catch (_e) { console.warn("Merge-crawl after Stage 1 failed:", _e) }
    } catch (e) {
      clearInterval(heartbeat)
      setCrawlStatus("error")
      setCrawlErrors([String(e)])
      glog(`Stage 1 FAILED: ${String(e)}`, "error")
      notify("Customer crawl failed: " + String(e), "error")
    }
  }

  // ── Stage 2: Crawl competitors only after pillar review ───────────────────
  const doCompetitorCrawl = async () => {
    setCompetitorCrawlStatus("crawling")
    setCrawlErrors([])
    glog("Stage 2: Crawling competitor sites...", "info")

    if (!competitorUrls || competitorUrls.length === 0) {
      setCompetitorCrawlStatus("done")
      glog("No competitor URLs provided. Skipping stage 2.", "info")
      notify("No competitors to crawl.", "info")
      return;
    }

    let compStep = 0
    const compSteps = [
      "Discovering competitor pages...",
      "Crawling competitor product pages...",
      "AI-analyzing competitor content...",
      "Extracting competitor keywords...",
      "Scoring competitor keywords...",
      "Almost done — finalizing...",
    ]
    const compHeartbeat = setInterval(() => {
      if (compStep < compSteps.length) {
        glog(compSteps[compStep], "info")
        compStep++
      } else {
        glog("Still processing competitors...", "info")
      }
    }, 8000)
    const confirmedPillars = [
      ...pillars,
      ...crawlProducts.map(p => typeof p === "string" ? p : p.name),
    ].filter((v, i, a) => v && a.indexOf(v) === i)

    try {
      const res = await fetch(`${API}/api/ki/${projectId}/intelligent-competitor`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          competitor_urls: competitorUrls,
          confirmed_pillars: confirmedPillars,
        }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d?.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()

      const compPillars = dedup((data.competitor_pillars || []).map(p => ({
        name: p.keyword,
        source: p.source || "competitor",
        intent: p.intent || "purchase",
        final_score: p.final_score ?? 0,
        is_good: p.is_good !== false,
      })))
      const compSupporting = dedup((data.competitor_supporting_keywords || []).map(k => ({
        name: k.keyword,
        pillar: k.pillar || "",
        source: k.source || "competitor",
        intent: k.intent || "informational",
        final_score: k.final_score ?? 0,
        is_good: k.is_good !== false,
      })))

      setCrawlCompPillars(compPillars)
      setCrawlCompSupportingKws(compSupporting)
      setCompetitorCrawlStatus("done")
      clearInterval(compHeartbeat)
      glog(`Stage 2 complete — ${compPillars.length} pillars, ${compSupporting.length} supporting`, "success")
      notify(`Competitor crawl complete — ${compPillars.length} pillars, ${compSupporting.length} supporting`, "success")
      // Auto-save with direct data (React state hasn't flushed yet)
      try { await saveState({ competitor_pillars: compPillars, competitor_supporting: compSupporting }) } catch (_e) { console.warn("Auto-save after competitor crawl failed:", _e) }
      // Merge ALL crawl keywords (Stage 1 + 2) to universe DB
      try {
        await mergeCrawlKeywords({
          pillar_keywords: crawlProducts,
          supporting_keywords: crawlSupportingKws,
          competitor_pillars: compPillars,
          competitor_supporting: compSupporting,
        })
      } catch (_e) { console.warn("Merge-crawl after Stage 2 failed:", _e) }
    } catch (e) {
      clearInterval(compHeartbeat)
      setCompetitorCrawlStatus("error")
      setCrawlErrors([String(e)])
      glog(`Stage 2 FAILED: ${String(e)}`, "error")
      notify("Competitor crawl failed: " + String(e), "error")
    }
  }

  // ── Merge crawl keywords to universe (combined view) ─────────────────────
  const mergeCrawlKeywords = async (data) => {
    if (!ctx.sessionId) return
    setMergingCrawl(true)
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/${ctx.sessionId}/merge-crawl`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(data),
      })
      if (res.ok) {
        const d = await res.json()
        setMergedCrawlCards(d.pillars || [])
        setMergedTotal(d.total || 0)
        setMergedDropped(d.dropped || 0)
        glog(`Combined: ${d.total} keywords across ${(d.pillars||[]).length} pillars (${d.dropped} dropped)`, "success")
        // Refresh pillar cards so Keyword Results section shows merged data
        fetchResults()
      }
    } catch (e) { console.warn("merge-crawl call failed:", e) }
    setMergingCrawl(false)
  }

  // ── Stage 5: AI Score & Cluster — scores all keywords + groups into clusters ──
  const runClusterKeywords = async () => {
    // Gather all keywords from universe or crawl state
    let allForScoring = []
    let confirmedPillars = [
      ...pillars,
      ...crawlProducts.map(p => typeof p === "string" ? p : p.name),
      ...crawlCompPillars.map(p => typeof p === "string" ? p : p.name),
    ].filter((v, i, a) => v && a.indexOf(v) === i)

    let uData = universeData;
    // Prefer universe data if available (Stage 4 was run). If not, implicitly run Stage 4 first!
    if (!uData) {
      uData = await runKeywordUniverse();
    }

    if (uData && uData.all_keywords && uData.all_keywords.length > 0) {
      allForScoring = uData.all_keywords.map(kw => ({
        keyword: kw.keyword, pillar: kw.pillar, source: kw.source,
        intent: kw.intent, keyword_type: kw.keyword_type || "supporting",
      }))
      confirmedPillars = [...new Set([...confirmedPillars, ...(uData.pillars || [])])]
    } else {
      // Fallback to crawl state only if Stage 4 totally failed
      allForScoring = [
        ...crawlProducts.map(p => ({ keyword: typeof p === "string" ? p : p.name, pillar: typeof p === "string" ? p : (p.name || ""), keyword_type: "pillar", source: (p.source || "site_crawl"), intent: (p.intent || "purchase") })),
        ...crawlSupportingKws.map(k => ({ keyword: typeof k === "string" ? k : k.name, pillar: typeof k === "object" ? (k.pillar || confirmedPillars[0] || "") : (confirmedPillars[0] || ""), keyword_type: "supporting", source: (k.source || "site_crawl"), intent: (k.intent || "informational") })),
        ...crawlCompPillars.map(p => ({ keyword: typeof p === "string" ? p : p.name, pillar: typeof p === "string" ? p : (p.name || ""), keyword_type: "pillar", source: (p.source || "competitor"), intent: (p.intent || "purchase") })),
        ...crawlCompSupportingKws.map(k => ({ keyword: typeof k === "string" ? k : k.name, pillar: typeof k === "object" ? (k.pillar || confirmedPillars[0] || "") : (confirmedPillars[0] || ""), keyword_type: "supporting", source: (k.source || "competitor"), intent: (k.intent || "informational") })),
      ].filter(x => x.keyword)
    }

    // If still empty, try DB
    if (allForScoring.length === 0 && ctx.sessionId) {
      glog("No keywords in memory — loading from DB...", "info")
      try {
        const dbRes = await fetch(`${API}/api/ki/${projectId}/review/${ctx.sessionId}?limit=2000&offset=0&sort_by=score_desc`, { headers: authHeaders() })
        if (dbRes.ok) {
          const dbData = await dbRes.json()
          allForScoring = (dbData.keywords || []).map(kw => ({
            keyword: kw.keyword, pillar: kw.pillar_keyword || "",
            source: kw.source || "discovered", intent: kw.intent || "informational",
            keyword_type: kw.keyword_type || "supporting",
          })).filter(x => x.keyword)
          const dbPillars = [...new Set((dbData.keywords || []).map(k => k.pillar_keyword).filter(Boolean))]
          confirmedPillars = [...new Set([...confirmedPillars, ...dbPillars])]
          glog(`Loaded ${allForScoring.length} keywords from DB`, "info")
        }
      } catch (e) { glog(`Failed to load DB keywords: ${e}`, "warn") }
    }

    if (allForScoring.length === 0 || confirmedPillars.length === 0) {
      notify("Run Stages 1-4 first to collect keywords", "error")
      return
    }

    setScoringStatus("running")
    glog(`Stage 5: AI scoring & clustering ${allForScoring.length} keywords across ${confirmedPillars.length} pillars...`, "info")
    const scoreAbort = new AbortController()
    const scoreTimeout = setTimeout(() => { scoreAbort.abort(); glog("Stage 5 timed out after 3 min — proceeding", "warn") }, 180000)
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/cluster-keywords`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        signal: scoreAbort.signal,
        body: JSON.stringify({
          keywords: allForScoring,
          pillars: confirmedPillars,
          per_pillar: 50,
          business_profile: businessProfile || undefined,
          session_id: ctx.sessionId || "",
          preferred_provider: discoveryAiProvider,
        }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d?.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setClusterData(data)
      // Also set topByPillar for compatibility
      const topMap = {}
      for (const [pillar, info] of Object.entries(data.clustered || {})) {
        topMap[pillar] = (info.keywords || [])
      }
      setTopByPillar(topMap)
      setScoringSummary({
        total: data.total_scored || 0,
        good: data.total_kept || Object.values(data.clustered || {}).reduce((sum, p) => sum + (p.top_count || 0), 0),
        bad: data.total_dropped || 0,
      })
      setScoringStatus("done")
      clearTimeout(scoreTimeout)
      glog(`Stage 5 complete — ${data.total_scored} evaluated, ${data.total_kept || "?"} kept, ${data.total_dropped || 0} dropped`, "success")
      notify(`AI validated ${data.total_scored} keywords — kept top ${data.total_kept || "?"}`, "success")
      // Refresh pillar cards so Keyword Results reflects new scores
      await fetchResults()
    } catch (e) {
      clearTimeout(scoreTimeout)
      if (e.name === "AbortError") {
        setScoringStatus("done")
        glog("Stage 5 timed out — proceeding with partial results", "warn")
        notify("Clustering timed out — proceeding", "warn")
      } else {
        setScoringStatus("error")
        glog(`Stage 5 FAILED: ${String(e)}`, "error")
        notify("Clustering failed: " + String(e), "error")
      }
    }
  }

  // ── Stage 4: Keyword Universe — aggregate ALL keywords from all stages ──
  const runKeywordUniverse = async () => {
    let confirmedPillars = [
      ...pillars,
      ...crawlProducts.map(p => typeof p === "string" ? p : p.name),
      ...crawlCompPillars.map(p => typeof p === "string" ? p : p.name),
    ].filter((v, i, a) => v && a.indexOf(v) === i)

    let allKws = [
      ...crawlProducts.map(p => ({ keyword: typeof p === "string" ? p : p.name, pillar: typeof p === "string" ? p : (p.name || ""), keyword_type: "pillar", source: p.source || "site_crawl", intent: p.intent || "purchase" })),
      ...crawlSupportingKws.map(k => ({ keyword: typeof k === "string" ? k : k.name, pillar: typeof k === "object" ? (k.pillar || "") : "", keyword_type: "supporting", source: k.source || "site_crawl", intent: k.intent || "informational" })),
      ...crawlCompPillars.map(p => ({ keyword: typeof p === "string" ? p : p.name, pillar: typeof p === "string" ? p : (p.name || ""), keyword_type: "pillar", source: p.source || "competitor", intent: p.intent || "purchase" })),
      ...crawlCompSupportingKws.map(k => ({ keyword: typeof k === "string" ? k : k.name, pillar: typeof k === "object" ? (k.pillar || "") : "", keyword_type: "supporting", source: k.source || "competitor", intent: k.intent || "informational" })),
    ].filter(x => x.keyword)

    setAiValidateStatus("running")
    glog("Stage 4: Building keyword universe from all sources...", "info")
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/keyword-universe`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          keywords: allKws,
          pillars: confirmedPillars,
          session_id: ctx.sessionId || "",
        }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d?.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setUniverseData(data)
      setAiValidateResult({
        total_scored: data.total_keywords,
        good_keywords: data.total_keywords,
        bad_keywords: 0,
        all_scored: data.all_keywords,
      })
      setAiValidateStatus("done")
      glog(`Stage 4 complete — ${data.total_keywords} keywords across ${data.pillar_count} pillars from ${Object.keys(data.by_source || {}).length} sources`, "success")
      notify(`Keyword Universe: ${data.total_keywords} keywords, ${data.pillar_count} pillars`, "success")
      // Refresh pillar cards so Keyword Results shows universe data
      await fetchResults()
      return data;
    } catch (e) {
      setAiValidateStatus("error")
      glog(`Stage 4 FAILED: ${String(e)}`, "error")
      notify("Keyword Universe failed: " + String(e), "error")
      return null;
    }
  }

  // ── Chip list helpers ───────────────────────────────────────────────────────
  const removeProduct = async (idx) => {
    const item = crawlProducts[idx]
    const name = typeof item === "string" ? item : item?.name
    if (name) await reviewAction("customer", name, "delete")
    setCrawlProducts(p => p.filter((_, i) => i !== idx))
  }
  const markBadProduct = async (idx) => {
    const item = crawlProducts[idx]
    const name = typeof item === "string" ? item : item?.name
    if (name) await reviewAction("customer", name, "bad")
    setCrawlProducts(p => p.filter((_, i) => i !== idx))
    // Cascade: remove all supporting keywords associated with this pillar
    if (name) {
      const lowerName = name.toLowerCase()
      setCrawlSupportingKws(prev => {
        const removed = prev.filter(k => (k.pillar || "").toLowerCase() === lowerName)
        removed.forEach(k => reviewAction("customer", k.name || k, "bad"))
        return prev.filter(k => (k.pillar || "").toLowerCase() !== lowerName)
      })
    }
  }
  const updateProduct = async (idx, val) => {
    const oldItem = crawlProducts[idx]
    const oldName = typeof oldItem === "string" ? oldItem : oldItem?.name
    if (oldName && val && oldName !== val) await reviewAction("customer", oldName, "edit", val)
    setCrawlProducts(p => p.map((it, i) => i === idx ? { ...it, name: val } : it))
  }
  const addProduct = (name) => setCrawlProducts(p => [...p, { name, source: "manual", intent: "purchase", final_score: 50, is_good: true, pillar_tier: "thematic" }])
  // Move pillar → supporting
  const movePillarToSupporting = async (idx) => {
    const item = crawlProducts[idx]
    const name = typeof item === "string" ? item : item.name
    setCrawlProducts(p => p.filter((_, i) => i !== idx))
    setCrawlSupportingKws(p => [...p, { name, source: "moved", intent: item?.intent || "informational" }])
    await reviewAction("customer", name, "move_to_supporting")
  }

  const removeSupportingKw = async (idx) => {
    const item = crawlSupportingKws[idx]
    const name = typeof item === "string" ? item : item?.name
    if (name) await reviewAction("customer", name, "delete")
    setCrawlSupportingKws(p => p.filter((_, i) => i !== idx))
  }
  const markBadSupportingKw = async (idx) => {
    const item = crawlSupportingKws[idx]
    const name = typeof item === "string" ? item : item?.name
    if (name) await reviewAction("customer", name, "bad")
    setCrawlSupportingKws(p => p.filter((_, i) => i !== idx))
  }
  const updateSupportingKw = async (idx, val) => {
    const oldItem = crawlSupportingKws[idx]
    const oldName = typeof oldItem === "string" ? oldItem : oldItem?.name
    if (oldName && val && oldName !== val) await reviewAction("customer", oldName, "edit", val)
    setCrawlSupportingKws(p => p.map((it, i) => i === idx ? { ...it, name: val } : it))
  }
  const addSupportingKw = (name) => setCrawlSupportingKws(p => [...p, { name, source: "manual", intent: "informational", final_score: 0, is_good: true }])
  // Bulk helpers for supporting keywords
  const bulkRemoveSupporting = async (indices) => {
    const sorted = [...indices].sort((a, b) => b - a)
    for (const idx of sorted) {
      const item = crawlSupportingKws[idx]
      const name = typeof item === "string" ? item : item?.name
      if (name) await reviewAction("customer", name, "delete")
    }
    setCrawlSupportingKws(p => p.filter((_, i) => !indices.includes(i)))
  }
  const bulkBadSupporting = async (indices) => {
    const sorted = [...indices].sort((a, b) => b - a)
    for (const idx of sorted) {
      const item = crawlSupportingKws[idx]
      const name = typeof item === "string" ? item : item?.name
      if (name) await reviewAction("customer", name, "bad")
    }
    setCrawlSupportingKws(p => p.filter((_, i) => !indices.includes(i)))
  }
  // Move supporting → pillar
  const moveSupportingToPillar = async (idx) => {
    const item = crawlSupportingKws[idx]
    const name = typeof item === "string" ? item : item.name
    setCrawlSupportingKws(p => p.filter((_, i) => i !== idx))
    setCrawlProducts(p => [...p, { name, source: "moved", intent: item?.intent || "purchase", final_score: 50, is_good: true, pillar_tier: "thematic" }])
    await reviewAction("customer", name, "move_to_pillar")
  }

  const removeCompPillar = async (idx) => {
    const item = crawlCompPillars[idx]
    const name = typeof item === "string" ? item : item?.name
    if (name) await reviewAction("competitor", name, "delete")
    setCrawlCompPillars(p => p.filter((_, i) => i !== idx))
  }
  const markBadCompPillar = async (idx) => {
    const item = crawlCompPillars[idx]
    const name = typeof item === "string" ? item : item?.name
    if (name) await reviewAction("competitor", name, "bad")
    setCrawlCompPillars(p => p.filter((_, i) => i !== idx))
    // Cascade: remove all competitor supporting keywords associated with this pillar
    if (name) {
      const lowerName = name.toLowerCase()
      setCrawlCompSupportingKws(prev => {
        const removed = prev.filter(k => (k.pillar || "").toLowerCase() === lowerName)
        removed.forEach(k => reviewAction("competitor", k.name || k, "bad"))
        return prev.filter(k => (k.pillar || "").toLowerCase() !== lowerName)
      })
    }
  }
  const updateCompPillar = async (idx, val) => {
    const oldItem = crawlCompPillars[idx]
    const oldName = typeof oldItem === "string" ? oldItem : oldItem?.name
    if (oldName && val && oldName !== val) await reviewAction("competitor", oldName, "edit", val)
    setCrawlCompPillars(p => p.map((it, i) => i === idx ? { ...it, name: val } : it))
  }
  const addCompPillar = (name) => setCrawlCompPillars(p => [...p, { name, source: "manual", intent: "purchase", final_score: 0, is_good: true }])
  const moveCompPillarToSupporting = async (idx) => {
    const item = crawlCompPillars[idx]
    const name = typeof item === "string" ? item : item.name
    setCrawlCompPillars(p => p.filter((_, i) => i !== idx))
    setCrawlCompSupportingKws(p => [...p, { name, source: "moved", intent: item?.intent || "informational" }])
    await reviewAction("competitor", name, "move_to_supporting")
  }

  const removeCompSupportingKw = async (idx) => {
    const item = crawlCompSupportingKws[idx]
    const name = typeof item === "string" ? item : item?.name
    if (name) await reviewAction("competitor", name, "delete")
    setCrawlCompSupportingKws(p => p.filter((_, i) => i !== idx))
  }
  const markBadCompSupportingKw = async (idx) => {
    const item = crawlCompSupportingKws[idx]
    const name = typeof item === "string" ? item : item?.name
    if (name) await reviewAction("competitor", name, "bad")
    setCrawlCompSupportingKws(p => p.filter((_, i) => i !== idx))
  }
  const updateCompSupportingKw = async (idx, val) => {
    const oldItem = crawlCompSupportingKws[idx]
    const oldName = typeof oldItem === "string" ? oldItem : oldItem?.name
    if (oldName && val && oldName !== val) await reviewAction("competitor", oldName, "edit", val)
    setCrawlCompSupportingKws(p => p.map((it, i) => i === idx ? { ...it, name: val } : it))
  }
  const addCompSupportingKw = (name) => setCrawlCompSupportingKws(p => [...p, { name, source: "manual", intent: "informational", final_score: 0, is_good: true }])
  // Bulk helpers for competitor supporting keywords
  const bulkRemoveCompSupporting = async (indices) => {
    const sorted = [...indices].sort((a, b) => b - a)
    for (const idx of sorted) {
      const item = crawlCompSupportingKws[idx]
      const name = typeof item === "string" ? item : item?.name
      if (name) await reviewAction("competitor", name, "delete")
    }
    setCrawlCompSupportingKws(p => p.filter((_, i) => !indices.includes(i)))
  }
  const bulkBadCompSupporting = async (indices) => {
    const sorted = [...indices].sort((a, b) => b - a)
    for (const idx of sorted) {
      const item = crawlCompSupportingKws[idx]
      const name = typeof item === "string" ? item : item?.name
      if (name) await reviewAction("competitor", name, "bad")
    }
    setCrawlCompSupportingKws(p => p.filter((_, i) => !indices.includes(i)))
  }
  const moveCompSupportingToPillar = async (idx) => {
    const item = crawlCompSupportingKws[idx]
    const name = typeof item === "string" ? item : item.name
    setCrawlCompSupportingKws(p => p.filter((_, i) => i !== idx))
    setCrawlCompPillars(p => [...p, { name, source: "moved", intent: item?.intent || "purchase", final_score: 50, is_good: true, pillar_tier: "thematic" }])
    await reviewAction("competitor", name, "move_to_pillar")
  }

  const removeTheme = (idx) => setCrawlReviewThemes(p => p.filter((_, i) => i !== idx))
  const updateTheme = (idx, val) => setCrawlReviewThemes(p => p.map((it, i) => i === idx ? val : it))
  const addTheme = (name) => setCrawlReviewThemes(p => [...p, name])

  // ── All pillars = user pillars + crawled products + competitor pillars ─────
  const allPillars = [
    ...pillars,
    ...crawlProducts.map(p => typeof p === "string" ? p : p.name),
    ...crawlCompPillars.map(p => typeof p === "string" ? p : p.name),
  ].filter((v, i, a) => v && a.indexOf(v) === i)

  // ── Start research SSE ──────────────────────────────────────────────────────
  // ── Stage 3: Research SSE (Wikipedia, Google Suggest, cross-multiply) ────
  const startResearch = () => {
    setError("")
    setLogs([])
    setSummary(null)
    setResults([])
    setResultTotal(0)
    setResultStats({})
    setStatus("running")
    // Reset stage 4/5 state so LiveConsole is visible (highestStage must be <= 3)
    setScoringSummary(null)
    setUniverseData(null)
    setClusterData(null)
    glog("Stage 3: Discovering keywords from Wikipedia, Google Suggest, cross-multiply...", "info")

    const ctrl = new AbortController()
    abortRef.current = ctrl

    // Merge manual products with crawled products as additional pillar keywords
    const extraProducts = manualProducts.split(",").map(s => s.trim()).filter(Boolean)
    const allProductNames = [
      ...crawlProducts.map(p => typeof p === "string" ? p : p.name),
      ...extraProducts,
    ].filter((v, i, a) => v && a.indexOf(v) === i)

    fetch(`${API}/api/ki/${projectId}/research/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        session_id: ctx.sessionId,
        business_intent: Array.isArray(businessIntent) ? businessIntent : [businessIntent],
        customer_url: customerUrl,
        competitor_urls: competitorUrls,
        products: allProductNames,
        seasonal_events: seasonalEvents,
        preferred_provider: discoveryAiProvider,
        customer_review_areas: [
          ...reviewAreas.split(",").map(s => s.trim()).filter(Boolean),
          ...crawlReviewThemes,
        ].filter((v, i, a) => v && a.indexOf(v) === i),
        // Send all pillars including crawled ones
        extra_pillars: allPillars.filter(p => !pillars.includes(p)),
      }),
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          const d = await res.json().catch(() => ({}))
          setError(d?.detail || `HTTP ${res.status}`)
          setStatus("failed")
          notify("Discovery failed: " + (d?.detail || `HTTP ${res.status}`), "error")
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
              const evt = JSON.parse(raw)
              if (evt.type === "log") {
                setLogs(prev => [...prev.slice(-499), evt])
              } else if (evt.type === "complete") {
                const kw = evt.keywords || []
                setSummary(evt.summary || { total: kw.length })
                setStatus("completed")
                ctx.setStep(2, { keyword_count: kw.length })
                ctx.flush(projectId).catch(() => {})
                glog(`Stage 3 complete — ${kw.length} keywords discovered`, "success")
                notify(`Discovery complete — ${kw.length} keywords found`, "success")
                // Auto-load results
                fetchResults()
              } else if (evt.type === "error") {
                setError(evt.msg || "Research failed")
                setStatus("failed")
                glog(`Stage 3 FAILED: ${evt.msg || "Research failed"}`, "error")
                notify("Discovery error: " + (evt.msg || "Research failed"), "error")
              }
            } catch { /* ignore parse errors */ }
          }
        }
        // Flush remaining buffer
        if (buf.trim().startsWith("data: ")) {
          try {
            const evt = JSON.parse(buf.trim().slice(6))
            if (evt.type === "complete") {
              const kw = evt.keywords || []
              setSummary(evt.summary || { total: kw.length })
              setStatus("completed")
              ctx.setStep(2, { keyword_count: kw.length })
              ctx.flush(projectId).catch(() => {})
            }
          } catch { /* ignore */ }
        }
        setStatus(s => s === "running" ? "completed" : s)
        fetchResults()
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError("Connection error: " + String(e))
          setStatus("failed")
          glog(`Stage 3 connection error: ${String(e)}`, "error")
          notify("Discovery connection error", "error")
        }
      })
  }

  // ── Fetch results from DB ───────────────────────────────────────────────────
  const fetchAbortRef = useRef(null)
  const fetchResults = useCallback(async () => {
    if (!ctx.sessionId) return
    // Abort any in-flight fetch to prevent race conditions
    fetchAbortRef.current?.abort()
    const ctrl = new AbortController()
    fetchAbortRef.current = ctrl
    setLoadingResults(true)
    try {
      // Fetch pillar cards view
      const cardsRes = await fetch(`${API}/api/ki/${projectId}/universe/${ctx.sessionId}/pillar-cards`, {
        headers: authHeaders(), signal: ctrl.signal,
      })
      if (cardsRes.ok) {
        const cardsData = await cardsRes.json()
        const pillars = cardsData.pillars || []
        setPillarCards(pillars)
        setResultTotal(cardsData.total || 0)
        setResultStats(cardsData.stats || {})
        // Also set flat results for table view compatibility
        const flatKws = pillars.flatMap(p =>
          (p.keywords || []).map(k => ({ ...k, pillar_keyword: p.pillar, opportunity_score: k.score }))
        )
        setResults(flatKws)

        // Restore stage completion states from data (e.g., on page revisit)
        if (pillars.length > 0) {
          setStatus(prev => prev || "completed")
          const hasScores = pillars.some(p => (p.avg_score || 0) > 0)
          if (hasScores) {
            setScoringStatus(prev => prev || "done")
            setScoringSummary(prev => prev || { total: cardsData.total || 0, good: cardsData.total || 0 })
          }
        }
      }
    } catch (e) { if (e.name !== "AbortError") { /* ignore network errors */ } }
    setLoadingResults(false)
  }, [projectId, ctx.sessionId])

  // Refetch when filters/page change — only after discovery complete
  useEffect(() => {
    if (status === "completed") fetchResults()
  }, [fetchResults, status])

  // Also load results on mount if previously completed
  useEffect(() => {
    if (!status && ctx.step2?.keyword_count) {
      setStatus("completed")
      fetchResults()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctx.step2?.keyword_count])

  // Always try to load pillar cards on mount — restores results from DB on revisit
  useEffect(() => {
    if (ctx.sessionId && projectId) fetchResults()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, ctx.sessionId])

  // ── Results action handlers ────────────────────────────────────────────────
  const bulkAction = async (action, itemIds, pillar) => {
    if (!ctx.sessionId) return
    setBulkLoading(true)
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/review/${ctx.sessionId}/bulk-action`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ action, item_ids: itemIds || [], pillar }),
      })
      if (res.ok) {
        const d = await res.json()
        notify(`${action}: ${d.affected} keywords`, "success")
        setSelectedKws(new Set())
        await fetchResults()
      }
    } catch (e) { notify("Action failed: " + e, "error") }
    setBulkLoading(false)
  }

  const renamePillar = async (oldName, newName) => {
    if (!ctx.sessionId || !newName.trim()) return
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/review/${ctx.sessionId}/rename-pillar`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ old_name: oldName, new_name: newName.trim() }),
      })
      if (res.ok) {
        notify(`Renamed "${oldName}" → "${newName.trim()}"`, "success")
        setRenamingPillar(null)
        await fetchResults()
      }
    } catch (e) { notify("Rename failed: " + e, "error") }
  }

  const deletePillar = async (pillar) => {
    if (!ctx.sessionId) return
    if (!confirm(`Delete pillar "${pillar}" and all its keywords?`)) return
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/review/${ctx.sessionId}/delete-pillar`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ pillar }),
      })
      if (res.ok) {
        const d = await res.json()
        notify(`Deleted "${pillar}" (${d.deleted} keywords)`, "success")
        await fetchResults()
      }
    } catch (e) { notify("Delete failed: " + e, "error") }
  }

  const moveSelectedToTarget = async (targetPillar) => {
    if (!ctx.sessionId || selectedKws.size === 0) return
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/review/${ctx.sessionId}/move-keywords`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ item_ids: [...selectedKws], target_pillar: targetPillar }),
      })
      if (res.ok) {
        const d = await res.json()
        notify(`Moved ${d.moved} keywords to "${targetPillar}"`, "success")
        setSelectedKws(new Set())
        setMovingTo(null)
        await fetchResults()
      }
    } catch (e) { notify("Move failed: " + e, "error") }
  }

  const rescorePillar = async (pillar) => {
    setRescoreTarget(pillar)
    // Gather keywords for just this pillar, then run cluster-keywords
    const pillarKws = pillar === "all"
      ? pillarCards.flatMap(p => p.keywords.map(k => ({ keyword: k.keyword, pillar: p.pillar, source: k.source, intent: k.intent, keyword_type: k.type })))
      : (pillarCards.find(p => p.pillar === pillar)?.keywords || []).map(k => ({
          keyword: k.keyword, pillar: pillar, source: k.source, intent: k.intent, keyword_type: k.type
        }))
    const confirmedPillars = pillar === "all" ? pillarCards.map(p => p.pillar) : [pillar]
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/cluster-keywords`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ keywords: pillarKws, pillars: confirmedPillars, per_pillar: 100 }),
        signal: AbortSignal.timeout(180000),
      })
      if (res.ok) {
        const d = await res.json()
        notify(`Re-scored: ${d.total_scored} keywords`, "success")
        await fetchResults()
      }
    } catch (e) { notify("Re-score failed: " + e, "error") }
    setRescoreTarget(null)
  }

  const handleContinue = async () => {
    // Auto-accept all discovered/pending keywords so pipeline can use them
    if (ctx.sessionId) {
      try {
        await fetch(`${API}/api/ki/${projectId}/review/${ctx.sessionId}/accept-all`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({}),
        })
      } catch (_e) { console.warn("Auto-accept failed:", _e) }
    }

    if (scoringSummary?.good) {
      ctx.setStep(2, { keyword_count: scoringSummary.good })
      await ctx.flush(projectId).catch(() => {})
    }
    try {
      const res = await fetch(`${API}/api/ki/${projectId}/workflow-status`, { headers: authHeaders() })
      const data = res.ok ? await res.json() : {}
      if (data?.keyword_count) {
        ctx.setStep(2, { keyword_count: data.keyword_count })
        await ctx.flush(projectId).catch(() => {})
      }
    } catch { /* ignore */ }
    if (onComplete) onComplete()
  }

  // ── Stage status helper ────────────────────────────────────────────────────
  const StageHeader = ({ num, title, subtitle, status: st, color = "#007AFF" }) => {
    const statusConfig = {
      running: { label: "Running…", bg: "#fef3c7", color: "#92400e", dot: "#f59e0b" },
      done: { label: "Done", bg: "#d1fae5", color: "#065f46", dot: "#10b981" },
      completed: { label: "Done", bg: "#d1fae5", color: "#065f46", dot: "#10b981" },
      error: { label: "Failed", bg: "#fee2e2", color: "#991b1b", dot: "#ef4444" },
      failed: { label: "Failed", bg: "#fee2e2", color: "#991b1b", dot: "#ef4444" },
      crawling: { label: "Running…", bg: "#fef3c7", color: "#92400e", dot: "#f59e0b" },
    }
    const sc = statusConfig[st] || null
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <div style={{
          width: 28, height: 28, borderRadius: "50%", background: color, color: "#fff",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, fontWeight: 800, flexShrink: 0,
        }}>{num}</div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
            {title}
            {sc && (
              <span style={{
                fontSize: 10, padding: "2px 8px", borderRadius: 10, fontWeight: 700,
                background: sc.bg, color: sc.color, display: "flex", alignItems: "center", gap: 4,
              }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: sc.dot, display: "inline-block" }} />
                {sc.label}
              </span>
            )}
          </div>
          {subtitle && <div style={{ fontSize: 11, color: T.textSoft }}>{subtitle}</div>}
        </div>
      </div>
    )
  }

  const stageBox = (borderColor = "#e5e7eb") => ({
    border: `1.5px solid ${borderColor}`, borderRadius: 12, padding: 18, marginBottom: 14,
    background: "#fff", boxShadow: borderColor !== "#e5e7eb" ? `0 1px 6px ${borderColor}18` : "none",
    transition: "box-shadow 0.2s, border-color 0.2s",
  })

  return (
    <div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } } @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>

      {/* ═══ GLOBAL ENGINE CONSOLE ═══════════════════════════════════════════════ */}
      {globalLogs.length > 0 && (
        <div style={{
          marginBottom: 12, border: "1.5px solid #374151", borderRadius: 10, overflow: "hidden",
          background: "#0f172a",
        }}>
          <div style={{
            padding: "8px 12px", display: "flex", alignItems: "center", justifyContent: "space-between",
            background: "#1e293b",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%", display: "inline-block",
                background: (crawlStatus === "crawling" || competitorCrawlStatus === "crawling" || status === "running" || scoringStatus === "running" || aiValidateStatus === "running")
                  ? "#10b981" : "#374151",
                animation: (crawlStatus === "crawling" || competitorCrawlStatus === "crawling" || status === "running" || scoringStatus === "running" || aiValidateStatus === "running")
                  ? "pulse 1.2s infinite" : "none",
              }} />
              <span style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: 1 }}>ENGINE CONSOLE</span>
              <span style={{ fontSize: 10, color: "#475569" }}>— all stages</span>
            </div>
            <button onClick={() => setGlobalLogs([])} style={{
              background: "none", border: "none", color: "#475569", cursor: "pointer", fontSize: 11,
            }}>clear</button>
          </div>
          <div ref={el => { if (el) el.scrollTop = el.scrollHeight }} style={{ maxHeight: 160, overflowY: "auto", padding: "8px 12px", fontFamily: "monospace", fontSize: 11 }}>
            {globalLogs.map((entry, i) => (
              <div key={i} style={{
                color: entry.level === "error" ? "#f87171" : entry.level === "warn" ? "#fbbf24" : entry.level === "success" ? "#4ade80" : "#94a3b8",
                padding: "1px 0",
              }}>
                <span style={{ color: "#475569", marginRight: 6 }}>{new Date(entry.ts).toLocaleTimeString()}</span>
                {entry.level === "error" ? "✗" : entry.level === "success" ? "✓" : entry.level === "warn" ? "⚠" : "›"} {entry.msg}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ═══ MAIN CARD ═══════════════════════════════════════════════════════════ */}
      <Card style={{ marginBottom: 16, borderTop: "3px solid #007AFF" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: "#1e293b" }}>Step 2 — Keyword Discovery</div>
            <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
              6-stage pipeline: crawl → discover → AI validate → rank → strategy
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {(crawlStatus === "done" || competitorCrawlStatus === "done") && (
              <Btn onClick={saveState} disabled={saveStatus === "saving"} style={{
                fontSize: 11, padding: "4px 10px",
                background: saveStatus === "saved" ? "#d1fae5" : undefined,
                color: saveStatus === "saved" ? "#065f46" : undefined,
              }}>
                {saveStatus === "saving" ? <><Spinner /> Saving…</> : saveStatus === "saved" ? "✓ Saved" : "💾 Save"}
              </Btn>
            )}
            <Btn onClick={onBack}>← Back</Btn>
          </div>
        </div>

        {/* Step 1 Context Bar */}
        <div style={{
          background: "linear-gradient(90deg, #f8fafc, #f1f5f9)", borderRadius: 10, padding: "10px 14px", marginBottom: 16,
          fontSize: 11, color: T.textSoft, display: "flex", flexWrap: "wrap", gap: "6px 18px",
          border: "1px solid #e2e8f0",
        }}>
          <span>Session: <code>{ctx.sessionId?.slice(-12) || "—"}</code></span>
          <span>Pillars: <strong>{pillars.join(", ") || "—"}</strong></span>
          {customerUrl && <span>Site: {customerUrl.replace(/^https?:\/\//, "")}</span>}
          {competitorUrls.length > 0 && <span>Competitors: {competitorUrls.length}</span>}
          <span>Intent: <strong>{Array.isArray(businessIntent) ? businessIntent.join(", ") : businessIntent}</strong></span>
        </div>

        {/* ─── STAGE 0: Strategy Context ─────────────────────────────────────── */}
        <div style={stageBox("#d1d5db")}>
          <StageHeader num="★" title="Strategy Context" subtitle="Feeds into all stages — add extra products, review areas, seasonal focus" color="#6b7280" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, display: "block", marginBottom: 3 }}>Extra Products / Services</label>
              <input value={manualProducts} onChange={e => setManualProducts(e.target.value)}
                placeholder="e.g. Cinnamon powder, Turmeric (comma separated)"
                style={{ width: "100%", padding: "6px 8px", borderRadius: 6, fontSize: 11, border: `1px solid ${T.border}`, boxSizing: "border-box" }} />
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, display: "block", marginBottom: 3 }}>Customer Review Areas</label>
              <input value={reviewAreas} onChange={e => setReviewAreas(e.target.value)}
                placeholder="e.g. Quality, Taste, Packaging, Delivery"
                style={{ width: "100%", padding: "6px 8px", borderRadius: 6, fontSize: 11, border: `1px solid ${T.border}`, boxSizing: "border-box" }} />
            </div>
          </div>
          <div style={{ marginTop: 8 }}>
            <label style={{ fontSize: 11, fontWeight: 600, display: "block", marginBottom: 4 }}>Seasonal Events</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
              {SEASONAL_PRESETS.map(ev => (
                <button key={ev} onClick={() => toggleSeasonal(ev)} style={{
                  padding: "3px 9px", borderRadius: 6, fontSize: 10, cursor: "pointer",
                  border: `1px solid ${seasonalEvents.includes(ev) ? T.teal : T.border}`,
                  background: seasonalEvents.includes(ev) ? T.tealLight : "#fff",
                  color: seasonalEvents.includes(ev) ? T.teal : T.textSoft,
                  fontWeight: seasonalEvents.includes(ev) ? 600 : 400,
                }}>{ev}</button>
              ))}
            </div>
          </div>
        </div>

        {/* ─── STAGE 1: Crawl My Website ─────────────────────────────────────── */}
        <div style={stageBox(crawlStatus === "done" ? "#10b981" : crawlStatus === "error" ? "#ef4444" : "#e5e7eb")}>
          <StageHeader num="1" title="Crawl My Website" subtitle="Extract product pillars & supporting keywords from your site pages"
            status={crawlStatus} color="#0d9488" />
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
            <Btn variant="teal" onClick={doCustomerCrawl} disabled={crawlStatus === "crawling" || !customerUrl}>
              {crawlStatus === "crawling" ? <><Spinner /> Crawling…</> : crawlStatus === "done" ? "Re-Crawl Site" : "Crawl My Website"}
            </Btn>
            {!customerUrl && <span style={{ fontSize: 11, color: "#dc2626" }}>No website URL configured in Step 1</span>}
            {customerUrl && crawlStatus !== "crawling" && (
              <span style={{ fontSize: 11, color: T.textSoft }}>{customerUrl.replace(/^https?:\/\//, "")}</span>
            )}
          </div>

          {crawlStatus === "crawling" && (
            <div style={{ textAlign: "center", padding: 16, color: T.textSoft, fontSize: 12 }}>
              <Spinner /> <span style={{ marginLeft: 8 }}>Crawling your website (home, product, about, blog pages)…</span>
            </div>
          )}

          {crawlErrors.length > 0 && (
            <div style={{ padding: "6px 10px", background: "#fef2f2", borderRadius: 6, marginBottom: 8, fontSize: 11, color: "#991b1b" }}>
              {crawlErrors.map((e, i) => <div key={i}>⚠ {e}</div>)}
            </div>
          )}

          {crawlStatus === "done" && (
            <div style={{ display: "grid", gap: 10 }}>
              {businessProfile && (
                <div style={{ padding: "6px 10px", background: T.grayLight, borderRadius: 7, fontSize: 11, color: T.textSoft }}>
                  <strong>Business:</strong> {businessProfile.business_name || "—"}{businessProfile.business_type ? ` (${businessProfile.business_type})` : ""}
                  {Object.keys(pageBreakdown || {}).length > 0 && (
                    <span style={{ marginLeft: 8 }}>| Pages: {Object.entries(pageBreakdown).map(([k, v]) => `${k}:${v}`).join(", ")}</span>
                  )}
                </div>
              )}

              {/* Show detailed crawl results ONLY if not yet combined into Stage 2+ */}
              {(highestStage <= 1 || showCrawlDetail) ? (
                <>
                  <div style={{ padding: 10, background: T.purpleLight, borderRadius: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, flexWrap: "wrap" }}>
                  <Badge color={T.purple}>PILLAR KEYWORDS ({crawlProducts.length})</Badge>
                  <span style={{ fontSize: 10, color: T.textSoft }}>
                    Click to edit · ↓ to Supporting · ✕ bad · × delete ·
                    <span style={{ background: "#d97706", color: "#fff", padding: "1px 4px", borderRadius: 3, fontSize: 9, fontWeight: 700, marginLeft: 4 }}>★100</span> product
                    <span style={{ background: "#2563eb", color: "#fff", padding: "1px 4px", borderRadius: 3, fontSize: 9, fontWeight: 700, marginLeft: 4 }}>◈50</span> category
                  </span>
                </div>
                <ChipList items={crawlProducts} onRemove={removeProduct} onUpdate={updateProduct}
                  onMarkBad={markBadProduct} onMove={movePillarToSupporting} moveLabel="→ Supporting"
                  color={T.purple} emptyText="No products detected — add manually" />
                <AddInput onAdd={addProduct} placeholder="Add pillar keyword…" />
              </div>

              <div style={{ padding: 10, background: "#fffbeb", borderRadius: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                  <Badge color="#d97706">SUPPORTING KEYWORDS ({crawlSupportingKws.length})</Badge>
                  <span style={{ fontSize: 10, color: T.textSoft }}>Grouped by pillar · sorted by score · click to edit · checkboxes for bulk</span>
                </div>
                <SupportingTable items={crawlSupportingKws} pillars={allPillars}
                  onRemove={removeSupportingKw} onUpdate={updateSupportingKw}
                  onMove={moveSupportingToPillar} onMarkBad={markBadSupportingKw}
                  onBulkRemove={bulkRemoveSupporting} onBulkBad={bulkBadSupporting}
                  stage="customer" color="#d97706" />
                <AddInput onAdd={addSupportingKw} placeholder="Add supporting keyword…" />
              </div>
                </>
              ) : (
                <div style={{ padding: "10px 14px", background: "#d1fae5", borderRadius: 8, fontSize: 12, color: "#065f46", display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 700 }}>✓ {crawlProducts.length} pillars + {crawlSupportingKws.length} supporting keywords</span>
                  <span style={{ color: "#047857" }}>→ Combined into Stage 2 results below</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ─── STAGE 2: Crawl Competitors ────────────────────────────────────── */}
        <div style={stageBox(competitorCrawlStatus === "done" ? "#10b981" : competitorCrawlStatus === "error" ? "#ef4444" : "#e5e7eb")}>
          <StageHeader num="2" title="Crawl Competitors" subtitle="Find competitor pillars & supporting keywords using your confirmed pillars"
            status={competitorCrawlStatus} color="#e11d48" />
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
            <Btn variant="primary" onClick={doCompetitorCrawl}
              disabled={competitorCrawlStatus === "crawling" || crawlStatus !== "done" || competitorUrls.length === 0}>
              {competitorCrawlStatus === "crawling" ? <><Spinner /> Crawling…</> : "Crawl Competitors"}
            </Btn>
            {crawlStatus !== "done" && <span style={{ fontSize: 11, color: T.textSoft }}>Complete Stage 1 first</span>}
            {competitorUrls.length === 0 && crawlStatus === "done" && (
              <span style={{ fontSize: 11, color: "#dc2626" }}>No competitor URLs configured in Step 1</span>
            )}
          </div>

          {competitorCrawlStatus === "crawling" && (
            <div style={{ textAlign: "center", padding: 16, color: T.textSoft, fontSize: 12 }}>
              <Spinner /> <span style={{ marginLeft: 8 }}>Crawling competitors with your pillar keywords…</span>
            </div>
          )}

          {competitorCrawlStatus === "done" && (
            <div style={{ display: "grid", gap: 10 }}>
              {/* Show detailed competitor results ONLY if combined not yet shown */}
              {(highestStage <= 2 && mergedCrawlCards.length === 0) || showCrawlDetail ? (
                <>
              <div style={{ padding: 10, background: "#fff1f2", borderRadius: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                  <Badge color="#e11d48">COMPETITOR PILLARS ({crawlCompPillars.length})</Badge>
                  <span style={{ fontSize: 10, color: T.textSoft }}>Click to edit · ↓ to Supporting · ✕ bad · × delete</span>
                </div>
                <ChipList items={crawlCompPillars} onRemove={removeCompPillar} onUpdate={updateCompPillar}
                  onMarkBad={markBadCompPillar} onMove={moveCompPillarToSupporting} moveLabel="→ Supporting"
                  color="#e11d48" emptyText="No competitor pillar keywords found" />
                <AddInput onAdd={addCompPillar} placeholder="Add competitor pillar…" />
              </div>

              <div style={{ padding: 10, background: "#fff7ed", borderRadius: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                  <Badge color="#ea580c">COMPETITOR SUPPORTING ({crawlCompSupportingKws.length})</Badge>
                  <span style={{ fontSize: 10, color: T.textSoft }}>Grouped by pillar · sorted by score · checkboxes for bulk</span>
                </div>
                <SupportingTable items={crawlCompSupportingKws} pillars={allPillars}
                  onRemove={removeCompSupportingKw} onUpdate={updateCompSupportingKw}
                  onMove={moveCompSupportingToPillar} onMarkBad={markBadCompSupportingKw}
                  onBulkRemove={bulkRemoveCompSupporting} onBulkBad={bulkBadCompSupporting}
                  stage="competitor" color="#ea580c" />
                <AddInput onAdd={addCompSupportingKw} placeholder="Add competitor supporting keyword…" />
              </div>
                </>
              ) : (
                <div style={{ padding: "8px 14px", background: "#f1f5f9", borderRadius: 8, fontSize: 11, color: "#475569", display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 700, color: "#1e293b" }}>✓ {crawlCompPillars.length} pillars + {crawlCompSupportingKws.length} supporting keywords</span>
                  <span style={{ color: "#94a3b8" }}>—</span>
                  <span style={{ color: "#64748b" }}>{highestStage > 2 ? "merged into results" : "combined below"}</span>
                  <button onClick={() => setShowCrawlDetail(v => !v)}
                    style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", fontSize: 11, color: "#007AFF", padding: "0 4px", fontWeight: 600 }}>
                    {showCrawlDetail ? "▲ Hide" : "▼ Show details"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ─── COMBINED CRAWL RESULTS (Stage 1+2 merged) ─────────────────────── */}
        {(mergedCrawlCards.length > 0 || mergingCrawl) && (
          <div style={{ padding: 16, background: "linear-gradient(135deg, rgba(0,122,255,0.1) 0%, #dbeafe 100%)", borderRadius: 12, border: "2px solid #007AFF" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 18 }}>📊</span>
                <span style={{ fontWeight: 800, fontSize: 14, color: "#4c1d95" }}>Combined Discovery (Stage 1 + 2)</span>
              </div>
              {mergingCrawl && <Spinner />}
              {!mergingCrawl && mergedCrawlCards.length > 0 && (
                <div style={{ display: "flex", gap: 12, fontSize: 11, color: "#64748b" }}>
                  <span>Total: <strong style={{ color: "#4c1d95" }}>{mergedTotal}</strong></span>
                  <span><strong>{mergedCrawlCards.length}</strong> pillars</span>
                  {mergedDropped > 0 && <span style={{ color: "#dc2626" }}>{mergedDropped} dropped (low quality)</span>}
                </div>
              )}
            </div>

            {mergingCrawl && (
              <div style={{ textAlign: "center", padding: 12, color: "#64748b", fontSize: 12 }}>
                Merging and scoring crawl keywords…
              </div>
            )}

            <div style={{ display: "grid", gap: 8 }}>
              {mergedCrawlCards.map(pillar => {
                const isOpen = mergedExpanded.has(pillar.pillar)
                const toggleMerged = () => setMergedExpanded(prev => {
                  const next = new Set(prev)
                  next.has(pillar.pillar) ? next.delete(pillar.pillar) : next.add(pillar.pillar)
                  return next
                })
                return (
                  <div key={pillar.pillar} style={{
                    border: `1.5px solid ${isOpen ? "#007AFF" : "rgba(0,122,255,0.3)"}`,
                    borderRadius: 10, overflow: "hidden", background: "#fff",
                  }}>
                    <div onClick={toggleMerged} style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "10px 14px", cursor: "pointer", userSelect: "none",
                      background: isOpen ? "rgba(0,122,255,0.06)" : "#fefce8",
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 14, transform: isOpen ? "rotate(90deg)" : "rotate(0)", transition: "transform 0.15s" }}>▸</span>
                        <span style={{ fontWeight: 700, fontSize: 13, color: "#1e293b" }}>{pillar.pillar}</span>
                        <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 10, fontWeight: 700, background: "rgba(0,122,255,0.1)", color: "#007AFF" }}>
                          {pillar.total} kw
                        </span>
                      </div>
                      <div style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 10 }}>
                        <span style={{ color: "#64748b" }}>Avg: <strong style={{ color: pillar.avg_score >= 60 ? "#059669" : pillar.avg_score >= 40 ? "#d97706" : "#dc2626" }}>{pillar.avg_score}</strong></span>
                        <span style={{ color: "#64748b" }}>Top: <strong style={{ color: "#059669" }}>{pillar.top_score}</strong></span>
                      </div>
                    </div>
                    {isOpen && (
                      <div style={{ padding: "0 4px 6px 4px" }}>
                        <div style={{
                          display: "grid", gridTemplateColumns: "1fr 80px 80px 55px",
                          gap: 4, padding: "6px 10px", fontSize: 9, fontWeight: 700, color: "#64748b",
                          borderBottom: "1px solid #e2e8f0", textTransform: "uppercase",
                        }}>
                          <span>Keyword</span><span style={{ textAlign: "center" }}>Intent</span>
                          <span style={{ textAlign: "center" }}>Source</span><span style={{ textAlign: "right" }}>Score</span>
                        </div>
                        <div style={{ maxHeight: 300, overflowY: "auto" }}>
                          {(pillar.keywords || []).map((kw, ki) => (
                            <div key={ki} style={{
                              display: "grid", gridTemplateColumns: "1fr 80px 80px 55px",
                              gap: 4, alignItems: "center", padding: "5px 10px", fontSize: 11,
                              borderBottom: "1px solid #f1f5f9",
                            }}>
                              <span style={{ fontWeight: 500, color: "#1e293b" }}>{kw.keyword}</span>
                              <span style={{ textAlign: "center" }}>
                                <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 4, background: intentColor(kw.intent) + "22", color: intentColor(kw.intent), fontWeight: 600 }}>
                                  {kw.intent}
                                </span>
                              </span>
                              <span style={{ textAlign: "center" }}>
                                <span style={{ fontSize: 9, padding: "1px 4px", borderRadius: 4, background: (SOURCE_COLORS[kw.source] || "#94a3b8") + "22", color: SOURCE_COLORS[kw.source] || "#94a3b8", fontWeight: 600 }}>
                                  {kw.source}
                                </span>
                              </span>
                              <span style={{
                                textAlign: "right", fontWeight: 800, fontSize: 12,
                                color: kw.score >= 70 ? "#059669" : kw.score >= 50 ? "#d97706" : kw.score >= 30 ? "#ea580c" : "#dc2626",
                              }}>{kw.score}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {mergedCrawlCards.length > 0 && (
              <div style={{ marginTop: 8, fontSize: 10, color: "#64748b", textAlign: "center" }}>
                ✓ These keywords are saved and will be included in Stage 3+ results
              </div>
            )}
          </div>
        )}

        {/* ─── STAGE 3: Discover Keywords ─────────────────────────────────────── */}
        <div style={stageBox(status === "completed" ? "#10b981" : status === "failed" ? "#ef4444" : "#e5e7eb")}>
          <StageHeader num="3" title="Discover Keywords" subtitle="Wikipedia, Google Suggest, cross-multiply — streams results live"
            status={status} color="#007AFF" />
          {/* AI Provider selector */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 11, color: T.textSoft, fontWeight: 600, whiteSpace: "nowrap" }}>AI for scoring:</span>
            <AiProviderSelect value={discoveryAiProvider} onChange={setDiscoveryAiProvider} />
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
            {status !== "running" && (
              <Btn variant="primary" onClick={startResearch}>
                {status === "completed" ? "Re-Discover" : "Discover Keywords"}
              </Btn>
            )}
            {status === "running" && (
              <Btn variant="danger" onClick={() => { abortRef.current?.abort(); setStatus("failed"); setError("Cancelled") }}>
                Stop
              </Btn>
            )}
            {allPillars.length > 0 && (
              <span style={{ fontSize: 11, color: T.textSoft }}>
                {allPillars.length} pillar{allPillars.length !== 1 ? "s" : ""} will be searched
                {crawlProducts.length > 0 && ` (incl. ${crawlProducts.length} from crawl)`}
              </span>
            )}
          </div>

          {highestStage <= 3 ? (
            <>
          <LiveConsole logs={logs} running={status === "running"} title="DISCOVERY STREAM" />

          {error && (
            <div style={{ padding: "8px 12px", background: "#fee2e2", borderRadius: 7, fontSize: 11, color: "#991b1b", marginTop: 8 }}>
              {error}
            </div>
          )}

          {summary && (
            <div style={{ padding: "8px 12px", background: "#d1fae5", borderRadius: 7, fontSize: 11, color: "#065f46", marginTop: 8, display: "flex", gap: 12, flexWrap: "wrap" }}>
              <strong>✓ {summary.total || resultTotal || 0} keywords discovered</strong>
              {summary.by_source && Object.entries(summary.by_source).map(([src, cnt]) => (
                <span key={src} style={{
                  padding: "1px 6px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                  background: (SOURCE_COLORS[src] || "#94a3b8") + "22",
                  color: SOURCE_COLORS[src] || "#94a3b8",
                }}>{src}: {cnt}</span>
              ))}
            </div>
          )}
            </>
          ) : (
            status === "completed" && (
              <div style={{ padding: "10px 14px", background: "#d1fae5", borderRadius: 8, fontSize: 12, color: "#065f46", display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontWeight: 700 }}>✓ {summary?.total || resultTotal || 0} keywords discovered</span>
                <span style={{ color: "#047857" }}>→ Combined into Keyword Universe below</span>
              </div>
            )
          )}
        </div>

        {/* ─── STAGE 4: Keyword Universe ──────────────────────────────── */}
        <div style={stageBox(aiValidateStatus === "done" ? "#10b981" : aiValidateStatus === "error" ? "#ef4444" : "#e5e7eb")}>
          <StageHeader num="4" title="Keyword Universe" subtitle="Aggregates ALL keywords from Crawl + Competitors + Discovery — grouped by pillar. No keywords removed."
            status={aiValidateStatus} color="#0ea5e9" />
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: universeData ? 10 : 0 }}>
            <Btn onClick={runKeywordUniverse} disabled={aiValidateStatus === "running"} style={{
              background: "#0ea5e9", color: "#fff", border: "none",
            }}>
              {aiValidateStatus === "running" ? <><Spinner /> Building Universe…</> : aiValidateStatus === "done" ? "Refresh Universe" : "Build Keyword Universe"}
            </Btn>
          </div>
          {universeData && (
            highestStage <= 4 ? (
            <>
              {/* Summary stats */}
              <div style={{ padding: "10px 14px", background: "#f0f9ff", borderRadius: 7, fontSize: 12, color: "#0c4a6e", display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 10 }}>
                <span><strong>{universeData.total_keywords}</strong> total keywords</span>
                <span><strong>{universeData.pillar_count}</strong> pillars</span>
                {Object.entries(universeData.by_source || {}).map(([src, cnt]) => (
                  <span key={src} style={{ opacity: 0.8 }}>{src}: <strong>{cnt}</strong></span>
                ))}
              </div>

              {/* Pillar accordion */}
              <div style={{ display: "grid", gap: 6, maxHeight: 450, overflowY: "auto" }}>
                {Object.entries(universeData.by_pillar || {}).sort((a, b) => b[1].count - a[1].count).map(([pillarName, info]) => (
                  <details key={pillarName} style={{ background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0", padding: "6px 10px" }}>
                    <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 700, color: "#1e40af", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span>🏷️ {pillarName}</span>
                      <span style={{ fontWeight: 400, color: "#64748b", fontSize: 11 }}>{info.count} keywords</span>
                    </summary>
                    <div style={{ marginTop: 6 }}>
                      {(info.keywords || []).map((kw, i) => (
                        <div key={i} style={{
                          display: "grid", gridTemplateColumns: "1fr auto auto", gap: 8,
                          alignItems: "center", fontSize: 11, padding: "3px 0",
                          borderTop: i ? "1px solid #e2e8f0" : "none",
                        }}>
                          <span>{kw.keyword}</span>
                          <span style={{ color: intentColor(kw.intent), fontSize: 10, fontWeight: 600 }}>{kw.intent}</span>
                          <span style={{ fontSize: 9, color: "#94a3b8", background: "#f1f5f9", padding: "1px 6px", borderRadius: 4 }}>{kw.source}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            </>
            ) : (
              <div style={{ padding: "10px 14px", background: "#d1fae5", borderRadius: 8, fontSize: 12, color: "#065f46", display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontWeight: 700 }}>✓ {universeData.total_keywords} keywords · {universeData.pillar_count} pillars</span>
                <span style={{ color: "#047857" }}>→ Scored & clustered in Stage 5 below</span>
              </div>
            )
          )}
        </div>

        {/* ─── STAGE 5: AI Score & Cluster ──────────────────────────────────── */}
        <div style={stageBox(scoringStatus === "done" ? "#10b981" : scoringStatus === "error" ? "#ef4444" : "#e5e7eb")}>
          <StageHeader num="5" title="AI Score & Cluster" subtitle="AI validates each keyword against your business, scores 0-100, keeps top 100, clusters into content themes"
            status={scoringStatus} color="#d97706" />
          {/* AI Provider selector */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 11, color: T.textSoft, fontWeight: 600, whiteSpace: "nowrap" }}>AI for scoring:</span>
            <AiProviderSelect value={discoveryAiProvider} onChange={setDiscoveryAiProvider} />
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: scoringStatus === "done" ? 10 : 0 }}>
            <Btn onClick={runClusterKeywords} disabled={scoringStatus === "running"}
              style={{ background: "#d97706", color: "#fff", border: "none" }}>
              {scoringStatus === "running" ? <><Spinner /> AI Validating & Clustering…</> : scoringStatus === "done" ? "Re-Validate & Cluster" : "AI Score & Cluster"}
            </Btn>
            {scoringSummary && (
              <span style={{ fontSize: 11, color: "#065f46", fontWeight: 600 }}>
                {scoringSummary.total} evaluated · <span style={{ color: "#059669" }}>{scoringSummary.good} kept</span> · <span style={{ color: "#dc2626" }}>{scoringSummary.bad} dropped</span>
              </span>
            )}
          </div>

          {scoringStatus === "done" && clusterData && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: "#78716c" }}>
                  {scoringSummary?.good || "?"} top keywords · {Object.keys(clusterData.clustered || {}).length} pillars · {Object.values(clusterData.clustered || {}).reduce((s, p) => s + (p.clusters || []).length, 0)} content clusters
                </span>
                <span style={{ fontSize: 9, color: "#94a3b8" }}>→ Review in Combined view below</span>
                <button onClick={() => setStage5Collapsed(v => !v)}
                  style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", fontSize: 11, color: "#d97706", fontWeight: 600, padding: "0 4px" }}>
                  {stage5Collapsed ? "▼ Show clusters" : "▲ Hide clusters"}
                </button>
              </div>
              {!stage5Collapsed && (
                <div style={{ display: "grid", gap: 8, maxHeight: 480, overflowY: "auto" }}>
                  {Object.entries(clusterData.clustered || {}).sort((a, b) => (b[1].total || 0) - (a[1].total || 0)).map(([pillarName, pillarInfo]) => (
                    <details key={pillarName} open style={{ background: "#fffbeb", borderRadius: 8, border: "1px solid #fde68a", padding: "8px 12px" }}>
                      <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 700, color: "#92400e", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span>🎯 {pillarName}</span>
                        <span style={{ fontWeight: 400, color: "#78716c", fontSize: 11 }}>
                          {pillarInfo.total} keywords · {(pillarInfo.clusters || []).length} content clusters
                        </span>
                      </summary>
                      <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
                        {(pillarInfo.clusters || []).map((cluster, ci) => (
                          <details key={ci} style={{
                            background: cluster.location_specific ? "#f0fdf4" : "#fff",
                            borderRadius: 6,
                            border: `1px solid ${cluster.location_specific ? "#86efac" : "#e5e7eb"}`,
                            padding: "5px 8px"
                          }}>
                            <summary style={{ cursor: "pointer", fontSize: 11, fontWeight: 600, color: "#374151" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                                <div>
                                  <span>{cluster.cluster_name}</span>
                                  {cluster.location_specific && (
                                    <span style={{ marginLeft: 6, fontSize: 9, background: "#dcfce7", color: "#166534", borderRadius: 4, padding: "1px 5px", fontWeight: 700 }}>📍 Local</span>
                                  )}
                                  {cluster.ai_generated && (
                                    <span style={{ marginLeft: 4, fontSize: 9, background: "rgba(0,122,255,0.1)", color: "#6d28d9", borderRadius: 4, padding: "1px 5px", fontWeight: 700 }}>✨ AI</span>
                                  )}
                                </div>
                                <span style={{ fontWeight: 400, color: "#9ca3af", whiteSpace: "nowrap", marginLeft: 8 }}>{cluster.keyword_count} kws · avg {cluster.avg_score}</span>
                              </div>
                              {cluster.content_angle && (
                                <div style={{ fontSize: 10, color: "#6b7280", fontWeight: 400, marginTop: 2, fontStyle: "italic" }}>
                                  {cluster.content_angle}
                                </div>
                              )}
                            </summary>
                            <div style={{ marginTop: 4 }}>
                              {(cluster.keywords || []).map((kw, ki) => (
                                <div key={ki} style={{
                                  display: "grid", gridTemplateColumns: "1fr auto auto auto", gap: 6,
                                  alignItems: "center", fontSize: 11, padding: "2px 0",
                                  borderTop: ki ? "1px solid #f3f4f6" : "none",
                                }}>
                                  <span>{kw.keyword}</span>
                                  <span style={{ color: intentColor(kw.intent), fontWeight: 600, fontSize: 10 }}>{kw.intent}</span>
                                  <span style={{ fontSize: 9, color: "#94a3b8" }}>{kw.source}</span>
                                  <span style={{ fontWeight: 700, color: (kw.ai_score ?? kw.final_score) >= 70 ? "#059669" : (kw.ai_score ?? kw.final_score) >= 50 ? "#d97706" : "#dc2626" }}>
                                    {Math.round(kw.ai_score ?? kw.final_score)}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </details>
                        ))}
                      </div>
                    </details>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* ─── KEYWORD RESULTS (inline, appears after whichever stage was last run) ─── */}
        {(status === "completed" || pillarCards.length > 0) && (
          <div style={{
            border: `2px solid ${highestStage >= 5 ? "#007AFF" : "#0ea5e9"}`,
            borderRadius: 12, overflow: "hidden",
            boxShadow: highestStage >= 5 ? "0 2px 16px rgba(124,58,237,0.10)" : "none",
          }}>
            {/* Header */}
            <div style={{
              padding: "12px 16px", cursor: "pointer", userSelect: "none",
              background: highestStage >= 5 ? "linear-gradient(135deg, rgba(0,122,255,0.1), #dbeafe)" : "#f0f9ff",
              display: "flex", alignItems: "center", justifyContent: "space-between",
            }} onClick={() => setCombinedCollapsed(v => !v)}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: highestStage >= 5 ? 18 : 16 }}>{highestStage >= 5 ? "🎯" : "📊"}</span>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 800, color: highestStage >= 5 ? "#4c1d95" : "#0c4a6e" }}>
                    {highestStage >= 5 ? "Keyword Results" : `Combined Discovery (Stages 1–${highestStage})`}
                  </div>
                  <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>
                    {highestStage >= 5
                      ? "Review & approve keywords before running strategy"
                      : `Aggregated from all stages run so far`}
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {loadingResults && <Spinner />}
                <div style={{ display: "flex", gap: 6 }}>
                  <Btn small onClick={e => { e.stopPropagation(); fetchResults() }} style={{ background: "#f1f5f9", border: "1px solid #e2e8f0" }}>🔄 Refresh</Btn>
                  <Btn small onClick={e => { e.stopPropagation(); rescorePillar("all") }} disabled={!!rescoreTarget}
                    style={{ background: "#007AFF", color: "#fff", border: "none" }}>
                    {rescoreTarget === "all" ? <><Spinner /> Re-scoring…</> : "⚡ Re-Score All"}
                  </Btn>
                </div>
                <span style={{ fontSize: 14, color: "#94a3b8" }}>{combinedCollapsed ? "▼" : "▲"}</span>
              </div>
            </div>

            {!combinedCollapsed && (
              <div style={{ padding: "12px 14px 16px" }}>
                {/* Stats bar */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))", gap: 8, marginBottom: 14 }}>
                  {[
                    { label: "Total", value: resultTotal, color: "#1e293b", bg: "#f1f5f9" },
                    { label: "Pillars", value: pillarCards.length, color: "#007AFF", bg: "rgba(0,122,255,0.1)" },
                    { label: "Accepted", value: resultStats.accepted || 0, color: "#059669", bg: "#d1fae5" },
                    { label: "Rejected", value: resultStats.rejected || 0, color: "#dc2626", bg: "#fee2e2" },
                    { label: "Pending", value: resultStats.pending || resultTotal - (resultStats.accepted || 0) - (resultStats.rejected || 0), color: "#d97706", bg: "#fef3c7" },
                  ].map(s => (
                    <div key={s.label} style={{ background: s.bg, borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                      <div style={{ fontSize: 20, fontWeight: 800, color: s.color }}>{s.value}</div>
                      <div style={{ fontSize: 10, color: "#64748b", fontWeight: 600 }}>{s.label}</div>
                    </div>
                  ))}
                </div>

                {/* Bulk toolbar */}
                {selectedKws.size > 0 && (
                  <div style={{
                    display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", marginBottom: 12,
                    background: "#eff6ff", borderRadius: 10, border: "1.5px solid #3b82f6", flexWrap: "wrap",
                  }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#1d4ed8" }}>{selectedKws.size} selected</span>
                    <Btn small onClick={() => bulkAction("accept", [...selectedKws])} disabled={bulkLoading}
                      style={{ background: "#059669", color: "#fff", border: "none", fontSize: 11 }}>✓ Accept</Btn>
                    <Btn small onClick={() => bulkAction("reject", [...selectedKws])} disabled={bulkLoading}
                      style={{ background: "#dc2626", color: "#fff", border: "none", fontSize: 11 }}>✕ Reject</Btn>
                    <Btn small onClick={() => bulkAction("delete", [...selectedKws])} disabled={bulkLoading}
                      style={{ background: "#64748b", color: "#fff", border: "none", fontSize: 11 }}>🗑 Delete</Btn>
                    <select value={movingTo || ""} onChange={e => { if (e.target.value) moveSelectedToTarget(e.target.value) }}
                      style={{ fontSize: 11, padding: "4px 8px", borderRadius: 6, border: "1px solid #cbd5e1" }}>
                      <option value="">Move to pillar…</option>
                      {pillarCards.map(p => <option key={p.pillar} value={p.pillar}>{p.pillar}</option>)}
                    </select>
                    <Btn small onClick={() => setSelectedKws(new Set())} style={{ background: "#fff", border: "1px solid #cbd5e1", fontSize: 11 }}>Clear</Btn>
                    {bulkLoading && <Spinner />}
                  </div>
                )}

                {/* Pillar Cards */}
                <div style={{ display: "grid", gap: 10 }}>
                  {pillarCards.map(pillar => {
                    const isOpen = expandedPillars.has(pillar.pillar)
                    const toggleExpand = () => setExpandedPillars(prev => {
                      const next = new Set(prev); next.has(pillar.pillar) ? next.delete(pillar.pillar) : next.add(pillar.pillar); return next
                    })
                    const pillarKwIds = (pillar.keywords || []).map(k => k.item_id).filter(Boolean)
                    const allSelected = pillarKwIds.length > 0 && pillarKwIds.every(id => selectedKws.has(id))
                    const someSelected = pillarKwIds.some(id => selectedKws.has(id))
                    const toggleSelectAll = (e) => {
                      e.stopPropagation()
                      setSelectedKws(prev => { const next = new Set(prev); if (allSelected) { pillarKwIds.forEach(id => next.delete(id)) } else { pillarKwIds.forEach(id => next.add(id)) }; return next })
                    }
                    const isRenaming = renamingPillar === pillar.pillar
                    return (
                      <div key={pillar.pillar} style={{
                        border: `1.5px solid ${isOpen ? "#007AFF" : someSelected ? "#3b82f6" : "#e2e8f0"}`,
                        borderRadius: 10, overflow: "hidden", transition: "all 0.2s",
                        boxShadow: isOpen ? "0 2px 12px rgba(124,58,237,0.1)" : "none",
                      }}>
                        {/* Pillar header */}
                        <div style={{ padding: "10px 14px", cursor: "pointer", userSelect: "none", background: isOpen ? "rgba(0,122,255,0.06)" : "#fafafa" }}>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }} onClick={toggleExpand}>
                              <input type="checkbox" checked={allSelected} ref={el => { if (el) el.indeterminate = someSelected && !allSelected }}
                                onChange={toggleSelectAll} onClick={e => e.stopPropagation()}
                                style={{ cursor: "pointer", width: 16, height: 16, accentColor: "#007AFF" }} />
                              <span style={{ fontSize: 14, transform: isOpen ? "rotate(90deg)" : "rotate(0)", transition: "transform 0.15s" }}>▸</span>
                              {isRenaming ? (
                                <input value={renameValue} onChange={e => setRenameValue(e.target.value)}
                                  onKeyDown={e => { if (e.key === "Enter") renamePillar(pillar.pillar, renameValue); if (e.key === "Escape") setRenamingPillar(null) }}
                                  onClick={e => e.stopPropagation()} autoFocus
                                  style={{ fontWeight: 700, fontSize: 13, border: "1px solid #007AFF", borderRadius: 4, padding: "2px 6px", width: 200 }} />
                              ) : (
                                <span style={{ fontWeight: 700, fontSize: 13, color: "#1e293b" }}>{pillar.pillar}</span>
                              )}
                              <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 10, fontWeight: 700, background: "rgba(0,122,255,0.1)", color: "#007AFF" }}>{pillar.total} kw</span>
                            </div>
                            <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 10 }}>
                              <span style={{ color: "#64748b" }}>Avg: <strong style={{ color: pillar.avg_score >= 60 ? "#059669" : pillar.avg_score >= 40 ? "#d97706" : "#dc2626" }}>{pillar.avg_score}</strong></span>
                              <span style={{ color: "#64748b" }}>Top: <strong style={{ color: "#059669" }}>{pillar.top_score}</strong></span>
                              <div style={{ display: "flex", gap: 3, marginLeft: 8 }} onClick={e => e.stopPropagation()}>
                                <button onClick={() => { setRenamingPillar(pillar.pillar); setRenameValue(pillar.pillar) }} title="Rename" style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, padding: "2px 4px" }}>✏️</button>
                                <button onClick={() => bulkAction("accept", null, pillar.pillar)} title="Accept all" style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, padding: "2px 4px" }}>✅</button>
                                <button onClick={() => bulkAction("reject", null, pillar.pillar)} title="Reject all" style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, padding: "2px 4px" }}>🚫</button>
                                <button onClick={() => rescorePillar(pillar.pillar)} disabled={!!rescoreTarget} title="Re-score" style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, padding: "2px 4px" }}>{rescoreTarget === pillar.pillar ? "⏳" : "⚡"}</button>
                                <button onClick={() => deletePillar(pillar.pillar)} title="Delete pillar" style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, padding: "2px 4px", color: "#dc2626" }}>🗑</button>
                              </div>
                            </div>
                          </div>
                          {/* Breakdown badges */}
                          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6, marginLeft: 38 }} onClick={toggleExpand}>
                            {(pillar.accepted > 0) && <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 8, fontWeight: 700, background: "#d1fae5", color: "#059669" }}>✓ {pillar.accepted} accepted</span>}
                            {(pillar.pending > 0) && <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 8, fontWeight: 700, background: "#fef3c7", color: "#d97706" }}>⏳ {pillar.pending} pending</span>}
                            {(pillar.rejected > 0) && <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 8, fontWeight: 700, background: "#fee2e2", color: "#dc2626" }}>✕ {pillar.rejected} rejected</span>}
                            <span style={{ color: "#cbd5e1", fontSize: 9 }}>|</span>
                            {Object.entries(pillar.by_intent || {}).map(([intent, count]) => (
                              <span key={intent} style={{ fontSize: 9, padding: "1px 6px", borderRadius: 8, fontWeight: 600, background: intentColor(intent) + "18", color: intentColor(intent) }}>{intent} ({count})</span>
                            ))}
                            <span style={{ color: "#cbd5e1", fontSize: 9 }}>|</span>
                            {Object.entries(pillar.by_source || {}).map(([src, count]) => (
                              <span key={src} style={{ fontSize: 9, padding: "1px 6px", borderRadius: 8, fontWeight: 600, background: (SOURCE_COLORS[src] || "#94a3b8") + "18", color: SOURCE_COLORS[src] || "#94a3b8" }}>{src} ({count})</span>
                            ))}
                          </div>
                        </div>

                        {/* Keywords grouped by intent */}
                        {isOpen && (
                          <div style={{ padding: "0 4px 8px 4px" }}>
                            {(() => {
                              const intentGroups = {}
                              for (const kw of (pillar.keywords || [])) {
                                const intent = kw.intent || "informational"
                                if (!intentGroups[intent]) intentGroups[intent] = []
                                intentGroups[intent].push(kw)
                              }
                              const INTENT_ICONS = { transactional: "🛒", informational: "📚", navigational: "🧭", comparison: "⚖️", commercial: "💰", research: "🔍" }
                              const intentOrder = ["transactional", "commercial", "comparison", "informational", "navigational", "research"]
                              const sortedIntents = Object.keys(intentGroups).sort((a, b) => {
                                const ia = intentOrder.indexOf(a), ib = intentOrder.indexOf(b)
                                return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
                              })
                              return sortedIntents.map(intent => {
                                const kws = intentGroups[intent]
                                const icon = INTENT_ICONS[intent] || "📌"
                                const acceptedInGroup = kws.filter(k => k.status === "accepted").length
                                return (
                                  <div key={intent} style={{ marginBottom: 6 }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: intentColor(intent) + "0C", borderBottom: `2px solid ${intentColor(intent)}30` }}>
                                      <span style={{ fontSize: 13 }}>{icon}</span>
                                      <span style={{ fontSize: 11, fontWeight: 700, color: intentColor(intent), textTransform: "capitalize" }}>{intent}</span>
                                      <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 8, fontWeight: 700, background: intentColor(intent) + "18", color: intentColor(intent) }}>{kws.length} keywords</span>
                                      {acceptedInGroup > 0 && <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 8, fontWeight: 600, background: "#d1fae5", color: "#059669" }}>✓ {acceptedInGroup} accepted</span>}
                                    </div>
                                    <div style={{ display: "grid", gridTemplateColumns: "30px 1fr 70px 80px 55px 40px", gap: 4, padding: "4px 10px", fontSize: 9, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                                      <span></span><span>Keyword</span><span style={{ textAlign: "center" }}>Type</span><span style={{ textAlign: "center" }}>Source</span><span style={{ textAlign: "right" }}>Score</span><span></span>
                                    </div>
                                    <div style={{ maxHeight: 300, overflowY: "auto" }}>
                                      {kws.map((kw, ki) => {
                                        const isSelected = selectedKws.has(kw.item_id)
                                        return (
                                          <div key={kw.item_id || ki} style={{
                                            display: "grid", gridTemplateColumns: "30px 1fr 70px 80px 55px 40px",
                                            gap: 4, alignItems: "center", padding: "5px 10px", fontSize: 11,
                                            borderBottom: "1px solid #f1f5f9",
                                            background: kw.status === "accepted" ? "#f0fdf4" : kw.status === "rejected" ? "#fff1f2" : isSelected ? "#eff6ff" : "#fff",
                                            opacity: kw.status === "rejected" ? 0.5 : 1,
                                          }}>
                                            <input type="checkbox" checked={isSelected}
                                              onChange={() => setSelectedKws(prev => { const next = new Set(prev); next.has(kw.item_id) ? next.delete(kw.item_id) : next.add(kw.item_id); return next })}
                                              style={{ cursor: "pointer", accentColor: "#3b82f6" }} />
                                            <span style={{ fontWeight: 500, color: "#1e293b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{kw.keyword}</span>
                                            <span style={{ textAlign: "center" }}><span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, fontWeight: 600, background: kw.type === "short_tail" ? "#dbeafe" : "#dcfce7", color: kw.type === "short_tail" ? "#1d4ed8" : "#15803d" }}>{kw.type === "short_tail" ? "short" : "long"}</span></span>
                                            <span style={{ textAlign: "center" }}><span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: (SOURCE_COLORS[kw.source] || "#94a3b8") + "22", color: SOURCE_COLORS[kw.source] || "#94a3b8", fontWeight: 600 }}>{kw.source}</span></span>
                                            <span style={{ textAlign: "right", fontWeight: 800, fontSize: 12, color: kw.score >= 70 ? "#059669" : kw.score >= 50 ? "#d97706" : kw.score >= 30 ? "#ea580c" : "#dc2626" }}>{kw.score}</span>
                                            <div style={{ display: "flex", gap: 2 }}>
                                              {kw.status !== "accepted" && <button onClick={() => bulkAction("accept", [kw.item_id])} title="Accept" style={{ background: "none", border: "none", cursor: "pointer", fontSize: 10, padding: 0 }}>✓</button>}
                                              {kw.status !== "rejected" && <button onClick={() => bulkAction("reject", [kw.item_id])} title="Reject" style={{ background: "none", border: "none", cursor: "pointer", fontSize: 10, padding: 0, color: "#dc2626" }}>✕</button>}
                                            </div>
                                          </div>
                                        )
                                      })}
                                    </div>
                                  </div>
                                )
                              })
                            })()}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>

                {/* Run Strategy CTA — only shown when stage 5 done and keywords accepted */}
                {highestStage >= 5 && pillarCards.length > 0 && (resultStats.accepted || 0) > 0 && (
                  <div style={{
                    marginTop: 16, padding: "14px 18px", borderRadius: 10,
                    background: "linear-gradient(135deg, #007AFF08, #007AFF18)",
                    border: "1.5px solid #007AFF50",
                    display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10,
                  }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>✅ Ready to run strategy</div>
                      <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                        <strong style={{ color: "#059669" }}>{resultStats.accepted}</strong> accepted keywords across{" "}
                        <strong style={{ color: "#007AFF" }}>{pillarCards.length}</strong> pillars
                      </div>
                    </div>
                    <Btn variant="primary" onClick={handleContinue} style={{ fontSize: 14, padding: "10px 28px", fontWeight: 700 }}>Run Strategy →</Btn>
                  </div>
                )}

                {pillarCards.length === 0 && !loadingResults && (
                  <div style={{ padding: 24, textAlign: "center", color: T.gray, fontSize: 12 }}>No keywords discovered yet. Run Stage 3 Discovery first.</div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ─── STAGE 6: Run Strategy Final ───────────────────────────────────── */}
        <div style={stageBox("#007AFF")}>
          <StageHeader num="6" title="Run Strategy Final" subtitle="Use all discovered & ranked keywords to build the complete SEO strategy"
            color="#007AFF" />
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <Btn variant="primary" onClick={handleContinue} style={{ fontSize: 14, padding: "10px 28px", fontWeight: 700 }}>
              Run Strategy →
            </Btn>
            <span style={{ fontSize: 11, color: T.textSoft }}>
              {(resultStats.accepted || 0) > 0
                ? `${resultStats.accepted} accepted keywords ready`
                : scoringSummary?.good
                  ? `${scoringSummary.good} ranked keywords ready`
                  : summary?.total
                    ? `${summary.total} discovered keywords ready`
                    : allPillars.length > 0 ? `${allPillars.length} pillars · accept keywords above first` : "Complete stages above first"}
            </span>
          </div>
        </div>
      </Card>

      {/* ═══ AI PROMPTS SECTION ═══════════════════════════════════════════════ */}
      <Card style={{ marginTop: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>🤖 AI Prompts</div>
        <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 14 }}>
          Customize the AI prompts used in keyword discovery. Edit to match your specific business needs.
        </div>

        {!promptsLoaded ? (
          <div style={{ padding: 20, textAlign: "center" }}><Spinner /> Loading prompts…</div>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {[
              { key: "deepseek_kw_review", label: "DeepSeek Keyword Review", desc: "Primary AI engine for keyword quality control, intent scoring, and cleanup" },
              { key: "groq_kw_review", label: "Groq Keyword Review", desc: "Fast AI validator for high-throughput keyword cleanup" },
              { key: "gemini_kw_review", label: "Gemini Keyword Review", desc: "Balanced AI for keyword semantics, intent, and conversion potential" },
              { key: "claude_kw_review", label: "Claude Keyword Review", desc: "Advanced SEO strategy reviewer with risk/opportunity analysis" },
              { key: "cluster_naming", label: "Cluster Naming", desc: "AI prompt for naming keyword clusters and suggesting content types" },
            ].map(({ key, label, desc }) => (
              <div key={key} style={{
                border: `1px solid ${editingPrompt === key ? "#3b82f6" : T.border}`,
                borderRadius: 8, padding: 12,
                background: editingPrompt === key ? "#f0f9ff" : "#fff",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700 }}>{label}</div>
                    <div style={{ fontSize: 10, color: T.textSoft }}>{desc}</div>
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    {editingPrompt === key ? (
                      <>
                        <Btn small onClick={async () => {
                          setPromptSaving(true)
                          try {
                            await fetch(`${API}/api/ki/${projectId}/prompts/${key}`, {
                              method: "PUT",
                              headers: { "Content-Type": "application/json", ...authHeaders() },
                              body: JSON.stringify({ content: promptDraft }),
                            })
                            setPrompts(prev => ({ ...prev, [key]: promptDraft }))
                            setEditingPrompt(null)
                            notify("Prompt saved", "success")
                          } catch (e) { notify("Save failed: " + e, "error") }
                          setPromptSaving(false)
                        }} disabled={promptSaving} style={{ background: "#10b981", color: "#fff", border: "none" }}>
                          {promptSaving ? <Spinner /> : "💾 Save"}
                        </Btn>
                        <Btn small onClick={async () => {
                          setPromptImproving(true)
                          try {
                            const res = await fetch(`${API}/api/ki/${projectId}/prompts/${key}/improve`, {
                              method: "POST",
                              headers: { "Content-Type": "application/json", ...authHeaders() },
                              body: JSON.stringify({ content: promptDraft }),
                            })
                            const data = await res.json()
                            if (data.improved) {
                              setPromptDraft(data.improved)
                              notify("AI improved the prompt — review and save", "success")
                            }
                          } catch (e) { notify("AI improve failed: " + e, "error") }
                          setPromptImproving(false)
                        }} disabled={promptImproving} style={{ background: "#007AFF", color: "#fff", border: "none" }}>
                          {promptImproving ? <><Spinner /> Improving…</> : "✨ AI Improve"}
                        </Btn>
                        <Btn small onClick={() => { setPromptDraft(prompts[key] || ""); }} style={{ background: "#f59e0b", color: "#fff", border: "none" }}>
                          ↩ Reset
                        </Btn>
                        <Btn small onClick={() => setEditingPrompt(null)}>Cancel</Btn>
                      </>
                    ) : (
                      <Btn small onClick={() => { setEditingPrompt(key); setPromptDraft(prompts[key] || "") }}>
                        ✏️ Edit
                      </Btn>
                    )}
                  </div>
                </div>
                {editingPrompt === key ? (
                  <textarea
                    value={promptDraft}
                    onChange={e => setPromptDraft(e.target.value)}
                    style={{
                      width: "100%", minHeight: 180, padding: 10, fontFamily: "monospace", fontSize: 11,
                      border: `1px solid ${T.border}`, borderRadius: 6, resize: "vertical",
                      lineHeight: 1.5, background: "#fff",
                    }}
                  />
                ) : (
                  <div style={{
                    fontSize: 10, color: T.textSoft, fontFamily: "monospace",
                    background: T.grayLight, borderRadius: 6, padding: 8,
                    maxHeight: 80, overflowY: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word",
                  }}>
                    {(prompts[key] || "No prompt set — click Edit to add one").slice(0, 300)}
                    {(prompts[key] || "").length > 300 ? "…" : ""}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
