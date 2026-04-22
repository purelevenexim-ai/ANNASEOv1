/**
 * Phase Search — unified keyword discovery engine.
 * Combines My GSC Data and Global Google Suggest workflows.
 *
 * Tabs:
 *   0. Setup Guide  — optional OAuth setup documentation
 *   1. Connect      — OAuth setup, site selection, sync data
 *   2. Keywords     — Process + keyword table + top 100
 *   3. Analysis     — intelligence (clusters, graph, insights)
 *   4. Search       — global suggest + GSC keyword lookup
 */
import React, { useState, useEffect, useCallback, useRef } from "react"
import useKw2Store from "../kw2/store"
import * as kw2Api from "../kw2/api"
import * as gscApi from "./api"
import KeywordGraph from "./KeywordGraph"
import GscSetupPage from "./GscSetupPage"
import GscSearchPage from "./GscSearchPage"

/* ── Shared helpers ───────────────────────────────────────────────────────── */

const INTENT_COLOR = {
  purchase:      { bg: "#dcfce7", fg: "#166534", icon: "💰" },
  wholesale:     { bg: "#ede9fe", fg: "#5b21b6", icon: "🏭" },
  commercial:    { bg: "#fef9c3", fg: "#854d0e", icon: "⭐" },
  informational: { bg: "#f3f4f6", fg: "#374151", icon: "📚" },
  navigational:  { bg: "#dbeafe", fg: "#1e40af", icon: "🔗" },
}

function IntentBadge({ intent }) {
  const c = INTENT_COLOR[intent] || INTENT_COLOR.informational
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      padding: "1px 8px", borderRadius: 10, fontSize: 10, fontWeight: 600,
      background: c.bg, color: c.fg,
    }}>
      {c.icon} {intent}
    </span>
  )
}

function MetricCard({ label, value, sub, color = "#3b82f6" }) {
  return (
    <div style={{
      padding: "10px 16px", borderRadius: 8, border: "1px solid #e5e7eb",
      background: "#fff", minWidth: 100, flex: "1 1 100px",
    }}>
      <div style={{ fontSize: 20, fontWeight: 800, color }}>{value ?? "—"}</div>
      <div style={{ fontSize: 11, fontWeight: 600, color: "#374151" }}>{label}</div>
      {sub && <div style={{ fontSize: 10, color: "#9ca3af" }}>{sub}</div>}
    </div>
  )
}

function Btn({ onClick, disabled, children, color = "blue", size = "sm" }) {
  const C = { blue: "#3b82f6", green: "#10b981", red: "#ef4444", gray: "#6b7280", purple: "#8b5cf6" }
  return (
    <button
      onClick={onClick} disabled={disabled}
      style={{
        padding: size === "sm" ? "5px 14px" : "8px 20px",
        borderRadius: 6, border: "none", cursor: disabled ? "not-allowed" : "pointer",
        background: disabled ? "#d1d5db" : (C[color] || C.blue),
        color: "#fff", fontWeight: 600, fontSize: size === "sm" ? 12 : 13,
        opacity: disabled ? 0.7 : 1,
      }}
    >{children}</button>
  )
}

function SectionTitle({ children }) {
  return (
    <div style={{
      fontSize: 13, fontWeight: 700, color: "#1e40af",
      borderBottom: "2px solid #dbeafe", paddingBottom: 5, marginBottom: 12,
    }}>{children}</div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Tab 0: Connect — OAuth + Site Selection + Sync
   ═══════════════════════════════════════════════════════════════════════════ */

function TabConnect({ projectId, status, onRefreshStatus, onSwitchTab }) {
  const [sites, setSites] = useState([])
  const [loadingSites, setLoadingSites] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncDays, setSyncDays] = useState(90)
  const [syncResult, setSyncResult] = useState(null)
  const [error, setError] = useState(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)

  const connected = status?.connected
  const isLiveGSC = status?.status === "connected"
  const isStageImport = status?.status === "connected_stages"

  const handleConnect = useCallback(async () => {
    setError(null)
    try {
      const { auth_url } = await gscApi.getAuthUrl(projectId)
      const popup = window.open(auth_url, "gsc_auth", "width=600,height=700,scrollbars=yes")
      const onMsg = (e) => {
        if (e.data?.type === "gsc_auth_success") {
          window.removeEventListener("message", onMsg)
          onRefreshStatus()
        }
        if (e.data?.type === "gsc_auth_error") {
          window.removeEventListener("message", onMsg)
          setError("Auth failed: " + (e.data.error || "unknown"))
        }
      }
      window.addEventListener("message", onMsg)
      const poll = setInterval(() => {
        if (popup?.closed) { clearInterval(poll); onRefreshStatus() }
      }, 2000)
    } catch (e) { setError(e.message) }
  }, [projectId])

  const handleLoadSites = useCallback(async () => {
    setLoadingSites(true); setError(null)
    try {
      const { sites: s } = await gscApi.listSites(projectId)
      setSites(s || [])
    } catch (e) { setError(e.message) }
    setLoadingSites(false)
  }, [projectId])

  const handleSetSite = useCallback(async (url) => {
    try {
      await gscApi.setSite(projectId, url)
      onRefreshStatus()
    } catch (e) { setError(e.message) }
  }, [projectId])

  const handleSync = useCallback(async () => {
    setSyncing(true); setError(null); setSyncResult(null)
    try {
      const r = await gscApi.syncData(projectId, syncDays)
      setSyncResult(r)
      onRefreshStatus()
    } catch (e) { setError(e.message) }
    setSyncing(false)
  }, [projectId, syncDays])

  const handleDisconnect = useCallback(async () => {
    if (!confirm("Disconnect Google Search Console? Synced data will be kept.")) return
    try {
      await gscApi.disconnect(projectId)
      onRefreshStatus()
    } catch (e) { setError(e.message) }
  }, [projectId])

  const handleImportStages = useCallback(async () => {
    setImporting(true); setError(null)
    try {
      const r = await gscApi.importFromStages(projectId)
      setImportResult(r)
      onRefreshStatus()
    } catch (e) { setError(e.message) }
    setImporting(false)
  }, [projectId])

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Connection status card */}
      <div style={{
        padding: 16, borderRadius: 10,
        border: "2px solid " + (connected ? "#10b981" : "#d1d5db"),
        background: connected ? "#f0fdf4" : "#fafafa",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: (connected || status?.raw_count > 0) ? 12 : 0 }}>
          <span style={{ fontSize: 28 }}>{connected ? "🟢" : "⚪"}</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14 }}>
              {isLiveGSC ? "Connected (Live GSC)" : isStageImport ? "Connected (Stage Import)" : "Not Connected"}
            </div>
            {connected && status?.site_url && (
              <div style={{ fontSize: 11, color: "#6b7280" }}>{status.site_url}</div>
            )}
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            {!connected && (
              <Btn onClick={handleConnect} color="blue" size="md">🔗 Connect Google Search Console</Btn>
            )}
            {connected && (
              <Btn onClick={handleDisconnect} color="red" size="sm">Disconnect</Btn>
            )}
          </div>
        </div>
        {(connected || status?.raw_count > 0) && (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <MetricCard label="Raw Keywords" value={status?.raw_count?.toLocaleString()} color="#3b82f6" />
            <MetricCard label="Processed" value={status?.processed_count?.toLocaleString()} color="#10b981" />
            <MetricCard label="Top 100" value={status?.top100_count?.toLocaleString()} color="#f59e0b" />
            <MetricCard label="Pillars" value={status?.pillar_count} color="#8b5cf6" />
          </div>
        )}
      </div>

      {/* Site selection — only for live GSC */}
      {isLiveGSC && (
        <div>
          <SectionTitle>Select Site</SectionTitle>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
            <Btn onClick={handleLoadSites} disabled={loadingSites} color="gray" size="sm">
              {loadingSites ? "Loading..." : "📋 List My Sites"}
            </Btn>
            {status?.site_url && (
              <span style={{ fontSize: 12, color: "#10b981", fontWeight: 600 }}>
                ✓ Active: {status.site_url}
              </span>
            )}
          </div>
          {sites.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {sites.map((s, i) => (
                <div key={i} style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                  borderRadius: 6, border: "1px solid #e5e7eb", background: "#fff", fontSize: 12,
                }}>
                  <span style={{ flex: 1 }}>{s.url}</span>
                  <span style={{ color: "#9ca3af", fontSize: 10 }}>{s.permission}</span>
                  <Btn onClick={() => handleSetSite(s.url)} color="blue" size="sm">Use This Site</Btn>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Fetch GSC Data — only for live GSC with site selected */}
      {isLiveGSC && status?.site_url && (
        <div>
          <SectionTitle>Fetch GSC Data</SectionTitle>
          <p style={{ fontSize: 12, color: "#6b7280", margin: "0 0 8px" }}>
            Pulls all search queries from your site (1 API call — paginates up to 25,000 rows).
          </p>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select value={syncDays} onChange={(e) => setSyncDays(Number(e.target.value))}
              style={{ padding: "4px 8px", borderRadius: 5, border: "1px solid #d1d5db", fontSize: 12 }}>
              <option value={28}>Last 28 days</option>
              <option value={90}>Last 90 days</option>
              <option value={180}>Last 6 months</option>
            </select>
            <Btn onClick={handleSync} disabled={syncing} color="green">
              {syncing ? "⟳ Syncing..." : "⬇ Fetch Data"}
            </Btn>
          </div>
          {syncResult && (
            <div style={{ marginTop: 8, padding: "8px 12px", borderRadius: 6, background: "#f0fdf4", fontSize: 12, color: "#166534" }}>
              ✓ Fetched {syncResult.fetched?.toLocaleString()} keywords. Total in DB: {syncResult.total_in_db?.toLocaleString()}
            </div>
          )}
        </div>
      )}

      {/* Alternative: Import from previous stages — show when not live GSC */}
      {!isLiveGSC && (
        <div style={{
          padding: 14, borderRadius: 8, background: "#f0f9ff", border: "1px solid #bae6fd",
        }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: "#0369a1", marginBottom: 6 }}>
            📥 {isStageImport ? "Re-import from" : "Alternative: Import from"} Previous Stages
          </div>
          <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 8 }}>
            If you don't have GSC access, import keywords from Stage 1 (crawl) and Stage 2 (discovery).
          </div>
          <Btn onClick={handleImportStages} disabled={importing} color="green" size="sm">
            {importing ? "⟳ Importing..." : "📥 Import Stage Keywords"}
          </Btn>
          {importResult && (
            <div style={{
              marginTop: 8, padding: "8px 12px", borderRadius: 6, fontSize: 12,
              background: importResult.imported > 0 ? "#f0fdf4" : "#fef9c3",
              color: importResult.imported > 0 ? "#166534" : "#854d0e",
            }}>
              {importResult.imported > 0
                ? "✅ Imported " + importResult.imported + " keywords from " + Object.entries(importResult.sources || {}).filter(function(e) { return e[1] > 0 }).map(function(e) { return e[0] + ": " + e[1] }).join(", ")
                : importResult.message || "No keywords found. Complete earlier stages first."}
            </div>
          )}
        </div>
      )}

      {/* Setup hint when not connected */}
      {!connected && (
        <div style={{
          padding: 12, borderRadius: 8, background: "#fefce8", border: "1px solid #fde68a", fontSize: 12,
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <div style={{ fontWeight: 700 }}>Setup Google Search Console</div>
            {onSwitchTab && (
              <button
                onClick={() => onSwitchTab(0)}
                style={{
                  padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 700,
                  background: "#f59e0b", color: "#fff", border: "none", cursor: "pointer",
                }}
              >
                📋 View Setup Guide →
              </button>
            )}
          </div>
          <ol style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
            <li>Click <strong>📋 View Setup Guide →</strong> above for step-by-step instructions</li>
            <li>Add your Google Client ID &amp; Secret in the Setup Guide credentials section</li>
            <li>Click <strong>Connect Google Search Console</strong> above to authorize</li>
          </ol>
        </div>
      )}

      {/* Quick jump to Search when connected */}
      {connected && onSwitchTab && (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={() => onSwitchTab(4)}
            style={{
              padding: "6px 16px", borderRadius: 6, fontSize: 12, fontWeight: 700,
              background: "#3b82f6", color: "#fff", border: "none", cursor: "pointer",
            }}
          >
            🔎 Search Keywords →
          </button>
        </div>
      )}

      {error && (
        <div style={{ padding: 10, borderRadius: 6, background: "#fee2e2", color: "#dc2626", fontSize: 12 }}>
          {error}
        </div>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Tab 1: Keywords — Process + Keyword Table + Top 100
   ═══════════════════════════════════════════════════════════════════════════ */

function TabKeywords({ projectId, profile, status, onRefreshStatus }) {
  const [processing, setProcessing] = useState(false)
  const [result, setResult] = useState(null)
  const [keywords, setKeywords] = useState([])
  const [top100, setTop100] = useState([])
  const [tree, setTree] = useState(null)
  const [pillarFilter, setPillarFilter] = useState("")
  const [intentFilter, setIntentFilter] = useState("")
  const [searchQ, setSearchQ] = useState("")
  const [sortBy, setSortBy] = useState("score")
  const [sortDir, setSortDir] = useState("desc")
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(0)
  const [view, setView] = useState("all")
  const PAGE_SIZE = 50

  const [config, setConfig] = useState(null)

  useEffect(() => {
    gscApi.getConfig(projectId).then(r => { if (r?.config) setConfig(r.config) }).catch(() => {})
  }, [projectId])

  useEffect(() => {
    if (status?.processed_count > 0) loadData()
  }, [status])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [kwRes, t100, treeData] = await Promise.all([
        gscApi.getKeywords(projectId),
        gscApi.getTop100(projectId),
        gscApi.getTree(projectId),
      ])
      setKeywords(kwRes.keywords || [])
      setTop100(t100.items || [])
      setTree(treeData.tree || null)
    } catch (e) { setError(e.message) }
    setLoading(false)
  }, [projectId])

  const activePillars = config?.pillars || (function() {
    const raw = profile?.pillar_keywords || profile?.pillars || []
    if (typeof raw === "string") { try { return JSON.parse(raw || "[]") } catch(e) { return [] } }
    return raw
  })()

  const handleProcess = useCallback(async () => {
    setProcessing(true); setError(null); setResult(null)
    try {
      const r = await gscApi.processKeywords(projectId, activePillars)
      setResult(r)
      onRefreshStatus()
      await loadData()
    } catch (e) { setError(e.message) }
    setProcessing(false)
  }, [projectId, activePillars])

  const handleSort = (col) => {
    if (sortBy === col) setSortDir(d => d === "desc" ? "asc" : "desc")
    else { setSortBy(col); setSortDir("desc") }
    setPage(0)
  }

  const uniquePillars = [...new Set(keywords.map(k => k.pillar).filter(Boolean))]
  const uniqueIntents = [...new Set(keywords.map(k => k.intent).filter(Boolean))]

  const activeList = view === "top100" ? top100 : keywords
  const filtered = activeList
    .filter(k => !pillarFilter || k.pillar === pillarFilter)
    .filter(k => !intentFilter || k.intent === intentFilter)
    .filter(k => !searchQ || k.keyword?.toLowerCase().includes(searchQ.toLowerCase()))
    .sort((a, b) => {
      const v = (x) => (typeof x[sortBy] === "number" ? x[sortBy] : 0)
      return sortDir === "desc" ? v(b) - v(a) : v(a) - v(b)
    })

  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  const quickWins = top100.filter(k => k.position > 10 && k.impressions > 200)
  const moneyKws = top100.filter(k => ["purchase", "wholesale"].includes(k.intent))

  const SortHdr = ({ col, label }) => (
    <th onClick={() => handleSort(col)}
      style={{ cursor: "pointer", padding: "6px 8px", fontSize: 10, fontWeight: 700, color: "#6b7280", whiteSpace: "nowrap", background: "#f9fafb", userSelect: "none" }}>
      {label} {sortBy === col ? (sortDir === "desc" ? "▼" : "▲") : "⇅"}
    </th>
  )

  const viewBtn = (v, label) => (
    <button onClick={() => { setView(v); setPage(0) }} style={{
      padding: "5px 14px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
      border: view === v ? "2px solid #3b82f6" : "1px solid #d1d5db",
      background: view === v ? "#eff6ff" : "#fff", color: view === v ? "#1e40af" : "#6b7280",
    }}>{label}</button>
  )

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Process section */}
      <div style={{
        padding: 14, borderRadius: 8, background: "#f9fafb", border: "1px solid #e5e7eb",
        display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 13 }}>Classify & Score Keywords</div>
          <div style={{ fontSize: 11, color: "#6b7280" }}>
            Assigns keywords to pillars, classifies intent, and scores. Picks top 100 per pillar.
            {activePillars.length > 0 && " Using " + activePillars.length + " pillars."}
          </div>
          {activePillars.length > 0 && (
            <div style={{ marginTop: 4, display: "flex", gap: 4, flexWrap: "wrap" }}>
              {activePillars.slice(0, 12).map((p, i) => (
                <span key={i} style={{
                  fontSize: 10, padding: "1px 8px", borderRadius: 10, background: "#dbeafe", color: "#1e40af",
                }}>{typeof p === "string" ? p : p.name || p}</span>
              ))}
              {activePillars.length > 12 && (
                <span style={{ fontSize: 10, color: "#9ca3af" }}>+{activePillars.length - 12} more</span>
              )}
            </div>
          )}
        </div>
        <Btn onClick={handleProcess} disabled={processing || !status?.raw_count} color="blue">
          {processing ? "⟳ Processing..." : "▶ Run Classification"}
        </Btn>
      </div>

      {result && (
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <MetricCard label="Processed" value={result.processed?.toLocaleString()} color="#3b82f6" />
          <MetricCard label="Top 100" value={result.top100?.toLocaleString()} color="#f59e0b" />
          <MetricCard label="Pillars Active" value={result.pillars} color="#10b981" />
        </div>
      )}

      {error && (
        <div style={{ padding: 10, borderRadius: 6, background: "#fee2e2", color: "#dc2626", fontSize: 12 }}>{error}</div>
      )}

      {!status?.raw_count && (
        <div style={{ padding: 16, borderRadius: 8, background: "#fafafa", border: "1px solid #e5e7eb", color: "#9ca3af", fontSize: 13 }}>
          No raw keyword data yet. Go to <strong>Connect</strong> tab to sync GSC data or import from stages.
        </div>
      )}

      {/* Results section */}
      {keywords.length > 0 && (
        <>
          {/* Summary cards */}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <MetricCard label="All Keywords" value={keywords.length} color="#3b82f6" />
            <MetricCard label="Top 100" value={top100.length} color="#f59e0b" sub="across all pillars" />
            <MetricCard label="Money Keywords" value={moneyKws.length} color="#10b981" sub="purchase + wholesale" />
            <MetricCard label="Quick Wins" value={quickWins.length} color="#ef4444" sub="pos > 10, imp > 200" />
          </div>

          {/* View toggle */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {viewBtn("all", "📋 All (" + keywords.length + ")")}
            {viewBtn("top100", "⭐ Top 100 (" + top100.length + ")")}
            {viewBtn("quickwins", "⚡ Quick Wins (" + quickWins.length + ")")}
            {viewBtn("tree", "🌳 Tree View")}
          </div>

          {view === "tree" && tree ? (
            <GscTree tree={tree} />
          ) : view === "quickwins" ? (
            <div>
              <p style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>
                High impressions but ranking below position 10 — easiest wins.
              </p>
              {quickWins.length === 0 ? (
                <p style={{ color: "#9ca3af", fontSize: 12 }}>No quick wins found.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {quickWins.sort((a, b) => b.impressions - a.impressions).map((kw, i) => (
                    <div key={i} style={{
                      padding: "8px 12px", borderRadius: 6, border: "1px solid #fde68a",
                      background: "#fffbeb", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
                    }}>
                      <span style={{ flex: 1, fontSize: 12, fontWeight: 500 }}>{kw.keyword}</span>
                      <span style={{ fontSize: 10, color: "#8b5cf6", fontWeight: 600 }}>{kw.pillar}</span>
                      <span style={{ fontSize: 10 }}>pos: <strong style={{ color: "#ef4444" }}>{kw.position?.toFixed(1)}</strong></span>
                      <span style={{ fontSize: 10 }}>imp: <strong>{(kw.impressions || 0).toLocaleString()}</strong></span>
                      <IntentBadge intent={kw.intent} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <>
              {/* Filters */}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <input value={searchQ} onChange={e => { setSearchQ(e.target.value); setPage(0) }}
                  placeholder="Search keywords..."
                  style={{ padding: "4px 8px", borderRadius: 5, border: "1px solid #d1d5db", fontSize: 12, width: 160 }} />
                {uniquePillars.length > 1 && (
                  <select value={pillarFilter} onChange={e => { setPillarFilter(e.target.value); setPage(0) }}
                    style={{ padding: "4px 8px", borderRadius: 5, border: "1px solid #d1d5db", fontSize: 12 }}>
                    <option value="">All pillars</option>
                    {uniquePillars.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                )}
                {uniqueIntents.length > 1 && (
                  <select value={intentFilter} onChange={e => { setIntentFilter(e.target.value); setPage(0) }}
                    style={{ padding: "4px 8px", borderRadius: 5, border: "1px solid #d1d5db", fontSize: 12 }}>
                    <option value="">All intents</option>
                    {uniqueIntents.map(i => <option key={i} value={i}>{i}</option>)}
                  </select>
                )}
                <span style={{ fontSize: 10, color: "#9ca3af" }}>
                  {filtered.length} results
                </span>
              </div>

              {/* Keyword table */}
              {loading ? (
                <p style={{ color: "#9ca3af", fontSize: 12 }}>Loading...</p>
              ) : (
                <>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <thead>
                        <tr>
                          <th style={{ padding: "6px 8px", background: "#f9fafb", fontSize: 10, fontWeight: 700, color: "#6b7280", textAlign: "left" }}>Keyword</th>
                          <th style={{ padding: "6px 8px", background: "#f9fafb", fontSize: 10, fontWeight: 700, color: "#6b7280" }}>Pillar</th>
                          <SortHdr col="impressions" label="Impressions" />
                          <SortHdr col="clicks" label="Clicks" />
                          <SortHdr col="ctr" label="CTR" />
                          <SortHdr col="position" label="Pos." />
                          <SortHdr col="score" label="Score" />
                          <th style={{ padding: "6px 8px", background: "#f9fafb", fontSize: 10, fontWeight: 700, color: "#6b7280" }}>Intent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {paginated.map((kw, i) => (
                          <tr key={i} style={{ borderBottom: "1px solid #f3f4f6", background: kw.top100 ? "#fffbeb" : "#fff" }}>
                            <td style={{ padding: "5px 8px" }}>
                              {kw.top100 ? <span style={{ fontSize: 9, marginRight: 4 }}>★</span> : null}
                              {kw.keyword}
                              {kw.opportunity_score > 5 && <span title="Quick win" style={{ marginLeft: 6, fontSize: 9, color: "#f97316" }}>⚡</span>}
                            </td>
                            <td style={{ padding: "5px 8px", color: "#8b5cf6", fontSize: 10, fontWeight: 600 }}>{kw.pillar}</td>
                            <td style={{ padding: "5px 8px", textAlign: "right" }}>{(kw.impressions || 0).toLocaleString()}</td>
                            <td style={{ padding: "5px 8px", textAlign: "right" }}>{(kw.clicks || 0).toLocaleString()}</td>
                            <td style={{ padding: "5px 8px", textAlign: "right" }}>{kw.ctr ? (kw.ctr * 100).toFixed(1) + "%" : "—"}</td>
                            <td style={{ padding: "5px 8px", textAlign: "right" }}>{kw.position ? kw.position.toFixed(1) : "—"}</td>
                            <td style={{ padding: "5px 8px", textAlign: "right", fontWeight: 700, color: kw.score > 50 ? "#10b981" : kw.score > 25 ? "#f59e0b" : "#6b7280" }}>
                              {kw.score?.toFixed(1)}
                            </td>
                            <td style={{ padding: "5px 8px" }}><IntentBadge intent={kw.intent || "informational"} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {totalPages > 1 && (
                    <div style={{ display: "flex", gap: 6, marginTop: 8, alignItems: "center" }}>
                      <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                        style={{ padding: "3px 10px", fontSize: 11, border: "1px solid #d1d5db", borderRadius: 5, cursor: "pointer" }}>‹</button>
                      <span style={{ fontSize: 11, color: "#6b7280" }}>Page {page + 1} / {totalPages}</span>
                      <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                        style={{ padding: "3px 10px", fontSize: 11, border: "1px solid #d1d5db", borderRadius: 5, cursor: "pointer" }}>›</button>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Tab 2: Analysis — Phase 2 Intelligence
   ═══════════════════════════════════════════════════════════════════════════ */

function TabAnalysis({ projectId, status }) {
  const [running, setRunning] = useState(false)
  const [pipelineResult, setPipelineResult] = useState(null)
  const [error, setError] = useState(null)
  const [view, setView] = useState("overview")
  const [clusters, setClusters] = useState(null)
  const [graphData, setGraphData] = useState(null)
  const [insights, setInsights] = useState(null)
  const [authority, setAuthority] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)

  useEffect(() => {
    if (status?.processed_count > 0) loadExistingData()
  }, [status])

  const loadExistingData = useCallback(async () => {
    try {
      const [c, g, ins, auth] = await Promise.all([
        gscApi.getClusters(projectId),
        gscApi.getGraph(projectId),
        gscApi.getInsights(projectId),
        gscApi.getAuthority(projectId),
      ])
      if (c.count > 0) setClusters(c.clusters)
      if (g.graph?.nodes?.length > 0) setGraphData(g.graph)
      if (Object.keys(ins.insights || {}).length > 0) setInsights(ins.insights)
      if (Object.keys(auth.authority || {}).length > 0) setAuthority(auth.authority)
    } catch (e) { /* silent */ }
  }, [projectId])

  const handleRunPipeline = useCallback(async () => {
    setRunning(true); setError(null); setPipelineResult(null)
    try {
      const r = await gscApi.runIntelligence(projectId)
      setPipelineResult(r)
      await loadExistingData()
    } catch (e) { setError(e.message) }
    setRunning(false)
  }, [projectId])

  const tabBtn = (v, label) => (
    <button onClick={() => setView(v)} style={{
      padding: "5px 14px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
      border: view === v ? "2px solid #8b5cf6" : "1px solid #d1d5db",
      background: view === v ? "#f5f3ff" : "#fff", color: view === v ? "#5b21b6" : "#6b7280",
    }}>{label}</button>
  )

  const hasData = clusters || graphData || insights

  if (!status?.processed_count) {
    return (
      <div style={{ padding: 16, borderRadius: 8, background: "#fafafa", border: "1px solid #e5e7eb", color: "#9ca3af", fontSize: 13 }}>
        Process keywords first in the <strong>Keywords</strong> tab before running analysis.
      </div>
    )
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Pipeline runner */}
      <div style={{
        padding: 14, borderRadius: 8, background: "#f5f3ff", border: "1px solid #ddd6fe",
        display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: "#5b21b6" }}>🧠 Deep Analysis Pipeline</div>
          <div style={{ fontSize: 11, color: "#6b7280" }}>
            Embeddings → AI Intent → Clustering → Graph → Scoring v2 → Insights
          </div>
        </div>
        <Btn onClick={handleRunPipeline} disabled={running} color="purple">
          {running ? "⟳ Running Pipeline..." : "▶ Run Analysis"}
        </Btn>
      </div>

      {pipelineResult && (
        <div style={{ padding: 12, borderRadius: 8, background: "#f0fdf4", border: "1px solid #bbf7d0", fontSize: 12 }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>✅ Pipeline Complete ({pipelineResult.total_time}s)</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {Object.entries(pipelineResult.steps || {}).map(([step, data]) => (
              <span key={step} style={{ padding: "2px 8px", background: "#dcfce7", borderRadius: 6, fontSize: 10, fontWeight: 600 }}>
                {step}: {data.time}s
              </span>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div style={{ padding: 10, borderRadius: 6, background: "#fee2e2", color: "#dc2626", fontSize: 12 }}>{error}</div>
      )}

      {/* Authority cards */}
      {authority && Object.keys(authority).length > 0 && (
        <div>
          <SectionTitle>Pillar Authority</SectionTitle>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {Object.entries(authority).map(([pillar, data]) => (
              <div key={pillar} style={{
                padding: "10px 14px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#fff",
                minWidth: 120, flex: "1 1 120px",
              }}>
                <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>{pillar}</div>
                <div style={{
                  fontSize: 22, fontWeight: 800,
                  color: data.authority_score >= 60 ? "#10b981" : data.authority_score >= 30 ? "#f59e0b" : "#ef4444",
                }}>{data.authority_score}</div>
                <div style={{ fontSize: 10, color: "#6b7280" }}>
                  {data.status} · {data.coverage} kws · {data.cluster_depth} clusters
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sub-navigation */}
      {hasData && (
        <>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {tabBtn("overview", "📊 Overview")}
            {clusters && tabBtn("clusters", "🧩 Clusters (" + Object.keys(clusters).length + ")")}
            {graphData && tabBtn("graph", "🌐 Graph (" + (graphData.nodes?.length || 0) + ")")}
            {insights && tabBtn("insights", "🔥 Insights")}
          </div>

          {view === "overview" && insights && (
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <MetricCard label="Quick Wins" value={insights.quick_wins?.items?.length || 0} color="#f59e0b" sub="position 5-20, high impressions" />
              <MetricCard label="Money Keywords" value={insights.money_keywords?.items?.length || 0} color="#10b981" sub="transactional + demand" />
              <MetricCard label="Content Gaps" value={insights.content_gaps?.items?.length || 0} color="#ef4444" sub="clusters without purchase" />
              <MetricCard label="Link Suggestions" value={insights.linking?.items?.length || 0} color="#8b5cf6" sub="supporting → purchase" />
            </div>
          )}

          {view === "clusters" && clusters && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {Object.entries(clusters).map(([name, kws]) => (
                <div key={name} style={{ padding: 12, borderRadius: 8, border: "1px solid #e5e7eb", background: "#fafafa" }}>
                  <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>
                    🧩 {name} <span style={{ fontWeight: 400, fontSize: 11, color: "#6b7280" }}>({kws.length} keywords)</span>
                  </div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {kws.slice(0, 20).map((k, i) => (
                      <span key={i} style={{ padding: "2px 8px", borderRadius: 10, fontSize: 10, background: "#ede9fe", color: "#5b21b6" }}>{k.keyword}</span>
                    ))}
                    {kws.length > 20 && <span style={{ fontSize: 10, color: "#9ca3af", padding: "2px 4px" }}>+{kws.length - 20} more</span>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {view === "graph" && graphData && (
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <div style={{ flex: "1 1 400px", border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden", background: "#fff" }}>
                <KeywordGraph data={graphData} width={600} height={500} onNodeClick={setSelectedNode} />
              </div>
              {selectedNode && (
                <div style={{ flex: "0 0 250px", padding: 12, borderRadius: 8, border: "1px solid #e5e7eb", background: "#fafafa" }}>
                  <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 8 }}>{selectedNode.id}</div>
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Pillar: <strong style={{ color: "#8b5cf6" }}>{selectedNode.group || "—"}</strong></div>
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Intent: <strong>{selectedNode.intent || "—"}</strong></div>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>Score: <strong style={{ color: "#10b981" }}>{selectedNode.score || "—"}</strong></div>
                  {selectedNode.top100 && <span style={{ fontSize: 10, padding: "1px 8px", borderRadius: 10, background: "#fef9c3", color: "#854d0e", fontWeight: 600 }}>★ Top 100</span>}
                </div>
              )}
            </div>
          )}

          {view === "insights" && insights && <InsightsPanel insights={insights} />}
        </>
      )}

      {!hasData && !running && (
        <div style={{ padding: 16, borderRadius: 8, background: "#fafafa", border: "1px solid #e5e7eb", color: "#6b7280", fontSize: 13 }}>
          Click <strong>Run Analysis</strong> to generate clusters, graph, and insights.
        </div>
      )}
    </div>
  )
}

/* ── Insights Panel ──────────────────────────────────────────────────────── */

function InsightsPanel({ insights }) {
  const [section, setSection] = useState("quick_wins")

  const secBtn = (s, label) => (
    <button onClick={() => setSection(s)} style={{
      padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: "pointer",
      border: section === s ? "2px solid #f59e0b" : "1px solid #d1d5db",
      background: section === s ? "#fffbeb" : "#fff", color: section === s ? "#92400e" : "#6b7280",
    }}>{label}</button>
  )

  const quickWins = insights?.quick_wins?.items || []
  const moneyKws = insights?.money_keywords?.items || []
  const gaps = insights?.content_gaps?.items || []
  const links = insights?.linking?.items || []
  const opps = insights?.opportunities?.items || []

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {secBtn("quick_wins", "🔥 Quick Wins (" + quickWins.length + ")")}
        {secBtn("money", "💰 Money (" + moneyKws.length + ")")}
        {secBtn("gaps", "📉 Gaps (" + gaps.length + ")")}
        {secBtn("linking", "🔗 Links (" + links.length + ")")}
        {secBtn("opportunities", "⚡ Opps (" + opps.length + ")")}
      </div>

      {section === "quick_wins" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {quickWins.slice(0, 30).map((kw, i) => (
            <div key={i} style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #fde68a", background: "#fffbeb", display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
              <span style={{ flex: 1, fontWeight: 500 }}>{kw.keyword}</span>
              <span style={{ fontSize: 10, color: "#8b5cf6" }}>{kw.pillar}</span>
              <span style={{ fontSize: 10 }}>pos: <strong style={{ color: "#ef4444" }}>{kw.position}</strong></span>
              <span style={{ fontSize: 10 }}>imp: <strong>{kw.impressions?.toLocaleString()}</strong></span>
            </div>
          ))}
          {quickWins.length === 0 && <p style={{ color: "#9ca3af", fontSize: 12 }}>No quick wins found.</p>}
        </div>
      )}

      {section === "money" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {moneyKws.slice(0, 30).map((kw, i) => (
            <div key={i} style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #bbf7d0", background: "#f0fdf4", display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
              <span style={{ flex: 1, fontWeight: 500 }}>💰 {kw.keyword}</span>
              <span style={{ fontSize: 10, color: "#8b5cf6" }}>{kw.pillar}</span>
              <IntentBadge intent={kw.intent} />
              <span style={{ fontSize: 10 }}>imp: {kw.impressions?.toLocaleString()}</span>
            </div>
          ))}
          {moneyKws.length === 0 && <p style={{ color: "#9ca3af", fontSize: 12 }}>No money keywords found.</p>}
        </div>
      )}

      {section === "gaps" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {gaps.map((gap, i) => (
            <div key={i} style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid #fecaca", background: "#fef2f2" }}>
              <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>📉 {gap.cluster}</div>
              <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>{gap.suggestion}</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {gap.sample_keywords?.map((k, j) => (
                  <span key={j} style={{ fontSize: 10, padding: "1px 6px", borderRadius: 8, background: "#fee2e2" }}>{k}</span>
                ))}
              </div>
            </div>
          ))}
          {gaps.length === 0 && <p style={{ color: "#9ca3af", fontSize: 12 }}>No content gaps detected.</p>}
        </div>
      )}

      {section === "linking" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {links.slice(0, 30).map((lnk, i) => (
            <div key={i} style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #ddd6fe", background: "#f5f3ff", display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
              <span style={{ flex: 1 }}>{lnk.from_keyword}</span>
              <span style={{ color: "#6b7280" }}>→</span>
              <span style={{ flex: 1, fontWeight: 600, color: "#10b981" }}>{lnk.to_keyword}</span>
              <span style={{ fontSize: 10, color: "#8b5cf6" }}>{lnk.pillar}</span>
            </div>
          ))}
          {links.length === 0 && <p style={{ color: "#9ca3af", fontSize: 12 }}>No linking suggestions yet.</p>}
        </div>
      )}

      {section === "opportunities" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {opps.slice(0, 20).map((kw, i) => (
            <div key={i} style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #fed7aa", background: "#fff7ed", display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
              <span style={{ flex: 1, fontWeight: 500 }}>⚡ {kw.keyword}</span>
              <span style={{ fontSize: 10, color: "#8b5cf6" }}>{kw.pillar}</span>
              <span style={{ fontSize: 10 }}>pos: <strong style={{ color: "#ef4444" }}>{kw.position}</strong></span>
              <span style={{ fontSize: 10 }}>imp: <strong>{kw.impressions?.toLocaleString()}</strong></span>
            </div>
          ))}
          {opps.length === 0 && <p style={{ color: "#9ca3af", fontSize: 12 }}>No opportunities found.</p>}
        </div>
      )}
    </div>
  )
}

/* ── Tree View ──────────────────────────────────────────────────────────── */

function GscTree({ tree }) {
  const [openPillars, setOpenPillars] = useState({})
  const [openGroups, setOpenGroups] = useState({})
  const u = tree?.universe
  if (!u) return <p style={{ color: "#9ca3af", fontSize: 12 }}>No tree data.</p>

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 800, fontSize: 14, marginBottom: 12 }}>
        🌐 {u.name} — {u.total} keywords
      </div>
      {(u.pillars || []).map((pillar, pi) => {
        const pOpen = openPillars[pi]
        return (
          <div key={pi} style={{ marginBottom: 8, borderLeft: "3px solid #3b82f6", paddingLeft: 10 }}>
            <div onClick={() => setOpenPillars(s => ({ ...s, [pi]: !s[pi] }))}
              style={{ cursor: "pointer", fontWeight: 700, fontSize: 13, display: "flex", gap: 8, alignItems: "center", padding: "4px 0" }}>
              <span style={{ fontSize: 8 }}>{pOpen ? "▼" : "▶"}</span>
              🎯 {pillar.name}
              <span style={{ fontSize: 10, color: "#6b7280" }}>({pillar.total} kws, ★{pillar.top100})</span>
            </div>
            {pOpen && (
              <div style={{ paddingLeft: 14 }}>
                {(pillar.groups || []).map((grp, gi) => {
                  const gKey = pi + "-" + gi
                  const gOpen = openGroups[gKey]
                  return (
                    <div key={gi} style={{ marginBottom: 6 }}>
                      <div onClick={() => setOpenGroups(s => ({ ...s, [gKey]: !s[gKey] }))}
                        style={{ cursor: "pointer", display: "flex", gap: 6, alignItems: "center", padding: "3px 0" }}>
                        <span style={{ fontSize: 8 }}>{gOpen ? "▼" : "▶"}</span>
                        <IntentBadge intent={grp.intent} />
                        <span style={{ color: "#374151" }}>{grp.name}</span>
                        <span style={{ fontSize: 10, color: "#9ca3af" }}>({grp.count})</span>
                      </div>
                      {gOpen && (
                        <div style={{ paddingLeft: 16 }}>
                          {(grp.keywords || []).slice(0, 20).map((kw, ki) => (
                            <div key={ki} style={{
                              padding: "2px 0", display: "flex", gap: 8, alignItems: "center",
                              opacity: kw.top100 ? 1 : 0.6, borderBottom: "1px solid #f9fafb",
                            }}>
                              <span style={{ fontSize: 10, color: "#f59e0b" }}>{kw.top100 ? "★" : "·"}</span>
                              <span style={{ flex: 1 }}>{kw.keyword}</span>
                              <span style={{ color: "#9ca3af", fontSize: 10 }}>
                                imp:{kw.impressions?.toLocaleString()} pos:{kw.position?.toFixed(1)}
                              </span>
                              <span style={{ fontWeight: 700, color: "#10b981", fontSize: 10 }}>{kw.score?.toFixed(1)}</span>
                            </div>
                          ))}
                          {(grp.keywords || []).length > 20 && (
                            <div style={{ fontSize: 10, color: "#9ca3af", padding: "4px 0" }}>
                              ... and {grp.keywords.length - 20} more
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Main PhaseGSC
   ═══════════════════════════════════════════════════════════════════════════ */

export default function PhaseGSC({
  projectId,
  sessionId,
  onComplete,
  mode = "brand",
  onContinue,
  allowWorkflowContinue = true,
}) {
  const { profile } = useKw2Store()
  const [activeTab, setActiveTab] = useState(0)
  const [status, setStatus] = useState(null)
  const [statusLoading, setStatusLoading] = useState(true)
  const defaultTabApplied = useRef(false)
  const discoveredRef = useRef({ keywords: [], pillars: [] })
  const approvedRef = useRef({ keywords: [], pillars: [] })
  const [importing, setImporting] = useState(false)
  const [approveMsg, setApproveMsg] = useState("")

  const refreshStatus = useCallback(async () => {
    try {
      const s = await gscApi.getStatus(projectId)
      setStatus(s)
    } catch (e) { /* silent */ }
    setStatusLoading(false)
  }, [projectId])

  useEffect(() => { refreshStatus() }, [projectId])

  // Mode-aware initial tab selection.
  useEffect(() => {
    if (!defaultTabApplied.current && status !== null) {
      defaultTabApplied.current = true
      if (mode === "review" || mode === "expand") {
        setActiveTab(4)
      } else {
        setActiveTab(status.connected ? 4 : 0)
      }
    }
  }, [status, mode])

  const handleKeywordsReady = useCallback((keywords, pillars) => {
    discoveredRef.current = { keywords: keywords || [], pillars: pillars || [] }
  }, [])

  const handleApproveKeywords = useCallback((keywords, pillars) => {
    approvedRef.current = { keywords: keywords || [], pillars: pillars || [] }
    const count = (keywords || []).length
    setApproveMsg(`✅ ${count} keyword${count !== 1 ? "s" : ""} approved — click Continue to import`)
    setTimeout(() => setApproveMsg(""), 5000)
  }, [])

  const handleContinue = useCallback(async () => {
    // Use approved selection if available, otherwise fall back to all discovered
    const approved = approvedRef.current
    const { keywords: allKw, pillars: allPillars } = discoveredRef.current
    const keywords = approved.keywords.length ? approved.keywords : allKw
    const usedPillars = approved.keywords.length ? approved.pillars : allPillars

    if (keywords.length && projectId && sessionId) {
      setImporting(true)
      try {
        const mapped = keywords.map(kw => ({
          keyword: kw.keyword,
          source: "search_import",
          pillar: kw._pillar || "",
          score: kw.score || 0,
        }))
        const seeds = [...new Set(usedPillars.filter(Boolean))]
        const sessionName = seeds.length ? seeds.join(", ") : ""
        await kw2Api.importKeywords(projectId, sessionId, {
          keywords: mapped,
          seeds,
          session_name: sessionName,
        })
        // Refresh session in store so Phase 2 picks up updated seed_keywords
        try {
          const { session: fresh } = await kw2Api.getSession(projectId, sessionId)
          if (fresh) useKw2Store.getState().setSessionData(fresh)
        } catch { /* non-fatal */ }
      } catch (e) {
        console.warn("Import keywords failed:", e)
      }
      setImporting(false)
    }
    if (onComplete) onComplete()
    if (onContinue) onContinue()
  }, [onComplete, onContinue, projectId, sessionId])

  const tabs = [
    { n: 0, label: "⚙ Setup Guide", icon: "⚙" },
    { n: 1, label: "1. Connect",    icon: "🔗" },
    { n: 2, label: "2. Keywords",   icon: "📋" },
    { n: 3, label: "3. Analysis",   icon: "🧠" },
    { n: 4, label: "4. Search",     icon: "🔎" },
  ]

  const tabStyle = (n) => ({
    padding: "6px 16px", borderRadius: 6, fontSize: 12, fontWeight: activeTab === n ? 700 : 400,
    border: activeTab === n ? "2px solid #3b82f6" : "1px solid #e5e7eb",
    background: activeTab === n ? "#eff6ff" : "#fff",
    color: activeTab === n ? "#1e40af" : "#6b7280",
    cursor: "pointer",
  })

  if (statusLoading) {
    return (
      <div style={{ padding: 24, borderRadius: 10, border: "1px solid #e5e7eb", background: "#fff" }}>
        <p style={{ color: "#9ca3af" }}>Loading Search status...</p>
      </div>
    )
  }

  return (
    <div style={{ borderRadius: 10, border: "1px solid #e5e7eb", background: "#fff", overflow: "hidden" }}>
      {/* Header */}
      <div style={{
        padding: "14px 18px", borderBottom: "1px solid #e5e7eb",
        background: "linear-gradient(135deg, #1e40af 0%, #1d4ed8 100%)",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <div style={{ color: "#fff", fontWeight: 800, fontSize: 16 }}>
            🔎 Search Engine
          </div>
          <div style={{ color: "#93c5fd", fontSize: 11 }}>
            Global discovery + My GSC data → classify per pillar → pipeline-ready keywords
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div style={{
            padding: "3px 10px", borderRadius: 10, fontSize: 10, fontWeight: 700,
            background: status?.connected ? "#10b981" : "#6b7280", color: "#fff",
          }}>
            {status?.connected ? "🟢 Source Connected" : "⚪ No Source Connected"}
          </div>
          {allowWorkflowContinue && mode !== "review" && (
            <button onClick={handleContinue} disabled={importing} style={{
              padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 700,
              background: importing ? "#6b7280" : "#10b981", color: "#fff", border: "none",
              cursor: importing ? "wait" : "pointer",
            }}>
              {importing ? "⟳ Importing..." : "Continue to Generate →"}
            </button>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ display: "flex", gap: 6, padding: "10px 16px", borderBottom: "1px solid #f3f4f6", background: "#fafafa", flexWrap: "wrap" }}>
        {tabs.map(t => (
          <button key={t.n} onClick={() => setActiveTab(t.n)} style={tabStyle(t.n)}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ padding: 18 }}>
        {activeTab === 0 && (
          <GscSetupPage projectId={projectId} />
        )}
        {activeTab === 1 && (
          <TabConnect projectId={projectId} status={status} onRefreshStatus={refreshStatus} onSwitchTab={setActiveTab} />
        )}
        {activeTab === 2 && (
          <TabKeywords projectId={projectId} profile={profile} status={status} onRefreshStatus={refreshStatus} />
        )}
        {activeTab === 3 && (
          <TabAnalysis projectId={projectId} status={status} />
        )}
        {activeTab === 4 && (
          <>
            {approveMsg && (
              <div style={{ padding: "8px 16px", marginBottom: 12, background: "#d1fae5", border: "1px solid #6ee7b7", borderRadius: 8, fontSize: 13, fontWeight: 600, color: "#065f46" }}>
                {approveMsg}
              </div>
            )}
            <GscSearchPage
            projectId={projectId}
            sessionId={sessionId}
            defaultSource={mode === "review" ? "gsc" : "global"}
            allowedSources={mode === "review" ? ["gsc"] : ["global", "gsc"]}
            sourceLocked={mode === "review"}
            onKeywordsReady={handleKeywordsReady}
            onApproveKeywords={handleApproveKeywords}
          />
          </>
        )}
      </div>
    </div>
  )
}
