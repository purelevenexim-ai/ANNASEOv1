import { useState, useEffect, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { T, api, Btn, Badge, Card } from "./App"

// ── Step grouping for sidebar navigation ────────────────────────────────────
const STEP_ORDER = [
  { prefix: "step1_",  step: 1,  label: "Research" },
  { prefix: "step2_",  step: 2,  label: "Structure" },
  { prefix: "step3_",  step: 3,  label: "Verify" },
  { prefix: "step4_",  step: 4,  label: "Links" },
  { prefix: "step5_",  step: 5,  label: "References" },
  { prefix: "step6_",  step: 6,  label: "Draft" },
  { prefix: "step7_",  step: 7,  label: "Review" },
  { prefix: "step9_",  step: 9,  label: "Redevelop" },
  { prefix: "step10_", step: 10, label: "Scoring" },
  { prefix: "step11_", step: 11, label: "Quality Loop" },
]

const VARS = [
  { name: "{keyword}", desc: "Target keyword" },
  { name: "{customer_context}", desc: "Brand, location, audience, business type" },
]

export default function PromptEditorPage() {
  const qc = useQueryClient()
  const { data, refetch, isLoading } = useQuery({
    queryKey: ["prompts"],
    queryFn: () => api.get("/api/prompts"),
  })

  const items = data?.prompts || []
  const [activeKey, setActiveKey] = useState(null)
  const [editValue, setEditValue] = useState("")
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [search, setSearch] = useState("")

  // Group prompts by step
  const grouped = STEP_ORDER.map(s => ({
    ...s,
    prompts: items.filter(p => p.key.startsWith(s.prefix)),
  })).filter(g => g.prompts.length > 0)

  const activePrompt = items.find(p => p.key === activeKey)

  // Auto-select first prompt
  useEffect(() => {
    if (!activeKey && items.length > 0) {
      setActiveKey(items[0].key)
      setEditValue(items[0].content || items[0].default || "")
      setDirty(false)
    }
  }, [items, activeKey])

  const selectPrompt = useCallback((p) => {
    if (dirty && !confirm("You have unsaved changes. Discard?")) return
    setActiveKey(p.key)
    setEditValue(p.content || p.default || "")
    setDirty(false)
  }, [dirty])

  const handleSave = async () => {
    if (!activeKey) return
    setSaving(true)
    try {
      await api.post(`/api/prompts/${activeKey}`, { content: editValue })
      await refetch()
      setDirty(false)
    } catch (e) {
      alert("Save failed: " + e.message)
    }
    setSaving(false)
  }

  const handleReset = async () => {
    if (!activeKey) return
    if (!confirm("Reset this prompt to its built-in default? Your custom version will be deleted.")) return
    setSaving(true)
    try {
      await api.delete(`/api/prompts/${activeKey}`)
      const fresh = await refetch()
      const updated = (fresh.data?.prompts || []).find(p => p.key === activeKey)
      if (updated) setEditValue(updated.default || "")
      setDirty(false)
    } catch (e) {
      alert("Reset failed: " + e.message)
    }
    setSaving(false)
  }

  const filteredGrouped = search.trim()
    ? grouped.map(g => ({
        ...g,
        prompts: g.prompts.filter(p =>
          p.label.toLowerCase().includes(search.toLowerCase()) ||
          p.key.toLowerCase().includes(search.toLowerCase()) ||
          p.desc.toLowerCase().includes(search.toLowerCase())
        ),
      })).filter(g => g.prompts.length > 0)
    : grouped

  if (isLoading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: T.textSoft }}>
      Loading prompts…
    </div>
  )

  return (
    <div style={{ display: "flex", height: "100%", fontFamily: T.bodyFont }}>
      {/* ── Left sidebar: step list ── */}
      <div style={{
        width: 260, minWidth: 260, borderRight: `1px solid ${T.border}`,
        display: "flex", flexDirection: "column", background: "#FAFAFA",
      }}>
        <div style={{ padding: "16px 14px 8px", borderBottom: `1px solid ${T.border}` }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: T.text, marginBottom: 10 }}>
            Pipeline Prompts
          </div>
          <input
            type="text" placeholder="Search prompts…" value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              width: "100%", padding: "7px 10px", fontSize: 12,
              border: `1px solid ${T.border}`, borderRadius: 8,
              outline: "none", background: "#fff", boxSizing: "border-box",
            }}
          />
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
          {filteredGrouped.map(g => (
            <div key={g.step}>
              <div style={{
                fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase",
                letterSpacing: 0.6, padding: "10px 14px 4px",
              }}>
                Step {g.step} — {g.label}
              </div>
              {g.prompts.map(p => (
                <div
                  key={p.key}
                  onClick={() => selectPrompt(p)}
                  style={{
                    padding: "8px 14px", cursor: "pointer", fontSize: 12,
                    display: "flex", alignItems: "center", gap: 6,
                    background: activeKey === p.key ? T.purpleLight : "transparent",
                    color: activeKey === p.key ? T.purple : T.text,
                    fontWeight: activeKey === p.key ? 600 : 400,
                    borderLeft: activeKey === p.key ? `3px solid ${T.purple}` : "3px solid transparent",
                  }}
                >
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {p.label.replace(/^Step \d+:\s*/, "")}
                  </span>
                  {p.is_custom && <Badge color="purple" size="xs">Custom</Badge>}
                </div>
              ))}
            </div>
          ))}
        </div>
        {/* Variable reference */}
        <div style={{ borderTop: `1px solid ${T.border}`, padding: "10px 14px" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", marginBottom: 6 }}>
            Variables
          </div>
          {VARS.map(v => (
            <div key={v.name} style={{ fontSize: 11, color: T.textSoft, marginBottom: 3 }}>
              <code style={{ background: T.grayLight, padding: "1px 4px", borderRadius: 3, fontSize: 10, color: T.purple }}>
                {v.name}
              </code>{" "}
              <span style={{ fontSize: 10 }}>{v.desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right panel: editor ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {activePrompt ? (
          <>
            {/* Header */}
            <div style={{
              padding: "14px 20px", borderBottom: `1px solid ${T.border}`,
              display: "flex", alignItems: "center", gap: 12,
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: T.text }}>
                  {activePrompt.label}
                </div>
                <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
                  {activePrompt.desc}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {activePrompt.is_custom && <Badge color="purple">Customised</Badge>}
                {dirty && <Badge color="amber">Unsaved</Badge>}
                {activePrompt.is_custom && (
                  <Btn size="sm" variant="ghost" onClick={handleReset} disabled={saving}>
                    Reset Default
                  </Btn>
                )}
                <Btn size="sm" onClick={handleSave} disabled={saving || !dirty}>
                  {saving ? "Saving…" : "Save"}
                </Btn>
              </div>
            </div>
            {/* Editor */}
            <div style={{ flex: 1, padding: 20, overflow: "auto" }}>
              <textarea
                value={editValue}
                onChange={e => { setEditValue(e.target.value); setDirty(true) }}
                spellCheck={false}
                style={{
                  width: "100%", height: "100%", minHeight: 500,
                  fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
                  fontSize: 12.5, lineHeight: 1.6, padding: 16,
                  border: `1px solid ${T.border}`, borderRadius: 10,
                  background: "#FDFDFD", color: T.text, resize: "vertical",
                  outline: "none", boxSizing: "border-box",
                  transition: "border-color 0.15s",
                }}
                onFocus={e => e.target.style.borderColor = T.purple}
                onBlur={e => e.target.style.borderColor = T.border}
              />
            </div>
            {/* Footer stats */}
            <div style={{
              padding: "8px 20px", borderTop: `1px solid ${T.border}`,
              display: "flex", gap: 16, fontSize: 11, color: T.textSoft,
            }}>
              <span>Key: <code style={{ color: T.purple }}>{activeKey}</code></span>
              <span>{editValue.length.toLocaleString()} chars</span>
              <span>{editValue.split("\n").length} lines</span>
            </div>
          </>
        ) : (
          <div style={{
            flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
            color: T.textSoft, fontSize: 13,
          }}>
            Select a prompt from the sidebar to edit
          </div>
        )}
      </div>
    </div>
  )
}
