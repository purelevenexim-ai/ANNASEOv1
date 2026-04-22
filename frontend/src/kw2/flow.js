/**
 * kw2 flow definitions + helpers for mode-based routing.
 */

export const KW2_FLOWS = {
  brand: [1, "BI", 2, "VALIDATE", "SCORETREE", "DELIVER"],
  expand: ["SEARCH", 2, "VALIDATE", "SCORETREE", "DELIVER"],
  review: ["SEARCH"],
  v2: ["UNDERSTAND", "EXPAND", "ORGANIZE", "APPLY"],
}

export const MODE_META = {
  brand: {
    title: "Develop for Brand",
    subtitle: "Analyze business, build intel, expand search, and run full strategy pipeline.",
    icon: "🚀",
    color: "#1d4ed8",
    bg: "#eff6ff",
    border: "#bfdbfe",
  },
  v2: {
    title: "v2 — Smart Pipeline",
    subtitle: "4 super phases: Understand → Expand → Organize → Apply. Multi-pillar keywords with graph visualization.",
    icon: "⚡",
    color: "#059669",
    bg: "#ecfdf5",
    border: "#6ee7b7",
  },
  expand: {
    title: "Expand Keyword Search",
    subtitle: "Start from Search (global) and push into generation + validation.",
    icon: "🔎",
    color: "#0f766e",
    bg: "#ecfeff",
    border: "#99f6e4",
  },
  review: {
    title: "Review Keywords",
    subtitle: "Use Search with My GSC data to inspect pillar authority and opportunities.",
    icon: "📊",
    color: "#7c3aed",
    bg: "#f5f3ff",
    border: "#ddd6fe",
  },
}

export function normalizeMode(mode) {
  const m = String(mode || "brand").toLowerCase()
  if (m === "expand" || m === "review" || m === "v2") return m
  if (m !== "brand") {
    // B18: log unknown modes instead of silently coercing
    console.warn(`[flow] Unknown mode "${mode}" — defaulting to brand`)
  }
  return "brand"
}

export function normalizePhaseKey(phase) {
  if (phase === "GSC") return "SEARCH"
  if (typeof phase === "string" && /^\d+$/.test(phase)) return Number(phase)
  return phase
}

export function getFlowForMode(mode) {
  const m = normalizeMode(mode)
  return (KW2_FLOWS[m] || KW2_FLOWS.brand).slice()
}

export function inferInitialPhase(session) {
  const mode = normalizeMode(session?.mode)
  const flow = (Array.isArray(session?.flow) && session.flow.length
    ? session.flow.map(normalizePhaseKey)
    : getFlowForMode(mode))

  // B19: validate current_phase belongs to the rendered flow before trusting it
  const current = normalizePhaseKey(session?.current_phase)
  if (current != null && flow.includes(current)) return current

  if (mode === "review") return "SEARCH"

  if (mode === "v2") {
    // B16: use ONLY phase_status JSON for v2 — never mix with legacy phase1_done
    const ps = session?.phase_status
    let phaseStatus = {}
    if (typeof ps === "string") {
      try { phaseStatus = JSON.parse(ps) } catch {
        // B17: corrupted phase_status — log and start from UNDERSTAND
        console.warn("[flow] Corrupted phase_status JSON — resetting to UNDERSTAND")
        return "UNDERSTAND"
      }
    } else if (ps && typeof ps === "object") {
      phaseStatus = ps
    }
    // Deterministic waterfall: each phase must be "done" to unlock the next
    if (phaseStatus.understand !== "done") return "UNDERSTAND"
    if (phaseStatus.expand !== "done") return "EXPAND"
    if (phaseStatus.organize !== "done") return "ORGANIZE"
    return "APPLY"
  }

  if (mode === "expand") {
    if (!session?.phase2_done) return "SEARCH"
    if (!session?.phase3_done) return "VALIDATE"
    if (!session?.phase6_done) return "SCORETREE"
    if (!session?.phase9_done) return "DELIVER"
    return "DELIVER"
  }

  // brand mode
  if (!session?.phase1_done) return 1
  if (!session?.phase2_done) return 2
  if (!session?.phase3_done) return "VALIDATE"
  if (!session?.phase6_done) return "SCORETREE"
  if (!session?.phase9_done) return "DELIVER"

  return flow[flow.length - 1] || 9
}

export function getNextFromFlow(flow, current) {
  const f = (flow || []).map(normalizePhaseKey)
  const cur = normalizePhaseKey(current)
  const idx = f.findIndex((x) => x === cur)
  if (idx < 0 || idx >= f.length - 1) return null
  return f[idx + 1]
}

export function getPrevFromFlow(flow, current) {
  const f = (flow || []).map(normalizePhaseKey)
  const cur = normalizePhaseKey(current)
  const idx = f.findIndex((x) => x === cur)
  if (idx <= 0) return null
  return f[idx - 1]
}
