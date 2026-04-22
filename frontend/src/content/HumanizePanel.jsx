import { useState, useRef, useEffect, useCallback } from "react"
import { T, api, Btn } from "../App"

const SEV_COLORS = { high: "#dc2626", medium: "#d97706", low: "#9ca3af" }

const TONE_OPTIONS = [
  { value: "natural", label: "Natural", desc: "Approachable, like explaining to a friend" },
  { value: "conversational", label: "Conversational", desc: "Warm, contractions, rhetorical questions" },
  { value: "expert", label: "Expert", desc: "Authoritative, precise terminology" },
  { value: "narrative", label: "Narrative", desc: "Storytelling, anecdotes, vivid" },
  { value: "direct", label: "Direct", desc: "No-nonsense, short sentences" },
]

const STYLE_OPTIONS = [
  { value: "conversational", label: "Blog-style" },
  { value: "academic", label: "Academic" },
  { value: "journalistic", label: "Journalistic" },
  { value: "casual", label: "Casual" },
]

// Log line type → color mapping for the console
const LOG_COLORS = {
  analyzing: "#60a5fa",   // blue
  analyzed: "#60a5fa",
  locking: "#a78bfa",     // purple
  locked: "#a78bfa",
  split: "#818cf8",       // indigo
  restructuring: "#fb923c", // orange
  restructured: "#34d399",  // green
  humanizing: "#fbbf24",  // amber
  section_done: "#34d399", // teal/green
  section_failed: "#f87171", // red
  assembling: "#60a5fa",
  validating: "#a78bfa",
  validated: "#34d399",
  seo_warning: "#fbbf24",
  scoring: "#60a5fa",
  judging: "#38bdf8",     // sky blue
  judged: "#818cf8",      // indigo
  iterating: "#fb923c",   // orange
  iterated: "#34d399",    // green
  done: "#34d399",
  complete: "#34d399",
  failed: "#f87171",
  error: "#f87171",
  stopped: "#9ca3af",
  info: "#9ca3af",
}

async function getStreamToken() {
  try {
    const res = await api.post("/api/auth/stream-token")
    return res?.stream_token || ""
  } catch {
    return localStorage.getItem("annaseo_token") || ""
  }
}

export default function HumanizePanel({ articleId, onHumanized }) {
  const [score, setScore] = useState(null)
  const [scanning, setScanning] = useState(false)
  const [humanizing, setHumanizing] = useState(false)
  const [paused, setPaused] = useState(false)
  const [tone, setTone] = useState("natural")
  const [style, setStyle] = useState("conversational")
  const [persona, setPersona] = useState("")
  const [result, setResult] = useState(null)
  const [signals, setSignals] = useState([])
  const [error, setError] = useState("")
  const [logs, setLogs] = useState([])
  const [pct, setPct] = useState(0)
  const [currentStep, setCurrentStep] = useState("")
  const [sessionId, setSessionId] = useState(null)

  const esRef = useRef(null)        // EventSource reference
  const logBoxRef = useRef(null)    // Console auto-scroll ref
  const sessionIdRef = useRef(null) // Track session id for control calls

  // Auto-scroll console to bottom
  useEffect(() => {
    if (logBoxRef.current) logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight
  }, [logs])

  const addLog = useCallback((type, text, extra) => {
    setLogs(prev => [...prev, { type, text, time: new Date(), extra }])
  }, [])

  const cleanupSSE = useCallback(() => {
    if (esRef.current) { esRef.current.close(); esRef.current = null }
  }, [])

  // Cleanup on unmount
  useEffect(() => () => cleanupSSE(), [cleanupSSE])

  const scanScore = async () => {
    setScanning(true)
    setError("")
    try {
      const res = await api.get(`/api/content/${articleId}/humanize/score`)
      setScore(res)
      setSignals(res?.signals || [])
    } catch (e) {
      setError(e?.detail || e?.message || "Scan failed")
    } finally {
      setScanning(false)
    }
  }

  const runHumanize = async () => {
    setHumanizing(true)
    setPaused(false)
    setError("")
    setResult(null)
    setLogs([])
    setPct(0)
    setCurrentStep("Starting...")

    addLog("info", "Starting humanization pipeline...")

    try {
      // Step 1: POST to /humanize/start to get session_id
      const startRes = await api.post(`/api/content/${articleId}/humanize/start`, {
        tone, style, persona, section_index: -1,
      })
      const sid = startRes?.session_id
      setSessionId(sid)
      sessionIdRef.current = sid
      addLog("info", `Session ${sid} created — connecting to stream...`)

      // Step 2: Get stream token and connect SSE
      const streamToken = await getStreamToken()
      const API = import.meta.env.VITE_API_URL || ""
      const sseUrl = `${API}/api/content/${articleId}/humanize/stream?session_id=${sid}&token=${encodeURIComponent(streamToken)}`

      cleanupSSE()
      const es = new EventSource(sseUrl)
      esRef.current = es

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)

          // Final "done" sentinel from SSE wrapper
          if (data.done === true && !data.type) {
            cleanupSSE()
            return
          }

          const type = data.type || "info"
          const detail = data.detail || ""

          // Update progress percentage
          if (data.total > 0 && data.current > 0) {
            const p = Math.round((data.current / data.total) * 100)
            if (type === "humanizing") setPct(p)
            else if (type === "section_done" || type === "section_failed") {
              setPct(Math.round((data.current / data.total) * 100))
            }
          }

          // Update current step display
          if (["analyzing", "locking", "restructuring", "humanizing", "assembling",
               "validating", "scoring", "judging", "iterating"].includes(type)) {
            setCurrentStep(detail)
          }

          // Log the event
          addLog(type, detail, data)

          // Handle specific event types
          if (type === "analyzed") {
            setScore(prev => ({ ...(prev || {}), score: data.score, signals: data.signals }))
            if (data.signals) setSignals(data.signals)
          }

          if (type === "restructured") {
            addLog("restructured", `Structure: ${data.original_count} → ${data.new_count} sections`)
          }

          if (type === "judged" && data.score) {
            const breakdown = data.breakdown || {}
            const parts = Object.entries(breakdown)
              .map(([k, v]) => `${k}: ${v}`).join(" | ")
            addLog("judged", `Judge: ${data.score}/100${parts ? " — " + parts : ""}`)
            if (data.issues?.length) {
              data.issues.slice(0, 3).forEach(issue => addLog("info", `  ↳ ${issue}`))
            }
          }

          if (type === "iterated") {
            addLog("iterated", `Fixed ${data.fixed} sections — applying improvements`)
          }

          if (type === "section_failed" && data.rate_limited) {
            addLog("error", `⚠ Rate limited on ${data.provider || "provider"} — pipeline will try next provider automatically`)
          }

          if (type === "complete") {
            const r = data.result || {}
            setResult(r)
            setScore(prev => ({ ...(prev || {}), score: r.final_score }))
            if (r.details?.final_signals) setSignals(r.details.final_signals)
            setPct(100)
            setCurrentStep("Complete!")
            setHumanizing(false)
            if (onHumanized) onHumanized(r)
            const judgeNote = r.judge_score ? ` | Judge: ${r.judge_score}/100` : ""
            addLog("done", `✓ Humanization complete — score ${r.original_score} → ${r.final_score}${judgeNote}`)
            cleanupSSE()
          }

          if (type === "failed" || type === "error") {
            setError(data.error || data.message || "Humanization failed")
            setHumanizing(false)
            setCurrentStep("Failed")
            cleanupSSE()
          }

          if (type === "done" && data.original_score !== undefined) {
            setPct(100)
            setCurrentStep(`Score: ${data.original_score} → ${data.final_score}`)
          }
        } catch (err) {
          addLog("error", `Parse error: ${err.message}`)
        }
      }

      es.onerror = () => {
        if (!esRef.current) return // already cleaned up
        addLog("error", "Connection lost — stream ended")
        setHumanizing(false)
        setCurrentStep("Disconnected")
        cleanupSSE()
      }
    } catch (e) {
      setError(e?.detail || e?.message || "Failed to start humanization")
      setHumanizing(false)
      setCurrentStep("")
    }
  }

  const sendControl = async (action) => {
    const sid = sessionIdRef.current
    if (!sid) return
    try {
      await api.post(`/api/content/${articleId}/humanize/${sid}/control`, { action })
      addLog("info", `→ ${action.toUpperCase()} sent`)
      if (action === "pause") setPaused(true)
      if (action === "resume") setPaused(false)
      if (action === "stop") {
        setHumanizing(false)
        setCurrentStep("Stopped")
        cleanupSSE()
      }
    } catch (e) {
      addLog("error", `Control failed: ${e?.detail || e?.message || "Unknown error"}`)
    }
  }

  const scoreVal = score?.score ?? null
  const scoreColor = scoreVal === null ? T.gray : scoreVal >= 85 ? T.teal : scoreVal >= 65 ? "#22c55e" : scoreVal >= 40 ? T.amber : "#dc2626"

  return (
    <div style={{ padding: "16px 14px", height: "100%", overflowY: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>Humanization</div>

      {/* Score display */}
      <div style={{ textAlign: "center", padding: "8px 0" }}>
        {scoreVal !== null ? (
          <>
            <div style={{ fontSize: 48, fontWeight: 700, color: scoreColor, lineHeight: 1, letterSpacing: -2 }}>
              {scoreVal}
            </div>
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4 }}>
              Human Score{score?.signal_count ? ` · ${score.signal_count} signals` : ""}
            </div>
            <div style={{
              marginTop: 6, fontSize: 10, fontWeight: 600, color: scoreColor,
              background: `${scoreColor}15`, borderRadius: 99, padding: "2px 10px", display: "inline-block",
            }}>
              {score?.summary || (scoreVal >= 85 ? "Reads naturally" : scoreVal >= 65 ? "Minor AI signals" : scoreVal >= 40 ? "Needs work" : "High AI risk")}
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: 34, fontWeight: 700, color: T.gray, lineHeight: 1 }}>—</div>
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4 }}>Not scanned yet</div>
          </>
        )}
      </div>

      {/* Progress bar (only during humanization) */}
      {humanizing && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 10, color: T.textSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
              {currentStep}
            </span>
            <span style={{ fontSize: 11, fontWeight: 700, color: T.purple, marginLeft: 8, flexShrink: 0 }}>
              {pct}%
            </span>
          </div>
          <div style={{ height: 6, background: "#e5e7eb", borderRadius: 4, overflow: "hidden" }}>
            <div style={{
              height: "100%", borderRadius: 4, transition: "width 0.3s ease",
              width: `${pct}%`,
              background: `linear-gradient(90deg, #7c3aed, #a78bfa)`,
            }} />
          </div>
        </div>
      )}

      {/* Console log */}
      {logs.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 10, fontWeight: 600, color: T.text }}>Console</span>
            {!humanizing && (
              <button onClick={() => setLogs([])} style={{
                fontSize: 8, color: T.textSoft, background: "none", border: "none", cursor: "pointer",
              }}>Clear</button>
            )}
          </div>
          <div ref={logBoxRef} style={{
            background: "#0f1117", borderRadius: 8, padding: "8px 10px",
            maxHeight: 200, overflowY: "auto", fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          }}>
            {logs.map((log, i) => (
              <div key={i} style={{
                fontSize: 10, lineHeight: 1.6, display: "flex", gap: 6, alignItems: "flex-start",
              }}>
                <span style={{ color: "#6b7280", fontSize: 9, flexShrink: 0, marginTop: 1 }}>
                  {log.time.toLocaleTimeString("en", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>
                <span style={{ color: LOG_COLORS[log.type] || "#9ca3af" }}>
                  {log.text}
                </span>
              </div>
            ))}
            {humanizing && (
              <div style={{ fontSize: 10, color: "#6b7280", animation: "pulse 1.5s infinite" }}>
                ▌
              </div>
            )}
          </div>
        </div>
      )}

      {/* Control buttons (shown while humanizing) */}
      {humanizing && (
        <div style={{ display: "flex", gap: 4 }}>
          {!paused ? (
            <button onClick={() => sendControl("pause")} style={{
              flex: 1, fontSize: 10, fontWeight: 600, padding: "5px 0", borderRadius: 6,
              border: `1px solid ${T.amber}`, background: "#fffbeb", color: "#92400e", cursor: "pointer",
            }}>⏸ Pause</button>
          ) : (
            <button onClick={() => sendControl("resume")} style={{
              flex: 1, fontSize: 10, fontWeight: 600, padding: "5px 0", borderRadius: 6,
              border: `1px solid ${T.teal}`, background: "#f0fdf4", color: "#15803d", cursor: "pointer",
            }}>▶ Resume</button>
          )}
          <button onClick={() => sendControl("stop")} style={{
            flex: 1, fontSize: 10, fontWeight: 600, padding: "5px 0", borderRadius: 6,
            border: "1px solid #dc2626", background: "#fef2f2", color: "#dc2626", cursor: "pointer",
          }}>⏹ Stop</button>
        </div>
      )}

      {/* Restart button (shown after completion/failure/stop) */}
      {!humanizing && result && (
        <button onClick={runHumanize} style={{
          fontSize: 10, fontWeight: 600, padding: "5px 0", borderRadius: 6, width: "100%",
          border: `1px solid ${T.purple}`, background: "#faf5ff", color: T.purple, cursor: "pointer",
        }}>↻ Restart Humanization</button>
      )}

      {/* AI Signals breakdown */}
      {signals.length > 0 && !humanizing && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: T.text }}>AI Signals Detected</div>
          {signals.map((sig, i) => (
            <div key={i} style={{
              fontSize: 10, lineHeight: 1.5, padding: "6px 8px", borderRadius: 7,
              background: sig.severity === "high" ? "#fef2f2" : sig.severity === "medium" ? "#fefce8" : "#f9f9f9",
              display: "flex", gap: 6, alignItems: "flex-start",
            }}>
              <span style={{
                fontSize: 8, fontWeight: 700, color: "#fff", flexShrink: 0,
                textTransform: "uppercase",
                background: SEV_COLORS[sig.severity] || SEV_COLORS.medium,
                borderRadius: 3, padding: "1px 4px", lineHeight: "14px", marginTop: 1,
              }}>{sig.severity?.[0]?.toUpperCase()}</span>
              <div style={{ flex: 1 }}>
                <div style={{ color: T.text, fontWeight: 500 }}>{sig.type.replace(/_/g, " ")}</div>
                <div style={{ color: T.textSoft, fontSize: 9, marginTop: 1 }}>{sig.detail}</div>
              </div>
              <span style={{ fontSize: 9, color: "#dc2626", fontWeight: 600, flexShrink: 0 }}>
                -{sig.deduction}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Tone selector */}
      {!humanizing && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 600, color: T.text, marginBottom: 4 }}>Tone</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {TONE_OPTIONS.map(t => (
              <button key={t.value} onClick={() => setTone(t.value)} title={t.desc}
                style={{
                  fontSize: 10, padding: "3px 8px", borderRadius: 6, cursor: "pointer",
                  border: `1px solid ${tone === t.value ? T.purple : T.border}`,
                  background: tone === t.value ? T.purpleLight : "#fff",
                  color: tone === t.value ? T.purple : T.text,
                  fontWeight: tone === t.value ? 600 : 400,
                }}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Style selector */}
      {!humanizing && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 600, color: T.text, marginBottom: 4 }}>Style</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {STYLE_OPTIONS.map(s => (
              <button key={s.value} onClick={() => setStyle(s.value)}
                style={{
                  fontSize: 10, padding: "3px 8px", borderRadius: 6, cursor: "pointer",
                  border: `1px solid ${style === s.value ? T.purple : T.border}`,
                  background: style === s.value ? T.purpleLight : "#fff",
                  color: style === s.value ? T.purple : T.text,
                  fontWeight: style === s.value ? 600 : 400,
                }}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Persona (optional) */}
      {!humanizing && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 600, color: T.text, marginBottom: 4 }}>Writer Persona <span style={{ fontWeight: 400, color: T.textSoft }}>(optional)</span></div>
          <input
            value={persona}
            onChange={e => setPersona(e.target.value)}
            placeholder="e.g. 10-year veterinarian, home gardening enthusiast"
            style={{
              width: "100%", fontSize: 10, padding: "5px 8px", borderRadius: 6,
              border: `1px solid ${T.border}`, background: "#fff", boxSizing: "border-box",
            }}
          />
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ fontSize: 10, color: "#dc2626", padding: "6px 8px", background: "#fef2f2", borderRadius: 6 }}>
          {error}
        </div>
      )}

      {/* Result summary */}
      {result && result.success && !humanizing && (
        <div style={{
          padding: "8px 10px", borderRadius: 8,
          background: result.final_score > result.original_score ? "#f0fdf4" : "#fffbeb",
          border: `1px solid ${result.final_score > result.original_score ? "#bbf7d0" : "#fde68a"}`,
        }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: result.final_score > result.original_score ? "#15803d" : "#92400e" }}>
            Score: {result.original_score} → {result.final_score}
            {result.final_score > result.original_score ? " ↑" : result.final_score === result.original_score ? " =" : " ↓"}
          </div>
          <div style={{ fontSize: 9, color: T.textSoft, marginTop: 2 }}>
            {result.sections_processed}/{result.sections_total} sections · {result.elapsed_seconds}s
            {result.tokens_used > 0 ? ` · ${result.tokens_used} tokens` : ""}
          </div>
          {result.seo_issues?.length > 0 && (
            <div style={{ fontSize: 9, color: "#dc2626", marginTop: 4 }}>
              ⚠ SEO: {result.seo_issues.join("; ")}
            </div>
          )}
        </div>
      )}

      {/* Action buttons */}
      {!humanizing && (
        <>
          <Btn onClick={scanScore} disabled={scanning} style={{ width: "100%" }}>
            {scanning ? "Scanning..." : scoreVal !== null ? "Re-Scan" : "Scan AI Score"}
          </Btn>

          <Btn onClick={runHumanize} variant="primary" disabled={scanning}
            style={{
              width: "100%",
              background: "#7c3aed",
              borderColor: "#7c3aed",
            }}>
            Humanize Article
          </Btn>
        </>
      )}
    </div>
  )
}
