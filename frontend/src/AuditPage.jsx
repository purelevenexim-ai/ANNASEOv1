/**
 * AuditPage — Multi-step code audit pipeline.
 * Select a page/target and an AI model, run sequential analysis,
 * view per-step results, and save report to audits/ folder.
 */
import { useState } from "react"
import { useStore } from "./App"

const API = import.meta.env.VITE_API_URL || ""

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
  { id: "ollama/mistral:7b-instruct-q4_K_M", label: "Ollama — Mistral 7B",      provider: "ollama", badge: "local · free",  color: T.teal   },
  { id: "ollama/llama3:8b",                  label: "Ollama — Llama 3 8B",       provider: "ollama", badge: "local · free",  color: T.teal   },
  { id: "ollama/deepseek-coder:7b",           label: "Ollama — DeepSeek Coder",   provider: "ollama", badge: "local · free",  color: T.teal   },
  { id: "gemini-flash",                       label: "Gemini 1.5 Flash",          provider: "gemini", badge: "cloud · free",  color: T.blue   },
]

const ALL_STEPS = [
  { id: 0, name: "Context Builder",   icon: "🗺️", desc: "Summarize system structure" },
  { id: 1, name: "Code Understanding",icon: "🔍", desc: "Trace execution + assumptions" },
  { id: 2, name: "Bug Analysis",      icon: "🐛", desc: "Functional bugs + edge cases" },
  { id: 3, name: "Data Flow",         icon: "🔄", desc: "Trace transformations + leaks" },
  { id: 4, name: "Performance",       icon: "⚡", desc: "Bottlenecks + async ops" },
  { id: 5, name: "AI Usage",          icon: "🤖", desc: "Optimize / reduce AI calls" },
  { id: 6, name: "Test Generator",    icon: "🧪", desc: "Unit, integration, regression tests" },
  { id: 7, name: "Fix Engine",        icon: "🔧", desc: "Rewrite problem sections" },
  { id: 8, name: "Final Report",      icon: "📋", desc: "P0/P1/P2/P3 fix roadmap" },
]

// ── Small components ──────────────────────────────────────────────────────────

function SelectCard({ item, selected, onSelect, children }) {
  return (
    <button
      onClick={() => onSelect(item.id)}
      style={{
        textAlign: "left", width: "100%", padding: "10px 14px",
        borderRadius: 9, border: `1.5px solid ${selected ? T.blue : T.border}`,
        background: selected ? T.blue + "0d" : "#fff",
        cursor: "pointer", transition: "border 0.1s, background 0.1s",
        marginBottom: 6,
      }}
    >
      {children}
    </button>
  )
}

function StepRow({ step, status, content, expanded, onToggle }) {
  const statusDot = {
    idle:    { color: T.border, label: "○" },
    running: { color: T.amber,  label: "⏳" },
    done:    { color: T.green,  label: "✅" },
    error:   { color: T.red,    label: "❌" },
  }[status] || { color: T.border, label: "○" }

  return (
    <div style={{
      border: `1px solid ${status === "error" ? T.red + "44" : T.border}`,
      borderLeft: `3px solid ${statusDot.color}`,
      borderRadius: 8, marginBottom: 8, overflow: "hidden",
    }}>
      <div
        onClick={content ? onToggle : undefined}
        style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "10px 14px",
          background: status === "running" ? T.amber + "08" : status === "done" ? T.green + "06" : "#fff",
          cursor: content ? "pointer" : "default",
        }}
      >
        <span style={{ fontSize: 16, width: 22, flexShrink: 0 }}>{step.icon}</span>
        <div style={{ flex: 1 }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{step.name}</span>
          <span style={{ fontSize: 11, color: T.soft, marginLeft: 8 }}>{step.desc}</span>
        </div>
        <span style={{ fontSize: 13 }}>{statusDot.label}</span>
        {content && (
          <span style={{ fontSize: 11, color: T.soft }}>{expanded ? "▲" : "▼"}</span>
        )}
      </div>
      {expanded && content && (
        <div style={{
          padding: "12px 14px", borderTop: `1px solid ${T.border}`,
          background: T.bg, fontSize: 12, lineHeight: 1.7,
          fontFamily: "monospace", whiteSpace: "pre-wrap", wordBreak: "break-word",
          maxHeight: 400, overflowY: "auto",
        }}>
          {content}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AuditPage() {
  const { token } = useStore()

  const [target,        setTarget]       = useState("phase1")
  const [model,         setModel]        = useState("ollama/mistral:7b-instruct-q4_K_M")
  const [selectedSteps, setSelectedSteps]= useState(new Set([0,1,2,3,4,5,6,7,8]))

  const [running,  setRunning]  = useState(false)
  const [queued,   setQueued]   = useState(false)
  const [stepStatus, setStepStatus] = useState({})   // { stepId: "idle"|"running"|"done"|"error" }
  const [stepContent, setStepContent] = useState({}) // { stepId: string }
  const [expanded,    setExpanded]    = useState({})  // { stepId: bool }
  const [folder,   setFolder]   = useState(null)
  const [error,    setError]    = useState(null)

  function toggleStep(id) {
    setSelectedSteps(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  function toggleExpand(id) {
    setExpanded(e => ({ ...e, [id]: !e[id] }))
  }

  function reset() {
    setStepStatus({})
    setStepContent({})
    setExpanded({})
    setFolder(null)
    setError(null)
    setQueued(false)
  }

  function startAudit() {
    if (running) return
    reset()
    setRunning(true)

    const stepsParam = [...selectedSteps].sort((a,b)=>a-b).join(",")
    const params = new URLSearchParams({ target, model, steps: stepsParam })
    const url = `${API}/api/audit/code/stream?${params}`

    const headers = token ? { Authorization: `Bearer ${token}` } : {}

    // Use fetch + ReadableStream (EventSource doesn't support custom headers)
    fetch(url, { headers })
      .then(async res => {
        if (!res.ok) {
          const t = await res.text()
          setError(`HTTP ${res.status}: ${t}`)
          setRunning(false)
          return
        }
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ""

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split("\n")
          buf = lines.pop()
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue
            try {
              const evt = JSON.parse(line.slice(6))
              if (evt.type === "queued")     { setQueued(true) }
              if (evt.type === "start")      { setQueued(false) }
              if (evt.type === "step_start") {
                setStepStatus(s => ({ ...s, [evt.step]: "running" }))
              }
              if (evt.type === "step_done") {
                setStepStatus(s => ({ ...s, [evt.step]: "done" }))
                setStepContent(c => ({ ...c, [evt.step]: evt.content }))
                setExpanded(e => ({ ...e, [evt.step]: false }))
              }
              if (evt.type === "step_error") {
                setStepStatus(s => ({ ...s, [evt.step]: "error" }))
                setStepContent(c => ({ ...c, [evt.step]: `Error: ${evt.error}` }))
              }
              if (evt.type === "done") {
                setFolder(evt.folder)
                setRunning(false)
              }
            } catch (_) {}
          }
        }
        setRunning(false)
      })
      .catch(e => { setError(String(e)); setRunning(false) })
  }

  function stopAudit() {
    setRunning(false)
  }

  const completedCount = Object.values(stepStatus).filter(s => s === "done").length

  return (
    <div style={{ maxWidth: 960, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: T.text, margin: 0 }}>🔬 Code Audit</h1>
          <p style={{ fontSize: 13, color: T.soft, margin: "4px 0 0" }}>
            Multi-step AI audit · select target · select model · results saved to file
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {running && (
            <button onClick={stopAudit} style={{
              padding: "9px 18px", borderRadius: 8, border: `1px solid ${T.red}`,
              background: T.red + "0d", color: T.red, fontWeight: 700, fontSize: 13, cursor: "pointer",
            }}>
              ■ Stop
            </button>
          )}
          <button
            onClick={running ? undefined : startAudit}
            disabled={running || selectedSteps.size === 0}
            style={{
              padding: "10px 24px", borderRadius: 8, border: "none",
              background: running ? "#9ca3af" : T.blue, color: "#fff",
              fontWeight: 700, fontSize: 14, cursor: (running || selectedSteps.size === 0) ? "not-allowed" : "pointer",
            }}
          >
            {running ? `⏳ Running… (${completedCount}/${selectedSteps.size})` : "▶ Run Audit"}
          </button>
        </div>
      </div>

      {/* Queued notice */}
      {queued && (
        <div style={{ background: T.amber + "18", border: `1px solid ${T.amber}44`, borderRadius: 8, padding: "10px 16px", fontSize: 13, color: T.amber, marginBottom: 16 }}>
          ⏳ Another audit is running — your audit is queued and will start automatically.
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ background: "#fef2f2", border: `1px solid #fca5a5`, borderRadius: 8, padding: "12px 16px", color: T.red, fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* Saved */}
      {folder && (
        <div style={{ background: "#f0fdf4", border: `1px solid #bbf7d0`, borderRadius: 8, padding: "10px 16px", fontSize: 13, color: "#15803d", marginBottom: 16 }}>
          ✅ Audit complete — saved to{" "}
          <code style={{ fontFamily: "monospace", fontSize: 12 }}>{folder}/</code>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
        {/* Target selector */}
        <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 12 }}>
            📁 Select Target
          </div>
          {TARGETS.map(t => (
            <SelectCard key={t.id} item={t} selected={target === t.id} onSelect={setTarget}>
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
          <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 12 }}>
            🤖 Select AI Model
          </div>
          {MODELS.map(m => (
            <SelectCard key={m.id} item={m} selected={model === m.id} onSelect={setModel}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{m.label}</div>
                <span style={{
                  fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 10,
                  background: m.color + "18", color: m.color, border: `1px solid ${m.color}33`,
                }}>{m.badge}</span>
              </div>
              <div style={{ fontSize: 11, color: T.soft, marginTop: 2, fontFamily: "monospace" }}>{m.id}</div>
            </SelectCard>
          ))}
          <div style={{ marginTop: 12, padding: "10px 12px", background: T.bg, borderRadius: 8, fontSize: 11, color: T.soft }}>
            <strong>Rate limit:</strong> 1 audit at a time · 1.5s between steps<br/>
            <strong>Claude</strong> is reserved for verification only (per project rules)
          </div>
        </div>
      </div>

      {/* Step selector */}
      <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 16, marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>⚙️ Audit Steps</div>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => setSelectedSteps(new Set(ALL_STEPS.map(s => s.id)))} style={{ fontSize: 11, color: T.blue, background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}>Select All</button>
            <button onClick={() => setSelectedSteps(new Set())} style={{ fontSize: 11, color: T.soft, background: "none", border: "none", cursor: "pointer" }}>Clear</button>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8 }}>
          {ALL_STEPS.map(s => {
            const sel = selectedSteps.has(s.id)
            return (
              <button key={s.id} onClick={() => toggleStep(s.id)} style={{
                padding: "8px 10px", borderRadius: 8, textAlign: "left",
                border: `1.5px solid ${sel ? T.blue : T.border}`,
                background: sel ? T.blue + "0d" : "#fff", cursor: "pointer",
              }}>
                <span style={{ fontSize: 14 }}>{s.icon}</span>
                <span style={{ fontSize: 12, fontWeight: sel ? 600 : 400, color: sel ? T.blue : T.text, marginLeft: 6 }}>{s.name}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Steps progress */}
      {Object.keys(stepStatus).length > 0 && (
        <div style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 14 }}>
            📊 Progress — {completedCount}/{selectedSteps.size} steps done
          </div>
          {ALL_STEPS.filter(s => selectedSteps.has(s.id)).map(s => (
            <StepRow
              key={s.id}
              step={s}
              status={stepStatus[s.id] || "idle"}
              content={stepContent[s.id]}
              expanded={!!expanded[s.id]}
              onToggle={() => toggleExpand(s.id)}
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!running && Object.keys(stepStatus).length === 0 && (
        <div style={{
          background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10,
          padding: 60, textAlign: "center", color: T.soft, fontSize: 14,
        }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🔬</div>
          Select a <strong>target</strong> and <strong>model</strong>, then click <strong>▶ Run Audit</strong>.<br/>
          <span style={{ fontSize: 12, marginTop: 8, display: "block" }}>
            Results are saved to <code>audits/{"{target}_{date}"}/</code> on the server.
          </span>
        </div>
      )}
    </div>
  )
}
