// Step 1 — Smart List
// Collects: pillars, supporting keywords, customer URL, competitor URLs, business intent
// On save: POSTs to /api/ki/{pid}/input → creates session → populates WorkflowContext.step1

import { useState, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNotification } from "../store/notification"
import useWorkflowContext from "../store/workflowContext"
import { apiCall, T, Card, Btn, Spinner, INTENT_OPTIONS, SEASONAL_PRESETS } from "./shared"

export default function Step1SmartList({ projectId, onComplete }) {
  const notify = useNotification(s => s.notify)
  const ctx = useWorkflowContext()

  // Form state
  const [pillars, setPillars]               = useState([])
  const [pillarInput, setPillarInput]       = useState("")
  const [globalSupports, setGlobalSupports] = useState([])
  const [supportInput, setSupportInput]     = useState("")
  const [intentFocus, setIntentFocus]       = useState("transactional")
  const [customerUrl, setCustomerUrl]       = useState("")
  const [competitorUrls, setCompetitorUrls] = useState([])
  const [competitorInput, setCompetitorInput] = useState("")
  const [businessIntent, setBusinessIntent] = useState(["ecommerce"])

  const [loading, setLoading]       = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage]       = useState("")
  const [error, setError]           = useState("")

  const inStyle = {
    width: "100%", padding: "7px 10px", borderRadius: 8,
    border: `1px solid ${T.border}`, fontSize: 13, boxSizing: "border-box",
  }

  // Load existing session data
  const { data: existingPillars } = useQuery({
    queryKey: ["ki-pillars", projectId],
    queryFn: () => apiCall(`/api/ki/${projectId}/pillars`),
    enabled: !!projectId,
    retry: false,
  })

  const { data: latestSession } = useQuery({
    queryKey: ["ki-latest-session", projectId],
    queryFn: () => apiCall(`/api/ki/${projectId}/latest-session`),
    enabled: !!projectId,
    retry: false,
  })

  const { data: projectData } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => apiCall(`/api/projects/${projectId}`),
    enabled: !!projectId,
    retry: false,
  })

  // Restore from WorkflowContext (page refresh recovery)
  useEffect(() => {
    if (ctx.step1) {
      const s1 = ctx.step1
      if (Array.isArray(s1.pillars) && s1.pillars.length > 0) {
        setPillars(s1.pillars.map(k => ({ keyword: k, intent: intentFocus, supports: [...globalSupports] })))
      }
      if (Array.isArray(s1.supports)) setGlobalSupports(s1.supports)
      if (s1.customerUrl) setCustomerUrl(s1.customerUrl)
      if (Array.isArray(s1.competitorUrls)) setCompetitorUrls(s1.competitorUrls)
      if (Array.isArray(s1.intent)) setBusinessIntent(s1.intent)
    }
  }, []) // Only run once on mount

  // Populate from latest session if no ctx
  useEffect(() => {
    if (!latestSession || ctx.step1) return
    if (latestSession.pillar_support_map) {
      const mapped = Object.entries(latestSession.pillar_support_map).map(([k, v]) => ({
        keyword: k, intent: latestSession.intent_focus || "transactional",
        supports: Array.isArray(v) ? v : [],
      }))
      setPillars(mapped)
    }
    if (latestSession.customer_url) setCustomerUrl(latestSession.customer_url)
    // competitor_urls stored as JSON string in DB — parse it
    const rawComp = latestSession.competitor_urls
    const parsedComp = typeof rawComp === "string"
      ? (() => { try { return JSON.parse(rawComp) } catch { return [] } })()
      : (Array.isArray(rawComp) ? rawComp : [])
    if (Array.isArray(parsedComp) && parsedComp.length > 0) setCompetitorUrls(parsedComp)
    if (latestSession.business_intent) {
      const bi = latestSession.business_intent
      setBusinessIntent(Array.isArray(bi) ? bi : [bi])
    }
  }, [latestSession])

  // Pre-fill from project if not in session
  useEffect(() => {
    if (!projectData) return
    if (!customerUrl && projectData.customer_url) setCustomerUrl(projectData.customer_url)
    if (competitorUrls.length === 0 && Array.isArray(projectData.competitor_urls) && projectData.competitor_urls.length > 0) {
      setCompetitorUrls(projectData.competitor_urls)
    }
  }, [projectData])

  const pillarBank = existingPillars?.pillars?.slice(0, 12) || []

  // ── Pillar actions ──────────────────────────────────────────────────────────
  const addPillar = () => {
    const kw = pillarInput.trim()
    if (!kw) return
    if (pillars.some(p => p.keyword.toLowerCase() === kw.toLowerCase())) {
      setMessage(`'${kw}' already added`)
      return
    }
    setPillars(prev => [...prev, { keyword: kw, intent: intentFocus, supports: [...globalSupports] }])
    setPillarInput("")
    setMessage("")
  }

  const removePillar = (kw) => setPillars(prev => prev.filter(p => p.keyword !== kw))

  const updatePillarIntent = (kw, intent) =>
    setPillars(prev => prev.map(p => p.keyword === kw ? { ...p, intent } : p))

  // ── Support actions ─────────────────────────────────────────────────────────
  const addSupport = () => {
    const kw = supportInput.trim()
    if (!kw) return
    if (globalSupports.some(s => s.toLowerCase() === kw.toLowerCase())) return
    setGlobalSupports(prev => [...prev, kw])
    setPillars(prev => prev.map(p => ({
      ...p, supports: Array.from(new Set([...(p.supports || []), kw])),
    })))
    setSupportInput("")
  }

  const removeSupport = (kw) => {
    setGlobalSupports(prev => prev.filter(s => s !== kw))
    setPillars(prev => prev.map(p => ({ ...p, supports: (p.supports || []).filter(s => s !== kw) })))
  }

  // ── Competitor actions ──────────────────────────────────────────────────────
  const addCompetitor = () => {
    const v = competitorInput.trim()
    if (v && !competitorUrls.includes(v)) {
      setCompetitorUrls(prev => [...prev, v])
      setCompetitorInput("")
    }
  }

  // ── Save & advance ──────────────────────────────────────────────────────────
  const handleSave = async (advance = false) => {
    if (submitting) return
    if (!pillars.length && !pillarInput.trim()) { setError("Add at least one pillar to continue"); return }

    // Auto-commit any pending text field values before saving
    let finalPillars = [...pillars]
    if (pillarInput.trim()) {
      const kw = pillarInput.trim()
      if (!finalPillars.find(p => p.keyword.toLowerCase() === kw.toLowerCase())) {
        finalPillars = [...finalPillars, { keyword: kw, intent: intentFocus, supports: [...globalSupports] }]
        setPillars(finalPillars)
      }
      setPillarInput("")
    }
    if (!finalPillars.length) { setError("Add at least one pillar to continue"); return }

    let finalSupports = [...globalSupports]
    if (supportInput.trim()) {
      const kw = supportInput.trim()
      if (!finalSupports.some(s => s.toLowerCase() === kw.toLowerCase())) {
        finalSupports = [...finalSupports, kw]
        setGlobalSupports(finalSupports)
      }
      setSupportInput("")
    }

    let finalCompetitorUrls = [...competitorUrls]
    if (competitorInput.trim()) {
      const v = competitorInput.trim()
      if (!finalCompetitorUrls.includes(v)) {
        finalCompetitorUrls = [...finalCompetitorUrls, v]
        setCompetitorUrls(finalCompetitorUrls)
      }
      setCompetitorInput("")
    }

    setSubmitting(true)
    setLoading(true)
    setError("")

    try {
      const pillarSupportMap = finalPillars.reduce((acc, p) => { acc[p.keyword] = p.supports || []; return acc }, {})
      const result = await apiCall(`/api/ki/${projectId}/input`, "POST", {
        pillars: finalPillars.map((p, i) => ({ keyword: p.keyword, intent: p.intent, priority: i + 1 })),
        supporting: finalSupports,
        pillar_support_map: pillarSupportMap,
        intent_focus: intentFocus,
        customer_url: customerUrl,
        competitor_urls: finalCompetitorUrls,
        business_intent: businessIntent,
      })

      if (result?.session_id) {
        const sid = result.session_id
        ctx.setSession(sid)
        ctx.setStep(1, {
          pillars: finalPillars.map(p => p.keyword),
          supports: finalSupports,
          customerUrl,
          competitorUrls: finalCompetitorUrls,
          intent: businessIntent,
        })
        await ctx.flush(projectId)
        notify("Smart list saved", "success")

        if (advance && onComplete) {
          onComplete({ sessionId: sid })
        }
      } else {
        setError("Save failed — no session returned")
      }
    } catch (e) {
      setError(String(e.message || e))
      notify(String(e.message || e), "error")
    } finally {
      setLoading(false)
      setSubmitting(false)
    }
  }

  if (!projectId) return <div style={{ color: T.gray, fontSize: 13 }}>Select a project first.</div>

  return (
    <div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <Card style={{ marginBottom: 16, padding: 18 }}>
        <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>Step 1 — Smart List</div>
            <div style={{ fontSize: 12, color: T.textSoft }}>
              Add your main pillars and supporting keywords. Global supports auto-apply to all pillars.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            <Btn onClick={() => handleSave(false)} disabled={loading || submitting}>
              {loading ? "Saving…" : "Save Draft"}
            </Btn>
            <Btn variant="teal" onClick={() => handleSave(true)} disabled={loading || submitting}>
              {submitting ? "Processing…" : "Discovery →"}
            </Btn>
          </div>
        </div>

        {/* Global Supporting Keywords */}
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 8 }}>Global Supporting Keywords</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
            {globalSupports.map(s => (
              <span key={s} style={{
                background: T.grayLight, borderRadius: 999, padding: "5px 8px",
                display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12,
              }}>
                {s}
                <button style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 11 }}
                  onClick={() => removeSupport(s)}>✕</button>
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={supportInput} onChange={e => setSupportInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && addSupport()}
              placeholder="Add support (e.g., organic, powder)"
              style={{ ...inStyle, flex: 1 }} />
            <Btn small onClick={addSupport}>+ Add</Btn>
          </div>
        </div>

        {/* Add Pillar Row */}
        <div style={{ marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
          <input value={pillarInput} onChange={e => setPillarInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && addPillar()}
            placeholder="Add pillar (e.g., cinnamon)"
            style={{ ...inStyle, width: 220 }} />
          <select value={intentFocus} onChange={e => setIntentFocus(e.target.value)}
            style={{ ...inStyle, width: 160 }}>
            {INTENT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <Btn onClick={addPillar}>+ Add Pillar</Btn>
        </div>

        {/* Pillars Table */}
        <div style={{ overflowX: "auto", marginBottom: 14 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: `1px solid ${T.border}` }}>
                <th style={{ padding: "8px", fontSize: 12 }}>Pillar</th>
                <th style={{ padding: "8px", fontSize: 12 }}>Intent</th>
                <th style={{ padding: "8px", fontSize: 12 }}>Supports</th>
                <th style={{ padding: "8px", fontSize: 12 }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {pillars.length === 0 && (
                <tr><td colSpan={4} style={{ padding: "12px 8px", color: T.gray, fontSize: 12 }}>
                  No pillars yet — add your main product/topic keywords above.
                </td></tr>
              )}
              {pillars.map((p, i) => (
                <tr key={p.keyword + i} style={{ borderBottom: `1px solid ${T.grayLight}` }}>
                  <td style={{ padding: "8px", fontWeight: 500, fontSize: 13 }}>{p.keyword}</td>
                  <td style={{ padding: "8px" }}>
                    <select value={p.intent || intentFocus}
                      onChange={e => updatePillarIntent(p.keyword, e.target.value)}
                      style={{ ...inStyle, width: "100%" }}>
                      {INTENT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </td>
                  <td style={{ padding: "8px" }}>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {(p.supports || []).map(s => (
                        <span key={s} style={{
                          background: T.grayLight, borderRadius: 6, padding: "2px 6px",
                          fontSize: 11, display: "inline-flex", alignItems: "center", gap: 4,
                        }}>
                          {s}
                          <button style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 10 }}
                            onClick={() => setPillars(prev => prev.map(pp =>
                              pp.keyword === p.keyword
                                ? { ...pp, supports: (pp.supports || []).filter(x => x !== s) }
                                : pp
                            ))}>✕</button>
                        </span>
                      ))}
                    </div>
                  </td>
                  <td style={{ padding: "8px" }}>
                    <Btn small variant="danger" onClick={() => removePillar(p.keyword)}>Remove</Btn>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Recent pillars bank */}
        {pillarBank.length > 0 && (
          <div style={{ background: T.grayLight, borderRadius: 10, padding: 10, marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 6 }}>Reuse Recent Pillars</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {pillarBank.map(b => (
                <button key={b.keyword} onClick={() => {
                  setPillarInput(b.keyword)
                  setIntentFocus(b.intent || "transactional")
                }}
                  style={{
                    border: `1px solid ${T.border}`, borderRadius: 8, padding: "4px 8px",
                    cursor: "pointer", fontSize: 12, background: "#fff",
                  }}>
                  + {b.keyword}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Website & Competitors */}
        <div style={{ background: T.grayLight, borderRadius: 12, padding: 12, marginBottom: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Your Website & Competitors</div>
          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 11, color: T.textSoft, display: "block", marginBottom: 4 }}>Your Website URL</label>
            <input value={customerUrl} onChange={e => setCustomerUrl(e.target.value)}
              placeholder="https://yoursite.com"
              style={{ ...inStyle }} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: T.textSoft, display: "block", marginBottom: 4 }}>Competitor URLs</label>
            <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
              <input value={competitorInput} onChange={e => setCompetitorInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && addCompetitor()}
                placeholder="https://competitor.com"
                style={{ flex: 1, padding: "6px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 13 }} />
              <Btn small variant="teal" onClick={addCompetitor}>Add</Btn>
            </div>
            {competitorUrls.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {competitorUrls.map(url => (
                  <span key={url} style={{
                    background: "#fff", border: `1px solid ${T.border}`, borderRadius: 8,
                    padding: "2px 8px", fontSize: 12, display: "flex", alignItems: "center", gap: 4,
                  }}>
                    {url}
                    <button onClick={() => setCompetitorUrls(prev => prev.filter(u => u !== url))}
                      style={{ border: "none", background: "transparent", cursor: "pointer", color: T.red, fontSize: 13 }}>✕</button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Business Intent */}
        <div style={{ background: T.purpleLight, borderRadius: 12, padding: 12, marginBottom: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Business Intent</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {[
              { value: "ecommerce",    label: "E-commerce (selling products)" },
              { value: "content_blog", label: "Content Blog (informational)" },
              { value: "supplier",     label: "B2B / Supplier" },
              { value: "mixed",        label: "Mixed / General" },
            ].map(intent => (
              <label key={intent.value} style={{ display: "flex", alignItems: "center", cursor: "pointer", fontSize: 12, gap: 6 }}>
                <input type="checkbox" checked={businessIntent.includes(intent.value)}
                  onChange={e => {
                    if (e.target.checked) {
                      setBusinessIntent(prev => Array.from(new Set([...prev.filter(b => b !== "mixed"), intent.value])))
                    } else {
                      const updated = businessIntent.filter(b => b !== intent.value)
                      setBusinessIntent(updated.length === 0 ? ["mixed"] : updated)
                    }
                  }}
                  style={{ width: 15, height: 15, cursor: "pointer" }} />
                {intent.label}
              </label>
            ))}
          </div>
          {projectData && (
            <div style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid rgba(0,0,0,0.08)`, fontSize: 11 }}>
              <div style={{ color: T.textSoft, marginBottom: 4 }}>From project profile:</div>
              {projectData.business_type && <div>• Business type: <strong>{projectData.business_type}</strong></div>}
              {projectData.target_locations && (
                <div>• Locations: <strong>{Array.isArray(projectData.target_locations)
                  ? projectData.target_locations.join(", ") : projectData.target_locations}</strong></div>
              )}
            </div>
          )}
        </div>

        {message && <div style={{ marginTop: 8, color: T.teal, fontSize: 12 }}>{message}</div>}
        {error && <div style={{ marginTop: 8, color: T.red, fontSize: 12 }}>{error}</div>}
      </Card>
    </div>
  )
}
