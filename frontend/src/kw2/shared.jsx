/**
 * kw2 shared UI components + hooks — reusable across all phase pages.
 * LiveConsole, ProgressBar, Toast, PhaseResult, NotificationList, ConsolePanel, usePhaseRunner.
 */
import React, { useRef, useEffect, useState, useCallback } from "react"
import useKw2Store from "./store"

/* ───────────────────────── helpers ───────────────────────── */

function _ts() {
  return new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

/* ───────────────────────── usePhaseRunner hook ───────────────────────── */

/**
 * Hook that gives each phase component: loading state, error state,
 * per-run notification list, and helper functions to log & toast.
 */
export function usePhaseRunner(badge) {
  const { pushLog, addToast } = useKw2Store()
  const [loading, setLoading] = useState(false)
  const [streamLoading, setStreamLoading] = useState(false)
  const [error, setError] = useState(null)
  const [notifications, setNotifications] = useState([])

  const log = useCallback((text, type = "info") => {
    const entry = { time: _ts(), text, type }
    setNotifications((prev) => [...prev.slice(-99), entry])
    pushLog(text, { badge, type })
  }, [badge, pushLog])

  const toast = useCallback((msg, type = "success") => {
    addToast(msg, type)
  }, [addToast])

  const clear = useCallback(() => {
    setNotifications([])
    setError(null)
  }, [])

  return { loading, setLoading, streamLoading, setStreamLoading, error, setError, notifications, log, toast, clear }
}

/* ───────────────────────── Phase Stepper ───────────────────────── */

export function PhaseStepper({ current, completed, onSelect }) {
  const phases = [
    { n: 1, label: "Analyze" },
    { n: 2, label: "Generate" },
    { n: 3, label: "Validate" },
    { n: 4, label: "Score" },
    { n: 5, label: "Tree" },
    { n: 6, label: "Graph" },
    { n: 7, label: "Links" },
    { n: 8, label: "Calendar" },
    { n: 9, label: "Strategy" },
  ]

  return (
    <div style={{ display: "flex", gap: 4, marginBottom: 16, flexWrap: "wrap" }}>
      {phases.map((p) => {
        const done = completed >= p.n
        const active = current === p.n || (current === "REVIEW" && p.n === 3)
        return (
          <button
            key={p.n}
            onClick={() => onSelect(p.n)}
            style={{
              padding: "6px 14px",
              borderRadius: 6,
              border: active ? "2px solid #3b82f6" : "1px solid #e5e7eb",
              background: done ? "#10b981" : active ? "#eff6ff" : "#fff",
              color: done ? "#fff" : active ? "#3b82f6" : "#6b7280",
              fontWeight: active ? 600 : 400,
              fontSize: 13,
              cursor: "pointer",
              transition: "all 150ms",
            }}
          >
            {p.n}. {p.label} {done && "\u2713"}
          </button>
        )
      })}
    </div>
  )
}

/* ───────────────────────── Status Badge ───────────────────────── */

export function Badge({ children, color = "gray" }) {
  const colors = {
    green: { bg: "#dcfce7", fg: "#166534" },
    blue: { bg: "#dbeafe", fg: "#1e40af" },
    yellow: { bg: "#fef9c3", fg: "#854d0e" },
    red: { bg: "#fee2e2", fg: "#991b1b" },
    gray: { bg: "#f3f4f6", fg: "#374151" },
    purple: { bg: "#f3e8ff", fg: "#6b21a8" },
    teal: { bg: "#ccfbf1", fg: "#0f766e" },
  }
  const c = colors[color] || colors.gray
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 4,
        background: c.bg,
        color: c.fg,
        fontSize: 12,
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  )
}

/* ───────────────────────── Spinner ───────────────────────── */

export function Spinner({ text = "Loading..." }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: 16 }}>
      <div className="kw2-spin" style={{ width: 20, height: 20, border: "3px solid #e5e7eb", borderTop: "3px solid #3b82f6", borderRadius: "50%" }} />
      <span style={{ color: "#6b7280", fontSize: 14 }}>{text}</span>
      <style>{`@keyframes kw2spin { to { transform: rotate(360deg) } } .kw2-spin { animation: kw2spin .7s linear infinite; }`}</style>
    </div>
  )
}

/* ───────────────────────── Card ───────────────────────── */

export function Card({ title, children, actions }) {
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 10, padding: 20, marginBottom: 14, background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,.04)" }}>
      {title && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{title}</h3>
          {actions && <div style={{ display: "flex", gap: 8 }}>{actions}</div>}
        </div>
      )}
      {children}
    </div>
  )
}

/* ───────────────────────── RunButton ───────────────────────── */

export function RunButton({ onClick, loading, children, disabled, variant = "primary" }) {
  const bg = variant === "secondary" ? "#6b7280" : "#3b82f6"
  const bgDis = variant === "secondary" ? "#9ca3af" : "#93c5fd"
  return (
    <button
      onClick={onClick}
      disabled={loading || disabled}
      style={{
        padding: "8px 20px", borderRadius: 6, border: "none",
        background: loading || disabled ? bgDis : bg,
        color: "#fff", fontWeight: 600, fontSize: 14,
        cursor: loading || disabled ? "not-allowed" : "pointer",
        display: "flex", alignItems: "center", gap: 6, transition: "background 150ms",
      }}
    >
      {loading && (
        <span className="kw2-spin" style={{ display: "inline-block", width: 14, height: 14, border: "2px solid rgba(255,255,255,.3)", borderTop: "2px solid #fff", borderRadius: "50%" }} />
      )}
      {loading ? "Running..." : children}
      <style>{`.kw2-spin { animation: kw2spin .7s linear infinite; } @keyframes kw2spin { to { transform: rotate(360deg) } }`}</style>
    </button>
  )
}

/* ───────────────────────── Progress Bar ───────────────────────── */

export function ProgressBar({ value = 0, max = 100, label = "", color = "#3b82f6", animated = false }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div style={{ marginBottom: 8 }}>
      {label && (
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>{label}</span>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>{pct}%</span>
        </div>
      )}
      <div style={{ height: 8, background: "#e5e7eb", borderRadius: 4, overflow: "hidden" }}>
        <div style={{
          height: "100%", width: `${pct}%`, background: color,
          borderRadius: 4, transition: "width 300ms ease",
          animation: animated ? "kw2barPulse 1.5s ease infinite" : "none",
        }} />
      </div>
      <style>{`@keyframes kw2barPulse { 0%,100%{opacity:.6} 50%{opacity:1} }`}</style>
    </div>
  )
}

/* ───────────────────────── Phase Result Card ───────────────────────── */

/**
 * Shown after a phase completes successfully.
 * Displays stats + a "→ Continue to Phase N" button.
 */
export function PhaseResult({ phaseNum, stats, children, onNext, nextLabel }) {
  const nextPhase = phaseNum < 9 ? phaseNum + 1 : null
  const PHASE_NAMES = ["", "Analyze", "Generate", "Validate", "Score", "Tree", "Graph", "Links", "Calendar", "Strategy"]
  const buttonLabel = nextLabel || (nextPhase ? `Continue to Phase ${nextPhase}: ${PHASE_NAMES[nextPhase]} →` : null)

  return (
    <div style={{ marginTop: 12, border: "1px solid #86efac", borderRadius: 8, overflow: "hidden" }}>
      {/* Success header */}
      <div style={{ background: "#f0fdf4", borderBottom: "1px solid #86efac", padding: "10px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18 }}>✓</span>
          <span style={{ fontWeight: 600, color: "#166534", fontSize: 14 }}>
            Phase {phaseNum} Complete
          </span>
        </div>
        {buttonLabel && onNext && (
          <button
            onClick={onNext}
            style={{
              background: "#10b981", color: "#fff", border: "none",
              borderRadius: 6, padding: "6px 16px", fontWeight: 600,
              fontSize: 13, cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
            }}
          >
            {buttonLabel}
          </button>
        )}
        {!nextPhase && (
          <Badge color="green">All 9 Phases Complete!</Badge>
        )}
      </div>

      {/* Stats + custom content */}
      <div style={{ padding: "12px 16px" }}>
        {stats && stats.length > 0 && <StatsRow items={stats} />}
        {children}
      </div>
    </div>
  )
}

/* ───────────────────────── Notification List ───────────────────────── */

const NOTIFY_COLORS = {
  info: { bg: "#eff6ff", fg: "#1e40af", dot: "#3b82f6" },
  success: { bg: "#f0fdf4", fg: "#166534", dot: "#10b981" },
  error: { bg: "#fef2f2", fg: "#991b1b", dot: "#ef4444" },
  warning: { bg: "#fefce8", fg: "#854d0e", dot: "#f59e0b" },
  progress: { bg: "#f8fafc", fg: "#475569", dot: "#94a3b8" },
}

/**
 * Per-phase list of notifications from the current run.
 * Collapsible. Shows time, type dot, and message.
 */
export function NotificationList({ notifications, title = "Notifications" }) {
  const [open, setOpen] = useState(true)
  if (!notifications || !notifications.length) return null

  return (
    <div style={{ marginTop: 10, border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "8px 14px", background: "#f9fafb", border: "none", cursor: "pointer",
          fontSize: 12, fontWeight: 600, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".4px",
        }}
      >
        <span>{title} ({notifications.length})</span>
        <span>{open ? "▼" : "▶"}</span>
      </button>
      {open && (
        <div style={{ maxHeight: 200, overflowY: "auto", padding: "6px 0" }}>
          {notifications.map((n, i) => {
            const s = NOTIFY_COLORS[n.type] || NOTIFY_COLORS.info
            return (
              <div key={i} style={{ display: "flex", gap: 8, padding: "4px 14px", alignItems: "flex-start", background: s.bg }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: s.dot, flexShrink: 0, marginTop: 5 }} />
                <span style={{ fontSize: 11, color: "#9ca3af", flexShrink: 0 }}>{n.time}</span>
                <span style={{ fontSize: 12, color: s.fg }}>{n.text}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ───────────────────────── Console Panel ───────────────────────── */

const LOG_COLORS = {
  info: "#cdd6f4", success: "#a6e3a1", warning: "#f9e2af",
  error: "#f38ba8", progress: "#89b4fa",
}
const LOG_BADGE_BG = {
  info: "#45475a", success: "#1e3a2f", warning: "#3a321e",
  error: "#45171e", progress: "#1e2d3a",
}

/**
 * Collapsible debug console. Shows global consoleLogs.
 * Optionally filtered to a specific phase badge.
 */
export function ConsolePanel({ filterBadge, maxHeight = 240, defaultOpen = false }) {
  const { consoleLogs } = useKw2Store()
  const endRef = useRef(null)
  const [open, setOpen] = useState(defaultOpen)

  const logs = filterBadge
    ? consoleLogs.filter((l) => !l.badge || l.badge === filterBadge || l.type === "error")
    : consoleLogs

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [logs.length, open])

  const errorCount = logs.filter((l) => l.type === "error").length

  return (
    <div style={{ marginTop: 10, border: "1px solid #313244", borderRadius: 8, overflow: "hidden" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "8px 14px", background: "#1e1e2e", border: "none", cursor: "pointer",
          fontSize: 12, fontWeight: 600, color: "#cdd6f4",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, opacity: .7 }}>▶_</span>
          Debug Console
          {logs.length > 0 && <span style={{ fontSize: 11, color: "#585b70" }}>({logs.length} events)</span>}
          {errorCount > 0 && (
            <span style={{ background: "#45171e", color: "#f38ba8", padding: "1px 6px", borderRadius: 3, fontSize: 11 }}>
              {errorCount} error{errorCount > 1 ? "s" : ""}
            </span>
          )}
        </span>
        <span style={{ color: "#585b70" }}>{open ? "▼" : "▶"}</span>
      </button>
      {open && (
        <div style={{
          background: "#1e1e2e", padding: "8px 14px", maxHeight,
          overflowY: "auto", fontFamily: "'JetBrains Mono','Fira Code',monospace",
          fontSize: 11.5, lineHeight: 1.7,
        }}>
          {logs.length === 0 ? (
            <span style={{ color: "#585b70" }}>No events yet. Run a phase to see output.</span>
          ) : (
            logs.map((entry, i) => {
              const type = entry.type || "info"
              return (
                <div key={i} style={{ color: LOG_COLORS[type] || LOG_COLORS.info, display: "flex", gap: 8, marginBottom: 1 }}>
                  <span style={{ color: "#585b70", flexShrink: 0 }}>{entry.time}</span>
                  {entry.badge && (
                    <span style={{
                      background: LOG_BADGE_BG[type] || LOG_BADGE_BG.info,
                      color: LOG_COLORS[type] || LOG_COLORS.info,
                      padding: "0 5px", borderRadius: 3, fontSize: 10, flexShrink: 0,
                    }}>
                      {entry.badge}
                    </span>
                  )}
                  <span style={{ wordBreak: "break-word" }}>{entry.text}</span>
                </div>
              )
            })
          )}
          <div ref={endRef} />
        </div>
      )}
    </div>
  )
}

/* ───────────────────────── Live Console (global) ───────────────────────── */

export function LiveConsole({ logs, maxHeight = 280 }) {
  const endRef = useRef(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [logs.length])
  if (!logs || !logs.length) return null

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px" }}>
          Session Console
        </span>
        <Badge color="green">{logs.length} events</Badge>
      </div>
      <div style={{
        background: "#1e1e2e", borderRadius: 8, padding: "10px 14px", maxHeight,
        overflowY: "auto", fontFamily: "'JetBrains Mono','Fira Code',monospace",
        fontSize: 12, lineHeight: 1.7, border: "1px solid #313244",
      }}>
        {logs.map((entry, i) => {
          const type = entry.type || "info"
          return (
            <div key={i} style={{ color: LOG_COLORS[type] || LOG_COLORS.info, display: "flex", gap: 8 }}>
              <span style={{ color: "#585b70", flexShrink: 0 }}>{entry.time}</span>
              {entry.badge && (
                <span style={{ background: LOG_BADGE_BG[type] || LOG_BADGE_BG.info, color: LOG_COLORS[type] || LOG_COLORS.info, padding: "0 6px", borderRadius: 3, fontSize: 11, flexShrink: 0 }}>
                  {entry.badge}
                </span>
              )}
              <span>{entry.text}</span>
            </div>
          )
        })}
        <div ref={endRef} />
      </div>
    </div>
  )
}

/* ───────────────────────── Toast Notification Container ───────────────────────── */

const TOAST_STYLE = {
  success: { bg: "#dcfce7", border: "#86efac", fg: "#166534", icon: "\u2713" },
  error: { bg: "#fee2e2", border: "#fca5a5", fg: "#991b1b", icon: "\u2717" },
  info: { bg: "#dbeafe", border: "#93c5fd", fg: "#1e40af", icon: "\u2139" },
  warning: { bg: "#fef9c3", border: "#fde047", fg: "#854d0e", icon: "\u26A0" },
}

export function ToastContainer({ toasts, onDismiss }) {
  if (!toasts || !toasts.length) return null
  return (
    <div style={{ position: "fixed", top: 16, right: 16, zIndex: 9999, display: "flex", flexDirection: "column", gap: 8, maxWidth: 380 }}>
      {toasts.map((t) => {
        const s = TOAST_STYLE[t.type] || TOAST_STYLE.info
        return (
          <div key={t.id} onClick={() => onDismiss(t.id)} style={{
            background: s.bg, border: `1px solid ${s.border}`, color: s.fg,
            borderRadius: 8, padding: "10px 14px", fontSize: 13,
            display: "flex", alignItems: "center", gap: 8,
            boxShadow: "0 4px 12px rgba(0,0,0,.1)", cursor: "pointer",
            animation: "kw2SlideIn .25s ease",
          }}>
            <span style={{ fontWeight: 700, fontSize: 16 }}>{s.icon}</span>
            <span style={{ flex: 1 }}>{t.message}</span>
            <span style={{ fontSize: 11, opacity: .5 }}>✕</span>
          </div>
        )
      })}
      <style>{`@keyframes kw2SlideIn { from{opacity:0;transform:translateX(30px)} to{opacity:1;transform:translateX(0)} }`}</style>
    </div>
  )
}

/* ───────────────────────── Stats Row ───────────────────────── */

export function StatsRow({ items }) {
  if (!items || !items.length) return null
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
      {items.map((s, i) => (
        <div key={i} style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 8, padding: "8px 14px", minWidth: 80, textAlign: "center" }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: s.color || "#374151" }}>
            {typeof s.value === "number" ? s.value.toLocaleString() : s.value}
          </div>
          <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>{s.label}</div>
        </div>
      ))}
    </div>
  )
}

/* ───────────────────────── Keyword Table ───────────────────────── */

export function KeywordTable({ keywords, onExplain, maxRows = 50 }) {
  if (!keywords || !keywords.length)
    return <p style={{ color: "#9ca3af", fontSize: 13 }}>No keywords yet.</p>
  const display = keywords.slice(0, maxRows)
  return (
    <div style={{ overflowX: "auto", maxHeight: 400 }}>
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "2px solid #e5e7eb", background: "#f9fafb" }}>
            <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 600 }}>#</th>
            <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 600 }}>Keyword</th>
            <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 600 }}>Pillar</th>
            <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 600 }}>Intent</th>
            <th style={{ textAlign: "right", padding: "8px 10px", fontWeight: 600 }}>Score</th>
            <th style={{ textAlign: "left", padding: "8px 10px", fontWeight: 600 }}>Page Type</th>
            {onExplain && <th style={{ padding: "8px 10px" }}></th>}
          </tr>
        </thead>
        <tbody>
          {display.map((kw, i) => (
            <tr key={kw.id || i} style={{ borderBottom: "1px solid #f3f4f6" }}>
              <td style={{ padding: "6px 10px", color: "#9ca3af", fontSize: 11 }}>{i + 1}</td>
              <td style={{ padding: "6px 10px", fontWeight: 500 }}>{kw.keyword}</td>
              <td style={{ padding: "6px 10px" }}><Badge color="blue">{kw.pillar || "-"}</Badge></td>
              <td style={{ padding: "6px 10px" }}>
                <Badge color={kw.intent === "purchase" ? "green" : kw.intent === "wholesale" ? "purple" : kw.intent === "commercial" ? "yellow" : "gray"}>
                  {kw.intent || "-"}
                </Badge>
              </td>
              <td style={{ padding: "6px 10px", textAlign: "right", fontWeight: 600 }}>{(kw.final_score || kw.score || 0).toFixed(1)}</td>
              <td style={{ padding: "6px 10px", fontSize: 12, color: "#6b7280" }}>{kw.mapped_page || "-"}</td>
              {onExplain && (
                <td style={{ padding: "6px 10px" }}>
                  <button onClick={() => onExplain(kw.id)} style={{ border: "1px solid #d1d5db", borderRadius: 4, padding: "2px 8px", fontSize: 11, cursor: "pointer", background: "#fff" }}>
                    Explain
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {keywords.length > maxRows && (
        <p style={{ fontSize: 12, color: "#9ca3af", textAlign: "center", padding: 8 }}>Showing {maxRows} of {keywords.length} keywords</p>
      )}
    </div>
  )
}

/* ───────────────────────── StreamLog (legacy compat) ───────────────────────── */

export function StreamLog({ events }) {
  if (!events || !events.length) return null
  return (
    <ConsolePanel defaultOpen />
  )
}
