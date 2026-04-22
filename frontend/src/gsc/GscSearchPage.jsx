/**
 * GscSearchPage — Keyword search: your GSC data OR global Google Suggestions
 *
 * Mode A (My GSC Data):   POST /api/gsc/{id}/search     — your site's own queries
 * Mode B (Global Google): POST /api/kw/global-suggest   — real Google Autocomplete, worldwide
 *
 * Enhanced: auto-populate pillars from Phase 1, bulk search per pillar, bulk-selectable results.
 */
import React, { useState, useMemo, useCallback, useEffect } from "react"
import * as gscApi from "./api"
import useKw2Store from "../kw2/store"
import { TagInput } from "../kw2/shared"

const API = import.meta.env.VITE_API_URL || ""

/* ── Design tokens ──────────────────────────────────────────────────────────── */

const T = {
  blue:   "#007AFF",
  green:  "#34C759",
  red:    "#FF3B30",
  orange: "#FF9500",
  purple: "#AF52DE",
  gray:   "#8E8E93",
  bg:     "#F2F2F7",
  card:   "#FFFFFF",
  border: "rgba(60,60,67,0.12)",
}

const INTENT_META = {
  purchase:      { bg: "#fee2e2", fg: "#dc2626", label: "Purchase" },
  commercial:    { bg: "#fef9c3", fg: "#854d0e", label: "Commercial" },
  informational: { bg: "#dbeafe", fg: "#1e40af", label: "Informational" },
  navigational:  { bg: "#f3e8ff", fg: "#7e22ce", label: "Navigational" },
  unknown:       { bg: "#f3f4f6", fg: "#374151", label: "Unknown" },
}

/* ── Primitives ─────────────────────────────────────────────────────────────── */

function Card({ children, style }) {
  return (
    <div style={{
      background: T.card, borderRadius: 12, padding: "16px 18px",
      border: `0.5px solid ${T.border}`, ...style,
    }}>{children}</div>
  )
}

function IntentBadge({ intent }) {
  const m = INTENT_META[intent] || INTENT_META.unknown
  return (
    <span style={{
      display: "inline-block", padding: "2px 7px", borderRadius: 8,
      fontSize: 10, fontWeight: 700, background: m.bg, color: m.fg,
    }}>{m.label}</span>
  )
}

function Metric({ label, value, sub }) {
  return (
    <div style={{
      flex: 1, minWidth: 100, padding: "14px 16px", borderRadius: 10,
      background: T.bg, textAlign: "center",
    }}>
      <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: -1 }}>{value}</div>
      <div style={{ fontSize: 11, fontWeight: 600, color: T.gray, marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: 10, color: T.gray, marginTop: 1 }}>{sub}</div>}
    </div>
  )
}

function SortTh({ col, sortBy, sortDir, onSort, children, style }) {
  const active = sortBy === col
  return (
    <th onClick={() => onSort(col)} style={{
      padding: "8px 10px", textAlign: "right", fontWeight: 700, fontSize: 11,
      color: active ? T.blue : "#374151", cursor: "pointer", whiteSpace: "nowrap",
      userSelect: "none", background: "#f9fafb", borderBottom: `1px solid ${T.border}`, ...style,
    }}>
      {children}{active ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
    </th>
  )
}

function exportCSV(rows, query) {
  const cols = ["keyword", "intent", "impressions", "clicks", "ctr", "position", "score"]
  const header = cols.join(",")
  const lines = rows.map(r =>
    cols.map(c => {
      const v = c === "ctr" ? (r.ctr * 100).toFixed(2) + "%" : r[c] ?? ""
      return `"${String(v).replace(/"/g, '""')}"`
    }).join(",")
  )
  const csv = [header, ...lines].join("\n")
  const blob = new Blob([csv], { type: "text/csv" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a"); a.href = url
  a.download = `keywords_${query.replace(/\s+/g, "_")}_${new Date().toISOString().slice(0, 10)}.csv`
  a.click(); URL.revokeObjectURL(url)
}

async function apiFetch(path, method = "GET", body) {
  const opts = {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + (localStorage.getItem("annaseo_token") || ""),
    },
  }
  if (body) opts.body = JSON.stringify(body)
  const r = await fetch(`${API}${path}`, opts)
  const data = await r.json()
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
  return data
}

/* ── Source toggle ──────────────────────────────────────────────────────────── */

function SourceToggle({ value, onChange, allowed = ["gsc", "global"], disabled = false }) {
  const opts = [
    { id: "gsc",     label: "📊 My GSC Data",        desc: "Queries from your own website" },
    { id: "global",  label: "🌍 Global Google Suggest", desc: "Real searches worldwide — no GSC needed" },
  ].filter((o) => allowed.includes(o.id))
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
      {opts.map(o => (
        <button key={o.id} onClick={() => onChange(o.id)} disabled={disabled} style={{
          padding: "10px 14px", borderRadius: 10,
          cursor: disabled ? "not-allowed" : "pointer", textAlign: "left",
          background: value === o.id ? "#eff6ff" : T.bg,
          border: value === o.id ? "2px solid #3b82f6" : "2px solid transparent",
          opacity: disabled ? 0.85 : 1,
          transition: "all .15s",
        }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: value === o.id ? "#1d4ed8" : "#374151" }}>{o.label}</div>
          <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>{o.desc}</div>
        </button>
      ))}
    </div>
  )
}

/* ── Main component ─────────────────────────────────────────────────────────── */

export default function GscSearchPage({
  projectId,
  sessionId,
  defaultSource = "global",
  allowedSources = ["gsc", "global"],
  sourceLocked = false,
  onKeywordsReady,
  onApproveKeywords,
}) {
  const { profile, session, mode } = useKw2Store()
  const initialSource = allowedSources.includes(defaultSource) ? defaultSource : (allowedSources[0] || "global")
  const [source, setSource]         = useState(initialSource)
  const [query, setQuery]           = useState("")
  const [days, setDays]             = useState(90)
  const [limit, setLimit]           = useState(100)
  const [loading, setLoading]       = useState(false)
  const [result, setResult]         = useState(null)
  const [error, setError]           = useState(null)
  const [sortBy, setSortBy]         = useState("score")
  const [sortDir, setSortDir]       = useState("desc")
  const [intentFilter, setIntentFilter] = useState("all")
  const [minImpressions, setMinImp] = useState("")
  const [searched, setSearched]     = useState("")
  // ── Pillar / modifier state (auto-populated from Phase 1 profile) ──
  const [pillars, setPillars]       = useState([])
  const [modifiers, setModifiers]   = useState([])
  const [bulkSearching, setBulkSearching] = useState(false)
  const [bulkProgress, setBulkProgress]   = useState({ current: 0, total: 0, pillar: "" })
  const [pillarFilter, setPillarFilter]   = useState("all")

  // ── Bulk selection ──
  const [selected, setSelected]     = useState(new Set())

  // Auto-populate pillars & modifiers from session seeds + store profile
  useEffect(() => {
    const sessionSeeds = Array.isArray(session?.seed_keywords)
      ? session.seed_keywords.filter(Boolean) : []
    const profilePillars = (profile && Array.isArray(profile.pillars))
      ? profile.pillars.filter(Boolean) : []
    const profileMods = (profile && Array.isArray(profile.modifiers))
      ? profile.modifiers.filter(Boolean) : []

    // Merge seeds + profile pillars (deduplicated, case-insensitive)
    const seen = new Set()
    const merged = []
    for (const p of [...sessionSeeds, ...profilePillars]) {
      const key = p.toLowerCase().trim()
      if (key && !seen.has(key)) { seen.add(key); merged.push(p) }
    }
    if (merged.length) setPillars(merged)
    if (profileMods.length) setModifiers(profileMods)
  }, [profile, session])

  // Report discovered keywords to parent whenever results change
  useEffect(() => {
    if (onKeywordsReady && result?.keywords?.length) {
      onKeywordsReady(result.keywords, pillars)
    }
  }, [result, pillars, onKeywordsReady])

  useEffect(() => {
    const next = allowedSources.includes(defaultSource) ? defaultSource : (allowedSources[0] || "global")
    setSource(next)
  }, [defaultSource, allowedSources.join("|")])

  const handleSearch = useCallback(async (e) => {
    if (e) e.preventDefault()
    // Use pillars as seed keywords for global search
    const seeds = source === "global" ? pillars : [query.trim()].filter(Boolean)
    if (!seeds.length) return

    // Multi-keyword: bulk-search all seed tags
    if (seeds.length > 1) {

      // Run bulk search over the seeds
      setBulkSearching(true)
      setError(null); setResult(null); setSelected(new Set())
      setBulkProgress({ current: 0, total: seeds.length, pillar: "" })
      setSearched(seeds.join(", "))

      const allKeywords = []
      const seen = new Set()
      let errorCount = 0

      for (let i = 0; i < seeds.length; i++) {
        const seed = seeds[i]
        setBulkProgress({ current: i + 1, total: seeds.length, pillar: seed })
        try {
          let r
          if (source === "gsc") {
            if (!projectId) throw new Error("No active project selected.")
            r = await gscApi.searchKeyword(projectId, seed, days, limit)
          } else {
            r = await apiFetch("/api/kw/global-suggest", "POST", { seed, limit, modifiers })
          }
          if (r?.keywords) {
            for (const kw of r.keywords) {
              const key = kw.keyword.toLowerCase().trim()
              if (!seen.has(key)) {
                seen.add(key)
                allKeywords.push({ ...kw, _pillar: seed })
              }
            }
          }
        } catch { errorCount++ }
      }

      setResult({
        keywords: allKeywords,
        total: allKeywords.length,
        _bulkSearch: true,
        _errorCount: errorCount,
      })
      if (source === "global") setSortBy("score")
      setBulkSearching(false)
      return
    }

    // Single keyword search
    const q = seeds[0]
    setLoading(true); setError(null); setResult(null); setSearched(q); setSelected(new Set())
    try {
      let r
      if (source === "gsc") {
        if (!projectId) throw new Error("No active project selected.")
        r = await gscApi.searchKeyword(projectId, q, days, limit)
      } else {
        r = await apiFetch("/api/kw/global-suggest", "POST", { seed: q, limit, modifiers })
      }
      if (r?.keywords) {
        r.keywords = r.keywords.map(kw => ({ ...kw, _pillar: q }))
      }
      setResult(r)
      if (source === "global") setSortBy("score")
    } catch (err) {
      setError(err.message || "Search failed")
    }
    setLoading(false)
  }, [pillars, query, days, limit, projectId, source, modifiers])

  // ── Bulk search: search all pillars sequentially ──
  const handleBulkSearch = useCallback(async () => {
    if (!pillars.length) return
    setBulkSearching(true)
    setError(null)
    setResult(null)
    setSelected(new Set())
    setBulkProgress({ current: 0, total: pillars.length, pillar: "" })
    setSearched(pillars.join(", "))

    const allKeywords = []
    const seen = new Set()
    let errorCount = 0

    for (let i = 0; i < pillars.length; i++) {
      const pillar = pillars[i]
      setBulkProgress({ current: i + 1, total: pillars.length, pillar })
      try {
        let r
        if (source === "gsc") {
          if (!projectId) throw new Error("No active project selected.")
          r = await gscApi.searchKeyword(projectId, pillar, days, limit)
        } else {
          r = await apiFetch("/api/kw/global-suggest", "POST", { seed: pillar, limit, modifiers })
        }
        if (r?.keywords) {
          for (const kw of r.keywords) {
            const key = kw.keyword.toLowerCase().trim()
            if (!seen.has(key)) {
              seen.add(key)
              allKeywords.push({ ...kw, _pillar: pillar })
            }
          }
        }
      } catch {
        errorCount++
      }
    }

    setResult({
      keywords: allKeywords,
      total: allKeywords.length,
      _bulkSearch: true,
      _errorCount: errorCount,
    })
    if (source === "global") setSortBy("score")
    setBulkSearching(false)
  }, [pillars, source, projectId, days, limit, modifiers])

  const handleKeyDown = (e) => { if (e.key === "Enter") { e.preventDefault(); handleSearch() } }

  const handleSort = useCallback((col) => {
    if (sortBy === col) setSortDir(d => d === "asc" ? "desc" : "asc")
    else { setSortBy(col); setSortDir("desc") }
  }, [sortBy])

  const filtered = useMemo(() => {
    if (!result?.keywords) return []
    let rows = result.keywords
    if (intentFilter !== "all") rows = rows.filter(r => r.intent === intentFilter)
    if (pillarFilter !== "all") rows = rows.filter(r => r._pillar === pillarFilter)
    if (minImpressions !== "" && source === "gsc") {
      const n = parseInt(minImpressions, 10)
      if (!isNaN(n)) rows = rows.filter(r => r.impressions >= n)
    }
    return [...rows].sort((a, b) => {
      const av = a[sortBy] ?? 0; const bv = b[sortBy] ?? 0
      return sortDir === "asc" ? av - bv : bv - av
    })
  }, [result, intentFilter, minImpressions, sortBy, sortDir, source])

  const intentCount = useMemo(() => {
    if (!result?.keywords) return {}
    return result.keywords.reduce((acc, r) => {
      acc[r.intent] = (acc[r.intent] || 0) + 1; return acc
    }, {})
  }, [result])

  const totalImpressions = useMemo(() =>
    (result?.keywords || []).reduce((s, r) => s + (r.impressions || 0), 0), [result])
  const totalClicks = useMemo(() =>
    (result?.keywords || []).reduce((s, r) => s + (r.clicks || 0), 0), [result])
  const avgScore = useMemo(() => {
    const kws = result?.keywords || []
    if (!kws.length) return 0
    return Math.round(kws.reduce((s, r) => s + (r.score || 0), 0) / kws.length)
  }, [result])

  const pillarCount = useMemo(() => {
    if (!result?.keywords) return {}
    return result.keywords.reduce((acc, r) => {
      const p = r._pillar || "unknown"
      acc[p] = (acc[p] || 0) + 1
      return acc
    }, {})
  }, [result])

  // ── Selection helpers (use keyword string as key for filter-stable selection) ──
  const toggleSelect = useCallback((kw) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(kw)) next.delete(kw); else next.add(kw)
      return next
    })
  }, [])

  const selectAll = useCallback(() => {
    setSelected(new Set(filtered.map(r => r.keyword)))
  }, [filtered])

  const deselectAll = useCallback(() => setSelected(new Set()), [])

  const deleteSelected = useCallback(() => {
    if (!selected.size) return
    const keep = result.keywords.filter(kw => !selected.has(kw.keyword))
    setResult(prev => ({ ...prev, keywords: keep, total: keep.length }))
    setSelected(new Set())
  }, [selected, result])

  const isGlobal = source === "global"
  const notConnected = !isGlobal && error && (
    error.includes("not connected") || error.includes("not_connected") || error.includes("No GSC integration")
  )

  return (
    <div style={{ maxWidth: 960, margin: "0 auto" }}>
      {/* ─ Header ─ */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: -0.5 }}>🔎 Keyword Search</div>
        <div style={{ fontSize: 13, color: T.gray, marginTop: 4 }}>
          Discover keywords from your GSC data <em>or</em> globally from Google Suggestions (no API key needed).
        </div>
      </div>

      {/* ─ Source toggle ─ */}
      <SourceToggle
        value={source}
        allowed={allowedSources}
        disabled={sourceLocked || allowedSources.length <= 1}
        onChange={(s) => {
          if (sourceLocked || allowedSources.length <= 1) return
          setSource(s)
          setResult(null)
          setError(null)
        }}
      />

      {/* ─ Pillars & Modifiers from Phase 1 ─ */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#374151" }}>
              Pillars ({pillars.length})
              {!pillars.length && <span style={{ marginLeft: 8, color: "#9ca3af", fontWeight: 400 }}>
                — {mode === "expand" || mode === "review" ? "enter your seed keywords as pillars" : "auto-loaded from Phase 1"}
              </span>}
            </div>
            <button
              onClick={handleBulkSearch}
              disabled={bulkSearching || !pillars.length}
              style={{
                padding: "6px 16px", borderRadius: 7, fontSize: 12, fontWeight: 700,
                background: bulkSearching || !pillars.length ? "#d1d5db" : "#10b981",
                color: "#fff", border: "none",
                cursor: bulkSearching || !pillars.length ? "not-allowed" : "pointer",
              }}
            >
              {bulkSearching ? `⟳ Searching ${bulkProgress.current}/${bulkProgress.total}...` : `🔎 Search All Pillars (${pillars.length})`}
            </button>
          </div>
          <TagInput
            tags={pillars}
            onChange={setPillars}
            placeholder="Add pillars (comma-separated, Enter to add)"
            color="#2563eb"
            bgColor="#dbeafe"
          />
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#374151", marginBottom: 6 }}>
            Modifiers ({modifiers.length})
          </div>
          <TagInput
            tags={modifiers}
            onChange={setModifiers}
            placeholder="Add modifiers (comma-separated, Enter to add)"
            color="#7c3aed"
            bgColor="#ede9fe"
          />
        </div>
        {bulkSearching && (
          <div style={{ marginTop: 10 }}>
            <div style={{ height: 6, background: "#e5e7eb", borderRadius: 3, overflow: "hidden" }}>
              <div style={{
                height: "100%",
                width: `${(bulkProgress.current / Math.max(bulkProgress.total, 1)) * 100}%`,
                background: "#10b981", borderRadius: 3, transition: "width 300ms ease",
              }} />
            </div>
            <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
              Searching: <strong>{bulkProgress.pillar}</strong> ({bulkProgress.current}/{bulkProgress.total})
            </div>
          </div>
        )}
      </Card>

      {/* ─ Global explain banner ─ */}
      {isGlobal && (
        <div style={{
          marginBottom: 12, padding: "10px 14px", borderRadius: 8,
          background: "#eff6ff", border: "1px solid #bfdbfe", fontSize: 12,
        }}>
          <strong style={{ color: "#1e40af" }}>🌍 Google Suggest mode</strong>
          <span style={{ color: "#374151", marginLeft: 6 }}>
            Expands your seed keyword with 60+ query variations and fetches real suggestions from Google Autocomplete.
            Covers: alphabet expansion, buyer modifiers (buy, organic, wholesale, bulk, price, etc.).
            Results are scored by intent — <strong>no impressions/clicks data</strong> (that requires live GSC connection).
          </span>
        </div>
      )}

      {/* ─ Search bar ─ */}
      <Card style={{ marginBottom: 16 }}>
        <form onSubmit={handleSearch}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={{ fontSize: 11, fontWeight: 600, display: "block", marginBottom: 4, color: "#374151" }}>
                {isGlobal ? "Seeds" : "Keywords"}
                {isGlobal && <span style={{ marginLeft: 6, fontWeight: 400, color: "#9ca3af", fontSize: 10 }}>pillar keywords above are used as seeds</span>}
              </label>
              {/* Global mode: pillars from the card above serve as seeds */}
              {isGlobal ? (
                <div style={{
                  padding: "9px 12px", borderRadius: 8, minHeight: 42, display: "flex", alignItems: "center",
                  background: pillars.length ? "#f0fdf4" : "#fef9c3",
                  border: `1px solid ${pillars.length ? "#bbf7d0" : "#fde68a"}`,
                  fontSize: 12, color: pillars.length ? "#166534" : "#854d0e",
                }}>
                  {pillars.length
                    ? `✓ ${pillars.length} pillar${pillars.length === 1 ? "" : "s"} ready: ${pillars.slice(0, 3).join(", ")}${pillars.length > 3 ? ` +${pillars.length - 3} more` : ""}`
                    : "⚠ Add keywords to the Pillars section above first"}
                </div>
              ) : (
                <input
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="e.g. organic cloves, buy cardamom..."
                  style={{
                    width: "100%", padding: "9px 12px", borderRadius: 8,
                    border: `1px solid ${T.border}`, fontSize: 13, background: "#fff",
                  }}
                />
              )}
            </div>

            {/* Period — only relevant for GSC mode */}
            {!isGlobal && (
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, display: "block", marginBottom: 4, color: "#374151" }}>Period</label>
                <select value={days} onChange={e => setDays(Number(e.target.value))}
                  style={{ padding: "9px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, background: "#fff" }}>
                  <option value={28}>Last 28 days</option>
                  <option value={90}>Last 90 days</option>
                  <option value={180}>Last 180 days</option>
                  <option value={365}>Last 365 days</option>
                </select>
              </div>
            )}

            <div>
              <label style={{ fontSize: 11, fontWeight: 600, display: "block", marginBottom: 4, color: "#374151" }}>Max results</label>
              <select value={limit} onChange={e => setLimit(Number(e.target.value))}
                style={{ padding: "9px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, background: "#fff" }}>
                <option value={50}>Top 50</option>
                <option value={100}>Top 100</option>
                <option value={200}>Top 200</option>
              </select>
            </div>

            <button type="submit" disabled={loading || (isGlobal ? !pillars.length : !query.trim())} style={{
              padding: "9px 22px", borderRadius: 8, fontSize: 13, fontWeight: 700,
              background: loading || (isGlobal ? !pillars.length : !query.trim()) ? "#d1d5db" : (isGlobal ? "#10b981" : T.blue),
              color: "#fff", border: "none",
              cursor: loading || (isGlobal ? !pillars.length : !query.trim()) ? "not-allowed" : "pointer",
            }}>
              {loading
                ? (isGlobal ? "⟳ Fetching Google..." : "⟳ Searching...")
                : (isGlobal ? "🌍 Discover Keywords" : "🔎 Search")}
            </button>
          </div>
        </form>
      </Card>

      {/* ─ Not-connected prompt ─ */}
      {notConnected && (
        <Card style={{ marginBottom: 16, background: "#fef9c3", border: "1px solid #fde68a" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#854d0e", marginBottom: 6 }}>⚠ GSC Not Connected</div>
          <div style={{ fontSize: 12, color: "#92400e", lineHeight: 1.6 }}>
            Switch to <strong>🌍 Global Google Suggest</strong> (no GSC needed) or connect GSC on the Setup Guide tab first.
          </div>
          <button onClick={() => setSource("global")} style={{
            marginTop: 10, padding: "7px 16px", borderRadius: 7, fontSize: 12, fontWeight: 700,
            background: "#10b981", color: "#fff", border: "none", cursor: "pointer",
          }}>
            Switch to Global Mode →
          </button>
        </Card>
      )}

      {/* ─ Generic error ─ */}
      {error && !notConnected && (
        <Card style={{ marginBottom: 16, background: "#fee2e2", border: "1px solid #fecaca" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#dc2626", marginBottom: 4 }}>❌ Search Error</div>
          <div style={{ fontSize: 12, color: "#7f1d1d" }}>{error}</div>
        </Card>
      )}

      {/* ─ Loading skeleton ─ */}
      {loading && (
        <Card>
          <div style={{ textAlign: "center", color: T.gray, padding: 40 }}>
            <div style={{ fontSize: 28, marginBottom: 10 }}>⟳</div>
            <div style={{ fontSize: 14 }}>
              {isGlobal ? "Querying Google Autocomplete (~5–10s)…" : "Querying your GSC data…"}
            </div>
            {isGlobal && (
              <div style={{ fontSize: 12, color: T.gray, marginTop: 6 }}>
                Expanding "{query}" with alphabet + 20 buyer/intent modifiers → classifying intent…
              </div>
            )}
          </div>
        </Card>
      )}

      {/* ─ Results ─ */}
      {result && !loading && (
        <>
          {/* Summary cards */}
          <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
            <Metric label="Keywords Found" value={result.total} />
            {isGlobal ? (
              <>
                <Metric label="Avg Score" value={avgScore} sub="intent-based scoring" />
                <Metric label="Source" value="Google" sub="Autocomplete API" />
              </>
            ) : (
              <>
                <Metric label="Total Impressions" value={totalImpressions.toLocaleString()} />
                <Metric label="Total Clicks" value={totalClicks.toLocaleString()} />
              </>
            )}
            <Metric label="Intent Types" value={Object.keys(intentCount).length} />
          </div>

          {/* Intent breakdown */}
          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#374151" }}>Intent breakdown:</div>
              {Object.entries(intentCount).sort((a,b) => b[1]-a[1]).map(([intent, count]) => (
                <div key={intent} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <IntentBadge intent={intent} />
                  <span style={{ fontSize: 12, color: T.gray }}>{count}</span>
                </div>
              ))}
              {isGlobal && (
                <div style={{ marginLeft: "auto", fontSize: 11, color: T.gray }}>
                  💡 Tip: filter by <strong>Purchase</strong> or <strong>Commercial</strong> for buyer keywords
                </div>
              )}
            </div>
          </Card>

          {/* Filters + export + pillar filter */}
          <Card style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#374151" }}>Intent:</span>
                {["all", "purchase", "commercial", "informational", "navigational"].map(v => (
                  <button key={v} onClick={() => setIntentFilter(v)} style={{
                    padding: "3px 10px", borderRadius: 7, fontSize: 11, fontWeight: 600,
                    background: intentFilter === v ? T.blue : "#f3f4f6",
                    color: intentFilter === v ? "#fff" : "#374151",
                    border: "none", cursor: "pointer",
                  }}>{v === "all" ? "All" : v.charAt(0).toUpperCase() + v.slice(1)}</button>
                ))}
              </div>
              {Object.keys(pillarCount).length > 1 && (
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: "#374151" }}>Pillar:</span>
                  <button onClick={() => setPillarFilter("all")} style={{
                    padding: "3px 10px", borderRadius: 7, fontSize: 11, fontWeight: 600,
                    background: pillarFilter === "all" ? "#2563eb" : "#f3f4f6",
                    color: pillarFilter === "all" ? "#fff" : "#374151",
                    border: "none", cursor: "pointer",
                  }}>All</button>
                  {Object.entries(pillarCount).sort((a,b) => b[1]-a[1]).map(([p, cnt]) => (
                    <button key={p} onClick={() => setPillarFilter(p)} style={{
                      padding: "3px 10px", borderRadius: 7, fontSize: 11, fontWeight: 600,
                      background: pillarFilter === p ? "#2563eb" : "#f3f4f6",
                      color: pillarFilter === p ? "#fff" : "#374151",
                      border: "none", cursor: "pointer",
                    }}>{p} ({cnt})</button>
                  ))}
                </div>
              )}
              {!isGlobal && (
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: "#374151" }}>Min impressions:</span>
                  <input value={minImpressions} onChange={e => setMinImp(e.target.value)}
                    placeholder="0"
                    style={{ width: 64, padding: "3px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12 }} />
                </div>
              )}
              <div style={{ marginLeft: "auto" }}>
                <button onClick={() => exportCSV(filtered, searched)} style={{
                  padding: "5px 14px", borderRadius: 7, fontSize: 12, fontWeight: 600,
                  background: "#f3f4f6", color: "#374151", border: "1px solid #d1d5db", cursor: "pointer",
                }}>
                  📥 Export CSV ({filtered.length})
                </button>
              </div>
            </div>
          </Card>

          {/* Bulk action bar */}
          {selected.size > 0 && (
            <Card style={{ marginBottom: 12, background: "#eff6ff", border: "1px solid #bfdbfe" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "#1e40af" }}>
                  {selected.size} keyword{selected.size > 1 ? "s" : ""} selected
                </span>
                <button onClick={selectAll} style={{
                  padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                  background: "#fff", color: "#374151", border: "1px solid #d1d5db", cursor: "pointer",
                }}>Select All ({filtered.length})</button>
                <button onClick={deselectAll} style={{
                  padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                  background: "#fff", color: "#374151", border: "1px solid #d1d5db", cursor: "pointer",
                }}>Deselect All</button>
                <button onClick={deleteSelected} style={{
                  padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                  background: "#fee2e2", color: "#dc2626", border: "1px solid #fca5a5", cursor: "pointer",
                }}>🗑 Remove Selected</button>
                {onApproveKeywords && (
                  <button onClick={() => {
                    const approved = filtered.filter(r => selected.has(r.keyword))
                    onApproveKeywords(approved, pillars)
                  }} style={{
                    padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                    background: "#d1fae5", color: "#065f46", border: "1px solid #6ee7b7", cursor: "pointer",
                  }}>✅ Approve Selected ({selected.size})</button>
                )}
              </div>
            </Card>
          )}

          {/* Results table */}
          <Card style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr>
                    <th style={{ padding: "8px 6px", textAlign: "center", fontWeight: 700, fontSize: 11, background: "#f9fafb", borderBottom: `1px solid ${T.border}`, width: 36 }}>
                      <input
                        type="checkbox"
                        checked={filtered.length > 0 && selected.size === filtered.length}
                        onChange={() => selected.size === filtered.length ? deselectAll() : selectAll()}
                        style={{ cursor: "pointer" }}
                      />
                    </th>
                    <th style={{ padding: "8px 10px", textAlign: "left", fontWeight: 700, fontSize: 11, background: "#f9fafb", borderBottom: `1px solid ${T.border}`, minWidth: 40 }}>#</th>
                    <th style={{ padding: "8px 10px", textAlign: "left", fontWeight: 700, fontSize: 11, background: "#f9fafb", borderBottom: `1px solid ${T.border}`, minWidth: 200 }}>Keyword</th>
                    <th style={{ padding: "8px 10px", textAlign: "left", fontWeight: 700, fontSize: 11, background: "#f9fafb", borderBottom: `1px solid ${T.border}` }}>Pillar</th>
                    <th style={{ padding: "8px 10px", textAlign: "left", fontWeight: 700, fontSize: 11, background: "#f9fafb", borderBottom: `1px solid ${T.border}` }}>Intent</th>
                    {!isGlobal && <>
                      <SortTh col="impressions" sortBy={sortBy} sortDir={sortDir} onSort={handleSort}>Impressions</SortTh>
                      <SortTh col="clicks"      sortBy={sortBy} sortDir={sortDir} onSort={handleSort}>Clicks</SortTh>
                      <SortTh col="ctr"         sortBy={sortBy} sortDir={sortDir} onSort={handleSort}>CTR</SortTh>
                      <SortTh col="position"    sortBy={sortBy} sortDir={sortDir} onSort={handleSort}>Position</SortTh>
                    </>}
                    <SortTh col="score" sortBy={sortBy} sortDir={sortDir} onSort={handleSort}>Score</SortTh>
                    <th style={{ padding: "8px 6px", textAlign: "center", fontWeight: 700, fontSize: 11, background: "#f9fafb", borderBottom: `1px solid ${T.border}`, width: 36 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr><td colSpan={isGlobal ? 7 : 11} style={{ textAlign: "center", padding: 40, color: T.gray }}>No keywords match current filters.</td></tr>
                  ) : filtered.map((row, i) => {
                    const isTop = i < 10
                    const isSelected = selected.has(row.keyword)
                    return (
                      <tr key={row.keyword || i} style={{
                        background: isSelected ? "#eff6ff" : isTop ? (isGlobal ? "#f0fff4" : "#fffff0") : i % 2 === 0 ? "#fff" : "#f9fafb",
                        borderBottom: `0.5px solid ${T.border}`,
                      }}>
                        <td style={{ padding: "7px 6px", textAlign: "center" }}>
                          <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(row.keyword)} style={{ cursor: "pointer" }} />
                        </td>
                        <td style={{ padding: "7px 10px", color: T.gray, fontWeight: 600 }}>{i+1}{isTop ? " ⭐" : ""}</td>
                        <td style={{ padding: "7px 10px", fontWeight: 500, color: "#1c1c1e", lineHeight: 1.4 }}>{row.keyword}</td>
                        <td style={{ padding: "7px 10px" }}>
                          {row._pillar && (
                            <span style={{
                              display: "inline-block", padding: "1px 7px", borderRadius: 6,
                              fontSize: 10, fontWeight: 600, background: "#dbeafe", color: "#1e40af",
                            }}>{row._pillar}</span>
                          )}
                        </td>
                        <td style={{ padding: "7px 10px" }}><IntentBadge intent={row.intent} /></td>
                        {!isGlobal && <>
                          <td style={{ padding: "7px 10px", textAlign: "right", fontWeight: 600 }}>{(row.impressions||0).toLocaleString()}</td>
                          <td style={{ padding: "7px 10px", textAlign: "right" }}>{(row.clicks||0).toLocaleString()}</td>
                          <td style={{ padding: "7px 10px", textAlign: "right" }}>{row.ctr != null ? (row.ctr * 100).toFixed(2) + "%" : "—"}</td>
                          <td style={{ padding: "7px 10px", textAlign: "right" }}>
                            <span style={{ fontWeight: 600, color: row.position <= 3 ? T.green : row.position <= 10 ? T.orange : T.red }}>
                              {row.position ? row.position.toFixed(1) : "—"}
                            </span>
                          </td>
                        </>}
                        <td style={{ padding: "7px 10px", textAlign: "right" }}>
                          {row.score != null ? (
                            <div style={{
                              display: "inline-flex", alignItems: "center",
                              padding: "1px 8px", borderRadius: 7, fontWeight: 700, fontSize: 11,
                              background: row.score >= 70 ? "#d1fae5" : row.score >= 40 ? "#fef9c3" : "#f3f4f6",
                              color: row.score >= 70 ? "#166534" : row.score >= 40 ? "#854d0e" : "#374151",
                            }}>{Math.round(row.score)}</div>
                          ) : "—"}
                        </td>
                        <td style={{ padding: "7px 6px", textAlign: "center" }}>
                          <button
                            onClick={() => {
                              const keep = result.keywords.filter(k => k !== row)
                              setResult(prev => ({ ...prev, keywords: keep, total: keep.length }))
                              setSelected(new Set())
                            }}
                            title="Remove keyword"
                            style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", fontSize: 13, padding: 2 }}
                          >×</button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ padding: "10px 14px", background: "#f9fafb", borderTop: `0.5px solid ${T.border}`, fontSize: 11, color: T.gray }}>
              Showing {filtered.length} of {result.total} keywords
              {intentFilter !== "all" ? ` (filtered by ${intentFilter})` : ""}
              {" · "}Source: {isGlobal ? "Google Autocomplete (global)" : (result.site_url || "stage-import")}
              {!isGlobal && result.days ? ` · ${result.days}-day window` : ""}
            </div>
          </Card>

          {result.total === 0 && (
            <Card style={{ marginTop: 12, background: "#fef9c3", border: "1px solid #fde68a" }}>
              <div style={{ fontWeight: 700, color: "#854d0e", marginBottom: 6 }}>⚠ No data found for "{searched}"</div>
              <div style={{ fontSize: 12, color: "#92400e", lineHeight: 1.6 }}>
                {isGlobal
                  ? "Google returned no autocomplete suggestions for this query. Try a shorter, more common word (e.g. 'clove' instead of 'adimali clove')."
                  : `No GSC impressions found for "${searched}" in the last ${days} days.`}
              </div>
            </Card>
          )}
        </>
      )}

      {/* ─ Empty idle state ─ */}
      {!result && !loading && !bulkSearching && !error && (
        <Card style={{ textAlign: "center", padding: 50, background: T.bg }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>{isGlobal ? "🌍" : "🔎"}</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "#374151", marginBottom: 6 }}>
            {pillars.length
              ? `${pillars.length} pillars loaded — click "Search All Pillars" to discover keywords`
              : isGlobal ? "Discover what people search on Google" : "Search your GSC data"}
          </div>
          <div style={{ fontSize: 13, color: T.gray, lineHeight: 1.6, maxWidth: 420, margin: "0 auto" }}>
            {pillars.length
              ? "Your pillars from Phase 1 are loaded above. Click the green button to search all pillars at once, or search individually below."
              : isGlobal
                ? "Enter any seed keyword (e.g. \"clove\") to discover 100+ real queries people type on Google — worldwide, no GSC account needed."
                : "Enter any keyword to see how it performs in your Google Search Console data."}
          </div>
        </Card>
      )}
    </div>
  )
}


