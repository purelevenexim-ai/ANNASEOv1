/**
 * System Routing Templates — single source of truth for built-in AI routing presets.
 *
 * Used by AIHub.jsx and NewArticleModal.jsx.
 * Each step uses a 3-slot fallback chain: { first, second, third } (provider IDs).
 *
 * Canonical v2 steps (10 AI-routed):
 *   research, structure, verify, links, references, draft, recovery,
 *   humanize, quality_loop, redevelop
 *
 * Step 7 (Validate & Score) is deterministic/local — no routing needed.
 *
 * Provider IDs must match backend _usable set exactly:
 *   groq, ollama, ollama_remote, gemini_free, gemini_paid,
 *   or_gemini_flash, or_gemini_lite, or_gemini_pro, or_deepseek, or_deepseek_r1,
 *   or_claude, or_gpt4o, or_o4_mini, or_qwen, skip, etc.
 */

export const SYSTEM_TEMPLATES = [
  {
    id: "free_testing",
    name: "🆓 Free Testing",
    description: "Zero cost — Groq for speed, Ollama for local recovery. Good for testing pipelines.",
    version: 2,
    system: true,
    steps: {
      research:     { first: "groq",    second: "ollama",  third: "skip" },
      structure:    { first: "groq",    second: "ollama",  third: "skip" },
      verify:       { first: "groq",    second: "ollama",  third: "skip" },
      links:        { first: "groq",    second: "ollama",  third: "skip" },
      references:   { first: "groq",    second: "ollama",  third: "skip" },
      draft:        { first: "groq",    second: "ollama",  third: "skip" },
      recovery:     { first: "ollama",  second: "groq",    third: "skip" },
      humanize:     { first: "groq",    second: "ollama",  third: "skip" },
      quality_loop: { first: "groq",    second: "ollama",  third: "skip" },
      redevelop:    { first: "groq",    second: "ollama",  third: "skip" },
    },
  },

  {
    id: "budget_balanced",
    name: "⚖️ Budget Balanced (Recommended)",
    description: "Best quality/cost balance — Flash for research, Claude for structure, DeepSeek for writing.",
    version: 2,
    system: true,
    steps: {
      research:     { first: "or_gemini_flash", second: "groq",            third: "or_qwen" },
      structure:    { first: "or_claude",       second: "or_deepseek",     third: "or_gemini_flash" },
      verify:       { first: "or_gemini_flash", second: "or_gemini_lite",  third: "skip" },
      links:        { first: "or_gemini_lite",  second: "or_gemini_flash", third: "skip" },
      references:   { first: "or_gemini_flash", second: "groq",            third: "or_qwen" },
      draft:        { first: "or_deepseek",     second: "or_gemini_flash", third: "groq" },
      recovery:     { first: "or_claude",       second: "or_deepseek",     third: "or_gemini_flash" },
      humanize:     { first: "or_gemini_flash", second: "or_deepseek",     third: "or_gemini_lite" },
      quality_loop: { first: "or_deepseek",     second: "or_gemini_flash", third: "or_gemini_lite" },
      redevelop:    { first: "or_gemini_flash", second: "or_deepseek",     third: "or_gemini_lite" },
    },
  },

  {
    id: "premium_under_1",
    name: "💎 Premium Under $1",
    description: "High quality within strict budget — Claude for structure/recovery, DeepSeek for drafting.",
    version: 2,
    system: true,
    steps: {
      research:     { first: "or_gemini_flash", second: "or_deepseek",    third: "groq" },
      structure:    { first: "or_claude",       second: "or_gemini_pro",  third: "or_deepseek" },
      verify:       { first: "or_gemini_flash", second: "or_gemini_pro",  third: "skip" },
      links:        { first: "or_gemini_lite",  second: "or_gemini_flash", third: "skip" },
      references:   { first: "or_gemini_flash", second: "or_deepseek",    third: "skip" },
      draft:        { first: "or_deepseek",     second: "or_claude",      third: "or_gemini_flash" },
      recovery:     { first: "or_claude",       second: "or_deepseek",    third: "or_gemini_flash" },
      humanize:     { first: "or_deepseek",     second: "or_gemini_flash", third: "or_gemini_lite" },
      quality_loop: { first: "or_deepseek",     second: "or_claude",      third: "or_gemini_flash" },
      redevelop:    { first: "or_deepseek",     second: "or_gemini_flash", third: "or_gemini_lite" },
    },
  },

  {
    id: "max_quality",
    name: "👑 Maximum Quality",
    description: "Best possible output — Gemini Pro + Claude for reasoning, GPT-4o for drafting. No budget cap.",
    version: 2,
    system: true,
    steps: {
      research:     { first: "or_gemini_pro",  second: "or_claude",      third: "or_gemini_flash" },
      structure:    { first: "or_gemini_pro",  second: "or_claude",      third: "or_gemini_flash" },
      verify:       { first: "or_gemini_pro",  second: "or_claude",      third: "skip" },
      links:        { first: "or_gemini_pro",  second: "or_deepseek",    third: "skip" },
      references:   { first: "or_gemini_pro",  second: "or_deepseek",    third: "skip" },
      draft:        { first: "or_gpt4o",       second: "or_claude",      third: "or_gemini_pro" },
      recovery:     { first: "or_claude",      second: "or_gemini_pro",  third: "or_o4_mini" },
      humanize:     { first: "or_claude",      second: "or_gemini_pro",  third: "or_gpt4o" },
      quality_loop: { first: "or_claude",      second: "or_gemini_pro",  third: "or_gpt4o" },
      redevelop:    { first: "or_gemini_pro",  second: "or_claude",      third: "or_gpt4o" },
    },
  },

  {
    id: "groq_ollama_utility",
    name: "⚡ Groq + Ollama Utility",
    description: "Fast infra mode — Groq for speed, remote Ollama for recovery. Ideal for bulk generation.",
    version: 2,
    system: true,
    steps: {
      research:     { first: "groq",           second: "ollama",         third: "skip" },
      structure:    { first: "groq",           second: "ollama",         third: "skip" },
      verify:       { first: "groq",           second: "ollama",         third: "skip" },
      links:        { first: "groq",           second: "ollama",         third: "skip" },
      references:   { first: "groq",           second: "ollama",         third: "skip" },
      draft:        { first: "groq",           second: "ollama_remote",  third: "ollama" },
      recovery:     { first: "ollama_remote",  second: "groq",           third: "ollama" },
      humanize:     { first: "groq",           second: "ollama_remote",  third: "ollama" },
      quality_loop: { first: "ollama_remote",  second: "groq",           third: "ollama" },
      redevelop:    { first: "ollama_remote",  second: "groq",           third: "ollama" },
    },
  },
]

export const DEFAULT_TEMPLATE_ID = "budget_balanced"

/**
 * Expand a v2 system template's steps into the legacy routing shape
 * that the backend _build_routing() and the current AIHub step matrix expect.
 *
 * All 10 canonical steps pass through directly.
 * Legacy-only fields (review, issues, score) are set to null so the backend uses its defaults.
 */
export function expandToLegacyRouting(steps) {
  const legacy = {}

  // Direct pass-through for all 10 canonical steps
  for (const key of ["research", "structure", "verify", "links", "references", "draft",
                      "recovery", "humanize", "quality_loop", "redevelop"]) {
    legacy[key] = steps[key] || null
  }

  // Legacy-only fields → null (backend uses engine defaults)
  legacy.review = null
  legacy.issues = null
  legacy.score = null

  return legacy
}
