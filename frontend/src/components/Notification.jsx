import React from "react"
import { useNotification } from "../store/notification"

export default function Notification() {
  const { message, type, show, clear } = useNotification()
  if (!show || !message) return null

  const bg = type === "error" ? "#dc2626" : "#059669"

  return (
    <div style={{ position: "fixed", top: 18, right: 18, zIndex: 1200 }}>
      <div style={{ minWidth: 280, padding: 12, borderRadius: 12, boxShadow: "0 8px 20px rgba(0,0,0,0.12)", background: bg, color: "#fff", whiteSpace: "pre-wrap" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
          <div style={{ flex: 1, fontSize: 13 }}>{message}</div>
          <button onClick={clear} style={{ background: "transparent", border: "none", color: "#fff", cursor: "pointer", fontSize: 14 }}>✖</button>
        </div>
      </div>
    </div>
  )
}
