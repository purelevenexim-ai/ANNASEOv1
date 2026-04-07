import { useState, useEffect, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { T, api, Btn } from "./App"
import RateLimitDashboard from "./aihub/RateLimitDashboard"

// ── Provider Icons ─────────────────────────────────────────────────────────────
const PROVIDER_ICONS = { ollama: "🦙", groq: "⚡", gemini: "💎", gemini_free: "💎", gemini_paid: "💎", chatgpt: "🤖", openai_paid: "🤖", claude: "🧠", anthropic: "🧠", anthropic_paid: "🧠", openrouter: "🌐", or_qwen: "🌐", or_qwen_next: "🌐", or_deepseek: "🌐", or_gemini_flash: "🌐", or_gemini_lite: "🌐", or_glm: "🌐", or_gpt4o: "🌐", or_claude: "🌐", or_llama: "🌐", or_qwen_coder: "🌐", or_deepseek_r1: "🌐" }
const PROVIDER_LABELS = { ollama: "Ollama", groq: "Groq", gemini: "Gemini", gemini_free: "Gemini", gemini_paid: "Gemini Paid", chatgpt: "ChatGPT", openai_paid: "ChatGPT", claude: "Claude", anthropic: "Claude", anthropic_paid: "Claude Pro", openrouter: "OpenRouter", or_qwen: "OR: Qwen 3.6+", or_qwen_next: "OR: Qwen3 Next 80B", or_deepseek: "OR: DeepSeek V3.2", or_gemini_flash: "OR: Gemini Flash", or_gemini_lite: "OR: Gemini Lite", or_glm: "OR: GLM 5 Turbo", or_gpt4o: "OR: GPT-4o", or_claude: "OR: Claude", or_llama: "OR: Llama 4", or_qwen_coder: "OR: Qwen Coder", or_deepseek_r1: "OR: DeepSeek R1", skip: "Skip" }

const STEPS = [
  { key: "research",     label: "Step 1: Research",     desc: "Topic analysis & crawling" },
  { key: "structure",    label: "Step 2: Structure",    desc: "Outline & headings" },
  { key: "verify",       label: "Step 3: Verify",       desc: "Structure validation" },
  { key: "links",        label: "Step 4: Links",        desc: "Internal link planning" },
  { key: "references",   label: "Step 5: References",   desc: "Wikipedia references" },
  { key: "draft",        label: "Step 6: Draft",        desc: "Write full article" },
  { key: "review",       label: "Step 7: Review",       desc: "AI quality review" },
  { key: "issues",       label: "Step 8: Issues",       desc: "53-rule checks" },
  { key: "redevelop",    label: "Step 9: Redevelop",    desc: "Rewrite & polish" },
  { key: "score",        label: "Step 10: Score",       desc: "Final quality scoring" },
  { key: "quality_loop", label: "Step 11: Quality",     desc: "Iterate to ≥75%" },
]

// Build dynamic provider groups from ALL providers (active + inactive)
function buildProviderGroups(providers = {}) {
  const local = []
  const cloud = []
  const orPrimary = []
  const orSecondary = []

  // Process ALL providers — including unconfigured, rate-limited, offline
  Object.entries(providers).forEach(([key, p]) => {
    // Status badge: ⚠ = rate limited, ○ = offline/no-key, nothing = ok/idle
    const badge = p.rate_limited ? " ⚠" : !p.available ? " ○" : ""

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
    groups.push({ label: "── OpenRouter ★ Primary ──", providers: orPrimary })
  }
  if (orSecondary.length > 0) {
    groups.push({ label: "── OpenRouter Secondary ──", providers: orSecondary })
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
  { label: "── OpenRouter ★ Primary ──", providers: [
    { value: "or_qwen",         label: "🌐 Qwen 3.6 Plus" },
    { value: "or_qwen_next",    label: "🌐 Qwen3 Next 80B" },
    { value: "or_deepseek",     label: "🌐 DeepSeek V3.2" },
    { value: "or_gemini_flash", label: "🌐 Gemini 2.5 Flash" },
    { value: "or_gemini_lite",  label: "🌐 Gemini 2.0 Flash Lite" },
    { value: "or_glm",          label: "🌐 GLM 5 Turbo" },
  ]},
  { label: "── OpenRouter Secondary ──", providers: [
    { value: "or_gpt4o",        label: "🌐 GPT-4o" },
    { value: "or_claude",       label: "🌐 Claude Sonnet 4.5" },
    { value: "or_llama",        label: "🌐 Llama 4 Maverick" },
    { value: "or_qwen_coder",   label: "🌐 Qwen3 Coder 480B" },
    { value: "or_deepseek_r1",  label: "🌐 DeepSeek R1" },
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

// ── Routing Table ──────────────────────────────────────────────────────────────
const thStyle = { padding: "8px 10px", textAlign: "left", fontSize: 11, fontWeight: 600, borderBottom: "1px solid #E5E5EA" }
const tdStyle = { padding: "8px 10px", borderBottom: "1px solid #E5E5EA", verticalAlign: "top" }

function RoutingTable({ routing, onChange, providerGroups }) {
  const groups = providerGroups || PROVIDER_GROUPS
  
  const handleChange = (stepKey, slotKey, value) => {
    const updated = { ...routing, [stepKey]: { ...routing[stepKey], [slotKey]: value } }
    onChange(updated)
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ background: "#F9F9F9" }}>
            <th style={{ ...thStyle, width: 180 }}>Pipeline Step</th>
            <th style={thStyle}>1st Priority</th>
            <th style={thStyle}>2nd Priority</th>
            <th style={thStyle}>3rd Priority</th>
          </tr>
        </thead>
        <tbody>
          {STEPS.map(s => (
            <tr key={s.key}>
              <td style={tdStyle}>
                <div style={{ fontWeight: 600, color: T.text }}>{s.label}</div>
                <div style={{ fontSize: 10, color: T.textSoft }}>{s.desc}</div>
              </td>
              {["first", "second", "third"].map(slot => (
                <td key={slot} style={tdStyle}>
                  <select value={routing[s.key]?.[slot] || "skip"} onChange={e => handleChange(s.key, slot, e.target.value)}
                    style={{ padding: "5px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12, background: "#fff", cursor: "pointer", width: "100%" }}>
                    {groups.map(g => (
                      <optgroup key={g.label} label={g.label}>
                        {g.providers.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                      </optgroup>
                    ))}
                  </select>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Routing Presets ────────────────────────────────────────────────────────────
const _groq_ollama_routing = {
  research:     { first: "groq",        second: "gemini_paid", third: "or_qwen" },
  structure:    { first: "groq",        second: "gemini_paid", third: "or_qwen" },
  verify:       { first: "groq",        second: "gemini_paid", third: "skip" },
  links:        { first: "groq",        second: "gemini_paid", third: "or_qwen" },
  references:   { first: "groq",        second: "gemini_paid", third: "or_qwen" },
  draft:        { first: "gemini_paid", second: "groq",        third: "or_qwen" },
  review:       { first: "groq",        second: "gemini_paid", third: "or_qwen" },
  issues:       { first: "groq",        second: "gemini_paid", third: "skip" },
  redevelop:    { first: "gemini_paid", second: "groq",        third: "or_qwen" },
  score:        { first: "groq",        second: "gemini_paid", third: "skip" },
  quality_loop: { first: "gemini_paid", second: "groq",        third: "or_qwen" },
}

const PRESETS = {
  groq_ollama: {
    label: "⚡💎 Groq + Gemini (Default)",
    desc: "Groq for simple tasks, Gemini Paid for heavy writing, OR Qwen fallback",
    routing: _groq_ollama_routing,
  },
  speed: {
    label: "⚡ Max Speed",
    desc: "Groq primary for everything, Gemini fallback",
    routing: {
      research:     { first: "groq", second: "gemini_paid", third: "skip" },
      structure:    { first: "groq", second: "gemini_paid", third: "skip" },
      verify:       { first: "groq", second: "gemini_paid", third: "skip" },
      links:        { first: "groq", second: "gemini_paid", third: "skip" },
      references:   { first: "groq", second: "gemini_paid", third: "skip" },
      draft:        { first: "groq", second: "gemini_paid", third: "or_qwen" },
      review:       { first: "groq", second: "gemini_paid", third: "skip" },
      issues:       { first: "groq", second: "gemini_paid", third: "skip" },
      redevelop:    { first: "groq", second: "gemini_paid", third: "or_qwen" },
      score:        { first: "groq", second: "gemini_paid", third: "skip" },
      quality_loop: { first: "groq", second: "gemini_paid", third: "or_qwen" },
    },
  },
  ollama_remote: {
    label: "🦙 Ollama Remote",
    desc: "Ollama remote primary, Groq fallback",
    routing: {
      research:     { first: "ollama", second: "groq",   third: "skip" },
      structure:    { first: "ollama", second: "groq",   third: "skip" },
      verify:       { first: "ollama", second: "groq",   third: "skip" },
      links:        { first: "ollama", second: "groq",   third: "skip" },
      references:   { first: "ollama", second: "groq",   third: "skip" },
      draft:        { first: "ollama", second: "groq",   third: "gemini_paid" },
      review:       { first: "ollama", second: "groq",   third: "skip" },
      issues:       { first: "ollama", second: "groq",   third: "skip" },
      redevelop:    { first: "ollama", second: "groq",   third: "gemini_paid" },
      score:        { first: "ollama", second: "groq",   third: "skip" },
      quality_loop: { first: "ollama", second: "groq",   third: "gemini_paid" },
    },
  },
  quality: {
    label: "🏆 Max Quality",
    desc: "Gemini + Groq + Ollama — all providers active",
    routing: {
      research:     { first: "groq",        second: "gemini_free", third: "ollama" },
      structure:    { first: "groq",        second: "gemini_free", third: "ollama" },
      verify:       { first: "gemini_free", second: "groq",        third: "skip" },
      links:        { first: "groq",        second: "gemini_free", third: "ollama" },
      references:   { first: "ollama",      second: "groq",        third: "skip" },
      draft:        { first: "ollama",      second: "groq",        third: "gemini_free" },
      review:       { first: "groq",        second: "gemini_free", third: "ollama" },
      issues:       { first: "groq",        second: "gemini_free", third: "skip" },
      redevelop:    { first: "ollama",      second: "groq",        third: "gemini_free" },
      score:        { first: "groq",        second: "gemini_free", third: "skip" },
      quality_loop: { first: "ollama",      second: "groq",        third: "gemini_free" },
    },
  },
  or_free: {
    label: "🆓 OR Free Models",
    desc: "Free models only: Qwen 3.6 (free) + Groq + Qwen Next (free)",
    routing: {
      research:     { first: "groq",     second: "or_qwen",       third: "or_qwen_next" },
      structure:    { first: "groq",     second: "or_qwen",       third: "or_qwen_next" },
      verify:       { first: "groq",     second: "or_qwen",       third: "skip" },
      links:        { first: "groq",     second: "or_qwen",       third: "skip" },
      references:   { first: "groq",     second: "or_qwen",       third: "skip" },
      draft:        { first: "or_qwen",  second: "or_qwen_next",  third: "groq" },
      review:       { first: "groq",     second: "or_qwen",       third: "skip" },
      issues:       { first: "groq",     second: "or_qwen",       third: "skip" },
      redevelop:    { first: "or_qwen",  second: "or_qwen_next",  third: "groq" },
      score:        { first: "groq",     second: "or_qwen",       third: "skip" },
      quality_loop: { first: "or_qwen",  second: "groq",          third: "or_qwen_next" },
    },
  },
  or_balanced: {
    label: "⚖️ OR Balanced",
    desc: "DeepSeek V3.2 + Gemini Lite + Groq — great cost/quality ratio",
    routing: {
      research:     { first: "or_deepseek",     second: "or_gemini_lite",  third: "groq" },
      structure:    { first: "or_deepseek",     second: "or_gemini_lite",  third: "groq" },
      verify:       { first: "groq",            second: "or_gemini_lite",  third: "skip" },
      links:        { first: "groq",            second: "or_deepseek",     third: "skip" },
      references:   { first: "groq",            second: "or_deepseek",     third: "skip" },
      draft:        { first: "or_deepseek",     second: "or_gemini_flash", third: "groq" },
      review:       { first: "or_gemini_lite",  second: "groq",            third: "skip" },
      issues:       { first: "groq",            second: "or_deepseek",     third: "skip" },
      redevelop:    { first: "or_deepseek",     second: "or_gemini_flash", third: "groq" },
      score:        { first: "groq",            second: "or_gemini_lite",  third: "skip" },
      quality_loop: { first: "or_deepseek",     second: "or_gemini_flash", third: "groq" },
    },
  },
  or_quality: {
    label: "🌐 OR Quality",
    desc: "Gemini Flash + GPT-4o + DeepSeek — premium OpenRouter output",
    routing: {
      research:     { first: "or_gemini_flash", second: "or_deepseek", third: "groq" },
      structure:    { first: "or_gemini_flash", second: "or_deepseek", third: "groq" },
      verify:       { first: "or_gemini_flash", second: "or_deepseek", third: "groq" },
      links:        { first: "groq",            second: "or_deepseek", third: "skip" },
      references:   { first: "groq",            second: "or_deepseek", third: "skip" },
      draft:        { first: "or_gpt4o",        second: "or_gemini_flash", third: "or_deepseek" },
      review:       { first: "or_gemini_flash", second: "or_deepseek", third: "groq" },
      issues:       { first: "or_gemini_flash", second: "groq",        third: "skip" },
      redevelop:    { first: "or_gpt4o",        second: "or_gemini_flash", third: "or_deepseek" },
      score:        { first: "or_gemini_flash", second: "groq",        third: "skip" },
      quality_loop: { first: "or_gpt4o",        second: "or_gemini_flash", third: "or_deepseek" },
    },
  },
  groq_or: {
    label: "⚡🌐 Groq + OpenRouter",
    desc: "Groq for speed, OpenRouter free models as fallback",
    routing: {
      research:     { first: "groq", second: "or_qwen",      third: "or_deepseek" },
      structure:    { first: "groq", second: "or_qwen",      third: "or_deepseek" },
      verify:       { first: "groq", second: "or_qwen",      third: "skip" },
      links:        { first: "groq", second: "or_qwen",      third: "skip" },
      references:   { first: "groq", second: "or_qwen",      third: "skip" },
      draft:        { first: "groq", second: "or_deepseek",  third: "or_gemini_flash" },
      review:       { first: "groq", second: "or_deepseek",  third: "skip" },
      issues:       { first: "groq", second: "or_qwen",      third: "skip" },
      redevelop:    { first: "groq", second: "or_deepseek",  third: "or_gemini_flash" },
      score:        { first: "groq", second: "or_qwen",      third: "skip" },
      quality_loop: { first: "groq", second: "or_deepseek",  third: "or_gemini_flash" },
    },
  },
  or_smart: {
    label: "🧠 OR Smart Mix",
    desc: "DeepSeek R1 reasoning + Gemini Flash + Qwen for intelligent pipeline",
    routing: {
      research:     { first: "or_qwen",        second: "or_deepseek_r1",  third: "groq" },
      structure:    { first: "or_deepseek_r1", second: "or_qwen",         third: "groq" },
      verify:       { first: "or_deepseek_r1", second: "groq",            third: "skip" },
      links:        { first: "groq",           second: "or_qwen",         third: "skip" },
      references:   { first: "groq",           second: "or_qwen",         third: "skip" },
      draft:        { first: "or_deepseek_r1", second: "or_gemini_flash", third: "or_deepseek" },
      review:       { first: "or_gemini_flash",second: "or_deepseek_r1",  third: "groq" },
      issues:       { first: "or_deepseek_r1", second: "groq",            third: "skip" },
      redevelop:    { first: "or_deepseek_r1", second: "or_gemini_flash", third: "or_deepseek" },
      score:        { first: "or_gemini_flash",second: "groq",            third: "skip" },
      quality_loop: { first: "or_deepseek_r1", second: "or_gemini_flash", third: "or_deepseek" },
    },
  },
}

// ── Button Styles ──────────────────────────────────────────────────────────────
const smallBtn = { padding: "3px 10px", borderRadius: 6, border: "1px solid #E5E5EA", background: "#fff", fontSize: 11, cursor: "pointer", fontWeight: 500 }

// ── Prompts Editor ─────────────────────────────────────────────────────────────
function PromptsEditor() {
  const { data: prompts, refetch } = useQuery({ queryKey: ["prompts"], queryFn: () => api.get("/api/prompts") })
  const [editing, setEditing] = useState(null)
  const [editValue, setEditValue] = useState("")
  const [saving, setSaving] = useState(false)

  const startEdit = (p) => { setEditing(p.key); setEditValue(p.content || p.default || "") }
  const cancel = () => { setEditing(null); setEditValue("") }
  const save = async () => {
    setSaving(true)
    try {
      await api.post(`/api/prompts/${editing}`, { content: editValue })
      refetch(); setEditing(null); setEditValue("")
    } catch (e) { alert(e.message) }
    setSaving(false)
  }
  const reset = async (key) => {
    if (!confirm("Reset to default?")) return
    try { await api.delete(`/api/prompts/${key}`); refetch() } catch (e) { alert(e.message) }
  }

  const items = prompts?.prompts || []
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {items.length === 0 && <div style={{ fontSize: 12, color: T.textSoft }}>Loading prompts…</div>}
      {items.map(p => (
        <div key={p.key} style={{ background: "#fff", borderRadius: 10, border: `1px solid ${T.border}`, overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", display: "flex", alignItems: "center", gap: 8, borderBottom: editing === p.key ? `1px solid ${T.border}` : "none" }}>
            <span style={{ fontSize: 14 }}>{p.key.includes("structure") ? "📐" : p.key.includes("draft") || p.key.includes("step6") ? "✍️" : p.key.includes("review") ? "🔎" : "🚀"}</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{p.label || p.key}</div>
              {p.desc && <div style={{ fontSize: 10, color: T.textSoft }}>{p.desc}</div>}
            </div>
            {p.is_custom && <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 99, background: T.purpleLight, color: T.purple, fontWeight: 600 }}>Custom</span>}
            {editing !== p.key ? (
              <div style={{ display: "flex", gap: 4 }}>
                <button onClick={() => startEdit(p)} style={smallBtn}>Edit</button>
                {p.is_custom && <button onClick={() => reset(p.key)} style={{ ...smallBtn, color: T.red }}>Reset</button>}
              </div>
            ) : (
              <div style={{ display: "flex", gap: 4 }}>
                <button onClick={save} disabled={saving} style={{ ...smallBtn, background: T.purple, color: "#fff" }}>{saving ? "Saving…" : "Save"}</button>
                <button onClick={cancel} style={smallBtn}>Cancel</button>
              </div>
            )}
          </div>
          {editing === p.key && (
            <textarea value={editValue} onChange={e => setEditValue(e.target.value)}
              style={{ width: "100%", minHeight: 200, padding: 14, border: "none", outline: "none", fontFamily: "monospace", fontSize: 12, resize: "vertical", background: "#FAFAFA" }} />
          )}
        </div>
      ))}
    </div>
  )
}

// ── Log Table ──────────────────────────────────────────────────────────────────
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

// ════════════════════════════════════════════════════════════════════════════════
// MAIN AI HUB COMPONENT
// ════════════════════════════════════════════════════════════════════════════════
export default function AIHub() {
  const qclient = useQueryClient()
  const [section, setSection] = useState("status")     // status | routing | prompts | logs
  const [routing, setRouting] = useState(null)
  const [routingDirty, setRoutingDirty] = useState(false)
  const [savingRouting, setSavingRouting] = useState(false)

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

  const applyPreset = (key) => {
    setRouting(PRESETS[key].routing)
    setRoutingDirty(true)
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
        {sectionBtn("prompts", "Prompts", "📝")}
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
          {/* Presets */}
          <div style={{ marginBottom: 14, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: T.textSoft }}>Presets:</span>
            {Object.entries(PRESETS).map(([key, preset]) => (
              <button key={key} onClick={() => applyPreset(key)} style={{
                padding: "5px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
                background: "#fff", fontSize: 11, cursor: "pointer", fontWeight: 500,
              }} title={preset.desc}>
                {preset.label}
              </button>
            ))}
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
          <div style={{ marginTop: 16, padding: 14, background: "#F9F9F9", borderRadius: 10, fontSize: 11, color: T.textSoft, lineHeight: 1.8 }}>
            <strong style={{ color: T.text }}>How routing works:</strong><br />
            Each pipeline step tries providers in order: 1st → 2nd → 3rd.<br />
            If a provider fails (timeout, rate limit, error), it falls through to the next.<br />
            <strong>"skip"</strong> = stop trying, use fallback data for that step.<br />
            <strong>"Save Routing"</strong> applies to new articles. <strong>"Save &amp; Propagate"</strong> also pushes changes to any currently running pipelines.
          </div>
        </div>
      )}

      {/* ── SECTION: Prompts ──────────────────────────────────────────────── */}
      {section === "prompts" && (
        <div>
          <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 12 }}>
            Customize the instructions given to AI at each pipeline step. Changes apply to all new articles.
          </div>
          <PromptsEditor />
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
