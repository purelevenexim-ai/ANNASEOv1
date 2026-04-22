import { useState, useEffect } from "react"
import { T, api, Btn } from "../App"
import { SYSTEM_TEMPLATES, DEFAULT_TEMPLATE_ID, expandToLegacyRouting } from "../aihub/systemRoutingTemplates"

const INTENT_OPTIONS = [
  { value: "informational", label: "Informational", desc: "Teach / explain (blog, guide, how-to)" },
  { value: "commercial",    label: "Commercial",    desc: "Compare / review — includes buyer guidance, pros/cons" },
  { value: "transactional", label: "Transactional", desc: "Buy / order — includes CTAs, conversion sections" },
  { value: "navigational",  label: "Navigational",  desc: "Find a page / brand query" },
]
const WC_OPTIONS = [1500, 2000, 3000, 4000]
const CT_OPTIONS = ["blog", "guide", "review", "comparison", "landing"]

// Page type definitions
const PAGE_TYPE_OPTIONS = [
  { value: "article",  label: "Article",  icon: "📝", desc: "Blog post / guide" },
  { value: "homepage", label: "Homepage", icon: "🏠", desc: "Business home page" },
  { value: "product",  label: "Product",  icon: "🛍", desc: "Product/item page" },
  { value: "about",    label: "About Us", icon: "👥", desc: "Company about page" },
  { value: "landing",  label: "Landing",  icon: "🎯", desc: "Conversion page" },
  { value: "service",  label: "Service",  icon: "🔧", desc: "Service offering" },
]

const PAGE_TYPE_WC = {
  article:  [1500, 2000, 3000, 4000],
  homepage: [500, 800, 1000, 1200],
  product:  [800, 1200, 1500, 2000],
  about:    [500, 800, 1000, 1500],
  landing:  [600, 800, 1000, 1500],
  service:  [800, 1200, 1500, 2000],
}
const RESEARCH_AI_OPTIONS = [
  { value: "auto",   label: "Auto",   desc: "Ollama → Groq → Gemini" },
  { value: "ollama", label: "Ollama",  desc: "Local (free, fast)" },
  { value: "groq",   label: "Groq",   desc: "llama-3.3-70b" },
  { value: "gemini", label: "Gemini",  desc: "gemini-2.0-flash" },
]

// ── AI providers grouped by tier ──────────────────────────────────────────────
const AI_PROVIDERS_BASE = {
  free: [
    { value: "gemini_free",  label: "Gemini",         desc: "Free tier",       color: "#1a73e8" },
    { value: "groq",         label: "Groq",           desc: "Free · fast",     color: "#f59e0b" },
    { value: "ollama",       label: "Ollama (Remote)",desc: "Remote server",   color: "#6b7280" },
  ],
  paid: [
    { value: "gemini_paid",    label: "Gemini Paid",   desc: "Paid tier",     color: "#0f9d58" },
    { value: "anthropic",      label: "Claude",        desc: "Anthropic API", color: "#7c3aed" },
    { value: "anthropic_paid", label: "Claude Pro",    desc: "Paid tier",     color: "#5b21b6" },
    { value: "openai_paid",    label: "ChatGPT",       desc: "OpenAI API",    color: "#10a37f" },
  ],
  other: [
    { value: "or_qwen",           label: "OR: GPT-OSS 120B",         desc: "Free",          color: "#6366f1" },
    { value: "or_qwen_next",      label: "OR: GPT-OSS 20B",          desc: "Free",          color: "#6366f1" },
    { value: "or_qwq",            label: "OR: QwQ 32B",              desc: "Free reasoning", color: "#6366f1" },
    { value: "or_phi4",           label: "OR: Phi-4 Reasoning",      desc: "Free reasoning", color: "#6366f1" },
    { value: "or_gemma3",         label: "OR: Gemma 3 27B",          desc: "Free",          color: "#6366f1" },
    { value: "or_mistral",        label: "OR: Mistral Small 3.2",    desc: "Free",          color: "#6366f1" },
    { value: "or_maverick_free",  label: "OR: Llama 4 Free",         desc: "Free",          color: "#6366f1" },
    { value: "or_haiku",          label: "OR: Claude Haiku 4.5",    desc: "$0.80/M",       color: "#7c3aed" },
    { value: "or_deepseek",       label: "OR: DeepSeek V3.2",        desc: "$0.26/M",       color: "#6366f1" },
    { value: "or_deepseek_r1",    label: "OR: DeepSeek R1",          desc: "$0.45/M",       color: "#6366f1" },
    { value: "or_gemini_flash",   label: "OR: Gemini 2.5 Flash",     desc: "$0.30/M",       color: "#6366f1" },
    { value: "or_gemini_lite",    label: "OR: Gemini 2.0 Flash Lite",desc: "$0.07/M",       color: "#6366f1" },
    { value: "or_glm",            label: "OR: GLM 5 Turbo",          desc: "$1.20/M",       color: "#6366f1" },
    { value: "or_gemini_pro",     label: "OR: Gemini 2.5 Pro",       desc: "$1.25/M",       color: "#0f9d58" },
    { value: "or_o4_mini",        label: "OR: o4-mini",              desc: "$1.10/M",       color: "#10a37f" },
    { value: "or_gpt4o",          label: "OR: GPT-4o",               desc: "$2.50/M",       color: "#10a37f" },
    { value: "or_claude",         label: "OR: Claude Sonnet 4",      desc: "$3.00/M",       color: "#7c3aed" },
    { value: "or_claude_opus",    label: "OR: Claude Opus 4",        desc: "$15/M",         color: "#7c3aed" },
    { value: "or_llama",          label: "OR: Llama 4 Maverick",     desc: "$0.20/M",       color: "#6366f1" },
    { value: "or_qwen_coder",     label: "OR: Qwen3 Coder 480B",    desc: "Free",          color: "#6366f1" },
    { value: "openrouter",        label: "OpenRouter",               desc: "Default model", color: "#6366f1" },
    { value: "skip",              label: "Skip",                     desc: "Don't run",     color: "#9ca3af" },
  ],
}
function _buildProviders(ollamaServers) {
  const remote = (ollamaServers || []).filter(s => s.enabled).map(s => ({
    value: `ollama_remote_${s.server_id}`,
    label: `Ollama (${s.name})`,
    desc: `${s.model || "?"} · ${(s.url || "").replace(/^https?:\/\//, "").replace(/:11434$/, "")}`,
    color: "#059669",
  }))
  return {
    free: [...AI_PROVIDERS_BASE.free, ...remote],
    paid: AI_PROVIDERS_BASE.paid,
    other: AI_PROVIDERS_BASE.other,
  }
}
const AI_PROVIDER_OPTIONS = [
  ...AI_PROVIDERS_BASE.free,
  ...AI_PROVIDERS_BASE.paid,
  ...AI_PROVIDERS_BASE.other,
]
const _providerMeta = Object.fromEntries(AI_PROVIDER_OPTIONS.map(p => [p.value, p]))

const ROUTING_TASKS = [
  { n: 1, key: "research",     label: "Research",         icon: "🔍", desc: "Step 1: Crawl & analysis",            tier: "free" },
  { n: 2, key: "structure",    label: "Structure",        icon: "📐", desc: "Step 2: Outline & headings",          tier: "free" },
  { n: 3, key: "verify",       label: "Blueprint",        icon: "🧠", desc: "Step 3: Blueprint & contracts",       tier: "free" },
  { n: 4, key: "links",        label: "Internal Links",   icon: "🔗", desc: "Step 4: Link planning",               tier: "free" },
  { n: 5, key: "references",   label: "References",       icon: "📚", desc: "Step 5: Wikipedia references",        tier: "free" },
  { n: 6, key: "draft",        label: "Draft",            icon: "✍️", desc: "Step 6: Contract-driven generation", tier: "paid" },
  { n: 7, key: "score",        label: "Validate & Score", icon: "📊", desc: "Step 7: 74-rule scoring + section contracts", tier: "free" },
  { n: 8, key: "quality_loop", label: "Recovery",         icon: "🔄", desc: "Step 8: Section-level fixes + contract repair",  tier: "paid" },
]
const DEFAULT_ROUTING = expandToLegacyRouting(SYSTEM_TEMPLATES.find(t => t.id === DEFAULT_TEMPLATE_ID).steps)

// ── Bulk topic parser ─────────────────────────────────────────────────────────
function parseBulkText(text) {
  if (!text?.trim()) return []
  const INTENT_MAP = {
    transactional: "transactional", commercial: "commercial",
    informational: "informational", navigational: "navigational",
    comparison: "commercial", "buy intent": "transactional", "purchase intent": "transactional",
  }
  const blocks = text.split(/\n(?=\s*\d+[.)]\s|[🔥🌿🛒🌶📦🌱🏆🍛⚙️✅💰🌍🌾]+\s)|\n{2,}/)
  const seen = new Set()
  return blocks.flatMap(block => {
    const lines = block.split("\n").map(l => l.trim()).filter(Boolean)
    if (!lines.length) return []
    let keyword = lines[0]
      .replace(/^\d+[.)]\s*/, "")
      .replace(/^[🔥🌿🛒🌶📦🌱🏆🍛⚙️✅💰🌍🌾]+\s*/, "")
      .replace(/[:\-–—]\s*(Structure|Intent|CTA|Keywords?).*$/i, "")
      .trim()
    if (!keyword || keyword.length < 3) return []
    let intent = "informational"
    const intentLine = lines.find(l => /^intent:/i.test(l))
    if (intentLine) {
      const raw = intentLine.replace(/^intent:\s*/i, "").toLowerCase().trim()
      for (const [k, v] of Object.entries(INTENT_MAP)) { if (raw.includes(k)) { intent = v; break } }
    }
    const key = keyword.toLowerCase()
    if (seen.has(key)) return []
    seen.add(key)
    return [{ id: Math.random().toString(36).slice(2), keyword, intent, selected: true }]
  })
}

// ── Bulk Topics Tab component ─────────────────────────────────────────────────
function BulkTopicsTab({ form, projectId, onClose }) {
  const [bulkText, setBulkText] = useState("")
  const [topics, setTopics] = useState([])
  const [phase, setPhase] = useState(1)
  const [genMode, setGenMode] = useState("sequential")
  const [pipelineMode, setPipelineMode] = useState(form.pipeline_mode || "standard")
  const [wordCount, setWordCount] = useState(form.word_count || 2000)
  const [parsing, setParsing] = useState(false)
  const [parseError, setParseError] = useState("")
  const [generating, setGenerating] = useState(false)
  const [results, setResults] = useState({})

  const inputStyle = {
    width: "100%", padding: "7px 10px", borderRadius: 8,
    border: `1px solid ${T.border}`, fontSize: 12,
    boxSizing: "border-box", fontFamily: "inherit", outline: "none",
  }
  const labelStyle = { fontSize: 11, color: T.textSoft, display: "block", marginBottom: 4, fontWeight: 500 }

  const selectedTopics = topics.filter(t => t.selected)

  const buildPayload = (topic) => ({
    keyword: topic.keyword,
    intent: topic.intent,
    pipeline_mode: pipelineMode,
    word_count: wordCount,
    page_type: form.page_type || "article",
    page_inputs: form.page_inputs || {},
    ai_routing: form.ai_routing,
    supporting_keywords: [],
    product_links: [],
    step_mode: "auto",
    project_id: projectId,
  })

  const runGenerate = async (addOnly = false) => {
    if (!selectedTopics.length) return
    setGenerating(true)
    setPhase(3)
    const go = async (topic) => {
      try {
        await api.post("/api/content/generate", buildPayload(topic))
        setResults(r => ({ ...r, [topic.id]: "ok" }))
      } catch {
        setResults(r => ({ ...r, [topic.id]: "error" }))
      }
    }
    if (genMode === "parallel" || addOnly) {
      await Promise.allSettled(selectedTopics.map(go))
    } else {
      for (const t of selectedTopics) await go(t)
    }
    setGenerating(false)
    if (addOnly) onClose()
  }

  const toggleTopic = id => setTopics(ts => ts.map(t => t.id === id ? { ...t, selected: !t.selected } : t))
  const updateTopic = (id, f, v) => setTopics(ts => ts.map(t => t.id === id ? { ...t, [f]: v } : t))
  const removeTopic = id => setTopics(ts => ts.filter(t => t.id !== id))
  const toggleAll = val => setTopics(ts => ts.map(t => ({ ...t, selected: val })))

  const handleParse = async () => {
    if (!bulkText.trim() || parsing) return
    setParsing(true)
    setParseError("")
    try {
      const res = await api.post("/api/content/parse-topics", { text: bulkText })
      if (res?.topics?.length) {
        setTopics(res.topics.map(t => ({ ...t, id: Math.random().toString(36).slice(2), selected: true })))
        setPhase(2)
      } else {
        const fallback = parseBulkText(bulkText)
        if (fallback.length) { setTopics(fallback); setPhase(2) }
        else setParseError(res?.error || "No topics found — check your text and try again")
      }
    } catch {
      const fallback = parseBulkText(bulkText)
      if (fallback.length) { setTopics(fallback); setPhase(2) }
      else setParseError("Parsing failed — check your connection and try again")
    }
    setParsing(false)
  }

  // Phase 1 — paste
  if (phase === 1) return (
    <div>
      <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 10 }}>
        Paste topic ideas, keyword lists, or structured content briefs. AI will extract the article titles and detect search intent automatically.
      </div>
      <textarea
        value={bulkText}
        onChange={e => setBulkText(e.target.value)}
        placeholder={"Paste your topic list here...\n\nExample:\n🔥 1. Buy Kerala Spices Online: Complete Guide\nIntent: Transactional\n\n🌿 2. Best Kerala Spices Top 10\nIntent: Commercial"}
        style={{ ...inputStyle, minHeight: 220, resize: "vertical", fontFamily: "monospace", fontSize: 11 }}
      />
      <div style={{ marginTop: 10, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
        {parseError && <div style={{ fontSize: 10, color: "#dc2626", alignSelf: "flex-start" }}>{parseError}</div>}
        <button
          onClick={handleParse}
          disabled={!bulkText.trim() || parsing}
          style={{
            padding: "8px 18px", borderRadius: 8, fontSize: 12, fontWeight: 600,
            background: bulkText.trim() && !parsing ? T.purple : "#e5e7eb",
            color: bulkText.trim() && !parsing ? "#fff" : T.textSoft,
            border: "none", cursor: bulkText.trim() && !parsing ? "pointer" : "default",
          }}
        >{parsing ? "Parsing with AI…" : "Parse Topics →"}</button>
      </div>
    </div>
  )

  // Phase 2 — review + settings
  if (phase === 2) return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#059669" }}>✓ {topics.length} topic{topics.length !== 1 ? "s" : ""} found</span>
        <button onClick={() => toggleAll(true)} style={{ fontSize: 10, color: T.purple, background: "none", border: "none", cursor: "pointer", padding: "2px 6px" }}>Select All</button>
        <button onClick={() => toggleAll(false)} style={{ fontSize: 10, color: T.gray, background: "none", border: "none", cursor: "pointer", padding: "2px 6px" }}>Deselect All</button>
        <button onClick={() => setPhase(1)} style={{ fontSize: 10, color: T.gray, background: "none", border: "none", cursor: "pointer", marginLeft: "auto", padding: "2px 6px" }}>← Edit Paste</button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 200, overflowY: "auto", marginBottom: 12 }}>
        {topics.map(t => (
          <div key={t.id} style={{
            display: "flex", alignItems: "center", gap: 6, padding: "5px 8px", borderRadius: 8,
            background: t.selected ? `${T.purple}08` : "#f9fafb",
            border: `1px solid ${t.selected ? `${T.purple}30` : T.border}`,
          }}>
            <input type="checkbox" checked={t.selected} onChange={() => toggleTopic(t.id)} style={{ accentColor: T.purple, flexShrink: 0 }} />
            <input
              value={t.keyword}
              onChange={e => updateTopic(t.id, "keyword", e.target.value)}
              style={{ flex: 1, border: "none", outline: "none", fontSize: 11, background: "transparent", color: T.text, fontFamily: "inherit" }}
            />
            <select value={t.intent} onChange={e => updateTopic(t.id, "intent", e.target.value)}
              style={{ fontSize: 10, border: `1px solid ${T.border}`, borderRadius: 6, padding: "2px 5px", background: "#fff", color: T.gray, cursor: "pointer", flexShrink: 0 }}>
              {INTENT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <button onClick={() => removeTopic(t.id)}
              style={{ background: "none", border: "none", cursor: "pointer", color: T.red, fontSize: 13, padding: "0 2px", flexShrink: 0 }}>✕</button>
          </div>
        ))}
      </div>

      <div style={{ padding: "10px 12px", borderRadius: 10, background: "#f9fafb", border: `1px solid ${T.border}`, marginBottom: 12 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: T.text, marginBottom: 8 }}>Settings for all topics</div>
        <div style={{ display: "flex", gap: 12, marginBottom: 8, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 4 }}>Pipeline</div>
            <div style={{ display: "flex", gap: 4 }}>
              {[{ v: "standard", l: "⚙ Standard" }, { v: "lean", l: "⚡ Lean" }].map(m => (
                <button key={m.v} onClick={() => setPipelineMode(m.v)} style={{
                  padding: "4px 10px", borderRadius: 6, fontSize: 10, cursor: "pointer",
                  border: `1px solid ${pipelineMode === m.v ? T.purple : T.border}`,
                  background: pipelineMode === m.v ? `${T.purple}15` : "transparent",
                  color: pipelineMode === m.v ? T.purple : T.gray, fontWeight: pipelineMode === m.v ? 600 : 400,
                }}>{m.l}</button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 4 }}>Word count</div>
            <div style={{ display: "flex", gap: 4 }}>
              {WC_OPTIONS.map(wc => (
                <button key={wc} onClick={() => setWordCount(wc)} style={{
                  padding: "4px 10px", borderRadius: 6, fontSize: 10, cursor: "pointer",
                  border: `1px solid ${wordCount === wc ? T.purple : T.border}`,
                  background: wordCount === wc ? `${T.purple}15` : "transparent",
                  color: wordCount === wc ? T.purple : T.gray, fontWeight: wordCount === wc ? 600 : 400,
                }}>{wc.toLocaleString()}w</button>
              ))}
            </div>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 4 }}>Generation mode</div>
          <div style={{ display: "flex", gap: 12 }}>
            {[
              { v: "sequential", l: "Queue one by one", d: "Starts next after each completes" },
              { v: "parallel",   l: "Launch all at once", d: "Parallel — faster, higher API load" },
            ].map(m => (
              <label key={m.v} style={{ display: "flex", alignItems: "flex-start", gap: 5, cursor: "pointer", flex: 1 }}>
                <input type="radio" name="bulkGenMode" value={m.v} checked={genMode === m.v}
                  onChange={() => setGenMode(m.v)} style={{ accentColor: T.purple, marginTop: 2, flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 11, fontWeight: 500, color: T.text }}>{m.l}</div>
                  <div style={{ fontSize: 9, color: T.textSoft }}>{m.d}</div>
                </div>
              </label>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={() => runGenerate(true)} disabled={!selectedTopics.length}
          style={{
            flex: 1, padding: "8px 12px", borderRadius: 8, fontSize: 11, fontWeight: 500,
            border: `1px solid ${T.border}`, background: "transparent",
            color: T.gray, cursor: selectedTopics.length ? "pointer" : "default",
          }}>Add to List Only</button>
        <button onClick={() => runGenerate(false)} disabled={!selectedTopics.length}
          style={{
            flex: 2, padding: "8px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600,
            background: selectedTopics.length ? T.purple : "#e5e7eb",
            color: selectedTopics.length ? "#fff" : T.textSoft,
            border: "none", cursor: selectedTopics.length ? "pointer" : "default",
          }}>Generate {selectedTopics.length} Selected Topic{selectedTopics.length !== 1 ? "s" : ""} ✨</button>
      </div>
    </div>
  )

  // Phase 3 — progress / results
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: T.text, marginBottom: 12 }}>
        {generating ? `Generating articles… (${Object.keys(results).length}/${selectedTopics.length})` : "Generation complete"}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 300, overflowY: "auto" }}>
        {selectedTopics.map(t => {
          const s = results[t.id]
          return (
            <div key={t.id} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 8,
              background: s === "ok" ? "#f0fdf4" : s === "error" ? "#fef2f2" : "#f9fafb",
              border: `1px solid ${s === "ok" ? "#bbf7d0" : s === "error" ? "#fecaca" : T.border}`,
            }}>
              <span style={{ fontSize: 14, flexShrink: 0 }}>{s === "ok" ? "✓" : s === "error" ? "✗" : "⏳"}</span>
              <span style={{ fontSize: 11, color: T.text, flex: 1 }}>{t.keyword}</span>
              <span style={{
                fontSize: 9, padding: "1px 6px", borderRadius: 4,
                background: t.intent === "transactional" ? "#fef3c7" : t.intent === "commercial" ? "#ede9fe" : "#e0f2fe",
                color: t.intent === "transactional" ? "#d97706" : t.intent === "commercial" ? "#7c3aed" : "#0369a1",
              }}>{t.intent}</span>
            </div>
          )
        })}
      </div>
      {!generating && (
        <button onClick={onClose} style={{
          marginTop: 14, width: "100%", padding: "8px 12px", borderRadius: 8,
          fontSize: 12, fontWeight: 600, background: T.purple, color: "#fff", border: "none", cursor: "pointer",
        }}>Done ✓</button>
      )}
    </div>
  )
}

const EMPTY_FORM = {
  page_type: "article",
  page_inputs: {},
  keyword: "",
  supporting_keywords: "",  // comma-separated string → split on submit
  product_links: [],        // [{url, name}]
  intent: "informational",
  word_count: 2000,
  target_audience: "",
  content_type: "blog",
  pipeline_mode: "standard",  // "standard" | "lean"
  ai_routing: { ...DEFAULT_ROUTING },
  title: "",
  step_mode: "auto",
}

function NewArticleModal({ onClose, onGenerate, isPending, initialKeyword = "", projectId }) {
  const [form, setForm] = useState(() => initialKeyword ? { ...EMPTY_FORM, keyword: initialKeyword } : EMPTY_FORM)
  const [newLink, setNewLink] = useState({ url: "", name: "" })
  const [activeTab, setActiveTab] = useState("settings")
  const [blueprint, setBlueprint] = useState(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [showPlan, setShowPlan] = useState(false)
  const [ollamaServers, setOllamaServers] = useState([])

  // Load available Ollama servers + saved AI Hub routing
  useEffect(() => {
    api.get("/api/settings/ollama-servers").then(s => setOllamaServers(s || [])).catch(() => {})
    api.get("/api/ai/routing").then(saved => {
      if (saved && typeof saved === "object" && saved.research) {
        setForm(f => ({ ...f, ai_routing: saved }))
      }
    }).catch(() => {})
  }, [])

  const AI_PROVIDERS = _buildProviders(ollamaServers)
  const allProviderOptions = [...AI_PROVIDERS.free, ...AI_PROVIDERS.paid, ...AI_PROVIDERS.other]
  const providerLookup = Object.fromEntries(allProviderOptions.map(p => [p.value, p]))

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const setRouting = (task, rank, value) =>
    setForm(f => ({ ...f, ai_routing: { ...f.ai_routing, [task]: { ...f.ai_routing[task], [rank]: value } } }))

  const applyPreset = (tpl) =>
    setForm(f => ({ ...f, ai_routing: expandToLegacyRouting(tpl.steps) }))

  const addLink = () => {
    if (!newLink.url.trim()) return
    setForm(f => ({ ...f, product_links: [...f.product_links, { url: newLink.url.trim(), name: newLink.name.trim() || newLink.url.trim() }] }))
    setNewLink({ url: "", name: "" })
  }

  const removeLink = (i) => setForm(f => ({ ...f, product_links: f.product_links.filter((_, idx) => idx !== i) }))

  const generatePlan = async () => {
    if (!form.keyword.trim()) return
    setPlanLoading(true)
    try {
      const res = await api.post("/api/content/plan", {
        keyword: form.keyword.trim(),
        page_type: form.page_type || "article",
        intent: form.intent,
        word_count: form.word_count,
        page_inputs: form.page_inputs || {},
        supporting_keywords: form.supporting_keywords.split(",").map(s => s.trim()).filter(Boolean),
        target_audience: form.target_audience,
        content_type: form.content_type,
      })
      if (res?.blueprint) {
        setBlueprint(res.blueprint)
        setShowPlan(true)
      }
    } catch (e) {
      alert("Failed to generate plan: " + (e?.message || "Unknown error"))
    }
    setPlanLoading(false)
  }

  const handleSubmit = () => {
    if (!form.keyword.trim()) return
    const payload = {
      ...form,
      supporting_keywords: form.supporting_keywords
        .split(",").map(s => s.trim()).filter(Boolean),
      page_type: form.page_type || "article",
      page_inputs: form.page_inputs || {},
      step_mode: form.step_mode || "auto",
      pipeline_mode: form.pipeline_mode || "standard",
    }
    onGenerate(payload)
  }

  const inputStyle = {
    width: "100%", padding: "7px 10px", borderRadius: 8,
    border: `1px solid ${T.border}`, fontSize: 12,
    boxSizing: "border-box", fontFamily: "inherit", outline: "none",
  }
  const labelStyle = { fontSize: 11, color: T.textSoft, display: "block", marginBottom: 4, fontWeight: 500 }
  const sectionStyle = { marginBottom: 16 }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 2000,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
    }} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{
        background: "#fff", borderRadius: 16, width: "100%", maxWidth: 560,
        boxShadow: "0 12px 60px rgba(0,0,0,0.18)", maxHeight: "90vh",
        display: "flex", flexDirection: "column", overflow: "hidden",
      }}>
        {/* Modal header */}
        <div style={{
          padding: "18px 24px 14px", borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div>
            <div style={{ fontSize: 17, fontWeight: 600, color: T.text }}>
              New {PAGE_TYPE_OPTIONS.find(p => p.value === form.page_type)?.label || "Article"}
            </div>
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>Configure your content before generation starts</div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: T.gray }}>✕</button>
        </div>

        {/* Tab bar */}
        <div style={{ display: "flex", borderBottom: `1px solid ${T.border}`, padding: "0 24px" }}>
          {[{ key: "settings", label: "Settings" }, { key: "routing", label: "AI Routing" }, { key: "bulk", label: "📋 Bulk Topics" }].map(tab => (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)} style={{
              padding: "10px 16px", fontSize: 12, fontWeight: activeTab === tab.key ? 600 : 400,
              color: activeTab === tab.key ? T.purple : T.textSoft,
              background: "none", border: "none", cursor: "pointer",
              borderBottom: activeTab === tab.key ? `2px solid ${T.purple}` : "2px solid transparent",
              marginBottom: -1,
            }}>{tab.label}</button>
          ))}
        </div>

        {/* Scrollable body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "18px 24px" }}>

          {activeTab === "settings" && <>

          {/* Page type selector */}
          <div style={sectionStyle}>
            <label style={labelStyle}>Page Type</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {PAGE_TYPE_OPTIONS.map(pt => (
                <button key={pt.value} onClick={() => {
                  set("page_type", pt.value)
                  set("page_inputs", {})
                  // Reset word count to first option for selected type
                  const wcOpts = PAGE_TYPE_WC[pt.value] || WC_OPTIONS
                  set("word_count", wcOpts[1] || wcOpts[0])
                }} style={{
                  padding: "6px 12px", borderRadius: 8, fontSize: 11, cursor: "pointer",
                  border: `1px solid ${form.page_type === pt.value ? T.purple : T.border}`,
                  background: form.page_type === pt.value ? `${T.purple}15` : "transparent",
                  color: form.page_type === pt.value ? T.purple : T.gray,
                  fontWeight: form.page_type === pt.value ? 600 : 400,
                  display: "flex", alignItems: "center", gap: 4,
                }}>
                  <span>{pt.icon}</span> {pt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Pipeline mode selector */}
          <div style={sectionStyle}>
            <label style={labelStyle}>Pipeline Mode</label>
            <div style={{ display: "flex", gap: 8 }}>
              {[
                { value: "standard", label: "⚙️ Standard", desc: "12-step quality pipeline · rules-first draft · ~$0.50–$1.50" },
                { value: "lean",     label: "⚡ Lean",     desc: "3-call budget pipeline · fast · ~$0.08–$0.20" },
              ].map(m => (
                <button key={m.value} onClick={() => set("pipeline_mode", m.value)} style={{
                  flex: 1, padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                  border: `2px solid ${form.pipeline_mode === m.value ? (m.value === "lean" ? "#10b981" : T.purple) : T.border}`,
                  background: form.pipeline_mode === m.value
                    ? (m.value === "lean" ? "#10b98115" : `${T.purple}15`)
                    : "transparent",
                  textAlign: "left",
                }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: form.pipeline_mode === m.value ? (m.value === "lean" ? "#059669" : T.purple) : T.text }}>
                    {m.label}
                  </div>
                  <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{m.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Pillar keyword — REQUIRED */}
          <div style={sectionStyle}>
            <label style={labelStyle}>
              Pillar Keyword <span style={{ color: T.red }}>*</span>
            </label>
            <input
              autoFocus
              value={form.keyword}
              onChange={e => set("keyword", e.target.value)}
              placeholder="e.g. buy cardamom online india"
              style={inputStyle}
            />
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3 }}>
              The main keyword this article targets. Keep it specific (3-6 words).
            </div>
          </div>

          {/* Supporting keywords */}
          <div style={sectionStyle}>
            <label style={labelStyle}>Supporting Keywords</label>
            <input
              value={form.supporting_keywords}
              onChange={e => set("supporting_keywords", e.target.value)}
              placeholder="cardamom benefits, green cardamom uses, organic cardamom..."
              style={inputStyle}
            />
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3 }}>
              Comma-separated LSI / related keywords to weave into the article naturally.
            </div>
          </div>

          {/* Intent + Content type row */}
          <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Search Intent</label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {INTENT_OPTIONS.map(o => (
                  <button key={o.value} onClick={() => set("intent", o.value)} style={{
                    padding: "5px 11px", borderRadius: 99, fontSize: 11, cursor: "pointer",
                    border: `1px solid ${form.intent === o.value ? T.purple : T.border}`,
                    background: form.intent === o.value ? `${T.purple}15` : "transparent",
                    color: form.intent === o.value ? T.purple : T.gray,
                    fontWeight: form.intent === o.value ? 600 : 400,
                  }} title={o.desc}>{o.label}</button>
                ))}
              </div>
            </div>
            <div style={{ width: 130, flexShrink: 0 }}>
              <label style={labelStyle}>Content Type</label>
              <select value={form.content_type} onChange={e => set("content_type", e.target.value)} style={{ ...inputStyle, padding: "6px 8px" }}>
                {CT_OPTIONS.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
              </select>
            </div>
          </div>

          {/* Word count */}
          <div style={sectionStyle}>
            <label style={labelStyle}>Target Word Count</label>
            <div style={{ display: "flex", gap: 6 }}>
              {(PAGE_TYPE_WC[form.page_type] || WC_OPTIONS).map(wc => (
                <button key={wc} onClick={() => set("word_count", wc)} style={{
                  flex: 1, padding: "6px 0", borderRadius: 8, fontSize: 11, cursor: "pointer",
                  border: `1px solid ${form.word_count === wc ? T.purple : T.border}`,
                  background: form.word_count === wc ? `${T.purple}15` : "transparent",
                  color: form.word_count === wc ? T.purple : T.gray,
                  fontWeight: form.word_count === wc ? 600 : 400,
                }}>{wc.toLocaleString()}w</button>
              ))}
            </div>
          </div>

          {/* Target audience */}
          <div style={sectionStyle}>
            <label style={labelStyle}>Target Audience</label>
            <input
              value={form.target_audience}
              onChange={e => set("target_audience", e.target.value)}
              placeholder="e.g. home cooks in India looking for authentic spices"
              style={inputStyle}
            />
          </div>

          {/* ── Page-type-specific inputs ── */}
          {form.page_type === "homepage" && (
            <div style={{ padding: "12px 14px", borderRadius: 10, background: `${T.purple}06`, border: `1px solid ${T.border}`, marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.text, marginBottom: 10 }}>🏠 Homepage Details</div>
              {[
                { key: "business_name", label: "Business Name", placeholder: "e.g. Acme Spices Co." },
                { key: "tagline", label: "Tagline", placeholder: "e.g. Premium spices delivered to your door" },
                { key: "services_list", label: "Services / Products", placeholder: "e.g. Organic cardamom, Saffron, Custom spice blends", area: true },
                { key: "unique_selling_points", label: "Unique Selling Points", placeholder: "e.g. Farm-to-table, 100% organic, Free shipping", area: true },
                { key: "target_locations", label: "Target Locations", placeholder: "e.g. India, USA, Global" },
              ].map(f => (
                <div key={f.key} style={{ marginBottom: 10 }}>
                  <label style={labelStyle}>{f.label}</label>
                  {f.area ? (
                    <textarea value={form.page_inputs[f.key] || ""} onChange={e => set("page_inputs", { ...form.page_inputs, [f.key]: e.target.value })}
                      placeholder={f.placeholder} style={{ ...inputStyle, minHeight: 50, resize: "vertical" }} />
                  ) : (
                    <input value={form.page_inputs[f.key] || ""} onChange={e => set("page_inputs", { ...form.page_inputs, [f.key]: e.target.value })}
                      placeholder={f.placeholder} style={inputStyle} />
                  )}
                </div>
              ))}
            </div>
          )}

          {form.page_type === "product" && (
            <div style={{ padding: "12px 14px", borderRadius: 10, background: `${T.purple}06`, border: `1px solid ${T.border}`, marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.text, marginBottom: 10 }}>🛍 Product Details</div>
              {[
                { key: "product_name", label: "Product Name", placeholder: "e.g. Kerala Green Cardamom 100g" },
                { key: "price", label: "Price", placeholder: "e.g. ₹499 / $12.99" },
                { key: "features_list", label: "Key Features", placeholder: "e.g. 100% organic, Hand-picked, Grade-A quality", area: true },
                { key: "benefits", label: "Benefits", placeholder: "e.g. Rich aroma, Health benefits, Versatile cooking uses", area: true },
                { key: "specifications", label: "Specifications", placeholder: "e.g. Weight: 100g, Origin: Kerala, Shelf life: 12 months", area: true },
              ].map(f => (
                <div key={f.key} style={{ marginBottom: 10 }}>
                  <label style={labelStyle}>{f.label}</label>
                  {f.area ? (
                    <textarea value={form.page_inputs[f.key] || ""} onChange={e => set("page_inputs", { ...form.page_inputs, [f.key]: e.target.value })}
                      placeholder={f.placeholder} style={{ ...inputStyle, minHeight: 50, resize: "vertical" }} />
                  ) : (
                    <input value={form.page_inputs[f.key] || ""} onChange={e => set("page_inputs", { ...form.page_inputs, [f.key]: e.target.value })}
                      placeholder={f.placeholder} style={inputStyle} />
                  )}
                </div>
              ))}
            </div>
          )}

          {form.page_type === "about" && (
            <div style={{ padding: "12px 14px", borderRadius: 10, background: `${T.purple}06`, border: `1px solid ${T.border}`, marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.text, marginBottom: 10 }}>👥 About Us Details</div>
              {[
                { key: "company_story", label: "Company Story", placeholder: "Brief origin story of the company", area: true },
                { key: "founding_year", label: "Founded Year", placeholder: "e.g. 2015" },
                { key: "mission", label: "Mission Statement", placeholder: "e.g. To bring authentic Indian spices to every kitchen" },
                { key: "values", label: "Core Values", placeholder: "e.g. Quality, Sustainability, Community", area: true },
                { key: "achievements", label: "Key Achievements", placeholder: "e.g. 50,000+ customers, ISO certified, Featured in Forbes", area: true },
              ].map(f => (
                <div key={f.key} style={{ marginBottom: 10 }}>
                  <label style={labelStyle}>{f.label}</label>
                  {f.area ? (
                    <textarea value={form.page_inputs[f.key] || ""} onChange={e => set("page_inputs", { ...form.page_inputs, [f.key]: e.target.value })}
                      placeholder={f.placeholder} style={{ ...inputStyle, minHeight: 50, resize: "vertical" }} />
                  ) : (
                    <input value={form.page_inputs[f.key] || ""} onChange={e => set("page_inputs", { ...form.page_inputs, [f.key]: e.target.value })}
                      placeholder={f.placeholder} style={inputStyle} />
                  )}
                </div>
              ))}
            </div>
          )}

          {form.page_type === "landing" && (
            <div style={{ padding: "12px 14px", borderRadius: 10, background: `${T.purple}06`, border: `1px solid ${T.border}`, marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.text, marginBottom: 10 }}>🎯 Landing Page Details</div>
              {[
                { key: "offer_headline", label: "Offer Headline", placeholder: "e.g. Get 50% Off Premium Cardamom — Limited Time" },
                { key: "target_action", label: "Target Action (CTA)", placeholder: "e.g. Buy Now, Sign Up, Book a Call" },
                { key: "pain_points", label: "Pain Points", placeholder: "e.g. Hard to find quality spices, Expensive imports, Inconsistent flavor", area: true },
                { key: "benefits", label: "Key Benefits", placeholder: "e.g. Direct from farms, Guaranteed freshness, Free shipping", area: true },
                { key: "social_proof", label: "Social Proof", placeholder: "e.g. 10,000+ happy customers, 4.9-star rating, As seen in...", area: true },
              ].map(f => (
                <div key={f.key} style={{ marginBottom: 10 }}>
                  <label style={labelStyle}>{f.label}</label>
                  {f.area ? (
                    <textarea value={form.page_inputs[f.key] || ""} onChange={e => set("page_inputs", { ...form.page_inputs, [f.key]: e.target.value })}
                      placeholder={f.placeholder} style={{ ...inputStyle, minHeight: 50, resize: "vertical" }} />
                  ) : (
                    <input value={form.page_inputs[f.key] || ""} onChange={e => set("page_inputs", { ...form.page_inputs, [f.key]: e.target.value })}
                      placeholder={f.placeholder} style={inputStyle} />
                  )}
                </div>
              ))}
            </div>
          )}

          {form.page_type === "service" && (
            <div style={{ padding: "12px 14px", borderRadius: 10, background: `${T.purple}06`, border: `1px solid ${T.border}`, marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.text, marginBottom: 10 }}>🔧 Service Details</div>
              {[
                { key: "service_name", label: "Service Name", placeholder: "e.g. Custom Spice Blending Service" },
                { key: "service_description", label: "Service Description", placeholder: "What does this service include?", area: true },
                { key: "process_steps", label: "Process Steps", placeholder: "e.g. 1. Consultation 2. Blend creation 3. Delivery", area: true },
                { key: "pricing_hint", label: "Pricing Info", placeholder: "e.g. Starting from ₹999, Custom quotes available" },
                { key: "faq_items", label: "Common Questions", placeholder: "e.g. How long does it take? What's the minimum order?", area: true },
              ].map(f => (
                <div key={f.key} style={{ marginBottom: 10 }}>
                  <label style={labelStyle}>{f.label}</label>
                  {f.area ? (
                    <textarea value={form.page_inputs[f.key] || ""} onChange={e => set("page_inputs", { ...form.page_inputs, [f.key]: e.target.value })}
                      placeholder={f.placeholder} style={{ ...inputStyle, minHeight: 50, resize: "vertical" }} />
                  ) : (
                    <input value={form.page_inputs[f.key] || ""} onChange={e => set("page_inputs", { ...form.page_inputs, [f.key]: e.target.value })}
                      placeholder={f.placeholder} style={inputStyle} />
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Product / page links */}
          <div style={sectionStyle}>
            <label style={labelStyle}>Product & Page Links</label>
            <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 6 }}>
              Add internal pages to link to from this article. The pipeline will embed them naturally.
            </div>
            {form.product_links.map((lk, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 8, marginBottom: 5,
                padding: "6px 10px", borderRadius: 8, background: `${T.purple}08`,
                border: `1px solid ${T.border}`,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, fontWeight: 500, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{lk.name}</div>
                  <div style={{ fontSize: 10, color: T.textSoft, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{lk.url}</div>
                </div>
                <button onClick={() => removeLink(i)} style={{ background: "none", border: "none", cursor: "pointer", color: T.red, fontSize: 14, padding: "0 2px" }}>✕</button>
              </div>
            ))}
            {/* Add link row */}
            <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
              <input
                value={newLink.url}
                onChange={e => setNewLink(l => ({ ...l, url: e.target.value }))}
                placeholder="URL  e.g. /products/cardamom"
                style={{ ...inputStyle, flex: 2 }}
                onKeyDown={e => e.key === "Enter" && addLink()}
              />
              <input
                value={newLink.name}
                onChange={e => setNewLink(l => ({ ...l, name: e.target.value }))}
                placeholder="Label (optional)"
                style={{ ...inputStyle, flex: 1 }}
                onKeyDown={e => e.key === "Enter" && addLink()}
              />
              <button onClick={addLink} style={{
                padding: "6px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
                background: "transparent", cursor: "pointer", fontSize: 16, color: T.purple, flexShrink: 0,
              }}>+</button>
            </div>
          </div>

          {/* Optional title override */}
          <div style={sectionStyle}>
            <label style={labelStyle}>Article Title <span style={{ fontWeight: 400, color: T.gray }}>(optional override)</span></label>
            <input
              value={form.title}
              onChange={e => set("title", e.target.value)}
              placeholder="Leave blank to let AI generate the title"
              style={inputStyle}
            />
          </div>

          </>}

          {activeTab === "bulk" && (
            <BulkTopicsTab form={form} projectId={projectId} onClose={onClose} />
          )}

          {activeTab === "routing" && <>
            {/* System Template presets */}
            <div style={sectionStyle}>
              <label style={labelStyle}>System Templates</label>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {SYSTEM_TEMPLATES.map(tpl => (
                  <button key={tpl.id} onClick={() => applyPreset(tpl)} style={{
                    flex: "1 1 120px", padding: "8px 10px", borderRadius: 8, fontSize: 11,
                    cursor: "pointer",
                    border: tpl.id === DEFAULT_TEMPLATE_ID ? "1px solid #7c3aed80" : `1px solid ${T.border}`,
                    background: tpl.id === DEFAULT_TEMPLATE_ID ? "#7c3aed08" : "transparent",
                    color: tpl.id === DEFAULT_TEMPLATE_ID ? "#7c3aed" : T.gray,
                    textAlign: "center",
                  }}>
                    <div style={{ fontWeight: 600 }}>{tpl.name}</div>
                    <div style={{ fontSize: 9, color: T.textSoft, marginTop: 2 }}>{tpl.description}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Per-task routing table */}
            <div style={sectionStyle}>
              <label style={labelStyle}>Per-Step AI Selection</label>
              <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 10 }}>
                Choose free or paid AI for each pipeline step. Falls back in order on failure.
              </div>

              {/* Legend */}
              <div style={{ display: "flex", gap: 12, marginBottom: 10, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9 }}>
                  <div style={{ width: 8, height: 8, borderRadius: 2, background: "#e0f2fe" }} />
                  <span style={{ color: T.textSoft }}>Free tier steps</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9 }}>
                  <div style={{ width: 8, height: 8, borderRadius: 2, background: "#fdf4ff" }} />
                  <span style={{ color: T.textSoft }}>Content steps (paid recommended)</span>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {ROUTING_TASKS.map(task => {
                  const isPaid = task.tier === "paid"
                  const rowBg = isPaid ? "#fdf4ff" : "#f0f9ff"
                  const borderColor = isPaid ? "#e9d5ff" : "#bae6fd"
                  return (
                    <div key={task.key} style={{
                      padding: "8px 10px", borderRadius: 8,
                      background: rowBg, border: `1px solid ${borderColor}`,
                    }}>
                      {/* Step header */}
                      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                        <div style={{
                          width: 20, height: 20, borderRadius: "50%", flexShrink: 0,
                          background: isPaid ? "#7c3aed" : "#0369a1",
                          color: "#fff", fontSize: 9, fontWeight: 700,
                          display: "flex", alignItems: "center", justifyContent: "center",
                        }}>{task.n}</div>
                        <span style={{ fontSize: 12, fontWeight: 600, color: T.text }}>
                          {task.icon} {task.label}
                        </span>
                        <span style={{
                          fontSize: 8, padding: "1px 5px", borderRadius: 99, fontWeight: 600,
                          background: isPaid ? "#ede9fe" : "#e0f2fe",
                          color: isPaid ? "#6d28d9" : "#0369a1",
                        }}>{isPaid ? "CONTENT" : "RESEARCH"}</span>
                        <span style={{ fontSize: 9, color: T.textSoft, marginLeft: "auto" }}>{task.desc}</span>
                      </div>

                      {/* Choice selectors */}
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                        {[
                          { rank: "first",  label: "1st" },
                          { rank: "second", label: "2nd" },
                          { rank: "third",  label: "3rd" },
                        ].map(({ rank, label }) => {
                          const val = form.ai_routing[task.key]?.[rank] || "skip"
                          const meta = providerLookup[val] || _providerMeta[val] || _providerMeta.skip || { color: "#9ca3af" }
                          return (
                            <div key={rank}>
                              <div style={{ fontSize: 9, color: T.textSoft, marginBottom: 2 }}>{label} choice</div>
                              <select
                                value={val}
                                onChange={e => setRouting(task.key, rank, e.target.value)}
                                style={{
                                  width: "100%", padding: "4px 6px", borderRadius: 6, fontSize: 10,
                                  border: `1.5px solid ${meta.color}60`,
                                  background: val === "skip" ? "#f9fafb" : `${meta.color}08`,
                                  color: meta.color, cursor: "pointer", fontWeight: 500,
                                }}
                              >
                                <optgroup label="── Free Tier ──">
                                  {AI_PROVIDERS.free.map(o => (
                                    <option key={o.value} value={o.value}>{o.label} ({o.desc})</option>
                                  ))}
                                </optgroup>
                                <optgroup label="── Paid Tier ──">
                                  {AI_PROVIDERS.paid.map(o => (
                                    <option key={o.value} value={o.value}>{o.label} ({o.desc})</option>
                                  ))}
                                </optgroup>
                                <optgroup label="──">
                                  <option value="skip">Skip</option>
                                </optgroup>
                              </select>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </>}
        </div>

        {/* Blueprint Plan Review */}
        {showPlan && blueprint && (
          <div style={{ padding: "14px 24px", borderTop: `1px solid ${T.border}`, maxHeight: 300, overflowY: "auto", background: "#f9fafb" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>Content Blueprint</div>
              <button onClick={() => setShowPlan(false)} style={{ background: "none", border: "none", cursor: "pointer", color: T.textSoft, fontSize: 18 }}>×</button>
            </div>

            {/* H1 & Meta */}
            <div style={{ marginBottom: 10, padding: "8px 10px", background: "#fff", borderRadius: 8, border: `1px solid ${T.border}` }}>
              <div style={{ fontSize: 10, color: T.textSoft, fontWeight: 600, marginBottom: 4, textTransform: "uppercase" }}>Title & Meta</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{blueprint.h1}</div>
              <div style={{ fontSize: 10, color: T.teal, marginTop: 2 }}>{blueprint.meta_title}</div>
              <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{blueprint.meta_description}</div>
            </div>

            {/* Sections */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: T.textSoft, fontWeight: 600, marginBottom: 6, textTransform: "uppercase" }}>Sections ({blueprint.sections?.length || 0})</div>
              {(blueprint.sections || []).map((sec, i) => (
                <div key={i} style={{ padding: "6px 10px", background: "#fff", borderRadius: 6, border: `1px solid ${T.border}`, marginBottom: 4 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: T.text }}>{sec.h2}</span>
                    <span style={{ fontSize: 9, color: T.textSoft }}>~{sec.word_target}w</span>
                  </div>
                  {sec.h3s?.length > 0 && (
                    <div style={{ fontSize: 9, color: T.textSoft, marginTop: 2 }}>
                      H3s: {sec.h3s.join(" · ")}
                    </div>
                  )}
                  {sec.must_include?.length > 0 && (
                    <div style={{ display: "flex", gap: 3, flexWrap: "wrap", marginTop: 4 }}>
                      {sec.must_include.map((el, j) => (
                        <span key={j} style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: "#e0f2fe", color: "#0369a1", fontWeight: 500 }}>
                          {el.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* FAQs */}
            {blueprint.faqs?.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, color: T.textSoft, fontWeight: 600, marginBottom: 4, textTransform: "uppercase" }}>FAQs ({blueprint.faqs.length})</div>
                {blueprint.faqs.map((faq, i) => (
                  <div key={i} style={{ fontSize: 10, color: T.text, padding: "3px 0" }}>
                    <strong>Q{i + 1}:</strong> {faq.q}
                  </div>
                ))}
              </div>
            )}

            {/* Required Elements Checklist */}
            <div style={{ padding: "8px 10px", background: "#fff", borderRadius: 8, border: `1px solid ${T.border}` }}>
              <div style={{ fontSize: 10, color: T.textSoft, fontWeight: 600, marginBottom: 6, textTransform: "uppercase" }}>SEO Checklist</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {Object.entries(blueprint.required_elements || {}).map(([key, val]) => {
                  const label = key.replace(/_/g, " ")
                  const display = typeof val === "boolean" ? (val ? "✓" : "—") : val
                  return (
                    <span key={key} style={{
                      fontSize: 9, padding: "2px 6px", borderRadius: 4,
                      background: val ? "#f0fdf4" : "#fef2f2",
                      color: val ? "#15803d" : "#dc2626",
                      fontWeight: 500,
                    }}>
                      {label}: {display}
                    </span>
                  )
                })}
              </div>
            </div>

            {/* Planned word count */}
            <div style={{ marginTop: 8, fontSize: 10, color: T.textSoft, textAlign: "center" }}>
              Planned: ~{blueprint.planned_word_count || "?"} words · Target: {blueprint.target_word_count} words
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={{
          padding: "14px 24px", borderTop: `1px solid ${T.border}`,
          display: "flex", gap: 8, alignItems: "center",
        }}>
          <Btn onClick={onClose} style={{ flex: 1 }}>Cancel</Btn>
          {activeTab !== "bulk" && <>
            <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
              <label style={{ fontSize: 10, color: T.textSoft, cursor: "pointer", display: "flex", alignItems: "center", gap: 3 }}>
                <input type="checkbox" checked={form.step_mode === "pause"}
                  onChange={e => set("step_mode", e.target.checked ? "pause" : "auto")}
                  style={{ accentColor: T.purple }} />
                Step-by-step
              </label>
            </div>
            {!showPlan ? (
              <>
                <Btn
                  onClick={generatePlan}
                  disabled={!form.keyword.trim() || planLoading}
                  style={{ flex: 1 }}
                >
                  {planLoading ? "Planning…" : "Preview Plan 📋"}
                </Btn>
                <Btn
                  onClick={handleSubmit}
                  variant="primary"
                  disabled={!form.keyword.trim() || isPending}
                  style={{ flex: 2 }}
                >
                  {isPending ? "Starting pipeline…" : `Generate ${PAGE_TYPE_OPTIONS.find(p => p.value === form.page_type)?.label || "Article"} ✨`}
                </Btn>
              </>
            ) : (
              <>
                <Btn onClick={() => setShowPlan(false)} style={{ flex: 1 }}>Edit Plan</Btn>
                <Btn
                  onClick={handleSubmit}
                  variant="primary"
                  disabled={!form.keyword.trim() || isPending}
                  style={{ flex: 2 }}
                >
                  {isPending ? "Starting pipeline…" : "Approve & Generate ✨"}
                </Btn>
              </>
            )}
          </>}
        </div>
      </div>
    </div>
  )
}

// Named exports for constants needed by other files
export { AI_PROVIDERS_BASE, AI_PROVIDER_OPTIONS, _buildProviders, _providerMeta, DEFAULT_ROUTING }
// Default export
export default NewArticleModal
