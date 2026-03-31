import React from "react"
import { useNotification } from "../store/notification"

const COLOR_MAP = {
  error:   "#dc2626",
  success: "#059669",
  warning: "#d97706",
  info:    "#2563eb",
}

const LABEL_MAP = {
  error:   "Error",
  success: "Success",
  warning: "Warning",
  info:    "Info",
}

export default function Notification() {
  const { notifications = [], clear, pause, resume } = useNotification(s => ({
    notifications: s.notifications,
    clear: s.clear,
    pause: s.pause,
    resume: s.resume,
  }))

  if (!notifications || notifications.length === 0) return null

  return (
    <div style={{ position: "fixed", top: 18, right: 18, zIndex: 1200, display: "flex", flexDirection: "column", gap: 8 }}>
      {notifications.map(n => {
        const bg = COLOR_MAP[n.type] || COLOR_MAP.info
        const label = LABEL_MAP[n.type] || ""
        return (
          <div key={n.id}
            onMouseEnter={() => pause(n.id)}
            onMouseLeave={() => resume(n.id)}
            style={{ minWidth: 280, maxWidth: 420, padding: 12, borderRadius: 12, boxShadow: "0 8px 20px rgba(0,0,0,0.18)", background: bg, color: "#fff", whiteSpace: "pre-wrap" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
              <div style={{ flex: 1, fontSize: 13 }}>
                {label && <strong>{label}: </strong>}
                {n.message}
              </div>
              <button onClick={() => clear(n.id)} style={{ background: "transparent", border: "none", color: "#fff", cursor: "pointer", fontSize: 14 }}>✖</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
