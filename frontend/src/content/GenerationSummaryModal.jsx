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

// ── Stat card ──────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, accent }) {
  return (
    <div style={{
      flex: 1, minWidth: 0,
      padding: "12px 14px",
      borderRadius: 10,
      background: accent ? `${accent}12` : "#F5F5F7",
      border: `1px solid ${accent ? `${accent}30` : T.border}`,
    }}>
      <div style={{ fontSize: 10, color: T.textSoft, fontWeight: 500, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: accent || T.text, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

// ── Log entry ──────────────────────────────────────────────────────────────────
function LogLine({ entry }) {
  const isError = entry.level === "error"
  const icon = isError ? "✕" : "⚠"
  const color = isError ? "#ef4444" : "#f59e0b"
  const ts = entry.ts ? new Date(entry.ts).toLocaleTimeString() : ""
  return (
    <div style={{
      display: "flex", gap: 8, alignItems: "flex-start",
      padding: "4px 0", borderBottom: "1px solid #1e2028",
      fontSize: 11, lineHeight: 1.5, color: "#c9d1d9",
    }}>
      <span style={{ color, flexShrink: 0, fontWeight: 700, fontSize: 10 }}>{icon}</span>
      {ts && <span style={{ color: "#6e7681", flexShrink: 0, fontSize: 10 }}>{ts}</span>}
      {entry.step != null && <span style={{ color: "#8b949e", flexShrink: 0, fontSize: 10 }}>S{entry.step}</span>}
      <span style={{ wordBreak: "break-word" }}>{entry.msg}</span>
    </div>
  )
}

// ── Main modal ─────────────────────────────────────────────────────────────────
export default function GenerationSummaryModal({ summary, onClose }) {
  if (!summary) return null

  const failed = summary.status === "failed"
  const headerColor = failed ? "#dc2626" : "#16a34a"
  const headerIcon = failed ? "✕" : "✓"
  const headerLabel = failed ? "Generation Failed" : "Generation Complete"

  const allLogs = [...(summary.error_logs || []), ...(summary.warning_logs || [])]
    .sort((a, b) => (a.ts || "").localeCompare(b.ts || ""))

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        background: "rgba(0,0,0,0.45)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: "100%", maxWidth: 560,
          maxHeight: "90vh",
          background: "#fff",
          borderRadius: 14,
          boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
          display: "flex", flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div style={{
          padding: "16px 20px",
          borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <span style={{
            width: 28, height: 28, borderRadius: "50%",
            background: `${headerColor}18`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14, color: headerColor, fontWeight: 700, flexShrink: 0,
          }}>{headerIcon}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: headerColor }}>{headerLabel}</div>
            <div style={{ fontSize: 11, color: T.textSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {summary.keyword}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none", border: "none", cursor: "pointer",
              fontSize: 16, color: T.textSoft, padding: "2px 6px", borderRadius: 4,
              flexShrink: 0,
            }}
          >✕</button>
        </div>

        {/* Scrollable body */}
        <div style={{ overflowY: "auto", flex: 1 }}>
          {/* Stats row */}
          <div style={{ padding: "16px 20px", display: "flex", gap: 10 }}>
            <StatCard
              label="Total Cost"
              value={fmtCost(summary.total_cost_usd)}
              accent={summary.total_cost_usd > 0 ? "#6366f1" : T.teal}
            />
            <StatCard
              label="Time Taken"
              value={fmtDuration(summary.total_duration_seconds)}
              accent="#0891b2"
            />
            <StatCard
              label="AI Calls"
              value={summary.total_calls ?? "—"}
              sub={`${summary.models_used ?? 0} model${summary.models_used !== 1 ? "s" : ""}`}
              accent="#7c3aed"
            />
          </div>

          {/* Fetch error state */}
          {summary._fetchError && (
            <div style={{ padding: "16px 20px", color: T.textSoft, fontSize: 12, textAlign: "center" }}>
              Summary data unavailable — check server logs for details.
            </div>
          )}

          {/* Key insights */}
          {!summary._fetchError && (summary.most_expensive_model || summary.slowest_step) && (
            <div style={{ padding: "0 20px 12px", display: "flex", gap: 8, flexWrap: "wrap" }}>
              {summary.most_expensive_model && (
                <div style={{ fontSize: 10, color: T.textSoft, background: "#6366f110", border: "1px solid #6366f130", borderRadius: 6, padding: "4px 8px" }}>
                  Priciest: <strong>{summary.most_expensive_model}</strong>
                </div>
              )}
              {summary.slowest_step && (
                <div style={{ fontSize: 10, color: T.textSoft, background: "#0891b210", border: "1px solid #0891b230", borderRadius: 6, padding: "4px 8px" }}>
                  Slowest: <strong>S{summary.slowest_step.step} {summary.slowest_step.name}</strong> ({fmtDuration(summary.slowest_step.duration_seconds)})
                </div>
              )}
            </div>
          )}

          {/* Model breakdown table */}
          {!summary._fetchError && (summary.by_model || []).length > 0 && (
            <div style={{ padding: "0 20px 16px" }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
                AI Calls per Model
              </div>
              <div style={{ borderRadius: 8, border: `1px solid ${T.border}`, overflow: "hidden" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                  <thead>
                    <tr style={{ background: "#F5F5F7" }}>
                      {["Model", "Provider", "Calls", "Tokens", "Cost"].map(h => (
                        <th key={h} style={{
                          padding: "6px 10px", textAlign: h === "Calls" || h === "Tokens" || h === "Cost" ? "right" : "left",
                          fontWeight: 600, color: T.textSoft, fontSize: 10,
                          borderBottom: `1px solid ${T.border}`,
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {summary.by_model.map((row, i) => (
                      <tr
                        key={i}
                        style={{ borderBottom: i < summary.by_model.length - 1 ? `1px solid ${T.border}` : "none" }}
                      >
                        <td style={{ padding: "6px 10px", fontWeight: 500, color: T.text, fontFamily: "monospace", fontSize: 10 }}>
                          {row.model}
                        </td>
                        <td style={{ padding: "6px 10px", color: T.textSoft }}>
                          {row.provider}
                        </td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: T.text }}>
                          {row.calls}
                        </td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: T.textSoft }}>
                          {fmtTokens((row.input_tokens || 0) + (row.output_tokens || 0))}
                        </td>
                        <td style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600, color: row.cost_usd > 0 ? "#6366f1" : T.teal }}>
                          {fmtCost(row.cost_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Step timings */}
          {!summary._fetchError && (summary.step_timings || []).some(s => s.duration_seconds != null) && (
            <div style={{ padding: "0 20px 16px" }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
                Step Timings
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {summary.step_timings.filter(s => s.duration_seconds != null).map((s, i) => (
                  <div key={i} style={{
                    padding: "4px 8px", borderRadius: 6, fontSize: 10,
                    background: s.status === "error" ? "#fef2f2" : s.status === "done" ? "#f0fdf4" : "#F5F5F7",
                    border: `1px solid ${s.status === "error" ? "#fecaca" : s.status === "done" ? "#bbf7d0" : T.border}`,
                    color: s.status === "error" ? "#dc2626" : s.status === "done" ? "#16a34a" : T.textSoft,
                  }}>
                    <span style={{ fontWeight: 600 }}>S{s.step}</span>
                    {" "}{s.name}
                    <span style={{ marginLeft: 4, color: T.textSoft }}>{fmtDuration(s.duration_seconds)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error / warning logs */}
          {!summary._fetchError && allLogs.length > 0 && (
            <div style={{ padding: "0 20px 20px" }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
                {summary.error_logs.length > 0 ? `${summary.error_logs.length} Error${summary.error_logs.length !== 1 ? "s" : ""}` : ""}
                {summary.error_logs.length > 0 && summary.warning_logs.length > 0 ? " · " : ""}
                {summary.warning_logs.length > 0 ? `${summary.warning_logs.length} Warning${summary.warning_logs.length !== 1 ? "s" : ""}` : ""}
              </div>
              <div style={{
                background: "#0d1117", borderRadius: 8, padding: "10px 12px",
                maxHeight: 180, overflowY: "auto",
                fontFamily: "monospace",
              }}>
                {allLogs.map((entry, i) => <LogLine key={i} entry={entry} />)}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: "12px 20px",
          borderTop: `1px solid ${T.border}`,
          display: "flex", justifyContent: "flex-end",
        }}>
          <button
            onClick={onClose}
            style={{
              padding: "7px 20px", borderRadius: 8, fontSize: 12, fontWeight: 600,
              cursor: "pointer", border: "none",
              background: headerColor, color: "#fff",
            }}
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  )
}
