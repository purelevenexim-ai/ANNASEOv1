// Business Story Tab — R2 Knowledge Engine
// Two-panel layout: product list (left) + detail (right, snippets by kind + plots panel)
// Features: snippet AI typeahead, plot lifecycle management, story mode toggle.

import { useState, useEffect, useRef, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { T, api, useStore } from "../App"

// ── Kind taxonomy ─────────────────────────────────────────────────────────────
const KIND_GROUPS = {
  "Core": ["flagship_product","secondary_product","hero_ingredient","key_process"],
  "Identity": ["founder_fact","brand_value","origin_story","region_claim","certification"],
  "Customer": ["customer_result","testimonial","common_objection","faq"],
  "Sales": ["differentiator","competitor_contrast","use_case","price_anchor"],
  "Content": ["content_anchor","seo_hook","other"],
}
const ALL_KINDS = Object.values(KIND_GROUPS).flat()

const KIND_LABEL = {
  flagship_product: "Flagship Product", secondary_product: "Secondary Product",
  hero_ingredient: "Hero Ingredient", key_process: "Key Process",
  founder_fact: "Founder Fact", brand_value: "Brand Value", origin_story: "Origin Story",
  region_claim: "Region Claim", certification: "Certification",
  customer_result: "Customer Result", testimonial: "Testimonial",
  common_objection: "Common Objection", faq: "FAQ",
  differentiator: "Differentiator", competitor_contrast: "Competitor Contrast",
  use_case: "Use Case", price_anchor: "Price Anchor",
  content_anchor: "Content Anchor", seo_hook: "SEO Hook", other: "Other",
}

const KIND_COLOR = {
  flagship_product: "#FF3B30", secondary_product: "#FF9500", hero_ingredient: "#34C759",
  key_process: "#007AFF", founder_fact: "#5856D6", brand_value: "#AF52DE",
  origin_story: "#FF2D55", region_claim: "#00B0FF", certification: "#34C759",
  customer_result: "#007AFF", testimonial: "#5856D6", common_objection: "#FF9500",
  faq: "#00897B", differentiator: "#FF3B30", competitor_contrast: "#FF2D55",
  use_case: "#007AFF", price_anchor: "#FF9500", content_anchor: "#8E8E93",
  seo_hook: "#007AFF", other: "#8E8E93",
}

const PLOT_TYPE_OPTIONS = [
  { v: "hero", label: "Hero", desc: "Central brand narrative" },
  { v: "supporting", label: "Supporting", desc: "Complementary context" },
  { v: "contrast", label: "Contrast", desc: "What we're not / vs. competitors" },
]

const CONFIDENCE_OPTIONS = ["verified","probable","hypothesis"]
const SOURCE_OPTIONS = ["founder_input","ai_generated","customer_research","market_data"]

// ── Helpers ───────────────────────────────────────────────────────────────────
function Badge({ text, color = T.purple }) {
  return (
    <span style={{
      display: "inline-block", fontSize: 10, fontWeight: 700, letterSpacing: 0.3,
      padding: "2px 7px", borderRadius: 20,
      background: color + "22", color,
    }}>
      {text}
    </span>
  )
}

function Btn({ children, onClick, disabled, variant = "default", small, style: sx }) {
  const base = {
    border: "none", cursor: disabled ? "not-allowed" : "pointer", borderRadius: 8,
    fontFamily: T.bodyFont, fontWeight: 600, transition: "opacity .15s",
    opacity: disabled ? 0.5 : 1, ...sx,
  }
  if (variant === "primary") {
    Object.assign(base, { background: T.purple, color: "#fff", padding: small ? "5px 12px" : "8px 18px", fontSize: small ? 12 : 13 })
  } else if (variant === "danger") {
    Object.assign(base, { background: T.red + "18", color: T.red, padding: small ? "5px 12px" : "8px 18px", fontSize: small ? 12 : 13 })
  } else if (variant === "outline") {
    Object.assign(base, { background: "transparent", color: T.purple, border: `1px solid ${T.purple}`, padding: small ? "4px 11px" : "7px 16px", fontSize: small ? 12 : 13 })
  } else {
    Object.assign(base, { background: T.grayLight, color: T.text, padding: small ? "5px 12px" : "8px 14px", fontSize: small ? 12 : 13 })
  }
  return <button style={base} onClick={onClick} disabled={disabled}>{children}</button>
}

function useDebounce(value, delay = 600) {
  const [dv, setDv] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDv(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return dv
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function BusinessStoryTab() {
  const { activeProject, setProject } = useStore()
  // activeProject is the project_id string (per useStore in App.jsx)
  const pid = typeof activeProject === "string" ? activeProject : activeProject?.project_id
  const qc = useQueryClient()

  // Project list (for inline selector when no project is active)
  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get("/api/projects").then(r => r?.projects || []),
    staleTime: 60_000,
  })
  const projects = projectsData || []

  // ── Remote state ─────────────────────────────────────────────────────────
  const { data: full, isLoading } = useQuery({
    queryKey: ["bs-full", pid],
    queryFn: () => api.get(`/api/bs/${pid}/full`),
    enabled: !!pid,
  })

  // ── Story mode toggle ─────────────────────────────────────────────────────
  const storyModeMut = useMutation({
    mutationFn: (mode) => api.put(`/api/bs/${pid}/story-mode`, { story_mode: mode }),
    onSuccess: () => qc.invalidateQueries(["bs-full", pid]),
  })
  const storyMode = full?.story_mode || "on"

  // ── Panel state ───────────────────────────────────────────────────────────
  const [selectedProductId, setSelectedProductId] = useState(null) // null = project-level
  const [activeTab, setActiveTab] = useState("snippets") // "snippets" | "plots"
  const [activeKindGroup, setActiveKindGroup] = useState("Core")

  const products = full?.products || []
  const projectSnippets = full?.project_snippets || []
  const plots = full?.plots || []

  // Determine currently-viewed snippets
  const selectedProduct = products.find(p => p.id === selectedProductId) || null
  const viewSnippets = selectedProductId
    ? (selectedProduct?.snippets || [])
    : projectSnippets

  // ── Auto-select first product if none selected ────────────────────────────
  useEffect(() => {
    if (products.length > 0 && selectedProductId === null) {
      setSelectedProductId(products[0].id)
    }
  }, [products])

  // ── No project selected → show picker ────────────────────────────────────
  if (!pid) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 320, gap: 16 }}>
        <div style={{ fontSize: 15, fontWeight: 600, color: T.text }}>Brand Knowledge Engine</div>
        <div style={{ fontSize: 13, color: T.textSoft }}>Select a project to view and manage brand knowledge</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", maxWidth: 600 }}>
          {projects.map(p => (
            <button key={p.project_id} onClick={() => setProject(p.project_id)}
              style={{
                padding: "8px 18px", borderRadius: 8, border: `1px solid ${T.border}`,
                background: "#fff", cursor: "pointer", fontSize: 13, color: T.text,
                boxShadow: "0 1px 3px rgba(0,0,0,0.06)", transition: "box-shadow .15s",
              }}>
              {p.name || p.project_id}
            </button>
          ))}
          {projects.length === 0 && (
            <div style={{ fontSize: 12, color: T.textSoft }}>No projects yet — create one from the Dashboard.</div>
          )}
        </div>
      </div>
    )
  }

  if (isLoading) return <div style={{ padding: 32, color: T.textSoft }}>Loading…</div>

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 0 }}>
      {/* ── Top bar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 20px", borderBottom: `1px solid ${T.border}`,
        background: "#fff",
      }}>
        <div>
          <span style={{ fontSize: 15, fontWeight: 700, color: T.text }}>Brand Knowledge Engine</span>
          <span style={{ fontSize: 11, color: T.textSoft, marginLeft: 10 }}>
            Snap in brand truths → AI weaves them into every article
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {/* Project selector — always visible in active state */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, color: T.textSoft }}>Project:</span>
            <select
              value={pid || ""}
              onChange={e => e.target.value && setProject(e.target.value)}
              style={{
                fontSize: 12, padding: "4px 8px", borderRadius: 6,
                border: `1px solid ${T.border}`, background: "#fff",
                color: T.text, cursor: "pointer", maxWidth: 200,
              }}
            >
              {projects.map(p => (
                <option key={p.project_id} value={p.project_id}>{p.name || p.project_id}</option>
              ))}
            </select>
          </div>

          <span style={{ fontSize: 12, color: T.textSoft }}>Story mode</span>
          <button
            onClick={() => storyModeMut.mutate(storyMode === "on" ? "off" : "on")}
            style={{
              width: 44, height: 24, borderRadius: 12, border: "none", cursor: "pointer",
              background: storyMode === "on" ? T.purple : T.border,
              position: "relative", transition: "background .2s",
            }}
          >
            <span style={{
              position: "absolute", top: 2, left: storyMode === "on" ? 22 : 2,
              width: 20, height: 20, borderRadius: 10, background: "#fff",
              transition: "left .2s", boxShadow: "0 1px 3px rgba(0,0,0,.25)",
            }} />
          </button>
          <span style={{ fontSize: 11, color: storyMode === "on" ? T.purple : T.textSoft, fontWeight: 600 }}>
            {storyMode === "on" ? "ON" : "OFF"}
          </span>
        </div>
      </div>

      {storyMode === "off" && (
        <div style={{ margin: "12px 20px 0", padding: "10px 14px", borderRadius: 8, background: T.amber + "18", color: T.amber, fontSize: 12 }}>
          Story mode is OFF — brand knowledge won't be injected into content prompts. Toggle ON to activate.
        </div>
      )}

      {/* ── Two-panel layout */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* ── LEFT: product list */}
        <ProductPanel
          products={products}
          selectedProductId={selectedProductId}
          onSelect={setSelectedProductId}
          pid={pid}
          qc={qc}
        />

        {/* ── RIGHT: detail */}
        <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
          {/* Sub-tabs */}
          <div style={{ display: "flex", gap: 4, marginBottom: 16 }}>
            {["snippets", "plots"].map(t => (
              <button key={t} onClick={() => setActiveTab(t)} style={{
                padding: "6px 16px", borderRadius: 8, border: "none", cursor: "pointer",
                background: activeTab === t ? T.purple : T.grayLight,
                color: activeTab === t ? "#fff" : T.text,
                fontSize: 12, fontWeight: 600, fontFamily: T.bodyFont,
              }}>
                {t === "snippets" ? "Knowledge Snippets" : `Narrative Plots (${plots.filter(p => p.status === "active").length} active)`}
              </button>
            ))}
          </div>

          {activeTab === "snippets" && (
            <SnippetsPanel
              snippets={viewSnippets}
              productId={selectedProductId}
              productName={selectedProduct?.name || "Project-level"}
              pid={pid}
              qc={qc}
              activeKindGroup={activeKindGroup}
              onKindGroupChange={setActiveKindGroup}
            />
          )}

          {activeTab === "plots" && (
            <PlotsPanel
              plots={plots}
              productId={selectedProductId}
              productName={selectedProduct?.name || ""}
              pid={pid}
              qc={qc}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// ── Product Panel (left sidebar) ──────────────────────────────────────────────
function ProductPanel({ products, selectedProductId, onSelect, pid, qc }) {
  const [adding, setAdding] = useState(false)
  const [newName, setNewName] = useState("")

  const createMut = useMutation({
    mutationFn: (data) => api.post(`/api/bs/${pid}/products`, data),
    onSuccess: (created) => {
      qc.invalidateQueries(["bs-full", pid])
      onSelect(created.id)
      setAdding(false)
      setNewName("")
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id) => api.delete(`/api/bs/${pid}/products/${id}`),
    onSuccess: () => {
      qc.invalidateQueries(["bs-full", pid])
      onSelect(null)
    },
  })

  return (
    <div style={{
      width: 220, borderRight: `1px solid ${T.border}`, background: T.grayLight,
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      <div style={{ padding: "12px 14px 8px", fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5 }}>
        Products / Services
      </div>
      <div style={{ flex: 1, overflow: "auto" }}>
        {/* Project-level snippets entry */}
        <SidebarItem
          label="Brand-level"
          active={selectedProductId === null}
          onClick={() => onSelect(null)}
          icon="🏷️"
        />
        {products.filter(p => p.is_active).map(p => (
          <SidebarItem
            key={p.id}
            label={p.name}
            active={selectedProductId === p.id}
            onClick={() => onSelect(p.id)}
            icon={p.type === "service" ? "⚙️" : "📦"}
            onDelete={() => {
              if (window.confirm(`Remove "${p.name}"?`)) deleteMut.mutate(p.id)
            }}
          />
        ))}
      </div>
      <div style={{ padding: 12, borderTop: `1px solid ${T.border}` }}>
        {adding ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <input
              autoFocus
              placeholder="Product name"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && newName.trim()) createMut.mutate({ name: newName.trim() })
                if (e.key === "Escape") { setAdding(false); setNewName("") }
              }}
              style={{ fontSize: 12, padding: "5px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontFamily: T.bodyFont }}
            />
            <div style={{ display: "flex", gap: 6 }}>
              <Btn small variant="primary" onClick={() => newName.trim() && createMut.mutate({ name: newName.trim() })}>Add</Btn>
              <Btn small onClick={() => { setAdding(false); setNewName("") }}>Cancel</Btn>
            </div>
          </div>
        ) : (
          <Btn small variant="outline" onClick={() => setAdding(true)} style={{ width: "100%" }}>+ Add Product</Btn>
        )}
      </div>
    </div>
  )
}

function SidebarItem({ label, active, onClick, icon, onDelete }) {
  const [hover, setHover] = useState(false)
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "8px 14px", cursor: "pointer",
        background: active ? T.purple + "18" : hover ? T.border : "transparent",
        borderLeft: active ? `3px solid ${T.purple}` : "3px solid transparent",
      }}
    >
      <span style={{ fontSize: 12, color: active ? T.purple : T.text, fontWeight: active ? 700 : 400, display: "flex", alignItems: "center", gap: 6 }}>
        <span>{icon}</span>{label}
      </span>
      {onDelete && hover && (
        <button
          onClick={e => { e.stopPropagation(); onDelete() }}
          style={{ border: "none", background: "none", cursor: "pointer", fontSize: 12, color: T.textSoft, padding: "0 2px" }}
        >
          ×
        </button>
      )}
    </div>
  )
}

// ── Snippets Panel ────────────────────────────────────────────────────────────
function SnippetsPanel({ snippets, productId, productName, pid, qc, activeKindGroup, onKindGroupChange }) {
  const [editingId, setEditingId] = useState(null)
  const [newSnippet, setNewSnippet] = useState(null) // null or {kind, text, confidence, source}
  const [typeaheadResults, setTypeaheadResults] = useState([])
  const [typeaheadLoading, setTypeaheadLoading] = useState(false)
  const [typeaheadKind, setTypeaheadKind] = useState("flagship_product")

  const createMut = useMutation({
    mutationFn: (data) => api.post(`/api/bs/${pid}/snippets`, data),
    onSuccess: () => { qc.invalidateQueries(["bs-full", pid]); setNewSnippet(null) },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, ...data }) => api.put(`/api/bs/${pid}/snippets/${id}`, data),
    onSuccess: () => { qc.invalidateQueries(["bs-full", pid]); setEditingId(null) },
  })

  const deleteMut = useMutation({
    mutationFn: (id) => api.delete(`/api/bs/${pid}/snippets/${id}`),
    onSuccess: () => qc.invalidateQueries(["bs-full", pid]),
  })

  const activeKindsList = KIND_GROUPS[activeKindGroup] || []
  const groupSnippets = snippets.filter(s => activeKindsList.includes(s.kind))

  const runTypeahead = useCallback(async () => {
    setTypeaheadLoading(true)
    setTypeaheadResults([])
    try {
      const res = await api.post(`/api/bs/${pid}/snippets/typeahead`, {
        kind: typeaheadKind,
        product_name: productName,
        partial: "",
      })
      setTypeaheadResults(res.suggestions || [])
    } finally {
      setTypeaheadLoading(false)
    }
  }, [pid, typeaheadKind, productName])

  return (
    <div>
      {/* Kind group tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 14, flexWrap: "wrap" }}>
        {Object.keys(KIND_GROUPS).map(g => (
          <button key={g} onClick={() => onKindGroupChange(g)} style={{
            padding: "4px 12px", borderRadius: 20, border: "none", cursor: "pointer",
            background: activeKindGroup === g ? T.text : T.grayLight,
            color: activeKindGroup === g ? "#fff" : T.text,
            fontSize: 11, fontWeight: 600, fontFamily: T.bodyFont,
          }}>
            {g} ({snippets.filter(s => KIND_GROUPS[g].includes(s.kind)).length})
          </button>
        ))}
      </div>

      {/* Add snippet button */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        <Btn small variant="primary" onClick={() => setNewSnippet({ kind: activeKindsList[0] || "other", text: "", confidence: "verified", source: "founder_input" })}>
          + Add Snippet
        </Btn>
        <Btn small variant="outline" onClick={runTypeahead} disabled={typeaheadLoading}>
          {typeaheadLoading ? "Thinking…" : "✨ AI Suggest"}
        </Btn>
        {!typeaheadLoading && (
          <select
            value={typeaheadKind}
            onChange={e => setTypeaheadKind(e.target.value)}
            style={{ fontSize: 11, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontFamily: T.bodyFont }}
          >
            {ALL_KINDS.map(k => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        )}
      </div>

      {/* AI typeahead results */}
      {typeaheadResults.length > 0 && (
        <div style={{ marginBottom: 14, padding: 12, background: T.purple + "08", borderRadius: 10, border: `1px solid ${T.purple}30` }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, marginBottom: 8 }}>AI Suggestions — click to add</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {typeaheadResults.map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                <span style={{ fontSize: 12, color: T.text, flex: 1, lineHeight: 1.5 }}>{s}</span>
                <Btn small variant="outline" onClick={() => {
                  createMut.mutate({ text: s, kind: typeaheadKind, product_id: productId || "", confidence: "ai_generated", source: "ai_generated" })
                  setTypeaheadResults(prev => prev.filter((_, j) => j !== i))
                }}>
                  Add
                </Btn>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* New snippet form */}
      {newSnippet && (
        <SnippetForm
          initial={newSnippet}
          kindOptions={activeKindsList}
          onSave={(data) => createMut.mutate({ ...data, product_id: productId || "" })}
          onCancel={() => setNewSnippet(null)}
          loading={createMut.isPending}
        />
      )}

      {/* Snippet list */}
      {groupSnippets.length === 0 && !newSnippet && (
        <div style={{ color: T.textSoft, fontSize: 12, padding: "12px 0" }}>
          No {activeKindGroup.toLowerCase()} snippets yet — add one or use AI Suggest.
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {groupSnippets.map(s => (
          editingId === s.id
            ? <SnippetForm
                key={s.id}
                initial={s}
                kindOptions={ALL_KINDS}
                onSave={(data) => updateMut.mutate({ id: s.id, ...data })}
                onCancel={() => setEditingId(null)}
                loading={updateMut.isPending}
              />
            : <SnippetCard
                key={s.id}
                snippet={s}
                onEdit={() => setEditingId(s.id)}
                onDelete={() => deleteMut.mutate(s.id)}
              />
        ))}
      </div>
    </div>
  )
}

function SnippetCard({ snippet, onEdit, onDelete }) {
  const color = KIND_COLOR[snippet.kind] || T.purple
  return (
    <div style={{
      background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: "10px 14px",
      display: "flex", flexDirection: "column", gap: 6,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <Badge text={KIND_LABEL[snippet.kind] || snippet.kind} color={color} />
          <Badge text={snippet.confidence} color={snippet.confidence === "verified" ? T.teal : T.amber} />
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <Btn small onClick={onEdit}>Edit</Btn>
          <Btn small variant="danger" onClick={() => window.confirm("Delete snippet?") && onDelete()}>×</Btn>
        </div>
      </div>
      <div style={{ fontSize: 13, color: T.text, lineHeight: 1.55 }}>{snippet.text}</div>
      {snippet.usage_count > 0 && (
        <div style={{ fontSize: 10, color: T.textSoft }}>Used {snippet.usage_count}× · avg score {snippet.avg_performance?.toFixed(2)}</div>
      )}
    </div>
  )
}

function SnippetForm({ initial, kindOptions, onSave, onCancel, loading }) {
  const [text, setText] = useState(initial.text || "")
  const [kind, setKind] = useState(initial.kind || "other")
  const [confidence, setConfidence] = useState(initial.confidence || "verified")
  const [source, setSource] = useState(initial.source || "founder_input")

  return (
    <div style={{ background: T.purple + "06", border: `1px solid ${T.purple}30`, borderRadius: 10, padding: 14, marginBottom: 4 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <select value={kind} onChange={e => setKind(e.target.value)} style={{ fontSize: 11, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontFamily: T.bodyFont }}>
          {kindOptions.map(k => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
        </select>
        <select value={confidence} onChange={e => setConfidence(e.target.value)} style={{ fontSize: 11, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontFamily: T.bodyFont }}>
          {CONFIDENCE_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={source} onChange={e => setSource(e.target.value)} style={{ fontSize: 11, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontFamily: T.bodyFont }}>
          {SOURCE_OPTIONS.map(s => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
        </select>
      </div>
      <textarea
        autoFocus
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder="Type the fact, quote, or claim…"
        rows={3}
        style={{ width: "100%", fontSize: 13, padding: "8px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontFamily: T.bodyFont, resize: "vertical", boxSizing: "border-box" }}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <Btn small variant="primary" disabled={!text.trim() || loading} onClick={() => onSave({ text: text.trim(), kind, confidence, source })}>
          {loading ? "Saving…" : "Save"}
        </Btn>
        <Btn small onClick={onCancel}>Cancel</Btn>
      </div>
    </div>
  )
}

// ── Plots Panel ───────────────────────────────────────────────────────────────
function PlotsPanel({ plots, productId, productName, pid, qc }) {
  const [showForm, setShowForm] = useState(false)
  const [editingPlot, setEditingPlot] = useState(null)
  const [brainstorming, setBrainstorming] = useState(false)
  const [brainstormResults, setBrainstormResults] = useState([])
  const [filterStatus, setFilterStatus] = useState("active")

  const createMut = useMutation({
    mutationFn: (data) => api.post(`/api/bs/${pid}/plots`, data),
    onSuccess: () => { qc.invalidateQueries(["bs-full", pid]); setShowForm(false) },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, ...data }) => api.put(`/api/bs/${pid}/plots/${id}`, data),
    onSuccess: () => { qc.invalidateQueries(["bs-full", pid]); setEditingPlot(null) },
  })

  const deleteMut = useMutation({
    mutationFn: (id) => api.delete(`/api/bs/${pid}/plots/${id}`),
    onSuccess: () => qc.invalidateQueries(["bs-full", pid]),
  })

  const activateMut = useMutation({
    mutationFn: (id) => api.post(`/api/bs/${pid}/plots/${id}/activate`),
    onSuccess: () => qc.invalidateQueries(["bs-full", pid]),
  })

  const deactivateMut = useMutation({
    mutationFn: (id) => api.post(`/api/bs/${pid}/plots/${id}/deactivate`),
    onSuccess: () => qc.invalidateQueries(["bs-full", pid]),
  })

  const runBrainstorm = async () => {
    setBrainstorming(true)
    setBrainstormResults([])
    try {
      const res = await api.post(`/api/bs/${pid}/plots/brainstorm`, { product_id: productId || "" })
      setBrainstormResults(res.plots || [])
    } finally {
      setBrainstorming(false)
    }
  }

  const visiblePlots = filterStatus === "all"
    ? plots
    : plots.filter(p => p.status === filterStatus)

  const STATUS_COLOR = { active: T.teal, inactive: T.amber, deleted: T.red }

  return (
    <div>
      {/* Controls */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
        <Btn small variant="primary" onClick={() => setShowForm(true)}>+ New Plot</Btn>
        <Btn small variant="outline" disabled={brainstorming} onClick={runBrainstorm}>
          {brainstorming ? "Brainstorming…" : "✨ AI Brainstorm"}
        </Btn>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          {["active","inactive","all"].map(s => (
            <button key={s} onClick={() => setFilterStatus(s)} style={{
              padding: "4px 10px", borderRadius: 20, border: "none", cursor: "pointer", fontSize: 11, fontWeight: 600, fontFamily: T.bodyFont,
              background: filterStatus === s ? T.text : T.grayLight,
              color: filterStatus === s ? "#fff" : T.text,
            }}>{s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}</button>
          ))}
        </div>
      </div>

      {/* Brainstorm results */}
      {brainstormResults.length > 0 && (
        <div style={{ marginBottom: 16, padding: 14, background: T.purple + "08", borderRadius: 10, border: `1px solid ${T.purple}30` }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: T.purple, marginBottom: 10 }}>AI Plot Ideas — click to save</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {brainstormResults.map((p, i) => (
              <div key={i} style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 8, padding: 10, display: "flex", gap: 10, alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{p.title}</div>
                  {p.thesis && <div style={{ fontSize: 12, color: T.textSoft, marginTop: 3, lineHeight: 1.5 }}>{p.thesis}</div>}
                  <div style={{ marginTop: 4 }}><Badge text={p.plot_type || "supporting"} color={T.purple} /></div>
                </div>
                <Btn small variant="primary" onClick={() => {
                  createMut.mutate({ title: p.title, thesis: p.thesis || "", plot_type: p.plot_type || "supporting", product_id: productId || "" })
                  setBrainstormResults(prev => prev.filter((_, j) => j !== i))
                }}>Save</Btn>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* New plot form */}
      {showForm && (
        <PlotForm
          initial={{ title: "", thesis: "", plot_type: "supporting", priority: 3, product_id: productId || "" }}
          onSave={(data) => createMut.mutate(data)}
          onCancel={() => setShowForm(false)}
          loading={createMut.isPending}
        />
      )}

      {/* Plot list */}
      {visiblePlots.length === 0 && !showForm && (
        <div style={{ color: T.textSoft, fontSize: 12, padding: "12px 0" }}>
          No {filterStatus === "all" ? "" : filterStatus + " "}plots yet — create one or use AI Brainstorm.
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {visiblePlots.map(plot => (
          editingPlot === plot.id
            ? <PlotForm
                key={plot.id}
                initial={plot}
                onSave={(data) => updateMut.mutate({ id: plot.id, ...data })}
                onCancel={() => setEditingPlot(null)}
                loading={updateMut.isPending}
              />
            : (
              <div key={plot.id} style={{
                background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10, padding: "12px 14px",
              }}>
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 5 }}>
                      <Badge text={plot.plot_type || "supporting"} color={T.purple} />
                      <Badge text={plot.status} color={STATUS_COLOR[plot.status] || T.textSoft} />
                      <span style={{ fontSize: 10, color: T.textSoft }}>priority {plot.priority}</span>
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 4 }}>{plot.title}</div>
                    {plot.thesis && <div style={{ fontSize: 12, color: T.textSoft, lineHeight: 1.55 }}>{plot.thesis}</div>}
                    {plot.continuity_notes && (
                      <div style={{ fontSize: 11, color: T.textSoft, marginTop: 5, fontStyle: "italic" }}>
                        Note: {plot.continuity_notes}
                      </div>
                    )}
                    {plot.used_count > 0 && (
                      <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4 }}>Used {plot.used_count}× · avg {plot.avg_performance?.toFixed(2)}</div>
                    )}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <Btn small onClick={() => setEditingPlot(plot.id)}>Edit</Btn>
                    {plot.status === "active" && <Btn small onClick={() => deactivateMut.mutate(plot.id)}>Pause</Btn>}
                    {plot.status === "inactive" && <Btn small variant="outline" onClick={() => activateMut.mutate(plot.id)}>Activate</Btn>}
                    {plot.status !== "deleted" && (
                      <Btn small variant="danger" onClick={() => window.confirm("Archive plot?") && deleteMut.mutate(plot.id)}>Archive</Btn>
                    )}
                  </div>
                </div>
              </div>
            )
        ))}
      </div>
    </div>
  )
}

function PlotForm({ initial, onSave, onCancel, loading }) {
  const [title, setTitle] = useState(initial.title || "")
  const [thesis, setThesis] = useState(initial.thesis || "")
  const [plotType, setPlotType] = useState(initial.plot_type || "supporting")
  const [priority, setPriority] = useState(initial.priority ?? 3)
  const [notes, setNotes] = useState(initial.continuity_notes || "")

  return (
    <div style={{ background: T.purple + "06", border: `1px solid ${T.purple}30`, borderRadius: 10, padding: 14, marginBottom: 4 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <select value={plotType} onChange={e => setPlotType(e.target.value)} style={{ fontSize: 11, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontFamily: T.bodyFont }}>
          {PLOT_TYPE_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
        </select>
        <select value={priority} onChange={e => setPriority(Number(e.target.value))} style={{ fontSize: 11, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontFamily: T.bodyFont }}>
          {[1,2,3,4,5].map(n => <option key={n} value={n}>Priority {n}</option>)}
        </select>
      </div>
      <input
        autoFocus
        placeholder="Plot title*"
        value={title}
        onChange={e => setTitle(e.target.value)}
        style={{ width: "100%", fontSize: 13, padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontFamily: T.bodyFont, marginBottom: 8, boxSizing: "border-box" }}
      />
      <textarea
        placeholder="Thesis — what narrative thread does this plot carry?"
        value={thesis}
        onChange={e => setThesis(e.target.value)}
        rows={2}
        style={{ width: "100%", fontSize: 12, padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontFamily: T.bodyFont, resize: "vertical", marginBottom: 8, boxSizing: "border-box" }}
      />
      <textarea
        placeholder="Continuity notes — what was said in previous articles using this plot?"
        value={notes}
        onChange={e => setNotes(e.target.value)}
        rows={2}
        style={{ width: "100%", fontSize: 12, padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontFamily: T.bodyFont, resize: "vertical", marginBottom: 8, boxSizing: "border-box" }}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <Btn small variant="primary" disabled={!title.trim() || loading} onClick={() => onSave({ title: title.trim(), thesis: thesis.trim(), plot_type: plotType, priority, continuity_notes: notes.trim(), product_id: initial.product_id || "" })}>
          {loading ? "Saving…" : "Save Plot"}
        </Btn>
        <Btn small onClick={onCancel}>Cancel</Btn>
      </div>
    </div>
  )
}
