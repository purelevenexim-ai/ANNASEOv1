// Step 1 — Project Setup (Consolidated)
// Collects: business profile, audience, competitor URLs, pillars, supporting keywords
// Replaces old Step1SmartList + parts of Step3Strategy + StrategyPage profile
// Saves via: PUT /api/ki/{pid}/profile + POST /api/ki/{pid}/input

import { useState, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNotification } from "../store/notification"
import useWorkflowContext from "../store/workflowContext"
import { apiCall, API, T, Card, Btn, Spinner, INTENT_OPTIONS } from "./shared"

function authHeaders() {
  const t = localStorage.getItem("annaseo_token")
  return t ? { Authorization: `Bearer ${t}` } : {}
}

// ─── Chip Input ─────────────────────────────────────────────────────────────
function ChipInput({ items, setItems, placeholder, inputValue, setInputValue }) {
  const add = () => {
    const v = (inputValue || "").trim()
    if (!v) return
    if (items.some(x => x.toLowerCase() === v.toLowerCase())) return
    setItems([...items, v])
    setInputValue("")
  }
  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 6 }}>
        {items.map(item => (
          <span key={item} style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            padding: "3px 10px", borderRadius: 99, fontSize: 11, fontWeight: 500,
            background: T.purpleLight, color: T.purple, border: `1px solid ${T.purple}30`,
          }}>
            {item}
            <span style={{ cursor: "pointer", fontWeight: 700 }}
              onClick={() => setItems(items.filter(x => x !== item))}>×</span>
          </span>
        ))}
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        <input value={inputValue} onChange={e => setInputValue(e.target.value)}
          placeholder={placeholder}
          onKeyDown={e => e.key === "Enter" && (e.preventDefault(), add())}
          style={{ flex: 1, padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box" }}
        />
        <Btn small onClick={add}>Add</Btn>
      </div>
    </div>
  )
}

// ─── AI Suggest Button (with optional depth label) ─────────────────────────
function AISuggestBtn({ projectId, type, onResult, disabled, context, label, aiProvider }) {
  const [loading, setLoading] = useState(false)
  return (
    <Btn small variant="teal" disabled={loading || disabled}
      onClick={async () => {
        setLoading(true)
        try {
          const body = { type }
          if (context) body.context = context
          // Pass depth and current for progressive location drill-down
          if (context?.depth !== undefined) body.depth = context.depth
          if (context?.current) body.current = context.current
          if (aiProvider) body.preferred_provider = aiProvider
          const res = await apiCall(`/api/strategy/${projectId}/ai-suggest`, "POST", body)
          if (res?.suggestions) onResult(res.suggestions)
        } catch (e) { console.warn("AI suggest failed:", e) }
        setLoading(false)
      }}>
      {loading ? <Spinner /> : (label || `✨ AI Suggest`)}
    </Btn>
  )
}

// ─── Section Header ─────────────────────────────────────────────────────────
function SectionTitle({ children }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 8, marginTop: 16 }}>
      {children}
    </div>
  )
}

const inStyle = {
  width: "100%", padding: "7px 10px", borderRadius: 8,
  border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box",
}

const DEPTH_LABELS = ["🌍 Countries", "🏛️ States", "🏘️ Districts", "📍 Towns"]
const DEPTH_NEXT = ["→ States", "→ Districts", "→ Towns", "→ Areas"]

// ─── Main Component ──────────────────────────────────────────────────────────
export default function Step1Setup({ projectId, onComplete, aiProvider = "groq" }) {
  const notify = useNotification(s => s.notify)
  const ctx = useWorkflowContext()

  // Business profile
  const [websiteUrl, setWebsiteUrl]       = useState("")
  const [businessType, setBusinessType]   = useState("B2C")
  const [usp, setUsp]                     = useState("")
  const [products, setProducts]           = useState([])
  const [productInput, setProductInput]   = useState("")
  const [competitorUrls, setCompetitorUrls] = useState([])
  const [competitorInput, setCompetitorInput] = useState("")

  // Audience
  const [personas, setPersonas]           = useState([])
  const [personaInput, setPersonaInput]   = useState("")
  const [targetLocations, setTargetLocations] = useState([])
  const [locationInput, setLocationInput] = useState("")
  const [targetLocationDepth, setTargetLocationDepth] = useState(0)
  const [businessLocations, setBusinessLocations] = useState([])
  const [businessLocationInput, setBusinessLocationInput] = useState("")
  const [businessLocationDepth, setBusinessLocationDepth] = useState(0)
  const [targetLanguages, setTargetLanguages] = useState([])
  const [languageInput, setLanguageInput] = useState("")
  const [targetReligions, setTargetReligions] = useState([])
  const [religionInput, setReligionInput] = useState("")
  const [customerReviews, setCustomerReviews] = useState("")

  // Pillar keywords
  const [pillars, setPillars]             = useState([])
  const [pillarInput, setPillarInput]     = useState("")
  const [globalSupports, setGlobalSupports] = useState([])
  const [supportInput, setSupportInput]   = useState("")
  const [intentFocus, setIntentFocus]     = useState(["transactional"])

  // Strategy settings
  const [rankTarget, setRankTarget]       = useState("top 5")
  const [timeframe, setTimeframe]         = useState(6)
  const [blogsPerWeek, setBlogsPerWeek]   = useState(3)

  const [submitting, setSubmitting]       = useState(false)
  const [crawling, setCrawling]           = useState(false)

  // Load existing profile
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ["ki-profile", projectId],
    queryFn: () => apiCall(`/api/ki/${projectId}/profile`),
    enabled: !!projectId,
    retry: false,
  })

  // Load existing pillars
  const { data: existingPillars } = useQuery({
    queryKey: ["ki-pillars", projectId],
    queryFn: () => apiCall(`/api/ki/${projectId}/pillars`),
    enabled: !!projectId,
    retry: false,
  })

  // Populate form from profile
  useEffect(() => {
    if (!profile) return
    if (profile.website_url) setWebsiteUrl(profile.website_url)
    if (profile.business_type) setBusinessType(profile.business_type)
    if (profile.usp) setUsp(profile.usp)
    if (Array.isArray(profile.products)) setProducts(profile.products.map(p => typeof p === "string" ? p : p.name || JSON.stringify(p)))
    if (Array.isArray(profile.competitor_urls)) setCompetitorUrls(profile.competitor_urls)
    if (Array.isArray(profile.personas)) setPersonas(profile.personas.map(p => typeof p === "string" ? p : p.name || JSON.stringify(p)))
    if (Array.isArray(profile.target_locations)) setTargetLocations(profile.target_locations)
    if (Array.isArray(profile.business_locations)) setBusinessLocations(profile.business_locations)
    if (Array.isArray(profile.target_languages)) setTargetLanguages(profile.target_languages)
    if (Array.isArray(profile.target_religions)) setTargetReligions(profile.target_religions)
    if (profile.customer_reviews) setCustomerReviews(profile.customer_reviews)
    if (profile.rank_target) setRankTarget(profile.rank_target)
    if (profile.timeframe_months) setTimeframe(profile.timeframe_months)
    if (profile.blogs_per_week) setBlogsPerWeek(profile.blogs_per_week)
    if (profile.intent_focus) {
      const v = profile.intent_focus
      setIntentFocus(Array.isArray(v) ? v : [v])
    }
  }, [profile])

  // Restore from workflow context
  useEffect(() => {
    if (ctx.step1) {
      const s1 = ctx.step1
      if (Array.isArray(s1.pillars) && s1.pillars.length > 0) {
        setPillars(s1.pillars.map(k => typeof k === "string" ? k : k.keyword || k))
      }
      if (Array.isArray(s1.supports)) setGlobalSupports(s1.supports)
      if (Array.isArray(s1.intent)) setIntentFocus(s1.intent.length > 0 ? s1.intent : ["transactional"])
    }
  }, [])

  const pillarBank = existingPillars?.pillars?.slice(0, 12) || []

  // ── Save & Continue ────────────────────────────────────────────────────
  const handleSave = async () => {
    if (pillars.length === 0) {
      notify("Add at least one pillar keyword", "warn")
      return
    }
    setSubmitting(true)
    try {
      // 1. Save consolidated profile
      await apiCall(`/api/ki/${projectId}/profile`, "PUT", {
        website_url: websiteUrl,
        business_type: businessType,
        usp,
        products,
        competitor_urls: competitorUrls,
        personas,
        target_locations: targetLocations,
        business_locations: businessLocations,
        target_languages: targetLanguages,
        target_religions: targetReligions,
        customer_reviews: customerReviews,
        rank_target: rankTarget,
        timeframe_months: timeframe,
        blogs_per_week: blogsPerWeek,
      })

      // 2. Save pillar keywords (creates session)
      const pillarMap = {}
      pillars.forEach(p => {
        pillarMap[typeof p === "string" ? p : p.keyword || p] = globalSupports
      })

      const res = await apiCall(`/api/ki/${projectId}/input`, "POST", {
        pillars: pillars.map(p => typeof p === "string" ? p : p.keyword || p),
        supporting: globalSupports,
        pillar_support_map: pillarMap,
        customer_url: websiteUrl,
        competitor_urls: competitorUrls,
        intent_focus: intentFocus,
        business_intent: intentFocus,
      })

      const sessionId = res?.session_id
      if (sessionId) {
        ctx.setStep(1, {
          pillars: pillars.map(p => typeof p === "string" ? p : p.keyword || p),
          supports: globalSupports,
          customerUrl: websiteUrl,
          competitorUrls,
          intent: intentFocus,
        })
        ctx.flush(projectId)
      }

      notify("Setup saved successfully", "success")
      onComplete({ sessionId })
    } catch (e) {
      notify(`Save failed: ${e.message}`, "error")
    }
    setSubmitting(false)
  }

  if (profileLoading) {
    return (
      <div style={{ textAlign: "center", padding: 40 }}>
        <Spinner />
        <div style={{ fontSize: 13, marginTop: 10, color: T.textSoft }}>Loading profile…</div>
      </div>
    )
  }

  return (
    <div>
      <Card style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>
          Project Setup
        </div>
        <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 16 }}>
          Configure your business profile, target audience, and pillar keywords. All settings in one place.
        </div>

        {/* ── Two-column layout ──────────────────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
          {/* LEFT COLUMN — Business Profile */}
          <div>
            <SectionTitle>🏢 Business Profile</SectionTitle>

            <label style={{ fontSize: 12, color: T.textSoft }}>Website URL</label>
            <input value={websiteUrl} onChange={e => setWebsiteUrl(e.target.value)}
              placeholder="https://yourdomain.com" style={{ ...inStyle, marginBottom: 8 }} />

            <label style={{ fontSize: 12, color: T.textSoft }}>Business Type</label>
            <select value={businessType} onChange={e => setBusinessType(e.target.value)}
              style={{ ...inStyle, marginBottom: 8 }}>
              <option value="B2C">B2C — Direct to Consumer</option>
              <option value="B2B">B2B — Business to Business</option>
              <option value="D2C">D2C — Direct to Consumer (Brand)</option>
              <option value="SaaS">SaaS — Software as a Service</option>
              <option value="Local">Local Business</option>
              <option value="Ecommerce">E-Commerce</option>
            </select>

            <label style={{ fontSize: 12, color: T.textSoft }}>USP (Unique Selling Proposition)</label>
            <textarea value={usp} onChange={e => setUsp(e.target.value)}
              placeholder="What makes you unique?" rows={2}
              style={{ ...inStyle, marginBottom: 8, resize: "vertical" }} />

            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <label style={{ fontSize: 12, color: T.textSoft, flex: 1 }}>Products & Services</label>
              <Btn small variant="teal" disabled={crawling || !websiteUrl}
                onClick={async () => {
                  setCrawling(true)
                  try {
                    const res = await apiCall(`/api/ki/${projectId}/crawl-context`, "POST", {
                      customer_url: websiteUrl,
                      existing_pillars: pillars,
                    })
                    const found = (res?.products || []).map(p => typeof p === "string" ? p : p.name || String(p)).filter(Boolean)
                    if (found.length > 0) {
                      setProducts(prev => [...new Set([...prev, ...found])])
                      notify(`Found ${found.length} products from website`, "success")
                    } else {
                      notify("No products found on website", "warn")
                    }
                  } catch (e) { notify(`Crawl failed: ${e.message}`, "error") }
                  setCrawling(false)
                }}>
                {crawling ? <Spinner /> : "🔍 Crawl from Website"}
              </Btn>
            </div>
            <ChipInput items={products} setItems={setProducts}
              inputValue={productInput} setInputValue={setProductInput}
              placeholder="Add a product or service" />

            <SectionTitle style={{ marginTop: 16 }}>🔗 Competitor URLs</SectionTitle>
            <ChipInput items={competitorUrls} setItems={setCompetitorUrls}
              inputValue={competitorInput} setInputValue={setCompetitorInput}
              placeholder="https://competitor.com" />
          </div>

          {/* RIGHT COLUMN — Audience & Targeting */}
          <div>
            <SectionTitle>🎯 Target Audience</SectionTitle>

            {/* Business Locations */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <label style={{ fontSize: 12, color: T.textSoft, flex: 1 }}>
                📍 Business Location(s)
                {businessLocations.length > 0 && <span style={{ fontSize: 10, color: T.purple, marginLeft: 6 }}>Level: {DEPTH_LABELS[Math.min(businessLocationDepth, 3)]}</span>}
              </label>
              <AISuggestBtn projectId={projectId} type="business_regions"
                aiProvider={aiProvider}
                label={businessLocations.length === 0 ? "✨ AI Suggest" : `✨ Drill ${DEPTH_NEXT[Math.min(businessLocationDepth, 3)]}`}
                context={{ depth: businessLocationDepth, current: businessLocations }}
                onResult={items => {
                  const names = items.map(x => typeof x === 'string' ? x : x.name || String(x))
                  setBusinessLocations(prev => [...new Set([...prev, ...names])])
                  setBusinessLocationDepth(d => d + 1)
                }} />
            </div>
            <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 4 }}>Where your business operates from (origin/authority signals)</div>
            <ChipInput items={businessLocations} setItems={v => { setBusinessLocations(v); if (v.length === 0) setBusinessLocationDepth(0) }}
              inputValue={businessLocationInput} setInputValue={setBusinessLocationInput}
              placeholder="Kerala, Tamil Nadu…" />

            {/* Target Locations */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, marginTop: 10 }}>
              <label style={{ fontSize: 12, color: T.textSoft, flex: 1 }}>
                🎯 Target Location(s)
                {targetLocations.length > 0 && <span style={{ fontSize: 10, color: T.purple, marginLeft: 6 }}>Level: {DEPTH_LABELS[Math.min(targetLocationDepth, 3)]}</span>}
              </label>
              <AISuggestBtn projectId={projectId} type="regions"
                aiProvider={aiProvider}
                label={targetLocations.length === 0 ? "✨ AI Suggest" : `✨ Drill ${DEPTH_NEXT[Math.min(targetLocationDepth, 3)]}`}
                context={{ depth: targetLocationDepth, current: targetLocations }}
                onResult={items => {
                  const names = items.map(x => typeof x === 'string' ? x : x.name || String(x))
                  setTargetLocations(prev => [...new Set([...prev, ...names])])
                  setTargetLocationDepth(d => d + 1)
                }} />
            </div>
            <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 4 }}>Where your customers are (geo-targeted keywords)</div>
            <ChipInput items={targetLocations} setItems={v => { setTargetLocations(v); if (v.length === 0) setTargetLocationDepth(0) }}
              inputValue={locationInput} setInputValue={setLocationInput}
              placeholder="India, USA, UK…" />

            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, marginTop: 10 }}>
              <label style={{ fontSize: 12, color: T.textSoft, flex: 1 }}>Languages</label>
              <AISuggestBtn projectId={projectId} type="languages"
                aiProvider={aiProvider}
                context={{
                  locations: targetLocations,
                  business_locations: businessLocations,
                  business_type: businessType,
                  products: products,
                }}
                onResult={items => {
                  const names = items.map(x => typeof x === 'string' ? x : x.name || String(x))
                  setTargetLanguages(prev => {
                    const existing = prev.map(l => l.toLowerCase())
                    const newItems = names.filter(n => !existing.includes(n.toLowerCase()))
                    return [...prev, ...newItems]
                  })
                }} />
            </div>
            <ChipInput items={targetLanguages} setItems={setTargetLanguages}
              inputValue={languageInput} setInputValue={setLanguageInput}
              placeholder="English, Hindi…" />

            <label style={{ fontSize: 12, color: T.textSoft, marginTop: 10, display: "block" }}>Cultural Context</label>
            <ChipInput items={targetReligions} setItems={setTargetReligions}
              inputValue={religionInput} setInputValue={setReligionInput}
              placeholder="General, Hindu, Muslim…" />

            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, marginTop: 10 }}>
              <label style={{ fontSize: 12, color: T.textSoft, flex: 1 }}>
                Target Audiences
                {personas.length === 0 && (
                  <span style={{ fontSize: 10, color: T.amber, marginLeft: 6 }}>Add at least 1 to enable AI Suggest</span>
                )}
              </label>
              <AISuggestBtn projectId={projectId} type="personas"
                aiProvider={aiProvider}
                disabled={personas.length === 0}
                label={personas.length === 0 ? "✨ AI Suggest" : "✨ Expand Audiences"}
                context={{
                  business_type: businessType,
                  products: products,
                  pillars: pillars,
                  personas: personas,
                  locations: targetLocations,
                  website_url: websiteUrl,
                  usp,
                  industry: profile?.industry || "",
                }}
                onResult={items => setPersonas(prev => [...new Set([...prev, ...items.map(x => typeof x === 'string' ? x : x.audience || x.name || String(x))])])} />
            </div>
            <ChipInput items={personas} setItems={setPersonas}
              inputValue={personaInput} setInputValue={setPersonaInput}
              placeholder="Home cooks, Restaurant chefs…" />

            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, marginTop: 10 }}>
              <label style={{ fontSize: 12, color: T.textSoft, flex: 1 }}>Customer Reviews</label>
              <AISuggestBtn projectId={projectId} type="reviews"
                aiProvider={aiProvider}
                onResult={items => { const strs = items.map(x => typeof x === 'string' ? x : x.review || String(x)); setCustomerReviews(prev => prev ? prev + "\n" + strs.join("\n") : strs.join("\n")); }} />
            </div>
            <textarea value={customerReviews} onChange={e => setCustomerReviews(e.target.value)}
              placeholder="Paste real customer reviews or generate samples…" rows={3}
              style={{ ...inStyle, resize: "vertical" }} />
          </div>
        </div>

        {/* ── Pillar Keywords ────────────────────────────────────────────── */}
        <SectionTitle>🎯 Pillar Keywords</SectionTitle>
        <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 8 }}>
          These are your main topic areas. Each pillar will be expanded into clusters of keywords.
        </div>

        {pillarBank.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 4 }}>Quick add from existing:</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {pillarBank.map(p => (
                <Btn key={p} small onClick={() => {
                  if (!pillars.includes(p)) setPillars(prev => [...prev, p])
                }} style={{ fontSize: 10 }}>{p}</Btn>
              ))}
            </div>
          </div>
        )}

        <ChipInput items={pillars} setItems={setPillars}
          inputValue={pillarInput} setInputValue={setPillarInput}
          placeholder="Enter a pillar keyword (e.g., turmeric, clove)" />

        <SectionTitle>📎 Supporting Keywords (Global)</SectionTitle>
        <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 8 }}>
          These keywords will be used across all pillars to guide discovery.
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <label style={{ fontSize: 12, color: T.textSoft, flex: 1 }}>AI Suggest</label>
          <AISuggestBtn projectId={projectId} type="supporting"
            aiProvider={aiProvider}
            context={{
              business_type: businessType,
              industry: profile?.industry || "",
              products: products,
              pillars: pillars,
              personas: personas,
              locations: targetLocations,
              business_locations: businessLocations,
              languages: targetLanguages,
              intent: intentFocus,
            }}
            onResult={items => setGlobalSupports(prev => [...new Set([...prev, ...items.map(x => typeof x === 'string' ? x : x.keyword || String(x))])])} />
        </div>
        <ChipInput items={globalSupports} setItems={setGlobalSupports}
          inputValue={supportInput} setInputValue={setSupportInput}
          placeholder="brand name, product type…" />

        <SectionTitle>🧭 Business Intent Focus</SectionTitle>
        <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 6 }}>Select all that apply</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
          {INTENT_OPTIONS.map(opt => {
            const selected = intentFocus.includes(opt.value)
            return (
              <label key={opt.value} style={{
                display: "flex", alignItems: "center", gap: 4, padding: "4px 10px",
                borderRadius: 8, fontSize: 11, cursor: "pointer",
                background: selected ? T.purpleLight : T.grayLight,
                border: `1px solid ${selected ? T.purple : T.border}`,
              }}>
                <input type="checkbox" value={opt.value}
                  checked={selected}
                  onChange={e => {
                    if (e.target.checked) setIntentFocus(prev => [...prev, opt.value])
                    else setIntentFocus(prev => prev.filter(v => v !== opt.value))
                  }}
                  style={{ display: "none" }} />
                {selected ? "✓ " : ""}{opt.label}
              </label>
            )
          })}
        </div>

        {/* ── Strategy Settings ──────────────────────────────────────────── */}
        <SectionTitle>⚙️ Strategy Settings</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          <div>
            <label style={{ fontSize: 12, color: T.textSoft }}>Rank Target</label>
            <select value={rankTarget} onChange={e => setRankTarget(e.target.value)} style={inStyle}>
              <option value="top 3">Top 3</option>
              <option value="top 5">Top 5</option>
              <option value="top 10">Top 10</option>
              <option value="top 20">Top 20</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, color: T.textSoft }}>Timeframe (months)</label>
            <input type="number" min={1} max={24} value={timeframe}
              onChange={e => setTimeframe(parseInt(e.target.value) || 6)} style={inStyle} />
          </div>
          <div>
            <label style={{ fontSize: 12, color: T.textSoft }}>Blogs/Week</label>
            <input type="number" min={1} max={20} value={blogsPerWeek}
              onChange={e => setBlogsPerWeek(parseInt(e.target.value) || 3)} style={inStyle} />
          </div>
        </div>
      </Card>

      {/* ── Save Button ──────────────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
        <Btn variant="primary" onClick={handleSave} disabled={submitting || pillars.length === 0}>
          {submitting ? <><Spinner /> Saving…</> : "Save & Continue to Discovery →"}
        </Btn>
      </div>
    </div>
  )
}
