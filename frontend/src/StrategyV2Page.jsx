/**
 * Strategy V2 Page — Intent → Angle → Blueprint wizard.
 * Generates high-quality content blueprints using the strategy_v2 engine.
 */
import React, { useState, useEffect, useRef, useCallback } from "react"
import BlueprintCard from "./components/BlueprintCard"

const API = import.meta.env.VITE_API_URL || ""

// ── helpers ─────────────────────────────────────────────────────────────────

function token() {
  return localStorage.getItem("annaseo_token") || ""
}

// ── sub-components ───────────────────────────────────────────────────────────

function Toast({ toast, onDismiss }) {
  if (!toast) return null
  const bg = toast.type === "success" ? "#16a34a" : toast.type === "error" ? "#dc2626" : "#2563eb"
  return (
    <div
      onClick={onDismiss}
      style={{
        position: "fixed", bottom: 24, right: 24, zIndex: 9999,
        background: bg, color: "#fff", padding: "10px 16px",
        borderRadius: 8, fontSize: 13, cursor: "pointer",
        boxShadow: "0 4px 12px rgba(0,0,0,0.25)", maxWidth: 360,
      }}
    >
      {toast.message}
    </div>
  )
}

function ProgressItem({ item }) {
  const color = item.status === "done" ? "#16a34a" : item.status === "error" ? "#dc2626" : item.status === "running" ? "#2563eb" : "#9ca3af"
  const icon = item.status === "done" ? "✓" : item.status === "error" ? "✗" : item.status === "running" ? "⟳" : "·"
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", fontSize: 13 }}>
      <span style={{ color, fontWeight: 700, width: 16, display: "inline-block" }}>{icon}</span>
      <span style={{ color: item.status === "running" ? "#1e40af" : "#374151" }}>{item.label}</span>
      {item.note && <span style={{ color: "#9ca3af", fontSize: 11 }}>— {item.note}</span>}
    </div>
  )
}

function FilterChip({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "4px 12px", borderRadius: 999, fontSize: 12, cursor: "pointer",
        border: "1px solid " + (active ? "#3b82f6" : "#d1d5db"),
        background: active ? "#3b82f6" : "#fff",
        color: active ? "#fff" : "#374151",
        transition: "all .15s",
      }}
    >
      {label}
    </button>
  )
}

// ── main component ────────────────────────────────────────────────────────────

export default function StrategyV2Page({ projectId, setPage }) {
  // step: "input" | "generating" | "results"
  const [step, setStep] = useState("input")

  // step 1 — input
  const [keywordsText, setKeywordsText] = useState("")
  const [sessions, setSessions] = useState([])
  const [selectedSession, setSelectedSession] = useState("")
  const [useKw2Context, setUseKw2Context] = useState(true)
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [fetchingKeywords, setFetchingKeywords] = useState(false)

  // goals & context
  const [businessGoals, setBusinessGoals] = useState({
    targetAudience: "",
    businessOutcome: "traffic",
    timeframe: "12_months"
  })

  // step 2 — generation
  const [progressItems, setProgressItems] = useState([])
  const [genError, setGenError] = useState(null)
  const [liveCards, setLiveCards] = useState([])
  const abortRef = useRef(null)

  // step 3 — results
  const [blueprints, setBlueprints] = useState([])
  const [angleFilter, setAngleFilter] = useState("all")
  const [minScore, setMinScore] = useState(0)

  // global
  const [toast, setToast] = useState(null)

  // toast helper
  const showToast = useCallback((message, type = "info") => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }, [])

  // load KW2 sessions
  useEffect(() => {
    if (!projectId) return
    setSessionsLoading(true)
    fetch(`${API}/api/kw2/${projectId}/sessions/list`, {
      headers: { Authorization: `Bearer ${token()}` },
    })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => {
        const list = data.sessions || data || []
        setSessions(list)
        if (list.length > 0) setSelectedSession(list[0].session_id || list[0].id || "")
      })
      .catch(() => {})
      .finally(() => setSessionsLoading(false))
  }, [projectId])

  // load existing blueprints on mount
  useEffect(() => {
    if (!projectId) return
    fetch(`${API}/api/strategy-v2/${projectId}/blueprints?limit=50`, {
      headers: { Authorization: `Bearer ${token()}` },
    })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => {
        const list = data.blueprints || []
        if (list.length > 0) {
          setBlueprints(list)
          setStep("results")
        }
      })
      .catch(() => {})
  }, [projectId])

  // ── generation ──────────────────────────────────────────────────────────────

  function addProgress(id, label, status = "pending", note = "") {
    setProgressItems(prev => {
      const idx = prev.findIndex(x => x.id === id)
      if (idx >= 0) {
        const updated = [...prev]
        updated[idx] = { ...updated[idx], label, status, note }
        return updated
      }
      return [...prev, { id, label, status, note }]
    })
  }

  function updateProgress(id, status, note = "") {
    setProgressItems(prev => prev.map(x => x.id === id ? { ...x, status, note } : x))
  }

  async function fetchSessionKeywords() {
    if (!selectedSession) {
      showToast("Please select a session first", "error")
      return
    }
    setFetchingKeywords(true)
    try {
      const resp = await fetch(`${API}/api/kw2/${projectId}/sessions/${selectedSession}/validated`, {
        headers: { Authorization: `Bearer ${token()}` }
      })
      if (!resp.ok) throw new Error("Failed to fetch keywords")
      const data = await resp.json()
      const items = data.items || []
      const kws = items.map(k => typeof k === 'string' ? k : k.keyword).filter(Boolean)
      if (kws.length === 0) {
        showToast("No validated keywords found in session.", "info")
      } else {
        showToast(`Loaded ${kws.length} keywords.`)
        // set to text box (top 10 by default)
        setKeywordsText(kws.slice(0, 10).join("\n"))
      }
    } catch (e) {
      showToast(e.message, "error")
    } finally {
      setFetchingKeywords(false)
    }
  }

  async function startGeneration() {
    const keywords = keywordsText
      .split("\n")
      .map(k => k.trim())
      .filter(Boolean)
      .slice(0, 10)

    if (keywords.length === 0) {
      showToast("Enter at least one keyword", "error")
      return
    }

    setStep("generating")
    setProgressItems([])
    setLiveCards([])
    setGenError(null)

    const body = {
      keywords,
      session_id: useKw2Context && selectedSession ? selectedSession : "",
      goals: businessGoals,
    }

    addProgress("start", "Starting pipeline…", "running")

    try {
      const controller = new AbortController()
      abortRef.current = controller

      const resp = await fetch(`${API}/api/strategy-v2/${projectId}/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token()}`,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!resp.ok) {
        const err = await resp.text()
        throw new Error(err || `HTTP ${resp.status}`)
      }

      updateProgress("start", "done")

      // read SSE stream
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split("\n")
        buffer = lines.pop() // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const raw = line.slice(6).trim()
          if (!raw) continue

          let evt
          try { evt = JSON.parse(raw) } catch { continue }

          handleStreamEvent(evt)
        }
      }
    } catch (e) {
      if (e.name === "AbortError") {
        showToast("Generation cancelled", "info")
        setStep("input")
        return
      }
      setGenError(e.message || "Unknown error")
      showToast(`Error: ${e.message}`, "error")
    }
  }

  function handleStreamEvent(evt) {
    const type = evt.type || evt.event

    if (type === "classify") {
      addProgress(`kw_${evt.keyword}`, `${evt.keyword} → intent: ${evt.intent}`, "done")
    } else if (type === "angles") {
      addProgress(`angles_${evt.keyword}`, `${evt.keyword} → ${evt.count} angles generated`, "done")
    } else if (type === "blueprint_start") {
      addProgress(`bp_${evt.keyword}_${evt.angle_index}`, `Blueprint: "${evt.angle_label || "angle " + evt.angle_index}"`, "running")
    } else if (type === "blueprint_done") {
      updateProgress(`bp_${evt.keyword}_${evt.angle_index}`, "done", `score ${evt.score}`)
      if (evt.blueprint) {
        setLiveCards(prev => [...prev, evt.blueprint])
      }
    } else if (type === "fix") {
      addProgress(`fix_${evt.blueprint_id}`, `Auto-fixing blueprint (score < 75)…`, "running")
    } else if (type === "fix_done") {
      updateProgress(`fix_${evt.blueprint_id}`, "done", `score → ${evt.new_score}`)
    } else if (type === "complete") {
      addProgress("complete", `✓ Done — ${evt.total} blueprints ready`, "done")
      const allBlueprints = evt.blueprints || []
      setBlueprints(allBlueprints)
      setTimeout(() => {
        setStep("results")
      }, 600)
    } else if (type === "error") {
      addProgress(`err_${Date.now()}`, evt.message || "Error", "error")
      setGenError(evt.message)
    } else if (type === "progress") {
      addProgress(`prog_${evt.step}`, evt.message, evt.done ? "done" : "running")
    }
  }

  function cancelGeneration() {
    if (abortRef.current) abortRef.current.abort()
  }

  // ── filter logic ─────────────────────────────────────────────────────────────

  const angleTypes = ["all", ...new Set(blueprints.map(b => b.angle_type).filter(Boolean))]
  const filtered = blueprints.filter(b => {
    const matchAngle = angleFilter === "all" || b.angle_type === angleFilter
    const score = b.qa_overall_score ?? b.score ?? 0
    return matchAngle && score >= minScore
  })

  // ── content started callback ──────────────────────────────────────────────────

  function handleContentStarted(data) {
    showToast("Content generation started! Open Content to track progress.", "success")
  }

  // ── render ────────────────────────────────────────────────────────────────────

  const containerStyle = {
    maxWidth: 900, margin: "0 auto", padding: "24px 16px", fontFamily: "inherit",
  }
  const cardStyle = {
    background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10,
    padding: 24, marginBottom: 20, boxShadow: "0 1px 3px rgba(0,0,0,.06)",
  }
  const headingStyle = { fontSize: 15, fontWeight: 700, color: "#111827", margin: "0 0 16px" }
  const labelStyle = { fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }
  const inputStyle = {
    width: "100%", padding: "8px 10px", border: "1px solid #d1d5db", borderRadius: 6,
    fontSize: 13, boxSizing: "border-box", outline: "none",
  }
  const btnPrimary = {
    background: "#2563eb", color: "#fff", border: "none",
    padding: "9px 20px", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600,
  }
  const btnSecondary = {
    background: "#f3f4f6", color: "#374151", border: "1px solid #d1d5db",
    padding: "8px 16px", borderRadius: 6, cursor: "pointer", fontSize: 13,
  }

  return (
    <div style={containerStyle}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 4px", color: "#111827" }}>
          🎯 Strategy V2 — Content Blueprint Engine
        </h1>
        <p style={{ fontSize: 13, color: "#6b7280", margin: 0 }}>
          Transform keywords into uniquely-angled, high-quality content blueprints
        </p>
      </div>

      {/* Step tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20 }}>
        {[
          { id: "input", label: "1. Keywords" },
          { id: "generating", label: "2. Generating" },
          { id: "results", label: "3. Blueprints" },
        ].map(s => (
          <div
            key={s.id}
            style={{
              padding: "6px 14px", borderRadius: 6, fontSize: 12, fontWeight: 600,
              background: step === s.id ? "#2563eb" : "#f3f4f6",
              color: step === s.id ? "#fff" : "#9ca3af",
              cursor: blueprints.length > 0 && s.id === "results" ? "pointer" : "default",
            }}
            onClick={() => {
              if (s.id === "results" && blueprints.length > 0) setStep("results")
              if (s.id === "input" && step !== "generating") setStep("input")
            }}
          >
            {s.label}
          </div>
        ))}
      </div>

      {/* ── Step 1: Keywords Input ── */}
      {step === "input" && (
        <div style={cardStyle}>
          <h2 style={headingStyle}>Enter Keywords</h2>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Keywords (one per line, max 10)</label>
            <textarea
              style={{ ...inputStyle, resize: "vertical", minHeight: 120 }}
              placeholder={"best cinnamon supplement\norganic turmeric powder\nblack pepper extract benefits"}
              value={keywordsText}
              onChange={e => setKeywordsText(e.target.value)}
            />
            <p style={{ fontSize: 11, color: "#9ca3af", margin: "4px 0 0" }}>
              {keywordsText.split("\n").filter(k => k.trim()).length} / 10 keywords
            </p>
          </div>

          {sessions.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>
                <input
                  type="checkbox"
                  checked={useKw2Context}
                  onChange={e => setUseKw2Context(e.target.checked)}
                  style={{ marginRight: 6 }}
                />
                Use KW2 session context (brand voice, audience, competitors)
              </label>
              {useKw2Context && (
                <div style={{ marginTop: 8 }}>
                  <select
                    style={inputStyle}
                    value={selectedSession}
                    onChange={e => setSelectedSession(e.target.value)}
                  >
                    {sessions.map(s => (
                      <option key={s.session_id || s.id} value={s.session_id || s.id}>
                        {s.name || s.session_name || `Session ${s.session_id || s.id}`}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={fetchSessionKeywords}
                    disabled={fetchingKeywords}
                    style={{ ...btnSecondary, marginTop: 8, display: "block" }}
                  >
                    {fetchingKeywords ? "Loading..." : "Pull Validated Keywords"}
                  </button>

                  <div style={{ marginTop: 16, padding: 12, background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>
                    <label style={labelStyle}>Business Outcome</label>
                    <select
                      style={{ ...inputStyle, marginBottom: 12 }}
                      value={businessGoals.businessOutcome}
                      onChange={e => setBusinessGoals(g => ({ ...g, businessOutcome: e.target.value }))}
                    >
                      <option value="traffic">Drive Organic Traffic</option>
                      <option value="leads">Generate B2B Leads</option>
                      <option value="sales">Direct eCommerce Sales</option>
                      <option value="authority">Establish Brand Authority</option>
                    </select>

                    <label style={labelStyle}>Target Audience</label>
                    <input
                      style={inputStyle}
                      placeholder="e.g. CMOs at B2B Tech Companies (optional)"
                      value={businessGoals.targetAudience}
                      onChange={e => setBusinessGoals(g => ({ ...g, targetAudience: e.target.value }))}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {sessionsLoading && (
            <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: 12 }}>Loading KW2 sessions…</p>
          )}

          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <button style={btnPrimary} onClick={startGeneration}>
              Generate Blueprints →
            </button>
            {blueprints.length > 0 && (
              <button style={btnSecondary} onClick={() => setStep("results")}>
                View existing ({blueprints.length})
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Step 2: Generation Progress ── */}
      {step === "generating" && (
        <div style={cardStyle}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <h2 style={{ ...headingStyle, margin: 0 }}>Generating Blueprints…</h2>
            <button style={btnSecondary} onClick={cancelGeneration}>Cancel</button>
          </div>

          {genError && (
            <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, padding: "10px 12px", marginBottom: 12 }}>
              <p style={{ color: "#dc2626", fontSize: 13, margin: 0 }}>Error: {genError}</p>
              <button style={{ ...btnSecondary, marginTop: 8 }} onClick={() => setStep("input")}>← Back</button>
            </div>
          )}

          <div style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6, padding: 12, marginBottom: 16 }}>
            {progressItems.length === 0 && (
              <div style={{ color: "#9ca3af", fontSize: 13 }}>Starting…</div>
            )}
            {progressItems.map(item => <ProgressItem key={item.id} item={item} />)}
          </div>

          {/* Live blueprint cards as they come in */}
          {liveCards.length > 0 && (
            <div>
              <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 10, color: "#374151" }}>
                Blueprints ready ({liveCards.length})
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(380px,1fr))", gap: 14 }}>
                {liveCards.map((bp, i) => (
                  <BlueprintCard
                    key={bp.id || i}
                    blueprint={bp}
                    projectId={projectId}
                    onContentStarted={handleContentStarted}
                    setPage={setPage}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Step 3: Results ── */}
      {step === "results" && (
        <div>
          {/* Filter bar */}
          <div style={{
            ...cardStyle, padding: "12px 16px",
            display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
          }}>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", flex: 1 }}>
              {angleTypes.map(a => (
                <FilterChip
                  key={a}
                  label={a === "all" ? "All angles" : a.replace(/_/g, " ")}
                  active={angleFilter === a}
                  onClick={() => setAngleFilter(a)}
                />
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <label style={{ fontSize: 12, color: "#374151", whiteSpace: "nowrap" }}>
                Min score: <strong>{minScore}</strong>
              </label>
              <input
                type="range" min={0} max={100} step={5} value={minScore}
                onChange={e => setMinScore(Number(e.target.value))}
                style={{ width: 100 }}
              />
            </div>
            <button style={btnPrimary} onClick={() => setStep("input")}>
              + Generate More
            </button>
          </div>

          {/* Stats row */}
          <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
            {[
              { label: "Total Blueprints", value: blueprints.length, color: "#3b82f6" },
              { label: "Showing", value: filtered.length, color: "#10b981" },
              {
                label: "Avg Score",
                value: blueprints.length
                  ? Math.round(blueprints.reduce((s, b) => s + (b.qa_overall_score ?? 0), 0) / blueprints.length)
                  : 0,
                color: "#8b5cf6",
              },
            ].map(stat => (
              <div
                key={stat.label}
                style={{
                  background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8,
                  padding: "10px 16px", display: "flex", flexDirection: "column", alignItems: "center",
                  minWidth: 110,
                }}
              >
                <span style={{ fontSize: 22, fontWeight: 700, color: stat.color }}>{stat.value}</span>
                <span style={{ fontSize: 11, color: "#9ca3af" }}>{stat.label}</span>
              </div>
            ))}
          </div>

          {filtered.length === 0 ? (
            <div style={{ ...cardStyle, textAlign: "center", color: "#9ca3af", padding: 40 }}>
              <p style={{ fontSize: 24, margin: "0 0 8px" }}>🔍</p>
              <p style={{ margin: 0, fontSize: 14 }}>No blueprints match the current filters</p>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(400px,1fr))", gap: 16 }}>
              {filtered.map((bp, i) => (
                <BlueprintCard
                  key={bp.id || i}
                  blueprint={bp}
                  projectId={projectId}
                  onContentStarted={handleContentStarted}
                  setPage={setPage}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  )
}
