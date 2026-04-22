/**
 * Kw2PromptStudio — modal overlay for editing KW2 AI prompts.
 * Accepts `filterPhases` (number[]) to show only prompts from those pipeline phases.
 * Usage:
 *   <Kw2PromptStudio filterPhases={[3, 5, 9]} onClose={() => setShow(false)} />
 *   <Kw2PromptStudio filterPhases={[2]}         onClose={() => setShow(false)} />
 */
import { useState, useEffect, useCallback } from "react"
import * as api from "./api"

const PHASE_LABELS = {
  2: "Strategy",
  3: "Question Module",
  5: "Enrichment",
  9: "Title Generation",
}

const PHASE_ICONS = {
  2: "🗺️",
  3: "❓",
  5: "🔍",
  9: "📝",
}

const T = {
  purple: "#007AFF", purpleLight: "rgba(0,122,255,0.1)", purpleDark: "#0040DD",
  teal: "#34C759", red: "#FF3B30", amber: "#FF9500",
  gray: "#8E8E93", border: "rgba(60,60,67,0.12)",
  text: "#000000", textSoft: "rgba(60,60,67,0.55)",
}

export default function Kw2PromptStudio({ filterPhases, onClose }) {
  const [allPrompts, setAllPrompts] = useState([])
  const [activeKey, setActiveKey] = useState(null)
  const [template, setTemplate] = useState("")
  const [originalTemplate, setOriginalTemplate] = useState("")
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveOk, setSaveOk] = useState(false)
  const [panelTab, setPanelTab] = useState("Edit")
  const [versions, setVersions] = useState([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [restoring, setRestoring] = useState(null)

  // Test tab state
  const [testProvider, setTestProvider] = useState("ollama")
  const [testResult, setTestResult] = useState(null)
  const [testRunning, setTestRunning] = useState(false)
  const [testError, setTestError] = useState(null)
  const [sampleData, setSampleData] = useState(null)
  const [sampleDataStr, setSampleDataStr] = useState("")
  const [sampleLoading, setSampleLoading] = useState(false)
  const [showVars, setShowVars] = useState(false)

  // Filter to requested phases
  const prompts = filterPhases
    ? allPrompts.filter(p => filterPhases.includes(p.phase))
    : allPrompts

  const activePrompt = prompts.find(p => p.prompt_key === activeKey)
  const isDirty = template !== originalTemplate
  const isSystem = activePrompt?.is_system === 1

  // Load prompt list
  const loadPrompts = useCallback(() => {
    api.listPrompts().then(d => {
      const list = d.prompts || []
      setAllPrompts(list)
      if (!activeKey && list.length) {
        const filtered = filterPhases ? list.filter(p => filterPhases.includes(p.phase)) : list
        if (filtered.length) setActiveKey(filtered[0].prompt_key)
      }
    }).catch(() => {})
  }, []) // eslint-disable-line

  useEffect(() => { loadPrompts() }, []) // eslint-disable-line

  // Load full template when active key changes
  useEffect(() => {
    if (!activeKey) return
    setLoadingDetail(true)
    setPanelTab("Edit")
    api.getPromptDetail(activeKey)
      .then(d => {
        const t = d?.template ?? d?.content ?? ""
        setTemplate(t)
        setOriginalTemplate(t)
      })
      .catch(() => { setTemplate(""); setOriginalTemplate("") })
      .finally(() => setLoadingDetail(false))
  }, [activeKey])

  // Load versions when switching to Versions tab
  useEffect(() => {
    if (panelTab !== "Versions" || !activeKey) return
    setVersionsLoading(true)
    api.getPromptVersions(activeKey)
      .then(d => setVersions(d.versions || []))
      .catch(() => setVersions([]))
      .finally(() => setVersionsLoading(false))
  }, [panelTab, activeKey])

  // Load sample data when switching to Test tab
  useEffect(() => {
    if (panelTab !== "Test" || !activeKey) return
    setSampleLoading(true)
    setTestResult(null)
    setTestError(null)
    api.getPromptSampleData(activeKey)
      .then(d => {
        const sd = d.sample_data || {}
        setSampleData(sd)
        // Remove internal keys for display
        const display = { ...sd }
        delete display._test_user_prompt
        delete display._meta
        setSampleDataStr(JSON.stringify(display, null, 2))
      })
      .catch(() => { setSampleData({}); setSampleDataStr("{}") })
      .finally(() => setSampleLoading(false))
  }, [panelTab, activeKey])

  const handleTest = async () => {
    if (!activeKey || !template) return
    setTestRunning(true)
    setTestResult(null)
    setTestError(null)
    try {
      let parsedOverrides = null
      try { parsedOverrides = JSON.parse(sampleDataStr) } catch { parsedOverrides = null }
      const res = await api.testPrompt(activeKey, template, testProvider, parsedOverrides)
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
    if (!activeKey || isSystem) return
    setSaving(true)
    try {
      await api.updatePrompt(activeKey, template)
      setOriginalTemplate(template)
      setSaveOk(true)
      setTimeout(() => setSaveOk(false), 2000)
      loadPrompts()
    } catch (e) { alert(e?.message || "Save failed") }
    setSaving(false)
  }

  const handleRestore = async (version) => {
    if (!activeKey) return
    setRestoring(version.version)
    try {
      await api.restorePromptVersion(activeKey, version.version)
      // Reload detail
      const d = await api.getPromptDetail(activeKey)
      const t = d?.template ?? d?.content ?? ""
      setTemplate(t)
      setOriginalTemplate(t)
      // Reload versions
      const vd = await api.getPromptVersions(activeKey)
      setVersions(vd.versions || [])
      setPanelTab("Edit")
      loadPrompts()
    } catch (e) { alert(e?.message || "Restore failed") }
    setRestoring(null)
  }

  const handleSelectStep = (key) => {
    setActiveKey(key)
    setPanelTab("Edit")
  }

  // Close on backdrop click
  const handleBackdrop = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  // Group visible prompts by phase
  const byPhase = prompts.reduce((acc, p) => {
    if (!acc[p.phase]) acc[p.phase] = []
    acc[p.phase].push(p)
    return acc
  }, {})

  // ── Styles ───────────────────────────────────────────────────────────────────

  const sidebarStyle = {
    width: 220, flexShrink: 0, borderRight: `1px solid ${T.border}`,
    display: "flex", flexDirection: "column", overflowY: "auto", background: "#fafafa",
  }

  const stepItem = (key, isActive) => ({
    padding: "8px 14px", cursor: "pointer",
    borderLeft: isActive ? `3px solid ${T.purple}` : "3px solid transparent",
    background: isActive ? T.purpleLight : "transparent",
    display: "flex", alignItems: "center", gap: 8, fontSize: 12,
    fontWeight: isActive ? 600 : 400,
    color: isActive ? T.purple : T.text,
  })

  const tabBtn = (label) => ({
    padding: "5px 14px", fontSize: 12, fontWeight: 500, borderRadius: 99,
    border: "none", cursor: "pointer",
    background: panelTab === label ? T.purple : "transparent",
    color: panelTab === label ? "#fff" : T.gray,
  })

  const taStyle = {
    width: "100%", flex: 1, padding: "12px 14px", fontSize: 12, lineHeight: 1.7,
    border: `1px solid ${isDirty && !isSystem ? T.purple : T.border}`, borderRadius: 8,
    fontFamily: "ui-monospace, 'Cascadia Code', 'Fira Code', monospace",
    resize: "none", outline: "none", background: isSystem ? "#f8f8fa" : "#fff",
    color: isSystem ? T.textSoft : T.text, boxSizing: "border-box",
  }

  const charCount = template.length
  const lineCount = template.split("\n").length

  return (
    <div
      onClick={handleBackdrop}
      style={{
        position: "fixed", inset: 0, zIndex: 1100,
        background: "rgba(0,0,0,0.4)", display: "flex",
        alignItems: "center", justifyContent: "center", padding: 20,
      }}
    >
      <div
        style={{
          background: "#fff", borderRadius: 14, width: "100%", maxWidth: 940,
          height: "82vh", display: "flex", flexDirection: "column",
          boxShadow: "0 24px 72px rgba(0,0,0,0.25)", overflow: "hidden",
        }}
      >
        {/* ── Modal header ─────────────────────────────────────────────────── */}
        <div style={{
          padding: "14px 18px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", gap: 10, flexShrink: 0,
        }}>
          <span style={{ fontSize: 18 }}>🧪</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: T.text }}>Prompt Studio</div>
            <div style={{ fontSize: 11, color: T.textSoft }}>
              {filterPhases ? filterPhases.map(p => PHASE_LABELS[p] || `Phase ${p}`).join(" · ") : "All phases"} · {prompts.length} prompts
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: T.gray, padding: "2px 6px" }}
          >✕</button>
        </div>

        {/* ── Body: sidebar + editor ────────────────────────────────────────── */}
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

          {/* Sidebar */}
          <div style={sidebarStyle}>
            {Object.entries(byPhase).map(([phase, phasePrompts]) => (
              <div key={phase}>
                <div style={{
                  padding: "10px 14px 4px", fontSize: 9, fontWeight: 700, color: T.textSoft,
                  textTransform: "uppercase", letterSpacing: 0.5, display: "flex", alignItems: "center", gap: 5,
                }}>
                  <span>{PHASE_ICONS[phase] || "⚙️"}</span>
                  <span>{PHASE_LABELS[phase] || `Phase ${phase}`}</span>
                </div>
                {phasePrompts.map(p => (
                  <div key={p.prompt_key} onClick={() => handleSelectStep(p.prompt_key)} style={stepItem(p.prompt_key, p.prompt_key === activeKey)}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {p.display_name}
                      </div>
                      {p.is_system === 1 && (
                        <div style={{ fontSize: 9, color: T.amber, marginTop: 1 }}>⚙ system</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>

          {/* Editor panel */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
            {activePrompt ? (
              <>
                {/* Step header */}
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${T.border}`,
                  display: "flex", alignItems: "center", gap: 10, flexShrink: 0, background: "#fff" }}>
                  <span style={{ fontSize: 16 }}>{PHASE_ICONS[activePrompt.phase] || "⚙️"}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>{activePrompt.display_name}</div>
                    {activePrompt.description && (
                      <div style={{ fontSize: 11, color: T.textSoft, marginTop: 1 }}>{activePrompt.description}</div>
                    )}
                  </div>
                  {activePrompt.is_system === 1 && (
                    <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99,
                      background: "rgba(255,149,0,0.1)", color: T.amber, fontWeight: 600 }}>
                      System (read-only)
                    </span>
                  )}
                  {activePrompt.version > 1 && (
                    <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99,
                      background: "rgba(0,122,255,0.08)", color: T.purple, fontWeight: 600 }}>
                      v{activePrompt.version}
                    </span>
                  )}
                </div>

                {/* Sub-tabs */}
                <div style={{ display: "flex", gap: 4, padding: "8px 16px", flexShrink: 0,
                  borderBottom: `1px solid ${T.border}`, background: "#fafafa" }}>
                  <button style={tabBtn("Edit")} onClick={() => setPanelTab("Edit")}>Edit</button>
                  <button style={tabBtn("Versions")} onClick={() => setPanelTab("Versions")}>Versions</button>
                  <button style={tabBtn("Test")} onClick={() => setPanelTab("Test")}>▶ Test</button>
                  <div style={{ flex: 1 }} />
                  {panelTab === "Edit" && (
                    <span style={{ fontSize: 10, color: T.textSoft, alignSelf: "center" }}>
                      {lineCount} lines · {charCount.toLocaleString()} chars
                    </span>
                  )}
                </div>

                {/* Tab content */}
                <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>

                  {/* ── Edit ── */}
                  {panelTab === "Edit" && (
                    <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: 16, gap: 10, overflow: "hidden" }}>
                      {loadingDetail ? (
                        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: T.textSoft, fontSize: 12 }}>
                          Loading…
                        </div>
                      ) : (
                        <textarea
                          style={taStyle}
                          value={template}
                          onChange={e => !isSystem && setTemplate(e.target.value)}
                          readOnly={isSystem}
                          spellCheck={false}
                        />
                      )}
                      {!loadingDetail && (
                        <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
                          {!isSystem ? (
                            <>
                              <button
                                onClick={handleSave}
                                disabled={saving || !isDirty}
                                style={{
                                  padding: "6px 16px", borderRadius: 7, fontSize: 12, fontWeight: 600,
                                  border: "none", cursor: isDirty ? "pointer" : "default",
                                  background: isDirty ? T.purple : "#e5e5ea",
                                  color: isDirty ? "#fff" : T.gray,
                                  opacity: saving ? 0.6 : 1,
                                }}
                              >
                                {saving ? "Saving…" : saveOk ? "✓ Saved" : "Save"}
                              </button>
                              {isDirty && (
                                <button
                                  onClick={() => setTemplate(originalTemplate)}
                                  style={{ padding: "6px 14px", borderRadius: 7, fontSize: 12, fontWeight: 600,
                                    border: `1px solid ${T.border}`, background: "transparent", color: T.gray, cursor: "pointer" }}
                                >
                                  Discard
                                </button>
                              )}
                            </>
                          ) : (
                            <span style={{ fontSize: 11, color: T.amber }}>
                              ⚠ System prompts are read-only.
                            </span>
                          )}
                          <div style={{ flex: 1 }} />
                          {activePrompt.updated_at && (
                            <span style={{ fontSize: 10, color: T.textSoft }}>
                              Updated {new Date(activePrompt.updated_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* ── Versions ── */}
                  {panelTab === "Versions" && (
                    <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
                      {versionsLoading ? (
                        <div style={{ color: T.textSoft, fontSize: 12, textAlign: "center", paddingTop: 40 }}>
                          Loading versions…
                        </div>
                      ) : versions.length === 0 ? (
                        <div style={{ color: T.textSoft, fontSize: 12, textAlign: "center", paddingTop: 40 }}>
                          No saved versions yet. Every save creates a version automatically.
                        </div>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                          {versions.map((v, idx) => (
                            <div key={v.version ?? idx} style={{
                              border: `1px solid ${T.border}`, borderRadius: 8, padding: "10px 14px", background: "#fff",
                            }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                                <span style={{ fontWeight: 700, fontSize: 12, color: T.text }}>v{v.version}</span>
                                <span style={{ fontSize: 11, color: T.textSoft }}>
                                  {v.created_at ? new Date(v.created_at).toLocaleString() : ""}
                                </span>
                                {v.edited_by && (
                                  <span style={{ fontSize: 10, color: T.gray }}>by {v.edited_by}</span>
                                )}
                                <div style={{ flex: 1 }} />
                                {!isSystem && (
                                  <button
                                    onClick={() => handleRestore(v)}
                                    disabled={restoring === v.version}
                                    style={{
                                      padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600,
                                      border: `1px solid ${T.purple}`, background: "transparent",
                                      color: T.purple, cursor: "pointer",
                                      opacity: restoring === v.version ? 0.5 : 1,
                                    }}
                                  >
                                    {restoring === v.version ? "Restoring…" : "Restore"}
                                  </button>
                                )}
                              </div>
                              <pre style={{
                                fontSize: 10, color: T.textSoft, margin: 0, whiteSpace: "pre-wrap",
                                maxHeight: 120, overflow: "hidden",
                                fontFamily: "ui-monospace, 'Cascadia Code', monospace",
                              }}>
                                {(v.template || v.content || "").slice(0, 400)}
                                {(v.template || v.content || "").length > 400 ? "\n…" : ""}
                              </pre>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* ── Test ── */}
                  {panelTab === "Test" && (
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
                          disabled={testRunning || !template}
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
                        {isSystem && " System prompts are tested with a fixed user message."}
                      </div>

                      {/* Sample Variables (collapsible) */}
                      {!isSystem && (
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
                      )}

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
                              background: "rgba(52,199,89,0.1)", color: T.teal, fontWeight: 600,
                            }}>
                              {testResult.provider}
                            </span>
                            <span style={{
                              fontSize: 10, padding: "2px 8px", borderRadius: 99,
                              background: "rgba(0,122,255,0.08)", color: T.purple, fontWeight: 600,
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
                          color: T.textSoft, fontSize: 12, paddingTop: 30  }}>
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
                Select a prompt to edit.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
