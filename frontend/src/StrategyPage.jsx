// StrategyPage.jsx — SEO/AEO Strategy Wizard
// Step 1: Business & Audience Profile → Step 2: AI generates strategy → Step 3: Review & confirm
// Goal: Top 5 in Google search AND AI search engines

import { useState, useEffect, useRef, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

const API = import.meta.env.VITE_API_URL || ""

function authHeaders() {
  const token = localStorage.getItem("annaseo_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const T = {
  purple: "#7F77DD",
  purpleLight: "#EEEDFE",
  purpleDark: "#534AB7",
  teal: "#1D9E75",
  tealLight: "#E8F8F2",
  red: "#DC2626",
  amber: "#D97706",
  amberLight: "#FFF8E1",
  gray: "#888780",
  grayLight: "#F8F7F4",
  border: "#E5E3DC",
  text: "#1A1A1A",
  textSoft: "#666",
}

function Card({ children, style = {} }) {
  return (
    <div style={{
      background: "#fff", border: `0.6px solid ${T.border}`,
      borderRadius: 12, padding: 18, ...style,
    }}>{children}</div>
  )
}

function Btn({ children, onClick, disabled, loading, variant = "primary", small, style = {} }) {
  const base = {
    padding: small ? "5px 12px" : "8px 18px",
    borderRadius: 8, fontWeight: 600, cursor: (disabled || loading) ? "not-allowed" : "pointer",
    opacity: (disabled || loading) ? 0.6 : 1, fontSize: small ? 12 : 13,
    transition: "opacity .15s, background .15s", border: "none",
  }
  const variants = {
    primary: { background: T.purpleDark, color: "#fff" },
    teal: { background: T.teal, color: "#fff" },
    outline: { background: "#fff", color: T.purpleDark, border: `1px solid ${T.purpleDark}` },
    danger: { background: T.red, color: "#fff" },
    ghost: { background: "transparent", color: T.gray, border: `1px solid ${T.border}` },
  }
  return (
    <button onClick={onClick} disabled={disabled || loading} style={{ ...base, ...variants[variant], ...style }}>
      {loading ? "…" : children}
    </button>
  )
}

function ChipInput({ items, onChange, placeholder, color = T.purple }) {
  const [val, setVal] = useState("")
  const add = () => {
    const v = val.trim()
    if (v && !items.includes(v)) { onChange([...items, v]); setVal("") }
  }
  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        <input value={val} onChange={e => setVal(e.target.value)}
          onKeyDown={e => e.key === "Enter" && add()}
          placeholder={placeholder}
          style={{ flex: 1, padding: "6px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13 }} />
        <Btn small variant="outline" onClick={add}>+ Add</Btn>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {items.map((it, i) => (
          <span key={i} style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            padding: "3px 10px", borderRadius: 20, fontSize: 12, fontWeight: 500,
            background: color + "18", color, border: `1px solid ${color}33`,
          }}>
            {it}
            <button onClick={() => onChange(items.filter((_, j) => j !== i))}
              style={{ border: "none", background: "transparent", cursor: "pointer", color: T.red, fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>
          </span>
        ))}
      </div>
    </div>
  )
}

function StepIndicator({ step, total = 3 }) {
  const labels = ["Business Profile", "AI Generation", "Strategy Plan"]
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 24 }}>
      {labels.map((label, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", flex: 1 }}>
          <div style={{
            width: 28, height: 28, borderRadius: "50%",
            background: i + 1 <= step ? T.purpleDark : "#E5E3DC",
            color: i + 1 <= step ? "#fff" : T.gray,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontWeight: 700, fontSize: 13, flexShrink: 0,
          }}>
            {i + 1 < step ? "✓" : i + 1}
          </div>
          <div style={{
            fontSize: 11, fontWeight: i + 1 === step ? 700 : 400,
            color: i + 1 <= step ? T.purpleDark : T.gray, marginLeft: 6, flexShrink: 0,
          }}>{label}</div>
          {i < total - 1 && (
            <div style={{ flex: 1, height: 2, background: i + 1 < step ? T.purpleDark : "#E5E3DC", margin: "0 10px" }} />
          )}
        </div>
      ))}
    </div>
  )
}

// ── Step 1: Business & Audience Profile Form ──────────────────────────────────
function ProfileStep({ projectId, onNext }) {
  const qc = useQueryClient()

  // Load existing audience profile
  const { data: existing } = useQuery({
    queryKey: ["audience", projectId],
    queryFn: async () => {
      const r = await fetch(`${API}/api/strategy/${projectId}/audience`, { headers: authHeaders() })
      if (!r.ok) return null
      return r.json()
    },
    enabled: !!projectId,
    retry: false,
  })

  const { data: projectData } = useQuery({
    queryKey: ["project", projectId],
    queryFn: async () => {
      const r = await fetch(`${API}/api/projects/${projectId}`, { headers: authHeaders() })
      if (!r.ok) return {}
      return r.json()
    },
    enabled: !!projectId,
  })

  function safeL(val, def = []) {
    if (!val) return def
    if (Array.isArray(val)) return val
    try { return JSON.parse(val) } catch { return def }
  }

  const [form, setForm] = useState({
    website_url: "",
    business_type: "B2C",
    usp: "",
    target_locations: ["India"],
    target_languages: ["English"],
    target_religions: ["general"],
    personas: [],
    products: [],
    competitor_urls: [],
    customer_reviews: "",
  })

  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState([])

  // Pre-fill from existing data
  useEffect(() => {
    if (!existing && !projectData) return
    const src = existing || {}
    setForm({
      website_url: src.website_url || projectData?.customer_url || "",
      business_type: src.business_type || projectData?.business_type || "B2C",
      usp: src.usp || projectData?.usp || "",
      target_locations: safeL(src.target_locations, ["India"]),
      target_languages: safeL(src.target_languages, ["English"]),
      target_religions: safeL(src.target_religions, ["general"]),
      personas: safeL(src.personas, []),
      products: safeL(src.products, []),
      competitor_urls: safeL(src.competitor_urls || projectData?.competitor_urls, []),
      customer_reviews: src.customer_reviews || projectData?.customer_reviews || "",
    })
  }, [existing, projectData])

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }))

  const handleSave = async () => {
    const errs = []
    if (!form.target_locations.length) errs.push("Add at least one target location")
    if (!form.target_languages.length) errs.push("Add at least one target language")
    if (!form.target_religions.length) errs.push("Add at least one religion/culture")
    if (!form.personas.length) errs.push("Add at least one target audience")
    if (!form.products.length) errs.push("Add at least one product or service")
    if (errs.length) { setErrors(errs); return }
    setErrors([])
    setSaving(true)
    try {
      const r = await fetch(`${API}/api/strategy/${projectId}/audience`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(form),
      })
      if (!r.ok) {
        const d = await r.json().catch(() => ({}))
        setErrors([d?.detail || "Save failed"])
        return
      }
      qc.invalidateQueries(["audience", projectId])
      onNext()
    } catch (e) {
      setErrors([String(e)])
    } finally {
      setSaving(false)
    }
  }

  const inStyle = {
    width: "100%", padding: "7px 10px", borderRadius: 8,
    border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box",
  }
  const labelStyle = { fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 18, color: T.text }}>Business & Audience Profile</h2>
        <p style={{ margin: 0, fontSize: 13, color: T.textSoft }}>
          This information drives the AI strategy. Tell us who you are, who you serve, and where.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Left column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12, color: T.purpleDark }}>Your Business</div>
            <div style={{ marginBottom: 10 }}>
              <label style={labelStyle}>Website URL</label>
              <input value={form.website_url} onChange={e => set("website_url", e.target.value)}
                placeholder="https://yourbusiness.com" style={inStyle} />
            </div>
            <div style={{ marginBottom: 10 }}>
              <label style={labelStyle}>Business Type</label>
              <select value={form.business_type} onChange={e => set("business_type", e.target.value)} style={inStyle}>
                <option value="B2C">B2C — Selling directly to consumers</option>
                <option value="B2B">B2B — Selling to businesses</option>
                <option value="D2C">D2C — Direct-to-consumer brand</option>
                <option value="marketplace">Marketplace / Platform</option>
                <option value="publisher">Content Publisher / Blog</option>
                <option value="service">Service Business</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>Unique Selling Proposition (USP)</label>
              <textarea value={form.usp} onChange={e => set("usp", e.target.value)}
                placeholder="What makes your business special? E.g., Organic certified products, 24/7 delivery, lowest price guarantee"
                style={{ ...inStyle, height: 72, resize: "vertical", fontFamily: "inherit" }} />
            </div>
          </Card>

          <Card>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12, color: T.purpleDark }}>Products & Services</div>
            <label style={labelStyle}>List your main products or services</label>
            <ChipInput items={form.products} onChange={v => set("products", v)}
              placeholder="Add a product/service (Enter)" color={T.teal} />
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 6 }}>
              e.g., Organic Turmeric Powder, Spice Blends, Gift Hampers
            </div>
          </Card>

          <Card>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12, color: T.purpleDark }}>Competitor Websites</div>
            <ChipInput items={form.competitor_urls} onChange={v => set("competitor_urls", v)}
              placeholder="https://competitor.com (Enter)" color={T.amber} />
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 6 }}>
              We'll analyze gaps vs your competitors
            </div>
          </Card>
        </div>

        {/* Right column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12, color: T.purpleDark }}>Target Market</div>
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>Target Locations / Regions</label>
              <ChipInput items={form.target_locations} onChange={v => set("target_locations", v)}
                placeholder="Country or city (Enter)" color={T.purple} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>Target Languages</label>
              <ChipInput items={form.target_languages} onChange={v => set("target_languages", v)}
                placeholder="Language (Enter)" color={T.purple} />
              <div style={{ fontSize: 11, color: T.textSoft, marginTop: 4 }}>e.g., English, Hindi, Tamil</div>
            </div>
            <div>
              <label style={labelStyle}>Cultural / Religious Context</label>
              <ChipInput items={form.target_religions} onChange={v => set("target_religions", v)}
                placeholder="e.g., Hindu, Muslim, general (Enter)" color={T.purple} />
              <div style={{ fontSize: 11, color: T.textSoft, marginTop: 4 }}>Helps tailor content messaging and timing</div>
            </div>
          </Card>

          <Card>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12, color: T.purpleDark }}>Target Audiences</div>
            <ChipInput items={form.personas} onChange={v => set("personas", v)}
              placeholder="e.g., Health-conscious home cooks (Enter)" color={T.teal} />
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 6 }}>
              Who are your target audiences? Describe the groups you want to reach.
            </div>
            <div style={{ marginTop: 10 }}>
              <label style={labelStyle}>Customer Reviews / Insights (optional)</label>
              <textarea value={form.customer_reviews} onChange={e => set("customer_reviews", e.target.value)}
                placeholder="Paste common feedback or topics customers ask about..."
                style={{ ...inStyle, height: 72, resize: "vertical", fontFamily: "inherit" }} />
            </div>
          </Card>
        </div>
      </div>

      {errors.length > 0 && (
        <div style={{ background: "#FEF2F2", border: `1px solid #FCA5A5`, borderRadius: 8, padding: 12, marginTop: 14 }}>
          {errors.map((e, i) => <div key={i} style={{ fontSize: 12, color: T.red }}>• {e}</div>)}
        </div>
      )}

      <div style={{ marginTop: 20, display: "flex", justifyContent: "flex-end" }}>
        <Btn onClick={handleSave} loading={saving} variant="primary">
          Save & Generate Strategy →
        </Btn>
      </div>
    </div>
  )
}

// ── Step 2: AI Strategy Generation SSE ───────────────────────────────────────
function GenerateStep({ projectId, onBack, onComplete }) {
  const [status, setStatus] = useState("idle") // idle | running | done | error
  const [logs, setLogs] = useState([])
  const [strategy, setStrategy] = useState(null)
  const [error, setError] = useState("")
  const abortRef = useRef(null)
  const scrollRef = useRef(null)

  useEffect(() => () => abortRef.current?.abort(), [])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [logs])

  const startGeneration = useCallback(() => {
    setStatus("running")
    setLogs([])
    setError("")
    setStrategy(null)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    fetch(`${API}/api/strategy/${projectId}/generate-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({}),
      signal: ctrl.signal,
    })
      .then(async res => {
        if (!res.ok) {
          const d = await res.json().catch(() => ({}))
          setError(d?.detail || `HTTP ${res.status}`)
          setStatus("error")
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
                setStrategy(ev.strategy)
                setStatus("done")
              } else if (ev.type === "error") {
                setError(ev.msg || "Generation failed")
                setStatus("error")
              }
            } catch { /* ignore */ }
          }
        }
        setStatus(s => s === "running" ? "done" : s)
      })
      .catch(e => {
        if (e.name !== "AbortError") { setError(String(e)); setStatus("error") }
      })
  }, [projectId])

  // Auto-start on mount
  useEffect(() => { startGeneration() }, [startGeneration])

  const levelColor = l => l === "success" ? T.teal : l === "error" ? T.red : l === "warn" ? T.amber : "#0f0"

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>AI Strategy Generation</h2>
        <p style={{ margin: 0, fontSize: 13, color: T.textSoft }}>
          DeepSeek AI is analyzing your business profile and keywords to build a personalized ranking strategy.
        </p>
      </div>

      <Card style={{ marginBottom: 16 }}>
        {/* Status bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <div style={{
            width: 10, height: 10, borderRadius: "50%",
            background: status === "done" ? T.teal : status === "error" ? T.red : T.purple,
            animation: status === "running" ? "pulse 1.2s infinite" : "none",
          }} />
          <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>
            {status === "idle" && "Preparing..."}
            {status === "running" && "Generating strategy..."}
            {status === "done" && "Strategy generated!"}
            {status === "error" && "Generation failed"}
          </div>
        </div>

        {/* Console */}
        <div ref={scrollRef} style={{
          background: "#0d0d0d", borderRadius: 8, padding: 12, height: 240,
          overflowY: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.6,
        }}>
          {logs.length === 0 && <div style={{ color: "#555" }}>Starting AI engine...</div>}
          {logs.map((l, i) => (
            <div key={i} style={{ color: levelColor(l.level) }}>
              → {l.msg}
            </div>
          ))}
        </div>

        {error && (
          <div style={{ marginTop: 10, padding: 10, background: "#FEF2F2", borderRadius: 8, fontSize: 12, color: T.red }}>
            ✗ {error}
          </div>
        )}
      </Card>

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }`}</style>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16 }}>
        <Btn variant="ghost" onClick={onBack} disabled={status === "running"}>← Edit Profile</Btn>
        <div style={{ display: "flex", gap: 8 }}>
          {(status === "error") && (
            <Btn variant="outline" onClick={startGeneration}>↻ Retry</Btn>
          )}
          <Btn variant="teal" disabled={status !== "done" || !strategy}
            onClick={() => onComplete(strategy)}>
            Review Strategy →
          </Btn>
        </div>
      </div>
    </div>
  )
}

// ── Step 3: Strategy Plan View ────────────────────────────────────────────────
function StrategyPlanStep({ strategy, onBack, onRegenerate }) {
  const [confirmed, setConfirmed] = useState(false)

  if (!strategy) return <div>No strategy data</div>

  const conf = strategy.strategy_confidence || 0
  const confColor = conf >= 80 ? T.teal : conf >= 50 ? T.amber : T.red

  return (
    <div>
      <div style={{ marginBottom: 20, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Your SEO/AEO Strategy Plan</h2>
          <p style={{ margin: 0, fontSize: 13, color: T.textSoft }}>AI-generated strategy targeting Top 5 in Google & AI search</p>
        </div>
        <div style={{
          background: confColor + "18", border: `1px solid ${confColor}33`,
          borderRadius: 10, padding: "6px 14px", textAlign: "center",
        }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: confColor }}>{conf}%</div>
          <div style={{ fontSize: 10, color: confColor }}>AI Confidence</div>
        </div>
      </div>

      {/* Executive Summary */}
      {strategy.executive_summary && (
        <Card style={{ marginBottom: 14, background: T.purpleLight, border: `1px solid ${T.purple}33` }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.purpleDark, marginBottom: 6 }}>EXECUTIVE SUMMARY</div>
          <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6 }}>{strategy.executive_summary}</div>
        </Card>
      )}

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
              <div key={i} style={{
                background: T.grayLight, borderRadius: 8, padding: 10, textAlign: "center",
              }}>
                <div style={{ fontSize: 20, marginBottom: 4 }}>{g.icon}</div>
                <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 4 }}>{g.label}</div>
                <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{g.val}</div>
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
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {strategy.pillar_strategy.slice(0, 6).map((p, i) => (
                <div key={i} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "8px 10px", background: T.grayLight, borderRadius: 8,
                }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600 }}>{p.pillar}</div>
                    <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>
                      {p.content_type} • {p.monthly_searches || "??"} searches/mo
                      {p.ai_snippet_opportunity && " • 🤖 AI snippet"}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{
                      fontSize: 14, fontWeight: 700,
                      color: p.target_rank <= 3 ? T.teal : T.amber,
                    }}>#{p.target_rank}</div>
                    <div style={{
                      fontSize: 10,
                      color: p.difficulty === "low" ? T.teal : p.difficulty === "high" ? T.red : T.amber,
                    }}>{p.difficulty}</div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Quick Wins */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {strategy.quick_wins?.length > 0 && (
            <Card>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 8 }}>QUICK WINS (Do This Week)</div>
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
              <div key={i} style={{
                minWidth: 200, background: T.grayLight, borderRadius: 8, padding: 10, flexShrink: 0,
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.purpleDark, marginBottom: 8 }}>
                  {month.month} — {month.focus_pillar}
                </div>
                {(month.articles || []).slice(0, 3).map((a, j) => (
                  <div key={j} style={{
                    background: "#fff", borderRadius: 6, padding: "6px 8px", marginBottom: 4,
                    fontSize: 11, border: `0.5px solid ${T.border}`,
                  }}>
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
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
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

      {/* Action buttons */}
      <Card style={{ background: confirmed ? T.tealLight : T.amberLight, border: `1px solid ${confirmed ? T.teal : T.amber}33` }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            {confirmed
              ? <div style={{ fontSize: 13, fontWeight: 600, color: T.teal }}>✓ Strategy confirmed! Start executing the content plan.</div>
              : <div style={{ fontSize: 13, color: T.text }}>Review the strategy above, then confirm to lock it in.</div>
            }
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn variant="ghost" onClick={onBack}>← Edit Profile</Btn>
            <Btn variant="ghost" onClick={onRegenerate}>↻ Regenerate</Btn>
            {!confirmed && (
              <Btn variant="teal" onClick={() => setConfirmed(true)}>
                ✓ Confirm Strategy
              </Btn>
            )}
          </div>
        </div>
      </Card>
    </div>
  )
}

// ── Main StrategyPage ─────────────────────────────────────────────────────────
export default function StrategyPage({ projectId }) {
  const [step, setStep] = useState(1)
  const [strategy, setStrategy] = useState(null)

  // Load latest saved strategy on mount
  const { data: latestStrategy } = useQuery({
    queryKey: ["latest-strategy", projectId],
    queryFn: async () => {
      const r = await fetch(`${API}/api/strategy/${projectId}/latest`, { headers: authHeaders() })
      if (!r.ok) return null
      const d = await r.json()
      return d?.meta?.has_data ? d.strategy : null
    },
    enabled: !!projectId,
    retry: false,
  })

  if (!projectId) {
    return (
      <div style={{ padding: 32, textAlign: "center", color: T.textSoft }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>📊</div>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>Select a project to view strategy</div>
        <div style={{ fontSize: 13 }}>Choose a project from the sidebar to get started.</div>
      </div>
    )
  }

  return (
    <div style={{ padding: "20px 24px", maxWidth: 1100, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 22, fontWeight: 700, color: T.text }}>
          SEO / AEO Strategy
        </h1>
        <p style={{ margin: 0, fontSize: 13, color: T.textSoft }}>
          AI-powered strategy to reach Top 5 in Google Search and AI search engines (ChatGPT, Gemini, Perplexity)
        </p>
      </div>

      {/* Show existing strategy shortcut */}
      {latestStrategy && step === 1 && (
        <Card style={{ marginBottom: 20, background: T.tealLight, border: `1px solid ${T.teal}33` }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.teal }}>✓ You have a saved strategy</div>
              <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
                {latestStrategy.executive_summary?.slice(0, 100)}...
              </div>
            </div>
            <Btn variant="teal" small onClick={() => { setStrategy(latestStrategy); setStep(3) }}>
              View Current Strategy
            </Btn>
          </div>
        </Card>
      )}

      <StepIndicator step={step} />

      {step === 1 && (
        <ProfileStep
          projectId={projectId}
          onNext={() => setStep(2)}
        />
      )}

      {step === 2 && (
        <GenerateStep
          projectId={projectId}
          onBack={() => setStep(1)}
          onComplete={(s) => { setStrategy(s); setStep(3) }}
        />
      )}

      {step === 3 && (
        <StrategyPlanStep
          strategy={strategy || latestStrategy}
          onBack={() => setStep(1)}
          onRegenerate={() => setStep(2)}
        />
      )}
    </div>
  )
}
