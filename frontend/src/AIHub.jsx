import { useState, useEffect, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { T, api, Btn } from "./App"
import RateLimitDashboard from "./aihub/RateLimitDashboard"
import { SYSTEM_TEMPLATES, DEFAULT_TEMPLATE_ID, expandToLegacyRouting } from "./aihub/systemRoutingTemplates"

// ── Provider Icons ─────────────────────────────────────────────────────────────
const PROVIDER_ICONS = { ollama: "🦙", groq: "⚡", gemini: "💎", gemini_free: "💎", gemini_paid: "💎", chatgpt: "🤖", openai_paid: "🤖", claude: "🧠", anthropic: "🧠", anthropic_paid: "🧠", openrouter: "🌐", or_qwen: "🌐", or_qwen_next: "🌐", or_deepseek: "🌐", or_gemini_flash: "🌐", or_gemini_lite: "🌐", or_glm: "🌐", or_qwq: "🌐", or_phi4: "🌐", or_gemma3: "🌐", or_mistral: "🌐", or_maverick_free: "🌐", or_haiku: "🌐", or_gpt4o: "🌐", or_claude: "🌐", or_llama: "🌐", or_qwen_coder: "🌐", or_deepseek_r1: "🌐", or_gemini_pro: "🌐", or_o4_mini: "🌐", or_claude_opus: "🌐" }
const PROVIDER_LABELS = { ollama: "Ollama", groq: "Groq", gemini: "Gemini", gemini_free: "Gemini", gemini_paid: "Gemini Paid", chatgpt: "ChatGPT", openai_paid: "ChatGPT", claude: "Claude", anthropic: "Claude", anthropic_paid: "Claude Pro", openrouter: "OpenRouter", or_qwen: "OR: GPT-OSS 120B", or_qwen_next: "OR: GPT-OSS 20B", or_deepseek: "OR: DeepSeek V3.2", or_gemini_flash: "OR: Gemini 2.5 Flash", or_gemini_lite: "OR: Gemini 2.0 Lite", or_glm: "OR: GLM 5 Turbo", or_qwq: "OR: QwQ 32B", or_phi4: "OR: Phi-4 Reasoning", or_gemma3: "OR: Gemma 3 27B", or_mistral: "OR: Mistral Small", or_maverick_free: "OR: Llama 4 Free", or_haiku: "OR: Claude Haiku 4.5", or_gpt4o: "OR: GPT-4o", or_claude: "OR: Claude Sonnet 4", or_llama: "OR: Llama 4 Maverick", or_qwen_coder: "OR: Qwen3 Coder 480B", or_deepseek_r1: "OR: DeepSeek R1", or_gemini_pro: "OR: Gemini 2.5 Pro", or_o4_mini: "OR: o4-mini", or_claude_opus: "OR: Claude Opus 4", skip: "Skip" }

const STEPS = [
  { key: "research",     label: "Step 1: Research",         desc: "Topic analysis & crawling" },
  { key: "structure",    label: "Step 2: Structure",         desc: "Outline & headings" },
  { key: "verify",       label: "Step 3: Blueprint",        desc: "3-layer blueprint assembly" },
  { key: "links",        label: "Step 4: Links",            desc: "Internal link planning" },
  { key: "references",   label: "Step 5: References",       desc: "Wikipedia refs + confidence" },
  { key: "draft",        label: "Step 6: Draft",            desc: "Blueprint-controlled generation" },
  { key: "review",       label: "Step 7: Validate & Score", desc: "Deterministic quality check", local: true },
  { key: "recovery",     label: "Step 8: Recovery",         desc: "Section-level targeted fixes" },
  { key: "humanize",     label: "Step 9: Humanize",         desc: "AI pattern removal & voice" },
  { key: "quality_loop", label: "Step 11: Quality Loop",    desc: "Iterative quality improvement" },
  { key: "redevelop",    label: "Step 12: Redevelopment",   desc: "Full content polish pass" },
]

const PHASES = [
  {
    key: "research_planning",
    label: "Research & Planning",
    icon: "🔍",
    color: "#007AFF",
    steps: ["research", "structure", "verify", "links", "references"],
  },
  {
    key: "writing",
    label: "Writing & Recovery",
    icon: "✍️",
    color: "#7c3aed",
    steps: ["draft", "review", "recovery"],
  },
  {
    key: "quality_polish",
    label: "Quality & Polish",
    icon: "✨",
    color: "#16a34a",
    steps: ["humanize", "quality_loop", "redevelop"],
  },
]

// AI-routed steps in v2 pipeline (Validate & Score stays deterministic/local)
const AI_ROUTED_STEPS = new Set(["research", "structure", "verify", "links", "references", "draft", "recovery", "humanize", "quality_loop", "redevelop"])

// Build dynamic provider groups from ALL providers (active + inactive)
function buildProviderGroups(providers = {}) {
  const local = []
  const cloud = []
  const orPrimary = []
  const orSecondary = []
  const customModels = []

  // Process ALL providers — including unconfigured, rate-limited, offline
  Object.entries(providers).forEach(([key, p]) => {
    // Status badge: ⚠ = rate limited, ○ = offline/no-key, nothing = ok/idle
    const badge = p.rate_limited ? " ⚠" : !p.available ? " ○" : ""

    // Custom models (custom_*)
    if (p.is_custom_model || key.startsWith("custom_")) {
      customModels.push({ value: key, label: `🔧 ${p.name || key}${badge}` })
      return
    }

    // OpenRouter model variants (or_*)
    if (p.is_openrouter_model) {
      const entry = { value: key, label: `🌐 ${p.name?.replace("OR: ", "") || key}${badge}` }
      if (p.tier === "primary") orPrimary.push(entry)
      else orSecondary.push(entry)
      return
    }

    // Ollama providers (remote)
    if (key === "ollama") {
      local.push({ value: "ollama", label: `🦙 Ollama (Remote)${badge}` })
    } else if (key.startsWith("ollama_remote_")) {
      const name = p.name || key
      local.push({ value: key, label: `🦙 ${name}${badge}` })
    }
    // Groq
    else if (key === "groq") {
      local.push({ value: "groq", label: `⚡ Groq${badge}` })
    }
    // Cloud/Paid providers — use canonical IDs
    else if (key === "gemini_paid") {
      cloud.push({ value: "gemini_paid", label: `💎 Gemini (Paid)${badge}` })
    } else if (key === "gemini" || key === "gemini_free") {
      cloud.push({ value: "gemini_free", label: `💎 Gemini (Free)${badge}` })
    } else if (key === "anthropic" || key === "anthropic_paid" || key === "claude") {
      cloud.push({ value: "anthropic", label: `🧠 Claude${badge}` })
    } else if (key === "openai_paid" || key === "chatgpt" || key === "openai") {
      cloud.push({ value: "openai_paid", label: `🤖 ChatGPT${badge}` })
    } else if (key === "openrouter") {
      cloud.push({ value: "openrouter", label: `🌐 OpenRouter (default)${badge}` })
    }
  })

  // Remove duplicates
  const localUnique = Array.from(new Map(local.map(p => [p.value, p])).values())
  const cloudUnique = Array.from(new Map(cloud.map(p => [p.value, p])).values())

  const groups = []
  if (localUnique.length > 0) {
    groups.push({ label: "── Free / Local ──", providers: localUnique })
  }
  if (cloudUnique.length > 0) {
    groups.push({ label: "── Cloud (Paid) ──", providers: cloudUnique })
  }
  if (orPrimary.length > 0) {
    groups.push({ label: "── OpenRouter ★ Free ──", providers: orPrimary })
  }
  if (orSecondary.length > 0) {
    groups.push({ label: "── OpenRouter Premium ──", providers: orSecondary })
  }
  if (customModels.length > 0) {
    groups.push({ label: "── Custom Models ──", providers: customModels })
  }
  groups.push({ label: "──", providers: [{ value: "skip", label: "Skip" }] })

  return groups
}

// Fallback for static provider groups
const PROVIDER_GROUPS = [
  { label: "── Free / Local ──", providers: [
    { value: "groq",         label: "⚡ Groq" },
    { value: "ollama",       label: "🦙 Ollama (Remote)" },
  ]},
  { label: "── Cloud (Paid) ──", providers: [
    { value: "gemini_free",    label: "💎 Gemini Free" },
    { value: "gemini_paid",    label: "💎 Gemini Paid" },
    { value: "anthropic",      label: "🧠 Claude" },
    { value: "anthropic_paid", label: "🧠 Claude Pro" },
    { value: "openai_paid",    label: "🤖 ChatGPT" },
    { value: "openrouter",     label: "🌐 OpenRouter (default)" },
  ]},
  { label: "── OpenRouter ★ Free ──", providers: [
    { value: "or_qwen",           label: "🌐 GPT-OSS 120B (Free)" },
    { value: "or_qwen_next",      label: "🌐 GPT-OSS 20B (Free)" },
    { value: "or_qwq",            label: "🌐 QwQ 32B (Free)" },
    { value: "or_phi4",           label: "🌐 Phi-4 Reasoning (Free)" },
    { value: "or_gemma3",         label: "🌐 Gemma 3 27B (Free)" },
    { value: "or_mistral",        label: "🌐 Mistral Small 3.2 (Free)" },
    { value: "or_maverick_free",  label: "🌐 Llama 4 Maverick (Free)" },
    { value: "or_qwen_coder",     label: "🌐 Qwen3 Coder 480B (Free)" },
  ]},
  { label: "── OpenRouter ★ Budget ──", providers: [
    { value: "or_gemini_lite",  label: "🌐 Gemini 2.0 Flash Lite ($0.07/M)" },
    { value: "or_llama",        label: "🌐 Llama 4 Maverick ($0.20/M)" },
    { value: "or_deepseek",     label: "🌐 DeepSeek V3.2 ($0.26/M)" },
    { value: "or_gemini_flash", label: "🌐 Gemini 2.5 Flash ($0.30/M)" },
    { value: "or_deepseek_r1",  label: "🌐 DeepSeek R1 ($0.45/M)" },
    { value: "or_haiku",         label: "🌐 Claude Haiku 4.5 ($0.80/M)" },
  ]},
  { label: "── OpenRouter Premium ──", providers: [
    { value: "or_o4_mini",       label: "🌐 o4-mini ($1.10/M)" },
    { value: "or_glm",           label: "🌐 GLM 5 Turbo ($1.20/M)" },
    { value: "or_gemini_pro",    label: "🌐 Gemini 2.5 Pro ($1.25/M)" },
    { value: "or_gpt4o",         label: "🌐 GPT-4o ($2.50/M)" },
    { value: "or_claude",        label: "🌐 Claude Sonnet 4 ($3/M)" },
    { value: "or_claude_opus",   label: "🌐 Claude Opus 4 ($15/M)" },
  ]},
  { label: "──", providers: [
    { value: "skip",  label: "Skip" },
  ]},
]

// ── Status Badge ───────────────────────────────────────────────────────────────
function StatusBadge({ status, label }) {
  const colors = {
    ok: { bg: "#E8F8EC", text: "#1B7A2E", dot: "#34C759" },
    running: { bg: "#E8F8EC", text: "#1B7A2E", dot: "#34C759" },
    idle: { bg: "#FFF8E6", text: "#8A6D00", dot: "#FF9500" },
    rate_limited: { bg: "#FFF0EB", text: "#CC3300", dot: "#FF3B30" },
    error: { bg: "#FFF0EB", text: "#CC3300", dot: "#FF3B30" },
    offline: { bg: "#F2F2F7", text: "#8E8E93", dot: "#8E8E93" },
    unconfigured: { bg: "#F2F2F7", text: "#8E8E93", dot: "#C7C7CC" },
    critical: { bg: "#FFF0EB", text: "#CC3300", dot: "#FF3B30" },
    warning: { bg: "#FFF8E6", text: "#8A6D00", dot: "#FF9500" },
  }
  const c = colors[status] || colors.unconfigured
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 600,
      background: c.bg, color: c.text,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.dot }} />
      {label || status}
    </span>
  )
}

// ── Memory Bar ─────────────────────────────────────────────────────────────────
function MemBar({ pct, label }) {
  const color = pct < 70 ? T.teal : pct < 85 ? T.amber : T.red
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: T.textSoft, marginBottom: 3 }}>
        <span>{label}</span><span style={{ fontWeight: 600, color }}>{pct}%</span>
      </div>
      <div style={{ height: 6, background: "#E5E5EA", borderRadius: 99 }}>
        <div style={{ height: 6, borderRadius: 99, background: color, width: `${Math.min(pct, 100)}%`, transition: "width 0.4s" }} />
      </div>
    </div>
  )
}

// ── Per-Key Status Slider ──────────────────────────────────────────────────────
function KeySlider({ keys }) {
  const [idx, setIdx] = useState(0)
  if (!keys || keys.length === 0) return null
  const k = keys[idx]
  const rl = k.rate_limit_info || {}
  return (
    <div style={{ fontSize: 10, padding: "8px 10px", background: "#F4F8FF", borderRadius: 8, border: "1px solid #E0E8F5" }}>
      {/* Slider header with arrows */}
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 5 }}>
        <button onClick={() => setIdx(Math.max(0, idx - 1))} disabled={idx === 0}
          style={{ border: "none", background: "none", cursor: idx === 0 ? "default" : "pointer", fontSize: 13, opacity: idx === 0 ? 0.25 : 0.8, padding: "0 2px", lineHeight: 1 }}>◀</button>
        <div style={{ flex: 1, textAlign: "center", display: "flex", alignItems: "center", justifyContent: "center", gap: 5 }}>
          <span style={{ fontWeight: 700, color: T.text, fontSize: 11 }}>{k.name}</span>
          {k.is_default && <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: "#3478F6", color: "#fff", fontWeight: 700 }}>DEFAULT</span>}
          {k.tier && <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: k.tier === "paid" ? "#FF950020" : "#34C75920", color: k.tier === "paid" ? "#8A6D00" : "#1B7A2E", fontWeight: 600 }}>{k.tier}</span>}
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: k.status === "ok" ? "#34C759" : k.status === "rate_limited" ? "#FF3B30" : "#8E8E93" }} />
        </div>
        <button onClick={() => setIdx(Math.min(keys.length - 1, idx + 1))} disabled={idx === keys.length - 1}
          style={{ border: "none", background: "none", cursor: idx === keys.length - 1 ? "default" : "pointer", fontSize: 13, opacity: idx === keys.length - 1 ? 0.25 : 0.8, padding: "0 2px", lineHeight: 1 }}>▶</button>
      </div>
      {/* Dots */}
      {keys.length > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 4, marginBottom: 6 }}>
          {keys.map((_, i) => (
            <span key={i} onClick={() => setIdx(i)} style={{
              width: 6, height: 6, borderRadius: "50%", cursor: "pointer",
              background: i === idx ? T.purple : "#D1D1D6", transition: "background 0.2s",
            }} />
          ))}
        </div>
      )}
      {/* Key mask */}
      {k.key_masked && <div style={{ textAlign: "center", fontSize: 9, color: T.textSoft, fontFamily: "monospace", marginBottom: 4 }}>{k.key_masked}</div>}
      {/* Rate limit bars */}
      {rl.requests_remaining && rl.requests_limit && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
            <span style={{ color: T.textSoft }}>Requests</span>
            <span style={{ fontWeight: 600, color: T.text }}>{rl.requests_remaining}/{rl.requests_limit}</span>
          </div>
          <div style={{ height: 4, background: "#E5E5EA", borderRadius: 99 }}>
            <div style={{ height: 4, borderRadius: 99, background: T.teal, width: `${Math.min(100, (Number(rl.requests_remaining) / Number(rl.requests_limit)) * 100)}%`, transition: "width 0.3s" }} />
          </div>
          {rl.tokens_remaining && rl.tokens_limit && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3, marginTop: 6 }}>
                <span style={{ color: T.textSoft }}>Tokens</span>
                <span style={{ fontWeight: 600, color: T.text }}>{Number(rl.tokens_remaining).toLocaleString()}/{Number(rl.tokens_limit).toLocaleString()}</span>
              </div>
              <div style={{ height: 4, background: "#E5E5EA", borderRadius: 99 }}>
                <div style={{ height: 4, borderRadius: 99, background: T.purple, width: `${Math.min(100, (Number(rl.tokens_remaining) / Number(rl.tokens_limit)) * 100)}%`, transition: "width 0.3s" }} />
              </div>
            </>
          )}
          {rl.requests_reset && (
            <div style={{ fontSize: 9, color: T.textSoft, marginTop: 4 }}>Resets in {rl.requests_reset}</div>
          )}
        </>
      )}
      {/* Gemini paid model status */}
      {k.models_status && Object.keys(k.models_status).length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 5 }}>
          {Object.entries(k.models_status).map(([m, s]) => (
            <span key={m} style={{
              fontSize: 9, padding: "1px 5px", borderRadius: 3,
              background: s === "ok" ? "#E8F8EC" : s === "rate_limited" ? "#FFF0EB" : "#F2F2F7",
              color: s === "ok" ? "#1B7A2E" : s === "rate_limited" ? "#CC3300" : "#8E8E93",
            }}>
              {m.replace("gemini-", "").replace("-", " ")} {s === "ok" ? "✓" : s === "rate_limited" ? "429" : "✗"}
            </span>
          ))}
        </div>
      )}
      {/* Status text for non-ok keys */}
      {k.status !== "ok" && !rl.requests_remaining && (
        <div style={{ textAlign: "center", fontSize: 10, color: k.status === "rate_limited" ? "#CC3300" : "#8E8E93", fontWeight: 600, marginTop: 2 }}>
          {k.status === "rate_limited" ? "⚠ Rate Limited (429)" : k.status === "error" ? "✗ Error" : k.status === "timeout" ? "⏱ Timeout" : k.status}
        </div>
      )}
    </div>
  )
}

// ── Provider Card ──────────────────────────────────────────────────────────────
function ProviderCard({ id, p, onTest, onToggle }) {
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)

  const handleTest = async () => {
    setTesting(true); setTestResult(null)
    try {
      const r = await api.post("/api/settings/ai/test", { provider: id })
      setTestResult(r)
    } catch (e) { setTestResult({ ok: false, error: e.message }) }
    setTesting(false)
  }

  // Rate limit info for Groq
  const rl = p.rate_limit_info || {}

  return (
    <div style={{
      padding: 16, borderRadius: 12, background: p.disabled ? "#FAFAFA" : "#fff",
      border: `1px solid ${p.disabled ? "#CCC" : p.available ? `${T.teal}40` : p.rate_limited ? `${T.red}30` : T.border}`,
      display: "flex", flexDirection: "column", gap: 8,
      opacity: p.disabled ? 0.65 : 1,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 22 }}>{PROVIDER_ICONS[id] || "🔌"}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>{p.name}</div>
          <div style={{ fontSize: 11, color: T.textSoft }}>{p.model}</div>
        </div>
        {p.disabled
          ? <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 10, background: "#F2F2F7", color: "#888", fontWeight: 600 }}>DISABLED</span>
          : <StatusBadge status={p.status} />
        }
      </div>

      {/* Detail row */}
      {p.detail && (
        <div style={{ fontSize: 11, color: p.rate_limited ? T.red : T.textSoft, padding: "4px 8px", background: p.rate_limited ? "#FFF0EB" : "#F9F9F9", borderRadius: 6 }}>
          {p.detail}
        </div>
      )}

      {/* Per-key slider (for providers with multiple keys and per_key_status) */}
      {p.per_key_status && p.per_key_status.length > 0 ? (
        <KeySlider keys={p.per_key_status} />
      ) : (
        /* Fallback: Rate limit bars — Groq tokens/requests (single key) */
        rl.requests_remaining && rl.requests_limit && (
        <div style={{ fontSize: 10, padding: "6px 8px", background: "#F4F8FF", borderRadius: 6 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
            <span style={{ color: T.textSoft }}>Requests</span>
            <span style={{ fontWeight: 600, color: T.text }}>{rl.requests_remaining}/{rl.requests_limit}</span>
          </div>
          <div style={{ height: 4, background: "#E5E5EA", borderRadius: 99 }}>
            <div style={{ height: 4, borderRadius: 99, background: T.teal, width: `${Math.min(100, (Number(rl.requests_remaining) / Number(rl.requests_limit)) * 100)}%`, transition: "width 0.3s" }} />
          </div>
          {rl.tokens_remaining && rl.tokens_limit && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3, marginTop: 6 }}>
                <span style={{ color: T.textSoft }}>Tokens</span>
                <span style={{ fontWeight: 600, color: T.text }}>{Number(rl.tokens_remaining).toLocaleString()}/{Number(rl.tokens_limit).toLocaleString()}</span>
              </div>
              <div style={{ height: 4, background: "#E5E5EA", borderRadius: 99 }}>
                <div style={{ height: 4, borderRadius: 99, background: T.purple, width: `${Math.min(100, (Number(rl.tokens_remaining) / Number(rl.tokens_limit)) * 100)}%`, transition: "width 0.3s" }} />
              </div>
            </>
          )}
          {rl.requests_reset && (
            <div style={{ fontSize: 9, color: T.textSoft, marginTop: 4 }}>Resets in {rl.requests_reset}</div>
          )}
        </div>
        )
      )}

      {/* Info grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px", fontSize: 11 }}>
        <span style={{ color: T.textSoft }}>Cost</span><span style={{ color: T.text, fontWeight: 500 }}>{p.cost || "—"}</span>
        <span style={{ color: T.textSoft }}>Speed</span><span style={{ color: T.text, fontWeight: 500 }}>{p.speed || "—"}</span>
        <span style={{ color: T.textSoft }}>Quality</span><span style={{ color: T.text, fontWeight: 500 }}>{p.quality || "—"}</span>
      </div>

      {/* Multi-key count */}
      {p.multi_keys_count > 0 && (
        <div style={{ fontSize: 10, padding: "3px 6px", background: "#E8F8EC", borderRadius: 4, color: "#1B7A2E" }}>
          🔑 {p.multi_keys_enabled}/{p.multi_keys_count} keys active{p.multi_keys_default ? ` — Default: ${p.multi_keys_default}` : ""}
        </div>
      )}

      {/* Limits */}
      {p.limits && <div style={{ fontSize: 10, color: T.textSoft, padding: "3px 6px", background: "#F2F2F7", borderRadius: 4 }}>📊 {p.limits}</div>}

      {/* Ollama local: RAM usage */}
      {id === "ollama" && p.model_loaded && p.loaded_ram_mb > 0 && (
        <MemBar pct={Math.round((p.loaded_ram_mb / 2100) * 100)} label={`Model RAM: ${p.loaded_ram_mb}MB / ~2100MB`} />
      )}

      {/* Remote Ollama: version, running models, memory, proxy health */}
      {id.startsWith("ollama_remote_") && (
        <>
          <div style={{ fontSize: 10, color: T.textSoft }}>
            {p.version && p.version !== "unknown" ? `🔖 v${p.version} · ` : ""}
            {Array.isArray(p.models_installed) ? `${p.models_installed.length} model${p.models_installed.length !== 1 ? "s" : ""} installed` : ""}
          </div>
          {Array.isArray(p.running_models) && p.running_models.length > 0 && (
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {p.running_models.map((m, i) => (
                <span key={i} style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: "#E8F8EC", color: "#1B7A2E" }}>
                  ▶ {m.name} {m.size_mb > 0 ? `(${m.size_mb}MB)` : ""}
                </span>
              ))}
            </div>
          )}
          {p.remote_system && p.remote_system.ram_percent !== undefined && (
            <MemBar pct={Math.round(p.remote_system.ram_percent)} label={`Remote RAM: ${p.remote_system.ram_available_gb ? p.remote_system.ram_available_gb.toFixed(1) + "GB free" : ""}`} />
          )}
          {p.remote_circuit_breaker && p.remote_circuit_breaker.open && (
            <div style={{ fontSize: 10, color: T.red, fontWeight: 600 }}>⚠ Circuit breaker OPEN — {p.remote_circuit_breaker.cooldown_remaining_sec}s remaining</div>
          )}
          {p.remote_queue_slots !== undefined && (
            <div style={{ fontSize: 10, color: T.textSoft }}>Queue slots: {p.remote_queue_slots}</div>
          )}
          {p.loaded_ram_mb > 0 && (
            <MemBar pct={Math.round((p.loaded_ram_mb / 8192) * 100)} label={`Model RAM: ${p.loaded_ram_mb}MB`} />
          )}
          {Array.isArray(p.models_installed) && p.models_installed.length > 0 && (
            <div style={{ fontSize: 10, color: T.textSoft, lineHeight: 1.6 }}>
              {p.models_installed.slice(0, 5).join(" · ")}
              {p.models_installed.length > 5 ? ` +${p.models_installed.length - 5} more` : ""}
            </div>
          )}
        </>
      )}

      {/* Gemini model status (only show models_status badges if no per_key_status slider) */}
      {(id === "gemini" || id === "gemini_free" || id === "gemini_paid") && p.models_status && !p.per_key_status?.length && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {Object.entries(p.models_status).map(([m, s]) => (
            <span key={m} style={{
              fontSize: 10, padding: "2px 6px", borderRadius: 4,
              background: s === "ok" ? "#E8F8EC" : s === "rate_limited" ? "#FFF0EB" : "#F2F2F7",
              color: s === "ok" ? "#1B7A2E" : s === "rate_limited" ? "#CC3300" : T.gray,
            }}>
              {m.replace("gemini-", "").replace("-", " ")} — {s === "ok" ? "✓" : s === "rate_limited" ? "429" : s === "deprecated" ? "404" : "✗"}
            </span>
          ))}
        </div>
      )}

      {/* Note */}
      {p.note && <div style={{ fontSize: 10, color: T.textSoft, fontStyle: "italic" }}>{p.note}</div>}

      {/* Test + Disable + Error */}
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        {(id === "ollama" || id === "groq" || id === "gemini" || id === "gemini_free" || id === "gemini_paid" || id.startsWith("ollama_remote_")) && (
          <button onClick={handleTest} disabled={testing} style={{
            padding: "4px 10px", borderRadius: 6, border: `1px solid ${T.border}`,
            background: "#fff", fontSize: 11, cursor: "pointer", fontWeight: 500,
            opacity: testing ? 0.5 : 1,
          }}>
            {testing ? "Testing…" : "🧪 Test"}
          </button>
        )}
        {onToggle && (
          <button onClick={onToggle} style={{
            padding: "4px 10px", borderRadius: 6, fontSize: 11, cursor: "pointer", fontWeight: 500,
            border: `1px solid ${p.disabled ? T.teal + "60" : "#CC330040"}`,
            background: p.disabled ? `${T.teal}10` : "#FFF0EB",
            color: p.disabled ? T.teal : "#CC3300",
          }}>
            {p.disabled ? "⚡ Enable" : "⛔ Disable"}
          </button>
        )}
        {testResult && (
          <span style={{ fontSize: 11, color: testResult.ok ? T.teal : T.red }}>
            {testResult.ok ? `✓ ${testResult.response?.slice(0, 50)}` : `✗ ${testResult.error?.slice(0, 60)}`}
          </span>
        )}
      </div>

      {/* Key status */}
      {p.key_configured === false && id !== "ollama" && !id.startsWith("ollama_") && (
        <div style={{ fontSize: 11, color: T.amber, fontWeight: 600 }}>⚠️ No API key configured — add in AI Hub → API Keys</div>
      )}
    </div>
  )
}

// ── Routing Tiers — 5 smart categories ────────────────────────────────────────
// Based on real cost data: Flash Redevelop=10K tok $0.003, Claude Draft=2.7K tok $0.017
const TIERS = [
  {
    id: "smart_balance",
    label: "⚖️ Smart Balance",
    desc: "Best value — Flash quality at $0.30/M, DeepSeek fallback, free safety net",
    color: "#6366f1", bg: "#eef2ff",
    chain: { first: "or_gemini_flash", second: "or_deepseek", third: "or_qwen" },
    models: ["Gemini 2.5 Flash", "DeepSeek V3.2", "GPT-OSS 120B"],
  },
  {
    id: "turbo_free",
    label: "🆓 Turbo Free",
    desc: "100% free — Groq fastest + OR free models, zero cost",
    color: "#10b981", bg: "#ecfdf5",
    chain: { first: "groq", second: "or_qwen", third: "or_gemma3" },
    models: ["Groq", "GPT-OSS 120B", "Gemma 3 27B"],
  },
  {
    id: "budget",
    label: "💸 Budget",
    desc: "Ultra cheap paid — Gemini Lite at $0.07/M, DeepSeek V3.2 fallback",
    color: "#f59e0b", bg: "#fef3c7",
    chain: { first: "or_gemini_lite", second: "or_deepseek", third: "or_qwen" },
    models: ["Gemini 2.0 Lite", "DeepSeek V3.2", "GPT-OSS 120B"],
  },
  {
    id: "quality",
    label: "💎 Quality",
    desc: "High quality — Flash workhorse, Gemini Pro for hard steps",
    color: "#0ea5e9", bg: "#e0f2fe",
    chain: { first: "or_gemini_flash", second: "or_gemini_pro", third: "or_claude" },
    models: ["Gemini 2.5 Flash", "Gemini 2.5 Pro", "Claude Sonnet 4"],
  },
  {
    id: "premium",
    label: "👑 Premium",
    desc: "Top tier — Gemini Pro + Claude Sonnet 4, best output quality",
    color: "#7c3aed", bg: "#f3e8ff",
    chain: { first: "or_gemini_pro", second: "or_claude", third: "or_o4_mini" },
    models: ["Gemini 2.5 Pro", "Claude Sonnet 4", "o4-mini"],
  },
]

// ── Step Row ──────────────────────────────────────────────────────────────────
function StepRow({ stepDef, config, onChange, providerGroups }) {
  const groups = providerGroups || PROVIDER_GROUPS
  const isAiRouted = AI_ROUTED_STEPS.has(stepDef.key)
  const tierMatch = TIERS.find(t =>
    t.chain.first === (config?.first || "skip") &&
    t.chain.second === (config?.second || "skip") &&
    t.chain.third === (config?.third || "skip")
  )
  return (
    <tr style={{ borderBottom: "1px solid rgba(60,60,67,0.07)" }}>
      <td style={{ padding: "8px 12px", verticalAlign: "middle" }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{stepDef.label.replace(/Step \d+: /, "")}</div>
        <div style={{ fontSize: 10, color: T.textSoft }}>{stepDef.desc}</div>
      </td>
      {isAiRouted ? (
        ["first", "second", "third"].map(slot => (
          <td key={slot} style={{ padding: "6px 8px", verticalAlign: "middle" }}>
            <select
              value={config?.[slot] || "skip"}
              onChange={e => onChange(slot, e.target.value)}
              style={{
                width: "100%", padding: "5px 6px", borderRadius: 6,
                border: "1px solid rgba(60,60,67,0.15)",
                fontSize: 11, background: "#fff", cursor: "pointer",
              }}
            >
              {groups.map(g => (
                <optgroup key={g.label} label={g.label}>
                  {g.providers.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </optgroup>
              ))}
            </select>
          </td>
        ))
      ) : (
        <td colSpan={3} style={{ padding: "6px 8px", textAlign: "center", verticalAlign: "middle" }}>
          <span style={{
            display: "inline-block", padding: "4px 12px", borderRadius: 20, fontSize: 11, fontWeight: 600,
            background: "#ecfdf5", color: "#059669", border: "1px solid #a7f3d030",
          }}>
            Deterministic (No AI Call)
          </span>
        </td>
      )}
      <td style={{ padding: "6px 8px", textAlign: "center", verticalAlign: "middle" }}>
        {isAiRouted ? (
          tierMatch ? (
            <span style={{
              display: "inline-block", padding: "2px 7px", borderRadius: 20, fontSize: 9, fontWeight: 700,
              background: tierMatch.bg, color: tierMatch.color, border: `1px solid ${tierMatch.color}30`,
              whiteSpace: "nowrap",
            }}>
              {tierMatch.label.split(" ").slice(0, 2).join(" ")}
            </span>
          ) : (
            <span style={{
              display: "inline-block", padding: "2px 7px", borderRadius: 20, fontSize: 9, fontWeight: 600,
              background: "#f1f5f9", color: "#64748b",
            }}>
              Custom
            </span>
          )
        ) : (
          <span style={{ fontSize: 9, color: T.textSoft }}>—</span>
        )}
      </td>
    </tr>
  )
}

// ── Phase Group ────────────────────────────────────────────────────────────────
function PhaseGroup({ phase, routing, onChangeStep, providerGroups }) {
  const [open, setOpen] = useState(true)
  const stepDefs = STEPS.filter(s => phase.steps.includes(s.key))

  const detectPhaseTier = () => {
    for (const tier of TIERS) {
      const allMatch = phase.steps.every(key => {
        const r = routing[key]
        return r && r.first === tier.chain.first && r.second === tier.chain.second && r.third === tier.chain.third
      })
      if (allMatch) return tier.id
    }
    return ""
  }
  const phaseTier = detectPhaseTier()

  const applyToPhase = (tierId) => {
    const tier = TIERS.find(t => t.id === tierId)
    if (!tier) return
    phase.steps.forEach(key => onChangeStep(key, { ...tier.chain }))
  }

  return (
    <div style={{ borderRadius: 10, border: "1px solid rgba(60,60,67,0.12)", overflow: "hidden", marginBottom: 12 }}>
      <div
        style={{
          display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
          background: phase.color + "0d", borderLeft: `3px solid ${phase.color}`, cursor: "pointer",
        }}
        onClick={() => setOpen(o => !o)}
      >
        <span style={{ fontSize: 15 }}>{phase.icon}</span>
        <span style={{ flex: 1, fontSize: 13, fontWeight: 700, color: T.text }}>{phase.label}</span>
        <div onClick={e => e.stopPropagation()} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 10, color: T.textSoft, fontWeight: 600 }}>Apply tier:</span>
          <select
            value={phaseTier}
            onChange={e => applyToPhase(e.target.value)}
            style={{ padding: "3px 8px", borderRadius: 6, fontSize: 11, border: "1px solid rgba(60,60,67,0.2)", background: "#fff", cursor: "pointer" }}
          >
            <option value="">— Mixed —</option>
            {TIERS.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </div>
        <span style={{ fontSize: 12, color: T.textSoft }}>{open ? "▾" : "▸"}</span>
      </div>
      {open && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f5f5f7" }}>
                <th style={{ padding: "6px 12px", textAlign: "left", fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5 }}>Step</th>
                <th style={{ padding: "6px 8px", textAlign: "left", fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, width: "21%" }}>1st Priority</th>
                <th style={{ padding: "6px 8px", textAlign: "left", fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, width: "21%" }}>2nd Priority</th>
                <th style={{ padding: "6px 8px", textAlign: "left", fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, width: "21%" }}>3rd Priority</th>
                <th style={{ padding: "6px 8px", textAlign: "center", fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, width: 80 }}>Tier</th>
              </tr>
            </thead>
            <tbody>
              {stepDefs.map(s => (
                <StepRow
                  key={s.key}
                  stepDef={s}
                  config={routing[s.key]}
                  onChange={(slot, val) => onChangeStep(s.key, { ...(routing[s.key] || {}), [slot]: val })}
                  providerGroups={providerGroups}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Routing Table ──────────────────────────────────────────────────────────────
function RoutingTable({ routing, onChange, providerGroups }) {
  const handleChangeStep = (stepKey, newConfig) => {
    onChange({ ...routing, [stepKey]: newConfig })
  }

  const applyToAll = (tier) => {
    const updated = {}
    STEPS.forEach(s => { updated[s.key] = { ...tier.chain } })
    onChange({ ...routing, ...updated })
  }

  const detectGlobalTier = () => {
    for (const tier of TIERS) {
      if (STEPS.every(s => {
        const r = routing[s.key]
        return r && r.first === tier.chain.first && r.second === tier.chain.second && r.third === tier.chain.third
      })) return tier.id
    }
    return null
  }
  const globalTier = detectGlobalTier()

  return (
    <div style={{ padding: 16 }}>
      {/* Global tier quick-apply bar */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
          Apply to all steps
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {TIERS.map(tier => {
            const isActive = globalTier === tier.id
            return (
              <button key={tier.id} onClick={() => applyToAll(tier)} title={tier.desc}
                style={{
                  padding: "7px 14px", borderRadius: 20, fontSize: 12, fontWeight: isActive ? 700 : 500,
                  cursor: "pointer", transition: "all 0.15s",
                  border: `2px solid ${isActive ? tier.color : tier.color + "50"}`,
                  background: isActive ? tier.color : tier.bg,
                  color: isActive ? "#fff" : tier.color,
                  boxShadow: isActive ? `0 2px 8px ${tier.color}30` : "none",
                }}
                onMouseEnter={e => { if (!isActive) e.currentTarget.style.borderColor = tier.color }}
                onMouseLeave={e => { if (!isActive) e.currentTarget.style.borderColor = tier.color + "50" }}
              >
                {tier.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Phase-grouped matrix */}
      {PHASES.map(phase => (
        <PhaseGroup
          key={phase.key}
          phase={phase}
          routing={routing}
          onChangeStep={handleChangeStep}
          providerGroups={providerGroups}
        />
      ))}
    </div>
  )
}

// ── System Templates now imported from ./aihub/systemRoutingTemplates.js ──────

// ── Button Styles ──────────────────────────────────────────────────────────────
const smallBtn = { padding: "3px 10px", borderRadius: 6, border: "1px solid #E5E5EA", background: "#fff", fontSize: 11, cursor: "pointer", fontWeight: 500 }

// ── Log Table ──────────────────────────────────────────────────────────────────
const thStyle = { padding: "6px 10px", textAlign: "left", fontSize: 10, fontWeight: 700, color: "rgba(60,60,67,0.55)", textTransform: "uppercase", letterSpacing: 0.5, borderBottom: "1px solid rgba(60,60,67,0.12)" }
const tdStyle = { padding: "6px 10px", fontSize: 12, color: "#000000", borderBottom: "1px solid rgba(60,60,67,0.12)", verticalAlign: "middle" }

function LogTable({ logs }) {
  if (!logs || logs.length === 0) return <div style={{ fontSize: 12, color: T.textSoft, padding: 16 }}>No recent AI logs.</div>
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
        <thead>
          <tr style={{ background: "#F9F9F9" }}>
            {["Time", "Step", "Model", "Tokens", "Cost", "Status"].map(h => <th key={h} style={thStyle}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {logs.map((l, i) => (
            <tr key={i} style={{ background: l.error ? "#FFF8F7" : undefined }}>
              <td style={{ ...tdStyle, whiteSpace: "nowrap", color: T.textSoft }}>{l.time ? new Date(l.time).toLocaleString() : "—"}</td>
              <td style={tdStyle}>{l.step || "—"}</td>
              <td style={{ ...tdStyle, fontWeight: 500 }}>{l.model || "—"}</td>
              <td style={tdStyle}>{l.tokens || "—"}</td>
              <td style={tdStyle}>{l.cost ? `$${l.cost.toFixed(4)}` : "—"}</td>
              <td style={tdStyle}>
                {l.error
                  ? <span style={{ color: T.red, fontWeight: 600 }}>✗ {l.error.slice(0, 60)}</span>
                  : <span style={{ color: T.teal }}>✓ OK</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Usage Stats ────────────────────────────────────────────────────────────────
function UsageStats({ stats }) {
  if (!stats || stats.length === 0) return <div style={{ fontSize: 12, color: T.textSoft, padding: 16 }}>No usage data in last 7 days.</div>
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
      {stats.map((s, i) => (
        <div key={i} style={{ padding: 14, background: "#fff", borderRadius: 10, border: `1px solid ${T.border}` }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 6 }}>{s.model}</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, fontSize: 11 }}>
            <span style={{ color: T.textSoft }}>Calls</span><span style={{ fontWeight: 600 }}>{s.calls}</span>
            <span style={{ color: T.textSoft }}>Input</span><span>{(s.input_tokens || 0).toLocaleString()} tok</span>
            <span style={{ color: T.textSoft }}>Output</span><span>{(s.output_tokens || 0).toLocaleString()} tok</span>
            <span style={{ color: T.textSoft }}>Cost</span><span style={{ fontWeight: 600, color: s.cost_usd > 0 ? T.amber : T.teal }}>{s.cost_usd > 0 ? `$${s.cost_usd.toFixed(4)}` : "Free"}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── API Keys Manager ───────────────────────────────────────────────────────────
const KEY_PROVIDER_OPTIONS = [
  { value: "groq",        label: "⚡ Groq",       model: "llama-3.3-70b-versatile" },
  { value: "gemini",      label: "💎 Gemini",     model: "gemini-2.5-flash" },
  { value: "openai",      label: "🤖 OpenAI",     model: "gpt-4o" },
  { value: "anthropic",   label: "🧠 Claude",     model: "claude-sonnet-4-6" },
  { value: "openrouter",  label: "🌐 OpenRouter", model: "openai/gpt-4o" },
]

const testStatusColors = {
  ok: { bg: "#E8F8EC", text: "#1B7A2E" },
  rate_limited: { bg: "#FFF0EB", text: "#CC3300" },
  invalid: { bg: "#FFF0EB", text: "#CC3300" },
  error: { bg: "#FFF0EB", text: "#CC3300" },
  untested: { bg: "#F2F2F7", text: "#8E8E93" },
}

function APIKeysManager() {
  const qclient = useQueryClient()
  const { data: keys = [], refetch } = useQuery({
    queryKey: ["provider-keys"],
    queryFn: () => api.get("/api/settings/provider-keys"),
  })
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState({ provider: "groq", name: "", api_key: "", model: "" })
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState("")
  const [testingId, setTestingId] = useState(null)
  const [testResults, setTestResults] = useState({})

  const handleAdd = async () => {
    setAdding(true); setAddError("")
    try {
      await api.post("/api/settings/provider-keys", {
        ...addForm,
        model: addForm.model || KEY_PROVIDER_OPTIONS.find(o => o.value === addForm.provider)?.model || "",
      })
      setShowAdd(false)
      setAddForm({ provider: "groq", name: "", api_key: "", model: "" })
      refetch()
      qclient.invalidateQueries(["ai-dashboard"])
    } catch (e) {
      setAddError(e.message || "Failed to add key")
    }
    setAdding(false)
  }

  const handleDelete = async (keyId, name) => {
    if (!confirm(`Delete key "${name}"?`)) return
    try {
      await api.delete(`/api/settings/provider-keys/${keyId}`)
      refetch()
      qclient.invalidateQueries(["ai-dashboard"])
    } catch (e) { alert(e.message) }
  }

  const handleTest = async (keyId) => {
    setTestingId(keyId)
    try {
      const r = await api.post(`/api/settings/provider-keys/${keyId}/test`)
      setTestResults(prev => ({ ...prev, [keyId]: r }))
      refetch()
    } catch (e) {
      setTestResults(prev => ({ ...prev, [keyId]: { status: "error", detail: e.message } }))
    }
    setTestingId(null)
  }

  const handleSetDefault = async (keyId) => {
    try {
      await api.post(`/api/settings/provider-keys/${keyId}/set-default`)
      refetch()
      qclient.invalidateQueries(["ai-dashboard"])
    } catch (e) { alert(e.message) }
  }

  const handleToggle = async (keyId, currentEnabled, provider, name, apiKeyMasked) => {
    try {
      await api.put(`/api/settings/provider-keys/${keyId}`, {
        provider, name, api_key: "****", model: "",
        enabled: !currentEnabled, is_default: false,
      })
      refetch()
    } catch (e) { alert(e.message) }
  }

  // Group keys by provider
  const grouped = {}
  keys.forEach(k => {
    if (!grouped[k.provider]) grouped[k.provider] = []
    grouped[k.provider].push(k)
  })

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>🔑 API Keys</div>
          <div style={{ fontSize: 11, color: T.textSoft }}>Add multiple API keys per provider. Keys rotate automatically. Duplicate keys are flagged.</div>
        </div>
        <button onClick={() => setShowAdd(!showAdd)} style={{
          padding: "6px 14px", borderRadius: 8, border: `1px solid ${T.purple}40`,
          background: T.purpleLight, color: T.purple, fontSize: 12, fontWeight: 600, cursor: "pointer",
        }}>
          {showAdd ? "Cancel" : "+ Add Key"}
        </button>
      </div>

      {/* Add Key Form */}
      {showAdd && (
        <div style={{ padding: 16, background: "#fff", borderRadius: 12, border: `1px solid ${T.purple}30` }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
            <div>
              <label style={{ fontSize: 11, color: T.textSoft, display: "block", marginBottom: 3 }}>Provider</label>
              <select value={addForm.provider} onChange={e => setAddForm({ ...addForm, provider: e.target.value })}
                style={{ width: "100%", padding: "6px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12 }}>
                {KEY_PROVIDER_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, color: T.textSoft, display: "block", marginBottom: 3 }}>Name (unique label)</label>
              <input value={addForm.name} onChange={e => setAddForm({ ...addForm, name: e.target.value })}
                placeholder="e.g. Groq Key 1, Gemini Production"
                style={{ width: "100%", padding: "6px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12 }} />
            </div>
          </div>
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 11, color: T.textSoft, display: "block", marginBottom: 3 }}>API Key</label>
            <input value={addForm.api_key} onChange={e => setAddForm({ ...addForm, api_key: e.target.value })}
              type="password" placeholder="Paste API key here"
              style={{ width: "100%", padding: "6px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12, fontFamily: "monospace" }} />
          </div>
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 11, color: T.textSoft, display: "block", marginBottom: 3 }}>Model (optional — uses default if empty)</label>
            <input value={addForm.model} onChange={e => setAddForm({ ...addForm, model: e.target.value })}
              placeholder={KEY_PROVIDER_OPTIONS.find(o => o.value === addForm.provider)?.model || ""}
              style={{ width: "100%", padding: "6px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12 }} />
          </div>
          {addError && <div style={{ fontSize: 11, color: T.red, marginBottom: 8, fontWeight: 600 }}>⚠️ {addError}</div>}
          <button onClick={handleAdd} disabled={adding || !addForm.name || !addForm.api_key}
            style={{ padding: "8px 20px", borderRadius: 8, border: "none", background: T.purple, color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer", opacity: adding ? 0.5 : 1 }}>
            {adding ? "Adding…" : "Add Key"}
          </button>
        </div>
      )}

      {/* Keys by provider */}
      {KEY_PROVIDER_OPTIONS.map(prov => {
        const provKeys = grouped[prov.value] || []
        return (
          <div key={prov.value} style={{ background: "#fff", borderRadius: 12, border: `1px solid ${T.border}`, overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", background: "#F9F9F9", borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 16 }}>{prov.label.split(" ")[0]}</span>
              <span style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{prov.label.split(" ").slice(1).join(" ")}</span>
              <span style={{ fontSize: 11, color: T.textSoft, marginLeft: "auto" }}>
                {provKeys.length} key{provKeys.length !== 1 ? "s" : ""} · {provKeys.filter(k => k.enabled).length} enabled
              </span>
            </div>
            {provKeys.length === 0 ? (
              <div style={{ padding: "12px 14px", fontSize: 11, color: T.textSoft }}>No keys configured. Click "+ Add Key" to add one.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column" }}>
                {provKeys.map(k => {
                  const tr = testResults[k.key_id]
                  const ts = tr || { status: k.test_status, detail: k.test_detail }
                  const tsColor = testStatusColors[ts.status] || testStatusColors.untested
                  return (
                    <div key={k.key_id} style={{
                      padding: "10px 14px", borderBottom: `1px solid ${T.border}`,
                      display: "flex", alignItems: "center", gap: 10,
                      opacity: k.enabled ? 1 : 0.5,
                      background: k.is_default ? "#F0F7FF" : "transparent",
                    }}>
                      {/* Name + key mask */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{k.name}</span>
                          {k.is_default && <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: "#3478F6", color: "#fff", fontWeight: 600 }}>DEFAULT</span>}
                          {!k.enabled && <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: "#F2F2F7", color: "#888", fontWeight: 600 }}>DISABLED</span>}
                        </div>
                        <div style={{ fontSize: 10, color: T.textSoft, fontFamily: "monospace" }}>{k.key_masked}</div>
                      </div>
                      {/* Test status */}
                      <div style={{ minWidth: 100, textAlign: "center" }}>
                        <span style={{
                          fontSize: 10, padding: "2px 6px", borderRadius: 4,
                          background: tsColor.bg, color: tsColor.text, fontWeight: 600,
                        }}>
                          {ts.status === "ok" ? "✓ Active" : ts.status === "rate_limited" ? "⚠ Rate Limited" : ts.status === "invalid" ? "✗ Invalid" : ts.status === "error" ? "✗ Error" : "? Untested"}
                        </span>
                        {ts.detail && <div style={{ fontSize: 9, color: T.textSoft, marginTop: 2 }}>{ts.detail.slice(0, 60)}</div>}
                        {tr?.rate_limit_info?.requests_remaining && (
                          <div style={{ fontSize: 9, color: T.text, marginTop: 2, fontWeight: 600 }}>
                            {tr.rate_limit_info.requests_remaining}/{tr.rate_limit_info.requests_limit} req
                            {tr.rate_limit_info.tokens_remaining ? ` · ${Number(tr.rate_limit_info.tokens_remaining).toLocaleString()} tok` : ""}
                          </div>
                        )}
                      </div>
                      {/* Actions */}
                      <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                        <button onClick={() => handleTest(k.key_id)} disabled={testingId === k.key_id}
                          style={{ ...smallBtn, opacity: testingId === k.key_id ? 0.5 : 1 }}>
                          {testingId === k.key_id ? "…" : "Test"}
                        </button>
                        {!k.is_default && k.enabled && (
                          <button onClick={() => handleSetDefault(k.key_id)} style={{ ...smallBtn, color: "#3478F6", borderColor: "#3478F640" }}>
                            Set Default
                          </button>
                        )}
                        <button onClick={() => handleToggle(k.key_id, k.enabled, k.provider, k.name)} style={{ ...smallBtn, color: k.enabled ? "#CC3300" : T.teal }}>
                          {k.enabled ? "Disable" : "Enable"}
                        </button>
                        <button onClick={() => handleDelete(k.key_id, k.name)} style={{ ...smallBtn, color: "#CC3300" }}>✗</button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      <div style={{ padding: 12, background: "#F9F9F9", borderRadius: 10, fontSize: 11, color: T.textSoft, lineHeight: 1.7 }}>
        <strong style={{ color: T.text }}>How multi-key works:</strong><br />
        • Add multiple API keys per provider (e.g. 5 Gemini keys, 3 Groq keys)<br />
        • The <strong>default</strong> key is used for generation. Switch defaults when rate limited.<br />
        • <strong>Test</strong> checks if the key is active and shows remaining requests/tokens.<br />
        • Duplicate keys (same key added twice) are automatically flagged and rejected.
      </div>
    </div>
  )
}

// ── Custom Models Manager ──────────────────────────────────────────────────────
function CustomModelsManager({ onModelsChanged }) {
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState("")
  const [modelId, setModelId] = useState("")
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState("")

  const fetchModels = useCallback(async () => {
    try {
      const data = await api.get("/api/ai/models/custom")
      setModels(data || [])
    } catch { setModels([]) }
    setLoading(false)
  }, [])

  useEffect(() => { fetchModels() }, [fetchModels])

  const handleAdd = async () => {
    if (!name.trim() || !modelId.trim()) { setError("Name and Model ID are required"); return }
    setAdding(true); setError("")
    try {
      const res = await api.post("/api/ai/models/custom", { name: name.trim(), model_id: modelId.trim() })
      if (res?.ok) {
        setName(""); setModelId("")
        await fetchModels()
        if (onModelsChanged) onModelsChanged()
      } else {
        setError(res?.error || "Failed to add model")
      }
    } catch (e) { setError(e.message || "Failed to add model") }
    setAdding(false)
  }

  const handleDelete = async (id) => {
    if (!confirm("Delete this custom model?")) return
    try {
      await api.delete(`/api/ai/models/custom/${id}`)
      await fetchModels()
      if (onModelsChanged) onModelsChanged()
    } catch (e) { alert(e.message) }
  }

  return (
    <div style={{ background: "#fff", borderRadius: 12, border: `1px solid ${T.border}`, padding: 16, marginBottom: 16 }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 12 }}>🔧 Custom AI Models</div>
      <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 12 }}>
        Add custom OpenRouter models. They'll appear in the routing dropdowns above.
      </div>

      {/* Add form */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div style={{ flex: "1 1 180px" }}>
          <label style={{ fontSize: 11, color: T.textSoft, display: "block", marginBottom: 2 }}>Display Name</label>
          <input
            value={name} onChange={e => setName(e.target.value)}
            placeholder="e.g. My GPT-4o"
            style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12 }}
          />
        </div>
        <div style={{ flex: "1 1 260px" }}>
          <label style={{ fontSize: 11, color: T.textSoft, display: "block", marginBottom: 2 }}>OpenRouter Model ID</label>
          <input
            value={modelId} onChange={e => setModelId(e.target.value)}
            placeholder="e.g. openai/gpt-4o or anthropic/claude-3-opus"
            style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12 }}
          />
        </div>
        <Btn variant="primary" onClick={handleAdd} disabled={adding} style={{ height: 32 }}>
          {adding ? "Adding…" : "+ Add Model"}
        </Btn>
      </div>
      {error && <div style={{ fontSize: 11, color: "#cc3300", marginBottom: 8 }}>{error}</div>}

      {/* Models list */}
      {loading ? (
        <div style={{ fontSize: 12, color: T.textSoft }}>Loading…</div>
      ) : models.length === 0 ? (
        <div style={{ fontSize: 12, color: T.textSoft, fontStyle: "italic" }}>No custom models added yet.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {models.map(m => (
            <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 10px", background: "#F9F9FB", borderRadius: 8, fontSize: 12 }}>
              <span style={{ fontWeight: 600, color: T.text, flex: "0 0 auto" }}>🔧 {m.name}</span>
              <span style={{ color: T.textSoft, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.model_id}</span>
              <span style={{ fontSize: 10, color: T.textSoft, fontFamily: "monospace" }}>{m.provider_id}</span>
              <button onClick={() => handleDelete(m.id)} style={{ background: "none", border: "none", cursor: "pointer", color: "#cc3300", fontSize: 14, padding: "2px 6px" }} title="Delete model">✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════════
// MAIN AI HUB COMPONENT
// ════════════════════════════════════════════════════════════════════════════════
export default function AIHub() {
  const qclient = useQueryClient()
  const [section, setSection] = useState("status")     // status | routing | prompts | logs
  const [routing, setRouting] = useState(null)
  const [routingDirty, setRoutingDirty] = useState(false)
  const [savingRouting, setSavingRouting] = useState(false)
  const [templateName, setTemplateName] = useState("")
  const [savingTemplate, setSavingTemplate] = useState(false)

  // ── Queries ──────────────────────────────────────────────────────────────
  const { data: dashboard, isLoading, refetch } = useQuery({
    queryKey: ["ai-dashboard"],
    queryFn: () => api.get("/api/ai/dashboard"),
    refetchInterval: 30000,  // refresh every 30s
    staleTime: 10000,
  })

  const toggleProviderMutation = useMutation({
    mutationFn: ({ provider, disabled }) => api.post("/api/ai/providers/toggle", { provider, disabled }),
    onSuccess: () => refetch(),
  })

  const { data: orUsage, refetch: refetchOrUsage } = useQuery({
    queryKey: ["or-usage"],
    queryFn: () => api.get("/api/ai/openrouter-usage"),
    refetchInterval: 60000,
    staleTime: 30000,
    enabled: true,
  })

  const { data: savedRouting } = useQuery({
    queryKey: ["ai-routing"],
    queryFn: () => api.get("/api/ai/routing"),
  })

  const { data: routingTemplatesData } = useQuery({
    queryKey: ["ai-routing-templates"],
    queryFn: () => api.get("/api/ai/routing/templates"),
  })

  // Initialize routing from saved or dashboard defaults
  useEffect(() => {
    if (routing) return
    if (savedRouting) { setRouting(savedRouting); return }
    if (dashboard?.routing) setRouting(dashboard.routing)
  }, [savedRouting, dashboard]) // eslint-disable-line

  const handleRoutingChange = (r) => { setRouting(r); setRoutingDirty(true) }

  const saveRouting = async () => {
    setSavingRouting(true)
    try {
      await api.post("/api/ai/routing", routing)
      setRoutingDirty(false)
      qclient.invalidateQueries(["ai-routing"])
    } catch (e) { alert(e.message) }
    setSavingRouting(false)
  }

  const saveAndPropagateRouting = async () => {
    setSavingRouting(true)
    try {
      const result = await api.post("/api/ai/routing/propagate", routing)
      setRoutingDirty(false)
      qclient.invalidateQueries(["ai-routing"])
      if (result?.propagated_to > 0) {
        alert(`✅ Routing saved and pushed to ${result.propagated_to} active pipeline(s).`)
      }
    } catch (e) { alert(e.message) }
    setSavingRouting(false)
  }

  const applySystemTemplate = (tpl) => {
    setRouting(expandToLegacyRouting(tpl.steps))
    setRoutingDirty(true)
  }

  const copySystemTemplate = async (tpl) => {
    const name = tpl.name.replace(/^[^\w]*\s*/, "") + " (Copy)"
    const routing = expandToLegacyRouting(tpl.steps)
    try {
      await api.post("/api/ai/routing/templates", { name, routing })
      qclient.invalidateQueries(["ai-routing-templates"])
    } catch (e) { alert(e.message) }
  }

  const routingTemplates = routingTemplatesData?.templates || []

  const saveCurrentAsTemplate = async () => {
    const name = (templateName || "").trim()
    if (!name) {
      alert("Template name is required")
      return
    }
    if (!routing) {
      alert("Routing is not ready yet")
      return
    }

    setSavingTemplate(true)
    try {
      await api.post("/api/ai/routing/templates", { name, routing })
      setTemplateName("")
      qclient.invalidateQueries(["ai-routing-templates"])
    } catch (e) {
      alert(e.message)
    }
    setSavingTemplate(false)
  }

  const applyCustomTemplate = (tpl) => {
    if (!tpl?.routing) return
    setRouting(tpl.routing)
    setRoutingDirty(true)
  }

  const deleteCustomTemplate = async (tpl) => {
    if (!tpl?.id) return
    if (!confirm(`Delete template "${tpl.name}"?`)) return
    try {
      await api.delete(`/api/ai/routing/templates/${tpl.id}`)
      qclient.invalidateQueries(["ai-routing-templates"])
    } catch (e) {
      alert(e.message)
    }
  }

  const providers = dashboard?.providers || {}
  const sys = dashboard?.system || {}
  
  // Build dynamic provider groups from available providers
  const dynamicProviderGroups = buildProviderGroups(providers)

  // Count available / issues
  const availCount = Object.values(providers).filter(p => p.available).length
  const rlCount = Object.values(providers).filter(p => p.rate_limited).length

  const sectionBtn = (key, label, icon) => (
    <button onClick={() => setSection(key)} style={{
      padding: "7px 14px", borderRadius: 8, border: `1px solid ${section === key ? T.purple : T.border}`,
      background: section === key ? T.purpleLight : "#fff",
      color: section === key ? T.purple : T.text,
      fontSize: 12, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 5,
    }}>
      <span>{icon}</span>{label}
    </button>
  )

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "0 20px 40px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <div style={{ fontSize: 17, fontWeight: 700, color: T.text }}>AI Hub</div>
        <div style={{ display: "flex", gap: 3, fontSize: 11 }}>
          <StatusBadge status={sys.ram_status || "unknown"} label={`RAM ${sys.ram_used_pct || 0}%`} />
          <StatusBadge status={availCount >= 3 ? "ok" : availCount >= 1 ? "warning" : "error"} label={`${availCount}/5 providers`} />
          {rlCount > 0 && <StatusBadge status="rate_limited" label={`${rlCount} rate limited`} />}
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          <button onClick={() => refetch()} style={{ ...smallBtn, fontSize: 11 }}>🔄 Refresh</button>
          <button onClick={async () => {
            try {
              await api.post("/api/ai/providers/clear-status-cache", {})
              await refetch()
            } catch (e) { console.warn("Cache clear failed", e) }
          }} style={{ ...smallBtn, fontSize: 11, background: "#FFF0EB", borderColor: "#CC330040", color: "#CC3300" }}
            title="Force live re-test of all keys (clears 5-min cache)">
            🔴 Force Re-check
          </button>
        </div>
      </div>

      {/* System Memory Bar */}
      {sys.ram_total_mb > 0 && (
        <div style={{ marginBottom: 16, padding: 14, background: "#fff", borderRadius: 10, border: `1px solid ${T.border}` }}>
          <MemBar pct={sys.ram_used_pct} label={`System Memory — ${sys.ram_available_mb}MB free of ${sys.ram_total_mb}MB`} />
        </div>
      )}

      {/* Sub-nav */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {sectionBtn("status", "Provider Status", "📡")}
        {sectionBtn("keys", "API Keys", "🔑")}
        {sectionBtn("routing", "AI Routing", "🔀")}
        {sectionBtn("logs", "Logs & Usage", "📊")}
        {sectionBtn("ratelimits", "Rate Limits", "⏱")}
      </div>

      {/* ── SECTION: Provider Status ──────────────────────────────────────── */}
      {section === "status" && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
            {Object.entries(providers).filter(([id, p]) => !id.startsWith("or_") && !p._hidden_from_cards).map(([id, p]) => (
              <ProviderCard key={id} id={id} p={p}
                onToggle={() => toggleProviderMutation.mutate({ provider: id, disabled: !p.disabled })} />
            ))}
          </div>
          {/* OpenRouter Models Panel */}
          {providers.openrouter?.key_configured && (
            <div style={{ marginTop: 16, background: "#fff", borderRadius: 12, border: `1px solid ${T.border}`, overflow: "hidden" }}>
              {/* OR Panel Header with usage bar */}
              <div style={{ padding: "14px 16px", borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 2 }}>🌐 OpenRouter Models</div>
                  <div style={{ fontSize: 11, color: T.textSoft }}>Enable/disable models and set as primary/secondary in AI Routing tab.</div>
                </div>
                <button onClick={() => refetchOrUsage()} style={{ ...smallBtn, fontSize: 11, padding: "4px 10px" }}>🔄 Refresh stats</button>
              </div>

              {/* Usage Stats Bar */}
              {orUsage && !orUsage.error && (
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${T.border}`, background: "#FAFBFF" }}>
                  <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
                    {/* Token limit bar (only if limit is set) */}
                    {orUsage.tokens_limit && orUsage.tokens_limit > 0 && (
                      <div style={{ minWidth: 200, flex: 2 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 11 }}>
                          <span style={{ color: T.textSoft, fontWeight: 600 }}>Tokens Remaining</span>
                          <span style={{ fontWeight: 700, color: T.text }}>{(orUsage.tokens_remaining || 0).toLocaleString()} / {orUsage.tokens_limit.toLocaleString()}</span>
                        </div>
                        <div style={{ height: 6, background: "#E5E5EA", borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ height: "100%", borderRadius: 3,
                            background: (orUsage.tokens_remaining / orUsage.tokens_limit) > 0.3 ? "#34C759" : "#FF9500",
                            width: `${Math.min(100, Math.round((orUsage.tokens_remaining / orUsage.tokens_limit) * 100))}%` }} />
                        </div>
                        <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3 }}>
                          {Math.round((orUsage.tokens_remaining / orUsage.tokens_limit) * 100)}% remaining
                        </div>
                      </div>
                    )}
                    {/* Credit usage (when no hard token limit) */}
                    {!orUsage.tokens_limit && orUsage.tokens_used !== undefined && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <div style={{ fontSize: 11, color: T.textSoft, fontWeight: 600 }}>Credits Used</div>
                        <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>${(orUsage.tokens_used || 0).toFixed(4)}</div>
                        <div style={{ fontSize: 10, color: T.teal }}>No credit limit set (unlimited)</div>
                      </div>
                    )}
                    {/* Rate limit */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <div style={{ fontSize: 11, color: T.textSoft, fontWeight: 600 }}>Rate Limit</div>
                      <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>
                        {orUsage.rate_limit?.requests_per_interval > 0
                          ? `${orUsage.rate_limit.requests_per_interval} req / ${orUsage.rate_limit.interval}`
                          : "Per-model limits apply"}
                      </div>
                      <div style={{ fontSize: 10, color: T.textSoft }}>
                        {orUsage.is_free_tier ? "Free tier key" : "Paid tier key"}
                        {orUsage.label ? ` · ${orUsage.label.slice(0, 20)}…` : ""}
                      </div>
                    </div>
                  </div>
                </div>
              )}
              {orUsage?.error && (
                <div style={{ padding: "10px 16px", borderBottom: `1px solid ${T.border}`, fontSize: 11, color: T.red }}>
                  ⚠ Could not fetch usage stats: {orUsage.error}
                </div>
              )}

              {/* Model Cards Grid */}
              <div style={{ padding: 16 }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
                  {Object.entries(providers).filter(([id, p]) => p.is_openrouter_model).map(([id, p]) => {
                    const isDisabled = p.disabled
                    return (
                      <div key={id} style={{
                        borderRadius: 10, overflow: "hidden",
                        border: `1px solid ${isDisabled ? "#E5E5EA" : p.tier === "primary" ? "#c0d8f0" : "#e8e8ea"}`,
                        background: isDisabled ? "#F8F8FA" : p.tier === "primary" ? "#f0f7ff" : "#FAFAFA",
                        opacity: isDisabled ? 0.65 : 1,
                        transition: "all 0.2s",
                      }}>
                        <div style={{ padding: "10px 12px" }}>
                          {/* Model header row */}
                          <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 6 }}>
                            <span style={{ fontSize: 11, fontWeight: 700, marginTop: 1,
                              color: isDisabled ? "#C7C7CC" : p.available ? "#34C759" : "#8E8E93" }}>
                              {isDisabled ? "○" : p.available ? "●" : "○"}
                            </span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontSize: 13, fontWeight: 700, color: isDisabled ? T.textSoft : T.text, lineHeight: 1.2 }}>
                                {p.name?.replace("OR: ", "")}
                              </div>
                              <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{p.model}</div>
                            </div>
                            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 4, flexShrink: 0,
                              background: p.tier === "primary" ? "#E8F0FE" : "#F2F2F7",
                              color: p.tier === "primary" ? "#1a73e8" : "#8E8E93", fontWeight: 700 }}>
                              {p.tier === "primary" ? "★ Primary" : "Secondary"}
                            </span>
                          </div>
                          {/* Cost row */}
                          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                            <span style={{ fontSize: 11, color: p.cost === "Free" ? T.teal : T.amber, fontWeight: 600 }}>
                              {p.cost === "Free" ? "🆓 Free" : `💰 ${p.cost}`}
                            </span>
                          </div>
                          {/* Toggle button */}
                          <button
                            onClick={() => toggleProviderMutation.mutate({ provider: id, disabled: !isDisabled })}
                            style={{
                              width: "100%", padding: "5px 0", borderRadius: 6, fontSize: 11, fontWeight: 600,
                              cursor: "pointer", border: `1px solid ${isDisabled ? "#34C759" : "#FF3B30"}`,
                              background: isDisabled ? "#E8F8EC" : "#FFF0F0",
                              color: isDisabled ? "#1B7A2E" : "#CC2200",
                            }}>
                            {isDisabled ? "✓ Enable" : "⊘ Disable"}
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── SECTION: API Keys ─────────────────────────────────────────────── */}
      {section === "keys" && <APIKeysManager />}

      {/* ── SECTION: Routing ──────────────────────────────────────────────── */}
      {section === "routing" && routing && (
        <div>
          <CustomModelsManager onModelsChanged={() => { refetch() }} />

          {/* System Templates */}
          <div style={{ background: "#fff", borderRadius: 12, border: `1px solid ${T.border}`, padding: 14, marginBottom: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 4 }}>🎯 System Templates</div>
            <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 10 }}>
              Curated routing presets optimized for different goals. Apply directly or copy to customize.
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {SYSTEM_TEMPLATES.map(tpl => (
                <div key={tpl.id} style={{
                  display: "flex", flexDirection: "column", gap: 6,
                  borderRadius: 10, padding: "10px 14px",
                  border: `1px solid ${tpl.id === DEFAULT_TEMPLATE_ID ? "#6366f140" : "#d1d5db"}`,
                  background: tpl.id === DEFAULT_TEMPLATE_ID ? "#eef2ff" : "#f9fafb",
                  minWidth: 200, flex: "1 1 200px", maxWidth: 280,
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.text }}>{tpl.name}</div>
                  <div style={{ fontSize: 10, color: T.textSoft, lineHeight: 1.4 }}>{tpl.description}</div>
                  <div style={{ display: "flex", gap: 4, marginTop: "auto" }}>
                    <button onClick={() => applySystemTemplate(tpl)} style={{
                      border: "1px solid #93c5fd", background: "#eff6ff", color: "#1d4ed8",
                      borderRadius: 6, fontSize: 10, fontWeight: 700, cursor: "pointer", padding: "3px 10px",
                    }}>Apply</button>
                    <button onClick={() => copySystemTemplate(tpl)} title="Copy as custom template" style={{
                      border: "1px solid #d1d5db", background: "#fff", color: T.textSoft,
                      borderRadius: 6, fontSize: 10, fontWeight: 600, cursor: "pointer", padding: "3px 8px",
                    }}>📋 Copy</button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ background: "#fff", borderRadius: 12, border: `1px solid ${T.border}`, padding: 14, marginBottom: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 4 }}>🧩 Custom Routing Templates</div>
            <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 10 }}>
              Save your current routing as a reusable template and apply it anytime like Smart Balance or Premium.
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
              <input
                value={templateName}
                onChange={e => setTemplateName(e.target.value)}
                placeholder="Template name (e.g. My SEO Mix)"
                style={{
                  minWidth: 260,
                  flex: "1 1 280px",
                  padding: "7px 10px",
                  borderRadius: 8,
                  border: `1px solid ${T.border}`,
                  fontSize: 12,
                  background: "#fff",
                }}
              />
              <Btn variant="primary" onClick={saveCurrentAsTemplate} disabled={savingTemplate || !templateName.trim()}>
                {savingTemplate ? "Saving…" : "+ Save Current as Template"}
              </Btn>
            </div>

            {routingTemplates.length === 0 ? (
              <div style={{ fontSize: 11, color: T.textSoft, fontStyle: "italic" }}>No custom templates yet.</div>
            ) : (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {routingTemplates.map(tpl => (
                  <div key={tpl.id} style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    borderRadius: 20,
                    padding: "4px 8px 4px 10px",
                    border: "1px solid #d1d5db",
                    background: "#f9fafb",
                  }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: T.text }}>{tpl.name}</span>
                    <button
                      onClick={() => applyCustomTemplate(tpl)}
                      style={{
                        border: "1px solid #93c5fd",
                        background: "#eff6ff",
                        color: "#1d4ed8",
                        borderRadius: 12,
                        fontSize: 10,
                        fontWeight: 700,
                        cursor: "pointer",
                        padding: "2px 8px",
                      }}
                    >
                      Apply
                    </button>
                    <button
                      onClick={() => deleteCustomTemplate(tpl)}
                      title="Delete template"
                      style={{
                        border: "none",
                        background: "transparent",
                        color: "#b91c1c",
                        fontSize: 12,
                        cursor: "pointer",
                        padding: "0 4px",
                        lineHeight: 1,
                      }}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ background: "#fff", borderRadius: 12, border: `1px solid ${T.border}`, overflow: "hidden" }}>
            <RoutingTable routing={routing} onChange={handleRoutingChange} providerGroups={dynamicProviderGroups} />
          </div>

          {/* Save buttons */}
          <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center", flexWrap: "wrap" }}>
            <Btn variant="primary" onClick={saveRouting} disabled={!routingDirty || savingRouting}>
              {savingRouting ? "Saving…" : "💾 Save Routing"}
            </Btn>
            <Btn variant="success" onClick={saveAndPropagateRouting} disabled={savingRouting} title="Save routing and immediately apply it to any currently running pipelines">
              {savingRouting ? "Propagating…" : "📡 Save & Propagate"}
            </Btn>
            {routingDirty && <span style={{ fontSize: 11, color: T.amber, fontWeight: 600 }}>Unsaved changes</span>}
            {!routingDirty && <span style={{ fontSize: 11, color: T.teal }}>✓ Saved</span>}
          </div>

          {/* Legend */}
          <div style={{ marginTop: 14, padding: 12, background: "#F9F9F9", borderRadius: 10, fontSize: 11, color: T.textSoft, lineHeight: 1.7 }}>
            <strong style={{ color: T.text }}>How it works:</strong> Pick a tier to set all steps at once. Each tier has 3 models — if the first fails, it tries the next.<br />
            <strong>"Save Routing"</strong> applies to new articles. <strong>"Save &amp; Propagate"</strong> also pushes changes to running pipelines.
          </div>
        </div>
      )}

      {/* ── SECTION: Logs & Usage ─────────────────────────────────────────── */}
      {section === "logs" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 8 }}>📊 Usage (Last 7 Days)</div>
            <UsageStats stats={dashboard?.usage_stats} />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 8 }}>📋 Recent AI Calls</div>
            <div style={{ background: "#fff", borderRadius: 12, border: `1px solid ${T.border}`, overflow: "hidden" }}>
              <LogTable logs={dashboard?.recent_logs} />
            </div>
          </div>
        </div>
      )}

      {section === "ratelimits" && (
        <div style={{ flex: 1, overflowY: "auto" }}>
          <RateLimitDashboard />
        </div>
      )}

      {isLoading && (
        <div style={{ textAlign: "center", padding: 40, color: T.textSoft, fontSize: 13 }}>
          Loading AI dashboard…
        </div>
      )}
    </div>
  )
}
