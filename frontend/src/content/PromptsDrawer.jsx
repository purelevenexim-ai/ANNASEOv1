import { useState, useEffect } from "react"
import { T, api } from "../App"

export default function PromptsDrawer({ onClose, onTest }) {
  const [prompts, setPrompts] = useState([])
  const [activeKey, setActiveKey] = useState(null)
  const [editing, setEditing] = useState({})   // { [key]: string }
  const [saving, setSaving] = useState({})
  const [testKw, setTestKw] = useState("")
  const [saved, setSaved] = useState({})

  useEffect(() => {
    api.get("/api/prompts").then(d => {
      setPrompts(d.prompts || [])
      if (d.prompts?.length) setActiveKey(d.prompts[0].key)
    }).catch(() => {})
  }, [])

  const active = prompts.find(p => p.key === activeKey)

  const currentText = activeKey
    ? (editing[activeKey] !== undefined ? editing[activeKey] : active?.content || "")
    : ""

  const handleSave = async (key) => {
    setSaving(s => ({ ...s, [key]: true }))
    try {
      await api.post(`/api/prompts/${key}`, { content: editing[key] ?? active?.content ?? "" })
      setSaved(s => ({ ...s, [key]: true }))
      setTimeout(() => setSaved(s => ({ ...s, [key]: false })), 2000)
      // Refresh
      const d = await api.get("/api/prompts")
      setPrompts(d.prompts || [])
    } catch (e) { /* ignore */ }
    setSaving(s => ({ ...s, [key]: false }))
  }

  const handleReset = async (key) => {
    try {
      await api.delete(`/api/prompts/${key}`)
      const d = await api.get("/api/prompts")
      setPrompts(d.prompts || [])
      setEditing(e => { const n = {...e}; delete n[key]; return n })
    } catch (e) { /* ignore */ }
  }

  const isDirty = activeKey && editing[activeKey] !== undefined && editing[activeKey] !== active?.content

  const taStyle = {
    width: "100%", padding: "10px 12px", fontSize: 11, lineHeight: 1.6,
    fontFamily: "ui-monospace, 'Cascadia Code', monospace",
    border: `1px solid ${T.border}`, borderRadius: 8, resize: "vertical",
    boxSizing: "border-box", outline: "none", minHeight: 320,
    background: "#fafafa", color: T.text,
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 2100,
      display: "flex", alignItems: "flex-end", justifyContent: "center",
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: "#fff", borderRadius: "16px 16px 0 0", width: "100%", maxWidth: 720,
        maxHeight: "85vh", display: "flex", flexDirection: "column",
        boxShadow: "0 -8px 40px rgba(0,0,0,0.16)",
      }}>
        {/* Header */}
        <div style={{
          padding: "16px 20px 12px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: T.text }}>Prompt Editor</div>
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
              Edit the instruction blocks injected into each pipeline step. Changes apply on next generate.
            </div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: T.gray }}>✕</button>
        </div>

        {/* Step tabs */}
        <div style={{ display: "flex", borderBottom: `1px solid ${T.border}`, padding: "0 20px", overflowX: "auto" }}>
          {prompts.map(p => (
            <button key={p.key} onClick={() => setActiveKey(p.key)} style={{
              padding: "8px 14px", fontSize: 11, whiteSpace: "nowrap",
              fontWeight: activeKey === p.key ? 600 : 400,
              color: activeKey === p.key ? T.purple : T.textSoft,
              background: "none", border: "none", cursor: "pointer",
              borderBottom: activeKey === p.key ? `2px solid ${T.purple}` : "2px solid transparent",
              marginBottom: -1,
            }}>
              {p.label.replace(/^Step \d+: /, "")}
              {p.is_custom && <span style={{ marginLeft: 4, fontSize: 8, color: T.teal, fontWeight: 700 }}>CUSTOM</span>}
            </button>
          ))}
        </div>

        {/* Editor body */}
        {active && (
          <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
            <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 8 }}>{active.desc}</div>
            <textarea
              style={taStyle}
              value={currentText}
              onChange={e => setEditing(ed => ({ ...ed, [activeKey]: e.target.value }))}
              spellCheck={false}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center" }}>
              <button
                onClick={() => handleSave(activeKey)}
                disabled={saving[activeKey]}
                style={{
                  padding: "7px 16px", borderRadius: 8, fontSize: 11, cursor: "pointer",
                  background: saved[activeKey] ? T.teal : T.purple,
                  color: "#fff", border: "none", fontWeight: 600,
                }}
              >
                {saving[activeKey] ? "Saving…" : saved[activeKey] ? "Saved ✓" : "Save Changes"}
              </button>
              {active.is_custom && (
                <button
                  onClick={() => handleReset(activeKey)}
                  style={{
                    padding: "7px 14px", borderRadius: 8, fontSize: 11, cursor: "pointer",
                    background: "transparent", border: `1px solid ${T.border}`, color: T.red,
                  }}
                >
                  Reset to Default
                </button>
              )}
              {isDirty && <span style={{ fontSize: 10, color: T.amber }}>Unsaved changes</span>}
              <div style={{ flex: 1 }} />
              {active.is_custom && <span style={{ fontSize: 10, color: T.teal }}>Using custom prompt</span>}
            </div>
          </div>
        )}

        {/* Test section */}
        <div style={{
          padding: "12px 20px", borderTop: `1px solid ${T.border}`,
          display: "flex", gap: 8, alignItems: "center",
        }}>
          <div style={{ fontSize: 11, color: T.textSoft, flexShrink: 0 }}>Test keyword:</div>
          <input
            value={testKw}
            onChange={e => setTestKw(e.target.value)}
            placeholder="e.g. best kerala spices online"
            style={{
              flex: 1, padding: "6px 10px", borderRadius: 8, fontSize: 11,
              border: `1px solid ${T.border}`, outline: "none",
            }}
            onKeyDown={e => e.key === "Enter" && testKw.trim() && onTest(testKw.trim())}
          />
          <button
            onClick={() => testKw.trim() && onTest(testKw.trim())}
            disabled={!testKw.trim()}
            style={{
              padding: "6px 16px", borderRadius: 8, fontSize: 11, cursor: "pointer",
              background: T.purple, color: "#fff", border: "none", fontWeight: 600,
              opacity: testKw.trim() ? 1 : 0.5,
            }}
          >
            Test Article ▶
          </button>
        </div>
      </div>
    </div>
  )
}
