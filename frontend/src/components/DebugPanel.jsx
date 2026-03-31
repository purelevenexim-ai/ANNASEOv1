import { useEffect, useState } from "react"
import useDebug from "../store/debug"

export default function DebugPanel() {
  const { enabled, logs, toggle, clear } = useDebug(s => ({
    enabled: s.enabled,
    logs: s.logs,
    toggle: s.toggle,
    clear: s.clear,
  }))

  const [expanded, setExpanded] = useState(true)

  // Keyboard shortcut Ctrl+Shift+D
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.ctrlKey && e.shiftKey && e.key === "D") {
        e.preventDefault()
        toggle()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [toggle])

  if (!enabled) return null

  return (
    <div
      style={{
        position: "fixed",
        bottom: 16,
        right: 16,
        zIndex: 9999,
        fontFamily: "monospace",
        fontSize: 11,
        maxWidth: 500,
        maxHeight: 400,
        backgroundColor: "#1f2937",
        color: "#f3f4f6",
        borderRadius: 8,
        boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
        border: "1px solid #374151",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid #374151",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
          userSelect: "none",
          backgroundColor: "#111827",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <span style={{ fontWeight: "bold" }}>
          {expanded ? "▼" : "▶"} Debug Panel ({logs.length} logs)
        </span>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={(e) => { e.stopPropagation(); clear() }}
            style={{
              background: "#7f1d1d",
              color: "#fca5a5",
              border: "none",
              borderRadius: 4,
              padding: "2px 6px",
              cursor: "pointer",
              fontSize: 10,
            }}
          >
            Clear
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); toggle() }}
            style={{
              background: "#1e40af",
              color: "#93c5fd",
              border: "none",
              borderRadius: 4,
              padding: "2px 6px",
              cursor: "pointer",
              fontSize: 10,
            }}
          >
            Off
          </button>
        </div>
      </div>

      {/* Logs */}
      {expanded && (
        <div
          style={{
            overflowY: "auto",
            flex: 1,
            padding: 8,
            backgroundColor: "#1f2937",
          }}
        >
          {logs.length === 0 ? (
            <div style={{ color: "#9ca3af" }}>No logs yet</div>
          ) : (
            logs.map((log, i) => (
              <LogEntry key={i} log={log} />
            ))
          )}
        </div>
      )}
    </div>
  )
}

function LogEntry({ log }) {
  const [expanded, setExpanded] = useState(false)

  const statusColor = log.error
    ? "#ef4444"
    : log.status >= 400
      ? "#f97316"
      : log.status >= 200 && log.status < 300
        ? "#22c55e"
        : "#8b5cf6"

  return (
    <div style={{ marginBottom: 6, borderLeft: `2px solid ${statusColor}`, paddingLeft: 6 }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          cursor: "pointer",
          userSelect: "none",
          color: "#e5e7eb",
          fontSize: 10,
        }}
      >
        <strong>{log.method}</strong> {log.path} {log.status ? `(${log.status})` : ""} {log.elapsed}ms
        {log.error && ` ⚠ ${log.error}`}
      </div>
      {expanded && (
        <div
          style={{
            marginTop: 4,
            padding: "4px 6px",
            background: "#111827",
            borderRadius: 4,
            fontSize: 9,
            color: "#d1d5db",
            overflowX: "auto",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            maxHeight: 200,
            overflowY: "auto",
          }}
        >
          {log.request && (
            <>
              <div style={{ color: "#60a5fa" }}>Request:</div>
              <div>{JSON.stringify(log.request, null, 2)}</div>
            </>
          )}
          {log.response && Object.keys(log.response).length > 0 && (
            <>
              <div style={{ color: "#60a5fa", marginTop: 4 }}>Response:</div>
              <div>{JSON.stringify(log.response, null, 2)}</div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
