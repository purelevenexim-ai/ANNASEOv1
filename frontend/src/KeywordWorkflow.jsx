// ============================================================================
// ANNASEO — Keyword Workflow  (src/KeywordWorkflow.jsx)
// 7-step linear wizard:
//   1. Input (Method 1)  → 2. Research (Method 2) → 3. Unified Review
//   → 4. AI Review → 5. Pipeline → 6. Clusters → 7. Calendar Handoff
// ============================================================================

import { useState, useEffect, useRef, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNotification } from "./store/notification"
import useDebug from "./store/debug"
import DebugPanel from "./components/DebugPanel"
import PillarConfirmation from "./components/PillarConfirmation"
import UniverseConfirmation from "./components/UniverseConfirmation"
import KeywordTreeConfirmation from "./components/KeywordTreeConfirmation"
import BlogSuggestionsConfirmation from "./components/BlogSuggestionsConfirmation"
import FinalStrategyConfirmation from "./components/FinalStrategyConfirmation"
import ContentStrategy from "./components/ContentStrategy"

const API = import.meta.env.VITE_API_URL || ""

// Debug-aware fetch helper
async function fetchDebug(url, opts = {}) {
  const start = Date.now()
  try {
    const res = await fetch(url, opts)
    const parsed = await res.json().catch(() => ({}))
    const duration = Date.now() - start
    const debugStore = useDebug.getState()

    if (debugStore.enabled) {
      const reqBody = opts.body ? JSON.parse(opts.body) : null
      debugStore.pushLog({
        method: opts.method || "GET",
        path: url.replace(API, ""),
        status: res.status,
        ok: res.ok,
        duration,
        reqBody: reqBody ? JSON.stringify(reqBody).slice(0, 100) : null,
        resSnippet: JSON.stringify(parsed).slice(0, 100),
        ts: Date.now(),
      })
    }

    return { res, parsed }
  } catch (e) {
    const duration = Date.now() - start
    const debugStore = useDebug.getState()
    if (debugStore.enabled) {
      debugStore.pushLog({
        method: opts.method || "GET",
        path: url.replace(API, ""),
        error: e.message,
        duration,
        ts: Date.now(),
      })
    }
    throw e
  }
}

async function apiCall(path, method = "GET", body = null) {
  const token = localStorage.getItem("annaseo_token")
  const url = `${API}${path}`
  const start = Date.now()
  try {
    const { res, parsed: data } = await fetchDebug(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
    const duration = Date.now() - start
    const ok = !!res.ok

    if (!ok) {
      const msg = data?.detail || data?.error || `API ${method} ${path} failed (${res.status})`
      throw new Error(msg)
    }
    return data
  } catch (e) {
    const duration = Date.now() - start
    // fetchDebug already logs errors when debug is enabled
    throw e
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// DESIGN TOKENS
// ─────────────────────────────────────────────────────────────────────────────
const T = {
  purple:     "#7c3aed",
  purpleLight:"#f5f3ff",
  purpleDark: "#5b21b6",
  teal:       "#0d9488",
  tealLight:  "#f0fdfa",
  amber:      "#d97706",
  amberLight: "#fffbeb",
  red:        "#dc2626",
  green:      "#16a34a",
  greenLight: "#f0fdf4",
  gray:       "#6b7280",
  grayLight:  "#f9fafb",
  border:     "rgba(0,0,0,0.09)",
  text:       "#111827",
  textSoft:   "#6b7280",
}

const STEPS = [
  { label: "Input",    desc: "Method 1" },
  { label: "Strategy", desc: "AI model" },
  { label: "Research", desc: "Method 2" },
  { label: "Review",   desc: "Unify" },
  { label: "AI Check", desc: "3-stage" },
  { label: "Pipeline", desc: "20-phase" },
  { label: "Clusters", desc: "Organize" },
  { label: "Calendar", desc: "Schedule" },
]

const INTENT_OPTIONS = [
  { value: "transactional", label: "Buy / Purchase" },
  { value: "informational", label: "Information / Learn" },
  { value: "commercial",    label: "Commercial Research" },
  { value: "local",         label: "Local / Near me" },
  { value: "comparison",    label: "Comparison / Review" },
]

const SOURCE_COLORS = {
  cross_multiply:    T.purple,
  site_crawl:        T.teal,
  template:          T.amber,
  research_autosuggest: "#0284c7",
  research_competitor_gap: "#dc2626",
  research_site_crawl: "#0d9488",
  strategy:          "#16a34a",
  // Research engine source colors (Task 6)
  "user":            "#10b981",      // green
  "google":          "#3b82f6",      // blue
  "ai_generated":    "#f59e0b",      // amber
}

// Intent badge colors for Step 3 (Task 6)
const intentBadgeColors = {
  "transactional":   "#ef4444",      // red
  "informational":   "#06b6d4",      // cyan
  "comparison":      "#8b5cf6",      // purple
  "commercial":      "#ec4899",      // pink
  "local":           "#eab308",      // yellow
}

function intentColor(intent) {
  return { transactional: T.teal, informational: T.purple, commercial: T.amber,
           local: "#0284c7", comparison: T.purpleDark, question: "#0891b2" }[intent] || T.gray
}

// Audience form constants (used in Business Profile section of Step 1)
const LOCATION_OPTIONS = [
  "global","india","south_india","kerala","malabar","wayanad",
  "kochi","kozhikode","thrissur","kottayam","tamil_nadu","national",
]
const RELIGION_OPTIONS = ["general","hindu","muslim","christian"]
const LANGUAGE_OPTIONS = ["english","malayalam","hindi","tamil","kannada","telugu","arabic"]
const BUSINESS_TYPES   = ["B2C","B2B","D2C","Service","Marketplace"]
const SEASONAL_PRESETS = ["Christmas","Onam","Eid","Diwali","Vishu","Easter","Ramadan","Holi"]

// ─────────────────────────────────────────────────────────────────────────────
// SHARED UI PRIMITIVES
// ─────────────────────────────────────────────────────────────────────────────

function Card({ children, style }) {
  return (
    <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 12,
                  padding: 20, ...style }}>
      {children}
    </div>
  )
}

function Btn({ children, onClick, variant = "default", disabled, small, style }) {
  const base = {
    padding: small ? "5px 12px" : "8px 18px",
    borderRadius: 8, fontSize: small ? 11 : 13, fontWeight: 500,
    cursor: disabled ? "not-allowed" : "pointer",
    border: "none", transition: "opacity 0.1s",
    opacity: disabled ? 0.5 : 1, ...style,
  }
  const variants = {
    primary: { background: T.purple, color: "#fff" },
    teal:    { background: T.teal,   color: "#fff" },
    danger:  { background: T.red,    color: "#fff" },
    default: { background: T.grayLight, color: T.text, border: `1px solid ${T.border}` },
  }
  return <button style={{ ...base, ...variants[variant] }} onClick={onClick} disabled={disabled}>{children}</button>
}

function Badge({ color, children }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 8px",
                   borderRadius: 99, fontSize: 10, fontWeight: 600,
                   background: color + "22", color }}>
      {children}
    </span>
  )
}

function Spinner() {
  return <span style={{ display: "inline-block", width: 14, height: 14,
                        border: `2px solid ${T.purple}44`, borderTopColor: T.purple,
                        borderRadius: "50%", animation: "spin 0.7s linear infinite" }}/>
}

// ─────────────────────────────────────────────────────────────────────────────
// PROGRESS BAR
// ─────────────────────────────────────────────────────────────────────────────

function ProgressBar({ step }) {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: 28, overflowX: "auto" }}>
      {STEPS.map((s, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", flex: i < STEPS.length - 1 ? 1 : "none" }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
            <div style={{
              width: 32, height: 32, borderRadius: "50%", display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: 13, fontWeight: 700,
              background: i < step ? T.teal : i === step ? T.purple : T.grayLight,
              color: i <= step ? "#fff" : T.gray,
              border: i === step ? `2px solid ${T.purpleDark}` : "2px solid transparent",
            }}>
              {i < step ? "✓" : i + 1}
            </div>
            <div style={{ fontSize: 10, color: i === step ? T.purple : T.gray,
                          fontWeight: i === step ? 600 : 400, marginTop: 4, whiteSpace: "nowrap" }}>
              {s.label}
            </div>
            <div style={{ fontSize: 9, color: T.textSoft, whiteSpace: "nowrap" }}>{s.desc}</div>
          </div>
          {i < STEPS.length - 1 && (
            <div style={{ flex: 1, height: 2, background: i < step ? T.teal : T.border,
                          margin: "0 4px", marginBottom: 24 }} />
          )}
        </div>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PILL TOGGLE — multi-select pill buttons used in Business Profile
// ─────────────────────────────────────────────────────────────────────────────

function PillToggle({ options, selected, onChange, color }) {
  const c = color || T.purple
  return (
    <div style={{ display:"flex", flexWrap:"wrap", gap:5 }}>
      {options.map(v => {
        const active = selected.includes(v)
        return (
          <button key={v} onClick={() => onChange(active ? selected.filter(x=>x!==v) : [...selected, v])}
            style={{ padding:"3px 9px", borderRadius:99, fontSize:10, cursor:"pointer", border:"none",
              background: active ? c : T.grayLight, color: active ? "#fff" : T.gray }}>
            {v}
          </button>
        )
      })}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// INLINE CHIPS INPUT — chips + add button
// ─────────────────────────────────────────────────────────────────────────────

function InlineChips({ label, value, onChange, placeholder, inStyle }) {
  const [inp, setInp] = useState("")
  const add = () => { const v = inp.trim(); if(v) { onChange([...value, v]); setInp("") } }
  return (
    <div style={{ marginBottom:12 }}>
      {label && <label style={{ fontSize:11, fontWeight:500, color:T.gray, display:"block", marginBottom:4 }}>{label}</label>}
      <div style={{ display:"flex", flexWrap:"wrap", gap:4, marginBottom:5 }}>
        {value.map((v,i) => (
          <span key={i} style={{ display:"inline-flex", alignItems:"center", gap:3,
            background:T.purpleLight, color:T.purpleDark, padding:"2px 8px", borderRadius:99, fontSize:11 }}>
            {v}
            <button onClick={() => onChange(value.filter((_,j)=>j!==i))}
              style={{ background:"none", border:"none", cursor:"pointer", fontSize:12, color:T.purpleDark, padding:0, lineHeight:1 }}>×</button>
          </span>
        ))}
      </div>
      <div style={{ display:"flex", gap:5 }}>
        <input value={inp} onChange={e=>setInp(e.target.value)} onKeyDown={e=>e.key==="Enter"&&add()}
          placeholder={placeholder || "Type and press Enter"}
          style={{ ...(inStyle||{}), flex:1, fontSize:12, padding:"5px 9px" }} />
        <Btn small onClick={add}>Add</Btn>
      </div>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// StrategyPanel removed — strategy UI moved to the dedicated Strategy page.

// ─────────────────────────────────────────────────────────────────────────────
// STEP 1 — INPUT (Method 1)
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// STEP 1 — INPUT (Method 1) - Smart List
// ─────────────────────────────────────────────────────────────────────────────

function StepInput({ projectId, onComplete, setPage }) {
  const [globalSupports, setGlobalSupports] = useState([])
  const [supportInput, setSupportInput] = useState('')
  const [pillars, setPillars] = useState([])
  const [pillarInput, setPillarInput] = useState('')
  const [pillarBank, setPillarBank] = useState([])
  const [intentFocus, setIntentFocus] = useState('transactional')
  const [customerUrl, setCustomerUrl] = useState('')
  const [competitorUrls, setCompetitorUrls] = useState([])
  const [competitorInput, setCompetitorInput] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)
  // Task 6: Business intent fields for research engine (now multi-select)
  const [businessIntent, setBusinessIntent] = useState(["ecommerce"])
  const [targetAudience, setTargetAudience] = useState("")
  const [geographicFocus, setGeographicFocus] = useState("India")
  const inStyle = { width: '100%', padding: '7px 10px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, boxSizing: 'border-box' }

  const { data: existingPillars } = useQuery({
    queryKey: ['ki-pillars', projectId],
    queryFn: () => apiCall(`/api/ki/${projectId}/pillars`),
    enabled: !!projectId,
    retry: false,
  })

  const { data: latestSession } = useQuery({
    queryKey: ['ki-latest-session', projectId],
    queryFn: () => apiCall(`/api/ki/${projectId}/latest-session`),
    enabled: !!projectId,
    retry: false,
  })

  useEffect(() => {
    if (existingPillars && existingPillars.pillars) {
      const bank = existingPillars.pillars.map(p => ({
        keyword: p.keyword || '',
        intent: p.intent || 'transactional',
        supports: Array.isArray(p.supports) ? p.supports : [],
      }))
      setPillarBank(bank)
    }
  }, [existingPillars])

  useEffect(() => {
    if (!latestSession) return
    if (Array.isArray(latestSession.supporting)) setGlobalSupports(latestSession.supporting)
    if (latestSession.pillar_support_map) {
      const mapped = Object.entries(latestSession.pillar_support_map).map(([k,v]) => ({
        keyword: k,
        intent: latestSession.intent_focus || 'transactional',
        supports: Array.isArray(v) ? v : [],
      }))
      setPillars(mapped)
    }
    if (latestSession.intent_focus) setIntentFocus(latestSession.intent_focus)
    if (latestSession.customer_url) setCustomerUrl(latestSession.customer_url)
    if (Array.isArray(latestSession.competitor_urls)) setCompetitorUrls(latestSession.competitor_urls)
    // Task 6: Load business intent fields (handle both string and array)
    if (latestSession.business_intent) {
      const bi = latestSession.business_intent
      setBusinessIntent(Array.isArray(bi) ? bi : [bi])
    }
    if (latestSession.target_audience) setTargetAudience(latestSession.target_audience)
    if (latestSession.geographic_focus) setGeographicFocus(latestSession.geographic_focus)
  }, [latestSession])

  const addSupport = () => {
    const kw = supportInput.trim()
    if (!kw) return
    if (globalSupports.some(s => s.toLowerCase() === kw.toLowerCase())) {
      setMessage(`Support '${kw}' already exists`)
      return
    }
    const nextSupports = [...globalSupports, kw]
    setGlobalSupports(nextSupports)
    setPillars(prev => prev.map(p => ({ ...p, supports: Array.from(new Set([...(p.supports||[]), kw])) })))
    setSupportInput('')
    setMessage(`Added support '${kw}' to all pillars.`)
  }

  const removeSupport = kw => {
    setGlobalSupports(prev => prev.filter(item => item !== kw))
    setPillars(prev => prev.map(p => ({ ...p, supports: (p.supports || []).filter(item => item !== kw) })))
  }

  const addPillar = () => {
    const kw = pillarInput.trim()
    if (!kw) return
    const exists = pillars.some(p => p.keyword.toLowerCase() === kw.toLowerCase())
    if (exists) {
      setMessage(`Pillar '${kw}' already exists (focus).`)
      return
    }
    const fromBank = pillarBank.find(p => p.keyword.toLowerCase() === kw.toLowerCase())
    const candidate = fromBank ? { ...fromBank, supports: Array.from(new Set([...(fromBank.supports||[]), ...globalSupports])) } : { keyword: kw, intent: intentFocus, supports: [...globalSupports] }
    setPillars(prev => [...prev, candidate])
    setPillarInput('')
    setMessage(`Pillar '${kw}' added with auto-supports.`)
  }

  const removePillar = kw => setPillars(prev => prev.filter(p => p.keyword !== kw))
  const updatePillar = (kw, patch) => setPillars(prev => prev.map(p => p.keyword === kw ? { ...p, ...patch } : p))

  const addCompetitor = () => {
    const v = competitorInput.trim()
    if (v && !competitorUrls.includes(v)) { setCompetitorUrls(prev => [...prev, v]); setCompetitorInput('') }
  }

  const saveAll = async () => {
    if (!pillars.length) { setError('Add at least one pillar to continue'); return null }
    setLoading(true); setError('')
    try {
      const pillarSupportMap = pillars.reduce((acc, p) => { acc[p.keyword] = p.supports || []; return acc }, {})
      const r = await apiCall(`/api/ki/${projectId}/input`, 'POST', {
        pillars: pillars.map((p,i) => ({ keyword: p.keyword, intent: p.intent, priority: i+1 })),
        supporting: globalSupports,
        pillar_support_map: pillarSupportMap,
        intent_focus: intentFocus,
        customer_url: customerUrl,
        competitor_urls: competitorUrls,
        // Task 6: Include business intent fields
        business_intent: businessIntent,
        target_audience: targetAudience,
        geographic_focus: geographicFocus,
      })
      setLoading(false)
      if (r?.session_id) {
        setSaved(true)
        setTimeout(() => setSaved(false), 2200)
        return { sessionId: r.session_id, pillars, supports: globalSupports, customerUrl, competitorUrls, businessIntent, targetAudience, geographicFocus }
      }
      setError(typeof r?.detail === 'string' ? r.detail : Array.isArray(r?.detail) ? r.detail.map(e=>e.msg||String(e)).join('; ') : 'Save failed')
      return null
    } catch(e) {
      setLoading(false)
      setError(String(e))
      return null
    }
  }

  const goToStrategy = async () => {
    const result = await saveAll(); if (result && onComplete) onComplete(result)
  }

  if (!projectId) return <div style={{ color: T.gray, fontSize: 13 }}>Select a project first.</div>

  return (
    <div>
      <Card style={{ marginBottom: 16, padding: 18 }}>
        <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>Step 1 — Smart List</div>
            <div style={{ fontSize: 12, color: T.textSoft }}>Global supports auto-apply to each pillar by default.</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Btn variant='default' onClick={saveAll} disabled={loading}>{loading ? 'Saving...' : saved ? '✓ Saved' : 'Save Draft'}</Btn>
            <Btn variant='teal' onClick={goToStrategy} disabled={loading}>Step 2 — Strategy AI Model →</Btn>
          </div>
        </div>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 8 }}>Global Supporting Keywords</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {globalSupports.map(s => (
              <span key={s} style={{ background: T.grayLight, borderRadius: 999, padding: '5px 8px', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                {s} <button style={{ border:'none', background:'transparent', cursor:'pointer' }} onClick={() => removeSupport(s)}>✕</button>
              </span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input value={supportInput} onChange={e => setSupportInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && addSupport()} placeholder='Add support (e.g., tour)' style={{ ...inStyle, flex: 1 }} />
            <Btn small onClick={addSupport}>+ Add Support</Btn>
          </div>
        </div>
        <div style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <input value={pillarInput} onChange={e => setPillarInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && addPillar()} placeholder='Type pillar (e.g., Munnar)' style={{ ...inStyle, width: 240 }} />
          <select value={intentFocus} onChange={e => setIntentFocus(e.target.value)} style={{ ...inStyle, width: 180 }}>
            {INTENT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <Btn onClick={addPillar}>+ Add</Btn>
        </div>
        <div style={{ overflowX: 'auto', marginBottom: 14 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: `1px solid ${T.border}` }}>
                <th style={{ padding: '8px' }}>Pillar</th>
                <th style={{ padding: '8px' }}>Intent</th>
                <th style={{ padding: '8px' }}>Supports</th>
                <th style={{ padding: '8px' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {pillars.length === 0 && (<tr><td colSpan={4} style={{ padding: '8px', color: T.gray }}>No pillars yet.</td></tr>)}
              {pillars.map((p, i) => (
                <tr key={p.keyword + i} style={{ borderBottom: `1px solid ${T.grayLight}` }}>
                  <td style={{ padding: '8px' }}>{p.keyword}</td>
                  <td style={{ padding: '8px' }}>
                    <select value={p.intent || intentFocus} onChange={e => updatePillar(p.keyword, { intent: e.target.value })} style={{ ...inStyle, width: '100%' }}>
                      {INTENT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </td>
                  <td style={{ padding: '8px', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {(p.supports || []).map(s => (
                      <span key={s} style={{ background: T.grayLight, borderRadius: 999, padding: '4px 8px', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                        {s} <button style={{ border:'none', background:'transparent', cursor:'pointer' }} onClick={() => updatePillar(p.keyword, { supports: (p.supports||[]).filter(x => x !== s) })}>✕</button>
                      </span>
                    ))}
                  </td>
                  <td style={{ padding: '8px' }}><Btn small variant='danger' onClick={() => removePillar(p.keyword)}>🗑️</Btn></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Website & Competitor URLs */}
        <div style={{ background: T.grayLight, borderRadius: 12, padding: 12, marginBottom: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Your Website & Competitors (for Research Engine)</div>
          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 11, color: T.textSoft, display: 'block', marginBottom: 4 }}>Your Website URL</label>
            <input
              value={customerUrl}
              onChange={e => setCustomerUrl(e.target.value)}
              placeholder="https://yoursite.com"
              style={{ width: '100%', padding: '6px 10px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13, boxSizing: 'border-box' }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11, color: T.textSoft, display: 'block', marginBottom: 4 }}>Competitor URLs</label>
            <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
              <input
                value={competitorInput}
                onChange={e => setCompetitorInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addCompetitor()}
                placeholder="https://competitor.com"
                style={{ flex: 1, padding: '6px 10px', borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13 }}
              />
              <Btn small variant='teal' onClick={addCompetitor}>Add</Btn>
            </div>
            {(competitorUrls || []).length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {(competitorUrls || []).map(url => (
                  <span key={url} style={{ background: T.white, border: `1px solid ${T.border}`, borderRadius: 8, padding: '2px 8px', fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
                    {url}
                    <button onClick={() => setCompetitorUrls(prev => prev.filter(u => u !== url))} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: T.red, fontSize: 13, lineHeight: 1 }}>✕</button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Task 6: Business Intent Questions */}
        <div style={{ background: T.purpleLight, borderRadius: 12, padding: 12, marginBottom: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Business Intent (Select Multiple)</div>
          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 11, color: T.textSoft, display: 'block', marginBottom: 6 }}>Select all applicable business intents:</label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {[
                { value: 'ecommerce', label: 'E-commerce (selling products)' },
                { value: 'content_blog', label: 'Content Blog (informational)' },
                { value: 'supplier', label: 'B2B / Supplier' },
                { value: 'mixed', label: 'Mixed / General' },
              ].map(intent => (
                <label key={intent.value} style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', fontSize: 12, gap: 6 }}>
                  <input
                    type="checkbox"
                    checked={businessIntent.includes(intent.value)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setBusinessIntent([...businessIntent.filter(b => b !== 'mixed'), intent.value])
                      } else {
                        const updated = businessIntent.filter(b => b !== intent.value)
                        setBusinessIntent(updated.length === 0 ? ['mixed'] : updated)
                      }
                    }}
                    style={{ width: 16, height: 16, cursor: 'pointer' }}
                  />
                  {intent.label}
                </label>
              ))}
            </div>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 11, color: T.textSoft, display: 'block', marginBottom: 4 }}>Target audience (optional)</label>
            <input
              value={targetAudience}
              onChange={e => setTargetAudience(e.target.value)}
              placeholder="e.g., health-conscious, budget-buyers, enterprise"
              style={{ ...inStyle }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11, color: T.textSoft, display: 'block', marginBottom: 4 }}>Geographic focus</label>
            <select value={geographicFocus} onChange={e => setGeographicFocus(e.target.value)} style={{ ...inStyle }}>
              <option value="India">India</option>
              <option value="global">Global</option>
              <option value="north_india">North India</option>
              <option value="south_india">South India</option>
              <option value="usa">USA</option>
              <option value="uk">UK</option>
              <option value="eu">Europe</option>
            </select>
          </div>
        </div>

        <div style={{ background: T.grayLight, borderRadius: 12, padding: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Reuse Recent Pillars</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {pillarBank.length ? pillarBank.slice(0, 12).map(b => (
              <button key={b.keyword} onClick={() => { setPillarInput(b.keyword); setIntentFocus(b.intent || 'transactional'); addPillar() }} style={{ border: `1px solid ${T.border}`, borderRadius: 8, padding: '4px 8px', cursor: 'pointer' }}>[+] {b.keyword}</button>
            )) : <span style={{ color: T.gray }}>No recent pillars</span>}
          </div>
        </div>
        {message && <div style={{ marginTop: 10, color: T.teal }}>{message}</div>}
        {error && <div style={{ marginTop: 10, color: T.red }}>{error}</div>}
      </Card>
    </div>
  )
}
// STEP 2 — RESEARCH (Method 2)
// ─────────────────────────────────────────────────────────────────────────────

function StepStrategy({ projectId, sessionId, customerUrl, competitorUrls, businessIntent, onComplete, onBack }) {
  const [jobId, setJobId] = useState(null)
  const [status, setStatus] = useState(null)
  const [error, setError] = useState("")
  const [pollId, setPollId] = useState(null)

  // Strategy form state
  const [showForm, setShowForm] = useState(true)
  const [formData, setFormData] = useState({
    business_type: 'B2C',
    usp: '',
    products: [],
    target_locations: [],
    target_demographics: [],
    languages_supported: [],
    customer_review_areas: [],
    seasonal_events: []
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!jobId || status !== "running") return
    const interval = setInterval(async () => {
      try {
        const r = await apiCall(`/api/jobs/${jobId}`)
        if (r.status === "completed") {
          setStatus("completed")
          clearInterval(interval)
          // Extract strategy_context from result_payload
          const strategyContext = r.result_payload?.strategy_context || r.result_payload?.data?.strategy_context
          if (onComplete) onComplete({ jobId, strategy_context: strategyContext })
        } else if (r.status === "failed") {
          setStatus("failed")
          setError(r.error_message || r.error || "Strategy processing failed")
          clearInterval(interval)
        }
      } catch (e) {
        setError(String(e))
        clearInterval(interval)
      }
    }, 1800)
    setPollId(interval)
    return () => clearInterval(interval)
  }, [jobId, status, projectId, onComplete])

  const handleInputChange = (field, value) => {
    setFormData(prev => ({...prev, [field]: value}))
  }

  const handleArrayInput = (field, value) => {
    // Parse comma-separated values
    const items = value.split(',').map(s => s.trim()).filter(s => s)
    handleInputChange(field, items)
  }

  const handleSaveStrategy = async () => {
    setSaving(true)
    setError("")
    try {
      const response = await apiCall(`/api/ki/${projectId}/strategy-input`, "POST", {
        session_id: sessionId,
        ...formData
      })
      if (response.success) {
        setShowForm(false)
        // Now run strategy processing with collected data
        startStrategy()
      } else {
        setError(response.error || "Failed to save strategy input")
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const startStrategy = async () => {
    setError("")
    try {
      setStatus("running")
      const response = await apiCall(`/api/ki/${projectId}/run`, "POST", {
        execution_mode: "single_call",
        session_id: sessionId,
        customer_url: customerUrl,
        competitor_urls: competitorUrls || [],
        business_intent: businessIntent
      })
      if (response.job_id) {
        setJobId(response.job_id)
        setStatus("running")
      } else {
        setStatus("failed")
        setError(typeof response?.detail === 'string' ? response.detail : Array.isArray(response?.detail) ? response.detail.map(e=>e.msg||String(e)).join('; ') : "Failed to start strategy processing")
      }
    } catch (e) {
      setStatus("failed")
      setError(String(e))
    }
  }

  // Render form if not saved yet
  if (showForm) {
    return (
      <Card>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>Step 2: Business Strategy Input</div>
        <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 14 }}>
          Tell us about your business strategy. This helps us better understand your context for keyword research.
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
            Business Type:
          </label>
          <select
            value={formData.business_type}
            onChange={e => handleInputChange('business_type', e.target.value)}
            style={{
              width: "100%",
              padding: "8px 12px",
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontSize: 13,
              fontFamily: "inherit"
            }}
          >
            <option value="B2C">B2C (Direct to Consumer)</option>
            <option value="B2B">B2B (Business to Business)</option>
            <option value="D2C">D2C (Direct to Consumer E-commerce)</option>
            <option value="Service">Service Provider</option>
            <option value="Marketplace">Marketplace/Multi-vendor</option>
          </select>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
            USP (Unique Selling Proposition):
          </label>
          <input
            type="text"
            value={formData.usp}
            onChange={e => handleInputChange('usp', e.target.value)}
            placeholder="e.g., organic, handcrafted, premium quality..."
            style={{
              width: "100%",
              padding: "8px 12px",
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontSize: 13,
              fontFamily: "inherit",
              boxSizing: "border-box"
            }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
            Products/Services (comma-separated):
          </label>
          <textarea
            value={formData.products.join(', ')}
            onChange={e => handleArrayInput('products', e.target.value)}
            placeholder="Cinnamon, Cardamom, Cloves"
            style={{
              width: "100%",
              padding: "8px 12px",
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontSize: 13,
              fontFamily: "inherit",
              minHeight: "80px",
              boxSizing: "border-box"
            }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
            Target Locations (comma-separated):
          </label>
          <textarea
            value={formData.target_locations.join(', ')}
            onChange={e => handleArrayInput('target_locations', e.target.value)}
            placeholder="USA, UK, Canada"
            style={{
              width: "100%",
              padding: "8px 12px",
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontSize: 13,
              fontFamily: "inherit",
              minHeight: "80px",
              boxSizing: "border-box"
            }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
            Target Demographics (comma-separated):
          </label>
          <textarea
            value={formData.target_demographics.join(', ')}
            onChange={e => handleArrayInput('target_demographics', e.target.value)}
            placeholder="health-conscious, eco-friendly, budget-conscious"
            style={{
              width: "100%",
              padding: "8px 12px",
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontSize: 13,
              fontFamily: "inherit",
              minHeight: "80px",
              boxSizing: "border-box"
            }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
            Languages Supported:
          </label>
          <textarea
            value={formData.languages_supported.join(', ')}
            onChange={e => handleArrayInput('languages_supported', e.target.value)}
            placeholder="English, Spanish, French"
            style={{
              width: "100%",
              padding: "8px 12px",
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontSize: 13,
              fontFamily: "inherit",
              minHeight: "60px",
              boxSizing: "border-box"
            }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
            Customer Review Areas (optional, comma-separated):
          </label>
          <textarea
            value={formData.customer_review_areas.join(', ')}
            onChange={e => handleArrayInput('customer_review_areas', e.target.value)}
            placeholder="Quality, Authenticity, Taste, Packaging"
            style={{
              width: "100%",
              padding: "8px 12px",
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontSize: 13,
              fontFamily: "inherit",
              minHeight: "60px",
              boxSizing: "border-box"
            }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
            Seasonal Events (optional, comma-separated):
          </label>
          <textarea
            value={formData.seasonal_events.join(', ')}
            onChange={e => handleArrayInput('seasonal_events', e.target.value)}
            placeholder="Christmas, Thanksgiving, Diwali"
            style={{
              width: "100%",
              padding: "8px 12px",
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              fontSize: 13,
              fontFamily: "inherit",
              minHeight: "60px",
              boxSizing: "border-box"
            }}
          />
        </div>

        {error && <div style={{ color: T.red, fontSize: 12, marginBottom: 12 }}>{error}</div>}

        <div style={{ display: "flex", gap: 8 }}>
          <Btn onClick={onBack}>← Back</Btn>
          <Btn variant='teal' onClick={handleSaveStrategy} disabled={saving}>
            {saving ? 'Saving...' : 'Save Strategy & Continue'}
          </Btn>
          <Btn variant="default" onClick={() => onComplete({})} style={{ marginLeft: "auto" }}>
            Skip to Research →
          </Btn>
        </div>
      </Card>
    )
  }

  // Render processing UI after form is saved
  return (
    <Card>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>Step 2 — Strategy Processing</div>
      <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 14 }}>
        Processing your business strategy. This step analyzes your inputs and prepares them for keyword discovery.
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <Btn onClick={onBack}>← Back</Btn>
        <Btn variant="teal" disabled={status === "running"}>
          {status === "running" ? "Processing…" : status === "completed" ? "Completed ✓" : "Run Strategy Processing"}
        </Btn>
        <Btn variant="default" onClick={() => onComplete({})} style={{ marginLeft: "auto" }}>
          Continue to Research →
        </Btn>
      </div>
      {status && <div style={{ marginBottom: 8, color: status === "failed" ? T.red : T.teal }}>
        Status: {status}{jobId ? ` (job ${jobId})` : ""}
      </div>}
      {error && <div style={{ color: T.red, fontSize: 12 }}>{error}</div>}
    </Card>
  )
}

function StepResearch({ projectId, sessionId, customerUrl, competitorUrls, businessIntent, strategyContext, onComplete, onBack }) {
  const notify = useNotification(s => s.notify)
  const [jobId, setJobId]     = useState(null)
  const [status, setStatus]   = useState(null)  // null | running | completed | failed
  const [result, setResult]   = useState(null)
  const [error, setError]     = useState("")
  const pollRef               = useRef(null)

  const startResearch = async () => {
    setError("")
    try {
      const r = await apiCall(`/api/ki/${projectId}/research`, "POST", {
        session_id: sessionId, customer_url: customerUrl,
        competitor_urls: competitorUrls,
        // Task 6: Pass business intents (array) to research engine
        business_intent: businessIntent && businessIntent.length > 0 ? businessIntent : ["ecommerce"],
        // Pass strategy_context from Step 2 for enhanced filtering
        strategy_context: strategyContext,
      })
      if (r.job_id) {
        setJobId(r.job_id); setStatus("running")
      } else {
        setError(typeof r?.detail === 'string' ? r.detail : Array.isArray(r?.detail) ? r.detail.map(e=>e.msg||String(e)).join('; ') : "Failed to start research")
      }
    } catch (e) { setError(String(e)) }
  }

  useEffect(() => {
    if (!jobId || status !== "running") return
    pollRef.current = setInterval(async () => {
      try {
        const r = await apiCall(`/api/ki/${projectId}/research/${jobId}`)
        setResult(r)
        if (r.status === "completed" || r.status === "failed") {
          setStatus(r.status)
          clearInterval(pollRef.current)
        }
      } catch (e) {
        setError("Research polling failed: " + (e?.message || String(e)))
        setStatus("failed")
        clearInterval(pollRef.current)
      }
    }, 2000)
    return () => clearInterval(pollRef.current)
  }, [jobId, status])

  const sources = result?.result_payload?.sources_done || []
  const count = result?.result_payload?.total_count || 0

  return (
    <Card>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Step 3 — Keyword Discovery</div>
      <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 16 }}>
        Discover new keywords from 3 sources: your supporting keywords (+10), Google Autosuggest (+5), and AI classification. Returns 20-50 ranked keywords with business intent filtering.
      </div>

      {/* Pillars summary */}
      <div style={{ background: T.grayLight, borderRadius: 8, padding: "10px 14px", marginBottom: 16 }}>
        <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 4 }}>From Step 1:</div>
        <div style={{ fontSize: 12 }}>Session: <code style={{ fontSize: 11 }}>{sessionId?.slice(0,20)}…</code></div>
        {customerUrl && <div style={{ fontSize: 12, marginTop: 2 }}>Website: {customerUrl}</div>}
        {(competitorUrls || []).length > 0 && (
          <div style={{ fontSize: 12, marginTop: 2 }}>Competitors: {(competitorUrls || []).length} URL(s)</div>
        )}
      </div>

      {/* Progress */}
      {status && (
        <div style={{ marginBottom: 16 }}>
          {[
            { key: "autosuggest", label: "Google Autosuggest (P2_Enhanced)" },
            { key: "competitor_gap", label: "Competitor keyword gap" },
            { key: "site_crawl", label: "Site crawl (H1/H2/product pages)" },
          ].map(s => (
            <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 8,
                                       padding: "6px 0", borderBottom: `1px solid ${T.border}` }}>
              <span style={{ fontSize: 16 }}>
                {sources.includes(s.key) ? "✅" : status === "running" ? "⏳" : "⬜"}
              </span>
              <span style={{ fontSize: 13 }}>{s.label}</span>
            </div>
          ))}
          {count > 0 && (
            <div style={{ marginTop: 10, fontSize: 13, color: T.teal, fontWeight: 600 }}>
              {count} keywords found so far
            </div>
          )}
          {status === "completed" && (
            <div style={{ marginTop: 10, padding: "8px 12px", background: T.greenLight,
                          borderRadius: 8, fontSize: 13, color: T.green, fontWeight: 500 }}>
              ✓ Research complete — {count} keywords added to review queue
            </div>
          )}
          {status === "failed" && (
            <div style={{ marginTop: 10, color: T.red, fontSize: 12 }}>{result?.error || "Research failed"}</div>
          )}
        </div>
      )}

      {error && <div style={{ color: T.red, fontSize: 12, marginBottom: 10 }}>{error}</div>}

      <div style={{ display: "flex", gap: 8 }}>
        <Btn onClick={onBack}>← Back</Btn>
        {!status && (
          <Btn variant="teal" onClick={startResearch}>▶ Fetch Keywords Now</Btn>
        )}
        {status === "running" && (
          <Btn disabled variant="teal">⏳ Researching…</Btn>
        )}
        <Btn variant="primary" onClick={onComplete}
          style={{ marginLeft: "auto" }}
          disabled={status === "running"}>
          {status === "completed" ? "Continue to Review →" : "Skip this step →"}
        </Btn>
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// KEYWORD DASHBOARD — shown when project already has keywords (skip Step 1+2)
// ─────────────────────────────────────────────────────────────────────────────

function KeywordDashboard({ projectId, onGoToStep, onStartFresh }) {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["ki-dashboard", projectId],
    queryFn: () => apiCall(`/api/ki/${projectId}/dashboard`),
    enabled: !!projectId,
  })

  if (isLoading) return (
    <div style={{ textAlign:"center", padding:40, color:T.textSoft }}>
      <div style={{ fontSize:24, marginBottom:8 }}>⏳</div>
      <div>Loading keyword intelligence…</div>
    </div>
  )

  if (!data?.has_keywords) return null  // no keywords → caller handles Step 1 flow

  const { stats, pillars, top_keywords, sources, session_id, session_created, stage } = data
  const kdColor = (kd) => kd <= 20 ? T.green : kd <= 50 ? T.amber : T.red
  const oppColor = (s) => s >= 75 ? T.green : s >= 50 ? T.amber : T.red
  const srcLabel = { cross_multiply:"User×", site_crawl:"Site", template:"Template",
    competitor_crawl:"Comp", research_autosuggest:"Suggest",
    research_competitor_gap:"Gap", autosuggest:"Suggest", competitor_gap:"Comp" }

  const totalKDKnown = (stats.kd_easy||0) + (stats.kd_medium||0) + (stats.kd_hard||0)

  return (
    <div>
      {/* Dashboard header */}
      <Card style={{ marginBottom:12, background: `linear-gradient(135deg, ${T.teal}15, ${T.purple}08)` }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
          <div>
            <div style={{ fontSize:18, fontWeight:700, marginBottom:4 }}>
              📊 Keyword Intelligence Dashboard
            </div>
            <div style={{ fontSize:12, color:T.textSoft }}>
              Session: <code style={{ fontSize:11 }}>{session_id?.slice(-20)}</code>
              {session_created && <span> · Created {new Date(session_created).toLocaleDateString()}</span>}
              {stage && <span> · Stage: <b>{stage}</b></span>}
            </div>
          </div>
          <div style={{ display:"flex", gap:8 }}>
            <Btn small onClick={() => refetch()} style={{ color:T.textSoft }}>⟳ Refresh</Btn>
            <Btn small onClick={onStartFresh} style={{ color:T.textSoft }}>+ New Session</Btn>
          </div>
        </div>
      </Card>

      {/* Stat cards */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(6,1fr)", gap:8, marginBottom:12 }}>
        {[
          { label:"Total Keywords", val:stats.total||0,       color:T.text },
          { label:"Pending Review", val:stats.pending||0,     color:T.amber },
          { label:"Accepted",       val:stats.accepted||0,    color:T.green },
          { label:"Rejected",       val:stats.rejected||0,    color:T.red },
          { label:"Quick Wins",     val:stats.quick_wins||0,  color:T.teal, sub:"KD≤20 · Vol≥100" },
          { label:"Avg KD",         val:stats.avg_kd||"—",    color:kdColor(stats.avg_kd) },
          { label:"AI Review",      val:stats.ai_review_total||0, color:T.purple, sub:`Removed ${stats.ai_review_removed||0}` },
        ].map(s => (
          <Card key={s.label} style={{ padding:"10px 12px", textAlign:"center" }}>
            <div style={{ fontSize:24, fontWeight:800, color:s.color, lineHeight:1 }}>{s.val}</div>
            <div style={{ fontSize:9, color:T.textSoft, marginTop:3, textTransform:"uppercase", letterSpacing:".06em" }}>{s.label}</div>
            {s.sub && <div style={{ fontSize:9, color:s.color, marginTop:2 }}>{s.sub}</div>}
          </Card>
        ))}
      </div>

      {/* Main body: two columns */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:12 }}>

        {/* Pillar breakdown */}
        <Card>
          <div style={{ fontSize:12, fontWeight:700, marginBottom:10, color:T.textSoft, textTransform:"uppercase", letterSpacing:".06em" }}>
            Pillars
          </div>
          {(pillars||[]).length === 0 ? (
            <div style={{ fontSize:12, color:T.textSoft }}>No pillars found</div>
          ) : (pillars||[]).map(p => (
            <div key={p.pillar} style={{ marginBottom:10 }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom:3 }}>
                <span style={{ fontSize:13, fontWeight:600, color:T.teal }}>{p.pillar || "(unassigned)"}</span>
                <span style={{ fontSize:11, color:T.textSoft }}>{p.total} kw</span>
              </div>
              {/* Mini progress bar: accepted vs pending */}
              <div style={{ height:4, background:"rgba(0,0,0,.06)", borderRadius:99, overflow:"hidden", marginBottom:3 }}>
                <div style={{ height:"100%", background:T.green, borderRadius:99,
                               width: `${p.total ? (p.accepted/p.total*100) : 0}%` }}/>
              </div>
              <div style={{ display:"flex", gap:8, fontSize:10, color:T.textSoft }}>
                <span style={{ color:T.green }}>{p.accepted} accepted</span>
                <span>{p.pending} pending</span>
                {p.avg_opp != null && <span style={{ color:oppColor(p.avg_opp), marginLeft:"auto" }}>Opp:{p.avg_opp}</span>}
                {p.avg_kd != null && <span style={{ color:kdColor(p.avg_kd) }}>KD:{p.avg_kd}</span>}
              </div>
            </div>
          ))}
        </Card>

        {/* KD distribution + Source breakdown */}
        <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
          <Card style={{ flex:"0 0 auto" }}>
            <div style={{ fontSize:12, fontWeight:700, marginBottom:10, color:T.textSoft, textTransform:"uppercase", letterSpacing:".06em" }}>
              KD Distribution
            </div>
            {[
              { label:"Easy (0–20)",  count:stats.kd_easy||0,   color:T.green },
              { label:"Medium (21–50)",count:stats.kd_medium||0, color:T.amber },
              { label:"Hard (51+)",   count:stats.kd_hard||0,   color:T.red },
            ].map(b => (
              <div key={b.label} style={{ marginBottom:8 }}>
                <div style={{ display:"flex", justifyContent:"space-between", marginBottom:2 }}>
                  <span style={{ fontSize:11, color:b.color, fontWeight:500 }}>{b.label}</span>
                  <span style={{ fontSize:11, color:T.textSoft }}>{b.count}</span>
                </div>
                <div style={{ height:6, background:"rgba(0,0,0,.06)", borderRadius:99, overflow:"hidden" }}>
                  <div style={{ height:"100%", background:b.color, borderRadius:99,
                                 width: `${totalKDKnown ? (b.count/totalKDKnown*100) : 0}%`, transition:"width .4s" }}/>
                </div>
              </div>
            ))}
          </Card>
          <Card style={{ flex:"0 0 auto" }}>
            <div style={{ fontSize:12, fontWeight:700, marginBottom:8, color:T.textSoft, textTransform:"uppercase", letterSpacing:".06em" }}>
              Sources
            </div>
            {(sources||[]).map(s => (
              <div key={s.source} style={{ display:"flex", justifyContent:"space-between", marginBottom:4 }}>
                <span style={{ fontSize:12, color:T.text }}>{srcLabel[s.source] || s.source}</span>
                <span style={{ fontSize:12, fontWeight:600, color:T.teal }}>{s.cnt}</span>
              </div>
            ))}
          </Card>
        </div>
      </div>

      {/* Top opportunity keywords */}
      <Card style={{ marginBottom:12 }}>
        <div style={{ fontSize:12, fontWeight:700, marginBottom:10, color:T.textSoft, textTransform:"uppercase", letterSpacing:".06em" }}>
          Top Opportunity Keywords
        </div>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
          <thead>
            <tr style={{ borderBottom:`1px solid ${T.border}` }}>
              {["Keyword","Pillar","KD","Volume","Source","Status"].map(h => (
                <th key={h} style={{ padding:"5px 8px", textAlign:"left", fontWeight:600, color:T.textSoft, fontSize:10, textTransform:"uppercase" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(top_keywords||[]).map((kw, i) => (
              <tr key={i} style={{ borderBottom:`1px solid ${T.border}` }}>
                <td style={{ padding:"6px 8px", fontWeight:500 }}>{kw.keyword}</td>
                <td style={{ padding:"6px 8px", color:T.teal, fontSize:11 }}>{kw.pillar_keyword||"—"}</td>
                <td style={{ padding:"6px 8px" }}>
                  <span style={{ fontWeight:700, color:kdColor(kw.difficulty) }}>{kw.difficulty??50}</span>
                </td>
                <td style={{ padding:"6px 8px", color:T.textSoft }}>
                  {kw.volume_estimate >= 1000 ? (kw.volume_estimate/1000).toFixed(1)+"K" : kw.volume_estimate||0}
                </td>
                <td style={{ padding:"6px 8px", color:T.textSoft, fontSize:11 }}>{kw.source || "—"}</td>
                <td style={{ padding:"6px 8px" }}>
                  <Badge color={kw.status==="accepted"?T.green:kw.status==="rejected"?T.red:T.amber}>
                    {kw.status}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Action buttons */}
      <Card style={{ background:`linear-gradient(135deg, ${T.teal}08, ${T.purple}05)` }}>
        <div style={{ fontSize:13, fontWeight:700, marginBottom:12 }}>Continue your SEO workflow</div>
        <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
          <div style={{ flex:1, minWidth:180, padding:"14px 16px", background:T.white, borderRadius:10,
                        border:`2px solid ${T.teal}`, cursor:"pointer" }}
            onClick={() => onGoToStep(3, session_id)}>
            <div style={{ fontSize:16, marginBottom:4 }}>📋</div>
            <div style={{ fontSize:13, fontWeight:700, color:T.teal }}>Review Keywords</div>
            <div style={{ fontSize:11, color:T.textSoft, marginTop:2 }}>
              Accept/reject keywords, score difficulty, filter by pillar
            </div>
            <div style={{ marginTop:8, fontSize:11, fontWeight:600, color:T.teal }}>
              {stats.pending||0} pending review →
            </div>
          </div>
          <div style={{ flex:1, minWidth:180, padding:"14px 16px", background:T.white, borderRadius:10,
                        border:`2px solid ${T.purple}`, cursor:"pointer" }}
            onClick={() => onGoToStep(4, session_id)}>
            <div style={{ fontSize:16, marginBottom:4 }}>🤖</div>
            <div style={{ fontSize:13, fontWeight:700, color:T.purple }}>AI Review</div>
            <div style={{ fontSize:11, color:T.textSoft, marginTop:2 }}>
              Run DeepSeek → Groq → Gemini validation on accepted keywords
            </div>
            <div style={{ marginTop:8, fontSize:11, fontWeight:600, color:T.purple }}>
              {stats.accepted||0} accepted keywords →
            </div>
          </div>
          <div style={{ flex:1, minWidth:180, padding:"14px 16px", background:T.white, borderRadius:10,
                        border:`2px solid ${T.amber}`, cursor:"pointer" }}
            onClick={() => onGoToStep(5, session_id)}>
            <div style={{ fontSize:16, marginBottom:4 }}>🚀</div>
            <div style={{ fontSize:13, fontWeight:700, color:T.amber }}>Run Pipeline</div>
            <div style={{ fontSize:11, color:T.textSoft, marginTop:2 }}>
              Launch 20-phase keyword universe engine for full cluster generation
            </div>
            <div style={{ marginTop:8, fontSize:11, fontWeight:600, color:T.amber }}>
              Start 20-phase engine →
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 3 — UNIFIED REVIEW (Score Dashboard + Pillar Sidebar + Table)
// ─────────────────────────────────────────────────────────────────────────────

const sourceLabel = (src) => {
  const map = {
    cross_multiply: "User×", site_crawl: "Site", template: "Template",
    competitor_crawl: "Competitor", research_autosuggest: "Suggest",
    research_competitor_gap: "Gap", research_site_crawl: "Site2", strategy: "Strategy",
  }
  return map[src] || src
}

function StepReview({ projectId, sessionId, onComplete, onBack, workflowStatus }) {
  const notify = useNotification(s => s.notify)
  const [filterPillar, setFilterPillar] = useState("all")
  const [filterStatus, setFilterStatus] = useState("all")
  const [filterIntent, setFilterIntent] = useState("all")
  const [intentFilter, setIntentFilter] = useState("all")  // Task 6: Intent filter for research results
  const [reviewMethod, setReviewMethod] = useState("merged")
  const [sortBy, setSortBy]             = useState("opp_desc")
  const [page, setPage]                 = useState(0)
  const [selected, setSelected]         = useState(new Set())
  const [scoreJobId, setScoreJobId]     = useState(null)
  const [scoreProgress, setScoreProgress] = useState(null)
  const [showScorePanel, setShowScorePanel] = useState(false)
  const [aiCleanRunning, setAiCleanRunning] = useState(false)
  const [aiCleanMessage, setAiCleanMessage] = useState("")
  const [top100Status, setTop100Status] = useState("")
  const [editModal, setEditModal]       = useState(null)
  const [reviewError, setReviewError]   = useState("")
  const [movePillarModal, setMovePillarModal] = useState(null)
  const PAGE_SIZE = 40
  const queryClient = useQueryClient()

  // ── Data fetching ──────────────────────────────────────────────────────────

  const { data, refetch, isLoading, isFetching } = useQuery({
    queryKey: ["ki-review", projectId, sessionId, filterPillar, filterStatus,
                filterIntent, sortBy, page, reviewMethod],
    queryFn: () => {
      const params = new URLSearchParams({
        limit: PAGE_SIZE, offset: page * PAGE_SIZE, sort_by: sortBy,
        ...(filterPillar !== "all" ? { pillar: filterPillar } : {}),
        ...(filterStatus !== "all" ? { status: filterStatus } : {}),
        ...(filterIntent !== "all" ? { intent: filterIntent } : {}),
        ...(reviewMethod !== "merged" ? { review_method: reviewMethod } : {}),
      })
      return apiCall(`/api/ki/${projectId}/review/${sessionId}?${params}`)
    },
    enabled: !!sessionId,
    refetchInterval: false,
    retry: 2,
  })

  const { data: pillarData, refetch: refetchPillars } = useQuery({
    queryKey: ["ki-pillars", projectId, sessionId],
    queryFn: () => apiCall(`/api/ki/${projectId}/universe/${sessionId}/by-pillar`),
    enabled: !!sessionId,
  })

  // Poll score job
  useEffect(() => {
    if (!scoreJobId) return
    const iv = setInterval(async () => {
      try {
        const r = await apiCall(`/api/ki/${projectId}/score/${sessionId}/${scoreJobId}`)
        setScoreProgress({ scored: r.scored, total: r.total, status: r.status })
        if (r.status === "completed" || r.status === "failed") {
          clearInterval(iv)
          setScoreJobId(null)
          if (r.status === "completed") {
            refetch()
            refetchPillars()
            queryClient.invalidateQueries(["ki-review"])
          }
        }
      } catch (e) {
        setScoreProgress(prev => ({ ...prev, status: "failed" }))
        setReviewError("Score calculation failed: " + (e?.message || String(e)))
        clearInterval(iv)
      }
    }, 2000)
    return () => clearInterval(iv)
  }, [scoreJobId])

  // ── Actions ────────────────────────────────────────────────────────────────

  const doAction = async (keyword_id, action, extra = {}) => {
    await apiCall(`/api/ki/${projectId}/review/${sessionId}/action`, "POST",
      { keyword_id, action, ...extra })
    refetch()
    refetchPillars()
  }

  const acceptAll = async () => {
    await apiCall(`/api/ki/${projectId}/review/${sessionId}/accept-all`, "POST",
      filterPillar !== "all" ? { pillar: filterPillar } : {})
    setSelected(new Set())
    refetch()
    refetchPillars()
  }

  const bulkAcceptReject = async (action) => {
    if (!selected.size) return
    await Promise.all([...selected].map(id => doAction(id, action)))
    setSelected(new Set())
  }

  const bulkDelete = async () => {
    if (!selected.size) return
    if (!window.confirm(`Delete ${selected.size} keyword(s) permanently?`)) return
    await apiCall(`/api/ki/${projectId}/review/${sessionId}/items`, "DELETE",
      { item_ids: [...selected] })
    setSelected(new Set())
    refetch()
    refetchPillars()
  }

  const deletePillar = async (pillar) => {
    if (!pillar || pillar === "all") return
    if (!window.confirm(`Delete pillar "${pillar}" and clear assigned keywords?`)) return
    await apiCall(`/api/ki/${projectId}/pillars/${encodeURIComponent(pillar)}`, "DELETE")
    setFilterPillar("all")
    setSelected(new Set())
    refetch()
    refetchPillars()
  }

  const startScoring = async () => {
    setShowScorePanel(true)
    try {
      const r = await apiCall(`/api/ki/${projectId}/score/${sessionId}`, "POST", {})
      setScoreJobId(r.job_id)
      setScoreProgress({ scored: 0, total: r.total, status: "running" })
    } catch (e) {
      notify("Scoring failed to start: " + (e?.message || String(e)), "error")
    }
  }

  const runAutoAIClean = async () => {
    setAiCleanRunning(true)
    setAiCleanMessage("Running AI review and auto-clean...")
    try {
      const r = await apiCall(`/api/ki/${projectId}/ai-review/session/${sessionId}`, "POST", {
        stage: "deepseek",
        auto_apply: true,
        limit: 5000,
      })
      setAiCleanMessage(`AI review completed: ${r.flagged_count || 0} flagged`)

      // refresh top100 after manual edits/AI cleaning
      const top100Res = await apiCall(`/api/ki/${projectId}/top100/${sessionId}/refresh`, "POST")
      setTop100Status(`Top100 refreshed: ${top100Res.top100?.length || 0} keywords`)

      refetch(); refetchPillars(); queryClient.invalidateQueries(["ki-review"])
    } catch (e) {
      setAiCleanMessage(`AI clean failed: ${String(e)}`)
      setTop100Status("Top100 refresh failed")
    } finally {
      setAiCleanRunning(false)
      setTimeout(() => setAiCleanMessage(""), 5000)
      setTimeout(() => setTop100Status(""), 5000)
    }
  }

  const toggleRow = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  // ── Derived data ───────────────────────────────────────────────────────────

  const keywords  = data?.keywords || []

  const toggleAll = (checked) => {
    setSelected(checked ? new Set(keywords.map(k => k.item_id)) : new Set())
  }
  const total     = data?.total || 0
  const stats     = data?.stats || {}
  const pillars   = pillarData?.pillars || []
  const allAccepted = stats.accepted || 0

  const kdColor = (kd) => kd <= 20 ? T.green : kd <= 50 ? T.amber : T.red
  const oppColor = (s) => s >= 75 ? T.green : s >= 50 ? T.amber : T.red
  const volColor = (v) => v >= 500 ? T.purple : v >= 200 ? T.teal : T.textSoft
  const fmtVol = (v) => v >= 1000 ? (v/1000).toFixed(1)+"K" : String(v || 0)

  const inStyle = {
    padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`,
    fontSize: 12, background: T.grayLight, color: T.text,
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Header */}
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:12 }}>
        <div>
          <div style={{ fontSize:15, fontWeight:700 }}>Step 3 — Review (Method 1 / Method 2)</div>
          <div style={{ fontSize:11, color:T.textSoft }}>
            Session: {sessionId?.slice(-16)}… · {reviewMethod === "merged" ? "All sources (merged)" : reviewMethod === "method1" ? "Method 1 only" : "Method 2 only"}
          </div>
        </div>
        <div style={{ display:"flex", gap:6 }}>
          <Btn small variant={reviewMethod === "merged" ? "primary" : "default"} onClick={() => setReviewMethod("merged")}>All</Btn>
          <Btn small variant={reviewMethod === "method1" ? "primary" : "default"} onClick={() => setReviewMethod("method1")}>Method 1</Btn>
          <Btn small variant={reviewMethod === "method2" ? "primary" : "default"} onClick={() => setReviewMethod("method2")}>Method 2</Btn>
        </div>
        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          <Btn small onClick={() => { refetch(); refetchPillars() }}
            style={{ fontSize:11, color:T.textSoft, border:`1px solid ${T.border}` }}>
            {isFetching ? "⟳ Loading…" : "⟳ Refresh"}
          </Btn>
          <Btn small onClick={runAutoAIClean} disabled={aiCleanRunning} style={{ border:`1px solid ${T.purple}`, color:T.purple }}>
            {aiCleanRunning ? "⚙️ AI cleaning..." : "Auto AI Clean →"}
          </Btn>
          <span style={{ fontSize:11, color:T.textSoft, marginLeft:8 }}>{top100Status}</span>
          <Btn variant="primary" onClick={startScoring} disabled={!!scoreJobId}>
            {scoreJobId ? `⚡ Scoring… ${scoreProgress?.scored||0}/${scoreProgress?.total||0}` : "⚡ Score Keywords"}
          </Btn>
        </div>
      </div>

      {aiCleanMessage && (
        <div style={{ marginBottom:10, fontSize:12, color:T.purple, fontWeight:600 }}>
          {aiCleanMessage}
        </div>
      )}

      {/* Loading state banner */}
      {isLoading && (
        <div style={{ marginBottom:12, padding:"14px 16px", background:"#eff6ff",
                      border:`1px solid #93c5fd`, borderRadius:8, fontSize:13 }}>
          <div style={{ fontWeight:600, color:"#1e40af", marginBottom:4 }}>
            ⏳ Loading your keyword queue…
          </div>
          <div style={{ fontSize:11, color:"#3b82f6" }}>
            Keywords may take a moment to appear after research completes. The database is being populated.
            Use the Refresh button above to check again.
          </div>
        </div>
      )}

      {/* Stat cards */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(6,1fr)", gap:8, marginBottom:12 }}>
        {[
          { label:"Total",       val: stats.total || 0,     color: T.text },
          { label:"Pending",     val: stats.pending || 0,   color: T.amber },
          { label:"Accepted",    val: stats.accepted || 0,  color: T.green },
          { label:"Rejected",    val: stats.rejected || 0,  color: T.red },
          { label:"Quick Wins",  val: stats.quick_wins != null ? stats.quick_wins : "—",
            color: T.teal, sub: "KD≤20 · Vol≥100" },
          { label:"Avg KD",
            val: (stats.avg_kd && stats.avg_kd !== 50) ? stats.avg_kd : "—",
            color: stats.avg_kd <= 20 ? T.green : stats.avg_kd <= 50 ? T.amber : T.red },
        ].map(s => (
          <Card key={s.label} style={{ padding:"8px 10px", textAlign:"center" }}>
            <div style={{ fontSize:20, fontWeight:800, color:s.color }}>{s.val}</div>
            <div style={{ fontSize:10, color:T.textSoft }}>{s.label}</div>
            {s.sub && <div style={{ fontSize:9, color:s.color }}>{s.sub}</div>}
          </Card>
        ))}
      </div>

      {/* Score progress bar */}
      {scoreProgress && scoreProgress.status === "running" && (
        <div style={{ marginBottom:10, padding:"8px 12px", background:"#fffbeb",
                      border:`1px solid ${T.amber}`, borderRadius:8, fontSize:12 }}>
          <div style={{ marginBottom:5, color:"#92400e" }}>
            <b>⚡ Scoring in progress…</b> {scoreProgress.scored} / {scoreProgress.total} keywords
          </div>
          <div style={{ height:4, background:"#fef3c7", borderRadius:2, overflow:"hidden" }}>
            <div style={{
              height:"100%", background:T.amber, borderRadius:2,
              width: `${scoreProgress.total ? (scoreProgress.scored/scoreProgress.total*100) : 0}%`,
              transition:"width .3s"
            }}/>
          </div>
        </div>
      )}

      {/* Main layout */}
      <div style={{ display:"flex", gap:10, alignItems:"flex-start" }}>

        {/* Pillar sidebar */}
        <Card style={{ width:160, flexShrink:0 }}>
          <div style={{ padding:"7px 10px", borderBottom:`1px solid ${T.border}`,
                        fontSize:10, fontWeight:700, color:T.textSoft,
                        textTransform:"uppercase", letterSpacing:".05em" }}>Pillars</div>
          <div style={{ display:"flex", gap:6, alignItems:"center", padding:"7px 10px", borderBottom:`1px solid ${T.border}` }}>
            <Btn small variant="default" onClick={() => { setFilterPillar("all"); setSelected(new Set()); }}>
              Show all
            </Btn>
            <Btn small variant="danger" disabled={filterPillar === "all"} onClick={() => deletePillar(filterPillar)}>
              Delete pillar
            </Btn>
          </div>
          {[{ pillar:"all", total: stats.total||0, avg_opp_score:null, avg_kd:null },
            ...pillars].map(p => {
            const active = filterPillar === p.pillar
            return (
              <div key={p.pillar}
                onClick={() => { setFilterPillar(p.pillar); setPage(0); setSelected(new Set()) }}
                style={{
                  padding:"7px 10px", cursor:"pointer",
                  background: active ? "#f0faf7" : "transparent",
                  borderLeft: `3px solid ${active ? T.teal : "transparent"}`,
                }}>
                <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                  <span style={{ fontSize:12, fontWeight: active?700:400,
                                 color: active ? T.teal : T.text }}>
                    {p.pillar === "all" ? "All pillars" : p.pillar}
                  </span>
                  <span style={{ fontSize:10, color:T.textSoft }}>{p.total}</span>
                </div>
                {p.avg_opp_score != null && (
                  <div style={{ fontSize:9, color: oppColor(p.avg_opp_score), marginTop:1 }}>
                    Opp:{p.avg_opp_score} · KD:{p.avg_kd}
                  </div>
                )}
              </div>
            )
          })}
          {/* KD legend */}
          <div style={{ padding:"8px 10px", borderTop:`1px solid ${T.border}` }}>
            <div style={{ fontSize:9, fontWeight:700, color:T.textSoft,
                          textTransform:"uppercase", marginBottom:5 }}>KD Legend</div>
            {[["#16a34a","0–20 Easy"],["#d97706","21–50 Med"],["#dc2626","51+ Hard"]].map(([c,l]) => (
              <div key={l} style={{ display:"flex", alignItems:"center", gap:5, marginBottom:3 }}>
                <div style={{ width:8, height:8, borderRadius:2, background:c, flexShrink:0 }}/>
                <span style={{ fontSize:10, color:T.textSoft }}>{l}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Table area */}
        <div style={{ flex:1, minWidth:0 }}>

          {/* Bulk toolbar */}
          <Card style={{ padding:"7px 10px", marginBottom:8,
                         display:"flex", gap:6, alignItems:"center", flexWrap:"wrap" }}>
            <input type="checkbox"
              checked={selected.size > 0 && selected.size === keywords.length}
              onChange={e => toggleAll(e.target.checked)}
              style={{ width:13, height:13, cursor:"pointer" }}/>
            <Btn small onClick={() => toggleAll(true)} style={{ padding:"0 6px", fontSize:11 }}>Select All</Btn>
            <Btn small onClick={() => toggleAll(false)} style={{ padding:"0 6px", fontSize:11 }}>Clear Selection</Btn>
            <span style={{ fontSize:11, color:T.textSoft, marginRight:4 }}>
              {selected.size > 0 ? `${selected.size} selected` : "0 selected"}
            </span>
            <div style={{ height:14, width:1, background:T.border, margin:"0 2px" }}/>
            <Btn small variant="teal"
              disabled={!selected.size} onClick={() => bulkAcceptReject("accept")}>✓ Accept</Btn>
            <Btn small style={{ background:"#fef2f2", borderColor:"#fca5a5", color:"#dc2626" }}
              disabled={!selected.size} onClick={() => bulkAcceptReject("reject")}>✕ Reject</Btn>
            <Btn small style={{ color:T.purple, borderColor:"#c4b5fd" }}
              disabled={!selected.size}
              onClick={() => {
                const items = keywords.filter(k => selected.has(k.item_id))
                  .map(k => ({ id: k.item_id, keyword: k.keyword }))
                setEditModal({ items })
              }}>✎ Edit</Btn>
            <Btn small style={{ color:T.amber, borderColor:"#fcd34d" }}
              disabled={!selected.size}
              onClick={() => setMovePillarModal({ choices: pillars.map(p => p.pillar) })}>
              ⇄ Move Pillar</Btn>
            <Btn small style={{ color:"#dc2626", borderColor:"#fca5a5" }}
              disabled={!selected.size} onClick={bulkDelete}>🗑 Delete</Btn>
            <div style={{ height:14, width:1, background:T.border, margin:"0 2px 0 auto" }}/>
            <select value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setPage(0) }} style={inStyle}>
              <option value="all">All Status</option>
              <option value="pending">Pending</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
            </select>
            <select value={filterIntent} onChange={e => { setFilterIntent(e.target.value); setPage(0) }} style={inStyle}>
              <option value="all">All Intent</option>
              <option value="transactional">Transactional</option>
              <option value="commercial">Commercial</option>
              <option value="informational">Informational</option>
            </select>
            <select value={sortBy} onChange={e => setSortBy(e.target.value)} style={inStyle}>
              <option value="opp_desc">Sort: Opp Score ↓</option>
              <option value="kd_asc">Sort: KD ↑ (easiest)</option>
              <option value="vol_desc">Sort: Volume ↓</option>
              <option value="kw_asc">Sort: A→Z</option>
            </select>
            <Btn small variant="teal" onClick={acceptAll}>✓ Accept All Visible</Btn>
          </Card>

          {/* Task 6: Intent Filter Buttons */}
          <div style={{ marginBottom: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {["all", "transactional", "informational", "comparison", "commercial", "local"].map(intent => (
              <button
                key={intent}
                onClick={() => { setIntentFilter(intent); setPage(0) }}
                style={{
                  padding: "6px 12px",
                  fontSize: 11,
                  fontWeight: 500,
                  borderRadius: 4,
                  border: intentFilter === intent ? "2px solid #000" : "1px solid #ddd",
                  background: intentFilter === intent ? (intentBadgeColors[intent] || "#f0f0f0") : "#f9f9f9",
                  color: intentFilter === intent ? "#fff" : "#666",
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
              >
                {intent === "all" ? "ALL INTENTS" : intent.toUpperCase()}
                {intent !== "all" && ` (${(keywords || []).filter(k => k.intent === intent).length})`}
              </button>
            ))}
          </div>

          {/* Table */}
          <Card style={{ padding:0, overflow:"hidden" }}>
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
              <thead>
                <tr style={{ background:T.grayLight, borderBottom:`1px solid ${T.border}` }}>
                  <th style={{ padding:"7px 10px", width:28 }}>
                    <input type="checkbox"
                      checked={selected.size > 0 && selected.size === keywords.length}
                      onChange={e => toggleAll(e.target.checked)}
                      style={{ width:13, height:13 }}/>
                  </th>
                  {[["Keyword",""], ["Pillar",""], ["Source",""], ["Intent",""],
                    ["KD","kd_asc"], ["Vol","vol_desc"], ["Opp Score","opp_desc"],
                    ["Status",""], ["",""]
                  ].map(([h, s]) => (
                    <th key={h} style={{ padding:"7px 10px", textAlign:"left",
                                        fontWeight:600, color:T.textSoft,
                                        cursor: s ? "pointer" : "default" }}
                      onClick={() => s && setSortBy(s)}>
                      {h}{s && sortBy===s ? " ↓" : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {keywords
                  // Task 6: Filter by selected intent
                  .filter(kw => intentFilter === "all" || kw.intent === intentFilter)
                  .map((kw, i) => {
                  const isSel = selected.has(kw.item_id)
                  const statusColor = kw.status==="accepted"?"#16a34a":kw.status==="rejected"?"#dc2626":T.amber
                  const statusBg = kw.status==="accepted"?"#f0faf7":kw.status==="rejected"?"#fef2f2":"#fffbeb"
                  return (
                    <tr key={kw.item_id || i}
                      style={{ borderBottom:`1px solid ${T.border}`,
                               background: isSel ? "#f0faf7" : "transparent" }}>
                      <td style={{ padding:"6px 10px" }}>
                        <input type="checkbox" checked={isSel}
                          onChange={() => toggleRow(kw.item_id)}
                          style={{ width:13, height:13 }}/>
                      </td>
                      <td style={{ padding:"6px 10px", fontWeight:500 }}>{kw.keyword}</td>
                      <td style={{ padding:"6px 10px", color:T.teal, fontSize:11 }}>
                        {kw.pillar_keyword || "—"}
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        {/* Task 6: Use source colors from research engine */}
                        <Badge color={SOURCE_COLORS[kw.source] || intentColor(kw.source) || T.gray}>
                          {sourceLabel(kw.source)}
                        </Badge>
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        {/* Task 6: Use intent badge colors */}
                        <Badge color={intentBadgeColors[kw.intent] || intentColor(kw.intent)}>
                          {kw.intent?.slice(0,6)}{kw.intent?.length > 6 ? "." : ""}
                        </Badge>
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        <span style={{ fontWeight:700, color: kdColor(kw.difficulty) }}>
                          {kw.difficulty ?? "—"}
                        </span>
                      </td>
                      <td style={{ padding:"6px 10px", fontWeight:600,
                                   color: volColor(kw.volume_estimate) }}>
                        {fmtVol(kw.volume_estimate)}
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        <div style={{ display:"flex", alignItems:"center", gap:5 }}>
                          <div style={{ width:50, height:6, borderRadius:3,
                                        background:"#e5e7eb", overflow:"hidden" }}>
                            <div style={{ height:"100%", borderRadius:3,
                                          background: oppColor(kw.opportunity_score),
                                          width: `${kw.opportunity_score || 0}%` }}/>
                          </div>
                          <span style={{ fontSize:11, fontWeight:700,
                                         color: oppColor(kw.opportunity_score),
                                         minWidth:24 }}>
                            {kw.opportunity_score ?? "—"}
                          </span>
                        </div>
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        <Badge color={statusColor} style={{ background:statusBg }}>
                          {kw.status}
                        </Badge>
                      </td>
                      <td style={{ padding:"6px 10px" }}>
                        <div style={{ display:"flex", gap:3 }}>
                          {kw.status !== "accepted" && (
                            <Btn small variant="teal" onClick={() => doAction(kw.item_id, "accept")}>✓</Btn>
                          )}
                          {kw.status !== "rejected" && (
                            <Btn small style={{ background:"#fef2f2", borderColor:"#fca5a5", color:"#dc2626" }}
                              onClick={() => doAction(kw.item_id, "reject")}>✕</Btn>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
                {keywords.length === 0 && (
                  <tr><td colSpan={10} style={{ padding:32, textAlign:"center", color:T.textSoft }}>
                    No keywords found. Complete Step 1 to add keywords.
                  </td></tr>
                )}
              </tbody>
            </table>
            {total > PAGE_SIZE && (
              <div style={{ padding:"7px 12px", display:"flex", gap:8, alignItems:"center",
                             borderTop:`1px solid ${T.border}`, background:T.grayLight }}>
                <Btn small disabled={page===0} onClick={() => setPage(p => p-1)}>← Prev</Btn>
                <span style={{ fontSize:11, color:T.textSoft }}>
                  Page {page+1} of {Math.ceil(total/PAGE_SIZE)} · {total} keywords
                </span>
                <Btn small disabled={(page+1)*PAGE_SIZE >= total}
                  onClick={() => setPage(p => p+1)}>Next →</Btn>
              </div>
            )}
          </Card>

        </div>
      </div>

      {/* Edit modal */}
      {editModal && (
        <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,.4)",
                      display:"flex", alignItems:"center", justifyContent:"center", zIndex:200 }}>
          <Card style={{ width:400, padding:16 }}>
            <div style={{ fontWeight:700, marginBottom:8 }}>
              Edit {editModal.items.length} keyword(s)
            </div>
            <div style={{ fontSize:11, color:T.textSoft, marginBottom:8 }}>
              One keyword per line. Line count must match selection ({editModal.items.length}).
            </div>
            <textarea
              id="editTextarea"
              defaultValue={editModal.items.map(k => k.keyword).join("\n")}
              style={{ width:"100%", height:160, fontSize:12, fontFamily:"monospace",
                       padding:8, borderRadius:6, border:`1px solid ${T.border}`,
                       resize:"vertical", boxSizing:"border-box" }}
            />
            <div style={{ display:"flex", gap:8, marginTop:10 }}>
              <Btn onClick={() => setEditModal(null)}>Cancel</Btn>
              <Btn variant="primary" onClick={async () => {
                const lines = document.getElementById("editTextarea").value
                  .split("\n").map(l => l.trim()).filter(Boolean)
                if (lines.length !== editModal.items.length) {
                  notify(`Line count mismatch: expected ${editModal.items.length}, got ${lines.length}`, "warning")
                  return
                }
                await Promise.all(editModal.items.map((item, i) =>
                  doAction(item.id, "edit", { new_keyword: lines[i] })
                ))
                setEditModal(null)
                setSelected(new Set())
              }}>Save Changes</Btn>
            </div>
          </Card>
        </div>
      )}

      {/* Move pillar modal */}
      {movePillarModal && (
        <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,.4)",
                      display:"flex", alignItems:"center", justifyContent:"center", zIndex:200 }}>
          <Card style={{ width:320, padding:16 }}>
            <div style={{ fontWeight:700, marginBottom:8 }}>
              Move {selected.size} keyword(s) to pillar:
            </div>
            {movePillarModal.choices.map(p => (
              <div key={p}
                onClick={async () => {
                  await Promise.all([...selected].map(id =>
                    doAction(id, "move_pillar", { new_pillar: p })
                  ))
                  setMovePillarModal(null)
                  setSelected(new Set())
                  refetch(); refetchPillars()
                }}
                style={{ padding:"8px 12px", cursor:"pointer", borderRadius:6,
                         border:`1px solid ${T.border}`, marginBottom:6,
                         color:T.teal, fontWeight:600 }}>
                {p}
              </div>
            ))}
            <Btn onClick={() => setMovePillarModal(null)} style={{ marginTop:4 }}>Cancel</Btn>
          </Card>
        </div>
      )}

      {/* Navigation */}
      <div style={{ display:"flex", justifyContent:"space-between", marginTop:12 }}>
        <Btn onClick={onBack}>← Back</Btn>
        <Btn variant="primary"
          disabled={!workflowStatus?.can_advance || allAccepted === 0}
          onClick={() => onComplete({ acceptedCount: allAccepted })}
          style={{ padding:"8px 20px", fontSize:13, fontWeight:600 }}>
          Continue to AI Check → ({allAccepted} accepted)
        </Btn>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 4 — AI REVIEW (3 sequential stages)
// ─────────────────────────────────────────────────────────────────────────────

const AI_STAGES = [
  { key: "deepseek", label: "DeepSeek", subtitle: "Local · Free · Deep semantic validation", color: "#2563eb" },
  { key: "groq",     label: "Groq",     subtitle: "Fast free Llama cleanup", color: T.teal },
  { key: "gemini",   label: "Gemini",   subtitle: "Balanced semantic quality and robustness", color: "#f59e0b" },
]

// Fallback prompts shown immediately before API loads
const LOCAL_DEFAULT_PROMPTS = {
  deepseek: `You are a Keyword Intelligence Engine in deep reasoning mode.\n
INPUT:\n- Business: {{business_type}} | {{industry}}\n- Location: {{locations}}\n- Audience: {{target_audience}}\n- Seed keywords: {{seed_keywords}}\n- Generated keywords: {{keywords}}\n
TASK:\n1. Remove unnatural or reversed word-order keywords (e.g., "powder turmeric").\n2. Convert unnatural phrases to natural search phrases (e.g., "powder turmeric" -> "turmeric powder").\n3. Normalize to lowercase, no noise words; keep concise.\n4. Classify intent: informational/commercial/transactional/navigational.\n5. Mark any not natural search query as removed.\n
OUTPUT JSON ONLY, array of objects: [{"keyword":"...","action":"kept|corrected|removed","original":"...","intent":"...","confidence":0-100,"reason":"..."}]`,

  groq: `You are a fast SEO keyword quality filter for a {{industry}} business.\n
TASK:\n- From provided keywords, remove low-likelihood search queries and bad order phrases.\n- Fix a keyword if a naturally better form exists (e.g., "powder turmeric" -> "turmeric powder").\n- Keep keywords that match real commercial search patterns.\n
OUTPUT JSON ONLY: [{"keyword":"...","action":"kept|corrected|removed","intent":"...","score":0-100,"reason":"..."}]`,
}

function AIStageCard({ projectId, sessionId, stage, accepted_keywords, onDone, isActive }) {
  const [prompt, setPrompt] = useState(LOCAL_DEFAULT_PROMPTS[stage.key] || "")
  const [showPrompt, setShowPrompt] = useState(true)
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState("")

  // Load saved prompt from API; if none saved, keep the local default
  useEffect(() => {
    if (!isActive) return
    apiCall(`/api/ki/${projectId}/prompts`).then(r => {
      const saved = r[`${stage.key}_kw_review`]
      if (saved) setPrompt(saved)
    }).catch(() => {})
  }, [isActive, stage.key])

  const savePrompt = async (text) => {
    setPrompt(text)
    await apiCall(`/api/ki/${projectId}/prompts/${stage.key}_kw_review`, "PUT", { content: text })
  }

  const runReview = async () => {
    setRunning(true); setError("")
    try {
      const r = await apiCall(`/api/ki/${projectId}/ai-review`, "POST", {
        stage: stage.key,
        keywords: accepted_keywords,
        session_id: sessionId,
        custom_prompt: prompt,
      })
      setResults(r)
    } catch (e) { setError(String(e)) }
    finally { setRunning(false) }
  }

  const override = async (kw, decision) => {
    await apiCall(`/api/ki/${projectId}/ai-review/override`, "POST", {
      session_id: sessionId,
      decisions: [{ keyword: kw, stage: stage.key, decision }],
    })
    setResults(r => ({
      ...r,
      results: r.results.map(x => x.keyword===kw ? {...x, user_decision: decision} : x)
    }))
  }

  const flagged = results?.results?.filter(r => r.flagged) || []
  const clean = results?.results?.filter(r => !r.flagged) || []

  return (
    <div style={{ border: `1px solid ${isActive ? stage.color : T.border}`, borderRadius: 10,
                  padding: 16, marginBottom: 12,
                  opacity: isActive ? 1 : 0.55 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <div style={{ width: 10, height: 10, borderRadius: "50%", background: stage.color }} />
        <div style={{ fontWeight: 600, fontSize: 14 }}>{stage.label}</div>
        <div style={{ fontSize: 11, color: T.textSoft }}>{stage.subtitle}</div>
        {results && (
          <Badge color={flagged.length > 0 ? T.amber : T.green}>
            {flagged.length} flagged / {results.total} total
          </Badge>
        )}
      </div>

      {isActive && (
        <>
          {/* Prompt editor */}
          <div style={{ marginBottom: 10 }}>
            <button onClick={() => setShowPrompt(v => !v)}
              style={{ fontSize: 11, color: T.purple, background: "none", border: "none",
                       cursor: "pointer", marginBottom: 4 }}>
              {showPrompt ? "▲ Hide prompt" : "▼ Edit prompt"}
            </button>
            {showPrompt && (
              <div>
                <textarea value={prompt || ""} onChange={e => setPrompt(e.target.value)} rows={6}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 8, fontSize: 11,
                           border: `1px solid ${T.border}`, fontFamily: "monospace",
                           resize: "vertical", boxSizing: "border-box" }} />
                <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                  <Btn small onClick={() => savePrompt(prompt)}>Save prompt</Btn>
                  <Btn small onClick={() => {
                    apiCall(`/api/ki/${projectId}/prompts`).then(r => setPrompt(r[`${stage.key}_kw_review`]))
                    setShowPrompt(false)
                  }}>Reset to default</Btn>
                </div>
              </div>
            )}
          </div>

          {/* Run / Skip buttons */}
          {!results && (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <Btn variant="primary" onClick={runReview} disabled={running}>
                {running ? <><Spinner /> Running {stage.label} review…</> : `▶ Run ${stage.label} Review`}
              </Btn>
              {!running && (
                <Btn small onClick={onDone} style={{ color: T.textSoft }}>
                  Skip this stage →
                </Btn>
              )}
            </div>
          )}

          {error && <div style={{ color: T.red, fontSize: 12, marginTop: 8 }}>{error}</div>}

          {/* Results: flagged keywords */}
          {results && flagged.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.amber, marginBottom: 6 }}>
                ⚠ {flagged.length} flagged keywords — review and decide:
              </div>
              {flagged.map((item, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8,
                                      padding: "6px 10px", marginBottom: 4, borderRadius: 8,
                                      background: item.user_decision==="remove" ? "#fef2f2" :
                                                  item.user_decision==="keep" ? T.greenLight : T.amberLight }}>
                  <span style={{ fontWeight: 500, fontSize: 12, flex: 1 }}>{item.keyword}</span>
                  <span style={{ fontSize: 11, color: T.textSoft, flex: 2 }}>{item.reason}</span>
                  {item.user_decision === "pending" ? (
                    <div style={{ display: "flex", gap: 4 }}>
                      <Btn small variant="teal" onClick={() => override(item.keyword, "keep")}>Keep</Btn>
                      <Btn small variant="danger" onClick={() => override(item.keyword, "remove")}>Remove</Btn>
                    </div>
                  ) : (
                    <Badge color={item.user_decision==="keep" ? T.green : T.red}>
                      {item.user_decision}
                    </Badge>
                  )}
                </div>
              ))}
              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <Btn small variant="teal"
                  onClick={() => flagged.forEach(f => f.user_decision==="pending" && override(f.keyword,"keep"))}>
                  Keep all
                </Btn>
                <Btn small variant="danger"
                  onClick={() => flagged.forEach(f => f.user_decision==="pending" && override(f.keyword,"remove"))}>
                  Remove all
                </Btn>
              </div>
            </div>
          )}

          {results && flagged.length === 0 && (
            <div style={{ color: T.green, fontSize: 12, marginTop: 8 }}>
              ✓ All {results.total} keywords passed — no issues found.
            </div>
          )}

          {/* Continue button */}
          {results && (
            <Btn variant="primary" onClick={onDone} style={{ marginTop: 10 }}>
              Continue to next stage →
            </Btn>
          )}
        </>
      )}

      {!isActive && results && (
        <div style={{ fontSize: 12, color: T.textSoft }}>
          {flagged.length} flagged, {clean.length} clean
        </div>
      )}
    </div>
  )
}

function StepAIReview({ projectId, sessionId, onComplete, onBack }) {
  const notify = useNotification(s => s.notify)
  const [activeStage, setActiveStage] = useState(0)
  const [doneStages, setDoneStages]   = useState(0)

  // Load accepted keywords for review
  const { data: kwData } = useQuery({
    queryKey: ["ki-accepted", projectId, sessionId],
    queryFn: () => apiCall(`/api/ki/${projectId}/review/${sessionId}?status=accepted&limit=500`),
    enabled: !!sessionId,
  })
  const accepted = (kwData?.keywords || []).map(k => k.keyword)

  const advanceStage = () => {
    const next = activeStage + 1
    setDoneStages(next)
    if (next >= AI_STAGES.length) {
      onComplete()
    } else {
      setActiveStage(next)
    }
  }

  return (
    <div>
      <Card style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Step 4 — AI Review</div>
        <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 4 }}>
          3 sequential AI stages validate your accepted keywords. Each stage flags issues — you decide keep or remove.
        </div>
        <div style={{ fontSize: 12, color: T.textSoft }}>
          Reviewing <strong>{accepted.length}</strong> accepted keywords.
        </div>
      </Card>

      {AI_STAGES.map((stage, i) => (
        <AIStageCard
          key={stage.key}
          projectId={projectId}
          sessionId={sessionId}
          stage={stage}
          accepted_keywords={accepted}
          isActive={i === activeStage}
          onDone={advanceStage}
        />
      ))}

      <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
        <Btn onClick={onBack}>← Back</Btn>
        <Btn onClick={onComplete} style={{ marginLeft: "auto", color: T.textSoft }}>
          Pass AI Review →
        </Btn>
        {doneStages >= AI_STAGES.length && (
          <Btn variant="primary" onClick={onComplete}>
            Send to Pipeline →
          </Btn>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 5 — PIPELINE CONSTANTS + SUB-COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

const PIPELINE_PHASES = [
  { key: "P1",  name: "Seed Validation",      group: "collection" },
  { key: "P2",  name: "Keyword Expansion",    group: "collection" },
  { key: "P3",  name: "Normalization",        group: "collection" },
  { key: "P4",  name: "Entity Detection",     group: "analysis"  },
  { key: "P5",  name: "Intent Classification",group: "analysis"  },
  { key: "P6",  name: "SERP Analysis",        group: "analysis"  },
  { key: "P7",  name: "Opportunity Scoring",  group: "scoring"   },
  { key: "P8",  name: "Topic Detection",      group: "scoring"   },
  { key: "P9",  name: "Cluster Formation",    group: "scoring"   },
  { key: "P10", name: "Pillar Identification",group: "structure" },
  { key: "P11", name: "Knowledge Graph",      group: "structure" },
  { key: "P12", name: "Internal Links",       group: "structure" },
  { key: "P13", name: "Content Calendar",     group: "planning"  },
  { key: "P14", name: "Deduplication",        group: "planning"  },
  { key: "P15", name: "Blog Suggestions",     group: "content"   },
  { key: "P16", name: "Content Generation",   group: "content"   },
  { key: "P17", name: "SEO Optimization",     group: "content"   },
  { key: "P18", name: "Schema Generation",    group: "content"   },
  { key: "P19", name: "Publishing",           group: "publish"   },
  { key: "P20", name: "Feedback Loop",        group: "publish"   },
]

const PHASE_GROUP_COLOR = {
  collection: "#0d9488",
  analysis:   "#0891b2",
  scoring:    "#d97706",
  structure:  "#ea580c",
  planning:   "#2563eb",
  content:    "#7c3aed",
  publish:    "#dc2626",
}

const PHASE_GROUP_LABEL = {
  collection: "Collection",
  analysis:   "Analysis",
  scoring:    "Scoring",
  structure:  "Structure",
  planning:   "Planning",
  content:    "Content",
  publish:    "Publish",
}

// Rough ETA per phase in milliseconds (used before actual data available)
const PHASE_ETA_MS = {
  P1: 800, P2: 4000, P3: 1200, P4: 2500, P5: 2500,
  P6: 6000, P7: 2500, P8: 2000, P9: 2500,
  P10: 2000, P11: 3000, P12: 2000, P13: 2000, P14: 1500,
  P15: 3000, P16: 8000, P17: 3000, P18: 2000, P19: 2000, P20: 1000,
}

// Step 5 runs P1-P12, P14, P18 (P13, P15-P17, P19-P20 are excluded from this step)
const STEP5_PHASES = PIPELINE_PHASES.filter(p =>
  ["P1","P2","P3","P4","P5","P6","P7","P8","P9","P10","P11","P12","P14","P18"].includes(p.key)
)

function PillarRunCard({ run, events, expanded, onToggle, phases, onCancel }) {
  const currentPhaseRef = useRef(null)
  const [tick, setTick] = useState(0)  // for live elapsed timer

  const displayPhases = phases || PIPELINE_PHASES

  // Live tick for running-phase elapsed
  useEffect(() => {
    const t = setInterval(() => setTick(v => v + 1), 1000)
    return () => clearInterval(t)
  }, [])

  // Build phase summary: last event per phase wins
  const phaseSummary = {}
  ;(events || []).forEach(ev => {
    if (ev.phase) {
      if (!phaseSummary[ev.phase] || ev.status !== "starting") {
        phaseSummary[ev.phase] = ev
      }
    }
  })
  // Also track start time for live elapsed
  const phaseStartTimes = {}
  ;(events || []).forEach(ev => {
    if (ev.phase && ev.status === "starting") phaseStartTimes[ev.phase] = ev._ts || Date.now()
  })

  const completedCount = displayPhases.filter(p => phaseSummary[p.key]?.status === "complete").length
  const runningPhase   = displayPhases.find(p => phaseSummary[p.key]?.status === "starting")

  const isComplete = run.status === "complete"
  const isError    = run.status === "error"
  const isCancelled= run.status === "cancelled"
  const isRunning  = ["queued", "running"].includes(run.status)

  const headColor  = isComplete ? T.green : isError ? T.red : isCancelled ? T.gray : isRunning ? T.purple : T.amber
  const progress   = isComplete ? 100 : Math.round((completedCount / displayPhases.length) * 100)

  // ETA remaining
  const remainingPhases = displayPhases.slice(completedCount)
  const etaRemainingMs  = remainingPhases.reduce((s, p) => s + (PHASE_ETA_MS[p.key] || 2000), 0)
  const etaStr = etaRemainingMs > 60000 ? `~${Math.round(etaRemainingMs/60000)}min`
               : etaRemainingMs > 0 ? `~${Math.round(etaRemainingMs/1000)}s` : ""

  // Total elapsed across completed phases
  const totalMs    = Object.values(phaseSummary).reduce((s, ev) => s + (ev.elapsed_ms || 0), 0)
  const totalItems = Object.values(phaseSummary).filter(ev => ev.status === "complete")
    .reduce((s, ev) => s + (ev.output_count || 0), 0)

  // Auto-scroll to current running phase
  useEffect(() => {
    if (expanded && currentPhaseRef.current) {
      currentPhaseRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" })
    }
  }, [runningPhase?.key, expanded])

  return (
    <div style={{
      border: `1px solid ${isRunning ? T.purple+"55" : isComplete ? T.green+"44" : isError ? T.red+"44" : T.border}`,
      borderRadius: 10, marginBottom: 10, overflow: "hidden",
      boxShadow: isRunning ? `0 0 0 2px ${T.purple}18` : "none",
    }}>
      {/* ── Header ── */}
      <div
        onClick={onToggle}
        style={{
          padding: "12px 16px", cursor: "pointer", display: "flex", alignItems: "center", gap: 10,
          background: isRunning ? "#f5f3ff" : isComplete ? "#f0fdf4" : isError ? "#fef2f2" : T.grayLight,
        }}
      >
        <div style={{ width: 9, height: 9, borderRadius: "50%", background: headColor, flexShrink: 0,
                      animation: isRunning ? "pulse 1.5s ease-in-out infinite" : "none" }} />
        <div style={{ flex: 1 }}>
          <span style={{ fontWeight: 700, fontSize: 13 }}>{run.pillar}</span>
          <span style={{ fontSize: 10, color: T.textSoft, marginLeft: 8, fontFamily: "monospace" }}>
            {run.run_id?.slice(-14)}
          </span>
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {isRunning && runningPhase && (
            <span style={{ fontSize: 11, color: T.purple, fontWeight: 600 }}>
              <Spinner /> {runningPhase.key}
            </span>
          )}
          {isRunning && etaStr && (
            <span style={{ fontSize: 10, color: T.textSoft }}>ETA {etaStr}</span>
          )}
          <Badge color={headColor}>
            {isComplete   ? `✓ ${(totalMs/1000).toFixed(0)}s · ${totalItems} items` :
             isError      ? `✗ Failed` :
             isCancelled  ? `Cancelled` :
             isRunning    ? `${completedCount}/${displayPhases.length}` : "Queued"}
          </Badge>
          {isRunning && onCancel && (
            <button
              onClick={e => { e.stopPropagation(); onCancel(run.run_id) }}
              style={{ fontSize: 10, padding: "2px 8px", borderRadius: 6, border: `1px solid ${T.red}33`,
                       background: "#fef2f2", color: T.red, cursor: "pointer" }}>
              Cancel
            </button>
          )}
        </div>
        <span style={{ fontSize: 11, color: T.textSoft, marginLeft: 4 }}>{expanded ? "▲" : "▼"}</span>
      </div>

      {/* ── Overall progress bar ── */}
      <div style={{ height: 4, background: "rgba(0,0,0,.06)", position: "relative" }}>
        <div style={{
          height: "100%", borderRadius: 2,
          background: isError ? T.red : isComplete ? T.green : T.purple,
          width: `${progress}%`, transition: "width .4s",
        }} />
        {isRunning && (
          <div style={{
            position: "absolute", right: 4, top: -10, fontSize: 9,
            color: T.purple, fontFamily: "monospace",
          }}>
            {progress}%
          </div>
        )}
      </div>

      {/* ── Phase timeline (expanded) ── */}
      {expanded && (
        <div style={{ fontSize: 12 }}>
          {(() => {
            let lastGroup = null
            return displayPhases.map(phase => {
              const ev      = phaseSummary[phase.key]
              const gc      = PHASE_GROUP_COLOR[phase.group]
              const isDone  = ev?.status === "complete"
              const isErr   = ev?.status === "error"
              const isActive= ev?.status === "starting"
              const isPending = !ev

              const showGroupHeader = phase.group !== lastGroup
              lastGroup = phase.group

              // Live elapsed for active phase
              const liveElapsedSec = isActive && phaseStartTimes[phase.key]
                ? Math.round((Date.now() - phaseStartTimes[phase.key]) / 1000)
                : null

              // Phase mini progress bar fill
              const etaMs   = PHASE_ETA_MS[phase.key] || 3000
              const fillPct = isActive && liveElapsedSec != null
                ? Math.min(Math.round((liveElapsedSec * 1000 / etaMs) * 100), 95)
                : isDone ? 100 : 0

              return (
                <div key={phase.key}>
                  {showGroupHeader && (
                    <div style={{
                      padding: "5px 16px 2px", fontSize: 9, fontWeight: 700,
                      letterSpacing: ".08em", color: gc, textTransform: "uppercase",
                      borderTop: "1px solid rgba(0,0,0,.05)", marginTop: 2,
                    }}>
                      {PHASE_GROUP_LABEL[phase.group]}
                    </div>
                  )}
                  <div
                    ref={isActive ? currentPhaseRef : null}
                    style={{
                      padding: "5px 16px 5px 12px",
                      background: isActive ? "#f5f3ff" : "transparent",
                      borderLeft: isDone   ? `3px solid ${gc}` :
                                  isErr    ? `3px solid ${T.red}` :
                                  isActive ? `3px solid ${T.purple}` : "3px solid transparent",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      {/* Phase badge */}
                      <div style={{
                        width: 30, height: 20, borderRadius: 4, flexShrink: 0,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 9, fontWeight: 700,
                        background: isDone ? gc+"22" : isErr ? T.red+"18" : isActive ? T.purple+"18" : "rgba(0,0,0,.04)",
                        color: isDone ? gc : isErr ? T.red : isActive ? T.purple : "#94a3b8",
                      }}>
                        {isDone ? "✓" : isErr ? "✗" : isActive ? "▶" : phase.key}
                      </div>

                      {/* Phase name */}
                      <div style={{ flex: 1, color: isDone ? T.text : isErr ? T.red : isActive ? T.purple : "#94a3b8",
                                    fontWeight: isActive ? 600 : 400 }}>
                        <span style={{ fontFamily: "monospace", fontSize: 10,
                                       color: isDone ? gc : isActive ? T.purple : "#cbd5e1", marginRight: 4 }}>
                          {phase.key}
                        </span>
                        {phase.name}
                        {isActive && <span style={{ marginLeft: 6 }}><Spinner /></span>}
                      </div>

                      {/* Metrics */}
                      <div style={{ display: "flex", gap: 8, fontSize: 11, color: T.textSoft, flexShrink: 0, fontFamily: "monospace" }}>
                        {isDone && ev.output_count != null && (
                          <span style={{ color: gc, fontWeight: 600, fontFamily: "inherit" }}>{ev.output_count} items</span>
                        )}
                        {isDone && ev.elapsed_ms != null && (
                          <span style={{ color: T.textSoft }}>{(ev.elapsed_ms/1000).toFixed(1)}s</span>
                        )}
                        {isDone && ev.memory_delta_mb != null && Math.abs(ev.memory_delta_mb) > 0.5 && (
                          <span style={{ color: ev.memory_delta_mb > 8 ? T.amber : "#cbd5e1" }}>
                            +{ev.memory_delta_mb.toFixed(1)}MB
                          </span>
                        )}
                        {isActive && liveElapsedSec !== null && (
                          <span style={{ color: T.purple }}>{liveElapsedSec}s</span>
                        )}
                        {isActive && (
                          <span style={{ color: "#94a3b8" }}>
                            ~{Math.round(PHASE_ETA_MS[phase.key]/1000)}s est
                          </span>
                        )}
                        {isErr && (
                          <span style={{ color: T.red, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "inherit" }}>
                            {ev.msg?.replace(/^[✗\s]+/, "").slice(0, 70)}
                          </span>
                        )}
                        {isPending && (
                          <span style={{ color: "#e2e8f0" }}>
                            ~{Math.round((PHASE_ETA_MS[phase.key]||2000)/1000)}s
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Per-phase mini progress bar */}
                    {(isActive || isDone) && (
                      <div style={{ marginTop: 4, marginLeft: 40, height: 2, background: "rgba(0,0,0,.06)", borderRadius: 99 }}>
                        <div style={{
                          height: "100%", borderRadius: 99,
                          background: isDone ? gc : T.purple,
                          width: `${fillPct}%`, transition: isDone ? "none" : "width 1s linear",
                        }} />
                      </div>
                    )}
                  </div>
                </div>
              )
            })
          })()}

          {/* Summary footer */}
          {(isComplete || isError || isCancelled) && (
            <div style={{
              margin: "6px 12px 10px", padding: "10px 14px", borderRadius: 8,
              background: isComplete ? "#f0fdf4" : "#fef2f2",
              display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center",
            }}>
              {isComplete ? (
                <>
                  <span style={{ fontSize: 11, color: T.green, fontWeight: 600 }}>✅ {completedCount}/{displayPhases.length} phases complete</span>
                  <span style={{ fontSize: 11, color: T.textSoft }}>Total: {(totalMs/1000).toFixed(1)}s</span>
                  <span style={{ fontSize: 11, color: T.teal }}>{totalItems} items processed</span>
                  {run.completed_at && (
                    <span style={{ fontSize: 11, color: T.textSoft }}>
                      Finished: {new Date(run.completed_at).toLocaleTimeString()}
                    </span>
                  )}
                </>
              ) : isCancelled ? (
                <span style={{ fontSize: 11, color: T.gray }}>Run cancelled at {run.current_phase || "—"}</span>
              ) : (
                <>
                  <span style={{ fontSize: 11, color: T.red, fontWeight: 600 }}>
                    ✗ Failed at {run.current_phase || "unknown phase"}
                  </span>
                  {run.error && <span style={{ fontSize: 11, color: T.red }}>{String(run.error).slice(0,120)}</span>}
                  {run.completed_at && (
                    <span style={{ fontSize: 11, color: T.textSoft }}>
                      Failed: {new Date(run.completed_at).toLocaleString()}
                    </span>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 5 — PIPELINE
// ─────────────────────────────────────────────────────────────────────────────

// ─── Sequential Phase-by-Phase Pipeline viewer ───────────────────────────────
// Phase group label colors for section headers
const GROUP_LABEL_COLOR = {
  collection: "#0d9488", analysis: "#0891b2", scoring: "#d97706",
  structure: "#ea580c", planning: "#2563eb", content: "#7c3aed",
}

// ─── Phase Result Panel — fetches, displays, and edits phase output ───────────
const INTENT_OPTS = ["transactional","informational","commercial","local","comparison","navigational","question"]

function PhaseResultPanel({ runId, phase, phaseEvent }) {
  const [data, setData]         = useState(null)
  const [loading, setLoading]   = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editItems, setEditItems] = useState([])
  const [addInput, setAddInput]   = useState("")
  const [saving, setSaving]       = useState(false)
  const [saved, setSaved]         = useState(false)
  const [hasOverride, setHasOverride] = useState(false)

  // Fetch phase result on first expand
  useEffect(() => {
    if (!runId || !phase) return
    setLoading(true)
    apiCall(`/api/runs/${runId}/phase-results`)
      .then(r => {
        const phaseData = r?.phases?.[phase]
        setData(phaseData || null)
        if (phaseData?.user_override) {
          setEditItems(phaseData.user_override)
          setHasOverride(true)
        } else if (phaseData?.result_sample) {
          const s = phaseData.result_sample
          if (s.type === "list") setEditItems(s.items || [])
          else if (s.type === "dict" || s.type === "object") setEditItems(s.items || [])
          else setEditItems([])
        }
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [runId, phase])

  const sample = data?.result_sample
  const displayItems = hasOverride && data?.user_override ? data.user_override : (sample?.items || [])
  const isList = !sample || sample.type === "list"
  const isDict = sample?.type === "dict" || sample?.type === "object"

  const saveOverride = async () => {
    setSaving(true)
    try {
      await apiCall(`/api/runs/${runId}/phase-override`, "POST", { phase, items: editItems })
      setSaved(true); setHasOverride(true)
      setData(prev => prev ? { ...prev, user_override: editItems } : prev)
      setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false); setEditMode(false) }
  }

  const revertOverride = async () => {
    await apiCall(`/api/runs/${runId}/phase-override/${phase}`, "DELETE")
    setHasOverride(false)
    setEditItems(sample?.type === "list" ? (sample.items || []) : (sample?.items || []))
  }

  const addItem = () => {
    if (!addInput.trim()) return
    setEditItems(prev => isList ? [...prev, addInput.trim()] : [...prev, [addInput.trim(), ""]])
    setAddInput("")
  }

  const deleteItem = (idx) => setEditItems(prev => prev.filter((_, i) => i !== idx))

  const updateItem = (idx, value, col = 0) => setEditItems(prev => {
    const next = [...prev]
    if (isList) {
      next[idx] = value
    } else {
      const row = Array.isArray(next[idx]) ? [...next[idx]] : [next[idx], ""]
      row[col] = value
      next[idx] = row
    }
    return next
  })

  if (loading) return (
    <div style={{ padding: "8px 12px", fontSize: 11, color: T.textSoft }}>Loading results…</div>
  )
  if (!data && !loading) return (
    <div style={{ padding: "8px 12px", fontSize: 11, color: T.textSoft }}>
      No stored result yet — results are captured as the phase runs.
    </div>
  )

  const items = editMode ? editItems : displayItems

  return (
    <div style={{ padding: "8px 12px 12px" }}>
      {/* Summary row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 11, color: T.textSoft, flex: 1 }}>
          {data.msg}
          {hasOverride && (
            <span style={{ marginLeft: 6, fontSize: 10, color: T.amber, fontWeight: 600 }}>⚠ Edited</span>
          )}
        </span>
        {!editMode && (
          <Btn small onClick={() => { setEditMode(true); setEditItems(displayItems) }}>✎ Edit</Btn>
        )}
        {hasOverride && !editMode && (
          <Btn small onClick={revertOverride} style={{ color: T.red }}>↺ Revert</Btn>
        )}
        {editMode && (
          <>
            <Btn small variant="teal" onClick={saveOverride} disabled={saving}>
              {saving ? "Saving…" : saved ? "✓ Saved!" : "Save"}
            </Btn>
            <Btn small onClick={() => setEditMode(false)}>Cancel</Btn>
          </>
        )}
      </div>

      {/* List type (P2, P3, P14) */}
      {isList && (
        <div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: editMode ? 8 : 0 }}>
            {items.map((item, idx) => (
              <div key={idx} style={{
                display: "inline-flex", alignItems: "center", gap: 4,
                padding: "3px 8px", borderRadius: 99, fontSize: 11, fontWeight: 500,
                background: T.purpleLight, border: `1px solid ${T.purple}22`,
              }}>
                {editMode ? (
                  <input
                    value={item}
                    onChange={e => updateItem(idx, e.target.value)}
                    style={{ border: "none", background: "transparent", fontSize: 11,
                             width: Math.max(60, item.length * 7), outline: "none" }}
                  />
                ) : (
                  <span style={{ color: T.purple }}>{item}</span>
                )}
                {editMode && (
                  <button onClick={() => deleteItem(idx)}
                    style={{ background: "none", border: "none", cursor: "pointer",
                             color: T.red, fontSize: 12, padding: 0, lineHeight: 1 }}>✕</button>
                )}
              </div>
            ))}
          </div>
          {editMode && (
            <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
              <input
                placeholder="Add keyword…"
                value={addInput}
                onChange={e => setAddInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && addItem()}
                style={{ flex: 1, padding: "5px 10px", borderRadius: 7, fontSize: 11,
                         border: `1px solid ${T.border}` }}
              />
              <Btn small onClick={addItem}>+ Add</Btn>
            </div>
          )}
          <div style={{ fontSize: 10, color: T.textSoft, marginTop: 6 }}>
            {items.length} items{items.length === 150 ? " (showing first 150)" : ""}
          </div>
        </div>
      )}

      {/* Dict / object type (P4 entities, P5 intent, P7 scores, P8 topics) */}
      {isDict && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 4,
                        fontSize: 11, marginBottom: 4 }}>
            <span style={{ color: T.textSoft, fontWeight: 600 }}>Key</span>
            <span style={{ color: T.textSoft, fontWeight: 600 }}>Value</span>
            <span/>
          </div>
          <div style={{ maxHeight: 260, overflowY: "auto", display: "flex", flexDirection: "column", gap: 3 }}>
            {items.map((row, idx) => {
              const [k, v] = Array.isArray(row) ? row : [row, ""]
              return (
                <div key={idx} style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto",
                                        gap: 4, alignItems: "center" }}>
                  <div style={{ fontSize: 11, padding: "3px 6px", borderRadius: 5,
                                background: T.grayLight, fontWeight: 500 }}>{k}</div>
                  {editMode ? (
                    phase === "P5" ? (
                      <select value={v} onChange={e => updateItem(idx, e.target.value, 1)}
                        style={{ fontSize: 11, padding: "3px 6px", borderRadius: 5,
                                 border: `1px solid ${T.border}` }}>
                        {INTENT_OPTS.map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input value={v} onChange={e => updateItem(idx, e.target.value, 1)}
                        style={{ fontSize: 11, padding: "3px 6px", borderRadius: 5,
                                 border: `1px solid ${T.border}` }}/>
                    )
                  ) : (
                    <div style={{ fontSize: 11, padding: "3px 6px", borderRadius: 5,
                                  background: "#f8fafc", color: T.textSoft }}>{v}</div>
                  )}
                  {editMode && (
                    <button onClick={() => deleteItem(idx)}
                      style={{ background: "none", border: "none", cursor: "pointer",
                               color: T.red, fontSize: 12 }}>✕</button>
                  )}
                </div>
              )
            })}
          </div>
          {editMode && (
            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              <input placeholder="Key" value={addInput} onChange={e => setAddInput(e.target.value)}
                style={{ flex: 1, padding: "5px 10px", borderRadius: 7, fontSize: 11,
                         border: `1px solid ${T.border}` }}/>
              <Btn small onClick={() => {
                if (!addInput.trim()) return
                setEditItems(prev => [...prev, [addInput.trim(), ""]])
                setAddInput("")
              }}>+ Add Row</Btn>
            </div>
          )}
          <div style={{ fontSize: 10, color: T.textSoft, marginTop: 6 }}>
            {items.length} entries{items.length >= 100 ? " (showing first 100)" : ""}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Pillar Phase Card ────────────────────────────────────────────────────────
function PillarPhaseCard({ run, events, awaitingPhase, currentPhase, onNext, phases, phaseStartTimes }) {
  const [tick, setTick] = useState(0)
  const [expandedPhases, setExpandedPhases] = useState({})

  useEffect(() => {
    const t = setInterval(() => setTick(v => v + 1), 1000)
    return () => clearInterval(t)
  }, [])

  const toggleExpand = (ph) => setExpandedPhases(prev => ({ ...prev, [ph]: !prev[ph] }))

  // Find total completed, current index
  const completedKeys = new Set(
    Object.entries(events)
      .filter(([, ev]) => ev.complete)
      .map(([k]) => k)
  )
  const totalPhases = phases.length
  const completedCount = phases.filter(p => completedKeys.has(p.key)).length
  const progressPct = totalPhases > 0 ? Math.round(completedCount / totalPhases * 100) : 0

  // Phase that is awaiting user → show big "Next" button
  const awaitingIdx = awaitingPhase ? phases.findIndex(p => p.key === awaitingPhase) : -1
  const nextPhaseKey = awaitingIdx >= 0 && awaitingIdx < phases.length - 1
    ? phases[awaitingIdx + 1]?.key : null
  const nextPhaseName = nextPhaseKey ? phases.find(p => p.key === nextPhaseKey)?.name : null

  const isFullyDone = completedCount === totalPhases || (run.status === "complete" && !awaitingPhase)

  // Group phases by group for section headers
  const groups = []
  let lastGroup = null
  phases.forEach((ph, idx) => {
    if (ph.group !== lastGroup) {
      groups.push({ type: "header", group: ph.group, idx })
      lastGroup = ph.group
    }
    groups.push({ type: "phase", phase: ph, idx })
  })

  return (
    <Card style={{ marginBottom: 12, borderColor: currentPhase ? T.purple + "66" : T.border }}>
      {/* Card header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        {/* Running dot or done check */}
        <div style={{
          width: 10, height: 10, borderRadius: "50%",
          background: isFullyDone ? T.green : currentPhase ? T.purple : T.amber,
          animation: currentPhase ? "pulse 1.5s infinite" : "none",
          flexShrink: 0,
        }}/>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>{run.seed || run.pillar}</div>
          <div style={{ fontSize: 11, color: T.textSoft }}>
            {isFullyDone
              ? `All ${totalPhases} phases complete`
              : currentPhase
              ? `Running: ${phases.find(p => p.key === currentPhase)?.name || currentPhase}…`
              : awaitingPhase
              ? `Paused after ${awaitingPhase} — click Next to continue`
              : `${completedCount}/${totalPhases} phases`}
          </div>
        </div>
        {/* Progress fraction */}
        <div style={{ fontSize: 11, color: T.textSoft, fontVariantNumeric: "tabular-nums" }}>
          {completedCount}/{totalPhases}
        </div>
        {isFullyDone && (
          <span style={{ fontSize: 12, color: T.green, fontWeight: 600 }}>✓ Done</span>
        )}
      </div>

      {/* Overall progress bar */}
      <div style={{ height: 4, background: T.grayLight, borderRadius: 99, marginBottom: 14, overflow: "hidden" }}>
        <div style={{
          height: "100%", borderRadius: 99,
          width: `${progressPct}%`,
          background: isFullyDone ? T.green : T.purple,
          transition: "width 0.4s ease",
        }}/>
      </div>

      {/* Phase list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {groups.map((item, i) => {
          if (item.type === "header") {
            return (
              <div key={`hdr-${item.group}`} style={{
                fontSize: 9, fontWeight: 700, color: GROUP_LABEL_COLOR[item.group] || T.gray,
                textTransform: "uppercase", letterSpacing: ".08em",
                padding: "8px 0 3px", marginTop: i > 0 ? 4 : 0,
              }}>
                {item.group}
              </div>
            )
          }

          const { phase: ph } = item
          const ev = events[ph.key] || {}
          const isDone      = !!ev.complete
          const isRunning   = ph.key === currentPhase
          const isAwaiting  = ph.key === awaitingPhase
          const isPending   = !isDone && !isRunning && !isAwaiting
          const hasError    = !!ev.error
          const groupColor  = PHASE_GROUP_COLOR[ph.group] || T.gray
          const etaMs       = PHASE_ETA_MS[ph.key] || 3000

          // Live elapsed for running phase
          const startKey = `${run.run_id}:${ph.key}`
          const startTs  = phaseStartTimes.current?.[startKey]
          const liveElapsed = startTs && isRunning ? Math.floor((Date.now() - startTs) / 1000) : 0
          const doneElapsed = ev.complete?.elapsed_ms ? Math.round(ev.complete.elapsed_ms / 1000) : 0
          const fillPct = isRunning
            ? Math.min(liveElapsed * 1000 / etaMs * 100, 95)
            : isDone ? 100 : 0

          const expanded = expandedPhases[ph.key]

          return (
            <div key={ph.key} style={{
              borderRadius: 7,
              border: `1px solid ${isAwaiting ? T.purple + "55" : isDone ? "#e5e7eb" : isRunning ? groupColor + "44" : "transparent"}`,
              overflow: "hidden",
              background: isAwaiting ? T.purpleLight + "88" : isRunning ? groupColor + "08" : "transparent",
              marginBottom: isAwaiting ? 2 : 0,
            }}>
              {/* Phase row */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                            cursor: isDone ? "pointer" : "default" }}
                   onClick={() => isDone && toggleExpand(ph.key)}>
                {/* Status icon */}
                <span style={{ fontSize: 12, width: 16, flexShrink: 0, color:
                  isDone ? T.green : isRunning ? groupColor : hasError ? T.red : "#d1d5db" }}>
                  {isDone ? "✓" : isRunning ? "●" : hasError ? "✕" : "○"}
                </span>
                {/* Phase key badge */}
                <span style={{ fontSize: 9, fontWeight: 700, color: groupColor,
                               background: groupColor + "18", borderRadius: 4,
                               padding: "1px 5px", flexShrink: 0 }}>
                  {ph.key}
                </span>
                {/* Phase name */}
                <span style={{ fontSize: 12, flex: 1, fontWeight: isDone || isRunning ? 500 : 400,
                               color: isPending ? "#9ca3af" : T.text }}>
                  {ph.name}
                </span>
                {/* Right side: output count or elapsed */}
                {isDone && ev.complete?.output_count != null && (
                  <span style={{ fontSize: 11, color: groupColor, fontWeight: 600 }}>
                    {ev.complete.output_count} items
                  </span>
                )}
                {isDone && doneElapsed > 0 && (
                  <span style={{ fontSize: 10, color: T.textSoft }}>{doneElapsed}s</span>
                )}
                {isRunning && liveElapsed > 0 && (
                  <span style={{ fontSize: 10, color: groupColor }}>{liveElapsed}s…</span>
                )}
                {isDone && (
                  <span style={{ fontSize: 10, color: T.textSoft }}>{expanded ? "▲" : "▼"}</span>
                )}
              </div>

              {/* Mini progress bar (only for running) */}
              {(isRunning || isDone) && (
                <div style={{ height: 2, background: "#f3f4f6", marginTop: -1 }}>
                  <div style={{
                    height: "100%",
                    width: `${fillPct}%`,
                    background: isDone ? T.green : groupColor,
                    transition: isDone ? "none" : "none",
                  }}/>
                </div>
              )}

              {/* Expanded result — full editable panel */}
              {isDone && expanded && (
                <div style={{ borderTop: "1px solid #f3f4f6" }}>
                  <PhaseResultPanel
                    runId={run.run_id}
                    phase={ph.key}
                    phaseEvent={ev.complete}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* "Next Phase" button — only shows when awaiting */}
      {awaitingPhase && !isFullyDone && (
        <div style={{
          marginTop: 14, padding: "12px 14px",
          background: T.purpleLight, borderRadius: 8,
          border: `1px solid ${T.purple}33`,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: T.purple }}>
              {awaitingPhase} complete
            </div>
            <div style={{ fontSize: 11, color: T.textSoft }}>
              {events[awaitingPhase]?.complete?.msg || `${phases.find(p => p.key === awaitingPhase)?.name} finished`}
            </div>
            {events[awaitingPhase]?.complete?.output_count != null && (
              <div style={{ fontSize: 11, color: T.text, marginTop: 2 }}>
                <strong>{events[awaitingPhase].complete.output_count}</strong> items produced
              </div>
            )}
          </div>
          <Btn variant="primary" onClick={() => onNext(run.run_id, awaitingPhase)}
               style={{ flexShrink: 0, marginLeft: 12 }}>
            {nextPhaseName ? `▶ Next: ${nextPhaseName}` : "▶ Finish Pipeline"}
          </Btn>
        </div>
      )}

      {/* Done state */}
      {isFullyDone && (
        <div style={{ marginTop: 10, padding: "8px 12px", background: T.greenLight,
                      borderRadius: 8, fontSize: 12, color: T.green, fontWeight: 600 }}>
          ✓ Pipeline complete — {completedCount} phases, {
            phases.reduce((sum, p) => sum + (events[p.key]?.complete?.output_count || 0), 0)
          } total items processed
        </div>
      )}
    </Card>
  )
}

function StepPipeline({ projectId, onComplete, onBack }) {
  const notify = useNotification(s => s.notify)
  const [mode, setMode]       = useState("select") // select | running | done
  const [error, setError]     = useState("")
  const [runs, setRuns]       = useState([])        // [{run_id, seed, status}]

  // Per-run phase events: runId → { P1: {starting?, complete?, error?}, ... }
  const [phaseEvents, setPhaseEvents]       = useState({})
  // Per-run: which phase is currently running
  const [currentPhase, setCurrentPhase]     = useState({})
  // Per-run: which phase is paused awaiting "Next"
  const [awaitingNext, setAwaitingNext]     = useState({})

  // Pillar selection (select mode)
  const [selectedPillars, setSelectedPillars] = useState([])

  const phaseStartRef = useRef({}) // "runId:phase" → Date.now()
  const sseRef        = useRef({}) // runId → EventSource

  // Cleanup SSE on unmount
  useEffect(() => () => Object.values(sseRef.current).forEach(es => es?.close()), [])

  // Load pillar status for selection
  const { data: pillarData, isLoading: pillarsLoading } = useQuery({
    queryKey: ["ki-pillar-status", projectId],
    queryFn:  () => apiCall(`/api/ki/${projectId}/pillar-status`),
    enabled:  !!projectId && mode === "select",
  })
  const allPillars = pillarData?.pillars || []

  // ── SSE listener per run ──────────────────────────────────────────────────

  const startSSE = (runId) => {
    if (sseRef.current[runId]) return
    const es = new EventSource(`${API}/api/runs/${runId}/stream`)

    es.addEventListener("message", (e) => {
      try {
        const payload = JSON.parse(e.data)

        if (payload.type === "phase_log") {
          const phase  = payload.phase
          const status = payload.status
          if (!phase) return

          if (status === "starting") {
            phaseStartRef.current[`${runId}:${phase}`] = Date.now()
            setCurrentPhase(prev => ({ ...prev, [runId]: phase }))
          }

          setPhaseEvents(prev => {
            const runEv  = { ...(prev[runId] || {}) }
            const phEv   = { ...(runEv[phase] || {}) }
            phEv[status] = payload
            runEv[phase] = phEv
            return { ...prev, [runId]: runEv }
          })

          if (status === "complete") {
            // Pipeline is now blocked — waiting for /next-phase
            setCurrentPhase(prev => ({ ...prev, [runId]: null }))
            setAwaitingNext(prev => ({ ...prev, [runId]: phase }))
          }

          if (status === "error") {
            setCurrentPhase(prev => ({ ...prev, [runId]: null }))
          }
        }

        if (payload.type === "run_complete") {
          setRuns(prev => prev.map(r => r.run_id === runId ? { ...r, status: "complete" } : r))
          setCurrentPhase(prev => ({ ...prev, [runId]: null }))
          setAwaitingNext(prev => { const n = { ...prev }; delete n[runId]; return n })
          es.close()
        }

        if (payload.type === "run_error") {
          setRuns(prev => prev.map(r => r.run_id === runId ? { ...r, status: "error" } : r))
          es.close()
        }

      } catch {}
    })

    es.addEventListener("error", () => { es.close() })
    sseRef.current[runId] = es
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  const startPipeline = async () => {
    if (!selectedPillars.length) { setError("Select at least one pillar"); return }
    setError("")
    try {
      const r = await apiCall(`/api/ki/${projectId}/run-pipeline`, "POST", {
        selected_pillars: selectedPillars,
        sequential: true,
      })
      if (r?.runs) {
        setRuns(r.runs.map(run => ({ ...run, status: "queued" })))
        setMode("running")
        r.runs.forEach(run => startSSE(run.run_id))
      } else {
        setError(typeof r?.detail === 'string' ? r.detail : Array.isArray(r?.detail) ? r.detail.map(e=>e.msg||String(e)).join('; ') : "Failed to start pipeline")
      }
    } catch (e) { setError(String(e)) }
  }

  const clickNext = async (runId, phase) => {
    try {
      await apiCall(`/api/runs/${runId}/next-phase`, "POST")
      setAwaitingNext(prev => { const n = { ...prev }; delete n[runId]; return n })
    } catch (e) { console.error("next-phase failed", e) }
  }

  const allComplete = runs.length > 0 && runs.every(r =>
    r.status === "complete" || r.status === "error"
  )

  // ── SELECT MODE ───────────────────────────────────────────────────────────

  if (mode === "select") {
    const togglePillar = (kw) => setSelectedPillars(prev =>
      prev.includes(kw) ? prev.filter(k => k !== kw) : [...prev, kw]
    )

    return (
      <div>
        {/* Header */}
        <Card style={{ marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 2 }}>
                Step 5 — Keyword Universe Pipeline
              </div>
              <div style={{ fontSize: 12, color: T.textSoft }}>
                Phases run one at a time. Review each result and click "Next Phase" to continue.
              </div>
            </div>
          </div>

          {/* Phase overview strip */}
          <div style={{ overflowX: "auto", marginBottom: 14 }}>
            <div style={{ display: "flex", gap: 3, alignItems: "center", minWidth: 0 }}>
              {STEP5_PHASES.map((ph, i) => (
                <div key={ph.key} style={{ display: "flex", alignItems: "center" }}>
                  <div style={{
                    padding: "3px 8px", borderRadius: 6, fontSize: 9, fontWeight: 700,
                    background: (PHASE_GROUP_COLOR[ph.group] || T.gray) + "18",
                    color: PHASE_GROUP_COLOR[ph.group] || T.gray, whiteSpace: "nowrap",
                  }}>
                    {ph.key}
                  </div>
                  {i < STEP5_PHASES.length - 1 && (
                    <div style={{ width: 8, height: 1, background: T.border, flexShrink: 0 }}/>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Pillar selection */}
          <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft,
                        textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>
            Select Pillars to Run
          </div>

          {pillarsLoading ? (
            <div style={{ color: T.textSoft, fontSize: 12, padding: "8px 0" }}>Loading pillars…</div>
          ) : allPillars.length === 0 ? (
            <div style={{ color: T.red, fontSize: 12, padding: "8px 12px", background: "#fef2f2", borderRadius: 8 }}>
              No confirmed pillar keywords. Complete Steps 1–4 first.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 12 }}>
              {allPillars.map(p => (
                <label key={p.keyword} style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "8px 12px", borderRadius: 8, cursor: "pointer",
                  background: selectedPillars.includes(p.keyword) ? T.purpleLight : T.grayLight,
                  border: `1px solid ${selectedPillars.includes(p.keyword) ? T.purple + "44" : "transparent"}`,
                }}>
                  <input type="checkbox" style={{ accentColor: T.purple }}
                    checked={selectedPillars.includes(p.keyword)}
                    onChange={() => togglePillar(p.keyword)} />
                  <span style={{ fontSize: 13, fontWeight: 500, flex: 1 }}>{p.keyword}</span>
                  {p.status === "complete" && (
                    <span style={{ fontSize: 10, color: T.teal, padding: "2px 8px",
                                   background: T.tealLight, borderRadius: 99, fontWeight: 600 }}>
                      ✓ Scanned
                    </span>
                  )}
                  {p.cluster_count > 0 && (
                    <span style={{ fontSize: 10, color: T.textSoft }}>{p.cluster_count} clusters</span>
                  )}
                </label>
              ))}
              <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                <Btn small onClick={() => setSelectedPillars(allPillars.map(p => p.keyword))}>Select All</Btn>
                <Btn small onClick={() => setSelectedPillars(allPillars.filter(p => p.status !== "complete").map(p => p.keyword))}>
                  Unscanned Only
                </Btn>
                <Btn small onClick={() => setSelectedPillars([])}>Clear</Btn>
              </div>
            </div>
          )}

          {error && (
            <div style={{ color: T.red, fontSize: 12, marginBottom: 10,
                          padding: "8px 12px", background: "#fef2f2", borderRadius: 8 }}>⚠ {error}</div>
          )}

          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={onBack}>← Back</Btn>
            <Btn variant="primary" onClick={startPipeline} disabled={!selectedPillars.length || pillarsLoading}>
              ▶ Run Pipeline ({selectedPillars.length} pillar{selectedPillars.length !== 1 ? "s" : ""})
            </Btn>
          </div>
        </Card>
      </div>
    )
  }

  // ── RUNNING MODE ──────────────────────────────────────────────────────────

  return (
    <div>
      {/* Header */}
      <Card style={{ marginBottom: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>
              Step 5 — Keyword Universe Pipeline
            </div>
            <div style={{ fontSize: 12, color: T.textSoft }}>
              {allComplete
                ? `All ${runs.length} pillar${runs.length !== 1 ? "s" : ""} complete`
                : Object.values(awaitingNext).length > 0
                ? "Paused — review the phase result and click Next to continue"
                : "Running phases… each phase processes and refines your keyword universe"}
            </div>
          </div>
          {allComplete && (
            <Btn variant="primary" onClick={onComplete}>View Clusters →</Btn>
          )}
        </div>

        {/* Overall pipeline phase strip */}
        <div style={{ overflowX: "auto", marginTop: 8 }}>
          <div style={{ display: "flex", gap: 2, alignItems: "center" }}>
            {STEP5_PHASES.map((ph, i) => {
              // Aggregate status across all runs for this phase
              const anyDone    = runs.some(r => phaseEvents[r.run_id]?.[ph.key]?.complete)
              const anyRunning = runs.some(r => currentPhase[r.run_id] === ph.key)
              const anyAwaiting= runs.some(r => awaitingNext[r.run_id] === ph.key)
              const color = PHASE_GROUP_COLOR[ph.group] || T.gray
              return (
                <div key={ph.key} style={{ display: "flex", alignItems: "center" }}>
                  <div style={{
                    padding: "2px 7px", borderRadius: 5, fontSize: 9, fontWeight: 700,
                    background: anyDone    ? T.green + "22"
                               : anyAwaiting ? T.purple + "22"
                               : anyRunning  ? color + "30"
                               : T.grayLight,
                    color: anyDone    ? T.green
                           : anyAwaiting ? T.purple
                           : anyRunning  ? color
                           : "#9ca3af",
                    border: anyAwaiting ? `1px solid ${T.purple}55` : "1px solid transparent",
                  }}>
                    {ph.key}
                  </div>
                  {i < STEP5_PHASES.length - 1 && (
                    <div style={{ width: 5, height: 1, background: anyDone ? T.green : T.border }}/>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </Card>

      {/* Per-pillar phase cards */}
      {runs.map(run => (
        <PillarPhaseCard
          key={run.run_id}
          run={run}
          events={phaseEvents[run.run_id] || {}}
          awaitingPhase={awaitingNext[run.run_id] || null}
          currentPhase={currentPhase[run.run_id] || null}
          onNext={clickNext}
          phases={STEP5_PHASES}
          phaseStartTimes={phaseStartRef}
        />
      ))}

      {/* Done CTA */}
      {allComplete && (
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <Btn onClick={() => { setMode("select"); setRuns([]); setPhaseEvents({}); setCurrentPhase({}); setAwaitingNext({}) }}>
            ← Run Another Pillar
          </Btn>
          <Btn variant="primary" onClick={onComplete}>Continue to Clusters →</Btn>
        </div>
      )}
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// STEP 6 — CLUSTERS
// ─────────────────────────────────────────────────────────────────────────────

function StepClusters({ projectId, onComplete, onBack }) {
  const notify = useNotification(s => s.notify)
  const [expanded, setExpanded] = useState({})
  const [renames, setRenames]   = useState({})
  const [genPillar, setGenPillar] = useState("")
  const [generating, setGenerating] = useState(false)
  const [genResult, setGenResult]   = useState([])

  const { data, refetch } = useQuery({
    queryKey: ["ki-clusters", projectId],
    queryFn: () => apiCall(`/api/ki/${projectId}/clusters`),
  })

  const byPillar = data?.by_pillar || {}
  const pillars = Object.keys(byPillar)

  const togglePillar = (p) => setExpanded(e => ({ ...e, [p]: !e[p] }))

  const generateForPillar = async (pillar) => {
    const clusters = byPillar[pillar] || []
    const kws = clusters.flatMap(c => c.keywords || [])
    if (!kws.length) return
    setGenerating(true)
    try {
      const r = await apiCall(`/api/ki/${projectId}/clusters/generate`, "POST",
        { pillar, keywords: kws })
      setGenResult(r.clusters || [])
    } catch (e) {} finally { setGenerating(false) }
  }

  // blogs-per-day capacity estimate
  const capacityNote = (count) => {
    const months = Math.round(count / 1.5)  // assuming 1-3 blogs per cluster
    return `~${months} months of content at 1–3/day`
  }

  return (
    <div>
      <Card style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Step 6 — Clusters</div>
        <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 4 }}>
          Clusters are the content units for your 2-year publishing plan. Each cluster = 1–5 blog articles.
        </div>
        <div style={{ fontSize: 12, color: T.purple }}>
          {data?.total_clusters || 0} clusters across {data?.total_pillars || 0} pillars
        </div>
      </Card>

      {pillars.length === 0 && (
        <Card>
          <div style={{ color: T.textSoft, fontSize: 13, textAlign: "center" }}>
            No clusters yet. Complete Step 5 (Pipeline) to generate clusters.
          </div>
        </Card>
      )}

      {pillars.map(pillar => {
        const clusters = byPillar[pillar] || []
        const isOpen = expanded[pillar]
        return (
          <Card key={pillar} style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", alignItems: "center", cursor: "pointer", gap: 10 }}
              onClick={() => togglePillar(pillar)}>
              <span style={{ fontSize: 16 }}>{isOpen ? "▼" : "▶"}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{pillar}</div>
                <div style={{ fontSize: 11, color: T.textSoft }}>
                  {clusters.length} clusters — {capacityNote(clusters.length)}
                </div>
              </div>
              <Badge color={clusters.length >= 24 ? T.green : T.amber}>
                {clusters.length >= 24 ? "2yr ready" : `${clusters.length} clusters`}
              </Badge>
            </div>

            {isOpen && (
              <div style={{ marginTop: 12 }}>
                {clusters.map((c, i) => (
                  <div key={i} style={{ padding: "8px 10px", borderRadius: 8,
                                         background: T.grayLight, marginBottom: 6 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontWeight: 500, fontSize: 13 }}>
                        {renames[`${pillar}:${c.cluster_name}`] || c.cluster_name}
                      </span>
                      <Badge color={T.purple}>{c.keyword_count} kw</Badge>
                      {c.intent && <Badge color={intentColor(c.intent)}>{c.intent}</Badge>}
                    </div>
                    <div style={{ fontSize: 11, color: T.textSoft, marginTop: 4 }}>
                      {(c.keywords || []).slice(0,5).join(" · ")}
                      {c.keyword_count > 5 && ` + ${c.keyword_count - 5} more`}
                    </div>
                  </div>
                ))}
                {clusters.length < 24 && (
                  <div style={{ marginTop: 8 }}>
                    <Btn small variant="teal" onClick={() => generateForPillar(pillar)} disabled={generating}>
                      {generating ? "Generating…" : "Generate more clusters"}
                    </Btn>
                  </div>
                )}
              </div>
            )}
          </Card>
        )
      })}

      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <Btn onClick={onBack}>← Back</Btn>
        <Btn variant="primary" onClick={onComplete} style={{ marginLeft: "auto" }}>
          Open Content Calendar →
        </Btn>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 7 — CALENDAR HANDOFF
// ─────────────────────────────────────────────────────────────────────────────

function StepCalendar({ projectId, onGoToCalendar, onBack }) {
  const { data } = useQuery({
    queryKey: ["ki-clusters-summary", projectId],
    queryFn: () => apiCall(`/api/ki/${projectId}/clusters`),
  })
  const totalClusters = data?.total_clusters || 0
  const totalPillars  = data?.total_pillars  || 0

  return (
    <Card>
      <div style={{ textAlign: "center", padding: "20px 0" }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>🎉</div>
        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>Keyword Workflow Complete!</div>
        <div style={{ fontSize: 13, color: T.textSoft, maxWidth: 400, margin: "0 auto 20px" }}>
          You have {totalClusters} content clusters across {totalPillars} pillar topics — enough for
          {" "}<strong>{Math.round(totalClusters * 2)} months</strong> of publishing at 2 articles/week.
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "center" }}>
          <Btn variant="primary" onClick={onGoToCalendar}>
            📅 Open Content Calendar
          </Btn>
          <div style={{ fontSize: 12, color: T.textSoft }}>
            Schedule your clusters, freeze articles, and set up your 2-year publishing calendar.
          </div>
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        <Btn onClick={onBack}>← Back to Clusters</Btn>
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN: KeywordWorkflow
// ─────────────────────────────────────────────────────────────────────────────

export default function KeywordWorkflow({ projectId, onGoToCalendar, setPage }) {
  const notify = useNotification(s => s.notify)
  const [step, setStep]                 = useState(1)
  const [sessionId, setSessionId]       = useState(null)
  const [customerUrl, setCustomerUrl]   = useState("")
  const [competitorUrls, setCompetitorUrls] = useState([])
  const [businessIntent, setBusinessIntent] = useState(["mixed"])  // Task 6 — array to match StepInput
  const [strategyContext, setStrategyContext] = useState(null)  // From Step 2
  const [skipDashboard, setSkipDashboard] = useState(false)

  const [workflowStatus, setWorkflowStatus] = useState(null)
  const [workflowLoading, setWorkflowLoading] = useState(false)

  const stageToStep = {
    input: 1,
    strategy: 2,
    research: 3,
    review: 4,
    ai_review: 5,
    pipeline: 6,
    clusters: 7,
    calendar: 8,
  }

  const stepToStage = {
    1: 'input',
    2: 'strategy',
    3: 'research',
    4: 'review',
    5: 'ai_review',
    6: 'pipeline',
    7: 'clusters',
    8: 'calendar',
  }

  const fetchWorkflowStatus = async () => {
    if (!projectId) return
    setWorkflowLoading(true)
    try {
      const res = await apiCall(`/api/ki/${projectId}/workflow-status`)
      setWorkflowStatus(res)
    } catch (e) {
      console.error("Workflow status fetch failed", e)
    } finally {
      setWorkflowLoading(false)
    }
  }

  const handleAdvance = async (targetStep) => {
    if (!workflowStatus) {
      notify("Workflow status not available yet", "warning")
      return
    }

    const allowedStep = stageToStep[workflowStatus.current_stage] || 1
    if (targetStep > allowedStep + 1) {
      notify("Complete previous steps before moving forward", "warning")
      return
    }
    if (targetStep === allowedStep + 1 && !workflowStatus.can_advance) {
      if (targetStep === 2) {
        notify("Complete Step 1 (Input) with pillars before Step 2 (Strategy)", "warning")
      } else if (targetStep === 3) {
        notify("Complete Step 2 (Strategy) before Step 3 (Research)", "warning")
      } else if (targetStep === 6) {
        notify("Complete Step 5 (AI Check) before Step 6 (Pipeline)", "warning")
      } else {
        notify("Complete current step before advancing", "warning")
      }
      return
    }

    try {
      const res = await apiCall(`/api/ki/${projectId}/workflow/advance`, "POST")
      await fetchWorkflowStatus()
      const nextStep = stageToStep[res.next_stage] || targetStep
      setStep(nextStep)
    } catch (e) {
      const errMsg = e?.message || e?.detail || String(e)
      notify("Workflow advance failed: " + errMsg, "error")
    }
  }

  const handleGoToStep = (s, sid) => {
    if (sid) setSessionId(sid)
    if (!workflowStatus) {
      setStep(s)
      return
    }
    const allowedStep = stageToStep[workflowStatus.current_stage] || 1
    if (s > allowedStep + 1) {
      notify("Please complete previous step(s) first", "warning")
      return
    }
    if (s === allowedStep + 1 && !workflowStatus.can_advance) {
      if (s === 3) {
        notify("Complete Step 2 (Strategy) before advancing to Step 3 (Research)", "warning")
      } else if (s === 6) {
        notify("Complete Step 5 (AI Check) before advancing to Step 6 (Pipeline)", "warning")
      } else {
        notify("Complete the current step before advancing to the next step", "warning")
      }
      return
    }
    setStep(s)
  }

  const { data: dashData, isLoading: dashLoading } = useQuery({
    queryKey: ["ki-dashboard", projectId],
    queryFn: () => apiCall(`/api/ki/${projectId}/dashboard`),
    enabled: !!projectId,
  })

  useEffect(() => {
    if (!projectId) return
    fetchWorkflowStatus()
  }, [projectId])

  useEffect(() => {
    if (!workflowStatus) return
    const desiredStep = stageToStep[workflowStatus.current_stage] || 1
    if (step !== desiredStep) setStep(desiredStep)
  }, [workflowStatus])

  const handleStep1Done = async ({ sessionId: sid, customerUrl: url, competitorUrls: urls, businessIntent: bi }) => {
    setSessionId(sid)
    setCustomerUrl(url)
    setCompetitorUrls(urls)
    if (bi) setBusinessIntent(bi)  // Task 6
    await fetchWorkflowStatus()
    await handleAdvance(2)
  }

  // Show dashboard when: not skipped, on step 1, and project has keywords
  const showDashboard = !skipDashboard && step === 1 && dashData?.has_keywords === true

  if ((dashLoading || workflowLoading) && step === 1 && !skipDashboard) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <div style={{ textAlign: "center", padding: 60, color: T.textSoft }}>
          <Spinner />
          <div style={{ fontSize: 13, marginTop: 12 }}>Loading keyword intelligence…</div>
        </div>
      </div>
    )
  }

  if (showDashboard) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto" }}>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <KeywordDashboard
          projectId={projectId}
          onGoToStep={handleGoToStep}
          onStartFresh={() => { setSkipDashboard(true); setStep(1) }}
        />
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <ProgressBar step={step - 1} />

      {step === 1 && <StepInput projectId={projectId} onComplete={handleStep1Done} setPage={setPage} />}
      {step === 2 && (
        <StepStrategy projectId={projectId} sessionId={sessionId}
          customerUrl={customerUrl} competitorUrls={competitorUrls}
          businessIntent={businessIntent}
          onComplete={(ctx) => {
            if (ctx?.strategy_context) setStrategyContext(ctx.strategy_context)
            handleAdvance(3)
          }}
          onBack={() => setStep(1)} />
      )}
      {step === 3 && (
        <StepResearch projectId={projectId} sessionId={sessionId}
          customerUrl={customerUrl} competitorUrls={competitorUrls}
          businessIntent={businessIntent} strategyContext={strategyContext}
          onComplete={() => handleAdvance(4)} onBack={() => setStep(2)} />
      )}
      {step === 4 && (
        <StepReview projectId={projectId} sessionId={sessionId}
          onComplete={() => handleAdvance(5)} onBack={() => setStep(3)} workflowStatus={workflowStatus} />
      )}
      {step === 5 && (
        <StepAIReview projectId={projectId} sessionId={sessionId}
          onComplete={() => handleAdvance(6)} onBack={() => setStep(4)} />
      )}
      {step === 6 && (
        <StepPipeline projectId={projectId}
          onComplete={() => handleAdvance(7)} onBack={() => setStep(5)} />
      )}
      {step === 7 && (
        <StepClusters projectId={projectId}
          onComplete={() => handleAdvance(8)} onBack={() => setStep(6)} />
      )}
      {step === 8 && (
        <StepCalendar projectId={projectId}
          onGoToCalendar={onGoToCalendar || (() => {})}
          onBack={() => setStep(7)} />
      )}
      <DebugPanel />
    </div>
  )
}