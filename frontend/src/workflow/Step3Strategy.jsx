// Step 3 — SEO/AEO Strategy
// Substep A: Business & Audience Profile (pre-filled, with AI suggestions)
// Substep B: AI generates the full strategy via SSE stream (8-phase live console)
// Substep C: Rich strategy plan review with regional, audience, publishing, priorities
// Goal: Top 5 in Google Search AND AI search (ChatGPT, Gemini, Perplexity)

import { useState, useEffect, useRef, useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNotification } from "../store/notification"
import useWorkflowContext from "../store/workflowContext"
import { apiCall, T, Card, Btn, Spinner, LiveConsole } from "./shared"

const API = import.meta.env.VITE_API_URL || ""

function authHeaders() {
  const token = localStorage.getItem("annaseo_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ─── Sub-step indicator ───────────────────────────────────────────────────────
function SubStepBar({ sub }) {
  const steps = ["Business Profile", "AI Generation", "Strategy Plan"]
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: 20 }}>
      {steps.map((label, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", flex: 1 }}>
          <div style={{
            width: 24, height: 24, borderRadius: "50%", flexShrink: 0,
            background: i + 1 <= sub ? T.purple : T.border,
            color: i + 1 <= sub ? "#fff" : T.textSoft,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 11, fontWeight: 700,
          }}>
            {i + 1 < sub ? "✓" : i + 1}
          </div>
          <span style={{
            fontSize: 11, marginLeft: 6, fontWeight: i + 1 === sub ? 700 : 400,
            color: i + 1 <= sub ? T.purple : T.textSoft, flexShrink: 0,
          }}>{label}</span>
          {i < steps.length - 1 && (
            <div style={{
              flex: 1, height: 2, margin: "0 8px",
              background: i + 1 < sub ? T.purple : T.border,
            }} />
          )}
        </div>
      ))}
    </div>
  )
}

// ─── Chip input helper ────────────────────────────────────────────────────────
function ChipInput({ items, onChange, placeholder, color }) {
  const [val, setVal] = useState("")
  const clr = color || T.purple
  const add = () => {
    const v = val.trim()
    if (v && !items.includes(v)) { onChange([...items, v]); setVal("") }
  }
  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
        <input
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => e.key === "Enter" && add()}
          placeholder={placeholder}
          style={{ flex: 1, padding: "6px 9px", borderRadius: 7, border: `1px solid ${T.border}`, fontSize: 12 }}
        />
        <Btn small onClick={add}>+ Add</Btn>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
        {items.map((it, i) => (
          <span key={i} style={{
            display: "inline-flex", alignItems: "center", gap: 3,
            padding: "3px 9px", borderRadius: 20, fontSize: 11, fontWeight: 500,
            background: clr + "18", color: clr, border: `1px solid ${clr}33`,
          }}>
            {it}
            <button
              onClick={() => onChange(items.filter((_, j) => j !== i))}
              style={{ border: "none", background: "transparent", cursor: "pointer", color: T.red, fontSize: 14, lineHeight: 1, padding: 0 }}
            >×</button>
          </span>
        ))}
      </div>
    </div>
  )
}

// ─── Discovery Summary Panel ──────────────────────────────────────────────────
function DiscoverySummary({ projectId }) {
  const { data, isLoading } = useQuery({
    queryKey: ["discovery-summary", projectId],
    queryFn: () => apiCall(`/api/strategy/${projectId}/discovery-summary`),
    enabled: !!projectId, retry: false, staleTime: 60000,
  })

  if (isLoading) return (
    <Card style={{ padding: 14, marginBottom: 14, background: T.purpleLight, border: `1px solid ${T.purple}22` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Spinner /> <span style={{ fontSize: 11, color: T.textSoft }}>Loading discovery data…</span>
      </div>
    </Card>
  )

  if (!data || !data.total_keywords) return null

  const intentColors = { informational: T.teal, transactional: T.amber, navigational: T.purple, commercial: "#007AFF", mixed: T.gray }
  const totalIntent = Object.values(data.intent_distribution || {}).reduce((a, b) => a + b, 0) || 1

  return (
    <Card style={{ padding: 14, marginBottom: 14, background: `linear-gradient(135deg, ${T.purpleLight}, ${T.tealLight})`, border: `1px solid ${T.purple}22` }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: T.purple }}>
          📊 Discovery Summary — Step 2 Results
        </div>
        <div style={{ fontSize: 10, color: T.textSoft }}>
          Session: {data.session_id?.slice(0, 8)}…
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
        <div style={{ background: "#fff", borderRadius: 8, padding: "8px 14px", textAlign: "center", flex: 1, border: `1px solid ${T.purple}15` }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: T.purple }}>{data.total_keywords.toLocaleString()}</div>
          <div style={{ fontSize: 9, color: T.textSoft }}>Keywords</div>
        </div>
        <div style={{ background: "#fff", borderRadius: 8, padding: "8px 14px", textAlign: "center", flex: 1, border: `1px solid ${T.teal}15` }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: T.teal }}>{data.pillars?.length || 0}</div>
          <div style={{ fontSize: 9, color: T.textSoft }}>Pillars</div>
        </div>
        <div style={{ background: "#fff", borderRadius: 8, padding: "8px 14px", textAlign: "center", flex: 1, border: `1px solid ${T.amber}15` }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: T.amber }}>
            {Object.keys(data.sources || {}).length}
          </div>
          <div style={{ fontSize: 9, color: T.textSoft }}>Sources</div>
        </div>
        <div style={{ background: "#fff", borderRadius: 8, padding: "8px 14px", textAlign: "center", flex: 1, border: `1px solid ${T.teal}15` }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: T.teal }}>
            {data.pillars?.reduce((s, p) => s + (p.quick_wins || 0), 0) || 0}
          </div>
          <div style={{ fontSize: 9, color: T.textSoft }}>Quick Wins</div>
        </div>
      </div>

      {/* Pillars list */}
      {data.pillars?.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 5, letterSpacing: 0.3 }}>PILLAR KEYWORDS</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {data.pillars.map((p, i) => (
              <span key={i} style={{
                display: "inline-flex", alignItems: "center", gap: 4,
                padding: "4px 10px", borderRadius: 20, fontSize: 10, fontWeight: 500,
                background: "#fff", border: `1px solid ${T.purple}25`,
              }}>
                <span style={{ fontWeight: 700, color: T.purple }}>{p.name}</span>
                <span style={{ color: T.textSoft }}>·</span>
                <span style={{ color: T.textSoft }}>{p.keywords} kw</span>
                <span style={{ color: T.textSoft }}>·</span>
                <span style={{ color: p.avg_score >= 60 ? T.teal : p.avg_score >= 40 ? T.amber : T.red, fontWeight: 600 }}>
                  {p.avg_score}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Intent distribution bar */}
      {Object.keys(data.intent_distribution || {}).length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 5, letterSpacing: 0.3 }}>INTENT MIX</div>
          <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", background: T.border }}>
            {Object.entries(data.intent_distribution).map(([intent, count], i) => (
              <div key={i} style={{
                width: `${(count / totalIntent) * 100}%`,
                background: intentColors[intent] || T.gray,
                minWidth: 2,
              }} title={`${intent}: ${count}`} />
            ))}
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
            {Object.entries(data.intent_distribution).map(([intent, count], i) => (
              <span key={i} style={{ fontSize: 9, color: intentColors[intent] || T.gray, fontWeight: 500 }}>
                ● {intent} ({count})
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Top keywords preview */}
      {data.top_keywords?.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 5, letterSpacing: 0.3 }}>TOP SCORED KEYWORDS</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {data.top_keywords.slice(0, 8).map((k, i) => (
              <span key={i} style={{
                padding: "3px 8px", borderRadius: 12, fontSize: 10,
                background: "#fff", border: `1px solid ${T.teal}25`, color: T.text,
              }}>
                {k.keyword} <span style={{ color: T.teal, fontWeight: 600 }}>{k.score}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

// ─── P0 Topic Boundaries ─────────────────────────────────────────────────────
function TopicBoundaries({ projectId }) {
  const notify = useNotification(s => s.notify)
  const ctx = useWorkflowContext()
  const [open, setOpen] = useState(false)
  const [allowed, setAllowed] = useState([])
  const [blocked, setBlocked] = useState([])
  const [saving, setSaving] = useState(false)
  const [validating, setValidating] = useState(false)
  const [validation, setValidation] = useState(null)

  const { data } = useQuery({
    queryKey: ["topic-boundaries", projectId],
    queryFn: () => apiCall(`/api/strategy/${projectId}/topic-boundaries`),
    enabled: !!projectId, retry: false,
  })

  useEffect(() => {
    if (data) {
      setAllowed(data.allowed_topics || [])
      setBlocked(data.blocked_topics || [])
    }
  }, [data])

  const save = async () => {
    setSaving(true)
    try {
      await fetch(`${API}/api/strategy/${projectId}/topic-boundaries`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ allowed_topics: allowed, blocked_topics: blocked }),
      })
      notify("Topic boundaries saved", "success")
    } catch { notify("Failed to save boundaries", "error") }
    setSaving(false)
  }

  const validate = async () => {
    setValidating(true)
    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/validate-keywords`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ session_id: ctx.sessionId }),
      })
      const d = await res.json()
      setValidation(d)
      if (d.blocked > 0) notify(`P0: ${d.blocked} keywords blocked by topic boundaries`, "warning")
      else notify(`P0: All ${d.passed} keywords pass validation`, "success")
    } catch { notify("Validation failed", "error") }
    setValidating(false)
  }

  const hasBoundaries = allowed.length > 0 || blocked.length > 0

  return (
    <Card style={{ padding: 0, marginBottom: 14, overflow: "hidden", border: `1px solid ${hasBoundaries ? T.amber : T.border}33` }}>
      <div onClick={() => setOpen(!open)} style={{
        padding: "10px 14px", cursor: "pointer",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: open ? `${T.amber}08` : "transparent",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 13 }}>🛡️</span>
          <span style={{ fontSize: 11, fontWeight: 700, color: T.amber, letterSpacing: 0.3 }}>
            P0 TOPIC BOUNDARIES
          </span>
          {hasBoundaries && (
            <span style={{ fontSize: 9, color: T.textSoft }}>
              {allowed.length} allowed · {blocked.length} blocked
            </span>
          )}
        </div>
        <span style={{ fontSize: 14, color: T.textSoft, transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}>▾</span>
      </div>
      {open && (
        <div style={{ padding: 14 }}>
          <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 12 }}>
            Block irrelevant topics before they enter strategy. Keywords matching blocked topics will be flagged.
            If allowed topics are set, ONLY keywords matching them will pass.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 12 }}>
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: T.teal, marginBottom: 4 }}>
                ✅ ALLOWED TOPICS (optional — whitelist)
              </div>
              <ChipInput items={allowed} onChange={setAllowed}
                placeholder="e.g., spices, organic, cooking" color={T.teal} />
              <div style={{ fontSize: 9, color: T.textSoft, marginTop: 3 }}>
                If set, only keywords containing these terms pass
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: T.red, marginBottom: 4 }}>
                🚫 BLOCKED TOPICS (blacklist)
              </div>
              <ChipInput items={blocked} onChange={setBlocked}
                placeholder="e.g., wholesale, dropshipping" color={T.red} />
              <div style={{ fontSize: 9, color: T.textSoft, marginTop: 3 }}>
                Keywords containing these terms will be blocked
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Btn small onClick={save} disabled={saving}>
              {saving ? "Saving…" : "💾 Save Boundaries"}
            </Btn>
            {ctx.sessionId && (
              <Btn small variant="teal" onClick={validate} disabled={validating}>
                {validating ? <><Spinner /> Checking…</> : "🔍 Validate Keywords"}
              </Btn>
            )}
          </div>

          {/* Validation results */}
          {validation && (
            <div style={{ marginTop: 10 }}>
              <div style={{ display: "flex", gap: 10, marginBottom: 8 }}>
                <div style={{ background: T.tealLight, borderRadius: 6, padding: "6px 12px", fontSize: 11, fontWeight: 600, color: T.teal }}>
                  ✅ {validation.passed} passed
                </div>
                <div style={{ background: validation.blocked > 0 ? "#fef2f2" : T.grayLight,
                  borderRadius: 6, padding: "6px 12px", fontSize: 11, fontWeight: 600,
                  color: validation.blocked > 0 ? T.red : T.textSoft }}>
                  🚫 {validation.blocked} blocked
                </div>
                <div style={{ fontSize: 11, color: T.textSoft, alignSelf: "center" }}>
                  of {validation.total} total keywords
                </div>
              </div>
              {validation.blocked_keywords?.length > 0 && (
                <div style={{ maxHeight: 140, overflowY: "auto", background: "#fef2f2", borderRadius: 6, padding: 8 }}>
                  {validation.blocked_keywords.slice(0, 20).map((bk, i) => (
                    <div key={i} style={{ fontSize: 10, marginBottom: 3, display: "flex", gap: 6 }}>
                      <span style={{ color: T.red, fontWeight: 600 }}>✗</span>
                      <span style={{ fontWeight: 500 }}>{bk.keyword}</span>
                      <span style={{ color: T.textSoft }}>— {bk.reason}</span>
                    </div>
                  ))}
                  {validation.blocked_keywords.length > 20 && (
                    <div style={{ fontSize: 9, color: T.textSoft, marginTop: 4 }}>
                      …and {validation.blocked_keywords.length - 20} more
                    </div>
                  )}
                </div>
              )}
              {validation.message && !validation.blocked_keywords?.length && (
                <div style={{ fontSize: 10, color: T.textSoft }}>{validation.message}</div>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ─── Competitor Intelligence ──────────────────────────────────────────────────
function CompetitorIntel({ projectId, competitorUrls }) {
  const notify = useNotification(s => s.notify)
  const ctx = useWorkflowContext()
  const [open, setOpen] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [results, setResults] = useState(null)

  const analyze = async () => {
    if (!competitorUrls?.length) { notify("Add competitor URLs first", "warning"); return }
    setAnalyzing(true)
    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/analyze-competitors`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ competitor_urls: competitorUrls, session_id: ctx.sessionId }),
      })
      const d = await res.json()
      setResults(d)
      if (d.summary?.total_gap_keywords > 0)
        notify(`Found ${d.summary.total_gap_keywords} gap keywords from competitors`, "success")
      else
        notify("Competitor analysis complete", "success")
    } catch { notify("Competitor analysis failed", "error") }
    setAnalyzing(false)
  }

  const hasUrls = competitorUrls?.length > 0

  return (
    <Card style={{ padding: 0, marginBottom: 14, overflow: "hidden", border: `1px solid ${T.amber}33` }}>
      <div onClick={() => setOpen(!open)} style={{
        padding: "10px 14px", cursor: "pointer",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: open ? `${T.amber}08` : "transparent",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 13 }}>🔍</span>
          <span style={{ fontSize: 11, fontWeight: 700, color: T.amber, letterSpacing: 0.3 }}>
            COMPETITOR INTELLIGENCE
          </span>
          {results && (
            <span style={{ fontSize: 9, color: T.textSoft }}>
              {results.summary?.total_competitors || 0} analyzed · {results.summary?.total_gap_keywords || 0} gaps
            </span>
          )}
        </div>
        <span style={{ fontSize: 14, color: T.textSoft, transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}>▾</span>
      </div>
      {open && (
        <div style={{ padding: 14 }}>
          <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 12 }}>
            Crawl competitor websites to discover their keyword strategy and find content gaps you can target.
          </div>

          <div style={{ marginBottom: 12 }}>
            <Btn small variant="primary" onClick={analyze} disabled={analyzing || !hasUrls}>
              {analyzing ? <><Spinner /> Analyzing competitors…</> : `🔍 Analyze ${competitorUrls?.length || 0} Competitors`}
            </Btn>
            {!hasUrls && <span style={{ fontSize: 10, color: T.textSoft, marginLeft: 8 }}>Add competitor URLs below first</span>}
          </div>

          {results && (
            <div>
              {/* Summary */}
              {results.summary && (
                <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
                  <div style={{ background: T.amberLight, borderRadius: 6, padding: "6px 12px", fontSize: 11, fontWeight: 600, color: T.amber }}>
                    {results.summary.total_competitors} competitors
                  </div>
                  <div style={{ background: results.summary.total_gap_keywords > 0 ? T.tealLight : T.grayLight,
                    borderRadius: 6, padding: "6px 12px", fontSize: 11, fontWeight: 600,
                    color: results.summary.total_gap_keywords > 0 ? T.teal : T.textSoft }}>
                    {results.summary.total_gap_keywords} gap keywords found
                  </div>
                </div>
              )}

              {/* Gap keywords */}
              {results.summary?.gap_keywords?.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.teal, marginBottom: 5 }}>🎯 GAP KEYWORDS — Topics competitors rank for that you don't have</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {results.summary.gap_keywords.slice(0, 20).map((g, i) => (
                      <span key={i} style={{
                        padding: "3px 9px", borderRadius: 12, fontSize: 10,
                        background: T.tealLight, border: `1px solid ${T.teal}25`, color: T.text,
                      }}>{g}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Per-competitor details */}
              {results.competitors?.map((c, ci) => (
                <Card key={ci} style={{ padding: 10, marginBottom: 8, background: T.grayLight }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, marginBottom: 4 }}>
                    {c.title || c.url}
                  </div>
                  {c.url !== c.title && <div style={{ fontSize: 9, color: T.textSoft, marginBottom: 6 }}>{c.url}</div>}
                  {c.error && <div style={{ fontSize: 10, color: T.red }}>Error: {c.error}</div>}

                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {c.headings?.length > 0 && (
                      <div style={{ flex: 1, minWidth: 150 }}>
                        <div style={{ fontSize: 9, fontWeight: 700, color: T.textSoft, marginBottom: 3 }}>HEADINGS ({c.headings.length})</div>
                        {c.headings.slice(0, 6).map((h, hi) => (
                          <div key={hi} style={{ fontSize: 10, marginBottom: 1 }}>
                            <span style={{ color: T.purple, fontWeight: 600, fontSize: 9 }}>{h.tag}</span> {h.text}
                          </div>
                        ))}
                      </div>
                    )}
                    {c.topics?.length > 0 && (
                      <div style={{ flex: 1, minWidth: 150 }}>
                        <div style={{ fontSize: 9, fontWeight: 700, color: T.textSoft, marginBottom: 3 }}>BLOG TOPICS ({c.topics.length})</div>
                        {c.topics.slice(0, 6).map((t, ti) => (
                          <div key={ti} style={{ fontSize: 10, marginBottom: 1, color: T.text }}>{t}</div>
                        ))}
                      </div>
                    )}
                    {c.gap_keywords?.length > 0 && (
                      <div style={{ flex: 1, minWidth: 150 }}>
                        <div style={{ fontSize: 9, fontWeight: 700, color: T.teal, marginBottom: 3 }}>GAPS ({c.gap_keywords.length})</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                          {c.gap_keywords.slice(0, 8).map((g, gi) => (
                            <span key={gi} style={{
                              padding: "2px 7px", borderRadius: 10, fontSize: 9,
                              background: T.tealLight, color: T.teal,
                            }}>{g}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </Card>
              ))}

              {/* Common topics */}
              {results.summary?.common_topics?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4 }}>COMMON TOPICS ACROSS COMPETITORS</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {results.summary.common_topics.slice(0, 15).map((t, i) => (
                      <span key={i} style={{
                        padding: "2px 8px", borderRadius: 10, fontSize: 9,
                        background: T.amberLight, color: T.amber, fontWeight: 500,
                      }}>{t}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ─── Signal Engine Panel ──────────────────────────────────────────────────────
function SignalPanel({ projectId }) {
  const [open, setOpen] = useState(false)
  const { data: signals, isLoading } = useQuery({
    queryKey: ["signals", projectId],
    queryFn: () => fetch(`${API}/api/strategy/${projectId}/extract-signals`, { headers: authHeaders() })
      .then(r => r.json()).then(d => d.signals),
    enabled: !!projectId,
    staleTime: 120000,
  })

  if (!signals || isLoading) return null
  const { intent_split = {}, opportunity_tiers = {}, pillar_strength = [], buyer_keywords = [],
    info_keywords = [], question_keywords = [], top_quick_wins = [], competitive_gaps = [],
    keyword_density = {} } = signals

  const totalIntent = Object.values(intent_split).reduce((s, v) => s + v, 0) || 1
  const intentColors = { informational: T.teal, transactional: T.purple, commercial: T.amber, navigational: "#6366f1", unknown: T.gray }

  return (
    <Card style={{ marginBottom: 12, padding: open ? 14 : 10, cursor: !open ? "pointer" : "default",
      borderLeft: `3px solid #007AFF`, transition: "all 0.2s" }}
      onClick={() => !open && setOpen(true)}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#007AFF", textTransform: "uppercase" }}>
          📡 Discovery Signals {keyword_density.total > 0 ? `· ${keyword_density.total} keywords analysed` : ""}
        </div>
        <button onClick={e => { e.stopPropagation(); setOpen(!open) }}
          style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 12, color: T.textSoft }}>
          {open ? "▲" : "▼"}
        </button>
      </div>

      {open && (
        <div style={{ marginTop: 10 }}>
          {/* Signal stats row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
            <div style={{ background: T.tealLight, borderRadius: 8, padding: 8, textAlign: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: T.teal }}>{opportunity_tiers.high || 0}</div>
              <div style={{ fontSize: 9, color: T.teal }}>High Opp.</div>
            </div>
            <div style={{ background: T.amberLight, borderRadius: 8, padding: 8, textAlign: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: T.amber }}>{opportunity_tiers.medium || 0}</div>
              <div style={{ fontSize: 9, color: T.amber }}>Medium Opp.</div>
            </div>
            <div style={{ background: T.purpleLight, borderRadius: 8, padding: 8, textAlign: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: T.purple }}>{buyer_keywords.length}</div>
              <div style={{ fontSize: 9, color: T.purple }}>Buyer Intent</div>
            </div>
            <div style={{ background: "rgba(0,122,255,0.1)", borderRadius: 8, padding: 8, textAlign: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: "#007AFF" }}>{question_keywords.length}</div>
              <div style={{ fontSize: 9, color: "#007AFF" }}>AEO Questions</div>
            </div>
          </div>

          {/* Intent distribution bar */}
          {Object.keys(intent_split).length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4 }}>INTENT DISTRIBUTION</div>
              <div style={{ display: "flex", borderRadius: 6, overflow: "hidden", height: 14 }}>
                {Object.entries(intent_split).map(([intent, cnt], i) => (
                  <div key={i} style={{
                    width: `${(cnt / totalIntent) * 100}%`, background: intentColors[intent] || T.gray,
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <span style={{ fontSize: 8, color: "#fff", fontWeight: 600 }}>{Math.round((cnt / totalIntent) * 100)}%</span>
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 3, flexWrap: "wrap" }}>
                {Object.entries(intent_split).map(([intent, cnt], i) => (
                  <span key={i} style={{ fontSize: 9, color: T.textSoft }}>
                    <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2,
                      background: intentColors[intent] || T.gray, marginRight: 3, verticalAlign: "middle" }} />
                    {intent} ({cnt})
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Keyword signals */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
            {buyer_keywords.length > 0 && (
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: T.purple, marginBottom: 4 }}>💰 BUYER KEYWORDS</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                  {buyer_keywords.slice(0, 10).map((kw, i) => (
                    <span key={i} style={{ padding: "2px 8px", borderRadius: 10, fontSize: 9,
                      background: T.purpleLight, color: T.purple }}>{kw}</span>
                  ))}
                </div>
              </div>
            )}
            {question_keywords.length > 0 && (
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#007AFF", marginBottom: 4 }}>❓ AEO QUESTION KEYWORDS</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                  {question_keywords.slice(0, 10).map((kw, i) => (
                    <span key={i} style={{ padding: "2px 8px", borderRadius: 10, fontSize: 9,
                      background: "rgba(0,122,255,0.1)", color: "#007AFF" }}>{kw}</span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Quick wins */}
          {top_quick_wins.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: T.teal, marginBottom: 4 }}>⚡ QUICK WIN KEYWORDS</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {top_quick_wins.slice(0, 8).map((qw, i) => (
                  <span key={i} style={{ padding: "3px 9px", borderRadius: 10, fontSize: 10, fontWeight: 500,
                    background: T.tealLight, color: T.teal, border: `1px solid ${T.teal}33` }}>
                    {qw.keyword} <span style={{ fontSize: 8, opacity: 0.7 }}>({qw.score})</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Competitive gaps */}
          {competitive_gaps.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: T.amber, marginBottom: 4 }}>🎯 COMPETITIVE GAPS</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {competitive_gaps.slice(0, 8).map((g, i) => (
                  <span key={i} style={{ padding: "3px 9px", borderRadius: 10, fontSize: 10, fontWeight: 500,
                    background: T.amberLight, color: T.amber, border: `1px solid ${T.amber}33` }}>{g}</span>
                ))}
              </div>
            </div>
          )}

          {/* Pillar strength */}
          {pillar_strength.length > 0 && (
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4 }}>PILLAR STRENGTH</div>
              <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
                {pillar_strength.slice(0, 8).map((p, i) => (
                  <div key={i} style={{ minWidth: 100, background: T.grayLight, borderRadius: 6, padding: "6px 8px",
                    textAlign: "center", flexShrink: 0, borderTop: `2px solid ${p.avg_score >= 60 ? T.teal : p.avg_score >= 35 ? T.amber : T.red}` }}>
                    <div style={{ fontSize: 10, fontWeight: 600, marginBottom: 2, lineHeight: 1.2 }}>{p.pillar}</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: p.avg_score >= 60 ? T.teal : p.avg_score >= 35 ? T.amber : T.red }}>{p.avg_score}</div>
                    <div style={{ fontSize: 8, color: T.textSoft }}>{p.count} kws</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ marginTop: 8, fontSize: 9, color: T.textSoft, fontStyle: "italic" }}>
            These signals feed directly into the AI strategy prompt for better keyword targeting and content planning.
          </div>
        </div>
      )}
    </Card>
  )
}

// ─── P7++ Score Panel ─────────────────────────────────────────────────────────
function P7ScorePanel({ projectId, sessionId }) {
  const [open, setOpen] = useState(false)
  const [scored, setScored] = useState(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(null)

  const runScoring = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/score-keywords-p7`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ session_id: sessionId }),
      })
      if (!res.ok) throw new Error("Scoring failed")
      const data = await res.json()
      setScored(data.scored || [])
      setSummary(data.summary || {})
      setOpen(true)
    } catch (e) {
      console.error("P7 scoring error:", e)
    } finally {
      setLoading(false)
    }
  }

  const priorityColors = { critical: T.purple, high: T.teal, medium: T.amber, low: T.gray }
  const subLabels = {
    business_fit: { label: "Business Fit", icon: "🏢", weight: "25%" },
    intent_value: { label: "Intent Value", icon: "🎯", weight: "20%" },
    ranking_feasibility: { label: "Feasibility", icon: "📊", weight: "20%" },
    traffic_potential: { label: "Traffic", icon: "📈", weight: "15%" },
    competitor_gap: { label: "Gap Opp.", icon: "⚡", weight: "10%" },
    content_ease: { label: "Content Ease", icon: "✍️", weight: "10%" },
  }

  return (
    <Card style={{ marginBottom: 12, padding: 14, borderLeft: `3px solid ${T.purple}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, textTransform: "uppercase" }}>
          🧮 P7++ Keyword Scoring {summary ? `· ${summary.total} scored` : ""}
        </div>
        {!scored ? (
          <Btn small onClick={runScoring} disabled={loading}>
            {loading ? <Spinner size={10} /> : "Run P7++ Scoring"}
          </Btn>
        ) : (
          <button onClick={() => setOpen(!open)}
            style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 12, color: T.textSoft }}>
            {open ? "▲" : "▼"}
          </button>
        )}
      </div>

      {summary && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr", gap: 8, marginTop: 10 }}>
          {[
            { label: "Critical", val: summary.critical, color: T.purple },
            { label: "High", val: summary.high, color: T.teal },
            { label: "Medium", val: summary.medium, color: T.amber },
            { label: "Low", val: summary.low, color: T.gray },
            { label: "Avg Score", val: (summary.avg_score * 100).toFixed(0) + "%", color: T.text },
          ].map((s, i) => (
            <div key={i} style={{ background: s.color + "12", borderRadius: 6, padding: 6, textAlign: "center" }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: s.color }}>{s.val}</div>
              <div style={{ fontSize: 8, color: s.color }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {open && scored && (
        <div style={{ marginTop: 12, maxHeight: 400, overflowY: "auto" }}>
          {scored.map((kw, i) => {
            const pc = priorityColors[kw.priority] || T.gray
            const isExpanded = expanded === i
            return (
              <div key={i} style={{
                padding: "8px 10px", borderRadius: 6, marginBottom: 4,
                background: i % 2 === 0 ? T.grayLight : "#fff",
                border: isExpanded ? `1px solid ${pc}44` : `0.5px solid ${T.border}`,
                cursor: "pointer",
              }} onClick={() => setExpanded(isExpanded ? null : i)}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: 11, fontWeight: 600 }}>{kw.keyword}</span>
                    {kw.pillar && <span style={{ fontSize: 9, color: T.textSoft, marginLeft: 6 }}>· {kw.pillar}</span>}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{
                      padding: "2px 8px", borderRadius: 10, fontSize: 9, fontWeight: 600,
                      background: pc + "18", color: pc, textTransform: "uppercase",
                    }}>{kw.priority}</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: pc }}>{(kw.score * 100).toFixed(0)}</span>
                  </div>
                </div>

                {/* Subscore breakdown on expand */}
                {isExpanded && kw.subscores && (
                  <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                    {Object.entries(kw.subscores).map(([key, val]) => {
                      const meta = subLabels[key] || { label: key, icon: "📌", weight: "?" }
                      const barColor = val >= 0.7 ? T.teal : val >= 0.4 ? T.amber : T.red
                      return (
                        <div key={key} style={{ background: "#fff", borderRadius: 4, padding: "4px 6px", border: `0.5px solid ${T.border}` }}>
                          <div style={{ fontSize: 9, color: T.textSoft, marginBottom: 2 }}>
                            {meta.icon} {meta.label} ({meta.weight})
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                            <div style={{ flex: 1, height: 6, background: T.grayLight, borderRadius: 3, overflow: "hidden" }}>
                              <div style={{ width: `${val * 100}%`, height: "100%", background: barColor, borderRadius: 3 }} />
                            </div>
                            <span style={{ fontSize: 10, fontWeight: 600, color: barColor, minWidth: 28, textAlign: "right" }}>
                              {(val * 100).toFixed(0)}%
                            </span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

// ─── SERP Reality Engine ──────────────────────────────────────────────────────
function SERPRealityPanel({ projectId }) {
  const [results, setResults] = useState(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)

  const runCheck = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/serp-reality`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({}),
      })
      if (!res.ok) throw new Error("SERP check failed")
      const data = await res.json()
      setResults(data.results || [])
      setSummary(data.summary || {})
      setOpen(true)
    } catch (e) {
      console.error("SERP reality error:", e)
    } finally {
      setLoading(false)
    }
  }

  const diffColor = (d) => d >= 0.7 ? T.red : d >= 0.4 ? T.amber : T.teal
  const feasColor = (f) => f >= 0.6 ? T.teal : f >= 0.3 ? T.amber : T.red

  return (
    <Card style={{ marginBottom: 12, padding: 14, borderLeft: `3px solid ${T.amber}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: T.amber, textTransform: "uppercase" }}>
          🔍 SERP Reality Engine {summary ? `· ${summary.total_checked} checked` : ""}
        </div>
        {!results ? (
          <Btn small variant="teal" onClick={runCheck} disabled={loading}>
            {loading ? <Spinner size={10} /> : "Check SERP Reality"}
          </Btn>
        ) : (
          <button onClick={() => setOpen(!open)}
            style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 12, color: T.textSoft }}>
            {open ? "▲" : "▼"}
          </button>
        )}
      </div>

      {summary && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 10 }}>
          <div style={{ background: diffColor(summary.avg_difficulty) + "12", borderRadius: 6, padding: 6, textAlign: "center" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: diffColor(summary.avg_difficulty) }}>
              {Math.round(summary.avg_difficulty * 100)}%
            </div>
            <div style={{ fontSize: 8, color: T.textSoft }}>Avg Difficulty</div>
          </div>
          <div style={{ background: feasColor(summary.avg_feasibility) + "12", borderRadius: 6, padding: 6, textAlign: "center" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: feasColor(summary.avg_feasibility) }}>
              {Math.round(summary.avg_feasibility * 100)}%
            </div>
            <div style={{ fontSize: 8, color: T.textSoft }}>Avg Feasibility</div>
          </div>
          <div style={{ background: T.tealLight, borderRadius: 6, padding: 6, textAlign: "center" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.teal }}>{(summary.easy_wins || []).length}</div>
            <div style={{ fontSize: 8, color: T.teal }}>Easy Wins</div>
          </div>
        </div>
      )}

      {open && results && (
        <div style={{ marginTop: 12 }}>
          {results.map((r, i) => (
            <div key={i} style={{
              padding: "8px 10px", borderRadius: 6, marginBottom: 4,
              background: i % 2 === 0 ? T.grayLight : "#fff", border: `0.5px solid ${T.border}`,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 11, fontWeight: 600 }}>{r.keyword}</span>
                <div style={{ display: "flex", gap: 8 }}>
                  <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 8,
                    background: diffColor(r.difficulty) + "18", color: diffColor(r.difficulty), fontWeight: 600 }}>
                    Diff: {Math.round(r.difficulty * 100)}%
                  </span>
                  <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 8,
                    background: feasColor(r.feasibility) + "18", color: feasColor(r.feasibility), fontWeight: 600 }}>
                    Feas: {Math.round(r.feasibility * 100)}%
                  </span>
                  {r.cached && <span style={{ fontSize: 8, color: T.textSoft }}>cached</span>}
                </div>
              </div>
              {/* Dual bar */}
              <div style={{ display: "flex", gap: 4, marginBottom: 4 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ height: 5, background: T.grayLight, borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ width: `${r.difficulty * 100}%`, height: "100%", background: diffColor(r.difficulty), borderRadius: 3 }} />
                  </div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ height: 5, background: T.grayLight, borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ width: `${r.feasibility * 100}%`, height: "100%", background: feasColor(r.feasibility), borderRadius: 3 }} />
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, fontSize: 9, color: T.textSoft }}>
                <span>{r.competitors} competitors</span>
                {(r.gaps || []).length > 0 && <span>· {r.gaps.length} gaps found</span>}
              </div>
              {(r.recommended_angles || []).length > 0 && (
                <div style={{ marginTop: 4, display: "flex", flexWrap: "wrap", gap: 3 }}>
                  {r.recommended_angles.map((a, j) => (
                    <span key={j} style={{ padding: "1px 6px", borderRadius: 8, fontSize: 8,
                      background: T.tealLight, color: T.teal }}>{a}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

// ─── Audience Auto-Detection ──────────────────────────────────────────────────
function AudienceDetect({ projectId, sessionId, onApply }) {
  const [detected, setDetected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [accepted, setAccepted] = useState(new Set())

  const detect = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/detect-audience`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ session_id: sessionId }),
      })
      if (!res.ok) throw new Error("Detection failed")
      const data = await res.json()
      setDetected(data.audiences || [])
      setAccepted(new Set((data.audiences || []).map((_, i) => i)))
    } catch (e) {
      console.error("Audience detect error:", e)
    } finally {
      setLoading(false)
    }
  }

  const toggle = (i) => {
    setAccepted(prev => {
      const next = new Set(prev)
      next.has(i) ? next.delete(i) : next.add(i)
      return next
    })
  }

  const apply = () => {
    if (!detected || !onApply) return
    const personas = detected.filter((_, i) => accepted.has(i)).map(a => a.persona)
    onApply(personas)
  }

  const confColor = (c) => c >= 0.7 ? T.teal : c >= 0.4 ? T.amber : T.red

  return (
    <Card style={{ marginBottom: 12, padding: 14, borderLeft: `3px solid ${T.teal}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: T.teal, textTransform: "uppercase" }}>
          👥 Target Audience Detection
        </div>
        {!detected ? (
          <Btn small variant="teal" onClick={detect} disabled={loading}>
            {loading ? <Spinner size={10} /> : "Detect Audiences"}
          </Btn>
        ) : (
          <Btn small onClick={apply}>Apply {accepted.size} Audiences</Btn>
        )}
      </div>

      {detected && detected.length === 0 && (
        <div style={{ marginTop: 8, fontSize: 11, color: T.textSoft }}>
          No clear audience patterns detected. Add target audiences manually.
        </div>
      )}

      {detected && detected.length > 0 && (
        <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {detected.map((a, i) => (
            <div key={i} onClick={() => toggle(i)} style={{
              padding: 10, borderRadius: 8, cursor: "pointer", transition: "all 0.15s",
              background: accepted.has(i) ? T.tealLight : T.grayLight,
              border: `1px solid ${accepted.has(i) ? T.teal + "44" : T.border}`,
              opacity: accepted.has(i) ? 1 : 0.6,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 11, fontWeight: 700 }}>
                  {accepted.has(i) ? "✓ " : ""}{a.persona}
                </span>
                <span style={{
                  fontSize: 10, fontWeight: 700, color: confColor(a.confidence),
                  background: confColor(a.confidence) + "18", padding: "1px 6px", borderRadius: 8,
                }}>{Math.round(a.confidence * 100)}%</span>
              </div>
              <div style={{ fontSize: 9, color: T.textSoft, marginBottom: 4 }}>
                Intent: {a.intent} · {a.keyword_matches} keyword matches
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                {(a.sample_keywords || []).map((kw, j) => (
                  <span key={j} style={{
                    padding: "1px 6px", borderRadius: 8, fontSize: 8,
                    background: accepted.has(i) ? T.teal + "18" : T.grayLight,
                    color: T.textSoft,
                  }}>{kw}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

// ─── AI Suggest button ────────────────────────────────────────────────────────
function AISuggestBtn({ projectId, type, context, onSuggestions }) {
  const [loading, setLoading] = useState(false)
  const suggest = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/ai-suggest`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ type, context }),
      })
      const data = await res.json()
      if (data.suggestions) onSuggestions(data.suggestions)
    } catch { /* ignore */ }
    setLoading(false)
  }
  return (
    <button onClick={suggest} disabled={loading} style={{
      border: `1px solid ${T.purple}44`, background: T.purpleLight, borderRadius: 6,
      padding: "3px 10px", fontSize: 10, fontWeight: 600, color: T.purple,
      cursor: loading ? "wait" : "pointer", opacity: loading ? 0.6 : 1,
      display: "inline-flex", alignItems: "center", gap: 4,
    }}>
      {loading ? <Spinner /> : "🔮"} AI Suggest
    </button>
  )
}

// ─── SUBSTEP A — Business & Audience Profile ──────────────────────────────────
function ProfileSubStep({ projectId, onNext, onBack }) {
  const notify = useNotification(s => s.notify)
  const ctx = useWorkflowContext()
  const step1 = ctx.step1 || {}

  const { data: apData } = useQuery({
    queryKey: ["audience", projectId],
    queryFn: () => apiCall(`/api/strategy/${projectId}/audience`),
    enabled: !!projectId, retry: false,
  })
  const { data: projData } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => apiCall(`/api/projects/${projectId}`),
    enabled: !!projectId,
  })

  function safeList(val, def) {
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
    strategy_name: "",
    rank_target: "top5",
    timeframe_months: 6,
    blogs_per_week: 3,
  })
  const [errors, setErrors] = useState([])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const ap = apData || {}
    const pr = projData || {}
    setForm(prev => ({
      ...prev,
      website_url: ap.website_url || step1.customerUrl || pr.customer_url || prev.website_url,
      business_type: ap.business_type || pr.business_type || prev.business_type,
      usp: ap.usp || pr.usp || prev.usp,
      target_locations: safeList(ap.target_locations || pr.target_locations || null, prev.target_locations),
      target_languages: safeList(ap.target_languages || pr.target_languages || null, prev.target_languages),
      target_religions: safeList(ap.target_religions, prev.target_religions),
      personas: safeList(ap.personas, prev.personas),
      products: safeList(ap.products, prev.products),
      competitor_urls: safeList(ap.competitor_urls || step1.competitorUrls || pr.competitor_urls || null, prev.competitor_urls),
      customer_reviews: ap.customer_reviews || pr.customer_reviews || prev.customer_reviews,
    }))
  }, [apData, projData])

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }))

  const inStyle = {
    width: "100%", padding: "6px 9px", borderRadius: 7,
    border: `1px solid ${T.border}`, fontSize: 12, boxSizing: "border-box",
  }
  const labelStyle = { fontSize: 11, fontWeight: 600, color: T.textSoft, display: "block", marginBottom: 4 }

  // Build context for AI suggestions
  const suggestCtx = {
    business_type: form.business_type,
    industry: projData?.industry || "",
    products: form.products,
    locations: form.target_locations,
    languages: form.target_languages,
    pillars: [],
    brand: projData?.name || step1.customerUrl || "",
  }

  const handleNext = async () => {
    const errs = []
    if (!form.target_locations.length) errs.push("Add at least one target location")
    if (!form.target_languages.length) errs.push("Add at least one language")
    if (!form.personas.length) errs.push("Add at least one target audience")
    if (!form.products.length) errs.push("Add at least one product or service")
    if (errs.length) { setErrors(errs); return }
    setErrors([])
    setSaving(true)
    try {
      await fetch(`${API}/api/strategy/${projectId}/audience`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ ...form, intent_focus: "transactional", pillar_support_map: {} }),
      })
    } catch { /* best-effort save */ }
    setSaving(false)
    onNext(form)
  }

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 3 }}>Business & Audience Profile</div>
        <div style={{ fontSize: 12, color: T.textSoft }}>
          Tell us about your business and who you serve. Use 🔮 AI Suggest for smart recommendations.
        </div>
      </div>

      {/* Discovery data from Step 2 */}
      <DiscoverySummary projectId={projectId} />

      {/* P0 Topic boundaries */}
      <TopicBoundaries projectId={projectId} />

      {/* Competitor Intelligence */}
      <CompetitorIntel projectId={projectId} competitorUrls={form.competitor_urls} />

      {/* Discovery Signals */}
      <SignalPanel projectId={projectId} />

      {/* P7++ Scoring */}
      <P7ScorePanel projectId={projectId} sessionId={ctx.sessionId} />

      {/* Audience Auto-Detection */}
      <AudienceDetect projectId={projectId} sessionId={ctx.sessionId}
        onApply={(personas) => {
          set("personas", [...new Set([...form.personas, ...personas])])
          notify(`Added ${personas.length} detected audiences`, "success")
        }} />

      {/* SERP Reality Engine */}
      <SERPRealityPanel projectId={projectId} />

      {/* Strategy name + goals row */}
      <Card style={{ padding: 14, marginBottom: 12 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: T.purple, marginBottom: 10 }}>Strategy Settings</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>
          <div>
            <label style={labelStyle}>Strategy Name</label>
            <input value={form.strategy_name} onChange={e => set("strategy_name", e.target.value)}
              placeholder="e.g., Q1 Spice Campaign" style={inStyle} />
          </div>
          <div>
            <label style={labelStyle}>Ranking Goal</label>
            <select value={form.rank_target} onChange={e => set("rank_target", e.target.value)} style={inStyle}>
              <option value="top1">🥇 #1 — Dominate</option>
              <option value="top3">🥉 Top 3 — Competitive</option>
              <option value="top5">🏆 Top 5 — Balanced</option>
              <option value="top10">📈 Top 10 — Growth</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Timeframe</label>
            <select value={form.timeframe_months} onChange={e => set("timeframe_months", +e.target.value)} style={inStyle}>
              <option value={3}>3 months — Sprint</option>
              <option value={6}>6 months — Standard</option>
              <option value={12}>12 months — Steady</option>
              <option value={24}>24 months — Dominate</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Blogs / Week</label>
            <select value={form.blogs_per_week} onChange={e => set("blogs_per_week", +e.target.value)} style={inStyle}>
              <option value={1}>1/week — Light</option>
              <option value={2}>2/week — Moderate</option>
              <option value={3}>3/week — Active</option>
              <option value={5}>5/week — Aggressive</option>
              <option value={7}>7/week — Full Throttle</option>
            </select>
          </div>
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Card style={{ padding: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.purple, marginBottom: 10 }}>Your Business</div>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Website URL</label>
              <input value={form.website_url} onChange={e => set("website_url", e.target.value)}
                placeholder="https://yourbusiness.com" style={inStyle} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={labelStyle}>Business Type</label>
              <select value={form.business_type} onChange={e => set("business_type", e.target.value)} style={inStyle}>
                <option value="B2C">B2C — Selling to consumers</option>
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
                placeholder="What makes you different? e.g., Organic certified, 24h delivery, lowest price"
                style={{ ...inStyle, height: 60, resize: "vertical", fontFamily: "inherit" }} />
            </div>
          </Card>

          <Card style={{ padding: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 10 }}>Products & Services</div>
            <ChipInput items={form.products} onChange={v => set("products", v)}
              placeholder="Add product/service (Enter)" color={T.teal} />
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 5 }}>
              e.g., Organic Turmeric, Spice Blends, Delivery Service
            </div>
          </Card>

          <Card style={{ padding: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.amber, marginBottom: 10 }}>Competitor Websites</div>
            <ChipInput items={form.competitor_urls} onChange={v => set("competitor_urls", v)}
              placeholder="https://competitor.com (Enter)" color={T.amber} />
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 5 }}>
              AI will analyse gaps vs your competitors
            </div>
          </Card>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Card style={{ padding: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.purple, marginBottom: 10 }}>Target Market</div>
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <label style={{ ...labelStyle, marginBottom: 0 }}>Target Locations / Regions</label>
                <AISuggestBtn projectId={projectId} type="regions" context={suggestCtx}
                  onSuggestions={s => set("target_locations", [...new Set([...form.target_locations, ...s.map(x => typeof x === "string" ? x : x.region || x.name)])])} />
              </div>
              <ChipInput items={form.target_locations} onChange={v => set("target_locations", v)}
                placeholder="Country or state (Enter)" color={T.purple} />
            </div>
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <label style={{ ...labelStyle, marginBottom: 0 }}>Content Languages</label>
                <AISuggestBtn projectId={projectId} type="languages" context={suggestCtx}
                  onSuggestions={s => set("target_languages", [...new Set([...form.target_languages, ...s.map(x => typeof x === "string" ? x : x.language || x.name)])])} />
              </div>
              <ChipInput items={form.target_languages} onChange={v => set("target_languages", v)}
                placeholder="Language (Enter)" color={T.purple} />
              <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3 }}>e.g., English, Hindi, Tamil, Malayalam</div>
            </div>
            <div>
              <label style={labelStyle}>Cultural / Religious Context</label>
              <ChipInput items={form.target_religions} onChange={v => set("target_religions", v)}
                placeholder="e.g., Hindu, Muslim, general (Enter)" color={T.purple} />
              <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3 }}>Helps time seasonal content (Onam, Eid, Diwali…)</div>
            </div>
          </Card>

          <Card style={{ padding: 14 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: T.teal }}>Target Audiences</div>
              <AISuggestBtn projectId={projectId} type="personas" context={suggestCtx}
                onSuggestions={s => set("personas", [...new Set([...form.personas, ...s.map(x => typeof x === "string" ? x : x.audience || x.persona || x.name)])])} />
            </div>
            <ChipInput items={form.personas} onChange={v => set("personas", v)}
              placeholder="e.g., Health-conscious home cooks (Enter)" color={T.teal} />
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 5 }}>Who are your target audiences? Describe the groups you want to reach.</div>
            <div style={{ marginTop: 10 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <label style={labelStyle}>Customer Reviews / Insights (optional)</label>
                <AISuggestBtn projectId={projectId} type="reviews" context={suggestCtx}
                  onSuggestions={s => {
                    const reviews = s.map(x => typeof x === "string" ? x : x.review || x.name || "").filter(Boolean)
                    const combined = [form.customer_reviews, ...reviews].filter(Boolean).join("\n• ")
                    set("customer_reviews", combined.startsWith("• ") ? combined : "• " + combined)
                  }} />
              </div>
              <textarea value={form.customer_reviews} onChange={e => set("customer_reviews", e.target.value)}
                placeholder="Common questions or feedback from customers…"
                style={{ ...inStyle, height: 55, resize: "vertical", fontFamily: "inherit" }} />
            </div>
          </Card>
        </div>
      </div>

      {errors.length > 0 && (
        <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: 10, marginTop: 12 }}>
          {errors.map((e, i) => <div key={i} style={{ fontSize: 11, color: T.red }}>• {e}</div>)}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16 }}>
        <Btn onClick={onBack}>← Back</Btn>
        <Btn variant="primary" onClick={handleNext} disabled={saving}>
          {saving ? <><Spinner /> Saving…</> : "Save & Generate Strategy →"}
        </Btn>
      </div>
    </div>
  )
}

// ─── SUBSTEP B — AI Generation (SSE) ─────────────────────────────────────────
function GenerateSubStep({ projectId, sessionId, audience, onBack, onComplete }) {
  const notify = useNotification(s => s.notify)
  const [logs, setLogs]     = useState([])
  const [status, setStatus] = useState("running")
  const [error, setError]   = useState("")
  const [phase, setPhase]   = useState("")
  const abortRef = useRef(null)

  useEffect(() => () => abortRef.current?.abort(), [])

  const run = useCallback(() => {
    setStatus("running"); setLogs([]); setError(""); setPhase("")
    const ctrl = new AbortController()
    abortRef.current = ctrl

    fetch(`${API}/api/ki/${projectId}/strategy/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ session_id: sessionId, audience }),
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
                setLogs(prev => [...prev.slice(-299), { msg: ev.msg, level: ev.level || "info" }])
                // Track phase from [X/8] pattern
                const pm = ev.msg?.match?.(/\[(\d+\/8)\]/)
                if (pm) setPhase(pm[1])
              } else if (ev.type === "complete") {
                setStatus("done")
                notify("Strategy generated", "success")
                onComplete(ev.strategy, ev.ai_source)
              } else if (ev.type === "error") {
                setError(ev.msg || "Generation failed")
                setStatus("error")
              }
            } catch { /* ignore parse errors */ }
          }
        }
        setStatus(s => s === "running" ? "done" : s)
      })
      .catch(e => {
        if (e.name !== "AbortError") { setError(String(e)); setStatus("error") }
      })
  }, [projectId, sessionId, audience])

  useEffect(() => { run() }, [run])

  // Phase progress bar
  const phaseNum = phase ? parseInt(phase.split("/")[0]) : 0
  const phasePct = Math.round((phaseNum / 8) * 100)

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 3 }}>Generating SEO/AEO Strategy</div>
        <div style={{ fontSize: 12, color: T.textSoft }}>
          AI is analysing your keywords and building a personalised Top-5 ranking strategy.
        </div>
      </div>

      <Card style={{ padding: 14, marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <div style={{
            width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
            background: status === "done" ? T.teal : status === "error" ? T.red : T.purple,
          }} />
          <div style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>
            {status === "running" && (phase ? `Phase ${phase} — Generating strategy…` : "Starting AI engine…")}
            {status === "done" && "Strategy generated successfully!"}
            {status === "error" && "Generation failed"}
          </div>
          {status === "running" && <Spinner />}
        </div>

        {/* Phase progress bar */}
        {status === "running" && (
          <div style={{ marginBottom: 10 }}>
            <div style={{ height: 4, borderRadius: 2, background: T.border, overflow: "hidden" }}>
              <div style={{
                height: "100%", borderRadius: 2, background: T.purple,
                width: `${phasePct}%`, transition: "width 0.5s ease",
              }} />
            </div>
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3, textAlign: "right" }}>
              {phaseNum}/8 phases
            </div>
          </div>
        )}

        <LiveConsole logs={logs} running={status === "running"} maxHeight={280} title="STRATEGY ENGINE" />

        {error && (
          <div style={{ marginTop: 10, padding: "8px 12px", background: "#fef2f2", borderRadius: 7, fontSize: 12, color: T.red }}>
            ✗ {error}
          </div>
        )}
      </Card>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Btn onClick={onBack} disabled={status === "running"}>← Edit Profile</Btn>
        <div style={{ display: "flex", gap: 8 }}>
          {status === "error" && <Btn onClick={run}>↻ Retry</Btn>}
          {status === "done" && (
            <div style={{ fontSize: 12, color: T.teal, fontWeight: 600 }}>✓ Reviewing strategy below…</div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Collapsible section helper ───────────────────────────────────────────────
function Section({ title, color, icon, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card style={{ padding: 0, marginBottom: 12, overflow: "hidden" }}>
      <div onClick={() => setOpen(!open)} style={{
        padding: "10px 14px", cursor: "pointer",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: open ? (color || T.purple) + "08" : "transparent",
        borderBottom: open ? `1px solid ${T.border}` : "none",
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: color || T.purple, textTransform: "uppercase" }}>
          {icon && <span style={{ marginRight: 6 }}>{icon}</span>}{title}
        </div>
        <span style={{ fontSize: 14, color: T.textSoft, transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}>▾</span>
      </div>
      {open && <div style={{ padding: 14 }}>{children}</div>}
    </Card>
  )
}

// ─── Priority Badge ───────────────────────────────────────────────────────────
function PriorityBadge({ level }) {
  const colors = { high: T.red, medium: T.amber, low: T.teal, avoid: T.gray }
  const c = colors[level] || T.gray
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 20, fontSize: 9, fontWeight: 700,
      background: c + "18", color: c, border: `1px solid ${c}33`, textTransform: "uppercase",
    }}>{level}</span>
  )
}

// ─── SUBSTEP C — Strategy Plan Review ────────────────────────────────────────
function PlanSubStep({ strategy: initialStrategy, aiSource, onBack, onConfirm, onUpdate, projectId }) {
  const notify = useNotification(s => s.notify)
  const [confirmed, setConfirmed] = useState(false)
  const [activeTab, setActiveTab] = useState("overview")
  const [editing, setEditing] = useState(false)
  const [strat, setStrat] = useState(initialStrategy)

  useEffect(() => { if (initialStrategy) setStrat(initialStrategy) }, [initialStrategy])

  if (!strat) return <div style={{ color: T.textSoft, padding: 20 }}>No strategy data.</div>

  // Edit helpers
  const updateField = (path, value) => {
    setStrat(prev => {
      const next = JSON.parse(JSON.stringify(prev))
      const keys = path.split(".")
      let obj = next
      for (let i = 0; i < keys.length - 1; i++) {
        if (obj[keys[i]] === undefined) obj[keys[i]] = {}
        obj = obj[keys[i]]
      }
      obj[keys[keys.length - 1]] = value
      return next
    })
  }

  const saveEdits = () => {
    setEditing(false)
    if (onUpdate) onUpdate(strat)
    notify("Strategy edits saved", "success")
  }

  const EditBtn = ({ onClick }) => editing ? null : (
    <button onClick={onClick || (() => setEditing(true))} style={{
      border: `1px solid ${T.purple}33`, background: T.purpleLight, borderRadius: 5,
      padding: "2px 8px", fontSize: 9, fontWeight: 600, color: T.purple, cursor: "pointer",
    }}>✏️ Edit</button>
  )

  const conf = strat.strategy_confidence || 0
  const confClr = conf >= 75 ? T.teal : conf >= 50 ? T.amber : T.red
  const aiLabel = aiSource && !aiSource.includes("rule") ? `AI (${aiSource})` : "Rule-based fallback"

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "pillars", label: "Pillars & Keywords" },
    { id: "audience", label: "Audience" },
    { id: "content", label: "Content Plan" },
    { id: "priorities", label: "Priorities" },
  ]

  return (
    <div>
      {/* Header with confidence */}
      <div style={{ marginBottom: 14, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 2 }}>Your SEO/AEO Strategy Plan</div>
          <div style={{ fontSize: 11, color: T.textSoft }}>
            Generated by {aiLabel} · {editing ? "Editing mode — make changes below" : "Review and confirm to proceed"}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          {!confirmed && (
            editing ? (
              <Btn small variant="teal" onClick={saveEdits}>💾 Save Edits</Btn>
            ) : (
              <Btn small onClick={() => setEditing(true)}>✏️ Edit Strategy</Btn>
            )
          )}
          {strat.total_articles_planned && (
            <div style={{ background: T.purpleLight, borderRadius: 8, padding: "5px 10px", textAlign: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: T.purple }}>{strat.total_articles_planned}</div>
              <div style={{ fontSize: 9, color: T.purple }}>Articles</div>
            </div>
          )}
          <div style={{
            background: confClr + "18", border: `1px solid ${confClr}33`,
            borderRadius: 8, padding: "5px 12px", textAlign: "center",
          }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: confClr }}>{conf}%</div>
            <div style={{ fontSize: 9, color: confClr }}>Confidence</div>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div style={{ display: "flex", gap: 4, marginBottom: 14, borderBottom: `1px solid ${T.border}`, paddingBottom: 8 }}>
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
            padding: "6px 14px", borderRadius: "8px 8px 0 0", border: "none", fontSize: 11, fontWeight: 600,
            cursor: "pointer", transition: "all 0.15s",
            background: activeTab === tab.id ? T.purple : "transparent",
            color: activeTab === tab.id ? "#fff" : T.textSoft,
          }}>{tab.label}</button>
        ))}
      </div>

      {/* ── Overview Tab ── */}
      {activeTab === "overview" && (
        <div>
          {strat.executive_summary && (
            <div style={{
              background: T.purpleLight, borderRadius: 10, padding: "12px 14px", marginBottom: 12,
              borderLeft: `3px solid ${T.purple}`,
            }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, marginBottom: 6, textTransform: "uppercase" }}>Executive Summary</div>
              {editing ? (
                <textarea value={strat.executive_summary} onChange={e => updateField("executive_summary", e.target.value)}
                  style={{ width: "100%", minHeight: 80, fontSize: 12, lineHeight: 1.6, padding: 8, borderRadius: 6,
                    border: `1px solid ${T.purple}44`, background: "#fff", resize: "vertical", fontFamily: "inherit" }} />
              ) : (
                <div style={{ fontSize: 12, lineHeight: 1.6 }}>{strat.executive_summary}</div>
              )}
            </div>
          )}

          {strat.seo_goals && (
            <Card style={{ marginBottom: 12, padding: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, marginBottom: 8, textTransform: "uppercase" }}>
                Ranking Goals — Top 5 in Google + AI Search
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                {[
                  { icon: "🔍", label: "Google Target", val: strat.seo_goals.google_target, field: "seo_goals.google_target" },
                  { icon: "🤖", label: "AI Search", val: strat.seo_goals.ai_search_target, field: "seo_goals.ai_search_target" },
                  { icon: "📈", label: "Traffic Goal", val: strat.seo_goals.monthly_traffic_target, field: "seo_goals.monthly_traffic_target" },
                ].map((g, i) => (
                  <div key={i} style={{ background: T.grayLight, borderRadius: 8, padding: 10, textAlign: "center" }}>
                    <div style={{ fontSize: 18, marginBottom: 4 }}>{g.icon}</div>
                    <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 3 }}>{g.label}</div>
                    {editing ? (
                      <input value={g.val || ""} onChange={e => updateField(g.field, e.target.value)}
                        style={{ width: "100%", fontSize: 11, fontWeight: 600, textAlign: "center", padding: "3px 6px",
                          borderRadius: 4, border: `1px solid ${T.purple}44`, background: "#fff" }} />
                    ) : (
                      <div style={{ fontSize: 11, fontWeight: 600 }}>{g.val}</div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Growth Projection */}
          {strat.growth_projection && (
            <Card style={{ marginBottom: 12, padding: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: T.teal, marginBottom: 8, textTransform: "uppercase" }}>
                📊 Growth Projection
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8 }}>
                {Object.entries(strat.growth_projection).map(([k, v], i) => (
                  <div key={i} style={{ background: T.grayLight, borderRadius: 8, padding: 10, textAlign: "center" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: T.teal, marginBottom: 4 }}>
                      {k.replace("month_", "Month ")}
                    </div>
                    <div style={{ fontSize: 10, lineHeight: 1.4 }}>{v}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {(strat.quick_wins || []).length > 0 && (
              <Card style={{ padding: 14 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.teal, marginBottom: 8, textTransform: "uppercase" }}>
                  ⚡ Quick Wins — Do This Week
                </div>
                <ul style={{ margin: 0, paddingLeft: 14 }}>
                  {strat.quick_wins.map((w, i) => (
                    <li key={i} style={{ fontSize: 11, marginBottom: 5, lineHeight: 1.4, display: "flex", alignItems: "center", gap: 6 }}>
                      {editing ? (
                        <>
                          <input value={w} onChange={e => {
                            const nw = [...strat.quick_wins]; nw[i] = e.target.value; updateField("quick_wins", nw)
                          }} style={{ flex: 1, fontSize: 11, padding: "3px 6px", borderRadius: 4, border: `1px solid ${T.teal}44` }} />
                          <button onClick={() => updateField("quick_wins", strat.quick_wins.filter((_, j) => j !== i))}
                            style={{ border: "none", background: T.red + "22", color: T.red, borderRadius: 4, padding: "2px 6px", fontSize: 10, cursor: "pointer" }}>✕</button>
                        </>
                      ) : w}
                    </li>
                  ))}
                </ul>
                {editing && (
                  <button onClick={() => updateField("quick_wins", [...(strat.quick_wins || []), ""])}
                    style={{ marginTop: 6, fontSize: 10, color: T.teal, background: T.tealLight, border: `1px solid ${T.teal}33`,
                      borderRadius: 4, padding: "3px 10px", cursor: "pointer" }}>+ Add Quick Win</button>
                )}
              </Card>
            )}
            {(strat.kpis || []).length > 0 && (
              <Card style={{ padding: 14 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, marginBottom: 8, textTransform: "uppercase" }}>
                  📏 KPIs to Track
                </div>
                {strat.kpis.map((kpi, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6, fontSize: 11, gap: 6 }}>
                    {editing ? (
                      <>
                        <input value={kpi.metric} onChange={e => {
                          const nk = [...strat.kpis]; nk[i] = { ...nk[i], metric: e.target.value }; updateField("kpis", nk)
                        }} style={{ flex: 1, fontSize: 11, padding: "3px 6px", borderRadius: 4, border: `1px solid ${T.purple}44` }} />
                        <input value={kpi.target} onChange={e => {
                          const nk = [...strat.kpis]; nk[i] = { ...nk[i], target: e.target.value }; updateField("kpis", nk)
                        }} style={{ width: 80, fontSize: 11, padding: "3px 6px", borderRadius: 4, border: `1px solid ${T.teal}44`, textAlign: "center" }} />
                        <input value={kpi.timeframe} onChange={e => {
                          const nk = [...strat.kpis]; nk[i] = { ...nk[i], timeframe: e.target.value }; updateField("kpis", nk)
                        }} style={{ width: 70, fontSize: 11, padding: "3px 6px", borderRadius: 4, border: `1px solid ${T.border}`, textAlign: "center" }} />
                        <button onClick={() => updateField("kpis", strat.kpis.filter((_, j) => j !== i))}
                          style={{ border: "none", background: T.red + "22", color: T.red, borderRadius: 4, padding: "2px 6px", fontSize: 10, cursor: "pointer" }}>✕</button>
                      </>
                    ) : (
                      <>
                        <span style={{ fontWeight: 500 }}>{kpi.metric}</span>
                        <span style={{ color: T.teal, fontWeight: 600 }}>{kpi.target} <span style={{ color: T.textSoft, fontWeight: 400 }}>({kpi.timeframe})</span></span>
                      </>
                    )}
                  </div>
                ))}
                {editing && (
                  <button onClick={() => updateField("kpis", [...(strat.kpis || []), { metric: "", target: "", timeframe: "" }])}
                    style={{ marginTop: 6, fontSize: 10, color: T.purple, background: T.purpleLight, border: `1px solid ${T.purple}33`,
                      borderRadius: 4, padding: "3px 10px", cursor: "pointer" }}>+ Add KPI</button>
                )}
              </Card>
            )}
          </div>
        </div>
      )}

      {/* ── Pillars & Keywords Tab ── */}
      {activeTab === "pillars" && (
        <div>
          {(strat.pillar_strategy || []).map((p, i) => {
            const dc = { low: T.teal, medium: T.amber, high: T.red }[p.current_difficulty] || T.gray
            return (
              <Section key={i} title={p.pillar} color={T.purple} defaultOpen={i < 3}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 10 }}>
                  <div style={{ background: T.grayLight, borderRadius: 6, padding: 8, textAlign: "center" }}>
                    <div style={{ fontSize: 18, fontWeight: 700, color: p.target_rank <= 3 ? T.teal : T.amber }}>#{p.target_rank}</div>
                    <div style={{ fontSize: 9, color: T.textSoft }}>Target Rank</div>
                  </div>
                  <div style={{ background: T.grayLight, borderRadius: 6, padding: 8, textAlign: "center" }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: dc }}>{p.current_difficulty}</div>
                    <div style={{ fontSize: 9, color: T.textSoft }}>Difficulty</div>
                  </div>
                  <div style={{ background: T.grayLight, borderRadius: 6, padding: 8, textAlign: "center" }}>
                    <div style={{ fontSize: 11, fontWeight: 600 }}>{p.content_type}</div>
                    <div style={{ fontSize: 9, color: T.textSoft }}>Content Type</div>
                  </div>
                </div>

                {p.rationale && (
                  <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 10, lineHeight: 1.5, fontStyle: "italic" }}>
                    {p.rationale}
                  </div>
                )}

                {/* Regional Keywords */}
                {(p.regional_keywords || []).length > 0 && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: T.amber, marginBottom: 4, textTransform: "uppercase" }}>🌍 Regional Keywords</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {p.regional_keywords.map((kw, j) => (
                        <span key={j} style={{
                          display: "inline-block", padding: "3px 9px", borderRadius: 20, fontSize: 10,
                          background: T.amberLight, color: T.amber, border: `1px solid ${T.amber}33`,
                        }}>{kw}</span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Language Keywords */}
                {p.language_keywords && Object.keys(p.language_keywords).length > 0 && (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: T.teal, marginBottom: 4, textTransform: "uppercase" }}>🗣️ Language Keywords</div>
                    {Object.entries(p.language_keywords).map(([lang, kws], j) => (
                      <div key={j} style={{ marginBottom: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 600, color: T.teal, marginRight: 6 }}>{lang}:</span>
                        {(Array.isArray(kws) ? kws : [kws]).map((kw, k) => (
                          <span key={k} style={{
                            display: "inline-block", padding: "2px 8px", borderRadius: 20, fontSize: 10, marginRight: 4,
                            background: T.tealLight, color: T.teal, border: `1px solid ${T.teal}33`,
                          }}>{kw}</span>
                        ))}
                      </div>
                    ))}
                  </div>
                )}

                {/* Audience Questions */}
                {(p.audience_questions || []).length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 700, color: T.purple, marginBottom: 4, textTransform: "uppercase" }}>❓ People Also Ask (AEO)</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
                      {p.audience_questions.map((q, j) => (
                        <div key={j} style={{
                          padding: "6px 10px", borderRadius: 6, fontSize: 10, lineHeight: 1.4,
                          background: T.purpleLight, border: `1px solid ${T.purple}22`,
                        }}>
                          💬 {q}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Section>
            )
          })}

          {/* Regional Expansion */}
          {(strat.regional_expansion || []).length > 0 && (
            <Section title="Regional Expansion" color={T.amber} icon="🌍">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {strat.regional_expansion.map((r, i) => (
                  <div key={i} style={{ background: T.grayLight, borderRadius: 8, padding: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <span style={{ fontSize: 12, fontWeight: 700 }}>{r.region}</span>
                      <PriorityBadge level={r.opportunity} />
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                      {(r.keywords || []).map((kw, j) => (
                        <span key={j} style={{
                          display: "inline-block", padding: "2px 7px", borderRadius: 20, fontSize: 9,
                          background: T.amberLight, color: T.amber, border: `1px solid ${T.amber}33`,
                        }}>{kw}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}
        </div>
      )}

      {/* ── Audience Tab ── */}
      {activeTab === "audience" && (
        <div>
          {strat.audience_strategy?.primary_audiences?.length > 0 && (
            <Section title="Target Audiences" color={T.teal} icon="👥">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {strat.audience_strategy.primary_audiences.map((a, i) => (
                  <div key={i} style={{ background: T.grayLight, borderRadius: 8, padding: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <span style={{ fontSize: 12, fontWeight: 700 }}>{a.persona}</span>
                      <PriorityBadge level={a.priority} />
                    </div>
                    <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 2 }}>
                      Intent: <span style={{ fontWeight: 600, color: T.teal }}>{a.search_intent}</span>
                    </div>
                    <div style={{ fontSize: 10, lineHeight: 1.4 }}>{a.content_focus}</div>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {strat.audience_strategy?.audience_questions && (
            <Section title="Audience Question Bank" color={T.purple} icon="❓">
              {Object.entries(strat.audience_strategy.audience_questions).map(([cat, qs], i) => (
                <div key={i} style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.purple, marginBottom: 4, textTransform: "uppercase" }}>
                    {cat.replace(/_/g, " ")}
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {(Array.isArray(qs) ? qs : [qs]).map((q, j) => (
                      <span key={j} style={{
                        display: "inline-block", padding: "3px 10px", borderRadius: 20, fontSize: 10,
                        background: T.purpleLight, color: T.purple, border: `1px solid ${T.purple}22`,
                      }}>{q}</span>
                    ))}
                  </div>
                </div>
              ))}
            </Section>
          )}

          {(strat.aeo_tactics || []).length > 0 && (
            <Section title="AEO Tactics — AI Search Visibility" color={T.purple} icon="🤖">
              <ul style={{ margin: 0, paddingLeft: 14 }}>
                {strat.aeo_tactics.map((t, i) => (
                  <li key={i} style={{ fontSize: 11, marginBottom: 6, lineHeight: 1.4 }}>🤖 {t}</li>
                ))}
              </ul>
            </Section>
          )}

          {(strat.competitor_gap_opportunities || []).length > 0 && (
            <Section title="Competitor Gap Opportunities" color={T.amber} icon="⚡">
              <ul style={{ margin: 0, paddingLeft: 14 }}>
                {strat.competitor_gap_opportunities.map((g, i) => (
                  <li key={i} style={{ fontSize: 11, marginBottom: 5, lineHeight: 1.4 }}>⚡ {g}</li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      )}

      {/* ── Content Plan Tab ── */}
      {activeTab === "content" && (
        <div>
          {/* Publishing Plan Summary */}
          {strat.publishing_plan && (
            <Card style={{ padding: 14, marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: T.teal, marginBottom: 8, textTransform: "uppercase" }}>
                📅 Publishing Plan
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 10 }}>
                <div style={{ background: T.grayLight, borderRadius: 8, padding: 10, textAlign: "center" }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: T.purple }}>{strat.publishing_plan.blogs_per_week || 3}</div>
                  <div style={{ fontSize: 9, color: T.textSoft }}>Blogs / Week</div>
                </div>
                <div style={{ background: T.grayLight, borderRadius: 8, padding: 10, textAlign: "center" }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: T.teal }}>{strat.publishing_plan.blogs_per_pillar || "-"}</div>
                  <div style={{ fontSize: 9, color: T.textSoft }}>Per Pillar</div>
                </div>
                <div style={{ background: T.grayLight, borderRadius: 8, padding: 10, textAlign: "center" }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: T.amber }}>{strat.publishing_plan.total_planned || strat.total_articles_planned || "-"}</div>
                  <div style={{ fontSize: 9, color: T.textSoft }}>Total Planned</div>
                </div>
              </div>

              {/* Priority Sequence */}
              {(strat.publishing_plan.priority_sequence || []).length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4 }}>PRIORITY SEQUENCE</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {strat.publishing_plan.priority_sequence.map((p, i) => (
                      <span key={i} style={{
                        display: "inline-flex", alignItems: "center", gap: 4,
                        padding: "3px 10px", borderRadius: 20, fontSize: 10,
                        background: i === 0 ? T.tealLight : T.grayLight,
                        color: i === 0 ? T.teal : T.text,
                        border: `1px solid ${i === 0 ? T.teal : T.border}33`,
                        fontWeight: i === 0 ? 600 : 400,
                      }}>
                        <span style={{ fontWeight: 700, color: T.textSoft }}>{i + 1}.</span> {p}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Weekly Schedule */}
              {(strat.publishing_plan.weekly_schedule || []).length > 0 && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 4 }}>WEEKLY SCHEDULE</div>
                  <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
                    {strat.publishing_plan.weekly_schedule.slice(0, 8).map((w, i) => (
                      <div key={i} style={{
                        minWidth: 160, background: T.grayLight, borderRadius: 8, padding: 10, flexShrink: 0,
                      }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: T.purple, marginBottom: 4 }}>Week {w.week}</div>
                        {(w.articles || []).map((a, j) => (
                          <div key={j} style={{
                            background: "#fff", borderRadius: 5, padding: "4px 8px", marginBottom: 3,
                            fontSize: 10, border: `0.5px solid ${T.border}`, lineHeight: 1.3,
                          }}>{a}</div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}

          {/* Monthly Content Calendar */}
          {(strat.content_calendar || []).length > 0 && (
            <Card style={{ padding: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, marginBottom: 8, textTransform: "uppercase" }}>
                📋 Content Calendar — {strat.posting_frequency || "2+ articles/week"}
              </div>
              <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
                {strat.content_calendar.slice(0, 6).map((month, i) => (
                  <div key={i} style={{ minWidth: 200, background: T.grayLight, borderRadius: 8, padding: 10, flexShrink: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, marginBottom: 6 }}>
                      {month.month}
                      {month.focus_pillar && <span style={{ color: T.textSoft, fontWeight: 400 }}> · {month.focus_pillar}</span>}
                    </div>
                    {month.theme && <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 6, fontStyle: "italic" }}>{month.theme}</div>}
                    {(month.articles || []).map((a, j) => {
                      const typeClrs = { pillar: T.purple, supporting: T.teal, faq: T.amber, aeo: "#007AFF", regional: T.amber, language: "#34C759" }
                      const tc = typeClrs[a.type] || T.gray
                      return (
                        <div key={j} style={{
                          background: "#fff", borderRadius: 6, padding: "6px 8px", marginBottom: 4,
                          border: `0.5px solid ${T.border}`, borderLeft: `3px solid ${tc}`,
                        }}>
                          {editing ? (
                            <input value={a.title} onChange={e => {
                              const cal = JSON.parse(JSON.stringify(strat.content_calendar))
                              cal[i].articles[j] = { ...cal[i].articles[j], title: e.target.value }
                              updateField("content_calendar", cal)
                            }} style={{ width: "100%", fontSize: 11, fontWeight: 500, padding: "2px 4px", marginBottom: 2,
                              borderRadius: 4, border: `1px solid ${tc}44`, background: "#fff" }} />
                          ) : (
                            <div style={{ fontSize: 11, fontWeight: 500, marginBottom: 2 }}>{a.title}</div>
                          )}
                          <div style={{ fontSize: 10, color: T.textSoft, display: "flex", gap: 6, flexWrap: "wrap" }}>
                            <span style={{ color: tc, fontWeight: 600 }}>{a.type}</span>
                            <span>{a.word_count || 1500}w</span>
                            {a.aeo_optimized && <span style={{ color: T.purple }}>🤖 AEO</span>}
                            {a.language && a.language !== "English" && <span style={{ color: T.teal }}>🗣️ {a.language}</span>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ── Priorities Tab ── */}
      {activeTab === "priorities" && (
        <div>
          {strat.keyword_priorities && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 12 }}>
              {/* High Priority */}
              {(strat.keyword_priorities.high_priority || []).length > 0 && (
                <Card style={{ padding: 14, borderTop: `3px solid ${T.teal}` }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: T.teal, marginBottom: 8, textTransform: "uppercase" }}>
                    🟢 High Priority
                  </div>
                  {strat.keyword_priorities.high_priority.map((kp, i) => (
                    <div key={i} style={{
                      padding: "6px 10px", borderRadius: 6, marginBottom: 4,
                      background: T.tealLight, border: `1px solid ${T.teal}22`,
                      display: "flex", alignItems: "center", gap: 6,
                    }}>
                      <div style={{ flex: 1 }}>
                        {editing ? (
                          <>
                            <input value={kp.keyword} onChange={e => {
                              const nk = JSON.parse(JSON.stringify(strat.keyword_priorities))
                              nk.high_priority[i].keyword = e.target.value; updateField("keyword_priorities", nk)
                            }} style={{ width: "100%", fontSize: 11, fontWeight: 600, padding: "2px 4px", marginBottom: 2,
                              borderRadius: 4, border: `1px solid ${T.teal}44`, background: "#fff" }} />
                            <input value={kp.reason} onChange={e => {
                              const nk = JSON.parse(JSON.stringify(strat.keyword_priorities))
                              nk.high_priority[i].reason = e.target.value; updateField("keyword_priorities", nk)
                            }} style={{ width: "100%", fontSize: 9, padding: "2px 4px", borderRadius: 4,
                              border: `1px solid ${T.border}`, background: "#fff" }} />
                          </>
                        ) : (
                          <>
                            <div style={{ fontSize: 11, fontWeight: 600 }}>{kp.keyword}</div>
                            <div style={{ fontSize: 9, color: T.textSoft }}>{kp.reason}</div>
                          </>
                        )}
                      </div>
                      {editing && (
                        <button onClick={() => {
                          const nk = JSON.parse(JSON.stringify(strat.keyword_priorities))
                          nk.high_priority.splice(i, 1); updateField("keyword_priorities", nk)
                        }} style={{ border: "none", background: T.red + "22", color: T.red, borderRadius: 4, padding: "2px 6px", fontSize: 10, cursor: "pointer", flexShrink: 0 }}>✕</button>
                      )}
                    </div>
                  ))}
                </Card>
              )}

              {/* Medium Priority */}
              {(strat.keyword_priorities.medium_priority || []).length > 0 && (
                <Card style={{ padding: 14, borderTop: `3px solid ${T.amber}` }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: T.amber, marginBottom: 8, textTransform: "uppercase" }}>
                    🟡 Medium Priority
                  </div>
                  {strat.keyword_priorities.medium_priority.map((kp, i) => (
                    <div key={i} style={{
                      padding: "6px 10px", borderRadius: 6, marginBottom: 4,
                      background: T.amberLight, border: `1px solid ${T.amber}22`,
                      display: "flex", alignItems: "center", gap: 6,
                    }}>
                      <div style={{ flex: 1 }}>
                        {editing ? (
                          <>
                            <input value={kp.keyword} onChange={e => {
                              const nk = JSON.parse(JSON.stringify(strat.keyword_priorities))
                              nk.medium_priority[i].keyword = e.target.value; updateField("keyword_priorities", nk)
                            }} style={{ width: "100%", fontSize: 11, fontWeight: 600, padding: "2px 4px", marginBottom: 2,
                              borderRadius: 4, border: `1px solid ${T.amber}44`, background: "#fff" }} />
                            <input value={kp.reason} onChange={e => {
                              const nk = JSON.parse(JSON.stringify(strat.keyword_priorities))
                              nk.medium_priority[i].reason = e.target.value; updateField("keyword_priorities", nk)
                            }} style={{ width: "100%", fontSize: 9, padding: "2px 4px", borderRadius: 4,
                              border: `1px solid ${T.border}`, background: "#fff" }} />
                          </>
                        ) : (
                          <>
                            <div style={{ fontSize: 11, fontWeight: 600 }}>{kp.keyword}</div>
                            <div style={{ fontSize: 9, color: T.textSoft }}>{kp.reason}</div>
                          </>
                        )}
                      </div>
                      {editing && (
                        <button onClick={() => {
                          const nk = JSON.parse(JSON.stringify(strat.keyword_priorities))
                          nk.medium_priority.splice(i, 1); updateField("keyword_priorities", nk)
                        }} style={{ border: "none", background: T.red + "22", color: T.red, borderRadius: 4, padding: "2px 6px", fontSize: 10, cursor: "pointer", flexShrink: 0 }}>✕</button>
                      )}
                    </div>
                  ))}
                </Card>
              )}

              {/* Avoid */}
              {(strat.keyword_priorities.avoid || []).length > 0 && (
                <Card style={{ padding: 14, borderTop: `3px solid ${T.red}` }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: T.red, marginBottom: 8, textTransform: "uppercase" }}>
                    🔴 Avoid
                  </div>
                  {strat.keyword_priorities.avoid.map((kp, i) => (
                    <div key={i} style={{
                      padding: "6px 10px", borderRadius: 6, marginBottom: 4,
                      background: "#fef2f2", border: `1px solid ${T.red}22`,
                      display: "flex", alignItems: "center", gap: 6,
                    }}>
                      <div style={{ flex: 1 }}>
                        {editing ? (
                          <>
                            <input value={kp.keyword} onChange={e => {
                              const nk = JSON.parse(JSON.stringify(strat.keyword_priorities))
                              nk.avoid[i].keyword = e.target.value; updateField("keyword_priorities", nk)
                            }} style={{ width: "100%", fontSize: 11, fontWeight: 600, padding: "2px 4px", marginBottom: 2,
                              borderRadius: 4, border: `1px solid ${T.red}44`, background: "#fff" }} />
                            <input value={kp.reason} onChange={e => {
                              const nk = JSON.parse(JSON.stringify(strat.keyword_priorities))
                              nk.avoid[i].reason = e.target.value; updateField("keyword_priorities", nk)
                            }} style={{ width: "100%", fontSize: 9, padding: "2px 4px", borderRadius: 4,
                              border: `1px solid ${T.border}`, background: "#fff" }} />
                          </>
                        ) : (
                          <>
                            <div style={{ fontSize: 11, fontWeight: 600 }}>{kp.keyword}</div>
                            <div style={{ fontSize: 9, color: T.textSoft }}>{kp.reason}</div>
                          </>
                        )}
                      </div>
                      {editing && (
                        <button onClick={() => {
                          const nk = JSON.parse(JSON.stringify(strat.keyword_priorities))
                          nk.avoid.splice(i, 1); updateField("keyword_priorities", nk)
                        }} style={{ border: "none", background: T.red + "22", color: T.red, borderRadius: 4, padding: "2px 6px", fontSize: 10, cursor: "pointer", flexShrink: 0 }}>✕</button>
                      )}
                    </div>
                  ))}
                </Card>
              )}
            </div>
          )}

          {/* Pillar Strategy Summary table */}
          {(strat.pillar_strategy || []).length > 0 && (
            <Card style={{ padding: 14, marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, marginBottom: 8, textTransform: "uppercase" }}>
                Pillar Priority Summary
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 700, color: T.textSoft }}>Pillar</th>
                    <th style={{ textAlign: "center", padding: "6px 8px", fontWeight: 700, color: T.textSoft }}>Target</th>
                    <th style={{ textAlign: "center", padding: "6px 8px", fontWeight: 700, color: T.textSoft }}>Difficulty</th>
                    <th style={{ textAlign: "center", padding: "6px 8px", fontWeight: 700, color: T.textSoft }}>Volume</th>
                    <th style={{ textAlign: "center", padding: "6px 8px", fontWeight: 700, color: T.textSoft }}>Type</th>
                    <th style={{ textAlign: "center", padding: "6px 8px", fontWeight: 700, color: T.textSoft }}>AI Opp</th>
                  </tr>
                </thead>
                <tbody>
                  {strat.pillar_strategy.map((p, i) => {
                    const dc = { low: T.teal, medium: T.amber, high: T.red }[p.current_difficulty] || T.gray
                    return (
                      <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }}>
                        <td style={{ padding: "6px 8px", fontWeight: 600 }}>{p.pillar}</td>
                        <td style={{ textAlign: "center", padding: "6px 8px" }}>
                          <span style={{ fontWeight: 700, color: p.target_rank <= 3 ? T.teal : T.amber }}>#{p.target_rank}</span>
                        </td>
                        <td style={{ textAlign: "center", padding: "6px 8px" }}>
                          <span style={{ color: dc, fontWeight: 600 }}>{p.current_difficulty}</span>
                        </td>
                        <td style={{ textAlign: "center", padding: "6px 8px", color: T.textSoft }}>{p.estimated_monthly_searches || "-"}</td>
                        <td style={{ textAlign: "center", padding: "6px 8px" }}>{p.content_type}</td>
                        <td style={{ textAlign: "center", padding: "6px 8px" }}>{p.ai_snippet_opportunity ? "🤖" : "-"}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}

      {/* Confirm bar */}
      <Card style={{
        padding: 14, marginTop: 12,
        background: confirmed ? T.tealLight : T.purpleLight,
        border: `1px solid ${confirmed ? T.teal : T.purple}33`,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            {confirmed
              ? <div style={{ fontSize: 13, fontWeight: 700, color: T.teal }}>✓ Strategy confirmed — proceeding to keyword review</div>
              : <div style={{ fontSize: 12 }}>Strategy looks good? Confirm to proceed to keyword review.</div>
            }
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {/* Export buttons */}
            {projectId && (
              <>
                <a href={`${API}/api/strategy/${projectId}/export/csv`} download
                  style={{ display: "inline-flex", alignItems: "center", padding: "5px 10px", borderRadius: 6,
                    fontSize: 10, fontWeight: 600, background: T.grayLight, color: T.textSoft, border: `1px solid ${T.border}`,
                    textDecoration: "none", cursor: "pointer" }}>📥 CSV</a>
                <a href={`${API}/api/strategy/${projectId}/export/json`} download
                  style={{ display: "inline-flex", alignItems: "center", padding: "5px 10px", borderRadius: 6,
                    fontSize: 10, fontWeight: 600, background: T.grayLight, color: T.textSoft, border: `1px solid ${T.border}`,
                    textDecoration: "none", cursor: "pointer" }}>📥 JSON</a>
              </>
            )}
            <Btn onClick={onBack}>← Edit Profile</Btn>
            {!confirmed && (
              <Btn variant="teal" onClick={() => { setConfirmed(true); setTimeout(onConfirm, 600) }}>
                ✓ Confirm &amp; Review Keywords
              </Btn>
            )}
          </div>
        </div>
      </Card>
    </div>
  )
}

// ─── Strategy Switcher (Multi-Strategy Support) ───────────────────────────────
function StrategySwitcher({ projectId, onLoad }) {
  const [open, setOpen] = useState(false)
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(false)
  const [renaming, setRenaming] = useState(null)
  const [newName, setNewName] = useState("")
  const notify = useNotification(s => s.notify)

  const loadSessions = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/sessions`, { headers: authHeaders() })
      if (!res.ok) return
      const data = await res.json()
      setSessions(data)
      setOpen(true)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const loadSession = async (sid) => {
    try {
      const res = await fetch(`${API}/api/strategy/${projectId}/sessions/${sid}`, { headers: authHeaders() })
      if (!res.ok) throw new Error("Load failed")
      const data = await res.json()
      const result = typeof data.result_json === "string" ? JSON.parse(data.result_json || "{}") : (data.result_json || {})
      if (onLoad) onLoad(result, data.engine_type)
      setOpen(false)
      notify("Strategy loaded", "success")
    } catch (e) {
      notify("Failed to load strategy", "error")
    }
  }

  const rename = async (sid) => {
    if (!newName.trim()) return
    try {
      await fetch(`${API}/api/strategy/${projectId}/sessions/${sid}/rename`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ name: newName.trim() }),
      })
      setSessions(prev => prev.map(s => s.session_id === sid ? { ...s, strategy_name: newName.trim() } : s))
      setRenaming(null)
      setNewName("")
    } catch (e) {
      notify("Rename failed", "error")
    }
  }

  if (!open) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
        <button onClick={loadSessions} disabled={loading}
          style={{ fontSize: 10, color: T.purple, background: T.purpleLight, border: `1px solid ${T.purple}33`,
            borderRadius: 6, padding: "4px 12px", cursor: "pointer", fontWeight: 600 }}>
          {loading ? "Loading…" : "📋 Saved Strategies"}
        </button>
      </div>
    )
  }

  return (
    <Card style={{ padding: 14, marginBottom: 12, borderLeft: `3px solid ${T.purple}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, textTransform: "uppercase" }}>
          📋 Saved Strategies ({sessions.length})
        </div>
        <button onClick={() => setOpen(false)}
          style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 12, color: T.textSoft }}>✕</button>
      </div>
      {sessions.length === 0 && (
        <div style={{ fontSize: 11, color: T.textSoft }}>No saved strategies yet. Generate one first.</div>
      )}
      {sessions.map((s, i) => (
        <div key={s.session_id} style={{
          padding: "8px 10px", borderRadius: 6, marginBottom: 4,
          background: i % 2 === 0 ? T.grayLight : "#fff", border: `0.5px solid ${T.border}`,
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <div style={{ flex: 1 }}>
            {renaming === s.session_id ? (
              <div style={{ display: "flex", gap: 4 }}>
                <input value={newName} onChange={e => setNewName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && rename(s.session_id)}
                  placeholder="Strategy name" autoFocus
                  style={{ flex: 1, fontSize: 11, padding: "2px 6px", borderRadius: 4, border: `1px solid ${T.purple}44` }} />
                <button onClick={() => rename(s.session_id)}
                  style={{ fontSize: 9, color: T.teal, background: T.tealLight, border: `1px solid ${T.teal}33`,
                    borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}>✓</button>
                <button onClick={() => { setRenaming(null); setNewName("") }}
                  style={{ fontSize: 9, color: T.red, background: "#fef2f2", border: `1px solid ${T.red}33`,
                    borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}>✕</button>
              </div>
            ) : (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600 }}>{s.strategy_name}</div>
                <div style={{ fontSize: 9, color: T.textSoft }}>
                  {s.engine_type} · confidence: {s.confidence || 0}% · {(s.created_at || "").slice(0, 16)}
                </div>
              </div>
            )}
          </div>
          <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
            <button onClick={() => { setRenaming(s.session_id); setNewName(s.strategy_name || "") }}
              style={{ fontSize: 9, color: T.purple, background: T.purpleLight, border: `1px solid ${T.purple}33`,
                borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}>✏️</button>
            <Btn small onClick={() => loadSession(s.session_id)}>Load</Btn>
          </div>
        </div>
      ))}
    </Card>
  )
}

// ─── MAIN ─────────────────────────────────────────────────────────────────────
export default function Step3Strategy({ projectId, onComplete, onBack }) {
  const notify = useNotification(s => s.notify)
  const ctx = useWorkflowContext()

  const [sub, setSub]           = useState(1)
  const [audience, setAudience] = useState(null)
  const [strategy, setStrategy] = useState(null)
  const [aiSource, setAiSource] = useState("")

  useEffect(() => {
    if (ctx.step3?.strategy_json && !strategy) {
      setStrategy(ctx.step3.strategy_json)
      setAiSource(ctx.step3.ai_source || "")
      setSub(3)
    }
  }, [])

  const handleProfileNext = (form) => { setAudience(form); setSub(2) }

  const handleStrategyReady = (strat, src) => {
    setStrategy(strat)
    setAiSource(src || "")
    ctx.setStep(3, { strategy_json: strat, ai_source: src || "" })
    ctx.flush(projectId).catch(() => {})
    setSub(3)
  }

  return (
    <div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <Card>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, letterSpacing: 0.5, marginBottom: 2 }}>
            STEP 3 — SEO/AEO STRATEGY
          </div>
          <div style={{ fontSize: 11, color: T.textSoft }}>
            Build a plan to reach Top 5 in Google Search + AI search (ChatGPT, Gemini, Perplexity)
          </div>
        </div>

        <SubStepBar sub={sub} />

        {/* Multi-strategy switcher */}
        <StrategySwitcher projectId={projectId} onLoad={(strat, src) => {
          setStrategy(strat)
          setAiSource(src || "")
          ctx.setStep(3, { strategy_json: strat, ai_source: src || "" })
          ctx.flush(projectId).catch(() => {})
          setSub(3)
        }} />

        {sub === 1 && (
          <ProfileSubStep projectId={projectId} onNext={handleProfileNext} onBack={onBack} />
        )}

        {sub === 2 && (
          <GenerateSubStep
            projectId={projectId}
            sessionId={ctx.sessionId}
            audience={audience}
            onBack={() => setSub(1)}
            onComplete={handleStrategyReady}
          />
        )}

        {sub === 3 && (
          <PlanSubStep
            strategy={strategy}
            aiSource={aiSource}
            projectId={projectId}
            onBack={() => setSub(1)}
            onConfirm={() => onComplete && onComplete()}
            onUpdate={(edited) => {
              setStrategy(edited)
              ctx.setStep(3, { strategy_json: edited, ai_source: aiSource })
              ctx.flush(projectId).catch(() => {})
            }}
          />
        )}
      </Card>
    </div>
  )
}
