/**
 * kw3 Tab 1: Business Analysis
 *
 * Exact feature parity with kw2/Phase1.jsx:
 *  - SSE-based streaming analysis with live log
 *  - Per-field AI suggest buttons (Business Locations, Target Locations, Audiences,
 *    Languages, Customer Reviews) + Modifiers / Negative Scope
 *  - Bulk "Suggest All Fields" button
 *  - AI-suggested Pillars panel (shown after analysis, user reviews before adding)
 *  - Competitor URL crawl → top keywords with drag-drop +P / +M buttons
 *  - AI Classify competitor keywords → suggested Pillars / Modifiers
 *  - Location depth drill-down
 *  - Website product crawl
 *  - Ollama pre-run warning + Provider retry dialog
 *  - Profile result summary with stat cards
 */
import React, { useState, useEffect, useCallback, useRef } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import apiCall from "../lib/apiCall"
import {
  runPhase1Stream, updateProfile, suggestFields, competitorCrawl,
  addToProfile, analyzeCompetitorKeywords, setSessionProvider,
  getProfile as kw2GetProfile,
} from "../kw2/api"
import { TagInput, StatsRow } from "../kw2/shared"
import { Card as Kw3Card, Btn, Spinner, T } from "./ui"

// ── Constants ─────────────────────────────────────────────────────────────────
const DEPTH_LABELS = ["🌍 Countries", "🏛️ States", "🏘️ Districts", "📍 Towns"]
const DEPTH_NEXT   = ["→ States",     "→ Districts", "→ Towns",     "→ Areas"]

const PROVIDER_LABELS = {
  auto:   "Auto (Groq → Gemini)",
  groq:   "Groq (fast, ~3–8s)",
  gemini: "Gemini",
  claude: "Claude (Anthropic)",
  ollama: "Ollama (local, slow ⚠️)",
}

const fs = { width: "100%", padding: "8px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13, boxSizing: "border-box" }
const ls = { fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 4, display: "block" }

// ── Small helpers ─────────────────────────────────────────────────────────────
function toArr(v) {
  if (Array.isArray(v)) return v
  if (typeof v === "string" && v) return v.split(",").map(s => s.trim()).filter(Boolean)
  return []
}

function SectionTitle({ icon, children }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 700, color: "#1e1b4b", margin: "14px 0 10px", paddingBottom: 5, borderBottom: "1px solid #e5e7eb" }}>
      {icon} {children}
    </div>
  )
}

function FieldRow({ label, hint, btn, children }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <label style={{ ...ls, marginBottom: 0, flex: 1 }}>{label}</label>
        {btn}
      </div>
      {hint && <div style={{ fontSize: 10, color: "#9ca3af", marginBottom: 4 }}>{hint}</div>}
      {children}
    </div>
  )
}

function AISuggestBtn({ label = "✨ AI Suggest", loading, onClick, disabled }) {
  return (
    <button onClick={onClick} disabled={loading || disabled} style={{
      padding: "3px 9px", borderRadius: 5, border: "1px solid #8b5cf6",
      background: loading ? "#ede9fe" : "#f5f3ff", color: "#7c3aed",
      fontSize: 11, fontWeight: 600, cursor: loading || disabled ? "not-allowed" : "pointer",
      whiteSpace: "nowrap", flexShrink: 0,
    }}>
      {loading ? "✨ …" : label}
    </button>
  )
}

// ── Ollama Warning ─────────────────────────────────────────────────────────────
function OllamaWarning({ onSwitch, onContinue }) {
  return (
    <div style={{ background: "#fffbeb", border: "1px solid #f59e0b", borderRadius: 8, padding: "14px 16px", marginBottom: 14 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#92400e", marginBottom: 6 }}>
        ⚠️ Ollama (Local AI) Selected — This May Take 5–15 Minutes
      </div>
      <div style={{ fontSize: 12, color: "#78350f", marginBottom: 12, lineHeight: 1.5 }}>
        Ollama runs on your local CPU and is very slow for large analysis prompts.
        Groq completes the same analysis in <strong>3–8 seconds</strong> for free.
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={onSwitch} style={{
          padding: "7px 14px", borderRadius: 6, border: "none",
          background: "#10b981", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer",
        }}>⚡ Switch to Groq &amp; Run</button>
        <button onClick={onContinue} style={{
          padding: "7px 14px", borderRadius: 6, border: "1px solid #d97706",
          background: "transparent", color: "#92400e", fontSize: 12, cursor: "pointer",
        }}>Continue with Ollama (slow)</button>
      </div>
    </div>
  )
}

// ── Provider Retry Dialog ──────────────────────────────────────────────────────
function ProviderRetryDialog({ reason, onRetry, onDismiss }) {
  const [selected, setSelected] = useState("groq")
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#fff", borderRadius: 12, padding: "24px 28px", maxWidth: 420, boxShadow: "0 20px 60px rgba(0,0,0,0.3)", width: "90%" }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: "#1e1b4b", marginBottom: 8 }}>🚫 AI Provider Issue</div>
        <div style={{ fontSize: 13, color: "#374151", marginBottom: 16, lineHeight: 1.5 }}>
          {reason || "The selected AI provider failed or is rate-limited. Your website crawl data is saved — retry will skip re-crawling."}
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>
            Select a different provider to retry:
          </label>
          {["groq", "gemini", "claude", "auto"].map(p => (
            <label key={p} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, cursor: "pointer" }}>
              <input type="radio" name="kw3_retry_provider" value={p} checked={selected === p} onChange={() => setSelected(p)} />
              <span style={{ fontSize: 13, color: "#374151" }}>{PROVIDER_LABELS[p] || p}</span>
            </label>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => onRetry(selected)} style={{
            flex: 1, padding: "9px 0", borderRadius: 7, border: "none",
            background: "#6366f1", color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer",
          }}>↩ Retry with {PROVIDER_LABELS[selected] || selected}</button>
          <button onClick={onDismiss} style={{
            padding: "9px 16px", borderRadius: 7, border: "1px solid #d1d5db",
            background: "#fff", color: "#6b7280", fontSize: 13, cursor: "pointer",
          }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

// ── Live log panel ─────────────────────────────────────────────────────────────
function LiveLog({ entries }) {
  const ref = useRef(null)
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight }, [entries])
  if (!entries.length) return null
  return (
    <div ref={ref} style={{
      marginTop: 10, background: "#0f172a", borderRadius: 8, padding: "10px 14px",
      maxHeight: 180, overflowY: "auto", fontFamily: "ui-monospace, SFMono-Regular, monospace",
      fontSize: 11, lineHeight: 1.6,
    }}>
      {entries.slice(-80).map((e, i) => (
        <div key={i} style={{ color: e.type === "error" ? "#fca5a5" : e.type === "success" ? "#86efac" : e.type === "warn" ? "#fcd34d" : "#cbd5e1" }}>
          <span style={{ color: "#475569" }}>{e.time}</span> {e.text}
        </div>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  Main Component
// ═══════════════════════════════════════════════════════════════════════════════
export default function TabBusiness({ projectId, sessionId, session, onDone }) {
  const qc = useQueryClient()

  // ── Log state (lightweight replacement for usePhaseRunner) ────────────────
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [logEntries, setLogEntries] = useState([])

  const log = useCallback((text, type = "info") => {
    const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    setLogEntries(prev => [...prev.slice(-99), { time, text, type }])
  }, [])
  const toast = useCallback((msg, type = "success") => {
    log(`[${type.toUpperCase()}] ${msg}`, type)
  }, [log])

  // ── Dialogs ───────────────────────────────────────────────────────────────
  const [retryDialog, setRetryDialog]   = useState(null)
  const [ollamaWarning, setOllamaWarning] = useState(false)
  const pendingBodyRef  = useRef(null)
  const sseCancel       = useRef(null)
  const profileInitRef  = useRef(false)

  // ── Core form state ───────────────────────────────────────────────────────
  const lsDomainKey = `kw3_domain_${sessionId}`
  const lsCompKey   = `kw3_comp_urls_${sessionId}`
  const [domain,   setDomain]   = useState(() => localStorage.getItem(lsDomainKey) || "")
  const [compUrls, setCompUrls] = useState(() => {
    try { return JSON.parse(localStorage.getItem(lsCompKey) || "[]") } catch { return [] }
  })
  const [bizType, setBizType] = useState("")
  const [usp,     setUsp]     = useState("")

  const [pillars,   setPillars]   = useState([])
  const [products,  setProducts]  = useState([])
  const [modifiers, setModifiers] = useState([])
  const [audience,  setAudience]  = useState([])
  const [negScope,  setNegScope]  = useState([])

  const [businessLocations,    setBusinessLocations]    = useState([])
  const [businessLocationDepth, setBusinessLocationDepth] = useState(0)
  const [targetLocations,      setTargetLocations]      = useState([])
  const [targetLocationDepth,  setTargetLocationDepth]  = useState(0)
  const [languages,        setLanguages]        = useState([])
  const [culturalContext,  setCulturalContext]  = useState([])
  const [customerReviews,  setCustomerReviews]  = useState("")

  // ── Per-field suggest loading ─────────────────────────────────────────────
  const [fs_map, setFsMap] = useState({})
  const setFS = (k, v) => setFsMap(p => ({ ...p, [k]: v }))

  // ── Crawl state ───────────────────────────────────────────────────────────
  const [crawling,       setCrawling]       = useState(false)
  const [crawlResult,    setCrawlResult]    = useState(null)
  const [websiteCrawling, setWebsiteCrawling] = useState(false)
  const [compAnalysis,   setCompAnalysis]   = useState(null)
  const [compAnalyzing,  setCompAnalyzing]  = useState(false)
  const [aiPillarSuggestions, setAiPillarSuggestions] = useState([])

  // ── Drag-drop ─────────────────────────────────────────────────────────────
  const [dragOverPillar,   setDragOverPillar]   = useState(false)
  const [dragOverModifier, setDragOverModifier] = useState(false)

  // Persist domain & compUrls
  useEffect(() => { const t = setTimeout(() => localStorage.setItem(lsDomainKey, domain), 500); return () => clearTimeout(t) }, [domain])
  useEffect(() => { const t = setTimeout(() => localStorage.setItem(lsCompKey, JSON.stringify(compUrls)), 500); return () => clearTimeout(t) }, [compUrls])

  // ── Load saved profile ────────────────────────────────────────────────────
  const profileQ = useQuery({
    queryKey: ["kw3", projectId, "profile"],
    queryFn: () => kw2GetProfile(projectId),
    enabled: !!projectId,
    staleTime: 30_000,
  })
  const savedProfile = profileQ.data?.profile

  useEffect(() => {
    if (!savedProfile) return
    if (savedProfile.domain && !domain) setDomain(savedProfile.domain)
    if (!profileInitRef.current) {
      setPillars(savedProfile.pillars || [])
      setModifiers(savedProfile.modifiers || [])
      profileInitRef.current = true
    }
    setProducts(toArr(savedProfile.product_catalog))
    setAudience(toArr(savedProfile.audience))
    setNegScope(toArr(savedProfile.negative_scope))
    setBizType(savedProfile.business_type || "")
    if (savedProfile.usp) setUsp(savedProfile.usp)
    if (Array.isArray(savedProfile.business_locations)) setBusinessLocations(savedProfile.business_locations)
    if (Array.isArray(savedProfile.target_locations)) setTargetLocations(savedProfile.target_locations)
    else if (savedProfile.geo_scope) setTargetLocations(savedProfile.geo_scope.split(",").map(s => s.trim()).filter(Boolean))
    if (Array.isArray(savedProfile.languages)) setLanguages(savedProfile.languages)
    const mi = savedProfile.manual_input || {}
    if (!savedProfile.languages?.length && Array.isArray(mi.languages)) setLanguages(mi.languages)
    if (Array.isArray(savedProfile.cultural_context)) setCulturalContext(savedProfile.cultural_context)
    if (savedProfile.customer_reviews) setCustomerReviews(savedProfile.customer_reviews)
  }, [savedProfile])

  // ── Per-field AI suggest ──────────────────────────────────────────────────
  const suggestField = async (type, extraContext, onResult) => {
    setFS(type, true)
    try {
      const res = await apiCall(`/api/strategy/${projectId}/ai-suggest`, "POST", {
        type,
        context: { domain: domain.trim(), business_type: bizType, pillars, product_catalog: products, usp, business_locations: businessLocations, target_locations: targetLocations, locations: targetLocations, languages, ...extraContext },
      })
      if (res?.suggestions) onResult(res.suggestions)
    } catch (e) { toast(`AI suggest failed: ${e.message}`, "error") }
    setFS(type, false)
  }

  // ── Bulk suggest ──────────────────────────────────────────────────────────
  const suggestBulk = async () => {
    setFS("_bulk", true)
    log("✨ Requesting AI suggestions for modifiers, audience, negative scope...", "info")
    try {
      const { suggestions } = await suggestFields(projectId, {
        domain: domain.trim(), business_type: bizType, pillars,
        product_catalog: products.slice(0, 10), geo_scope: targetLocations.join(", "),
      })
      if (suggestions.audience?.length)        setAudience(prev => [...new Set([...prev, ...suggestions.audience])])
      if (suggestions.modifiers?.length)        setModifiers(prev => [...new Set([...prev, ...suggestions.modifiers])])
      if (suggestions.negative_scope?.length)   setNegScope(prev => [...new Set([...prev, ...suggestions.negative_scope])])
      log(`✅ Audience +${(suggestions.audience||[]).length}, Modifiers +${(suggestions.modifiers||[]).length}, Negative +${(suggestions.negative_scope||[]).length}`, "success")
      toast("AI suggestions merged into fields", "success")
    } catch (e) { log(`❌ Suggestion failed: ${e.message}`, "error"); toast("AI suggest failed — try again", "error") }
    setFS("_bulk", false)
  }

  // ── Crawl website products ────────────────────────────────────────────────
  const crawlFromWebsite = async () => {
    if (!domain) { toast("Enter a domain URL first", "error"); return }
    setWebsiteCrawling(true)
    try {
      const res = await apiCall(`/api/ki/${projectId}/crawl-context`, "POST", { customer_url: domain, existing_pillars: pillars })
      const found = (res?.products || []).map(p => typeof p === "string" ? p : p.name || String(p)).filter(Boolean)
      if (found.length) { setProducts(prev => [...new Set([...prev, ...found])]); toast(`Found ${found.length} products from website`, "success") }
      else toast("No products found on website", "warn")
    } catch (e) { toast(`Website crawl failed: ${e.message}`, "error") }
    setWebsiteCrawling(false)
  }

  // ── Competitor crawl ──────────────────────────────────────────────────────
  const runCompetitorCrawl = useCallback(async () => {
    const urls = compUrls.filter(u => u.startsWith("http"))
    if (!urls.length) { toast("Add at least one competitor URL", "error"); return }
    setCrawling(true); setCrawlResult(null)
    log("🔍 Starting competitor keyword crawl...", "info")
    try {
      const data = await competitorCrawl(projectId, sessionId, {
        competitor_urls: urls, our_pillars: pillars, business_type: bizType, geo_scope: targetLocations.join(", "),
      })
      setCrawlResult(data)
      log(`✅ Competitor crawl — ${data.pages_crawled || 0} pages, top ${data.top_100?.length || 0} keywords`, "success")
      toast(`Competitor crawl: ${data.top_100?.length || 0} actionable keywords found`, "success")
    } catch (e) { log(`❌ Competitor crawl failed: ${e.message}`, "error"); toast("Competitor crawl failed", "error") }
    setCrawling(false)
  }, [projectId, sessionId, compUrls, pillars, bizType, targetLocations, log, toast])

  // ── Run analysis (SSE) ────────────────────────────────────────────────────
  const _doRun = useCallback(async (body, providerOverride = null) => {
    if (sseCancel.current) { sseCancel.current(); sseCancel.current = null }
    setLoading(true); setError(""); setRetryDialog(null); setOllamaWarning(false)
    if (providerOverride) {
      try { await setSessionProvider(projectId, sessionId, providerOverride); log(`✅ Provider: ${PROVIDER_LABELS[providerOverride] || providerOverride}`, "info") }
      catch (e) { log(`⚠ Could not update provider: ${e.message}`, "warn") }
    }
    log(`▶ Phase 1 started — analyzing ${body.domain || "business"}`, "info")
    let done = false
    const cancel = runPhase1Stream(projectId, sessionId, body, (ev) => {
      if (done) return
      switch (ev.type) {
        case "progress":
          log(`  ${ev.pct || ""}% — ${ev.message || ev.step}`, "progress"); break
        case "provider_selected":
          log(`🤖 Using: ${PROVIDER_LABELS[ev.provider] || ev.provider}`, "info"); break
        case "rate_limited":
          log(`⚠️ ${ev.message || `${ev.provider} rate-limited`}`, "warn")
          toast(`⚠️ ${ev.provider} rate-limited — switching to ${ev.switching_to}`, "warn"); break
        case "provider_switch":
          log(`🔄 Provider: ${ev.from} → ${ev.to} (${ev.reason})`, "warn"); break
        case "providers_exhausted":
          log(`❌ ${ev.message}`, "error")
          toast("All AI providers exhausted", "error")
          setRetryDialog({ reason: ev.message })
          done = true; setLoading(false); break
        case "done":
          done = true
          if (ev.profile) {
            const result = ev.profile
            const pArr   = toArr(result.pillars)
            profileInitRef.current = true
            // Update supplementary AI fields
            setProducts(toArr(result.product_catalog))
            setAudience(toArr(result.audience))
            if (result.negative_scope) setNegScope(toArr(result.negative_scope))
            // Merge modifiers (not pillars — user controls those)
            setModifiers(prev => { const ex = new Set(prev.map(m => m.toLowerCase())); return [...prev, ...toArr(result.modifiers).filter(m => !ex.has(m.toLowerCase()))] })
            // Show AI pillars as suggestions
            setPillars(prev => {
              const ex = new Set(prev.map(p => p.toLowerCase()))
              const newAi = pArr.filter(p => !ex.has(p.toLowerCase()))
              if (newAi.length) setAiPillarSuggestions(newAi)
              return prev
            })
            log(`✅ 100% — Analysis complete | Confidence: ${((result.confidence_score || 0) * 100).toFixed(0)}% | Type: ${result.business_type || "detected"}`, "success")
            toast(`Analysis complete — ${pArr.filter(p => !new Set(pillars.map(x => x.toLowerCase())).has(p.toLowerCase())).length} AI pillar suggestions ready`, "success")
            qc.invalidateQueries({ queryKey: ["kw3", projectId, "profile"] })
            qc.invalidateQueries({ queryKey: ["kw3", projectId, "session", sessionId] })
          }
          setLoading(false); break
        case "session_updated":
          done = true
          ;(async () => {
            const crawlableUrls = (body.competitor_urls || []).filter(u => u.startsWith("http"))
            if (crawlableUrls.length > 0) {
              log("🔍 Auto-running competitor crawl…", "info")
              setCrawling(true); setCrawlResult(null)
              try {
                const crawlData = await Promise.race([
                  competitorCrawl(projectId, sessionId, { competitor_urls: crawlableUrls, our_pillars: pillars, business_type: bizType, geo_scope: targetLocations.join(", ") }),
                  new Promise((_, rej) => setTimeout(() => rej(new Error("Crawl finishing in background")), 45000)),
                ])
                setCrawlResult(crawlData)
                log(`✅ Competitor crawl — ${crawlData.pages_crawled || 0} pages, top ${crawlData.top_100?.length || 0} keywords`, "success")
              } catch (ce) { log(`⏱ ${ce.message}`, "warn") }
              setCrawling(false)
            }
            setLoading(false)
            qc.invalidateQueries({ queryKey: ["kw3", projectId, "profile"] })
            qc.invalidateQueries({ queryKey: ["kw3", projectId, "session", sessionId] })
          })()
          return
        case "error":
          done = true
          log(`❌ Phase 1 failed: ${ev.message || "Unknown error"}`, "error")
          setError(ev.message || "Analysis failed")
          toast("Phase 1 failed — check log for details", "error")
          setRetryDialog({ reason: ev.message })
          setLoading(false); break
        default: break
      }
      if (done && ev.type !== "session_updated") setLoading(false)
    })
    sseCancel.current = cancel
  }, [projectId, sessionId, pillars, bizType, targetLocations, log, toast, qc])

  const run = useCallback(() => {
    profileInitRef.current = true
    const body = {
      domain: domain.trim(), pillars, product_catalog: products,
      modifiers, negative_scope: negScope, audience, usp,
      business_type: bizType.trim(),
      business_locations: businessLocations,
      target_locations: targetLocations,
      geo_scope: targetLocations.join(", "),
      languages, cultural_context: culturalContext,
      customer_reviews: customerReviews,
      competitor_urls: compUrls.filter(u => u.startsWith("http")),
    }
    pendingBodyRef.current = body
    const storedProvider = localStorage.getItem(`kw2_provider_${sessionId}`) || "auto"
    if (storedProvider === "ollama") { setOllamaWarning(true); return }
    _doRun(body)
  }, [domain, pillars, products, modifiers, negScope, audience, usp, bizType,
      businessLocations, targetLocations, languages, culturalContext, customerReviews,
      compUrls, sessionId, _doRun])

  useEffect(() => () => { if (sseCancel.current) sseCancel.current() }, [])

  const isDone = !!session?.phase1_done || !!savedProfile?.business_type

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Dialogs */}
      {retryDialog && (
        <ProviderRetryDialog
          reason={retryDialog.reason}
          onRetry={(p) => { const b = pendingBodyRef.current; if (b) _doRun(b, p); else setRetryDialog(null) }}
          onDismiss={() => setRetryDialog(null)}
        />
      )}
      {ollamaWarning && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 9998, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "#fff", borderRadius: 12, padding: "24px 28px", maxWidth: 440, width: "90%", boxShadow: "0 20px 60px rgba(0,0,0,0.3)" }}>
            <OllamaWarning
              onSwitch={async () => { setOllamaWarning(false); localStorage.setItem(`kw2_provider_${sessionId}`, "groq"); const b = pendingBodyRef.current; if (b) _doRun(b, "groq") }}
              onContinue={() => { setOllamaWarning(false); const b = pendingBodyRef.current; if (b) _doRun(b) }}
            />
          </div>
        </div>
      )}

      {/* Complete banner */}
      {isDone && (
        <div style={{ marginBottom: 14, padding: "12px 16px", background: T.successBg, border: `1px solid ${T.success}`, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 20 }}>✅</span>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.success }}>Business analysis complete</div>
              {savedProfile?.business_type && (
                <div style={{ fontSize: 12, color: T.textSoft, marginTop: 1 }}>
                  Detected: <b>{savedProfile.business_type}</b>
                  {typeof savedProfile.confidence_score === "number" && <> · confidence {Math.round(savedProfile.confidence_score * 100)}%</>}
                </div>
              )}
            </div>
          </div>
          <button onClick={onDone} style={{
            padding: "8px 18px", borderRadius: 7, border: "none", background: T.primary, color: "#fff",
            fontSize: 13, fontWeight: 600, cursor: "pointer",
          }}>Continue to Generate →</button>
        </div>
      )}

      {/* Main card */}
      <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: "18px 20px" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: "#1e1b4b" }}>Phase 1: Business Analysis</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button onClick={suggestBulk} disabled={fs_map._bulk || loading} style={{
              padding: "6px 12px", borderRadius: 6, border: "1px solid #8b5cf6",
              background: fs_map._bulk ? "#ede9fe" : "#f5f3ff", color: "#7c3aed",
              fontSize: 12, fontWeight: 600, cursor: fs_map._bulk ? "not-allowed" : "pointer",
            }}>
              {fs_map._bulk ? "✨ Suggesting..." : "✨ Suggest All Fields"}
            </button>
            <button onClick={run} disabled={loading} style={{
              padding: "8px 20px", borderRadius: 7, border: "none",
              background: loading ? "#818cf8" : "#4f46e5", color: "#fff",
              fontSize: 13, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              {loading ? <><Spinner color="#fff" /> Analyzing…</> : "Analyze Business"}
            </button>
          </div>
        </div>

        {/* Two-column layout */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 12 }}>

          {/* LEFT: Business Profile */}
          <div>
            <SectionTitle icon="🏢">Business Profile</SectionTitle>

            <div style={{ marginBottom: 10 }}>
              <label style={ls}>Domain *</label>
              <input style={fs} placeholder="https://example.com" value={domain} onChange={e => setDomain(e.target.value)} />
            </div>

            <div style={{ marginBottom: 10 }}>
              <label style={ls}>Business Type</label>
              <select style={fs} value={bizType} onChange={e => setBizType(e.target.value)}>
                <option value="">Auto-detect</option>
                <option value="Ecommerce">Ecommerce</option>
                <option value="B2B">B2B</option>
                <option value="B2C">B2C</option>
                <option value="D2C">D2C</option>
                <option value="SaaS">SaaS</option>
                <option value="Local">Local</option>
              </select>
            </div>

            <div style={{ marginBottom: 10 }}>
              <label style={ls}>USP (Unique Selling Proposition)</label>
              <textarea value={usp} onChange={e => setUsp(e.target.value)} placeholder="What makes your business unique?" rows={2} style={{ ...fs, resize: "vertical", fontFamily: "inherit" }} />
            </div>

            <FieldRow label="Products & Services" btn={
              <AISuggestBtn label={websiteCrawling ? "🔍 Crawling…" : "🔍 Crawl from Website"} loading={websiteCrawling} disabled={!domain} onClick={crawlFromWebsite} />
            }>
              <TagInput tags={products} onChange={setProducts} placeholder="turmeric powder, cardamom pods" color="#059669" bgColor="#d1fae5" />
            </FieldRow>

            <FieldRow label={<>Pillar Keywords <span style={{ fontSize: 10, color: "#6b7280", fontWeight: 400 }}>press Enter to add · or drag from competitor section</span></>}>
              <div
                onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; setDragOverPillar(true) }}
                onDragLeave={() => setDragOverPillar(false)}
                onDrop={async e => {
                  e.preventDefault(); setDragOverPillar(false)
                  const term = e.dataTransfer.getData("application/kw2-term")
                  if (!term) return
                  profileInitRef.current = true
                  const next = pillars.includes(term) ? pillars : [...pillars, term]
                  setPillars(next)
                  try { await Promise.all([addToProfile(projectId, sessionId, [term], "pillars"), updateProfile(projectId, { pillars: next })]) } catch {}
                  toast(`"${term}" dragged to Pillars ✓`, "success")
                }}
                style={{ borderRadius: 6, outline: dragOverPillar ? "2px dashed #3b82f6" : "2px dashed transparent", background: dragOverPillar ? "#eff6ff" : "transparent", transition: "all 0.15s" }}
              >
                <TagInput tags={pillars} onChange={async next => {
                  profileInitRef.current = true
                  setPillars(next)
                  if (projectId) { try { await updateProfile(projectId, { pillars: next }) } catch {} }
                }} placeholder="Type a pillar and press Enter" color="#2563eb" bgColor="#dbeafe" />
              </div>

              {/* AI pillar suggestions panel */}
              {aiPillarSuggestions.length > 0 && (
                <div style={{ marginTop: 6, padding: "8px 10px", background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 6 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#1d4ed8", marginBottom: 4 }}>
                    🤖 AI Suggested Pillars — click to add
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {aiPillarSuggestions.map((p, i) => (
                      <button key={i} onClick={async () => {
                        const next = pillars.includes(p) ? pillars : [...pillars, p]
                        setPillars(next)
                        setAiPillarSuggestions(prev => prev.filter((_, idx) => idx !== i))
                        try { await updateProfile(projectId, { pillars: next }) } catch {}
                        toast(`"${p}" added to pillars`, "success")
                      }} style={{ padding: "2px 10px", borderRadius: 10, border: "1px solid #93c5fd", background: "#eff6ff", color: "#1d4ed8", fontSize: 11, cursor: "pointer" }}>
                        + {p}
                      </button>
                    ))}
                    <button onClick={() => setAiPillarSuggestions([])} style={{ padding: "2px 8px", borderRadius: 10, border: "1px solid #d1d5db", background: "#fff", color: "#9ca3af", fontSize: 11, cursor: "pointer" }}>✕ Dismiss</button>
                  </div>
                </div>
              )}
            </FieldRow>

            <FieldRow label={<>Competitor URLs <span style={{ fontSize: 10, color: "#6b7280", fontWeight: 400 }}>full URL</span></>}>
              <TagInput tags={compUrls} onChange={setCompUrls} placeholder="https://competitor.com" color="#d97706" bgColor="#fef3c7" />
            </FieldRow>
          </div>

          {/* RIGHT: Target Audience */}
          <div>
            <SectionTitle icon="🎯">Target Audience</SectionTitle>

            <FieldRow
              label={<>📍 Business Location(s){businessLocations.length > 0 && <span style={{ fontSize: 10, color: "#8b5cf6", marginLeft: 6 }}>Level: {DEPTH_LABELS[Math.min(businessLocationDepth, 3)]}</span>}</>}
              hint="Where your business operates from (authority signals)"
              btn={<AISuggestBtn
                label={businessLocations.length === 0 ? "✨ AI Suggest" : `✨ Drill ${DEPTH_NEXT[Math.min(businessLocationDepth, 3)]}`}
                loading={fs_map.business_regions}
                onClick={() => suggestField("business_regions", { depth: businessLocationDepth, current: businessLocations }, items => {
                  const names = toArr(items).map(x => typeof x === "string" ? x : x.name || String(x))
                  setBusinessLocations(prev => [...new Set([...prev, ...names])])
                  setBusinessLocationDepth(d => d + 1)
                })}
              />}
            >
              <TagInput tags={businessLocations} onChange={v => { setBusinessLocations(v); if (!v.length) setBusinessLocationDepth(0) }} placeholder="Kerala, Tamil Nadu…" color="#8b5cf6" bgColor="#ede9fe" />
            </FieldRow>

            <FieldRow
              label={<>🎯 Target Location(s){targetLocations.length > 0 && <span style={{ fontSize: 10, color: "#8b5cf6", marginLeft: 6 }}>Level: {DEPTH_LABELS[Math.min(targetLocationDepth, 3)]}</span>}</>}
              hint="Where your customers are (geo-targeted keywords)"
              btn={<AISuggestBtn
                label={targetLocations.length === 0 ? "✨ AI Suggest" : `✨ Drill ${DEPTH_NEXT[Math.min(targetLocationDepth, 3)]}`}
                loading={fs_map.regions}
                onClick={() => suggestField("regions", { depth: targetLocationDepth, current: targetLocations }, items => {
                  const names = toArr(items).map(x => typeof x === "string" ? x : x.name || String(x))
                  setTargetLocations(prev => [...new Set([...prev, ...names])])
                  setTargetLocationDepth(d => d + 1)
                })}
              />}
            >
              <TagInput tags={targetLocations} onChange={v => { setTargetLocations(v); if (!v.length) setTargetLocationDepth(0) }} placeholder="India, USA, UK…" color="#0891b2" bgColor="#cffafe" />
            </FieldRow>

            <FieldRow label="Languages" btn={
              <AISuggestBtn label="✨ AI Suggest" loading={fs_map.languages}
                onClick={() => suggestField("languages", { locations: targetLocations }, items => {
                  const names = toArr(items).map(x => typeof x === "string" ? x : x.name || String(x))
                  setLanguages(prev => [...new Set([...prev, ...names])])
                })}
              />
            }>
              <TagInput tags={languages} onChange={setLanguages} placeholder="English, Hindi, Tamil…" color="#2563eb" bgColor="#dbeafe" />
            </FieldRow>

            <FieldRow label="Cultural Context">
              <TagInput tags={culturalContext} onChange={setCulturalContext} placeholder="General, Hindu, Muslim…" color="#6b7280" bgColor="#f3f4f6" />
            </FieldRow>

            <FieldRow label="Target Audiences" btn={
              <AISuggestBtn label={audience.length === 0 ? "✨ AI Suggest" : "✨ Expand Audiences"} loading={fs_map.personas}
                onClick={() => suggestField("personas", { personas: audience }, items => {
                  const names = toArr(items).map(x => typeof x === "string" ? x : x.audience || x.name || String(x))
                  setAudience(prev => [...new Set([...prev, ...names])])
                })}
              />
            }>
              <TagInput tags={audience} onChange={setAudience} placeholder="restaurant owners, home cooks" color="#0891b2" bgColor="#cffafe" />
            </FieldRow>

            <FieldRow label="Customer Reviews" btn={
              <AISuggestBtn label="✨ Generate Samples" loading={fs_map.reviews}
                onClick={() => suggestField("reviews", {}, items => {
                  const strs = toArr(items).map(x => typeof x === "string" ? x : x.review || String(x))
                  setCustomerReviews(prev => prev ? prev + "\n" + strs.join("\n") : strs.join("\n"))
                })}
              />
            }>
              <textarea value={customerReviews} onChange={e => setCustomerReviews(e.target.value)} placeholder="Paste real customer reviews or generate samples…" rows={3} style={{ ...fs, resize: "vertical", fontFamily: "inherit" }} />
            </FieldRow>
          </div>
        </div>

        {/* Modifiers & Negative Scope */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
          <FieldRow label="Modifiers" hint="Drag competitor keywords here to use as modifiers"
            btn={<AISuggestBtn label="✨ AI Suggest" loading={fs_map._mod} onClick={async () => {
              setFS("_mod", true)
              try {
                const { suggestions } = await suggestFields(projectId, { domain: domain.trim(), business_type: bizType, pillars, product_catalog: products.slice(0, 10), geo_scope: targetLocations.join(", ") })
                if (suggestions.modifiers?.length) setModifiers(prev => [...new Set([...prev, ...suggestions.modifiers])])
                toast(`+${(suggestions.modifiers||[]).length} modifiers added`, "success")
              } catch (e) { toast("Suggest failed", "error") }
              setFS("_mod", false)
            }} />}
          >
            <div
              onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; setDragOverModifier(true) }}
              onDragLeave={() => setDragOverModifier(false)}
              onDrop={async e => {
                e.preventDefault(); setDragOverModifier(false)
                const term = e.dataTransfer.getData("application/kw2-term")
                if (!term) return
                const next = modifiers.includes(term) ? modifiers : [...modifiers, term]
                setModifiers(next)
                try { await addToProfile(projectId, sessionId, [term], "modifiers") } catch {}
                toast(`"${term}" dragged to Modifiers ✓`, "success")
              }}
              style={{ borderRadius: 6, outline: dragOverModifier ? "2px dashed #8b5cf6" : "2px dashed transparent", background: dragOverModifier ? "#f5f3ff" : "transparent", transition: "all 0.15s" }}
            >
              <TagInput tags={modifiers} onChange={setModifiers} placeholder="organic, wholesale, bulk" color="#7c3aed" bgColor="#ede9fe" />
            </div>
          </FieldRow>

          <FieldRow label="Negative Scope"
            btn={<AISuggestBtn label="✨ AI Suggest" loading={fs_map._neg} onClick={async () => {
              setFS("_neg", true)
              try {
                const { suggestions } = await suggestFields(projectId, { domain: domain.trim(), business_type: bizType, pillars, product_catalog: products.slice(0, 10), geo_scope: targetLocations.join(", ") })
                if (suggestions.negative_scope?.length) setNegScope(prev => [...new Set([...prev, ...suggestions.negative_scope])])
                toast(`+${(suggestions.negative_scope||[]).length} negative scope items added`, "success")
              } catch (e) { toast("Suggest failed", "error") }
              setFS("_neg", false)
            }} />}
          >
            <TagInput tags={negScope} onChange={setNegScope} placeholder="recipe, benefits, how to" color="#dc2626" bgColor="#fee2e2" />
          </FieldRow>
        </div>

        {/* Competitor Keyword Crawl */}
        {compUrls.length > 0 && (
          <div style={{ marginBottom: 12, padding: 12, background: "#fefce8", border: "1px solid #fbbf2433", borderRadius: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
              <div>
                <span style={{ fontSize: 13, fontWeight: 600, color: "#92400e" }}>Competitor Keyword Intelligence</span>
                <p style={{ margin: "4px 0 0", fontSize: 11, color: "#78716c" }}>Crawl competitor pages, extract keywords, clean &amp; rank top 100</p>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                {crawlResult?.top_100?.length > 0 && (
                  <button disabled={compAnalyzing} onClick={async () => {
                    setCompAnalyzing(true); setCompAnalysis(null)
                    try {
                      const terms = crawlResult.top_100.slice(0, 60).map(k => typeof k === "string" ? k : k.keyword)
                      const res = await analyzeCompetitorKeywords(projectId, sessionId, terms)
                      setCompAnalysis(res)
                      toast(`AI analysis: ${res.pillars?.length || 0} pillars, ${res.modifiers?.length || 0} modifiers`, "success")
                    } catch (e) { toast(`Analysis failed: ${e.message}`, "error") }
                    setCompAnalyzing(false)
                  }} style={{ padding: "6px 12px", borderRadius: 6, border: "none", background: compAnalyzing ? "#a78bfa" : "#8b5cf6", color: "#fff", fontSize: 12, fontWeight: 600, cursor: compAnalyzing ? "not-allowed" : "pointer" }}>
                    {compAnalyzing ? "Analyzing..." : "🤖 AI Classify"}
                  </button>
                )}
                <button onClick={runCompetitorCrawl} disabled={crawling || loading} style={{ padding: "6px 14px", borderRadius: 6, border: "none", background: crawling ? "#fbbf24" : "#f59e0b", color: "#fff", fontSize: 12, fontWeight: 600, cursor: crawling ? "not-allowed" : "pointer" }}>
                  {crawling ? "Crawling..." : "Crawl Competitors"}
                </button>
              </div>
            </div>
            {crawlResult && (
              <div>
                <StatsRow items={[
                  { label: "Pages Crawled",  value: crawlResult.pages_crawled || 0,      color: "#d97706" },
                  { label: "Raw Keywords",   value: crawlResult.total_keywords || 0,     color: "#6b7280" },
                  { label: "After Clean",    value: crawlResult.cleaned_count || 0,      color: "#3b82f6" },
                  { label: "Top Keywords",   value: crawlResult.top_100?.length || 0,    color: "#10b981" },
                ]} />
                {crawlResult.top_100?.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 4 }}>
                      Top Competitor Keywords
                      <span style={{ fontWeight: 400, color: "#6b7280", marginLeft: 8, fontSize: 11 }}>
                        Click <span style={{ color: "#3b82f6" }}>+P</span> to add as Pillar, <span style={{ color: "#8b5cf6" }}>+M</span> to add as Modifier · Drag to confirm
                      </span>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, maxHeight: 200, overflowY: "auto" }}>
                      {crawlResult.top_100.slice(0, 80).map((kw, i) => {
                        const term = typeof kw === "string" ? kw : kw.keyword || kw.term
                        if (!term) return null
                        return (
                          <span key={i} draggable onDragStart={e => { e.dataTransfer.setData("application/kw2-term", term); e.dataTransfer.effectAllowed = "copy" }}
                            title="Drag to Pillar Keywords or Modifiers field above"
                            style={{ padding: "2px 4px 2px 8px", borderRadius: 10, fontSize: 11, background: "#fef3c7", border: "1px solid #fbbf24", color: "#92400e", display: "inline-flex", alignItems: "center", gap: 3, cursor: "grab" }}>
                            {term}
                            {typeof kw !== "string" && kw.score ? <b style={{ marginLeft: 2 }}>({kw.score})</b> : null}
                            <button title="Add as Pillar" onClick={async () => {
                              try { await addToProfile(projectId, sessionId, [term], "pillars"); setPillars(prev => prev.includes(term) ? prev : [...prev, term]); toast(`"${term}" added to pillars`, "success") }
                              catch (e) { toast(`Failed: ${e.message}`, "error") }
                            }} style={{ padding: "0 3px", border: "none", borderRadius: 4, fontSize: 10, background: "#dbeafe", color: "#2563eb", cursor: "pointer", fontWeight: 700 }}>+P</button>
                            <button title="Add as Modifier" onClick={async () => {
                              try { await addToProfile(projectId, sessionId, [term], "modifiers"); setModifiers(prev => prev.includes(term) ? prev : [...prev, term]); toast(`"${term}" added to modifiers`, "success") }
                              catch (e) { toast(`Failed: ${e.message}`, "error") }
                            }} style={{ padding: "0 3px", border: "none", borderRadius: 4, fontSize: 10, background: "#ede9fe", color: "#7c3aed", cursor: "pointer", fontWeight: 700 }}>+M</button>
                          </span>
                        )
                      })}
                      {crawlResult.top_100.length > 80 && <span style={{ fontSize: 11, color: "#9ca3af", alignSelf: "center" }}>+{crawlResult.top_100.length - 80} more</span>}
                    </div>
                  </div>
                )}
                {crawlResult.content_ideas?.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 4 }}>Content Ideas from Competitors</div>
                    <div style={{ fontSize: 12, color: "#4b5563", lineHeight: 1.6 }}>
                      {crawlResult.content_ideas.slice(0, 10).map((h, i) => <div key={i}>• {h}</div>)}
                    </div>
                  </div>
                )}
                {compAnalysis && (
                  <div style={{ marginTop: 10, padding: 10, background: "#f5f3ff", borderRadius: 6, border: "1px solid #ddd6fe" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#5b21b6", marginBottom: 8 }}>🤖 AI Classification — click to add</div>
                    {compAnalysis.pillars?.length > 0 && (
                      <div style={{ marginBottom: 6 }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: "#3b82f6", marginRight: 6 }}>Suggested Pillars:</span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                          {compAnalysis.pillars.map((r, i) => (
                            <button key={i} title={r.reason} onClick={async () => {
                              await addToProfile(projectId, sessionId, [r.keyword], "pillars")
                              setPillars(prev => prev.includes(r.keyword) ? prev : [...prev, r.keyword])
                              setCompAnalysis(prev => ({ ...prev, pillars: prev.pillars.filter((_, idx) => idx !== i) }))
                              toast(`"${r.keyword}" added to pillars`, "success")
                            }} style={{ padding: "2px 10px", borderRadius: 10, border: "1px solid #93c5fd", background: "#eff6ff", color: "#1d4ed8", fontSize: 11, cursor: "pointer" }}>+ {r.keyword}</button>
                          ))}
                        </div>
                      </div>
                    )}
                    {compAnalysis.modifiers?.length > 0 && (
                      <div>
                        <span style={{ fontSize: 11, fontWeight: 600, color: "#7c3aed", marginRight: 6 }}>Suggested Modifiers:</span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                          {compAnalysis.modifiers.map((r, i) => (
                            <button key={i} title={r.reason} onClick={async () => {
                              await addToProfile(projectId, sessionId, [r.keyword], "modifiers")
                              setModifiers(prev => prev.includes(r.keyword) ? prev : [...prev, r.keyword])
                              setCompAnalysis(prev => ({ ...prev, modifiers: prev.modifiers.filter((_, idx) => idx !== i) }))
                              toast(`"${r.keyword}" added to modifiers`, "success")
                            }} style={{ padding: "2px 10px", borderRadius: 10, border: "1px solid #c4b5fd", background: "#f5f3ff", color: "#6d28d9", fontSize: 11, cursor: "pointer" }}>+ {r.keyword}</button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {error && <p style={{ color: "#dc2626", marginTop: 8, fontSize: 13 }}>{error}</p>}

        {/* Live log */}
        <LiveLog entries={logEntries} />

        {/* Profile result summary */}
        {savedProfile && (
          <div style={{ marginTop: 16 }}>
            <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>Business Profile Summary</h4>
            <StatsRow items={[
              { label: "Pillars",    value: pillars.length,    color: "#3b82f6" },
              { label: "Products",   value: products.length,   color: "#10b981" },
              { label: "Modifiers",  value: modifiers.length,  color: "#8b5cf6" },
              { label: "Confidence", value: `${((savedProfile.confidence_score || 0) * 100).toFixed(0)}%`, color: savedProfile.confidence_score >= 0.7 ? "#10b981" : "#f59e0b" },
            ]} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {pillars.slice(0, 12).map((p, i) => (
                <span key={i} style={{ padding: "3px 10px", borderRadius: 10, background: "#dbeafe", color: "#1d4ed8", fontSize: 12, border: "1px solid #93c5fd" }}>{p}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
