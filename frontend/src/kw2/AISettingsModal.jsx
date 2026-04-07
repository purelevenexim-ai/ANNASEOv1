/**
 * AISettingsModal — choose AI provider for all KW2 phases in this session.
 * Provider is saved to the backend session so all phase API calls use it.
 */
import React, { useState } from "react"
import useKw2Store from "./store"
import * as api from "./api"

const PROVIDERS = [
  {
    id: "auto",
    label: "Auto (Cascade)",
    desc: "Groq → Ollama → Gemini. Tries each in order, falls back on failure.",
    color: "#6366f1",
    icon: "⚡",
  },
  {
    id: "groq",
    label: "Groq (Llama 3.1-8b)",
    desc: "Fast. Free tier. Best for quick generation, AI expand, batch validation.",
    color: "#f59e0b",
    icon: "🚀",
  },
  {
    id: "ollama",
    label: "Ollama (qwen2.5:3b)",
    desc: "Local, private, no rate limits. Slower but fully offline.",
    color: "#10b981",
    icon: "🏠",
  },
  {
    id: "gemini",
    label: "Gemini Flash",
    desc: "Google Gemini. Good for complex business analysis and strategy.",
    color: "#3b82f6",
    icon: "💎",
  },
  {
    id: "claude",
    label: "Claude (Anthropic)",
    desc: "Highest quality reasoning. Best for Phase 9 strategy generation.",
    color: "#8b5cf6",
    icon: "🧠",
  },
]

export default function AISettingsModal({ projectId, sessionId, onClose }) {
  const { aiProvider, setAiProvider, addToast, pushLog } = useKw2Store()
  const [selected, setSelected] = useState(aiProvider)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      if (sessionId) {
        await api.setSessionProvider(projectId, sessionId, selected)
      }
      setAiProvider(selected)
      pushLog(`AI provider set to: ${selected}`, { badge: "AI", type: "success" })
      addToast(`AI provider: ${PROVIDERS.find((p) => p.id === selected)?.label || selected}`, "success")
      onClose()
    } catch (e) {
      pushLog(`Failed to set provider: ${e.message}`, { badge: "AI", type: "error" })
      addToast(`Failed to update provider: ${e.message}`, "error")
    }
    setSaving(false)
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.5)",
        zIndex: 10000, display: "flex", alignItems: "center", justifyContent: "center",
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div style={{
        background: "#fff", borderRadius: 12, width: 520, maxWidth: "95vw",
        boxShadow: "0 20px 60px rgba(0,0,0,.2)", overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{ padding: "18px 24px", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>KW2 AI Settings</h2>
            <p style={{ margin: "2px 0 0", fontSize: 12, color: "#6b7280" }}>
              Choose AI provider for this research session. Applies to all phases.
            </p>
          </div>
          <button onClick={onClose} style={{ border: "none", background: "none", fontSize: 20, cursor: "pointer", color: "#9ca3af" }}>✕</button>
        </div>

        {/* Provider options */}
        <div style={{ padding: "16px 24px", display: "flex", flexDirection: "column", gap: 8 }}>
          {PROVIDERS.map((p) => {
            const active = selected === p.id
            return (
              <div
                key={p.id}
                onClick={() => setSelected(p.id)}
                style={{
                  border: active ? `2px solid ${p.color}` : "1px solid #e5e7eb",
                  borderRadius: 8, padding: "10px 14px", cursor: "pointer",
                  background: active ? `${p.color}08` : "#fff",
                  display: "flex", alignItems: "flex-start", gap: 12,
                  transition: "all 150ms",
                }}
              >
                <span style={{ fontSize: 22, lineHeight: 1.2 }}>{p.icon}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: 14, color: active ? p.color : "#374151" }}>{p.label}</span>
                    {aiProvider === p.id && (
                      <span style={{ fontSize: 10, background: "#dcfce7", color: "#166534", padding: "1px 6px", borderRadius: 9 }}>CURRENT</span>
                    )}
                  </div>
                  <p style={{ margin: "2px 0 0", fontSize: 12, color: "#6b7280" }}>{p.desc}</p>
                </div>
                <div style={{
                  width: 18, height: 18, borderRadius: "50%", flexShrink: 0, marginTop: 2,
                  border: active ? `2px solid ${p.color}` : "1px solid #d1d5db",
                  background: active ? p.color : "#fff",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  {active && <span style={{ fontSize: 10, color: "#fff" }}>✓</span>}
                </div>
              </div>
            )
          })}
        </div>

        {/* Footer */}
        <div style={{ padding: "14px 24px", borderTop: "1px solid #e5e7eb", display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #d1d5db", background: "#fff", cursor: "pointer", fontSize: 14 }}>
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving}
            style={{
              padding: "8px 20px", borderRadius: 6, border: "none",
              background: saving ? "#93c5fd" : "#3b82f6",
              color: "#fff", fontWeight: 600, fontSize: 14, cursor: saving ? "not-allowed" : "pointer",
            }}
          >
            {saving ? "Saving..." : "Apply Provider"}
          </button>
        </div>
      </div>
    </div>
  )
}
