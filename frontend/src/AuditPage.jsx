/**
 * AuditPage — Persistent multi-step code audit pipeline.
 * Audit runs as a background task on the server.
 * Refresh-safe: session restored from API on mount.
 * Controls: Pause · Resume · Stop · New Audit.
 */
import { useState, useEffect, useRef, useCallback } from "react"
import { useStore } from "./App"

const API = import.meta.env.VITE_API_URL || ""
const LS_KEY = "annaseo_code_audit_id"

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  text:   "#111827",
  soft:   "#6b7280",
  border: "#e5e7eb",
  bg:     "#f9fafb",
  blue:   "#1d4ed8",
  green:  "#059669",
  red:    "#dc2626",
  amber:  "#d97706",
  purple: "#7c3aed",
  teal:   "#0f766e",
}

// ── Static data ───────────────────────────────────────────────────────────────
const TARGETS = [
  { id: "phase1",   label: "Phase 1 — Business Analyzer",  icon: "🏢", desc: "Pillar extraction, product → entity, profile building" },
  { id: "phase2",   label: "Phase 2 — Keyword Generator",  icon: "🔑", desc: "Modifier extraction, keyword generation, suggest" },
  { id: "kw2",      label: "Full kw2 Pipeline",            icon: "🚀", desc: "All kw2 engines: business, pillars, modifiers, strategy" },
  { id: "content",  label: "Content Engine",               icon: "✍️",  desc: "7-pass generation, schema builder, lineage" },
  { id: "strategy", label: "Strategy Engine",              icon: "🧠", desc: "Strategy dev, final strategy, ranking monitor" },
  { id: "quality",  label: "Quality / QI Engine",          icon: "🎯", desc: "QI scoring, domain context, quality pipeline" },
  { id: "rsd",      label: "RSD / Self-Dev Engine",        icon: "🔬", desc: "Health monitoring, self-improvement, intelligence" },
]

const MODELS = [
  { id: "ollama/mistral:7b-instruct-q4_K_M", label: "Ollama — Mistral 7B",      badge: "local · free",  color: T.teal },
  { id: "ollama/llama3:8b",                  label: "Ollama — Llama 3 8B",       badge: "local · free",  color: T.teal },
  { id: "ollama/deepseek-coder:7b",           label: "Ollama — DeepSeek Coder",   badge: "local · free",  color: T.teal },
  { id: "gemini-flash",                       label: "Gemini 1.5 Flash",          badge: "cloud · free",  color: T.blue },
]

const ALL_STEPS = [
  { id: 0, name: "Context Builder",    icon: "🗺️", desc: "Summarize system structure" },
  { id: 1, name: "Code Understanding", icon: "🔍", desc: "Trace execution + assumptions" },
  { id: 2, name: "Bug Analysis",       icon: "🐛", desc: "Functional bugs + edge cases" },
  { id: 3, name: "Data Flow",          icon: "🔄", desc: "Trace transformations + leaks" },
  { id: 4, name: "Performance",        icon: "⚡", desc: "Bottlenecks + async ops" },
  { id: 5, name: "AI Usage",           icon: "🤖", desc: "Optimize / reduce AI calls" },
  { id: 6, name: "Test Generator",     icon: "🧪", desc: "Unit, integration, regression tests" },
  { id: 7, name: "Fix Engine",         icon: "🔧", desc: "Rewrite problem sections" },
  { id: 8, name: "Final Report",       icon: "📋", desc: "P0/P1/P2/P3 fix roadmap" },
]

// ── Markdown renderer (lightweight, no deps) ──────────────────────────────────
function renderMd(text) {
  if (!text) return []
  const lines = text.split("\n")
  const out = []
  let inCode = false
  let codeBuf = []
  let codeLang = ""
  let key = 0

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (line.startsWith("```")) {
      if (!inCode) {
        inCode = true
        codeLang = line.slice(3).trim()
        codeBuf = []
      } else {
        out.push(
          <pre key={key++} style={{
            background: "#1e293b", color: "#e2e8f0", borderRadius: 7,
            padding: "10px 14px", fontSize: 11.5, lineHeight: 1.6,
            overflowX: "auto", margin: "8px 0", whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>
            {codeLang && <span style={{ color: "#94a3b8", fontSize: 10, display: "block", marginBottom: 4 }}>{codeLang}</span>}
            {codeBuf.join("\n")}
          </pre>
        )
        inCode = false
        codeBuf = []
        codeLang = ""
      }
      continue
    }
    if (inCode) { codeBuf.push(line); continue }

    if (line.startsWith("### ")) {
      out.push(<div key={key++} style={{ fontWeight: 700, fontSize: 13, color: T.text, margin: "10px 0 4px" }}>{line.slice(4)}</div>)
    } else if (line.startsWith("## ")) {
      out.push(<div key={key++} style={{ fontWeight: 800, fontSize: 14, color: T.blue, margin: "14px 0 5px", borderBottom: `1px solid ${T.border}`, paddingBottom: 4 }}>{line.slice(3)}</div>)
    } else if (line.startsWith("# ")) {
      out.push(<div key={key++} style={{ fontWeight: 800, fontSize: 16, color: T.text, margin: "16px 0 6px" }}>{line.slice(2)}</div>)
    } else if (/^[-*] /.test(line)) {
      out.push(<div key={key++} style={{ display: "flex", gap: 6, margin: "2px 0", paddingLeft: 8 }}>
        <span style={{ color: T.blue, flexShrink: 0 }}>•</span>
        <span style={{ color: "#374151", fontSize: 12.5, lineHeight: 1.6 }}>{inlineFormat(line.slice(2))}</span>
      </div>)
    } else if (/^\d+\. /.test(line)) {
      const num = line.match(/^(\d+)\./)[1]
      out.push(<div key={key++} style={{ display: "flex", gap: 6, margin: "2px 0", paddingLeft: 8 }}>
        <span style={{ color: T.blue, flexShrink: 0, minWidth: 18 }}>{num}.</span>
        <span style={{ color: "#374151", fontSize: 12.5, lineHeight: 1.6 }}>{inlineFormat(line.slice(num.length + 2))}</span>
      </div>)
    } else if (line.trim() === "") {
      out.push(<div key={key++} style={{ height: 6 }} />)
    } else {
      out.push(<div key={key++} style={{ color: "#374151", fontSize: 12.5, lineHeight: 1.6 }}>{inlineFormat(line)}</div>)
    }
  }
  return out
}

function inlineFormat(text) {
  // Bold **text** and inline `code`
  const parts = []
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g
  let last = 0, m
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    if (m[0].startsWith("`")) {
      parts.push(<code key={m.index} style={{ background: "#f1f5f9", color: "#0f172a", borderRadius: 3, padding: "1px 4px", fontSize: 11, fontFamily: "monospace" }}>{m[0].slice(1, -1)}</code>)
    } else {
      parts.push(<strong key={m.index}>{m[0].slice(2, -2)}</strong>)
    }
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts.length === 1 && typeof parts[0] === "string" ? parts[0] : parts
}

// ── Small components ──────────────────────────────────────────────────────────

function SelectCard({ item, selected, onSelect, disabled, children }) {
  return (
    <button
      onClick={() => !disabled && onSelect(item.id)}
      style={{
        textAlign: "left", width: "100%", padding: "10px 14px",
        borderRadius: 9, border: `1.5px solid ${selected ? T.blue : T.border}`,
        background: selected ? T.blue + "0d" : "#fff",
        cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1,
        transition: "border 0.1s, background 0.1s", marginBottom: 6,
      }}
    >
      {children}
    </button>
  )
}

function StepRow({ step, status, content, expanded, onToggle, onCopy }) {
  const statusDot = {
    idle:    { color: T.border,  label: "○" },
    running: { color: T.amber,   label: "⏳" },
    done:    { color: T.green,   label: "✅" },
    error:   { color: T.red,     label: "❌" },
  }[status] || { color: T.border, label: "○" }

  return (
    <div style={{
      border: `1px solid ${status === "error" ? T.red + "44" : status === "done" ? T.green + "33" : T.border}`,
      borderLeft: `3px solid ${statusDot.color}`,
      borderRadius: 8, marginBottom: 8, overflow: "hidden",
    }}>
      <div
        onClick={content ? onToggle : undefined}
        style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "10px 14px",
          background: status === "running" ? T.amber + "08"
                    : status === "done"    ? T.green + "06"
                    : status === "error"   ? T.red + "06"
                    : "#fff",
          cursor: content ? "pointer" : "default",
        }}
      >
        <span style={{ fontSize: 16, width: 22, flexShrink: 0 }}>{step.icon}</span>
        <div style={{ flex: 1 }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{step.name}</span>
          <span style={{ fontSize: 11, color: T.soft, marginLeft: 8 }}>{step.desc}</span>
        </div>
        <span style={{ fontSize: 13 }}>{statusDot.label}</span>
        {content && onCopy && (
          <button
            onClick={e => { e.stopPropagation(); onCopy(content) }}
            title="Copy to clipboard"
            style={{ fontSize: 12, background: "none", border: `1px solid ${T.border}`, borderRadius: 5, padding: "2px 6px", cursor: "pointer", color: T.soft }}
          >
            📋
          </button>
        )}
        {content && (
          <span style={{ fontSize: 11, color: T.soft }}>{expanded ? "▲" : "▼"}</span>
        )}
      </div>
      {expanded && content && (
        <div style={{
          padding: "14px 16px", borderTop: `1px solid ${T.border}`,
          background: "#fff", maxHeight: 520, overflowY: "auto",
        }}>
          {renderMd(content)}
        </div>
      )}
    </div>
  )
}

function RecentAuditRow({ audit, onLoad }) {
  const statusColor = { running: T.amber, paused: T.purple, stopped: T.red, done: T.green, error: T.red }
  const label = TARGETS.find(t => t.id === audit.target)?.label || audit.target
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
      border: `1px solid ${T.border}`, borderRadius: 8, marginBottom: 6,
      background: "#fff",
    }}>
      <div style={{
        width: 8, height: 8, borderRadius: "50%",
        background: statusColor[audit.status] || T.soft, flexShrink: 0,
      }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{label}</div>
        <div style={{ fontSize: 11, color: T.soft }}>
          {audit.status.toUpperCase()} · {audit.created_at?.slice(0, 16).replace("T", " ")}
        </div>
      </div>
      <button
        onClick={() => onLoad(audit.audit_id)}
        style={{
          fontSize: 11, fontWeight: 600, padding: "4px 10px", borderRadius: 6,
          border: `1px solid ${T.blue}`, background: T.blue + "0d", color: T.blue,
          cursor: "pointer",
        }}
      >
        {["running", "paused"].includes(audit.status) ? "Reconnect" : "View"}
      </button>
    </div>
  )
}

// ── Elapsed timer hook ────────────────────────────────────────────────────────
function useElapsed(active) {
  const [secs, setSecs] = useState(0)
  const ref = useRef(null)
  useEffect(() => {
    if (active) {
      setSecs(0)
      ref.current = setInterval(() => setSecs(s => s + 1), 1000)
    } else {
      clearInterval(ref.current)
    }
    return () => clearInterval(ref.current)
  }, [active])
  if (!active && secs === 0) return null
  const m = Math.floor(secs / 60), s = secs % 60
  return `${m}m ${s.toString().padStart(2, "0")}s`
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AuditPage() {
  const { token } = useStore()
  // Use ref so closures (connectStream, loadAudit) always read the current token
  const authHeader = useCallback(() => tokenRef.current ? { Authorization: `Bearer ${tokenRef.current}` } : {}, [])

  // Config (only editable before starting)
  const [target,        setTarget]       = useState("phase1")
  const [model,         setModel]        = useState("ollama/mistral:7b-instruct-q4_K_M")
  const [selectedSteps, setSelectedSteps]= useState(new Set([0,1,2,3,4,5,6,7,8]))

  // Active audit
  const [auditId,     setAuditId]     = useState(null)
  const [auditStatus, setAuditStatus] = useState(null)  // running|paused|stopped|done|error
  const [currentStep, setCurrentStep] = useState(-1)
  const [stepStatus,  setStepStatus]  = useState({})    // { stepId: "idle"|"running"|"done"|"error" }
  const [stepContent, setStepContent] = useState({})    // { stepId: string }
  const [expanded,    setExpanded]    = useState({})
  const [folder,      setFolder]      = useState(null)
  const [error,       setError]       = useState(null)
  const [copied,      setCopied]      = useState(false)

  // Recent audits panel
  const [recentAudits, setRecentAudits] = useState([])
  const [showRecent,   setShowRecent]   = useState(false)

  const streamRef    = useRef(null)   // AbortController for SSE
  const copiedTimer   = useRef(null)   // setTimeout handle for copy flash
  const tokenRef      = useRef(token)  // always-current token for closures
  useEffect(() => { tokenRef.current = token }, [token])

  // Abort stream on unmount to prevent state updates on dead component
  useEffect(() => () => {
    if (streamRef.current) streamRef.current.abort()
    clearTimeout(copiedTimer.current)
  }, [])

  const elapsed = useElapsed(auditStatus === "running")

  // ── Helpers ──────────────────────────────────────────────────────────────

  function applyAuditRow(data) {
    setAuditId(data.audit_id)
    setAuditStatus(data.status)
    setCurrentStep(data.current_step ?? -1)
    setFolder(data.folder || null)

    // completed_steps may be a JSON string (from SQLite) or already parsed object
    let cs = data.completed_steps
    if (typeof cs === "string") { try { cs = JSON.parse(cs) } catch (_) { cs = null } }

    if (cs && typeof cs === "object") {
      const ss = {}, sc = {}
      for (const [sid, content] of Object.entries(cs)) {
        const id = Number(sid)
        const isErr = typeof content === "string" && content.startsWith("__error__:")
        ss[id] = isErr ? "error" : "done"
        sc[id] = content
      }
      setStepStatus(ss)
      setStepContent(sc)
      // Auto-expand errors
      const errExpand = {}
      for (const [id, st] of Object.entries(ss)) {
        if (st === "error") errExpand[Number(id)] = true
      }
      if (Object.keys(errExpand).length) setExpanded(e => ({ ...e, ...errExpand }))
    }
  }

  function connectStream(aid) {
    if (streamRef.current) streamRef.current.abort()
    const ctrl = new AbortController()
    streamRef.current = ctrl

    fetch(`${API}/api/audit/code/${aid}/stream`, { headers: authHeader(), signal: ctrl.signal })
      .then(async res => {
        if (!res.ok) {
          setError(`Stream connect failed (${res.status}). Refresh or click Resume.`)
          return
        }
        const reader = res.body.getReader()
        const dec = new TextDecoder()
        let buf = ""
        let receivedTerminal = false
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += dec.decode(value, { stream: true })
          const lines = buf.split("\n")
          buf = lines.pop()
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue
            try {
              const evt = JSON.parse(line.slice(6))
              if (evt.type === "step_start") {
                setCurrentStep(evt.step)
                setStepStatus(s => ({ ...s, [evt.step]: "running" }))
                setExpanded(e => ({ ...e, [evt.step]: false }))
              }
              if (evt.type === "step_done") {
                setCurrentStep(c => c === evt.step ? -1 : c)
                setStepStatus(s => ({ ...s, [evt.step]: "done" }))
                setStepContent(c => ({ ...c, [evt.step]: evt.content }))
                if (!evt.replayed) setExpanded(e => ({ ...e, [evt.step]: false }))
              }
              if (evt.type === "step_error") {
                setStepStatus(s => ({ ...s, [evt.step]: "error" }))
                setStepContent(c => ({ ...c, [evt.step]: evt.content || evt.error || "Unknown error" }))
                setExpanded(e => ({ ...e, [evt.step]: true }))
              }
              if (evt.type === "paused") {
                setAuditStatus("paused")
                receivedTerminal = true
              }
              if (["done", "stopped", "error"].includes(evt.type)) {
                setAuditStatus(evt.type)
                setCurrentStep(-1)
                receivedTerminal = true
              }
            } catch (_) {}
          }
        }
        // Stream ended without a terminal event = unexpected disconnect (not abort)
        if (!receivedTerminal && !ctrl.signal.aborted) {
          setError("Stream disconnected unexpectedly. Click Resume to reconnect.")
          setAuditStatus(s => s === "running" ? "paused" : s)
        }
      })
      .catch(err => {
        // AbortError = intentional (navigation / newAudit / component unmount) — ignore
        if (err?.name !== "AbortError") {
          setError("Stream connection error. Click Resume to reconnect.")
          setAuditStatus(s => s === "running" ? "paused" : s)
        }
      })
  }

  // ── On mount: restore last audit ─────────────────────────────────────────

  useEffect(() => {
    const saved = localStorage.getItem(LS_KEY)
    if (saved) loadAudit(saved)
  }, [])

  async function loadAudit(aid) {
    try {
      const res = await fetch(`${API}/api/audit/code/${aid}`, { headers: authHeader() })
      if (!res.ok) { localStorage.removeItem(LS_KEY); return }
      const data = await res.json()
      applyAuditRow(data)
      if (["running", "paused"].includes(data.status)) connectStream(aid)
      localStorage.setItem(LS_KEY, aid)
    } catch (_) {}
  }

  async function loadRecent() {
    try {
      const res = await fetch(`${API}/api/audit/code?limit=10`, { headers: authHeader() })
      if (res.ok) setRecentAudits(await res.json())
    } catch (_) {}
    setShowRecent(true)
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  async function startAudit() {
    setError(null)
    const body = { target, model, steps: [...selectedSteps].sort((a, b) => a - b) }
    try {
      const res = await fetch(`${API}/api/audit/code/start`, {
        method: "POST",
        headers: { ...authHeader(), "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (!res.ok) { setError(`Start failed: ${await res.text()}`); return }
      const data = await res.json()
      const aid = data.audit_id
      localStorage.setItem(LS_KEY, aid)
      setAuditId(aid)
      setAuditStatus("running")
      setCurrentStep(-1)
      setStepStatus({})
      setStepContent({})
      setExpanded({})
      setFolder(null)
      connectStream(aid)
    } catch (e) { setError(String(e)) }
  }

  async function pauseAudit() {
    if (!auditId) return
    await fetch(`${API}/api/audit/code/${auditId}/pause`, { method: "POST", headers: authHeader() })
    setAuditStatus("paused")
  }

  async function resumeAudit() {
    if (!auditId) return
    await fetch(`${API}/api/audit/code/${auditId}/resume`, { method: "POST", headers: authHeader() })
    setAuditStatus("running")
    connectStream(auditId)
  }

  async function stopAudit() {
    if (!auditId) return
    await fetch(`${API}/api/audit/code/${auditId}/stop`, { method: "POST", headers: authHeader() })
    setAuditStatus("stopped")
    setCurrentStep(-1)
    if (streamRef.current) streamRef.current.abort()
  }

  function newAudit() {
    if (streamRef.current) streamRef.current.abort()
    setAuditId(null); setAuditStatus(null); setCurrentStep(-1)
    setStepStatus({}); setStepContent({}); setExpanded({})
    setFolder(null); setError(null)
    localStorage.removeItem(LS_KEY)
  }

  function toggleStep(id) {
    if (auditId) return
    setSelectedSteps(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s })
  }

  function toggleExpand(id) {
    setExpanded(e => ({ ...e, [id]: !e[id] }))
  }

  function expandAll() {
    const ex = {}
    stepsToShow.forEach(s => { if (stepContent[s.id]) ex[s.id] = true })
    setExpanded(ex)
  }

  function collapseAll() { setExpanded({}) }

  async function copyStep(text) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      clearTimeout(copiedTimer.current)
      copiedTimer.current = setTimeout(() => setCopied(false), 1500)
    } catch (_) {}
  }

  // ── Derived state ─────────────────────────────────────────────────────────

  const isActive     = auditStatus === "running"
  const isPaused     = auditStatus === "paused"
  const isStopped    = ["stopped", "error"].includes(auditStatus)
  const isDone       = auditStatus === "done"
  const hasAudit     = !!auditId
  const configLocked = hasAudit && !isDone && !isStopped

  const doneCount = Object.values(stepStatus).filter(s => s === "done").length
  const stepCount = Object.values(stepStatus).length

  const stepsToShow = hasAudit
    ? ALL_STEPS.filter(s => selectedSteps.has(s.id) || stepStatus[s.id] !== undefined)
    : ALL_STEPS.filter(s => selectedSteps.has(s.id))

  // Progress bar percentage
  const totalSelected = hasAudit ? stepsToShow.length : selectedSteps.size
  const progressPct = totalSelected > 0 ? Math.round((doneCount / totalSelected) * 100) : 0

  const hasContent = stepsToShow.some(s => stepContent[s.id])

  return (
    <div style={{ maxWidth: 960, margin: "0 auto" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 20, flexWrap: "wrap", gap: 12,
      }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: T.text, margin: 0 }}>🔬 Code Audit</h1>
          <p style={{ fontSize: 13, color: T.soft, margin: "4px 0 0" }}>
            Multi-step AI audit · runs in background · refresh-safe · results saved to server
          </p>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button onClick={loadRecent}
            style={{ padding: "7px 14px", borderRadius: 8, border: `1px solid ${T.border}`, background: "#fff", color: T.soft, fontWeight: 600, fontSize: 12, cursor: "pointer" }}>
            📋 Recent
          </button>

          {hasAudit && !isDone && !isStopped && (
            <>
              {isActive && (
                <button onClick={pauseAudit} style={{ padding: "8px 16px", borderRadius: 8, border: `1px solid ${T.amber}`, background: T.amber + "0d", color: T.amber, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
                  ⏸ Pause
                </button>
              )}
              {isPaused && (
                <button onClick={resumeAudit} style={{ padding: "8px 16px", borderRadius: 8, border: `1px solid ${T.green}`, background: T.green + "0d", color: T.green, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
                  ▶ Resume
                </button>
              )}
              <button onClick={stopAudit} style={{ padding: "8px 16px", borderRadius: 8, border: `1px solid ${T.red}`, background: T.red + "0d", color: T.red, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
                ■ Stop
              </button>
            </>
          )}

          {isStopped && (
            <button onClick={resumeAudit} style={{ padding: "9px 18px", borderRadius: 8, border: `1px solid ${T.blue}`, background: T.blue + "0d", color: T.blue, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
              ▶ Resume from step {currentStep >= 0 ? currentStep : "last"}
            </button>
          )}

          {hasAudit ? (
            <button onClick={newAudit} style={{ padding: "9px 18px", borderRadius: 8, border: `1px solid ${T.border}`, background: "#fff", color: T.soft, fontWeight: 600, fontSize: 13, cursor: "pointer" }}>
              + New Audit
            </button>
          ) : (
            <button onClick={startAudit} disabled={selectedSteps.size === 0}
              style={{ padding: "10px 24px", borderRadius: 8, border: "none", background: selectedSteps.size === 0 ? "#9ca3af" : T.blue, color: "#fff", fontWeight: 700, fontSize: 14, cursor: selectedSteps.size === 0 ? "not-allowed" : "pointer" }}>
              ▶ Run Audit
            </button>
          )}
        </div>
      </div>

      {/* Status bar */}
      {hasAudit && (
        <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: "10px 16px", marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", fontSize: 13, marginBottom: progressPct > 0 ? 10 : 0 }}>
            <span style={{ fontWeight: 700, color: { running: T.amber, paused: T.purple, stopped: T.red, done: T.green, error: T.red }[auditStatus] || T.soft }}>
              {{ running: "⏳ Running", paused: "⏸ Paused", stopped: "■ Stopped", done: "✅ Done", error: "❌ Error" }[auditStatus] || auditStatus}
            </span>
            <span style={{ color: T.soft }}>·</span>
            <span style={{ fontWeight: 600 }}>{doneCount} / {stepCount || selectedSteps.size} steps done</span>
            {elapsed && <><span style={{ color: T.soft }}>·</span><span style={{ color: T.soft }}>⏱ {elapsed}</span></>}
            {copied && <span style={{ color: T.green, fontSize: 11 }}>✓ Copied!</span>}
            <span style={{ color: T.soft }}>·</span>
            <span style={{ fontFamily: "monospace", fontSize: 11, color: T.soft }}>{auditId}</span>
            {folder && <><span style={{ color: T.soft }}>·</span><span style={{ fontSize: 11, color: T.green }}>saved → {folder}/</span></>}
          </div>
          {/* Progress bar */}
          {(isActive || isDone || isPaused) && (
            <div style={{ height: 6, background: T.border, borderRadius: 4, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${progressPct}%`, background: isDone ? T.green : T.amber, borderRadius: 4, transition: "width 0.4s ease" }} />
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ background: "#fef2f2", border: `1px solid #fca5a5`, borderRadius: 8, padding: "12px 16px", color: T.red, fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* Recent audits panel */}
      {showRecent && (
        <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 16, marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>📋 Recent Audits</span>
            <button onClick={() => setShowRecent(false)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, color: T.soft }}>✕</button>
          </div>
          {recentAudits.length === 0
            ? <div style={{ color: T.soft, fontSize: 13 }}>No recent audits found.</div>
            : recentAudits.map(a => <RecentAuditRow key={a.audit_id} audit={a} onLoad={aid => { loadAudit(aid); setShowRecent(false) }} />)
          }
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
        {/* Target selector */}
        <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 12 }}>📁 Select Target</div>
          {TARGETS.map(t => (
            <SelectCard key={t.id} item={t} selected={target === t.id} onSelect={setTarget} disabled={configLocked}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 18 }}>{t.icon}</span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{t.label}</div>
                  <div style={{ fontSize: 11, color: T.soft }}>{t.desc}</div>
                </div>
              </div>
            </SelectCard>
          ))}
        </div>

        {/* Model selector */}
        <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 12 }}>🤖 Select AI Model</div>
          {MODELS.map(m => (
            <SelectCard key={m.id} item={m} selected={model === m.id} onSelect={setModel} disabled={configLocked}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{m.label}</div>
                <span style={{ fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 10, background: m.color + "18", color: m.color, border: `1px solid ${m.color}33` }}>{m.badge}</span>
              </div>
              <div style={{ fontSize: 11, color: T.soft, marginTop: 2, fontFamily: "monospace" }}>{m.id}</div>
            </SelectCard>
          ))}
          <div style={{ marginTop: 12, padding: "10px 12px", background: T.bg, borderRadius: 8, fontSize: 11, color: T.soft }}>
            <strong>Rate limit:</strong> 1 audit at a time · 5s between steps (slow AI mode)<br/>
            Steps take 3–10 min each on remote Ollama. Runs in background — safe to leave.
          </div>
        </div>
      </div>

      {/* Step selector */}
      <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 16, marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>⚙️ Audit Steps</div>
          {!configLocked
            ? <div style={{ display: "flex", gap: 8 }}>
                <button onClick={() => setSelectedSteps(new Set(ALL_STEPS.map(s => s.id)))} style={{ fontSize: 11, color: T.blue, background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}>Select All</button>
                <button onClick={() => setSelectedSteps(new Set())} style={{ fontSize: 11, color: T.soft, background: "none", border: "none", cursor: "pointer" }}>Clear</button>
              </div>
            : <span style={{ fontSize: 11, color: T.soft }}>locked while running</span>
          }
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8 }}>
          {ALL_STEPS.map(s => {
            const sel = selectedSteps.has(s.id)
            const st  = stepStatus[s.id]
            const dotColor = st === "done" ? T.green : st === "error" ? T.red : st === "running" ? T.amber : undefined
            return (
              <button key={s.id} onClick={() => toggleStep(s.id)} style={{
                padding: "8px 10px", borderRadius: 8, textAlign: "left",
                border: `1.5px solid ${dotColor || (sel ? T.blue : T.border)}`,
                background: dotColor ? dotColor + "10" : sel ? T.blue + "0d" : "#fff",
                cursor: configLocked ? "default" : "pointer",
                display: "flex", alignItems: "center", gap: 6,
              }}>
                <span style={{ fontSize: 14 }}>{s.icon}</span>
                <span style={{ fontSize: 12, fontWeight: sel ? 600 : 400, color: dotColor || (sel ? T.blue : T.text) }}>{s.name}</span>
                {st === "done"    && <span style={{ marginLeft: "auto", fontSize: 10 }}>✅</span>}
                {st === "running" && <span style={{ marginLeft: "auto", fontSize: 10 }}>⏳</span>}
                {st === "error"   && <span style={{ marginLeft: "auto", fontSize: 10 }}>❌</span>}
              </button>
            )
          })}
        </div>
      </div>

      {/* Steps progress */}
      {stepsToShow.length > 0 && (
        <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>
              📊 Progress — {doneCount}/{stepsToShow.length} steps done
              {isActive && currentStep >= 0 && (
                <span style={{ marginLeft: 10, fontWeight: 400, fontSize: 12, color: T.amber }}>
                  ⏳ {ALL_STEPS.find(s => s.id === currentStep)?.name}
                </span>
              )}
              {isPaused && (
                <span style={{ marginLeft: 10, fontWeight: 400, fontSize: 12, color: T.purple }}>⏸ Paused</span>
              )}
              {isDone && (
                <span style={{ marginLeft: 10, fontWeight: 400, fontSize: 12, color: T.green }}>✅ Complete</span>
              )}
            </div>
            {hasContent && (
              <div style={{ display: "flex", gap: 6 }}>
                <button onClick={expandAll}   style={{ fontSize: 11, color: T.blue, background: "none", border: `1px solid ${T.border}`, borderRadius: 5, padding: "3px 8px", cursor: "pointer" }}>Expand All</button>
                <button onClick={collapseAll} style={{ fontSize: 11, color: T.soft, background: "none", border: `1px solid ${T.border}`, borderRadius: 5, padding: "3px 8px", cursor: "pointer" }}>Collapse All</button>
              </div>
            )}
          </div>
          {stepsToShow.map(s => (
            <StepRow
              key={s.id}
              step={s}
              status={stepStatus[s.id] || "idle"}
              content={stepContent[s.id]}
              expanded={!!expanded[s.id]}
              onToggle={() => toggleExpand(s.id)}
              onCopy={copyStep}
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!hasAudit && stepsToShow.length === 0 && (
        <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 60, textAlign: "center", color: T.soft, fontSize: 14 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🔬</div>
          Select a <strong>target</strong> and <strong>model</strong>, then click <strong>▶ Run Audit</strong>.<br/>
          <span style={{ fontSize: 12, marginTop: 8, display: "block" }}>
            Audit runs in the background — refresh-safe. Results saved to <code>audits/</code> on the server.
          </span>
        </div>
      )}
    </div>
  )
}
