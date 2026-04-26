import { useState, useEffect, useCallback } from "react"
import { T, api } from "../App"

const STEP_ICONS = {
  step1_research_instructions: "🔍",
  step2_structure_rules: "🏗",
  step3_verify_instructions: "✅",
  step4_link_planning: "🔗",
  step6_quality_rules: "📋",
  step6_intelligence_rules: "🧠",
  step7_review_criteria: "🔎",
  step9_quality_rules: "🛠",
}

const PANEL_TABS = ["Edit", "Versions", "▶ Test"]

export default function PromptStudio() {
  const [prompts, setPrompts] = useState([])
  const [activeKey, setActiveKey] = useState(null)
  const [editing, setEditing] = useState({})
  const [saving, setSaving] = useState(false)
  const [saveOk, setSaveOk] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [panelTab, setPanelTab] = useState("Edit")
  const [versions, setVersions] = useState([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [restoring, setRestoring] = useState(null)

  // Test tab state
  const [testProvider, setTestProvider] = useState("ollama")
  const [testResult, setTestResult] = useState(null)
  const [testRunning, setTestRunning] = useState(false)
  const [testError, setTestError] = useState(null)
  const [sampleDataStr, setSampleDataStr] = useState("{}")
  const [showVars, setShowVars] = useState(false)

  const loadPrompts = useCallback(() => {
    api.get("/api/prompts").then(d => {
      setPrompts(d.prompts || [])
      if (!activeKey && d.prompts?.length) setActiveKey(d.prompts[0].key)
    }).catch(() => {})
  }, [activeKey])

  useEffect(() => { loadPrompts() }, []) // eslint-disable-line

  const active = prompts.find(p => p.key === activeKey)
  const currentText = activeKey
    ? (editing[activeKey] !== undefined ? editing[activeKey] : active?.content ?? "")
    : ""
  const isDirty = activeKey && editing[activeKey] !== undefined && editing[activeKey] !== active?.content
  const charCount = currentText.length
  const lineCount = currentText.split("\n").length

  // Load versions when switching to Versions tab or changing step
  useEffect(() => {
    if (panelTab === "Versions" && activeKey) {
      setVersionsLoading(true)
      api.get(`/api/prompts/${activeKey}/versions`)
        .then(d => setVersions(d.versions || []))
        .catch(() => setVersions([]))
        .finally(() => setVersionsLoading(false))
    }
  }, [panelTab, activeKey])

  // Load sample data when switching to Test tab
  useEffect(() => {
    if (panelTab !== "▶ Test" || !activeKey) return
    setTestResult(null)
    setTestError(null)
    api.get(`/api/prompts/${activeKey}/sample-data`)
      .then(d => {
        const sd = d.sample_data || {}
        const display = { ...sd }
        delete display._meta
        setSampleDataStr(JSON.stringify(display, null, 2))
      })
      .catch(() => setSampleDataStr("{}"))
  }, [panelTab, activeKey])

  const handleTest = async () => {
    if (!activeKey || !currentText) return
    setTestRunning(true)
    setTestResult(null)
    setTestError(null)
    try {
      let parsedOverrides = null
      try { parsedOverrides = JSON.parse(sampleDataStr) } catch { parsedOverrides = null }
      const res = await api.post("/api/prompts/test", {
        prompt_key: activeKey,
        template: currentText,
        provider: testProvider,
        sample_data: parsedOverrides,
      })
      if (res.error) {
        setTestError(res.error)
      } else {
        setTestResult(res)
      }
    } catch (e) {
      setTestError(e?.message || "Test failed")
    }
    setTestRunning(false)
  }

  const handleSave = async () => {
    if (!activeKey) return
    setSaving(true)
    try {
      await api.post(`/api/prompts/${activeKey}`, { content: currentText })
      setSaveOk(true)
      setTimeout(() => setSaveOk(false), 2000)
      loadPrompts()
    } catch {}
    setSaving(false)
  }

  const handleReset = async () => {
    if (!activeKey || !window.confirm("Reset this prompt to its built-in default?")) return
    setResetting(true)
    try {
      await api.delete(`/api/prompts/${activeKey}`)
      setEditing(e => { const n = { ...e }; delete n[activeKey]; return n })
      loadPrompts()
    } catch {}
    setResetting(false)
  }

  const handleRestore = async (idx) => {
    if (!activeKey) return
    setRestoring(idx)
    try {
      const res = await api.post(`/api/prompts/${activeKey}/restore/${idx}`, {})
      setEditing(e => { const n = { ...e }; delete n[activeKey]; return n })
      loadPrompts()
      // Reload versions
      const d = await api.get(`/api/prompts/${activeKey}/versions`)
      setVersions(d.versions || [])
      setPanelTab("Edit")
    } catch {}
    setRestoring(null)
  }

  const handleSelectStep = (key) => {
    setActiveKey(key)
    setPanelTab("Edit")
  }

  // ── Styles ──────────────────────────────────────────────────────────────────

  const sidebarStyle = {
    width: 220, flexShrink: 0, borderRight: `1px solid ${T.border}`,
    display: "flex", flexDirection: "column", overflowY: "auto", background: "#fafafa",
  }

  const stepItem = (key, isActive) => ({
    padding: "9px 14px", cursor: "pointer", borderLeft: isActive ? `3px solid ${T.purple}` : "3px solid transparent",
    background: isActive ? T.purpleLight || "rgba(139,92,246,0.08)" : "transparent",
    display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontWeight: isActive ? 600 : 400,
    color: isActive ? T.purple : T.text, transition: "background 0.1s",
  })

  const panelTabBtn = (label) => ({
    padding: "5px 14px", fontSize: 12, fontWeight: 500, borderRadius: 99,
    border: "none", cursor: "pointer",
    background: panelTab === label ? T.purple : "transparent",
    color: panelTab === label ? "#fff" : T.gray,
  })

  const btnStyle = (variant) => ({
    padding: "6px 16px", borderRadius: 7, fontSize: 12, fontWeight: 600,
    cursor: "pointer",
    background: variant === "primary" ? T.purple : variant === "danger" ? "transparent" : "transparent",
    color: variant === "primary" ? "#fff" : variant === "danger" ? T.red : T.gray,
    border: variant === "danger" ? `1px solid ${T.red}` : variant === "secondary" ? `1px solid ${T.border}` : "none",
    opacity: saving || resetting ? 0.6 : 1,
  })

  const taStyle = {
    width: "100%", flex: 1, padding: "12px 14px", fontSize: 12, lineHeight: 1.7,
    border: `1px solid ${isDirty ? T.purple : T.border}`, borderRadius: 8,
    fontFamily: "ui-monospace, 'Cascadia Code', 'Fira Code', monospace",
    resize: "none", outline: "none", background: "#fff", color: T.text, boxSizing: "border-box",
    transition: "border-color 0.15s",
  }

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>

      {/* ── Left: step list ────────────────────────────────────────────────── */}
      <div style={sidebarStyle}>
        <div style={{ padding: "12px 14px 8px", fontSize: 10, fontWeight: 700, color: T.textSoft,
          textTransform: "uppercase", letterSpacing: 0.5 }}>
          Pipeline Steps
        </div>
        {prompts.map(p => (
          <div key={p.key} onClick={() => handleSelectStep(p.key)} style={stepItem(p.key, p.key === activeKey)}>
            <span style={{ fontSize: 14 }}>{STEP_ICONS[p.key] || "⚙️"}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {p.label.replace(/^Step \d+: /, "")}
              </div>
              {p.is_custom && (
                <div style={{ fontSize: 9, color: T.purple, marginTop: 1 }}>● custom</div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* ── Right: editor panel ─────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {active ? (
          <>
            {/* Header */}
            <div style={{ padding: "12px 16px", borderBottom: `1px solid ${T.border}`,
              display: "flex", alignItems: "center", gap: 10, flexShrink: 0, background: "#fff" }}>
              <span style={{ fontSize: 18 }}>{STEP_ICONS[activeKey] || "⚙️"}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>{active.label}</div>
                <div style={{ fontSize: 11, color: T.textSoft, marginTop: 1 }}>{active.desc}</div>
              </div>
              {active.is_custom && (
                <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99,
                  background: "rgba(139,92,246,0.1)", color: T.purple, fontWeight: 600 }}>
                  Custom
                </span>
              )}
            </div>

            {/* Sub-tabs */}
            <div style={{ display: "flex", gap: 4, padding: "8px 16px", flexShrink: 0,
              borderBottom: `1px solid ${T.border}`, background: "#fafafa" }}>
              {PANEL_TABS.map(t => (
                <button key={t} onClick={() => setPanelTab(t)} style={panelTabBtn(t)}>{t}</button>
              ))}
              <div style={{ flex: 1 }} />
              {panelTab === "Edit" && (
                <span style={{ fontSize: 10, color: T.textSoft, alignSelf: "center" }}>
                  {lineCount} lines · {charCount.toLocaleString()} chars
                </span>
              )}
            </div>

            {/* Tab content */}
            <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>

              {/* ── Edit tab ── */}
              {panelTab === "Edit" && (
                <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: 16, gap: 10, overflow: "hidden" }}>
                  <textarea
                    style={taStyle}
                    value={currentText}
                    onChange={e => setEditing(d => ({ ...d, [activeKey]: e.target.value }))}
                    spellCheck={false}
                  />
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
                    <button
                      style={btnStyle("primary")}
                      onClick={handleSave}
                      disabled={saving || resetting}
                    >
                      {saving ? "Saving…" : saveOk ? "✓ Saved" : "Save"}
                    </button>
                    {isDirty && (
                      <button
                        style={btnStyle("secondary")}
                        onClick={() => setEditing(e => { const n = { ...e }; delete n[activeKey]; return n })}
                      >
                        Discard
                      </button>
                    )}
                    <div style={{ flex: 1 }} />
                    {active.is_custom && (
                      <button
                        style={btnStyle("danger")}
                        onClick={handleReset}
                        disabled={resetting || saving}
                      >
                        {resetting ? "Resetting…" : "Reset to Default"}
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* ── Versions tab ── */}
              {panelTab === "Versions" && (
                <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
                  {versionsLoading ? (
                    <div style={{ color: T.textSoft, fontSize: 12, textAlign: "center", paddingTop: 40 }}>
                      Loading versions…
                    </div>
                  ) : versions.length === 0 ? (
                    <div style={{ color: T.textSoft, fontSize: 12, textAlign: "center", paddingTop: 40 }}>
                      No saved versions yet. Versions are created automatically every time you save.
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {versions.map((v, idx) => (
                        <div key={idx} style={{
                          border: `1px solid ${T.border}`, borderRadius: 8, padding: "10px 14px",
                          background: "#fff",
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                            <span style={{ fontWeight: 700, fontSize: 12, color: T.text }}>{v.label || `v${versions.length - idx}`}</span>
                            <span style={{ fontSize: 11, color: T.textSoft }}>
                              {v.saved_at ? new Date(v.saved_at).toLocaleString() : ""}
                            </span>
                            <div style={{ flex: 1 }} />
                            <button
                              onClick={() => handleRestore(idx)}
                              disabled={restoring === idx}
                              style={{
                                padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                                border: `1px solid ${T.purple}`, background: "transparent",
                                color: T.purple, cursor: "pointer",
                                opacity: restoring === idx ? 0.5 : 1,
                              }}
                            >
                              {restoring === idx ? "Restoring…" : "Restore"}
                            </button>
                          </div>
                          <pre style={{
                            fontSize: 10, color: T.textSoft, margin: 0, whiteSpace: "pre-wrap",
                            maxHeight: 120, overflow: "hidden",
                            fontFamily: "ui-monospace, 'Cascadia Code', monospace",
                          }}>
                            {v.content?.slice(0, 400)}{v.content?.length > 400 ? "\n…" : ""}
                          </pre>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ── Test tab ── */}
              {panelTab === "▶ Test" && (
                <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>

                  {/* Model selector row */}
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <label style={{ fontSize: 11, fontWeight: 600, color: T.text }}>AI Model:</label>
                    <select
                      value={testProvider}
                      onChange={e => setTestProvider(e.target.value)}
                      style={{
                        fontSize: 11, padding: "4px 8px", borderRadius: 6,
                        border: `1px solid ${T.border}`, background: "#fff", cursor: "pointer",
                      }}
                    >
                      <option value="ollama">🦙 Ollama (Free)</option>
                      <option value="groq">⚡ Groq (Free)</option>
                      <option value="gemini">💎 Gemini Free</option>
                    </select>
                    <div style={{ flex: 1 }} />
                    <button
                      onClick={handleTest}
                      disabled={testRunning || !currentText}
                      style={{
                        padding: "6px 18px", borderRadius: 7, fontSize: 12, fontWeight: 600,
                        border: "none", cursor: testRunning ? "wait" : "pointer",
                        background: testRunning ? "#e5e5ea" : T.purple,
                        color: testRunning ? T.gray : "#fff",
                        opacity: testRunning ? 0.7 : 1,
                      }}
                    >
                      {testRunning ? "⏳ Running…" : "▶ Run Test"}
                    </button>
                  </div>

                  {/* Info note */}
                  <div style={{ fontSize: 10, color: T.textSoft, padding: "4px 0" }}>
                    Tests your <strong>current editor content</strong> (unsaved changes included) with sample data.
                  </div>

                  {/* Sample Variables (collapsible) */}
                  <div style={{ border: `1px solid ${T.border}`, borderRadius: 8, overflow: "hidden" }}>
                    <div
                      onClick={() => setShowVars(!showVars)}
                      style={{
                        padding: "8px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer",
                        background: "#fafafa", display: "flex", alignItems: "center", gap: 6,
                        color: T.text, userSelect: "none",
                      }}
                    >
                      <span style={{ fontSize: 10 }}>{showVars ? "▼" : "▶"}</span>
                      Sample Variables
                      <span style={{ fontSize: 10, color: T.textSoft, fontWeight: 400 }}>
                        (edit to customize test data)
                      </span>
                    </div>
                    {showVars && (
                      <textarea
                        value={sampleDataStr}
                        onChange={e => setSampleDataStr(e.target.value)}
                        style={{
                          width: "100%", minHeight: 120, maxHeight: 200, padding: "8px 12px",
                          fontSize: 11, fontFamily: "ui-monospace, monospace", lineHeight: 1.6,
                          border: "none", borderTop: `1px solid ${T.border}`, outline: "none",
                          resize: "vertical", boxSizing: "border-box", background: "#fff",
                        }}
                        spellCheck={false}
                      />
                    )}
                  </div>

                  {/* Error display */}
                  {testError && (
                    <div style={{
                      padding: "10px 14px", borderRadius: 8, fontSize: 12, lineHeight: 1.5,
                      background: "rgba(255,59,48,0.06)", border: `1px solid ${T.red}`,
                      color: T.red,
                    }}>
                      <strong>Error:</strong> {testError}
                    </div>
                  )}

                  {/* Test result */}
                  {testResult && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {/* Meta badges */}
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <span style={{
                          fontSize: 10, padding: "2px 8px", borderRadius: 99,
                          background: "rgba(52,199,89,0.1)", color: T.teal || "#34C759", fontWeight: 600,
                        }}>
                          {testResult.provider}
                        </span>
                        <span style={{
                          fontSize: 10, padding: "2px 8px", borderRadius: 99,
                          background: "rgba(139,92,246,0.08)", color: T.purple, fontWeight: 600,
                        }}>
                          {testResult.elapsed_seconds}s
                        </span>
                      </div>
                      {/* Response content */}
                      <div style={{
                        padding: "12px 14px", borderRadius: 8, fontSize: 12, lineHeight: 1.7,
                        background: "#f8f8fa", border: `1px solid ${T.border}`,
                        whiteSpace: "pre-wrap", wordBreak: "break-word",
                        maxHeight: 400, overflowY: "auto",
                        fontFamily: "ui-monospace, monospace",
                      }}>
                        {testResult.response || "(empty response)"}
                      </div>
                    </div>
                  )}

                  {/* Empty state */}
                  {!testResult && !testError && !testRunning && (
                    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
                      color: T.textSoft, fontSize: 12, paddingTop: 30 }}>
                      Click "▶ Run Test" to test this prompt with {testProvider === "ollama" ? "Ollama" : testProvider === "groq" ? "Groq" : "Gemini"}.
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
            color: T.textSoft, fontSize: 13 }}>
            Select a step to edit its prompt.
          </div>
        )}
      </div>
    </div>
  )
}
