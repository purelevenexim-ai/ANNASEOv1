/**
 * Phase BI — Business Intelligence (redesigned).
 *
 * Architecture: poll-based (no fragile SSE).
 * - Step A: Profile form  (optional, auto-saves)
 * - Steps B+C+D: single "Run BI Analysis" → POST /run-all → poll /progress
 * - Results reload from /biz-intel once done.
 */
import React, { useState, useEffect, useCallback, useRef } from "react"
import useKw2Store from "./store"
import apiCall from "../lib/apiCall"
import * as api from "./api"
import { Card, RunButton, Badge, StatsRow, Spinner, PhaseResult, usePhaseRunner } from "./shared"

// ─── Constants ───────────────────────────────────────────────────────────────

const GOALS_OPTIONS = ["Sales", "Lead Generation", "Brand Awareness", "Traffic", "Wholesale B2B", "Export", "Local Presence"]
const PRICING_OPTIONS = ["budget", "mid-range", "premium", "bulk/wholesale", "subscription", "custom/quote"]
const INTENT_COLORS = { homepage: "#3b82f6", landing_page: "#10b981", product_page: "#8b5cf6", pillar_page: "#f59e0b", blog_post: "#6b7280", other: "#d1d5db" }
const FUNNEL_COLORS = { BOFU: "#10b981", MOFU: "#f59e0b", TOFU: "#9ca3af", none: "#e5e7eb" }

// ─── Small Helpers ────────────────────────────────────────────────────────────

function Tag({ children, color = "blue", onRemove }) {
  const BG = { blue: "#dbeafe", green: "#d1fae5", amber: "#fef3c7", gray: "#f3f4f6", purple: "#ede9fe", red: "#fee2e2" }
  const TX = { blue: "#1d4ed8", green: "#065f46", amber: "#92400e", gray: "#374151", purple: "#5b21b6", red: "#991b1b" }
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 3, padding: "2px 8px", borderRadius: 12, background: BG[color] || BG.blue, color: TX[color] || TX.blue, fontSize: 12, fontWeight: 500, margin: "2px" }}>
      {children}
      {onRemove && <span onClick={onRemove} style={{ cursor: "pointer", opacity: 0.6, marginLeft: 2 }}>✕</span>}
    </span>
  )
}

function CheckTag({ label, checked, onChange }) {
  return (
    <span onClick={() => onChange(!checked)} style={{
      display: "inline-flex", alignItems: "center", gap: 4, padding: "4px 10px",
      borderRadius: 12, cursor: "pointer",
      border: `1px solid ${checked ? "#3b82f6" : "#d1d5db"}`,
      background: checked ? "#eff6ff" : "#fff",
      color: checked ? "#1d4ed8" : "#6b7280",
      fontSize: 12, fontWeight: checked ? 600 : 400, margin: "3px", transition: "all 150ms",
    }}>
      {checked && <span style={{ fontSize: 10 }}>✓</span>}
      {label}
    </span>
  )
}

// ─── Progress Bar ─────────────────────────────────────────────────────────────

function ProgressBar({ pct, message, color = "#3b82f6" }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 12, color: "#374151", fontWeight: 500 }}>{message || "Working..."}</span>
        <span style={{ fontSize: 12, color: "#6b7280", fontWeight: 600 }}>{pct}%</span>
      </div>
      <div style={{ background: "#e5e7eb", borderRadius: 6, height: 8, overflow: "hidden" }}>
        <div style={{
          height: "100%", borderRadius: 6, transition: "width 0.5s ease",
          width: `${pct}%`, background: `linear-gradient(90deg, ${color}, ${color}cc)`,
        }} />
      </div>
    </div>
  )
}

// ─── Step Icons ───────────────────────────────────────────────────────────────

function StepPipeline({ steps_done = [], running_step = null }) {
  const steps = [
    { key: "profile", label: "Profile", icon: "📋" },
    { key: "website", label: "Website", icon: "🌐" },
    { key: "competitors", label: "Competitors", icon: "⚔" },
    { key: "strategy", label: "Strategy", icon: "🗺" },
  ]
  return (
    <div style={{ display: "flex", gap: 0, alignItems: "center", marginBottom: 16 }}>
      {steps.map((s, i) => {
        const done = steps_done.includes(s.key)
        const running = running_step === s.key
        return (
          <React.Fragment key={s.key}>
            <div style={{
              display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
              padding: "8px 14px", borderRadius: 8, minWidth: 90,
              background: done ? "#f0fdf4" : running ? "#eff6ff" : "#f9fafb",
              border: `2px solid ${done ? "#86efac" : running ? "#93c5fd" : "#e5e7eb"}`,
              position: "relative",
            }}>
              <span style={{ fontSize: 18 }}>{done ? "✅" : running ? "⟳" : s.icon}</span>
              <span style={{ fontSize: 11, fontWeight: 600, color: done ? "#065f46" : running ? "#1d4ed8" : "#6b7280" }}>
                {s.label}
              </span>
              {running && <span style={{ fontSize: 9, color: "#3b82f6", animation: "pulse 1s infinite" }}>Running...</span>}
            </div>
            {i < steps.length - 1 && (
              <div style={{ width: 24, height: 2, background: done ? "#86efac" : "#e5e7eb", flexShrink: 0 }} />
            )}
          </React.Fragment>
        )
      })}
    </div>
  )
}

// ─── Step A: Profile Form ─────────────────────────────────────────────────────

function ProfileForm({ projectId, sessionId, profile, onSaved }) {
  const { addToast } = useKw2Store()
  const [open, setOpen] = useState(!profile?.goals?.length)
  const [form, setForm] = useState({
    goals: profile?.goals || [],
    pricing_model: profile?.pricing_model || "mid-range",
    usps: profile?.usps || [],
    audience_segments: profile?.audience_segments || [],
  })
  const [uspInput, setUspInput] = useState("")
  const [audInput, setAudInput] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (profile) setForm({
      goals: profile.goals || [],
      pricing_model: profile.pricing_model || "mid-range",
      usps: profile.usps || [],
      audience_segments: profile.audience_segments || [],
    })
  }, [profile])

  const save = async () => {
    setSaving(true)
    try {
      await api.saveBizProfile(projectId, sessionId, form)
      addToast("Profile saved", "success")
      onSaved(form)
      setOpen(false)
    } catch (e) { addToast("Save failed", "error") }
    setSaving(false)
  }

  const fs = { width: "100%", padding: "7px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13, boxSizing: "border-box" }

  return (
    <div style={{ marginBottom: 12, border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", background: profile?.goals?.length ? "#f0fdf4" : "#f9fafb", cursor: "pointer" }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 16 }}>{profile?.goals?.length ? "✅" : "📋"}</span>
          <span style={{ fontSize: 13, fontWeight: 700 }}>Step 1 — Business Profile</span>
          {profile?.goals?.length > 0 && <Tag color="green">{profile.goals.length} goals · {profile.pricing_model}</Tag>}
        </div>
        <span style={{ fontSize: 12, color: "#9ca3af" }}>{open ? "▲ Collapse" : "▼ Edit"}</span>
      </div>

      {open && (
        <div style={{ padding: "14px 14px 10px", background: "#fff" }}>
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>🎯 Business Goals</label>
            <div>{GOALS_OPTIONS.map(g => <CheckTag key={g} label={g} checked={form.goals.includes(g)} onChange={() => setForm(f => ({ ...f, goals: f.goals.includes(g) ? f.goals.filter(x => x !== g) : [...f.goals, g] }))} />)}</div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 10 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 4 }}>💰 Pricing</label>
              <select style={fs} value={form.pricing_model} onChange={e => setForm(f => ({ ...f, pricing_model: e.target.value }))}>
                {PRICING_OPTIONS.map(p => <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>)}
              </select>
            </div>

            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 4 }}>⭐ USPs</label>
              <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                <input style={{ flex: 1, padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 12 }} placeholder="organic certified, farm-direct" value={uspInput} onChange={e => setUspInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && uspInput.trim()) { setForm(f => ({ ...f, usps: [...f.usps, uspInput.trim()] })); setUspInput("") } }} />
                <button onClick={() => { if (uspInput.trim()) { setForm(f => ({ ...f, usps: [...f.usps, uspInput.trim()] })); setUspInput("") } }} style={{ padding: "6px 10px", background: "#10b981", color: "#fff", border: "none", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>+</button>
              </div>
              <div>{form.usps.map((u, i) => <Tag key={i} color="green" onRemove={() => setForm(f => ({ ...f, usps: f.usps.filter((_, j) => j !== i) }))}>{u}</Tag>)}</div>
            </div>
          </div>

          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 4 }}>👥 Target Audience Segments</label>
            <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
              <input style={{ flex: 1, padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 12 }} placeholder="restaurant owners, home cooks" value={audInput} onChange={e => setAudInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && audInput.trim()) { setForm(f => ({ ...f, audience_segments: [...f.audience_segments, audInput.trim()] })); setAudInput("") } }} />
              <button onClick={() => { if (audInput.trim()) { setForm(f => ({ ...f, audience_segments: [...f.audience_segments, audInput.trim()] })); setAudInput("") } }} style={{ padding: "6px 10px", background: "#8b5cf6", color: "#fff", border: "none", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>+</button>
            </div>
            <div>{form.audience_segments.map((a, i) => <Tag key={i} color="purple" onRemove={() => setForm(f => ({ ...f, audience_segments: f.audience_segments.filter((_, j) => j !== i) }))}>{a}</Tag>)}</div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <RunButton onClick={save} loading={saving}>Save Profile</RunButton>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Results Panels ───────────────────────────────────────────────────────────

function WebsiteResults({ pages = [], summary = null }) {
  if (!pages.length) return null
  const pageTypeMap = {}
  pages.forEach(p => { pageTypeMap[p.page_type] = (pageTypeMap[p.page_type] || 0) + 1 })
  return (
    <div style={{ marginBottom: 12, padding: 12, background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 8 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#065f46", marginBottom: 8 }}>
        🌐 Website Analysis — {pages.length} pages
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        {Object.entries(pageTypeMap).map(([pt, cnt]) => (
          <span key={pt} style={{ padding: "2px 8px", borderRadius: 10, background: (INTENT_COLORS[pt] || "#9ca3af") + "22", color: INTENT_COLORS[pt] || "#9ca3af", fontSize: 11, fontWeight: 600, border: `1px solid ${(INTENT_COLORS[pt] || "#9ca3af")}44` }}>
            {pt.replace("_", " ")} {cnt}
          </span>
        ))}
        {summary?.total_keywords > 0 && <Tag color="blue">{summary.total_keywords} keywords extracted</Tag>}
      </div>
      <div style={{ overflowX: "auto", maxHeight: 200, overflowY: "auto" }}>
        <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
          <thead style={{ position: "sticky", top: 0, background: "#ecfdf5" }}>
            <tr>
              <th style={{ textAlign: "left", padding: "4px 6px", fontWeight: 600 }}>Page</th>
              <th style={{ padding: "4px 6px", fontWeight: 600 }}>Type</th>
              <th style={{ padding: "4px 6px", fontWeight: 600 }}>Funnel</th>
              <th style={{ textAlign: "left", padding: "4px 6px", fontWeight: 600 }}>Topic</th>
            </tr>
          </thead>
          <tbody>
            {pages.map((p, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #d1fae5" }}>
                <td style={{ padding: "3px 6px", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  <a href={p.url} target="_blank" rel="noopener noreferrer" style={{ color: "#3b82f6" }}>{p.url}</a>
                </td>
                <td style={{ padding: "3px 6px", textAlign: "center" }}>
                  <span style={{ fontSize: 10, padding: "1px 5px", borderRadius: 8, background: (INTENT_COLORS[p.page_type] || "#9ca3af") + "22", color: INTENT_COLORS[p.page_type] || "#9ca3af", fontWeight: 600 }}>{p.page_type?.replace("_", " ") || "unknown"}</span>
                </td>
                <td style={{ padding: "3px 6px", textAlign: "center" }}>
                  <span style={{ fontSize: 10, padding: "1px 5px", borderRadius: 8, color: FUNNEL_COLORS[p.funnel_stage] || "#9ca3af" }}>{p.funnel_stage || "—"}</span>
                </td>
                <td style={{ padding: "3px 6px", color: "#374151" }}>{p.primary_topic || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CompetitorResults({ competitors = [] }) {
  if (!competitors.length) return null
  return (
    <div style={{ marginBottom: 12, padding: 12, background: "#faf5ff", border: "1px solid #e9d5ff", borderRadius: 8 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#5b21b6", marginBottom: 8 }}>
        ⚔ Competitor Analysis — {competitors.length} domain{competitors.length !== 1 ? "s" : ""}
      </div>
      {competitors.map((c, i) => (
        <div key={i} style={{ marginBottom: 8, padding: "8px 10px", background: c.crawl_done ? "#f3e8ff" : "#fdf4ff", borderRadius: 6, border: `1px solid ${c.crawl_done ? "#d8b4fe" : "#e9d5ff"}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: c.crawl_done ? 6 : 0 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{c.domain}</span>
            {c.crawl_done ? <Tag color="purple">✓ {c.pages_crawled}p analyzed</Tag> : <Tag color="gray">Pending</Tag>}
          </div>
          {c.crawl_done && (
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {(c.strengths || []).slice(0, 2).map((s, j) => <Tag key={j} color="green">✓ {s}</Tag>)}
              {(c.weaknesses || []).slice(0, 2).map((w, j) => <Tag key={j} color="amber">⚠ {w}</Tag>)}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function StrategyResults({ knowledge, strategy }) {
  const [tab, setTab] = useState("strategy")
  if (!strategy && !knowledge) return null

  const TABS = [
    { key: "strategy", label: "📅 Action Plan" },
    { key: "keywords", label: "🎯 Priority Keywords" },
    { key: "knowledge", label: "🧠 Intelligence" },
  ]

  const renderList = items => Array.isArray(items) ? items.map((x, i) => <div key={i} style={{ marginBottom: 2 }}>• {typeof x === "object" ? (x.action || x.name || JSON.stringify(x)) : x}</div>) : null

  return (
    <div style={{ marginBottom: 12, padding: 12, background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#92400e", marginBottom: 10 }}>🗺 AI Strategy & Intelligence</div>

      <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            padding: "4px 10px", borderRadius: 6, fontSize: 12, cursor: "pointer",
            border: tab === t.key ? "2px solid #f59e0b" : "1px solid #e5e7eb",
            background: tab === t.key ? "#fef3c7" : "#fff",
            fontWeight: tab === t.key ? 700 : 400, color: tab === t.key ? "#92400e" : "#6b7280",
          }}>{t.label}</button>
        ))}
      </div>

      {tab === "strategy" && strategy && (
        <div>
          {strategy.executive_summary && (
            <div style={{ padding: "8px 12px", background: "#fffde7", borderRadius: 6, marginBottom: 10, fontSize: 12, color: "#374151" }}>
              <strong>Summary:</strong> {strategy.executive_summary}
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            {["30_day_actions", "60_day_actions", "90_day_actions"].map((k, i) => strategy[k]?.length > 0 && (
              <div key={k} style={{ padding: 10, background: "#fff", borderRadius: 6, border: "1px solid #fde68a" }}>
                <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>{["📅 30 Days", "📅 60 Days", "📅 90 Days"][i]}</div>
                <div style={{ fontSize: 11, color: "#374151" }}>{renderList(strategy[k])}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "keywords" && (
        strategy?.priority_keywords?.length > 0 ? (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#fef3c7", borderBottom: "2px solid #fde68a" }}>
                <th style={{ textAlign: "left", padding: "5px 8px" }}>Keyword</th>
                <th style={{ padding: "5px 8px" }}>Intent</th>
                <th style={{ padding: "5px 8px" }}>Funnel</th>
                <th style={{ padding: "5px 8px" }}>Priority</th>
                <th style={{ textAlign: "left", padding: "5px 8px" }}>Why</th>
              </tr>
            </thead>
            <tbody>
              {strategy.priority_keywords.map((kw, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #fef3c7" }}>
                  <td style={{ padding: "4px 8px", fontWeight: 600 }}>{kw.keyword}</td>
                  <td style={{ padding: "4px 8px", textAlign: "center" }}><Badge color={kw.intent === "transactional" ? "green" : "yellow"}>{kw.intent}</Badge></td>
                  <td style={{ padding: "4px 8px", textAlign: "center" }}><Badge color="blue">{kw.page_type || kw.funnel}</Badge></td>
                  <td style={{ padding: "4px 8px", textAlign: "center" }}><Badge color={kw.priority === "high" ? "red" : "gray"}>{kw.priority}</Badge></td>
                  <td style={{ padding: "4px 8px", color: "#6b7280", fontSize: 11 }}>{kw.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        ) : (
          <div style={{ padding: "20px", textAlign: "center", color: "#9ca3af", fontSize: 12 }}>
            No priority keywords yet — run BI Analysis to generate AI-driven keyword recommendations.
          </div>
        )
      )}

      {tab === "knowledge" && knowledge && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {knowledge.business_identity && (
            <div style={{ padding: 10, background: "#fff", borderRadius: 6, border: "1px solid #e5e7eb" }}>
              <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>🏢 Business Identity</div>
              <div style={{ fontSize: 11, color: "#374151" }}>{knowledge.business_identity.positioning || ""}</div>
            </div>
          )}
          {knowledge.quick_wins?.length > 0 && (
            <div style={{ padding: 10, background: "#fff", borderRadius: 6, border: "1px solid #e5e7eb" }}>
              <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>⚡ Quick Wins</div>
              <div style={{ fontSize: 11, color: "#374151" }}>{renderList(knowledge.quick_wins)}</div>
            </div>
          )}
          {knowledge.competitive_landscape && (
            <div style={{ padding: 10, background: "#fff", borderRadius: 6, border: "1px solid #e5e7eb" }}>
              <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>⚔ Competitive Gaps</div>
              <div style={{ fontSize: 11, color: "#374151" }}>{renderList(knowledge.competitive_landscape.gaps || [])}</div>
            </div>
          )}
          {knowledge.content_opportunity_engine?.blog_angles?.length > 0 && (
            <div style={{ padding: 10, background: "#fff", borderRadius: 6, border: "1px solid #e5e7eb" }}>
              <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>✍ Blog Angles</div>
              <div style={{ fontSize: 11, color: "#374151" }}>{renderList(knowledge.content_opportunity_engine.blog_angles)}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Main PhaseBI Component ───────────────────────────────────────────────────

export default function PhaseBI({ projectId, sessionId, onComplete, onProceedPhase = "BI" }) {
  const { setActivePhase, goNextPhase, addToast } = useKw2Store()
  const { log } = usePhaseRunner("BI")
  const [intel, setIntel] = useState(null)
  const [loadingIntel, setLoadingIntel] = useState(true)
  const [proceeding, setProceeding] = useState(false)

  // Progress poll state
  const [progress, setProgress] = useState({ running: false, pct: 0, step: "idle", message: "", steps_done: [] })
  const pollRef = useRef(null)
  const runStartRef = useRef(null)       // tracks when polling started for timeout detection
  const [analysisError, setAnalysisError] = useState(null)
  const lastConsoleLogTime = useRef(0)   // throttle: log to console max once per 15s
  const lastConsolePct = useRef(-1)      // avoid duplicate messages at same pct

  // Load BI data from backend
  const loadIntel = useCallback(async () => {
    try {
      const data = await api.getBizIntel(projectId, sessionId)
      setIntel(data)
    } catch (e) { /* new session — no data yet */ }
    setLoadingIntel(false)
  }, [projectId, sessionId])

  useEffect(() => { loadIntel() }, [loadIntel])

  // Write a progress snapshot to the Session Console (max every 15s)
  const maybeLogProgress = useCallback((prog) => {
    const now = Date.now()
    const pct = prog.pct || 0
    if (now - lastConsoleLogTime.current < 15000 && pct === lastConsolePct.current) return
    // Only log if there's meaningful progress
    if (pct === 0 && prog.step === "idle") return
    lastConsoleLogTime.current = now
    lastConsolePct.current = pct

    const STEP_ICONS = { website: "🌐", competitors: "⚔", strategy: "🗺", done: "✅", error: "❌" }
    const icon = STEP_ICONS[prog.step] || "⟳"
    log(`${icon} ${pct}% — ${prog.message || prog.step}`, prog.step === "done" ? "success" : prog.step === "error" ? "error" : "info")
  }, [log])

  // Poll progress while running
  const startPolling = useCallback(() => {
    if (pollRef.current) return
    runStartRef.current = Date.now()
    pollRef.current = setInterval(async () => {
      // 6-minute timeout: BI analysis (crawl + competitors + AI strategy) normally takes 3-5 min
      if (Date.now() - runStartRef.current > 360000) {
        clearInterval(pollRef.current)
        pollRef.current = null
        setProgress(prev => ({ ...prev, running: false }))
        setAnalysisError("BI analysis timed out (>2 min). The job may still be running in the background — click Refresh or try re-running.")
        addToast("BI analysis timed out — try re-running", "error")
        return
      }
      try {
        const prog = await apiCall(`/api/kw2/${projectId}/sessions/${sessionId}/biz-intel/progress`)
        setProgress(prog)
        maybeLogProgress(prog)
        if (!prog.running) {
          clearInterval(pollRef.current)
          pollRef.current = null
          if (prog.step === "done") {
            const phases = prog.steps_done?.length || 0
            const label = phases === 3 ? "All 3 phases complete" : phases > 0 ? `${phases}/3 phases complete` : "complete"
            log(`✅ 100% — BI analysis ${label}`, "success")
            await loadIntel()
            addToast("BI analysis complete!", "success")
          } else if (prog.step === "error") {
            setAnalysisError(prog.message || "Analysis failed")
            log(`❌ BI failed: ${prog.message || "unknown error"}`, "error")
            addToast("BI analysis failed: " + (prog.message || ""), "error")
          }
        }
      } catch (e) {
        clearInterval(pollRef.current)
        pollRef.current = null
        log(`⚠ Progress polling error: ${e.message}`, "warn")
      }
    }, 2000)
  }, [projectId, sessionId, loadIntel, addToast, maybeLogProgress, log])

  useEffect(() => {
    // Check if a job is already running when we mount
    apiCall(`/api/kw2/${projectId}/sessions/${sessionId}/biz-intel/progress`)
      .then(prog => {
        setProgress(prog)
        if (prog.running) {
          log(`⟳ Resuming BI analysis in progress (${prog.pct || 0}%)...`, "info")
          startPolling()
        }
      })
      .catch(() => {})
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [projectId, sessionId, startPolling, log])

  // Start full BI analysis
  const runAnalysis = async () => {
    setAnalysisError(null)
    lastConsoleLogTime.current = 0
    lastConsolePct.current = -1
    try {
      const res = await apiCall(`/api/kw2/${projectId}/sessions/${sessionId}/biz-intel/run-all`, "POST")
      if (res.status === "already_running") {
        log(`⚠ BI analysis already running (${res.progress?.pct || 0}%)`, "warn")
        addToast("Analysis already running", "info")
        setProgress(prev => ({ ...prev, running: true }))
        startPolling()
        return
      }
      log(`▶ BI Analysis started — Website crawl → Competitor analysis → AI Strategy`, "info")
      setProgress(prev => ({ ...prev, running: true, pct: 0, message: "Starting...", steps_done: [] }))
      startPolling()
    } catch (e) {
      log(`❌ Failed to start BI analysis: ${e.message}`, "error")
      addToast("Failed to start analysis: " + e.message, "error")
    }
  }

  // Proceed to next phase
  const handleProceed = useCallback(async () => {
    setProceeding(true)
    // Fire-and-forget — don't block navigation on AI readme generation
    api.generateBusinessReadme(projectId, sessionId, false).catch(() => {})
    if (onComplete) onComplete()
    const next = goNextPhase(onProceedPhase)
    if (next == null) setActivePhase(onProceedPhase === "UNDERSTAND" ? "EXPAND" : "SEARCH")
    setProceeding(false)
  }, [projectId, sessionId, onComplete, goNextPhase, setActivePhase, onProceedPhase])

  // Elapsed time display while running (must be before any early return)
  const [elapsed, setElapsed] = useState(0)
  const elapsedRef = useRef(null)
  useEffect(() => {
    if (progress.running) {
      setElapsed(0)
      elapsedRef.current = setInterval(() => setElapsed(s => s + 1), 1000)
    } else {
      clearInterval(elapsedRef.current)
    }
    return () => clearInterval(elapsedRef.current)
  }, [progress.running])

  if (loadingIntel) return (
    <div style={{ textAlign: "center", padding: 40 }}>
      <Spinner />
      <div style={{ fontSize: 13, marginTop: 10, color: "#6b7280" }}>Loading business intelligence...</div>
    </div>
  )

  const profile = intel?.profile || {}
  const status = intel?.status || {}
  const stepsDone = []
  if (profile.goals?.length || profile.usps?.length) stepsDone.push("profile")
  if (status.website_crawl_done) stepsDone.push("website")
  if (status.competitor_crawl_done) stepsDone.push("competitors")
  if (status.strategy_done) stepsDone.push("strategy")

  const allDone = status.strategy_done || progress.step === "done"
  const effectiveStepsDone = progress.running ? progress.steps_done : stepsDone
  const elapsedStr = elapsed >= 60 ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s` : `${elapsed}s`

  return (
    <div>
      {/* ── Header Card ────────────────────────────────────────────────── */}
      <Card
        title="Business Intelligence — Deep Analysis"
        actions={
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => setActivePhase(1)}
              style={{ padding: "5px 12px", borderRadius: 6, border: "1px solid #d1d5db", background: "#f9fafb", fontSize: 12, cursor: "pointer" }}
            >
              ← Phase 1
            </button>
            <RunButton onClick={handleProceed} loading={proceeding}>
              Proceed to Search →
            </RunButton>
          </div>
        }
      >
        <p style={{ fontSize: 13, color: "#6b7280", margin: "0 0 14px" }}>
          Build comprehensive business intelligence before keyword generation. Each step enriches your keywords.
          <strong> All steps are optional</strong> — more data = better keywords.
        </p>

        {/* Pipeline status */}
        <StepPipeline
          steps_done={effectiveStepsDone}
          running_step={progress.running ? progress.step : null}
        />

        {/* Progress bar — shown when running */}
        {progress.running && (
          <div>
            <ProgressBar pct={progress.pct} message={progress.message} color="#3b82f6" />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#9ca3af", marginTop: -6, marginBottom: 8 }}>
              <span>⏱ Elapsed: <strong style={{ color: "#6b7280" }}>{elapsedStr}</strong></span>
              <span>Next progress log in ~{15 - Math.floor((Date.now() - lastConsoleLogTime.current) / 1000)}s (check Session Console)</span>
            </div>
          </div>
        )}

        {/* Done state */}
        {progress.step === "done" && !progress.running && (
          <div style={{ padding: "8px 12px", background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 6, marginBottom: 8, fontSize: 12, color: "#065f46", fontWeight: 600 }}>
            ✅ BI analysis complete — all data has been saved and will enrich your keywords.
          </div>
        )}

        {/* Error state */}
        {analysisError && (
          <div style={{ padding: "8px 12px", background: "#fee2e2", border: "1px solid #fca5a5", borderRadius: 6, marginBottom: 8, fontSize: 12, color: "#991b1b" }}>
            ❌ {analysisError}
          </div>
        )}

        {/* Run button */}
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button
            onClick={runAnalysis}
            disabled={progress.running}
            style={{
              padding: "9px 20px", borderRadius: 7, border: "none",
              background: progress.running ? "#93c5fd" : "#2563eb",
              color: "#fff", fontSize: 13, fontWeight: 700,
              cursor: progress.running ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", gap: 8,
            }}
          >
            {progress.running ? (
              <><span style={{ fontSize: 14, animation: "spin 1s linear infinite" }}>⟳</span> Running Analysis...</>
            ) : allDone ? (
              "🔄 Re-run BI Analysis"
            ) : (
              "▶ Run BI Analysis"
            )}
          </button>
          {!progress.running && !allDone && (
            <span style={{ fontSize: 12, color: "#9ca3af" }}>Runs website crawl → competitor analysis → AI strategy (~2-4 min)</span>
          )}
        </div>
      </Card>

      {/* ── Step A: Profile Form ─────────────────────────────────────── */}
      <ProfileForm
        projectId={projectId}
        sessionId={sessionId}
        profile={profile}
        onSaved={form => setIntel(prev => ({ ...prev, profile: { ...profile, ...form } }))}
      />

      {/* ── Results (shown when data exists) ─────────────────────────── */}
      <WebsiteResults pages={intel?.pages || []} summary={intel?.website_summary} />
      <CompetitorResults competitors={intel?.competitors || []} />
      <StrategyResults knowledge={intel?.knowledge} strategy={intel?.strategy} />

      {/* ── Bottom stats ─────────────────────────────────────────────── */}
      {intel && (
        <StatsRow items={[
          { label: "Pages Analyzed", value: intel.pages?.length || 0, color: "#3b82f6" },
          { label: "Competitors", value: intel.competitors?.length || 0, color: "#8b5cf6" },
          { label: "Comp Keywords", value: intel.competitor_keywords_count || 0, color: "#f59e0b" },
          { label: "Strategy", value: status.strategy_done ? "Done ✓" : "Pending", color: status.strategy_done ? "#10b981" : "#9ca3af" },
        ]} />
      )}

      {/* ── Proceed footer when analysis is done ─────────────────────── */}
      {allDone && (
        <div style={{ marginTop: 10, textAlign: "center" }}>
          <RunButton onClick={handleProceed} loading={proceeding}>
            Proceed to Keyword Search →
          </RunButton>
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 6 }}>All BI data has been saved and will shape your keyword generation.</div>
        </div>
      )}
    </div>
  )
}

