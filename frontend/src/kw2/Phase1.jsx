/**
 * Phase 1 — Business Analysis.
 * Full-featured input UI: per-field AI suggest, location drill-down, website crawl, competitor crawl.
 */
import React, { useState, useEffect, useCallback, useRef } from "react"
import apiCall from "../lib/apiCall"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, StatsRow, usePhaseRunner, PhaseResult, NotificationList, TagInput } from "./shared"

const DEPTH_LABELS = ["🌍 Countries", "🏛️ States", "🏘️ Districts", "📍 Towns"]
const DEPTH_NEXT = ["→ States", "→ Districts", "→ Towns", "→ Areas"]

const PROVIDER_LABELS = {
  auto:    "Auto (Groq → Gemini)",
  groq:    "Groq (fast, ~3–8s)",
  gemini:  "Gemini",
  claude:  "Claude (Anthropic)",
  ollama:  "Ollama (local, slow ⚠️)",
}

// ─── Ollama Warning Banner ────────────────────────────────────────────────────
function OllamaWarning({ onSwitch, onContinue }) {
  return (
    <div style={{
      background: "#fffbeb", border: "1px solid #f59e0b", borderRadius: 8,
      padding: "14px 16px", marginBottom: 14,
    }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#92400e", marginBottom: 6 }}>
        ⚠️ Ollama (Local AI) Selected — This May Take 5–15 Minutes
      </div>
      <div style={{ fontSize: 12, color: "#78350f", marginBottom: 12, lineHeight: 1.5 }}>
        Ollama runs on your local CPU and is very slow for large analysis prompts.
        Groq completes the same analysis in <strong>3–8 seconds</strong> for free.
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={onSwitch}
          style={{
            padding: "7px 14px", borderRadius: 6, border: "none",
            background: "#10b981", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer",
          }}
        >
          ⚡ Switch to Groq &amp; Run
        </button>
        <button
          onClick={onContinue}
          style={{
            padding: "7px 14px", borderRadius: 6, border: "1px solid #d97706",
            background: "transparent", color: "#92400e", fontSize: 12, cursor: "pointer",
          }}
        >
          Continue with Ollama (slow)
        </button>
      </div>
    </div>
  )
}

// ─── Provider Retry Dialog ────────────────────────────────────────────────────
function ProviderRetryDialog({ reason, onRetry, onDismiss }) {
  const [selected, setSelected] = useState("groq")
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 9999,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "#fff", borderRadius: 12, padding: "24px 28px", maxWidth: 420,
        boxShadow: "0 20px 60px rgba(0,0,0,0.3)", width: "90%",
      }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: "#1e1b4b", marginBottom: 8 }}>
          🚫 AI Provider Issue
        </div>
        <div style={{ fontSize: 13, color: "#374151", marginBottom: 16, lineHeight: 1.5 }}>
          {reason || "The selected AI provider failed or is rate-limited. Your website crawl data is saved — retry will skip re-crawling."}
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>
            Select a different provider to retry:
          </label>
          {["groq", "gemini", "claude", "auto"].map(p => (
            <label key={p} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, cursor: "pointer" }}>
              <input
                type="radio" name="retry_provider" value={p}
                checked={selected === p} onChange={() => setSelected(p)}
              />
              <span style={{ fontSize: 13, color: "#374151" }}>{PROVIDER_LABELS[p] || p}</span>
            </label>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => onRetry(selected)}
            style={{
              flex: 1, padding: "9px 0", borderRadius: 7, border: "none",
              background: "#6366f1", color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer",
            }}
          >
            ↩ Retry with {PROVIDER_LABELS[selected] || selected}
          </button>
          <button
            onClick={onDismiss}
            style={{
              padding: "9px 16px", borderRadius: 7, border: "1px solid #d1d5db",
              background: "#fff", color: "#6b7280", fontSize: 13, cursor: "pointer",
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Per-field AI Suggest Button ──────────────────────────────────────────────
function FieldSuggestBtn({ label = "✨ AI Suggest", loading, onClick, disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={loading || disabled}
      style={{
        padding: "3px 9px", borderRadius: 5, border: "1px solid #8b5cf6",
        background: loading ? "#ede9fe" : "#f5f3ff", color: "#7c3aed",
        fontSize: 11, fontWeight: 600, cursor: loading || disabled ? "not-allowed" : "pointer",
        whiteSpace: "nowrap", flexShrink: 0,
      }}
    >
      {loading ? "✨ …" : label}
    </button>
  )
}

export default function Phase1({ projectId, sessionId, onComplete, onNext }) {
  const { profile, setProfile, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P1")

  // Retry dialog state
  const [retryDialog, setRetryDialog] = useState(null)   // null | { reason }
  // Ollama pre-run warning state
  const [ollamaWarning, setOllamaWarning] = useState(false)
  // Pending run body (stored so we can re-run after provider switch without re-building)
  const pendingBodyRef = useRef(null)
  // SSE cancel ref
  const sseCancel = useRef(null)
  // Track whether form was already populated from the initial profile load.
  // After the first population, analysis results only UPDATE products/audience/negScope
  // (AI-generated fields) — NOT pillars or modifiers, which the user controls.
  const profileInitRef = useRef(false)

  // Core tag fields
  const [pillars, setPillars] = useState([])
  const [products, setProducts] = useState([])
  const [modifiers, setModifiers] = useState([])
  const [audience, setAudience] = useState([])
  const [negScope, setNegScope] = useState([])

  // Persisted: load from localStorage keyed by sessionId
  const lsDomainKey = `kw2_domain_${sessionId}`
  const lsCompKey = `kw2_comp_urls_${sessionId}`
  const [domain, setDomain] = useState(() => localStorage.getItem(lsDomainKey) || "")
  const [compUrls, setCompUrls] = useState(() => {
    try { return JSON.parse(localStorage.getItem(lsCompKey) || "[]") } catch { return [] }
  })

  // Business profile fields
  const [bizType, setBizType] = useState("")
  const [usp, setUsp] = useState("")

  // Location fields (chip-based, replaces plain geoScope text)
  const [businessLocations, setBusinessLocations] = useState([])
  const [businessLocationDepth, setBusinessLocationDepth] = useState(0)
  const [targetLocations, setTargetLocations] = useState([])
  const [targetLocationDepth, setTargetLocationDepth] = useState(0)

  // Extended audience fields
  const [languages, setLanguages] = useState([])
  const [culturalContext, setCulturalContext] = useState([])
  const [customerReviews, setCustomerReviews] = useState("")

  // Per-field suggest loading state
  const [fieldSuggesting, setFieldSuggesting] = useState({})

  // Crawl state
  const [crawling, setCrawling] = useState(false)
  const [crawlResult, setCrawlResult] = useState(null)
  const [websiteCrawling, setWebsiteCrawling] = useState(false)
  const [compAnalysis, setCompAnalysis] = useState(null)  // AI analysis of competitor kws
  const [compAnalyzing, setCompAnalyzing] = useState(false)

  // AI suggested pillars/modifiers from analysis — shown as suggestions, never auto-merged
  const [aiPillarSuggestions, setAiPillarSuggestions] = useState([])

  // Drag-drop: track which field is being dragged over
  const [dragOverPillar, setDragOverPillar] = useState(false)
  const [dragOverModifier, setDragOverModifier] = useState(false)

  // Debounced localStorage persist
  useEffect(() => {
    const t = setTimeout(() => { localStorage.setItem(lsDomainKey, domain) }, 500)
    return () => clearTimeout(t)
  }, [domain])
  useEffect(() => {
    const t = setTimeout(() => { localStorage.setItem(lsCompKey, JSON.stringify(compUrls)) }, 500)
    return () => clearTimeout(t)
  }, [compUrls])

  // Populate from store profile
  useEffect(() => {
    if (profile) {
      if (profile.domain && !domain) setDomain(profile.domain)
      if (!profileInitRef.current) {
        // First load only — populate user-controlled fields from saved profile
        setPillars(profile.pillars || [])
        setModifiers(profile.modifiers || [])
        profileInitRef.current = true
      }
      // Always update AI-generated/supplementary fields (user can adjust these)
      setProducts(profile.product_catalog || [])
      setAudience(profile.audience || [])
      setNegScope(profile.negative_scope || [])
      setBizType(profile.business_type || "")
      if (profile.usp) setUsp(profile.usp)
      if (Array.isArray(profile.business_locations)) setBusinessLocations(profile.business_locations)
      if (Array.isArray(profile.target_locations)) setTargetLocations(profile.target_locations)
      else if (profile.geo_scope) setTargetLocations(profile.geo_scope.split(",").map(s => s.trim()).filter(Boolean))
      if (Array.isArray(profile.languages)) setLanguages(profile.languages)
      if (Array.isArray(profile.cultural_context)) setCulturalContext(profile.cultural_context)
      if (profile.customer_reviews) setCustomerReviews(profile.customer_reviews)
    }
  }, [profile])

  // ── Per-field AI suggest via /api/strategy/{pid}/ai-suggest ──────────────
  const suggestField = async (type, extraContext = {}, onResult) => {
    setFieldSuggesting(prev => ({ ...prev, [type]: true }))
    try {
      const res = await apiCall(`/api/strategy/${projectId}/ai-suggest`, "POST", {
        type,
        context: {
          domain: domain.trim(), business_type: bizType, pillars,
          product_catalog: products, usp,
          business_locations: businessLocations,
          target_locations: targetLocations,
          locations: targetLocations,
          languages,
          ...extraContext,
        },
      })
      if (res?.suggestions) onResult(res.suggestions)
    } catch (e) {
      toast(`AI suggest failed: ${e.message}`, "error")
    }
    setFieldSuggesting(prev => ({ ...prev, [type]: false }))
  }

  // ── Bulk suggest via kw2 suggest-fields (modifiers + audience + negScope) ──
  const suggestBulk = async () => {
    setFieldSuggesting(prev => ({ ...prev, _bulk: true }))
    log("✨ Requesting AI suggestions for modifiers, audience, negative scope...", "info")
    try {
      const { suggestions } = await api.suggestFields(projectId, {
        domain: domain.trim(), business_type: bizType, pillars,
        product_catalog: products.slice(0, 10),
        geo_scope: targetLocations.join(", "),
      })
      if (suggestions.audience?.length) setAudience(prev => [...new Set([...prev, ...suggestions.audience])])
      if (suggestions.modifiers?.length) setModifiers(prev => [...new Set([...prev, ...suggestions.modifiers])])
      if (suggestions.negative_scope?.length) setNegScope(prev => [...new Set([...prev, ...suggestions.negative_scope])])
      log(`✅ Suggestions merged — Audience +${(suggestions.audience || []).length}, Modifiers +${(suggestions.modifiers || []).length}, Negative +${(suggestions.negative_scope || []).length}`, "success")
      toast("AI suggestions merged into fields", "success")
    } catch (e) {
      log(`❌ Suggestion failed: ${e.message}`, "error")
      toast("AI suggest failed — try again", "error")
    }
    setFieldSuggesting(prev => ({ ...prev, _bulk: false }))
  }

  // ── Crawl from website (auto-fill products) ──────────────────────────────
  const crawlFromWebsite = async () => {
    if (!domain) { toast("Enter a domain URL first", "error"); return }
    setWebsiteCrawling(true)
    try {
      const res = await apiCall(`/api/ki/${projectId}/crawl-context`, "POST", {
        customer_url: domain, existing_pillars: pillars,
      })
      const found = (res?.products || []).map(p => typeof p === "string" ? p : p.name || String(p)).filter(Boolean)
      if (found.length > 0) {
        setProducts(prev => [...new Set([...prev, ...found])])
        toast(`Found ${found.length} products from website`, "success")
      } else {
        toast("No products found on website", "warn")
      }
    } catch (e) { toast(`Website crawl failed: ${e.message}`, "error") }
    setWebsiteCrawling(false)
  }

  // ── Competitor Crawl ──────────────────────────────────────────────────────
  const runCompetitorCrawl = useCallback(async () => {
    if (!sessionId) { toast("Session not initialized — please refresh the page", "error"); return }
    const urls = compUrls.filter((u) => u.startsWith("http"))
    if (!urls.length) { toast("Add at least one competitor URL", "error"); return }
    setCrawling(true)
    setCrawlResult(null)
    log("🔍 Starting competitor keyword crawl...", "info")
    log("   Crawling homepage, blogs, landing pages...", "progress")
    try {
      const data = await api.competitorCrawl(projectId, sessionId, {
        competitor_urls: urls,
        our_pillars: pillars,
        business_type: bizType,
        geo_scope: targetLocations.join(", "),
      })
      setCrawlResult(data)
      log(`✅ Competitor crawl complete — ${data.pages_crawled || 0} pages, ${data.total_keywords || 0} raw keywords`, "success")
      log(`   Cleaned: ${data.cleaned_count || 0} → Top ${data.top_100?.length || 0} keywords`, "info")
      if (data.content_ideas?.length) log(`   Content ideas: ${data.content_ideas.length} headings extracted`, "info")
      toast(`Competitor crawl: ${data.top_100?.length || 0} actionable keywords found`, "success")
    } catch (e) {
      log(`❌ Competitor crawl failed: ${e.message}`, "error")
      toast("Competitor crawl failed", "error")
    }
    setCrawling(false)
  }, [projectId, sessionId, compUrls, pillars, bizType, targetLocations])

  // ── Analyze Business (SSE-based with real provider events) ─────────────────
  const _doRun = useCallback(async (body, providerOverride = null) => {
    // Cancel any existing SSE stream
    if (sseCancel.current) { sseCancel.current(); sseCancel.current = null }

    setLoading(true)
    setError(null)
    setRetryDialog(null)
    setOllamaWarning(false)

    // If provider override, update session first
    if (providerOverride) {
      try {
        await api.setSessionProvider(projectId, sessionId, providerOverride)
        log(`✅ Provider switched to: ${PROVIDER_LABELS[providerOverride] || providerOverride}`, "info")
      } catch (e) {
        log(`⚠ Could not update provider: ${e.message}`, "warn")
      }
    }

    log(`▶ Phase 1 started — analyzing ${body.domain || "business"}`, "info")
    log("  Preparing business context...", "progress")

    let done = false
    const toArr = (v) => Array.isArray(v) ? v : typeof v === "string" && v ? v.split(",").map(s => s.trim()).filter(Boolean) : []

    const cancel = api.runPhase1Stream(projectId, sessionId, body, (ev) => {
      if (done) return

      switch (ev.type) {
        case "progress":
          log(`  ${ev.pct || ""}% — ${ev.message || ev.step}`, "progress")
          break

        case "provider_selected":
          log(`🤖 Using provider: ${PROVIDER_LABELS[ev.provider] || ev.provider}`, "info")
          if (ev.message) toast(ev.message, "info")
          break

        case "provider_warning":
          // Ollama slow warning shown in UI (already intercepted before stream), just log it
          log(`⚠️ ${ev.message}`, "warn")
          break

        case "rate_limited":
          log(`⚠️ ${ev.message || `${ev.provider} rate-limited, switching to ${ev.switching_to}`}`, "warn")
          toast(`⚠️ ${ev.provider} rate-limited — switching to ${ev.switching_to}`, "warn")
          break

        case "provider_switch":
          log(`🔄 Provider switched: ${ev.from} → ${ev.to} (${ev.reason})`, "warn")
          break

        case "providers_exhausted":
          log(`❌ ${ev.message}`, "error")
          toast("All AI providers exhausted — see retry dialog", "error")
          setRetryDialog({ reason: ev.message })
          done = true
          setLoading(false)
          break

        case "done":
          done = true
          if (ev.profile) {
            const result = ev.profile
            const pArr = toArr(result.pillars)
            const prArr = toArr(result.product_catalog)
            const mArr = toArr(result.modifiers)
            const aArr = toArr(result.audience)

            // Lock ref BEFORE setProfile so useEffect doesn't overwrite user pillars
            profileInitRef.current = true
            setProfile(result)

            // Show AI pillars as SUGGESTIONS — never auto-merge into user's confirmed pillars.
            // User explicitly reviews and adds what they want via the suggestion panel.
            setPillars(prev => {
              const existing = new Set(prev.map(p => p.toLowerCase()))
              const newAi = pArr.filter(p => !existing.has(p.toLowerCase()))
              if (newAi.length) setAiPillarSuggestions(newAi)
              return prev  // user pillars unchanged
            })

            // Modifiers: auto-merge (less disruptive, user expects qualifier suggestions)
            setModifiers(prev => {
              const existing = new Set(prev.map(m => m.toLowerCase()))
              const aiOnly = mArr.filter(m => !existing.has(m.toLowerCase()))
              return [...prev, ...aiOnly]
            })

            // Update AI-generated supplementary fields
            setProducts(prArr)
            setAudience(aArr)
            if (result.negative_scope) setNegScope(toArr(result.negative_scope))

            log(`✅ 100% — Phase 1 complete`, "success")
            log(`   Your pillars: ${pillars.length} preserved | AI suggests: ${pArr.filter(p => !new Set(pillars.map(x=>x.toLowerCase())).has(p.toLowerCase())).length} new to review | Products: ${prArr.length}`, "info")
            log(`   Confidence: ${((result.confidence_score || 0) * 100).toFixed(0)}% | Type: ${result.business_type || "detected"}`, "info")
            toast(`Analysis complete — your pillars confirmed, ${pArr.filter(p => !new Set(pillars.map(x=>x.toLowerCase())).has(p.toLowerCase())).length} AI suggestions ready to review`, "success")
          }
          break

        case "session_updated":
          // Phase 1 complete, now auto-run competitor crawl if URLs given
          done = true
          ;(async () => {
            const crawlableUrls = (body.competitor_urls || []).filter(u => u.startsWith("http"))
            if (crawlableUrls.length > 0) {
              log(`🔍 Starting competitor keyword crawl...`, "info")
              setCrawling(true); setCrawlResult(null)
              const _timeout = new Promise((_, rej) => setTimeout(() => rej(new Error("Timeout — crawl finishing in background, check BI phase for results")), 45000))
              try {
                const crawlData = await Promise.race([
                  api.competitorCrawl(projectId, sessionId, {
                    competitor_urls: crawlableUrls,
                    our_pillars: pillars,
                    business_type: bizType,
                    geo_scope: targetLocations.join(", "),
                  }),
                  _timeout,
                ])
                setCrawlResult(crawlData)
                log(`✅ Competitor crawl — ${crawlData.pages_crawled || 0} pages, top ${crawlData.top_100?.length || 0} keywords`, "success")
              } catch (ce) {
                log(`⏱ ${ce.message}`, "warn")
              }
              setCrawling(false)
            }
            setLoading(false)
            onComplete()
            // Auto-advance to BI phase after Phase 1 completes
            setActivePhase("BI")
          })()
          return

        case "error":
          done = true
          const detail = ev.message || "Unknown error"
          log(`❌ Phase 1 failed: ${detail}`, "error")
          setError(detail)
          toast("Phase 1 failed — check log for details", "error")
          // Show retry dialog on any error
          setRetryDialog({ reason: detail })
          setLoading(false)
          break

        default:
          break
      }

      if (done && ev.type !== "session_updated") {
        setLoading(false)
      }
    })

    sseCancel.current = cancel
  }, [projectId, sessionId, pillars, bizType, targetLocations, log, toast, setProfile, setError, setLoading, onComplete])

  const run = useCallback(() => {
    // Validate domain before locking state
    if (!domain.trim()) { setError("Domain URL is required before running analysis."); return }

    // Lock user's pillars — from this point forward useEffect never overwrites
    profileInitRef.current = true
    const body = {
      domain: domain.trim(), pillars, product_catalog: products,
      modifiers, negative_scope: negScope, audience,
      usp, business_type: bizType.trim(),
      business_locations: businessLocations,
      target_locations: targetLocations,
      geo_scope: targetLocations.join(", "),
      languages, cultural_context: culturalContext,
      customer_reviews: customerReviews,
      competitor_urls: compUrls.filter(u => u.startsWith("http")),
    }
    pendingBodyRef.current = body

    // Check if Ollama is selected — show warning first
    // We read the provider from the store or will detect it from the SSE event.
    // For Ollama detection we check localStorage or store if available.
    const storedProvider = localStorage.getItem(`kw2_provider_${sessionId}`) || "auto"
    if (storedProvider === "ollama") {
      setOllamaWarning(true)
      return
    }

    _doRun(body)
  }, [domain, pillars, products, modifiers, negScope, audience, usp, bizType,
      businessLocations, targetLocations, languages, culturalContext, customerReviews,
      compUrls, sessionId, _doRun])

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => { if (sseCancel.current) sseCancel.current() }
  }, [])

  const fs = { width: "100%", padding: "8px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13, boxSizing: "border-box" }
  const ls = { fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 4, display: "block" }

  const SectionTitle = ({ icon, children }) => (
    <div style={{ fontSize: 13, fontWeight: 700, color: "#1e1b4b", margin: "14px 0 10px", paddingBottom: 5, borderBottom: "1px solid #e5e7eb" }}>
      {icon} {children}
    </div>
  )

  const FieldRow = ({ label, hint, btn, children }) => (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <label style={{ ...ls, marginBottom: 0, flex: 1 }}>{label}</label>
        {btn}
      </div>
      {hint && <div style={{ fontSize: 10, color: "#9ca3af", marginBottom: 4 }}>{hint}</div>}
      {children}
    </div>
  )

  return (
    <>
      {/* ── Dialogs & Warnings ─────────────────────────────────────────────── */}
      {retryDialog && (
        <ProviderRetryDialog
          reason={retryDialog.reason}
          onRetry={(newProvider) => {
            const body = pendingBodyRef.current
            if (body) _doRun(body, newProvider)
            else setRetryDialog(null)
          }}
          onDismiss={() => setRetryDialog(null)}
        />
      )}

      {ollamaWarning && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 9998, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "#fff", borderRadius: 12, padding: "24px 28px", maxWidth: 440, width: "90%", boxShadow: "0 20px 60px rgba(0,0,0,0.3)" }}>
            <OllamaWarning
              onSwitch={async () => {
                setOllamaWarning(false)
                localStorage.setItem(`kw2_provider_${sessionId}`, "groq")
                const body = pendingBodyRef.current
                if (body) _doRun(body, "groq")
              }}
              onContinue={() => {
                setOllamaWarning(false)
                const body = pendingBodyRef.current
                if (body) _doRun(body)
              }}
            />
          </div>
        </div>
      )}

    <Card title="Phase 1: Business Analysis" actions={
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button
          onClick={suggestBulk} disabled={fieldSuggesting._bulk || loading}
          style={{
            padding: "6px 12px", borderRadius: 6, border: "1px solid #8b5cf6",
            background: fieldSuggesting._bulk ? "#ede9fe" : "#f5f3ff", color: "#7c3aed",
            fontSize: 12, fontWeight: 600, cursor: fieldSuggesting._bulk ? "not-allowed" : "pointer",
          }}
        >
          {fieldSuggesting._bulk ? "✨ Suggesting..." : "✨ Suggest All Fields"}
        </button>
        <RunButton onClick={run} loading={loading} disabled={!domain}>
          Analyze Business
        </RunButton>
      </div>
    }>

      {/* ── Two-Column Layout ─────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 12 }}>

        {/* LEFT — Business Profile */}
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
            <textarea value={usp} onChange={e => setUsp(e.target.value)}
              placeholder="What makes your business unique?" rows={2}
              style={{ ...fs, resize: "vertical" }} />
          </div>

          <FieldRow
            label="Products & Services"
            btn={
              <FieldSuggestBtn
                label={websiteCrawling ? "🔍 Crawling…" : "🔍 Crawl from Website"}
                loading={websiteCrawling}
                disabled={!domain}
                onClick={crawlFromWebsite}
              />
            }
          >
            <TagInput tags={products} onChange={setProducts}
              placeholder="turmeric powder, cardamom pods" color="#059669" bgColor="#d1fae5" />
          </FieldRow>

          <FieldRow label={<>Pillar Keywords <span style={{ fontSize: 10, color: "#6b7280", fontWeight: 400 }}>press Enter to add · or drag from competitor section</span></>}>
            <div
              onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; setDragOverPillar(true) }}
              onDragLeave={() => setDragOverPillar(false)}
              onDrop={async (e) => {
                e.preventDefault(); setDragOverPillar(false)
                const term = e.dataTransfer.getData("application/kw2-term")
                if (!term) return
                profileInitRef.current = true
                const next = pillars.includes(term) ? pillars : [...pillars, term]
                setPillars(next)
                try {
                  await api.addToProfile(projectId, sessionId, [term], "pillars")
                  await api.updateProfile(projectId, { pillars: next })
                } catch {}
                toast(`"${term}" dragged to Pillars ✓`, "success")
              }}
              style={{
                borderRadius: 6,
                outline: dragOverPillar ? "2px dashed #3b82f6" : "2px dashed transparent",
                background: dragOverPillar ? "#eff6ff" : "transparent",
                transition: "all 0.15s",
              }}
            >
              <TagInput tags={pillars} onChange={async (next) => {
                profileInitRef.current = true  // user is managing pillars — lock against profile overwrites
                setPillars(next)
                if (projectId) {
                  try { await api.updateProfile(projectId, { pillars: next }) } catch { /* ignore */ }
                }
              }}
                placeholder="Type a pillar and press Enter" color="#2563eb" bgColor="#dbeafe" />
            </div>
            {/* AI-suggested pillars panel — shown after analysis, user reviews before adding */}
            {aiPillarSuggestions.length > 0 && (
              <div style={{ marginTop: 6, padding: "8px 10px", background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 6 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "#1d4ed8", marginBottom: 4 }}>
                  🤖 AI Suggested Pillars — click to add or drag to confirm
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {aiPillarSuggestions.map((p, i) => (
                    <button key={i} onClick={async () => {
                      const next = pillars.includes(p) ? pillars : [...pillars, p]
                      setPillars(next)
                      setAiPillarSuggestions(prev => prev.filter((_, idx) => idx !== i))
                      try { await api.updateProfile(projectId, { pillars: next }) } catch {}
                      toast(`"${p}" added to pillars`, "success")
                    }} style={{
                      padding: "2px 10px", borderRadius: 10, border: "1px solid #93c5fd",
                      background: "#eff6ff", color: "#1d4ed8", fontSize: 11, cursor: "pointer",
                    }}>+ {p}</button>
                  ))}
                  <button onClick={() => setAiPillarSuggestions([])} style={{
                    padding: "2px 8px", borderRadius: 10, border: "1px solid #d1d5db",
                    background: "#fff", color: "#9ca3af", fontSize: 11, cursor: "pointer",
                  }}>✕ Dismiss</button>
                </div>
              </div>
            )}
          </FieldRow>

          <FieldRow label={<>Competitor URLs <span style={{ fontSize: 10, color: "#6b7280", fontWeight: 400 }}>full URL</span></>}>
            <TagInput tags={compUrls} onChange={setCompUrls}
              placeholder="https://competitor.com" color="#d97706" bgColor="#fef3c7" />
          </FieldRow>
        </div>

        {/* RIGHT — Target Audience */}
        <div>
          <SectionTitle icon="🎯">Target Audience</SectionTitle>

          {/* Business Locations */}
          <FieldRow
            label={<>
              📍 Business Location(s)
              {businessLocations.length > 0 && (
                <span style={{ fontSize: 10, color: "#8b5cf6", marginLeft: 6 }}>
                  Level: {DEPTH_LABELS[Math.min(businessLocationDepth, 3)]}
                </span>
              )}
            </>}
            hint="Where your business operates from (authority signals)"
            btn={
              <FieldSuggestBtn
                label={businessLocations.length === 0 ? "✨ AI Suggest" : `✨ Drill ${DEPTH_NEXT[Math.min(businessLocationDepth, 3)]}`}
                loading={fieldSuggesting["business_regions"]}
                onClick={() => suggestField("business_regions",
                  { depth: businessLocationDepth, current: businessLocations },
                  (items) => {
                    const names = (Array.isArray(items) ? items : []).map(x => typeof x === "string" ? x : x.name || String(x))
                    setBusinessLocations(prev => [...new Set([...prev, ...names])])
                    setBusinessLocationDepth(d => d + 1)
                  }
                )}
              />
            }
          >
            <TagInput
              tags={businessLocations}
              onChange={v => { setBusinessLocations(v); if (v.length === 0) setBusinessLocationDepth(0) }}
              placeholder="Kerala, Tamil Nadu…" color="#8b5cf6" bgColor="#ede9fe"
            />
          </FieldRow>

          {/* Target Locations */}
          <FieldRow
            label={<>
              🎯 Target Location(s)
              {targetLocations.length > 0 && (
                <span style={{ fontSize: 10, color: "#8b5cf6", marginLeft: 6 }}>
                  Level: {DEPTH_LABELS[Math.min(targetLocationDepth, 3)]}
                </span>
              )}
            </>}
            hint="Where your customers are (geo-targeted keywords)"
            btn={
              <FieldSuggestBtn
                label={targetLocations.length === 0 ? "✨ AI Suggest" : `✨ Drill ${DEPTH_NEXT[Math.min(targetLocationDepth, 3)]}`}
                loading={fieldSuggesting["regions"]}
                onClick={() => suggestField("regions",
                  { depth: targetLocationDepth, current: targetLocations },
                  (items) => {
                    const names = (Array.isArray(items) ? items : []).map(x => typeof x === "string" ? x : x.name || String(x))
                    setTargetLocations(prev => [...new Set([...prev, ...names])])
                    setTargetLocationDepth(d => d + 1)
                  }
                )}
              />
            }
          >
            <TagInput
              tags={targetLocations}
              onChange={v => { setTargetLocations(v); if (v.length === 0) setTargetLocationDepth(0) }}
              placeholder="India, USA, UK…" color="#0891b2" bgColor="#cffafe"
            />
          </FieldRow>

          {/* Languages */}
          <FieldRow
            label="Languages"
            btn={
              <FieldSuggestBtn
                label="✨ AI Suggest"
                loading={fieldSuggesting["languages"]}
                onClick={() => suggestField("languages", { locations: targetLocations }, (items) => {
                  const names = (Array.isArray(items) ? items : []).map(x => typeof x === "string" ? x : x.name || String(x))
                  setLanguages(prev => [...new Set([...prev, ...names])])
                })}
              />
            }
          >
            <TagInput tags={languages} onChange={setLanguages}
              placeholder="English, Hindi, Tamil…" color="#2563eb" bgColor="#dbeafe" />
          </FieldRow>

          {/* Cultural Context */}
          <FieldRow label="Cultural Context">
            <TagInput tags={culturalContext} onChange={setCulturalContext}
              placeholder="General, Hindu, Muslim…" color="#6b7280" bgColor="#f3f4f6" />
          </FieldRow>

          {/* Target Audiences */}
          <FieldRow
            label="Target Audiences"
            btn={
              <FieldSuggestBtn
                label={audience.length === 0 ? "✨ AI Suggest" : "✨ Expand Audiences"}
                loading={fieldSuggesting["personas"]}
                onClick={() => suggestField("personas", { personas: audience }, (items) => {
                  const names = (Array.isArray(items) ? items : []).map(x => typeof x === "string" ? x : x.audience || x.name || String(x))
                  setAudience(prev => [...new Set([...prev, ...names])])
                })}
              />
            }
          >
            <TagInput tags={audience} onChange={setAudience}
              placeholder="restaurant owners, home cooks" color="#0891b2" bgColor="#cffafe" />
          </FieldRow>

          {/* Customer Reviews */}
          <FieldRow
            label="Customer Reviews"
            btn={
              <FieldSuggestBtn
                label="✨ Generate Samples"
                loading={fieldSuggesting["reviews"]}
                onClick={() => suggestField("reviews", {}, (items) => {
                  const strs = (Array.isArray(items) ? items : []).map(x => typeof x === "string" ? x : x.review || String(x))
                  setCustomerReviews(prev => prev ? prev + "\n" + strs.join("\n") : strs.join("\n"))
                })}
              />
            }
          >
            <textarea value={customerReviews} onChange={e => setCustomerReviews(e.target.value)}
              placeholder="Paste real customer reviews or generate samples…" rows={3}
              style={{ ...fs, resize: "vertical" }} />
          </FieldRow>
        </div>
      </div>

      {/* ── Modifiers & Negative Scope ─────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
        <FieldRow
          label="Modifiers"
          hint="Drag competitor keywords here to use as modifiers"
          btn={
            <FieldSuggestBtn
              label="✨ AI Suggest"
              loading={fieldSuggesting["_mod"]}
              onClick={async () => {
                setFieldSuggesting(prev => ({ ...prev, _mod: true }))
                try {
                  const { suggestions } = await api.suggestFields(projectId, {
                    domain: domain.trim(), business_type: bizType, pillars,
                    product_catalog: products.slice(0, 10), geo_scope: targetLocations.join(", "),
                  })
                  if (suggestions.modifiers?.length) setModifiers(prev => [...new Set([...prev, ...suggestions.modifiers])])
                  toast(`+${(suggestions.modifiers || []).length} modifiers added`, "success")
                } catch (e) { toast("Suggest failed", "error") }
                setFieldSuggesting(prev => ({ ...prev, _mod: false }))
              }}
            />
          }
        >
          <div
            onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; setDragOverModifier(true) }}
            onDragLeave={() => setDragOverModifier(false)}
            onDrop={async (e) => {
              e.preventDefault(); setDragOverModifier(false)
              const term = e.dataTransfer.getData("application/kw2-term")
              if (!term) return
              const next = modifiers.includes(term) ? modifiers : [...modifiers, term]
              setModifiers(next)
              try { await api.addToProfile(projectId, sessionId, [term], "modifiers") } catch {}
              toast(`"${term}" dragged to Modifiers ✓`, "success")
            }}
            style={{
              borderRadius: 6,
              outline: dragOverModifier ? "2px dashed #8b5cf6" : "2px dashed transparent",
              background: dragOverModifier ? "#f5f3ff" : "transparent",
              transition: "all 0.15s",
            }}
          >
            <TagInput tags={modifiers} onChange={setModifiers}
              placeholder="organic, wholesale, bulk" color="#7c3aed" bgColor="#ede9fe" />
          </div>
        </FieldRow>

        <FieldRow
          label="Negative Scope"
          btn={
            <FieldSuggestBtn
              label="✨ AI Suggest"
              loading={fieldSuggesting["_neg"]}
              onClick={async () => {
                setFieldSuggesting(prev => ({ ...prev, _neg: true }))
                try {
                  const { suggestions } = await api.suggestFields(projectId, {
                    domain: domain.trim(), business_type: bizType, pillars,
                    product_catalog: products.slice(0, 10), geo_scope: targetLocations.join(", "),
                  })
                  if (suggestions.negative_scope?.length) setNegScope(prev => [...new Set([...prev, ...suggestions.negative_scope])])
                  toast(`+${(suggestions.negative_scope || []).length} negative scope items added`, "success")
                } catch (e) { toast("Suggest failed", "error") }
                setFieldSuggesting(prev => ({ ...prev, _neg: false }))
              }}
            />
          }
        >
          <TagInput tags={negScope} onChange={setNegScope}
            placeholder="recipe, benefits, how to" color="#dc2626" bgColor="#fee2e2" />
        </FieldRow>
      </div>

      {/* ── Competitor Keyword Crawl ────────────────────────────────────────── */}
      {compUrls.length > 0 && (
        <div style={{ marginBottom: 12, padding: 12, background: "#fefce8", border: "1px solid #fbbf2433", borderRadius: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div>
              <span style={{ fontSize: 13, fontWeight: 600, color: "#92400e" }}>Competitor Keyword Intelligence</span>
              <p style={{ margin: "4px 0 0", fontSize: 11, color: "#78716c" }}>
                Crawl competitor pages, extract keywords, clean &amp; rank top 100
              </p>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              {crawlResult?.top_100?.length > 0 && (
                <button
                  disabled={compAnalyzing}
                  onClick={async () => {
                    setCompAnalyzing(true); setCompAnalysis(null)
                    try {
                      const terms = crawlResult.top_100.slice(0, 60).map(k => typeof k === "string" ? k : k.keyword)
                      const res = await api.analyzeCompetitorKeywords(projectId, sessionId, terms)
                      setCompAnalysis(res)
                      toast(`AI analysis: ${res.pillars?.length || 0} pillars, ${res.modifiers?.length || 0} modifiers suggested`, "success")
                    } catch (e) { toast(`Analysis failed: ${e.message}`, "error") }
                    setCompAnalyzing(false)
                  }}
                  style={{
                    padding: "6px 12px", borderRadius: 6, border: "none",
                    background: compAnalyzing ? "#a78bfa" : "#8b5cf6", color: "#fff",
                    fontSize: 12, fontWeight: 600, cursor: compAnalyzing ? "not-allowed" : "pointer",
                  }}
                >
                  {compAnalyzing ? "Analyzing..." : "🤖 AI Classify"}
                </button>
              )}
              <button
                onClick={runCompetitorCrawl} disabled={crawling || loading}
                style={{
                  padding: "6px 14px", borderRadius: 6, border: "none",
                  background: crawling ? "#fbbf24" : "#f59e0b", color: "#fff",
                  fontSize: 12, fontWeight: 600, cursor: crawling ? "not-allowed" : "pointer",
                }}
              >
                {crawling ? "Crawling..." : "Crawl Competitors"}
              </button>
            </div>
          </div>
          {crawlResult && (
            <div>
              <StatsRow items={[
                { label: "Pages Crawled", value: crawlResult.pages_crawled || 0, color: "#d97706" },
                { label: "Raw Keywords", value: crawlResult.total_keywords || 0, color: "#6b7280" },
                { label: "After Clean", value: crawlResult.cleaned_count || 0, color: "#3b82f6" },
                { label: "Top Keywords", value: crawlResult.top_100?.length || 0, color: "#10b981" },
              ]} />
              {crawlResult.top_100?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 4 }}>
                    Top Competitor Keywords
                    <span style={{ fontWeight: 400, color: "#6b7280", marginLeft: 8, fontSize: 11 }}>
                      Click <span style={{ color: "#3b82f6" }}>+P</span> to add as Pillar, <span style={{ color: "#8b5cf6" }}>+M</span> to add as Modifier
                    </span>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, maxHeight: 200, overflowY: "auto" }}>
                    {crawlResult.top_100.slice(0, 80).map((kw, i) => {
                      const term = typeof kw === "string" ? kw : kw.keyword || kw.term
                      if (!term) return null
                      return (
                        <span key={i}
                          draggable
                          onDragStart={(e) => {
                            e.dataTransfer.setData("application/kw2-term", term)
                            e.dataTransfer.effectAllowed = "copy"
                          }}
                          title="Drag to Pillar Keywords or Modifiers field above"
                          style={{
                          padding: "2px 4px 2px 8px", borderRadius: 10, fontSize: 11,
                          background: "#fef3c7", border: "1px solid #fbbf24", color: "#92400e",
                          display: "inline-flex", alignItems: "center", gap: 3,
                          cursor: "grab",
                        }}>
                          {term}
                          {typeof kw !== "string" && kw.score ? <b style={{ marginLeft: 2 }}>({kw.score})</b> : null}
                          <button title="Add as Pillar" onClick={async () => {
                            try {
                              await api.addToProfile(projectId, sessionId, [term], "pillars")
                              setPillars(prev => prev.includes(term) ? prev : [...prev, term])
                              toast(`"${term}" added to pillars`, "success")
                            } catch (e) { toast(`Failed: ${e.message}`, "error") }
                          }} style={{
                            padding: "0 3px", border: "none", borderRadius: 4, fontSize: 10,
                            background: "#dbeafe", color: "#2563eb", cursor: "pointer", fontWeight: 700,
                          }}>+P</button>
                          <button title="Add as Modifier" onClick={async () => {
                            try {
                              await api.addToProfile(projectId, sessionId, [term], "modifiers")
                              setModifiers(prev => prev.includes(term) ? prev : [...prev, term])
                              toast(`"${term}" added to modifiers`, "success")
                            } catch (e) { toast(`Failed: ${e.message}`, "error") }
                          }} style={{
                            padding: "0 3px", border: "none", borderRadius: 4, fontSize: 10,
                            background: "#ede9fe", color: "#7c3aed", cursor: "pointer", fontWeight: 700,
                          }}>+M</button>
                        </span>
                      )
                    })}
                    {crawlResult.top_100.length > 80 && (
                      <span style={{ fontSize: 11, color: "#9ca3af", alignSelf: "center" }}>+{crawlResult.top_100.length - 80} more</span>
                    )}
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

              {/* AI Classification Results */}
              {compAnalysis && (
                <div style={{ marginTop: 10, padding: 10, background: "#f5f3ff", borderRadius: 6, border: "1px solid #ddd6fe" }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#5b21b6", marginBottom: 8 }}>
                    🤖 AI Classification — click to add
                  </div>
                  {compAnalysis.pillars?.length > 0 && (
                    <div style={{ marginBottom: 6 }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: "#3b82f6", marginRight: 6 }}>Suggested Pillars:</span>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                        {compAnalysis.pillars.map((r, i) => (
                          <button key={i} title={r.reason} onClick={async () => {
                            await api.addToProfile(projectId, sessionId, [r.keyword], "pillars")
                            setPillars(prev => prev.includes(r.keyword) ? prev : [...prev, r.keyword])
                            setCompAnalysis(prev => ({ ...prev, pillars: prev.pillars.filter((_, idx) => idx !== i) }))
                            toast(`"${r.keyword}" added to pillars`, "success")
                          }} style={{
                            padding: "2px 10px", borderRadius: 10, border: "1px solid #93c5fd",
                            background: "#eff6ff", color: "#1d4ed8", fontSize: 11, cursor: "pointer",
                          }}>
                            + {r.keyword}
                          </button>
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
                            await api.addToProfile(projectId, sessionId, [r.keyword], "modifiers")
                            setModifiers(prev => prev.includes(r.keyword) ? prev : [...prev, r.keyword])
                            setCompAnalysis(prev => ({ ...prev, modifiers: prev.modifiers.filter((_, idx) => idx !== i) }))
                            toast(`"${r.keyword}" added to modifiers`, "success")
                          }} style={{
                            padding: "2px 10px", borderRadius: 10, border: "1px solid #c4b5fd",
                            background: "#f5f3ff", color: "#6d28d9", fontSize: 11, cursor: "pointer",
                          }}>
                            + {r.keyword}
                          </button>
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

      {/* ── Profile Result ──────────────────────────────────────────────────── */}
      {profile && (
        <div style={{ marginTop: 16 }}>
          <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>Business Profile</h4>
          <StatsRow items={[
            { label: "Pillars", value: (profile.pillars || []).length, color: "#3b82f6" },
            { label: "Products", value: (profile.product_catalog || []).length, color: "#10b981" },
            { label: "Modifiers", value: (profile.modifiers || []).length, color: "#8b5cf6" },
            { label: "Confidence", value: `${((profile.confidence_score || 0) * 100).toFixed(0)}%`, color: profile.confidence_score >= 0.7 ? "#10b981" : "#f59e0b" },
          ]} />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <Badge color="blue">{profile.universe || "Universe"}</Badge>
            <Badge color="green">{profile.business_type || "Unknown type"}</Badge>
            {targetLocations.length > 0 && <Badge color="gray">{targetLocations.slice(0, 3).join(", ")}</Badge>}
          </div>
          <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.7 }}>
            {(profile.pillars || []).length > 0 && (
              <div style={{ marginBottom: 6 }}>
                <strong>Pillars:</strong>{" "}
                {(profile.pillars || []).map((p, i) => <Badge key={i} color="blue">{p}</Badge>).reduce((a, b) => [a, " ", b])}
              </div>
            )}
            {(profile.product_catalog || []).length > 0 && (
              <div style={{ marginBottom: 6 }}><strong>Products:</strong> {(profile.product_catalog || []).join(", ")}</div>
            )}
            {(profile.modifiers || []).length > 0 && (
              <div style={{ marginBottom: 6 }}><strong>Modifiers:</strong> {(profile.modifiers || []).join(", ")}</div>
            )}
            {(profile.audience || []).length > 0 && (
              <div style={{ marginBottom: 6 }}><strong>Audience:</strong> {(profile.audience || []).join(", ")}</div>
            )}
          </div>

          <PhaseResult
            phaseNum={1}
            stats={[
              { label: "Pillars", value: (profile.pillars || []).length, color: "#3b82f6" },
              { label: "Products", value: (profile.product_catalog || []).length, color: "#10b981" },
              { label: "Confidence", value: `${((profile.confidence_score || 0) * 100).toFixed(0)}%`, color: "#8b5cf6" },
            ]}
            nextLabel="Continue to Business Intelligence →"
            onNext={onNext || (() => setActivePhase("BI"))}
          />
        </div>
      )}

      <NotificationList notifications={notifications} title="Run Notifications" />
    </Card>
    </>
  )
}
