import { useState } from "react"
import { T } from "../App"

function fmtCost(usd) {
  if (usd === null || usd === undefined) return "—"
  if (usd === 0) return "$0.00 (free)"
  if (usd < 0.001) return `$${(usd * 100).toFixed(4)}¢`
  return `$${usd.toFixed(4)}`
}

function fmtDuration(secs) {
  if (!secs && secs !== 0) return "—"
  if (secs < 60) return `${Math.round(secs)}s`
  const m = Math.floor(secs / 60)
  const s = Math.round(secs % 60)
  return s > 0 ? `${m}m ${s}s` : `${m}m`
}

function fmtTokens(n) {
  if (!n) return "0"
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

const AI_OPTIONS = [
  { value: "groq",            label: "Groq Llama",   desc: "Free · fastest",     color: "#f59e0b" },
  { value: "gemini_free",     label: "Gemini Free",  desc: "Free tier",           color: "#1a73e8" },
  { value: "or_gemini_flash", label: "Gemini Flash", desc: "OpenRouter · free",   color: "#4285f4" },
  { value: "or_deepseek",     label: "DeepSeek",     desc: "OpenRouter · free",   color: "#7c3aed" },
  { value: "gemini_paid",     label: "Gemini Paid",  desc: "Paid · high quality", color: "#0f9d58" },
  { value: "anthropic",       label: "Claude Haiku", desc: "Paid · reliable",     color: "#5b21b6" },
  { value: "anthropic_paid",  label: "Claude Sonnet",desc: "Paid · best",         color: "#4c1d95" },
  { value: "openai_paid",     label: "GPT-4o",       desc: "Paid",                color: "#10a37f" },
  { value: "ollama",          label: "Ollama Local", desc: "Local server",        color: "#6b7280" },
]

const STEP_KEYS = ["research","structure","verify","links","references","draft","review","issues","humanize","score","quality_loop","redevelop"]

function buildRouting(model) {
  return Object.fromEntries(STEP_KEYS.map(k => [k, { first: model, second: "groq", third: "gemini_free" }]))
}

function StatCard({ label, value, sub, accent }) {
  return (
    <div style={{
      flex: 1, minWidth: 0, padding: "12px 14px", borderRadius: 10,
      background: accent ? `${accent}12` : "#F5F5F7",
      border: `1px solid ${accent ? `${accent}30` : T.border}`,
    }}>
      <div style={{ fontSize: 10, color: T.textSoft, fontWeight: 500, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: accent || T.text, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

function LogLine({ entry }) {
  const isError = entry.level === "error"
  const color = isError ? "#ef4444" : "#f59e0b"
  const ts = entry.ts ? new Date(entry.ts).toLocaleTimeString() : ""
  return (
    <div style={{
      display: "flex", gap: 8, alignItems: "flex-start",
      padding: "5px 0", borderBottom: "1px solid #1e2028",
      fontSize: 11, lineHeight: 1.5, color: "#c9d1d9",
    }}>
      <span style={{ color, flexShrink: 0, fontWeight: 700, fontSize: 10, marginTop: 1 }}>{isError ? "✕" : "⚠"}</span>
      {ts && <span style={{ color: "#6e7681", flexShrink: 0, fontSize: 10, marginTop: 1, whiteSpace: "nowrap" }}>{ts}</span>}
      {entry.step != null && (
        <span style={{ color: "#8b949e", flexShrink: 0, fontSize: 9, marginTop: 1, background: "#21262d", padding: "1px 5px", borderRadius: 4, whiteSpace: "nowrap" }}>
          S{entry.step}
        </span>
      )}
      <span style={{ wordBreak: "break-word", flex: 1 }}>{entry.msg}</span>
    </div>
  )
}

function ModelPicker({ selected, onSelect }) {
  return (
    <div style={{ padding: "0 20px 16px" }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>
        Choose AI Model (applied to all steps)
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
        {AI_OPTIONS.map(opt => {
          const isSel = selected === opt.value
          return (
            <button key={opt.value} onClick={() => onSelect(opt.value)} style={{
              padding: "8px 10px", borderRadius: 8, cursor: "pointer", textAlign: "left",
              border: `2px solid ${isSel ? opt.color : T.border}`,
              background: isSel ? `${opt.color}12` : "#FAFAFA",
              transition: "all 0.1s",
            }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: isSel ? opt.color : T.text }}>{opt.label}</div>
              <div style={{ fontSize: 9, color: T.textSoft, marginTop: 1 }}>{opt.desc}</div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default function GenerationSummaryModal({ summary, onClose, onRestart, restarting }) {
  const [showModelPicker, setShowModelPicker] = useState(false)
  const [selectedModel, setSelectedModel] = useState(null)

  if (!summary) return null

  const failed = summary.status === "failed" || summary.status === "needs_review"
  const headerColor = failed ? "#dc2626" : "#16a34a"
  const failedStep = (summary.step_timings || []).find(s => s.status === "error")
  const errorLogs = summary.error_logs || []
  const warnLogs  = summary.warning_logs || []
  const allLogs   = [...errorLogs, ...warnLogs].sort((a, b) => (a.ts || "").localeCompare(b.ts || ""))

  function handleRestart(model) {
    onRestart?.({ routing: model ? buildRouting(model) : null, model })
    setShowModelPicker(false)
  }

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, zIndex: 9999,
      background: "rgba(0,0,0,0.5)",
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: 16,
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: "100%", maxWidth: 600, maxHeight: "92vh",
        background: "#fff", borderRadius: 14,
        boxShadow: "0 24px 64px rgba(0,0,0,0.3)",
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}>

        {/* Header */}
        <div style={{
          padding: "16px 20px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", gap: 10,
          background: failed ? "#fff5f5" : "#f0fdf4",
        }}>
          <span style={{
            width: 32, height: 32, borderRadius: "50%", background: `${headerColor}20`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 16, color: headerColor, fontWeight: 700, flexShrink: 0,
          }}>{failed ? "✕" : "✓"}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: headerColor }}>
              {failed ? "Generation Failed" : "Generation Complete"}
            </div>
            <div style={{ fontSize: 11, color: T.textSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginTop: 1 }}>
              {summary.keyword}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: "none", border: "none", cursor: "pointer",
            fontSize: 18, color: T.textSoft, padding: "2px 6px", borderRadius: 4, flexShrink: 0,
          }}>✕</button>
        </div>

        {/* Body */}
        <div style={{ overflowY: "auto", flex: 1 }}>

          {/* Failed step banner */}
          {failed && failedStep && (
            <div style={{
              margin: "16px 20px 0", padding: "12px 14px",
              borderRadius: 10, background: "#fef2f2", border: "1px solid #fecaca",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: failedStep.summary ? 6 : 0 }}>
                <span style={{ fontSize: 13, color: "#dc2626", fontWeight: 700 }}>
                  Failed at Step {failedStep.step}: {failedStep.name}
                </span>
                {failedStep.ai_first && (
                  <span style={{
                    marginLeft: "auto", fontSize: 10, color: "#7f1d1d",
                    background: "#fecaca", padding: "2px 7px", borderRadius: 4, whiteSpace: "nowrap",
                  }}>via {failedStep.ai_first}</span>
                )}
              </div>
              {failedStep.summary && (
                <div style={{
                  fontSize: 11, color: "#7f1d1d", lineHeight: 1.6,
                  fontFamily: "monospace", wordBreak: "break-word",
                  paddingTop: 6, borderTop: "1px solid #fecaca",
                }}>
                  {failedStep.summary}
                </div>
              )}
            </div>
          )}

          {/* Stats */}
          <div style={{ padding: "16px 20px", display: "flex", gap: 10 }}>
            <StatCard label="Total Cost" value={fmtCost(summary.total_cost_usd)} accent={summary.total_cost_usd > 0 ? "#6366f1" : T.teal} />
            <StatCard label="Time Taken" value={fmtDuration(summary.total_duration_seconds)} accent="#0891b2" />
            <StatCard label="AI Calls" value={summary.total_calls ?? "—"} sub={`${summary.models_used ?? 0} model${summary.models_used !== 1 ? "s" : ""}`} accent="#7c3aed" />
          </div>

          {/* Step timeline */}
          {(summary.step_timings || []).length > 0 && (
            <div style={{ padding: "0 20px 16px" }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
                Step Timeline
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                {summary.step_timings.map((s, i) => {
                  const isErr = s.status === "error"
                  const isDone = s.status === "done"
                  return (
                    <div key={i} title={s.summary || s.name} style={{
                      padding: "4px 8px", borderRadius: 6, fontSize: 10, cursor: s.summary ? "help" : "default",
                      background: isErr ? "#fef2f2" : isDone ? "#f0fdf4" : s.status === "pending" ? "transparent" : "#F5F5F7",
                      border: `1px solid ${isErr ? "#fecaca" : isDone ? "#bbf7d0" : T.border}`,
                      color: isErr ? "#dc2626" : isDone ? "#16a34a" : T.textSoft,
                    }}>
                      <span style={{ fontWeight: 700 }}>S{s.step}</span>
                      {" "}{s.name}
                      {s.duration_seconds != null && <span style={{ marginLeft: 4, opacity: 0.7 }}>{fmtDuration(s.duration_seconds)}</span>}
                      {isErr && <span style={{ marginLeft: 4 }}>✕</span>}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* AI calls per model */}
          {(summary.by_model || []).length > 0 && (
            <div style={{ padding: "0 20px 16px" }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
                AI Calls per Model
              </div>
              <div style={{ borderRadius: 8, border: `1px solid ${T.border}`, overflow: "hidden" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                  <thead>
                    <tr style={{ background: "#F5F5F7" }}>
                      {["Model","Provider","Calls","Tokens","Cost"].map(h => (
                        <th key={h} style={{
                          padding: "6px 10px", textAlign: ["Calls","Tokens","Cost"].includes(h) ? "right" : "left",
                          fontWeight: 600, color: T.textSoft, fontSize: 10,
                          borderBottom: `1px solid ${T.border}`,
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {summary.by_model.map((row, i) => (
                      <tr key={i} style={{ borderBottom: i < summary.by_model.length - 1 ? `1px solid ${T.border}` : "none" }}>
                        <td style={{ padding: "6px 10px", fontWeight: 500, color: T.text, fontFamily: "monospace", fontSize: 10 }}>{row.model}</td>
                        <td style={{ padding: "6px 10px", color: T.textSoft }}>{row.provider}</td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: T.text }}>{row.calls}</td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: T.textSoft }}>{fmtTokens((row.input_tokens||0)+(row.output_tokens||0))}</td>
                        <td style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600, color: row.cost_usd > 0 ? "#6366f1" : T.teal }}>{fmtCost(row.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Console error report */}
          {allLogs.length > 0 && (
            <div style={{ padding: "0 20px 16px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Console Report
                </span>
                {errorLogs.length > 0 && (
                  <span style={{ fontSize: 10, background: "#fef2f2", color: "#dc2626", border: "1px solid #fecaca", borderRadius: 99, padding: "1px 7px", fontWeight: 600 }}>
                    {errorLogs.length} error{errorLogs.length !== 1 ? "s" : ""}
                  </span>
                )}
                {warnLogs.length > 0 && (
                  <span style={{ fontSize: 10, background: "#fffbeb", color: "#d97706", border: "1px solid #fde68a", borderRadius: 99, padding: "1px 7px", fontWeight: 600 }}>
                    {warnLogs.length} warning{warnLogs.length !== 1 ? "s" : ""}
                  </span>
                )}
                <button
                  onClick={() => {
                    const text = allLogs.map(e => `[${(e.level||"").toUpperCase()}] S${e.step??"?"} ${e.ts??""} — ${e.msg}`).join("\n")
                    navigator.clipboard?.writeText(text)
                  }}
                  style={{
                    marginLeft: "auto", fontSize: 10, padding: "2px 8px", borderRadius: 5,
                    border: `1px solid ${T.border}`, background: "transparent",
                    cursor: "pointer", color: T.textSoft,
                  }}
                >Copy</button>
              </div>
              <div style={{ background: "#0d1117", borderRadius: 8, padding: "10px 12px", maxHeight: 220, overflowY: "auto", fontFamily: "monospace" }}>
                {allLogs.map((entry, i) => <LogLine key={i} entry={entry} />)}
              </div>
            </div>
          )}

          {/* Model picker */}
          {showModelPicker && (
            <ModelPicker selected={selectedModel} onSelect={setSelectedModel} />
          )}

        </div>

        {/* Footer */}
        <div style={{
          padding: "14px 20px", borderTop: `1px solid ${T.border}`,
          display: "flex", gap: 8, alignItems: "center", background: "#FAFAFA",
        }}>
          {failed ? (
            <>
              <button onClick={onClose} style={{
                padding: "8px 16px", borderRadius: 8, fontSize: 12, fontWeight: 500,
                cursor: "pointer", border: `1px solid ${T.border}`,
                background: "transparent", color: T.textSoft,
              }}>Dismiss</button>

              <div style={{ flex: 1 }} />

              <button
                onClick={() => { setShowModelPicker(v => !v); setSelectedModel(null) }}
                style={{
                  padding: "8px 14px", borderRadius: 8, fontSize: 12, fontWeight: 500,
                  cursor: "pointer",
                  border: `1px solid ${showModelPicker ? "#6366f1" : T.border}`,
                  background: showModelPicker ? "#6366f110" : "transparent",
                  color: showModelPicker ? "#6366f1" : T.textSoft,
                }}
              >{showModelPicker ? "▾ Choose AI" : "▸ Change AI"}</button>

              {showModelPicker ? (
                <button
                  onClick={() => selectedModel && handleRestart(selectedModel)}
                  disabled={!selectedModel || restarting}
                  style={{
                    padding: "8px 16px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                    cursor: selectedModel && !restarting ? "pointer" : "not-allowed",
                    border: "none",
                    background: selectedModel ? "#6366f1" : "#e5e7eb",
                    color: selectedModel ? "#fff" : T.textSoft,
                    opacity: restarting ? 0.6 : 1,
                  }}
                >{restarting ? "Starting…" : "Restart with This AI"}</button>
              ) : (
                <button
                  onClick={() => handleRestart(null)}
                  disabled={restarting}
                  style={{
                    padding: "8px 16px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                    cursor: restarting ? "not-allowed" : "pointer",
                    border: "none", background: "#dc2626", color: "#fff",
                    opacity: restarting ? 0.6 : 1,
                  }}
                >{restarting ? "Starting…" : "Restart Same AI"}</button>
              )}
            </>
          ) : (
            <button onClick={onClose} style={{
              marginLeft: "auto", padding: "8px 24px", borderRadius: 8,
              fontSize: 12, fontWeight: 600, cursor: "pointer",
              border: "none", background: "#16a34a", color: "#fff",
            }}>Dismiss</button>
          )}
        </div>
      </div>
    </div>
  )
}
