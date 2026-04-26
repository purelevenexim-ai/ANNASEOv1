/**
 * Tab 2: Generate (v2)
 *
 * Changes vs v1:
 *  - 9-layer progress visualization (seeds, rules, audience, attribute, problem,
 *    suggest, competitor, bi_competitor, ai_expand) during Phase 2 stream
 *  - Per-layer keyword counts displayed after completion
 *  - Pillar confirm/deconfirm toggle chips (instead of plain ChipList) + manual add
 *  - Business Context README section (collapsible) loaded on mount
 *  - Google autosuggest adds to toggleable pillar list
 */
import React, { useState, useEffect, useRef } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  globalSuggest, streamPhase2, getUniverse, getProfile,
  getBusinessReadme, generateBusinessReadme,
} from "./api"
import { Card, Btn, Input, Label, ChipList, Spinner, T, Stat, Badge, ProgressBar, Empty } from "./ui"

// ── Layer constants (Phase 2 pipeline) ───────────────────────────────────────
const LAYERS = [
  "seeds", "rules", "audience", "attribute", "problem",
  "suggest", "competitor", "bi_competitor", "ai_expand",
]
const LAYER_LABELS = {
  seeds:        "Seed Keywords",
  rules:        "Rule Expansions",
  audience:     "Audience Terms",
  attribute:    "Attribute Combos",
  problem:      "Problem Phrases",
  suggest:      "Google Suggest",
  competitor:   "Competitor Analysis",
  bi_competitor:"BI Competitors",
  ai_expand:    "AI Expansions",
}

export default function TabGenerate({ projectId, sessionId, session, onDone }) {
  const qc = useQueryClient()

  // ── Profile ───────────────────────────────────────────────────────────────
  const profileQ = useQuery({
    queryKey: ["kw3", projectId, "profile"],
    queryFn:  () => getProfile(projectId),
    enabled:  !!projectId,
    staleTime: 30_000,
  })
  const profile      = profileQ.data?.profile
  const profilePillars = profile?.pillars || profile?.manual_input?.pillars || []
  const profileMods    = profile?.manual_input?.modifiers || []

  // ── Pillar/modifier state ─────────────────────────────────────────────────
  const [availPillars,       setAvailPillars]       = useState([])
  const [confirmedPillars,   setConfirmedPillars]   = useState([])
  const [confirmedModifiers, setConfirmedModifiers] = useState([])
  const [manualPillar,       setManualPillar]       = useState("")

  // Init from profile once
  useEffect(() => {
    if (profilePillars.length && !availPillars.length) {
      setAvailPillars(profilePillars)
      setConfirmedPillars(profilePillars)
    }
    if (profileMods.length && !confirmedModifiers.length) {
      setConfirmedModifiers(profileMods)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profilePillars.join("|"), profileMods.join("|")])

  const togglePillar = (p) =>
    setConfirmedPillars(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p])

  const addManualPillar = () => {
    if (!manualPillar.trim()) return
    const newPillars = manualPillar.split(",").map(s => s.trim()).filter(Boolean)
    setAvailPillars(prev => [...prev, ...newPillars.filter(p => !prev.includes(p))])
    setConfirmedPillars(prev => [...prev, ...newPillars.filter(p => !prev.includes(p))])
    setManualPillar("")
  }

  // ── Universe (existing keywords) ─────────────────────────────────────────
  const universeQ = useQuery({
    queryKey: ["kw3", projectId, "universe", sessionId],
    queryFn:  () => getUniverse(projectId, sessionId),
    enabled:  !!sessionId,
    staleTime: 5_000,
  })
  const universe = universeQ.data || {}
  const totalKw  = universe.count ?? universe.total ?? (universe.items?.length ?? 0)

  // ── Business README ───────────────────────────────────────────────────────
  const [readme,          setReadme]          = useState("")
  const [readmeLoading,   setReadmeLoading]   = useState(false)
  const [readmeExpanded,  setReadmeExpanded]  = useState(false)

  const loadReadme = async (force = false) => {
    setReadmeLoading(true)
    try {
      const data = force
        ? await generateBusinessReadme(projectId, sessionId, true)
        : await getBusinessReadme(projectId, sessionId)
      setReadme(data?.readme || data?.content || data?.text || "")
    } catch {}
    setReadmeLoading(false)
  }

  useEffect(() => {
    if (sessionId) loadReadme()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  // ── Phase 2 stream state ──────────────────────────────────────────────────
  const [streaming,    setStreaming]    = useState(false)
  const [layerCounts,  setLayerCounts]  = useState({})
  const [activeLayer,  setActiveLayer]  = useState(null)
  const [streamErr,    setStreamErr]    = useState("")
  const [streamDone,   setStreamDone]   = useState(false)
  const [streamTotal,  setStreamTotal]  = useState(null)
  const stopRef = useRef(null)

  const completedLayers = LAYERS.filter(l => (layerCounts[l] || 0) > 0).length

  const runStream = () => {
    if (streaming) return
    if (!confirmedPillars.length) { setStreamErr("Add at least one pillar."); return }
    setStreaming(true)
    setLayerCounts({}); setActiveLayer(null); setStreamErr(""); setStreamDone(false); setStreamTotal(null)

    stopRef.current = streamPhase2(projectId, sessionId, confirmedPillars, confirmedModifiers, (ev) => {
      // Track layer progress
      if (ev.source && LAYERS.includes(ev.source)) {
        setActiveLayer(ev.source)
        if (ev.count != null) {
          setLayerCounts(prev => ({ ...prev, [ev.source]: ev.count }))
        }
      }

      if (ev.done === true || ev.type === "done" || ev.type === "complete" || ev.step === "done") {
        setStreaming(false)
        setActiveLayer(null)
        setStreamDone(true)
        if (ev.total != null) setStreamTotal(ev.total)
        qc.invalidateQueries({ queryKey: ["kw3", projectId, "universe", sessionId] })
        qc.invalidateQueries({ queryKey: ["kw3", projectId, "session", sessionId] })
      }
      if (ev.type === "error") {
        setStreaming(false); setStreamErr(ev.message || "Stream error")
      }
    })
  }

  const stopStream = () => { stopRef.current?.(); setStreaming(false) }
  useEffect(() => () => stopRef.current?.(), [])

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: "grid", gap: 16 }}>

      {/* ── Business README (collapsible) ──────────────────────────────── */}
      {sessionId && (
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>Business Context</div>
            <div style={{ display: "flex", gap: 6 }}>
              <Btn
                variant="ghost"
                onClick={() => setReadmeExpanded(!readmeExpanded)}
                style={{ fontSize: 12 }}
              >{readmeExpanded ? "Collapse ▲" : "Expand ▼"}</Btn>
              <Btn
                variant="ghost"
                onClick={() => loadReadme(true)}
                disabled={readmeLoading}
                style={{ fontSize: 12 }}
              >{readmeLoading ? "Refreshing…" : "Refresh README"}</Btn>
            </div>
          </div>
          {readmeExpanded && (
            <div style={{ marginTop: 10 }}>
              {readme ? (
                <div style={{
                  whiteSpace: "pre-wrap", fontSize: 12, color: "#4b5563", lineHeight: 1.55,
                  maxHeight: 180, overflowY: "auto",
                  background: "#f9fafb", border: `1px solid ${T.border}`, borderRadius: 6, padding: 10,
                }}>
                  {readme}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: T.textMute }}>
                  No business README yet. Click "Refresh README" to generate from your Phase 1 analysis.
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {/* ── Pillar & modifier confirmation ─────────────────────────────── */}
      <Card>
        <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 14 }}>
          Confirm pillars &amp; modifiers for this run
        </div>

        {/* Pillar toggle chips */}
        <div style={{ marginBottom: 16 }}>
          <Label hint="Main topics — keyword universe will be built around these">
            Pillars ({confirmedPillars.length} confirmed)
            {!confirmedPillars.length && (
              <span style={{ marginLeft: 8, color: T.error, fontWeight: 500, fontSize: 11 }}>
                ⚠ At least one pillar required
              </span>
            )}
          </Label>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
            {availPillars.map(pillar => {
              const checked = confirmedPillars.includes(pillar)
              return (
                <span key={pillar} style={{ display: "inline-flex", alignItems: "center" }}>
                  <button
                    onClick={() => togglePillar(pillar)}
                    style={{
                      borderRadius: "10px 0 0 10px",
                      border: checked ? "2px solid #2563eb" : `1px solid ${T.border}`,
                      borderRight: "none",
                      background: checked ? T.primaryBg : "#fff",
                      color: checked ? T.primary : T.textSoft,
                      fontSize: 12, fontWeight: checked ? 700 : 500,
                      padding: "4px 10px", cursor: "pointer",
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
                      border: checked ? "2px solid #2563eb" : `1px solid ${T.border}`,
                      borderLeft: `1px solid ${checked ? "#93c5fd" : T.border}`,
                      background: checked ? T.primaryBg : "#fff",
                      color: T.textMute, fontSize: 13, padding: "4px 7px",
                      cursor: "pointer", lineHeight: 1,
                    }}
                  >×</button>
                </span>
              )
            })}
            {!availPillars.length && (
              <span style={{ fontSize: 12, color: T.textMute }}>No pillars yet. Enter below.</span>
            )}
          </div>
          {/* Manual add input */}
          <div style={{ display: "flex", gap: 6 }}>
            <Input
              value={manualPillar}
              onChange={e => setManualPillar(e.target.value)}
              onKeyDown={e => e.key === "Enter" && addManualPillar()}
              placeholder="Add pillars (comma-separated) e.g. organic spices, whole spices"
              style={{ flex: 1 }}
            />
            <Btn onClick={addManualPillar} style={{ whiteSpace: "nowrap" }}>Add</Btn>
          </div>
        </div>

        {/* Modifiers */}
        <div>
          <Label hint="Each modifier is combined with every pillar during generation">
            Modifiers (optional)
          </Label>
          <ChipList
            items={confirmedModifiers}
            onChange={setConfirmedModifiers}
            placeholder="organic, bulk, buy, best..."
          />
          {confirmedPillars.length > 0 && confirmedModifiers.length > 0 && (
            <div style={{ marginTop: 6, fontSize: 11, color: T.textSoft }}>
              {confirmedPillars.length} × {confirmedModifiers.length} ={" "}
              <strong>{confirmedPillars.length * confirmedModifiers.length}</strong> seed combinations
            </div>
          )}
        </div>
      </Card>

      {/* ── Google autosuggest helper ───────────────────────────────────── */}
      <AutosuggestBox
        onPickPillar={s => {
          setAvailPillars(prev => prev.includes(s) ? prev : [...prev, s])
          setConfirmedPillars(prev => prev.includes(s) ? prev : [...prev, s])
        }}
        onPickModifier={s => setConfirmedModifiers(m => m.includes(s) ? m : [...m, s])}
      />

      {/* ── Run + progress ──────────────────────────────────────────────── */}
      <Card>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>Generate keyword universe</div>
            <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
              Runs Google + DataForSEO + AI expansions across all 9 layers for each pillar
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {streaming
              ? <Btn variant="danger" onClick={stopStream}>Stop</Btn>
              : (
                <Btn onClick={runStream} disabled={!confirmedPillars.length}>
                  {totalKw > 0 ? "Re-generate" : "Generate keywords"}
                </Btn>
              )
            }
            {totalKw > 0 && !streaming && (
              <Btn variant="secondary" onClick={onDone}>Continue →</Btn>
            )}
          </div>
        </div>

        {streamErr && (
          <div style={{ padding: 10, background: T.errorBg, color: T.error, border: `1px solid ${T.error}40`, borderRadius: 7, fontSize: 12, marginBottom: 12 }}>
            {streamErr}
          </div>
        )}

        {/* Summary stats */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <Stat label="Total keywords"  value={totalKw} />
          <Stat label="Confirmed pillars" value={confirmedPillars.length} color={T.success} />
          <Stat label="Status"
            value={session?.phase2_done ? "Ready ✓" : "Pending"}
            color={session?.phase2_done ? T.success : T.warn}
          />
        </div>

        {/* Per-layer progress rows (during stream OR after completion) */}
        {(streaming || (streamDone && completedLayers > 0)) && (
          <div style={{ marginTop: 16 }}>
            {/* Overall bar */}
            <div style={{ marginBottom: 10 }}>
              <ProgressBar pct={(completedLayers / LAYERS.length) * 100} color={T.success} />
            </div>
            {/* Per-layer rows */}
            {LAYERS.map(layer => {
              const count    = layerCounts[layer] || 0
              const isActive = activeLayer === layer
              const isDone   = count > 0
              return (
                <div key={layer} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span style={{
                    fontSize: 12, width: 165, flexShrink: 0,
                    color: isDone ? T.success : isActive ? T.primary : T.textMute,
                    fontWeight: isDone || isActive ? 600 : 400,
                  }}>
                    {isDone ? "✓ " : isActive ? "▶ " : ""}{LAYER_LABELS[layer]}
                  </span>
                  <div style={{ flex: 1, height: 6, background: T.border, borderRadius: 3, overflow: "hidden" }}>
                    <div style={{
                      height: "100%",
                      width: isDone ? "100%" : isActive ? "60%" : "0%",
                      background: isDone ? T.success : isActive ? T.primary : T.border,
                      borderRadius: 3,
                      transition: "width 300ms ease",
                      animation: isActive && !isDone ? "kw3genpulse 1.5s ease infinite" : "none",
                    }} />
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 600, color: T.text, width: 55, textAlign: "right" }}>
                    {isDone ? count.toLocaleString() : isActive ? "…" : ""}
                  </span>
                </div>
              )
            })}
            <style>{`@keyframes kw3genpulse { 0%,100%{opacity:.4} 50%{opacity:1} }`}</style>
          </div>
        )}

        {/* Post-completion per-layer stats */}
        {!streaming && streamDone && completedLayers > 0 && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
            <Stat label="Total generated" value={(streamTotal ?? totalKw).toLocaleString()} color={T.success} />
            {LAYERS.filter(k => (layerCounts[k] || 0) > 0).map(k => (
              <Stat key={k} label={LAYER_LABELS[k]} value={layerCounts[k].toLocaleString()} color={T.primary} />
            ))}
          </div>
        )}
      </Card>

      {/* ── Sample keywords ─────────────────────────────────────────────── */}
      {totalKw > 0 && (
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>Sample keywords</div>
            <Badge>{totalKw.toLocaleString()} total</Badge>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {(universe.items || []).slice(0, 60).map((kw, i) => (
              <span key={i} style={{
                background: T.primaryBg, color: T.primary,
                padding: "3px 10px", borderRadius: 12, fontSize: 11,
              }}>{kw.keyword || kw}</span>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

// ── Autosuggest helper box (unchanged from v1) ────────────────────────────────
function AutosuggestBox({ onPickPillar, onPickModifier }) {
  const [seed,    setSeed]    = useState("")
  const [results, setResults] = useState([])
  const mut = useMutation({
    mutationFn: () => globalSuggest(seed.trim(), "us", 50),
    onSuccess:  (res) => setResults(res?.keywords || res?.suggestions || res?.items || []),
  })
  const onKey = (e) => { if (e.key === "Enter" && seed.trim()) { e.preventDefault(); mut.mutate() } }

  return (
    <Card>
      <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 4 }}>
        Google autosuggest helper
      </div>
      <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 12 }}>
        Type a seed keyword to discover what people actually search for. Click any suggestion to add it as a pillar or modifier.
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <Input
          value={seed}
          onChange={e => setSeed(e.target.value)}
          onKeyDown={onKey}
          placeholder="e.g. black pepper"
        />
        <Btn onClick={() => mut.mutate()} disabled={!seed.trim() || mut.isPending}>
          {mut.isPending ? <Spinner color="#fff" /> : "Suggest"}
        </Btn>
      </div>

      {mut.isError && (
        <div style={{ marginTop: 10, fontSize: 12, color: T.error }}>
          {String(mut.error?.message || mut.error)}
        </div>
      )}

      {results.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 6 }}>
            {results.length} suggestions — click <b>P</b> to add as pillar, <b>M</b> to add as modifier
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, maxHeight: 240, overflowY: "auto" }}>
            {results.map((r, i) => {
              const txt = typeof r === "string" ? r : (r.keyword || r.text || r.suggestion)
              return (
                <span key={i} style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  background: "#f3f4f6", padding: "4px 4px 4px 10px",
                  borderRadius: 14, fontSize: 12, color: T.text,
                }}>
                  {txt}
                  <button
                    onClick={() => onPickPillar(txt)}
                    title="Add as pillar"
                    style={{
                      background: T.primary, color: "#fff", border: "none",
                      borderRadius: "50%", width: 18, height: 18,
                      fontSize: 10, cursor: "pointer", fontWeight: 700,
                    }}
                  >P</button>
                  <button
                    onClick={() => onPickModifier(txt)}
                    title="Add as modifier"
                    style={{
                      background: T.success, color: "#fff", border: "none",
                      borderRadius: "50%", width: 18, height: 18,
                      fontSize: 10, cursor: "pointer", fontWeight: 700,
                    }}
                  >M</button>
                </span>
              )
            })}
          </div>
        </div>
      )}
    </Card>
  )
}
