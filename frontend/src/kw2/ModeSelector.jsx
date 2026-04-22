/**
 * Mode selector shown before session creation.
 */
import React from "react"
import { MODE_META } from "./flow"

export default function ModeSelector({ onSelect, loading = false, error = "" }) {
  const modes = ["v2", "brand", "expand", "review"]

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 20, background: "#fff" }}>
      <h3 style={{ margin: "0 0 6px", fontSize: 18 }}>Choose Workflow</h3>
      <p style={{ margin: "0 0 14px", color: "#6b7280", fontSize: 13 }}>
        Start keyword research in the mode that matches your goal.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(210px,1fr))", gap: 10 }}>
        {modes.map((mode) => {
          const m = MODE_META[mode]
          const isV2 = mode === "v2"
          return (
            <button
              key={mode}
              onClick={() => onSelect(mode)}
              disabled={loading}
              style={{
                textAlign: "left",
                borderRadius: 10,
                border: isV2 ? `2px solid ${m.border}` : `1.5px solid ${m.border}`,
                background: m.bg,
                padding: "12px 14px",
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1,
                position: "relative",
              }}
            >
              {isV2 && (
                <span style={{
                  position: "absolute", top: -1, right: 10,
                  background: "#059669", color: "#fff",
                  fontSize: 10, fontWeight: 700, padding: "1px 7px",
                  borderRadius: "0 0 5px 5px", letterSpacing: "0.04em",
                }}>
                  RECOMMENDED
                </span>
              )}
              <div style={{ fontSize: 18, marginBottom: 4 }}>{m.icon}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: m.color, marginBottom: 4 }}>{m.title}</div>
              <div style={{ fontSize: 12, color: "#4b5563", lineHeight: 1.5 }}>{m.subtitle}</div>
            </button>
          )
        })}
      </div>

      {error && <p style={{ color: "#dc2626", marginTop: 10, fontSize: 13 }}>{error}</p>}
    </div>
  )
}
