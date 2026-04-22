/**
 * Phase 2 — Keyword Universe Generation.
 * 8-layer pipeline: seeds → rules → audience → attribute → problem → suggest → competitor → AI expand.
 * SSE streaming with per-layer progress bars, notifications, debug console.
 */
import React, { useState, useCallback, useRef } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, ProgressBar, StatsRow, usePhaseRunner, PhaseResult, NotificationList, TagInput } from "./shared"
import DataTable from "./DataTable"

const LAYERS = ["seeds", "rules", "audience", "attribute", "problem", "suggest", "competitor", "bi_competitor", "ai_expand"]
const LAYER_LABELS = {
  seeds: "Seed Keywords",
  rules: "Rule Templates",
  audience: "Audience Combos",
  attribute: "BI Attributes",
  problem: "Trust/Quality",
  suggest: "Google Suggest",
  competitor: "Competitor Crawl",
  bi_competitor: "Competitor Intel",
  ai_expand: "AI Expansion",
}

export default function Phase2({ projectId, sessionId, onComplete }) {
  const { setUniverseCount, setActivePhase, profile, goNextPhase, mode, session } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P2")

  const [result, setResult] = useState(null)
  const [layerCounts, setLayerCounts] = useState({})
  const [activeLayer, setActiveLayer] = useState(null)
  const [confirmedPillars, setConfirmedPillars] = useState([])
  const [availPillars, setAvailPillars] = useState([])
  const [manualPillar, setManualPillar] = useState("")
  const [readme, setReadme] = useState("")
  const [readmeLoading, setReadmeLoading] = useState(false)
  const [keywords, setKeywords] = useState([])
  const [confirmedModifiers, setConfirmedModifiers] = useState([])
  const cancelRef = useRef(null)
  // Track if pillars have been manually edited — prevents useEffect from overwriting user additions
  const pillarsInitialized = useRef(false)

  // Load pillars + modifiers: merge session seed_keywords + profile pillars
  // Cleanup SSE stream on unmount
  React.useEffect(() => {
    return () => { if (cancelRef.current) cancelRef.current() }
  }, [])

  React.useEffect(() => {
    // Only initialize pillars once — never overwrite manual additions after first load
    if (pillarsInitialized.current) return

    const sessionSeeds = Array.isArray(session?.seed_keywords)
      ? session.seed_keywords.filter(Boolean)
      : []

    const storePillars = Array.isArray(profile?.pillars) ? profile.pillars.filter(Boolean) : []
    const storeMods = Array.isArray(profile?.modifiers) ? profile.modifiers.filter(Boolean) : []

    // Merge: seeds + profile pillars (deduplicated, case-insensitive)
    const seen = new Set()
    const merged = []
    for (const p of [...sessionSeeds, ...storePillars]) {
      const key = p.toLowerCase().trim()
      if (key && !seen.has(key)) { seen.add(key); merged.push(p) }
    }

    if (merged.length) {
      setAvailPillars(merged)
      setConfirmedPillars(merged)
      pillarsInitialized.current = true
    }
    if (storeMods.length) {
      setConfirmedModifiers(storeMods)
    }
    if (!merged.length) {
      // Fetch project-level profile (works in expand mode when no session Phase1)
      api.getProfile(projectId)
        .then((data) => {
          const p = Array.isArray(data?.profile?.pillars) ? data.profile.pillars.filter(Boolean)
            : Array.isArray(data?.pillars) ? data.pillars.filter(Boolean) : []
          // Also merge seeds from session with fetched profile pillars
          const fetchSeen = new Set()
          const fetchMerged = []
          for (const item of [...sessionSeeds, ...p]) {
            const key = item.toLowerCase().trim()
            if (key && !fetchSeen.has(key)) { fetchSeen.add(key); fetchMerged.push(item) }
          }
          if (fetchMerged.length) {
            setAvailPillars(fetchMerged)
            setConfirmedPillars(fetchMerged)
            pillarsInitialized.current = true
          }
          const m = Array.isArray(data?.profile?.modifiers) ? data.profile.modifiers.filter(Boolean)
            : Array.isArray(data?.modifiers) ? data.modifiers.filter(Boolean) : []
          if (m.length && !storeMods.length) {
            setConfirmedModifiers(m)
          }
        })
        .catch(() => {})
    }
  }, [profile, projectId, mode, session])

  const addManualPillar = () => {
    const trimmed = manualPillar.trim()
    if (!trimmed) return
    // Support comma-separated entry
    const newPillars = trimmed.split(",").map((s) => s.trim()).filter(Boolean)
    setAvailPillars((prev) => {
      const existingLower = new Set(prev.map(p => p.toLowerCase()))
      const filtered = newPillars.filter(p => !existingLower.has(p.toLowerCase()))
      const next = [...prev, ...filtered]
      // Persist to backend so pillars survive page refresh
      api.updateProfile(projectId, { pillars: next }).catch(() => {})
      return next
    })
    setConfirmedPillars((prev) => {
      const existingLower = new Set(prev.map(p => p.toLowerCase()))
      return [...prev, ...newPillars.filter(p => !existingLower.has(p.toLowerCase()))]
    })
    setManualPillar("")
  }

  const loadReadme = useCallback(async (force = false) => {
    // Skip in modes without Phase1/BI (avoid noisy 404s)
    if (mode === "expand" || mode === "review") return
    setReadmeLoading(true)
    try {
      const cur = await api.getBusinessReadme(projectId, sessionId)
      if (cur?.readme && !force) {
        setReadme(cur.readme)
      } else {
        const gen = await api.generateBusinessReadme(projectId, sessionId, force)
        if (gen?.readme) setReadme(gen.readme)
      }
    } catch {
      // README is optional
    }
    setReadmeLoading(false)
  }, [projectId, sessionId, mode])

  React.useEffect(() => {
    loadReadme(false)
  }, [loadReadme])

  const togglePillar = useCallback((pillar) => {
    setConfirmedPillars((prev) =>
      prev.includes(pillar) ? prev.filter((p) => p !== pillar) : [...prev, pillar]
    )
  }, [])

  const loadKeywords = useCallback(async () => {
    try {
      const data = await api.getUniverse(projectId, sessionId)
      const kws = data.items || []
      setKeywords(Array.isArray(kws) ? kws : [])
    } catch { /* ignore */ }
  }, [projectId, sessionId])

  const runStream = useCallback(async () => {
    if (!confirmedPillars.length) {
      setError("Select at least one confirmed pillar before generation.")
      return
    }
    // Cancel any existing stream before starting a fresh one
    if (cancelRef.current) { cancelRef.current(); cancelRef.current = null }
    setLoading(true)
    setError(null)
    setLayerCounts({})
    setActiveLayer(null)
    setResult(null)
    log("Generating keyword universe (streaming)...", "info")

    cancelRef.current = api.streamPhase2(projectId, sessionId, (ev) => {
      if (ev.type === "progress") {
        setActiveLayer(ev.source)
        // IMPORTANT: suggest + ai_expand emit multiple events (one per pillar)
        // so we ACCUMULATE instead of overwrite
        setLayerCounts((prev) => ({
          ...prev,
          [ev.source]: (prev[ev.source] || 0) + (ev.count || 0),
        }))
        log(`[${LAYER_LABELS[ev.source] || ev.source}] +${ev.count} keywords${ev.pillar ? ` (${ev.pillar})` : ""}${ev.cached ? " ✓ cached" : ev.skipped ? " — skipped (AI unavailable)" : ""}`, "progress")
      }
      if (ev.type === "complete") {
        setResult({ total: ev.total, rejected: ev.rejected })
        setUniverseCount(ev.total || 0)
        setActiveLayer(null)
        log(`Universe complete: ${ev.total} generated, ${ev.rejected || 0} rejected`, "success")
        toast(`Keyword universe: ${ev.total} keywords generated`, "success")
      }
      if (ev.done && !ev.error) {
        setLoading(false)
        onComplete()
        loadKeywords()
      }
      if (ev.error) {
        setError("Stream error: " + (ev.message || "unknown"))
        log(`Stream error: ${ev.message || "unknown"}`, "error")
        toast("Phase 2 streaming failed", "error")
        setLoading(false)
      }
    }, confirmedPillars, confirmedModifiers, true /* reset=true: fresh user-initiated run */)
  }, [projectId, sessionId, confirmedPillars, confirmedModifiers])

  const runSync = useCallback(async () => {
    if (!confirmedPillars.length) {
      setError("Select at least one confirmed pillar before generation.")
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    log("Generating keyword universe (batch)...", "info")
    try {
      const data = await api.runPhase2(projectId, sessionId, confirmedPillars, confirmedModifiers)
      const u = data.universe || {}
      setResult(u)
      setUniverseCount(u.total || 0)
      if (u.sources) setLayerCounts(u.sources)
      log(`Batch complete: ${u.total || 0} keywords, ${u.rejected || 0} rejected`, "success")
      toast(`Keyword universe: ${u.total || 0} keywords generated`, "success")
      onComplete()
      await loadKeywords()
      const next = goNextPhase(2)
      if (next == null) setActivePhase(3)
    } catch (e) {
      setError(e.message)
      log(`Batch failed: ${e.message}`, "error")
      toast(`Phase 2 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId, confirmedPillars, goNextPhase, setActivePhase])

  const loadExisting = useCallback(async () => {
    try {
      const data = await api.getUniverse(projectId, sessionId)
      if (data.count > 0) {
        setResult({ total: data.count, rejected: 0 })
        setUniverseCount(data.count || 0)
        const kws = Array.isArray(data.items) ? data.items : []
        if (kws.length) setKeywords(kws)
      }
    } catch { /* ignore */ }
  }, [projectId, sessionId])

  React.useEffect(() => { loadExisting() }, [])

  const completedLayers = LAYERS.filter((l) => layerCounts[l] > 0).length

  return (
    <Card
      title="Phase 2: Keyword Universe"
      actions={
        <div style={{ display: "flex", gap: 8 }}>
          <RunButton onClick={runStream} loading={loading}>Stream</RunButton>
          <RunButton onClick={runSync} loading={loading} variant="secondary">Batch</RunButton>
        </div>
      }
    >
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 10 }}>
        8-layer pipeline: seeds, rules, audience combos, BI attributes, trust/quality, Google Suggest, competitor crawl, and AI expansion.
      </p>

      {/* ── Data Sources Active Panel ─────────────────────────────────────── */}
      {!result && !loading && (
        <div style={{ marginBottom: 12, padding: "10px 12px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#166534", marginBottom: 8 }}>
            📊 Data Sources Active for This Generation
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, fontSize: 11 }}>
            {/* Phase 1 pillars */}
            <span style={{
              padding: "3px 10px", borderRadius: 10, fontWeight: 600,
              background: confirmedPillars.length ? "#dcfce7" : "#fee2e2",
              color: confirmedPillars.length ? "#15803d" : "#dc2626",
              border: `1px solid ${confirmedPillars.length ? "#86efac" : "#fca5a5"}`,
            }}>
              {confirmedPillars.length ? "✓" : "⚠"} Phase 1 Pillars: {confirmedPillars.length}
            </span>
            {/* Modifiers */}
            <span style={{
              padding: "3px 10px", borderRadius: 10, fontWeight: 600,
              background: confirmedModifiers.length ? "#dcfce7" : "#f3f4f6",
              color: confirmedModifiers.length ? "#15803d" : "#6b7280",
              border: `1px solid ${confirmedModifiers.length ? "#86efac" : "#e5e7eb"}`,
            }}>
              {confirmedModifiers.length ? "✓" : "○"} Modifiers: {confirmedModifiers.length}
            </span>
            {/* Audience */}
            <span style={{
              padding: "3px 10px", borderRadius: 10, fontWeight: 600,
              background: (profile?.audience || []).length ? "#dcfce7" : "#f3f4f6",
              color: (profile?.audience || []).length ? "#15803d" : "#6b7280",
              border: `1px solid ${(profile?.audience || []).length ? "#86efac" : "#e5e7eb"}`,
            }}>
              {(profile?.audience || []).length ? "✓" : "○"} Audiences: {(profile?.audience || []).length}
            </span>
            {/* BI Competitor keywords */}
            <span style={{
              padding: "3px 10px", borderRadius: 10, fontWeight: 600,
              background: "#dbeafe", color: "#1d4ed8", border: "1px solid #93c5fd",
            }}>
              ↻ Competitor crawl keywords → Layer 4b
            </span>
            {/* BI Strategy */}
            <span style={{
              padding: "3px 10px", borderRadius: 10, fontWeight: 600,
              background: "#dbeafe", color: "#1d4ed8", border: "1px solid #93c5fd",
            }}>
              ↻ BI Strategy priority keywords → Layer 4c
            </span>
            {/* AI Expand */}
            <span style={{
              padding: "3px 10px", borderRadius: 10, fontWeight: 600,
              background: "#ede9fe", color: "#6d28d9", border: "1px solid #c4b5fd",
            }}>
              ✨ AI: ~{confirmedPillars.length * 80} keywords across {confirmedPillars.length} pillars
            </span>
          </div>
          {confirmedPillars.length === 0 && (
            <p style={{ margin: "8px 0 0", fontSize: 11, color: "#dc2626" }}>
              ⚠ No pillars confirmed — run Phase 1 (Analyze Business) first, then confirm your pillars below.
            </p>
          )}
          {profile?.negative_scope?.length > 0 && (
            <p style={{ margin: "6px 0 0", fontSize: 11, color: "#6b7280" }}>
              ✂ Negative scope filter active: {(profile.negative_scope || []).length} exclusion patterns
            </p>
          )}
          {/* Location & language context row */}
          {(() => {
            const mi = profile?.manual_input || {}
            const targLocs = (profile?.target_locations || mi.target_locations || []).slice(0, 4)
            const bizLocs = (profile?.business_locations || mi.business_locations || []).slice(0, 3)
            const langs = (profile?.languages || mi.languages || []).slice(0, 3)
            const usp = profile?.usp || mi.usp || ""
            if (!targLocs.length && !bizLocs.length && !langs.length && !usp) return null
            return (
              <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid #e5e7eb" }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 5 }}>
                  🎯 Generating keywords for:
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                  {targLocs.map(l => (
                    <span key={l} style={{ fontSize: 10, padding: "2px 7px", borderRadius: 8,
                      background: "#f0fdf4", color: "#15803d" }}>📍 {l}</span>
                  ))}
                  {bizLocs.map(l => (
                    <span key={l} style={{ fontSize: 10, padding: "2px 7px", borderRadius: 8,
                      background: "#ecfdf5", color: "#059669" }}>🏢 {l}</span>
                  ))}
                  {langs.map(l => (
                    <span key={l} style={{ fontSize: 10, padding: "2px 7px", borderRadius: 8,
                      background: "#eff6ff", color: "#2563eb" }}>🌐 {l}</span>
                  ))}
                  {usp && (
                    <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 8,
                      background: "#faf5ff", color: "#7c3aed", maxWidth: 220,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      💡 {usp.slice(0, 50)}{usp.length > 50 ? "…" : ""}
                    </span>
                  )}
                </div>
              </div>
            )
          })()}
        </div>
      )}

      {error && <p style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>{error}</p>}

      {/* Business context + confirmed pillars */}
      <div style={{ marginBottom: 12, border: "1px solid #e5e7eb", borderRadius: 8, background: "#f9fafb", padding: 12 }}>
        {/* README — only for brand/BI modes */}
        {mode !== "expand" && mode !== "review" && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, gap: 8, flexWrap: "wrap" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#374151" }}>Business Context (Analyze + Intel README)</div>
              <button
                onClick={() => loadReadme(true)}
                disabled={readmeLoading}
                style={{
                  border: "1px solid #d1d5db", borderRadius: 6, background: "#fff",
                  fontSize: 11, padding: "4px 10px", cursor: readmeLoading ? "not-allowed" : "pointer",
                }}
              >
                {readmeLoading ? "Refreshing..." : "Refresh README"}
              </button>
            </div>
            {readme ? (
              <div style={{ whiteSpace: "pre-wrap", fontSize: 12, color: "#4b5563", lineHeight: 1.55, maxHeight: 180, overflowY: "auto", background: "#fff", border: "1px solid #e5e7eb", borderRadius: 6, padding: 10, marginBottom: 10 }}>
                {readme}
              </div>
            ) : (
              <p style={{ margin: "0 0 10px", fontSize: 12, color: "#9ca3af" }}>
                README not generated yet. Click "Refresh README" to generate context from Analyze + Intel.
              </p>
            )}
          </>
        )}

        {/* Pillar confirmation */}
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#374151", marginBottom: 6 }}>
            Confirm Pillars ({confirmedPillars.length})
            {!confirmedPillars.length && (
              <span style={{ marginLeft: 8, color: "#dc2626", fontWeight: 500, fontSize: 11 }}>⚠ At least one pillar required</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
            {availPillars.map((pillar) => {
              const checked = confirmedPillars.includes(pillar)
              return (
                <span key={pillar} style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
                  <button
                    onClick={() => togglePillar(pillar)}
                    style={{
                      borderRadius: "10px 0 0 10px",
                      border: checked ? "2px solid #2563eb" : "1px solid #d1d5db",
                      borderRight: "none",
                      background: checked ? "#eff6ff" : "#fff",
                      color: checked ? "#1d4ed8" : "#6b7280",
                      fontSize: 12, fontWeight: checked ? 700 : 500,
                      padding: "4px 8px 4px 10px", cursor: "pointer",
                    }}
                  >
                    {checked && "✓ "}{pillar}
                  </button>
                  <button
                    onClick={() => {
                      setAvailPillars(prev => prev.filter(p => p !== pillar))
                      setConfirmedPillars(prev => prev.filter(p => p !== pillar))
                    }}
                    title="Remove pillar"
                    style={{
                      borderRadius: "0 10px 10px 0",
                      border: checked ? "2px solid #2563eb" : "1px solid #d1d5db",
                      borderLeft: `1px solid ${checked ? "#93c5fd" : "#e5e7eb"}`,
                      background: checked ? "#eff6ff" : "#fff",
                      color: "#9ca3af", fontSize: 13, padding: "4px 6px",
                      cursor: "pointer", lineHeight: 1,
                    }}
                  >×</button>
                </span>
              )
            })}
            {!availPillars.length && (
              <span style={{ fontSize: 12, color: "#9ca3af" }}>No pillars loaded yet. Enter pillars below.</span>
            )}
          </div>
          {/* Manual pillar entry */}
          <div style={{ display: "flex", gap: 6 }}>
            <input
              value={manualPillar}
              onChange={(e) => setManualPillar(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addManualPillar()}
              placeholder="Add pillars (comma-separated) e.g. organic spices, whole spices"
              style={{ flex: 1, padding: "5px 10px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 12, outline: "none" }}
            />
            <button
              onClick={addManualPillar}
              style={{ padding: "5px 14px", borderRadius: 6, background: "#3b82f6", color: "#fff", border: "none", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
            >
              Add
            </button>
          </div>
          {mode === "expand" && (
            <p style={{ margin: "6px 0 0", fontSize: 11, color: "#6b7280" }}>
              Expand mode: enter your target pillars above, then run generation.
            </p>
          )}
        </div>

        {/* Modifier management */}
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#374151", marginBottom: 6 }}>
            Modifiers ({confirmedModifiers.length})
            <span style={{ marginLeft: 8, color: "#6b7280", fontWeight: 400, fontSize: 11 }}>
              Each modifier is combined with every pillar during generation
            </span>
          </div>
          <TagInput
            tags={confirmedModifiers}
            onChange={setConfirmedModifiers}
            placeholder="Add modifiers (comma-separated) e.g. organic, wholesale, buy, best"
            color="#7c3aed"
            bgColor="#ede9fe"
          />
          {confirmedPillars.length > 0 && confirmedModifiers.length > 0 && (
            <div style={{ marginTop: 6, fontSize: 11, color: "#6b7280" }}>
              Will generate <strong>{confirmedPillars.length} × {confirmedModifiers.length} = {confirmedPillars.length * confirmedModifiers.length}</strong> seed combinations
              {confirmedPillars.length <= 3 && confirmedModifiers.length <= 4 && (
                <span style={{ marginLeft: 4 }}>
                  (e.g. "{confirmedModifiers[0]} {confirmedPillars[0]}", "{confirmedPillars[0]} {confirmedModifiers[0]}")
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Live progress during streaming */}
      {loading && (
        <div style={{ marginBottom: 12 }}>
          <ProgressBar value={completedLayers} max={LAYERS.length} label="Overall Progress" color="#10b981" animated />
          {LAYERS.map((layer) => {
            const count = layerCounts[layer] || 0
            const isActive = activeLayer === layer
            return (
              <div key={layer} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 12, width: 130, color: isActive ? "#3b82f6" : "#6b7280", fontWeight: isActive ? 600 : 400 }}>
                  {LAYER_LABELS[layer]}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ height: 6, background: "#e5e7eb", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{
                      height: "100%",
                      width: count > 0 ? "100%" : isActive ? "60%" : "0%",
                      background: count > 0 ? "#10b981" : isActive ? "#3b82f6" : "#e5e7eb",
                      borderRadius: 3,
                      transition: "width 300ms ease",
                      animation: isActive && !count ? "kw2pulse 1.5s ease infinite" : "none",
                    }} />
                  </div>
                </div>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#374151", width: 60, textAlign: "right" }}>
                  {count > 0 ? count : isActive ? "..." : !activeLayer ? "Skipped" : ""}
                </span>
              </div>
            )
          })}
          <style>{`@keyframes kw2pulse { 0%,100%{opacity:.4} 50%{opacity:1} }`}</style>
        </div>
      )}

      {/* Results after completion */}
      {result && !loading && (
        <>
          <StatsRow items={[
            { label: "Total Generated", value: result.total || 0, color: "#10b981" },
            { label: "Rejected (dupes)", value: result.rejected || 0, color: "#ef4444" },
            ...LAYERS.map((k) => ({
              label: LAYER_LABELS[k] || k,
              value: layerCounts[k] || 0,
              color: layerCounts[k] > 0 ? "#3b82f6" : "#9ca3af",
            })),
          ]} />

          {/* Keyword universe preview table — read-only. Editing/approval happens in Phase 3 (Validate). */}
          {keywords.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Raw Universe Preview ({keywords.length})</h4>
                  <span style={{ fontSize: 11, color: "#9ca3af" }}>Read-only — approve / reject keywords in Phase 3 (Validate)</span>
                </div>
                <button
                  onClick={loadKeywords}
                  style={{ padding: "4px 10px", borderRadius: 5, border: "1px solid #d1d5db", background: "#fff", fontSize: 11, cursor: "pointer" }}
                >
                  Refresh
                </button>
              </div>
              <DataTable
                columns={[
                  { key: "keyword", label: "Keyword", sortable: true, searchable: true },
                  { key: "pillar", label: "Pillar", sortable: true, filterable: true },
                  { key: "intent", label: "Intent", sortable: true, filterable: true, type: "badge" },
                  { key: "score", label: "Score", sortable: true, type: "number" },
                  { key: "status", label: "Status", sortable: true, filterable: true, type: "badge" },
                  { key: "source", label: "Source", sortable: true, filterable: true },
                ]}
                data={keywords.map((k, i) => ({
                  ...k,
                  id: k.id || `kw_${i}`,
                  pillar: Array.isArray(k.pillars) ? k.pillars[0] || k.pillar || "—" : k.pillar || "—",
                  score: k.score ?? k.final_score ?? k.raw_score ?? 0,
                }))}
                rowKey="id"
                emptyText="No keywords generated yet — run Stream or Batch above"
              />
            </div>
          )}

          <PhaseResult
            phaseNum={2}
            stats={[
              { label: "Total Keywords", value: result.total || 0, color: "#10b981" },
              { label: "Rejected", value: result.rejected || 0, color: "#ef4444" },
            ]}
            onNext={() => {
              const next = goNextPhase(2)
              if (next == null) setActivePhase(3)
            }}
          />
        </>
      )}

      <NotificationList notifications={notifications} title="Generation Events" />
    </Card>
  )
}
