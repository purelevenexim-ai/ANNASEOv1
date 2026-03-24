// ============================================================================
// ANNASEO — Keyword Input Page  (src/KeywordInput.jsx)
// 4-step wizard: input → generating → review → confirmed
// ============================================================================

import { useState, useEffect, useRef, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"

const API = import.meta.env.VITE_API_URL || ""

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────────

function apiCall(path, method = "GET", body = null) {
  const token = localStorage.getItem("annaseo_token")
  return fetch(`${API}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  }).then(r => r.json())
}

// Design tokens (matching App.jsx)
const T = {
  purple:     "#7c3aed",
  purpleLight:"#f5f3ff",
  purpleDark: "#5b21b6",
  teal:       "#0d9488",
  tealLight:  "#f0fdfa",
  amber:      "#d97706",
  amberLight: "#fffbeb",
  red:        "#dc2626",
  redLight:   "#fef2f2",
  green:      "#16a34a",
  greenLight: "#f0fdf4",
  gray:       "#6b7280",
  grayLight:  "#f9fafb",
  border:     "rgba(0,0,0,0.09)",
  text:       "#111827",
  textSoft:   "#6b7280",
}

const INTENT_OPTIONS = [
  { value: "transactional", label: "Buy / Purchase", color: T.teal },
  { value: "informational", label: "Information / Learn", color: T.purple },
  { value: "commercial",    label: "Commercial Research", color: T.amber },
  { value: "local",         label: "Local / Near me", color: "#0284c7" },
  { value: "comparison",    label: "Comparison / Review", color: "#7c3aed" },
]

function Badge({ color, children }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "2px 8px", borderRadius: 99, fontSize: 10, fontWeight: 600,
      background: color + "22", color,
    }}>
      {children}
    </span>
  )
}

function intentColor(intent) {
  const map = {
    transactional: T.teal,
    informational: T.purple,
    commercial:    T.amber,
    local:         "#0284c7",
    comparison:    T.purpleDark,
    question:      "#0891b2",
  }
  return map[intent] || T.gray
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 1 — INPUT FORM
// ─────────────────────────────────────────────────────────────────────────────

function KeywordInputForm({ projectId, onSubmit }) {
  const [pillars, setPillars]         = useState([{ keyword: "", intent: "transactional", priority: 1 }])
  const [supporting, setSupporting]   = useState([""])
  const [intentFocus, setIntentFocus] = useState(["transactional"])
  const [customerUrl, setCustomerUrl] = useState("")
  const [competitors, setCompetitors] = useState([""])
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState("")

  const addPillar = () => {
    if (pillars.length >= 10) return
    setPillars(p => [...p, { keyword: "", intent: intentFocus, priority: p.length + 1 }])
  }
  const removePillar = i => setPillars(p => p.filter((_, j) => j !== i))
  const setPillarField = (i, field, val) => {
    setPillars(p => p.map((x, j) => j === i ? { ...x, [field]: val } : x))
  }

  const addSupporting = () => {
    if (supporting.length >= 20) return
    setSupporting(s => [...s, ""])
  }
  const removeSupporting = i => setSupporting(s => s.filter((_, j) => j !== i))
  const setSupportingVal = (i, val) => setSupporting(s => s.map((x, j) => j === i ? val : x))

  const addCompetitor = () => setCompetitors(c => [...c, ""])
  const removeCompetitor = i => setCompetitors(c => c.filter((_, j) => j !== i))
  const setCompetitorVal = (i, val) => setCompetitors(c => c.map((x, j) => j === i ? val : x))

  const handleSubmit = async () => {
    const validPillars = pillars.filter(p => p.keyword.trim())
    if (!validPillars.length) { setError("Add at least one pillar keyword"); return }

    const validSupporting = supporting.filter(s => s.trim())
    if (!validSupporting.length) { setError("Add at least one supporting keyword"); return }

    if (!intentFocus.length) { setError("Select at least one intent focus"); return }

    setLoading(true); setError("")
    try {
      const result = await apiCall(`/api/ki/${projectId}/input`, "POST", {
        pillars: validPillars.map((p, i) => ({ ...p, priority: i + 1 })),
        supporting: validSupporting,
        intent_focus: intentFocus[0] || "transactional",
        customer_url: customerUrl.trim() || null,
        competitor_urls: competitors.filter(c => c.trim()),
      })
      if (result.session_id) {
        onSubmit(result.session_id)
      } else {
        setError(result.detail || result.error || "Failed to save input")
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const labelStyle = { fontSize: 11, fontWeight: 600, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }
  const inputStyle = {
    width: "100%", padding: "8px 10px", border: `1px solid ${T.border}`,
    borderRadius: 6, fontSize: 13, background: "#fff", outline: "none",
  }
  const cardStyle = {
    background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 20, marginBottom: 16,
  }

  return (
    <div style={{ maxWidth: 740, margin: "0 auto" }}>
      {/* Pillar Keywords */}
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: T.text }}>Pillar Keywords</div>
            <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
              Main topics your website ranks for (e.g. Cinnamon, Turmeric, Clove)
            </div>
          </div>
          <button onClick={addPillar} style={{
            background: T.purple, color: "#fff", border: "none", borderRadius: 6,
            padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
          }}>+ Add Pillar</button>
        </div>

        {pillars.map((p, i) => (
          <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
            <input
              style={{ ...inputStyle, flex: 2 }}
              placeholder={`Pillar ${i + 1} (e.g. cinnamon)`}
              value={p.keyword}
              onChange={e => setPillarField(i, "keyword", e.target.value)}
            />
            <select
              style={{ ...inputStyle, flex: 1, cursor: "pointer" }}
              value={p.intent}
              onChange={e => setPillarField(i, "intent", e.target.value)}
            >
              {INTENT_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            {pillars.length > 1 && (
              <button onClick={() => removePillar(i)} style={{
                background: T.redLight, color: T.red, border: "none", borderRadius: 6,
                padding: "8px 10px", fontSize: 13, cursor: "pointer", flexShrink: 0,
              }}>✕</button>
            )}
          </div>
        ))}
      </div>

      {/* Supporting Keywords */}
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: T.text }}>Supporting Keywords</div>
            <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
              Qualifiers that combine with pillars (e.g. organic, buy online, kerala, price)
            </div>
          </div>
          <button onClick={addSupporting} style={{
            background: T.teal, color: "#fff", border: "none", borderRadius: 6,
            padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
          }}>+ Add</button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8 }}>
          {supporting.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                style={{ ...inputStyle, flex: 1 }}
                placeholder={`e.g. organic`}
                value={s}
                onChange={e => setSupportingVal(i, e.target.value)}
              />
              {supporting.length > 1 && (
                <button onClick={() => removeSupporting(i)} style={{
                  background: "none", color: T.gray, border: "none", cursor: "pointer", fontSize: 14, padding: "4px",
                }}>✕</button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Intent Focus */}
      <div style={cardStyle}>
        <div style={{ fontWeight: 700, fontSize: 14, color: T.text, marginBottom: 8 }}>Primary Intent Focus</div>
        <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 12 }}>
          Select all that apply — selling products, information, local, or comparisons?
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {INTENT_OPTIONS.map(o => {
            const active = intentFocus.includes(o.value)
            return (
              <button
                key={o.value}
                onClick={() => setIntentFocus(prev =>
                  prev.includes(o.value) ? prev.filter(x => x !== o.value) : [...prev, o.value]
                )}
                style={{
                  padding: "6px 14px", borderRadius: 99, fontSize: 12, fontWeight: 600,
                  cursor: "pointer",
                  border: `2px solid ${active ? o.color : "transparent"}`,
                  background: active ? o.color : T.grayLight,
                  color: active ? "#fff" : T.textSoft,
                  transition: "all 0.15s",
                }}
              >{active ? "✓ " : ""}{o.label}</button>
            )
          })}
        </div>
        {intentFocus.length === 0 && (
          <div style={{ fontSize: 11, color: T.red, marginTop: 6 }}>Select at least one intent</div>
        )}
      </div>

      {/* Website URLs */}
      <div style={cardStyle}>
        <div style={{ fontWeight: 700, fontSize: 14, color: T.text, marginBottom: 12 }}>Website Analysis (optional)</div>
        <div style={{ marginBottom: 10 }}>
          <div style={labelStyle}>Your Website URL</div>
          <input
            style={inputStyle}
            placeholder="https://yourstore.com"
            value={customerUrl}
            onChange={e => setCustomerUrl(e.target.value)}
          />
        </div>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
            <div style={labelStyle}>Competitor URLs</div>
            <button onClick={addCompetitor} style={{
              background: "none", color: T.purple, border: "none", fontSize: 11,
              fontWeight: 600, cursor: "pointer",
            }}>+ Add competitor</button>
          </div>
          {competitors.map((c, i) => (
            <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6 }}>
              <input
                style={{ ...inputStyle, flex: 1 }}
                placeholder="https://competitor.com"
                value={c}
                onChange={e => setCompetitorVal(i, e.target.value)}
              />
              {competitors.length > 1 && (
                <button onClick={() => removeCompetitor(i)} style={{
                  background: "none", color: T.gray, border: "none", cursor: "pointer", fontSize: 14,
                }}>✕</button>
              )}
            </div>
          ))}
        </div>
      </div>

      {error && (
        <div style={{ background: T.redLight, color: T.red, padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 12 }}>
          {error}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={loading}
        style={{
          width: "100%", padding: "12px", background: loading ? T.gray : T.purple,
          color: "#fff", border: "none", borderRadius: 8, fontSize: 14, fontWeight: 700,
          cursor: loading ? "not-allowed" : "pointer",
        }}
      >
        {loading ? "Saving..." : "Generate Keyword Universe →"}
      </button>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 2 — GENERATING VIEW
// ─────────────────────────────────────────────────────────────────────────────

function GeneratingView({ projectId, sessionId, onComplete }) {
  const [status, setStatus]   = useState("running")
  const [progress, setProgress] = useState(0)
  const [log, setLog]         = useState([])
  const intervalRef           = useRef(null)

  const poll = useCallback(async () => {
    try {
      const data = await apiCall(`/api/ki/${projectId}/session/${sessionId}`)
      if (!data || data.detail) return

      const st = data.status || "running"
      setStatus(st)

      const total = data.total_keywords || 0
      if (total > 0) {
        setProgress(Math.min(100, Math.round(total / 3)))
      }

      setLog(l => {
        const msgs = []
        if (data.cross_product_count > 0 && !l.includes("cross_product"))
          msgs.push(`cross_product: ${data.cross_product_count} phrases generated`)
        if (data.website_kw_count > 0 && !l.includes("website"))
          msgs.push(`website: ${data.website_kw_count} keywords from crawl`)
        if (data.enriched_count > 0 && !l.includes("enriched"))
          msgs.push(`enriched: ${data.enriched_count} enriched keywords`)
        if (total > 0 && !l.includes("assembled"))
          msgs.push(`assembled: ${total} total keywords in universe`)
        return [...new Set([...l, ...msgs])]
      })

      if (st === "ready" || st === "error") {
        clearInterval(intervalRef.current)
        if (st === "ready") {
          setTimeout(() => onComplete(), 800)
        }
      }
    } catch (e) {
      console.error("Poll error:", e)
    }
  }, [projectId, sessionId, onComplete])

  useEffect(() => {
    // Trigger generation
    apiCall(`/api/ki/${projectId}/generate/${sessionId}`, "POST").catch(console.error)

    intervalRef.current = setInterval(poll, 2000)
    return () => clearInterval(intervalRef.current)
  }, [projectId, sessionId, poll])

  const steps = [
    { key: "cross_multiply",  label: "Cross-multiplying pillars × supporting keywords" },
    { key: "crawl_website",   label: "Crawling your website for keywords" },
    { key: "crawl_competitors",label: "Analyzing competitor websites" },
    { key: "google_enrich",   label: "Fetching Google autosuggest data" },
    { key: "assemble",        label: "Assembling keyword universe" },
    { key: "score",           label: "Scoring opportunities" },
  ]

  const completedStep = Math.floor(progress / 18)

  return (
    <div style={{ maxWidth: 520, margin: "80px auto", textAlign: "center" }}>
      <div style={{
        width: 64, height: 64, borderRadius: "50%",
        border: `4px solid ${T.purpleLight}`, borderTopColor: T.purple,
        animation: "spin 0.8s linear infinite", margin: "0 auto 24px",
      }}/>
      <div style={{ fontSize: 20, fontWeight: 700, color: T.text, marginBottom: 8 }}>
        Building Keyword Universe
      </div>
      <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 28 }}>
        Analyzing pillars, supporting keywords, and website data...
      </div>

      {/* Progress bar */}
      <div style={{ background: T.grayLight, borderRadius: 99, height: 6, marginBottom: 24 }}>
        <div style={{
          height: "100%", borderRadius: 99, background: T.purple,
          width: `${progress}%`, transition: "width 0.4s ease",
        }}/>
      </div>

      {/* Steps */}
      <div style={{ textAlign: "left", background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 16 }}>
        {steps.map((s, i) => (
          <div key={s.key} style={{
            display: "flex", gap: 10, alignItems: "center", padding: "7px 0",
            borderBottom: i < steps.length - 1 ? `1px solid ${T.border}` : "none",
          }}>
            <div style={{
              width: 20, height: 20, borderRadius: "50%", flexShrink: 0,
              background: i < completedStep ? T.green : i === completedStep ? T.amber : T.grayLight,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, color: "#fff",
            }}>
              {i < completedStep ? "✓" : i + 1}
            </div>
            <div style={{ fontSize: 12, color: i <= completedStep ? T.text : T.textSoft }}>
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* Log */}
      {log.length > 0 && (
        <div style={{ marginTop: 16, textAlign: "left" }}>
          {log.map((l, i) => (
            <div key={i} style={{ fontSize: 11, color: T.textSoft, padding: "2px 0" }}>
              {l}
            </div>
          ))}
        </div>
      )}

      {status === "error" && (
        <div style={{ marginTop: 16, background: T.redLight, color: T.red, padding: 12, borderRadius: 8, fontSize: 13 }}>
          Generation failed. Please try again.
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// KEYWORD ROW — accept / reject / edit / move pillar
// ─────────────────────────────────────────────────────────────────────────────

function KeywordRow({ item, pillars, onAction }) {
  const [editing, setEditing]   = useState(false)
  const [editVal, setEditVal]   = useState(item.keyword)
  const [moving, setMoving]     = useState(false)
  const inputRef                = useRef(null)

  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.focus()
  }, [editing])

  const doAction = (action, extra = {}) => onAction(item.item_id, action, extra)

  const saveEdit = () => {
    if (editVal.trim() && editVal.trim() !== item.keyword) {
      doAction("edit", { new_keyword: editVal.trim() })
    }
    setEditing(false)
  }

  const statusColors = {
    accepted: { bg: T.greenLight, border: "#bbf7d0", text: T.green },
    rejected: { bg: T.redLight,   border: "#fecaca", text: T.red },
    pending:  { bg: "#fff",       border: T.border,  text: T.text },
  }
  const sc = statusColors[item.status] || statusColors.pending

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
      border: `1px solid ${sc.border}`, borderRadius: 8, marginBottom: 6,
      background: sc.bg, transition: "all 0.12s",
    }}>
      {/* Keyword text */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {editing ? (
          <input
            ref={inputRef}
            value={editVal}
            onChange={e => setEditVal(e.target.value)}
            onBlur={saveEdit}
            onKeyDown={e => { if (e.key === "Enter") saveEdit(); if (e.key === "Escape") setEditing(false) }}
            style={{
              width: "100%", padding: "4px 8px", border: `1px solid ${T.purple}`,
              borderRadius: 4, fontSize: 13, outline: "none",
            }}
          />
        ) : (
          <div style={{ fontSize: 13, fontWeight: 500, color: sc.text,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {item.keyword}
          </div>
        )}
        <div style={{ display: "flex", gap: 6, marginTop: 3, flexWrap: "wrap" }}>
          <Badge color={intentColor(item.intent)}>{item.intent || "??"}</Badge>
          {item.source && <Badge color={T.gray}>{item.source}</Badge>}
          {item.opportunity_score > 0 && (
            <Badge color={item.opportunity_score >= 60 ? T.green : item.opportunity_score >= 40 ? T.amber : T.gray}>
              {Math.round(item.opportunity_score)}pts
            </Badge>
          )}
        </div>
      </div>

      {/* Pillar badge */}
      {item.pillar && !moving && (
        <div style={{ fontSize: 10, color: T.purple, background: T.purpleLight,
          padding: "2px 7px", borderRadius: 99, fontWeight: 600, flexShrink: 0 }}>
          {item.pillar}
        </div>
      )}

      {/* Move pillar dropdown */}
      {moving && (
        <select
          autoFocus
          onBlur={() => setMoving(false)}
          onChange={e => { doAction("move_pillar", { new_pillar: e.target.value }); setMoving(false) }}
          defaultValue=""
          style={{ fontSize: 11, border: `1px solid ${T.border}`, borderRadius: 4, padding: "3px 6px" }}
        >
          <option value="" disabled>Move to...</option>
          {pillars.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      )}

      {/* Actions */}
      <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
        {item.status !== "accepted" && (
          <button onClick={() => doAction("accept")} title="Accept" style={{
            width: 28, height: 28, border: "none", borderRadius: 6,
            background: T.greenLight, color: T.green, cursor: "pointer", fontSize: 13, fontWeight: 700,
          }}>✓</button>
        )}
        {item.status !== "rejected" && (
          <button onClick={() => doAction("reject")} title="Reject" style={{
            width: 28, height: 28, border: "none", borderRadius: 6,
            background: T.redLight, color: T.red, cursor: "pointer", fontSize: 13,
          }}>✕</button>
        )}
        <button onClick={() => setEditing(true)} title="Edit" style={{
          width: 28, height: 28, border: "none", borderRadius: 6,
          background: T.purpleLight, color: T.purple, cursor: "pointer", fontSize: 13,
        }}>✎</button>
        <button onClick={() => setMoving(true)} title="Move to pillar" style={{
          width: 28, height: 28, border: "none", borderRadius: 6,
          background: T.grayLight, color: T.gray, cursor: "pointer", fontSize: 11,
        }}>⇄</button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 3 — KEYWORD REVIEW UI
// ─────────────────────────────────────────────────────────────────────────────

function KeywordReviewUI({ projectId, sessionId, onConfirm }) {
  const qc = useQueryClient ? useQueryClient() : null
  const [filterPillar,  setFilterPillar]  = useState("")
  const [filterIntent,  setFilterIntent]  = useState("")
  const [filterStatus,  setFilterStatus]  = useState("pending")
  const [page, setPage]                   = useState(0)
  const [confirming, setConfirming]       = useState(false)
  const limit = 30

  // Fetch review queue
  const reviewKey = ["review", projectId, sessionId, filterPillar, filterIntent, filterStatus, page]
  const { data: reviewData, refetch } = useQuery({
    queryKey: reviewKey,
    queryFn: () => {
      let url = `/api/ki/${projectId}/review/${sessionId}?limit=${limit}&offset=${page * limit}`
      if (filterPillar)  url += `&pillar=${encodeURIComponent(filterPillar)}`
      if (filterIntent)  url += `&intent=${encodeURIComponent(filterIntent)}`
      if (filterStatus !== "all") url += `&status=${filterStatus}`
      return apiCall(url)
    },
    refetchOnWindowFocus: false,
  })

  // Fetch by-pillar summary
  const { data: pillarData } = useQuery({
    queryKey: ["by-pillar", projectId, sessionId],
    queryFn: () => apiCall(`/api/ki/${projectId}/universe/${sessionId}/by-pillar`),
    refetchOnWindowFocus: false,
  })

  const items    = reviewData?.items    || []
  const total    = reviewData?.total    || 0
  const stats    = reviewData?.stats    || {}
  const pillars  = pillarData?.pillars  || []
  const pillarNames = pillars.map(p => p.pillar || p)

  const doAction = async (itemId, action, extra = {}) => {
    await apiCall(`/api/ki/${projectId}/review/${sessionId}/action`, "POST", {
      item_id: itemId, action, ...extra,
    })
    refetch()
  }

  const acceptAll = async () => {
    await apiCall(`/api/ki/${projectId}/review/${sessionId}/accept-all`, "POST", {
      pillar: filterPillar || null,
      intent: filterIntent || null,
    })
    refetch()
  }

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      const result = await apiCall(`/api/ki/${projectId}/confirm/${sessionId}`, "POST")
      if (result.keyword_count > 0 || result.status === "confirmed") {
        onConfirm(result)
      }
    } finally {
      setConfirming(false)
    }
  }

  const totalPages = Math.ceil(total / limit)

  return (
    <div style={{ display: "flex", gap: 0, height: "calc(100vh - 100px)" }}>
      {/* Left sidebar — Pillar filter */}
      <div style={{
        width: 200, flexShrink: 0, borderRight: `1px solid ${T.border}`,
        overflowY: "auto", paddingTop: 8,
      }}>
        <div style={{ padding: "0 12px 8px", fontSize: 10, fontWeight: 700,
          color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5 }}>
          Pillars
        </div>
        <button
          onClick={() => { setFilterPillar(""); setPage(0) }}
          style={{
            width: "100%", textAlign: "left", padding: "7px 12px", border: "none",
            background: !filterPillar ? T.purpleLight : "transparent",
            color: !filterPillar ? T.purpleDark : T.textSoft,
            borderLeft: `3px solid ${!filterPillar ? T.purple : "transparent"}`,
            fontSize: 12, fontWeight: 500, cursor: "pointer",
          }}
        >All Pillars</button>
        {pillars.map(p => {
          const name = p.pillar || p
          const cnt = p.total || 0
          return (
            <button
              key={name}
              onClick={() => { setFilterPillar(name); setPage(0) }}
              style={{
                width: "100%", textAlign: "left", padding: "7px 12px", border: "none",
                background: filterPillar === name ? T.purpleLight : "transparent",
                color: filterPillar === name ? T.purpleDark : T.textSoft,
                borderLeft: `3px solid ${filterPillar === name ? T.purple : "transparent"}`,
                fontSize: 12, fontWeight: 500, cursor: "pointer",
                display: "flex", justifyContent: "space-between",
              }}
            >
              <span>{name}</span>
              {cnt > 0 && <span style={{ fontSize: 10, color: T.gray }}>{cnt}</span>}
            </button>
          )
        })}

        <div style={{ padding: "12px 12px 4px", fontSize: 10, fontWeight: 700,
          color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, marginTop: 8 }}>
          Intent
        </div>
        {[{ value: "", label: "All" }, ...INTENT_OPTIONS].map(o => (
          <button
            key={o.value}
            onClick={() => { setFilterIntent(o.value); setPage(0) }}
            style={{
              width: "100%", textAlign: "left", padding: "6px 12px", border: "none",
              background: filterIntent === o.value ? T.purpleLight : "transparent",
              color: filterIntent === o.value ? T.purpleDark : T.textSoft,
              fontSize: 11, cursor: "pointer",
            }}
          >{o.label}</button>
        ))}
      </div>

      {/* Right panel */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Stats bar */}
        <div style={{
          display: "flex", gap: 12, padding: "12px 16px",
          borderBottom: `1px solid ${T.border}`, flexShrink: 0,
        }}>
          {[
            { label: "Total",    value: stats.total    || 0, color: T.text },
            { label: "Pending",  value: stats.pending  || 0, color: T.amber },
            { label: "Accepted", value: stats.accepted || 0, color: T.green },
            { label: "Rejected", value: stats.rejected || 0, color: T.red },
          ].map(s => (
            <div key={s.label} style={{
              background: "#fff", border: `1px solid ${T.border}`, borderRadius: 8,
              padding: "8px 14px", minWidth: 80, textAlign: "center",
            }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: 10, color: T.textSoft }}>{s.label}</div>
            </div>
          ))}

          <div style={{ flex: 1 }}/>

          {/* Status filter */}
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            {["pending", "accepted", "rejected", "all"].map(s => (
              <button key={s} onClick={() => { setFilterStatus(s); setPage(0) }} style={{
                padding: "5px 10px", border: "none", borderRadius: 6, fontSize: 11,
                fontWeight: 600, cursor: "pointer",
                background: filterStatus === s ? T.purple : T.grayLight,
                color: filterStatus === s ? "#fff" : T.textSoft,
              }}>{s.charAt(0).toUpperCase() + s.slice(1)}</button>
            ))}
          </div>

          <button onClick={acceptAll} style={{
            padding: "6px 12px", background: T.greenLight, color: T.green,
            border: "none", borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: "pointer",
          }}>Accept All {filterPillar ? `(${filterPillar})` : ""}</button>

          <button
            onClick={handleConfirm}
            disabled={confirming || (stats.accepted || 0) === 0}
            style={{
              padding: "6px 14px", background: confirming ? T.gray : T.purple,
              color: "#fff", border: "none", borderRadius: 6, fontSize: 12,
              fontWeight: 700, cursor: confirming ? "not-allowed" : "pointer",
            }}
          >
            {confirming ? "Confirming..." : `Confirm ${stats.accepted || 0} Keywords →`}
          </button>
        </div>

        {/* Keyword list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
          {items.length === 0 ? (
            <div style={{ textAlign: "center", padding: "40px 0", color: T.textSoft, fontSize: 13 }}>
              No keywords found. Try a different filter.
            </div>
          ) : (
            items.map(item => (
              <KeywordRow
                key={item.item_id}
                item={item}
                pillars={pillarNames}
                onAction={doAction}
              />
            ))
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: "flex", justifyContent: "center", gap: 6, marginTop: 16 }}>
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                style={{ padding: "5px 12px", border: `1px solid ${T.border}`, borderRadius: 6,
                  fontSize: 12, cursor: "pointer", background: "#fff" }}
              >← Prev</button>
              <span style={{ fontSize: 12, color: T.textSoft, padding: "5px 10px" }}>
                {page + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                style={{ padding: "5px 12px", border: `1px solid ${T.border}`, borderRadius: 6,
                  fontSize: 12, cursor: "pointer", background: "#fff" }}
              >Next →</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 4 — CONFIRMED VIEW
// ─────────────────────────────────────────────────────────────────────────────

function ConfirmedView({ result, onRestart }) {
  return (
    <div style={{ maxWidth: 520, margin: "80px auto", textAlign: "center" }}>
      <div style={{
        width: 64, height: 64, borderRadius: "50%",
        background: T.greenLight, display: "flex", alignItems: "center",
        justifyContent: "center", fontSize: 28, margin: "0 auto 20px",
      }}>✓</div>

      <div style={{ fontSize: 22, fontWeight: 700, color: T.text, marginBottom: 8 }}>
        Keyword Universe Confirmed
      </div>
      <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 28 }}>
        {result.keyword_count || 0} keywords are ready for the pipeline.
        The next keyword run will use your confirmed universe.
      </div>

      <div style={{
        background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10,
        padding: 20, marginBottom: 20, textAlign: "left",
      }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: T.text, marginBottom: 12 }}>Summary</div>
        {[
          { label: "Total keywords",    value: result.keyword_count || 0 },
          { label: "Accepted",          value: result.accepted_count || result.keyword_count || 0 },
          { label: "Pillars confirmed", value: result.pillar_count || 0 },
          { label: "Session ID",        value: (result.session_id || "").slice(0, 14) + "..." },
        ].map(row => (
          <div key={row.label} style={{
            display: "flex", justifyContent: "space-between", padding: "6px 0",
            borderBottom: `1px solid ${T.border}`, fontSize: 13,
          }}>
            <span style={{ color: T.textSoft }}>{row.label}</span>
            <span style={{ fontWeight: 600, color: T.text }}>{row.value}</span>
          </div>
        ))}
      </div>

      <button
        onClick={onRestart}
        style={{
          padding: "10px 24px", background: T.purple, color: "#fff",
          border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer",
        }}
      >Start New Session</button>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────────────────────────────────────

export default function KeywordInputPage({ projectId }) {
  const [step, setStep]           = useState("input")   // input | generating | review | confirmed
  const [sessionId, setSessionId] = useState(null)
  const [confirmResult, setConfirmResult] = useState(null)

  if (!projectId) {
    return (
      <div style={{ textAlign: "center", padding: "60px 0", color: T.textSoft }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>📎</div>
        <div style={{ fontSize: 14 }}>Select a project first to manage its keyword universe.</div>
      </div>
    )
  }

  const handleInputSubmit = (sid) => {
    setSessionId(sid)
    setStep("generating")
  }

  const handleGenerationComplete = () => {
    setStep("review")
  }

  const handleConfirm = (result) => {
    setConfirmResult(result)
    setStep("confirmed")
  }

  const handleRestart = () => {
    setSessionId(null)
    setConfirmResult(null)
    setStep("input")
  }

  // Step indicator
  const STEPS = [
    { id: "input",      label: "1. Input Keywords" },
    { id: "generating", label: "2. Generating Universe" },
    { id: "review",     label: "3. Review & Edit" },
    { id: "confirmed",  label: "4. Confirmed" },
  ]
  const currentIdx = STEPS.findIndex(s => s.id === step)

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: T.text }}>Keyword Universe Input</div>
        <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
          Define pillar + supporting keywords — system builds and scores your full universe
        </div>
      </div>

      {/* Step indicator */}
      <div style={{ display: "flex", gap: 0, marginBottom: 24 }}>
        {STEPS.map((s, i) => (
          <div key={s.id} style={{ display: "flex", alignItems: "center" }}>
            <div style={{
              padding: "6px 14px", fontSize: 11, fontWeight: 600, borderRadius: 99,
              background: i < currentIdx ? T.greenLight : i === currentIdx ? T.purple : T.grayLight,
              color: i < currentIdx ? T.green : i === currentIdx ? "#fff" : T.textSoft,
            }}>
              {i < currentIdx ? "✓ " : ""}{s.label}
            </div>
            {i < STEPS.length - 1 && (
              <div style={{ width: 20, height: 1, background: i < currentIdx ? T.green : T.border, margin: "0 2px" }}/>
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      {step === "input" && (
        <KeywordInputForm projectId={projectId} onSubmit={handleInputSubmit} />
      )}
      {step === "generating" && sessionId && (
        <GeneratingView
          projectId={projectId}
          sessionId={sessionId}
          onComplete={handleGenerationComplete}
        />
      )}
      {step === "review" && sessionId && (
        <KeywordReviewUI
          projectId={projectId}
          sessionId={sessionId}
          onConfirm={handleConfirm}
        />
      )}
      {step === "confirmed" && confirmResult && (
        <ConfirmedView result={confirmResult} onRestart={handleRestart} />
      )}
    </div>
  )
}
