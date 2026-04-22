/**
 * kw2 Zustand store — manages session, phase progression, and cached data.
 */
import { create } from "zustand"
import { getFlowForMode, normalizeMode, normalizePhaseKey, inferInitialPhase, getNextFromFlow, getPrevFromFlow } from "./flow"

function _ts() {
  return new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

const useKw2Store = create((set, get) => ({
  // Session
  sessionId: null,
  projectId: null,
  session: null,
  mode: "brand",
  flow: getFlowForMode("brand"),

  // AI provider setting (per-session, falls back to global default)
  aiProvider: "auto",

  // Phase data
  profile: null,
  universeCount: 0,
  validatedCount: 0,
  top100: [],
  tree: null,
  graph: null,
  links: [],
  calendar: [],
  strategy: null,
  dashboard: null,

  // UI
  activePhase: 1,
  loading: false,
  error: null,
  streamEvents: [],

  // Global console log (all phases, capped at 300)
  consoleLogs: [],

  // Toast Notifications
  toasts: [],

  // ── Actions ──────────────────────────────────────────────────────────────
  setSession: (sid, pid) => {
    // B24-B25: Clear stale session state when switching sessions
    const prev = get().sessionId
    if (prev && prev !== sid) {
      // Remove session-scoped localStorage keys from prior session
      try { localStorage.removeItem(`kw2_phase1_${prev}`) } catch {}
      try { localStorage.removeItem(`kw2_domain_${prev}`) } catch {}
      try { localStorage.removeItem(`kw2_comp_urls_${prev}`) } catch {}
    }
    set({ sessionId: sid, projectId: pid, aiProvider: "auto" })
  },
  setSessionData: (data) => set({ session: data }),
  setWorkflow: (mode, flow = null) => {
    const m = normalizeMode(mode)
    const f = (Array.isArray(flow) && flow.length ? flow : getFlowForMode(m)).map(normalizePhaseKey)
    set({ mode: m, flow: f })
  },
  setProfile: (p) => {
    if (!p) { set({ profile: null }); return }
    // Normalize: ensure all array fields are always arrays (API may return strings, JSON arrays, or counts)
    const toArr = (v) => {
      if (Array.isArray(v)) return v
      if (typeof v === "string" && v) {
        if (v.startsWith("[")) {
          try { const p = JSON.parse(v); if (Array.isArray(p)) return p } catch {}
        }
        return v.split(",").map((s) => s.trim()).filter(Boolean)
      }
      return []
    }
    set({
      profile: {
        ...p,
        pillars: toArr(p.pillars),
        product_catalog: toArr(p.product_catalog),
        modifiers: toArr(p.modifiers),
        negative_scope: toArr(p.negative_scope),
        audience: toArr(p.audience),
      },
    })
  },
  setUniverseCount: (n) => set({ universeCount: n }),
  setValidatedCount: (n) => set({ validatedCount: n }),
  setTop100: (items) => set({ top100: items }),
  setTree: (t) => set({ tree: t }),
  setGraph: (g) => set({ graph: g }),
  setLinks: (l) => set({ links: l }),
  setCalendar: (c) => set({ calendar: c }),
  setStrategy: (s) => set({ strategy: s }),
  setDashboard: (d) => set({ dashboard: d }),
  setActivePhase: (n) => set({ activePhase: normalizePhaseKey(n) }),
  goNextPhase: (from = null) => {
    const s = get()
    const current = normalizePhaseKey(from ?? s.activePhase)
    const next = getNextFromFlow(s.flow, current)
    if (next !== null) set({ activePhase: next })
    return next
  },
  goPrevPhase: (from = null) => {
    const s = get()
    const current = normalizePhaseKey(from ?? s.activePhase)
    const prev = getPrevFromFlow(s.flow, current)
    if (prev !== null) set({ activePhase: prev })
    return prev
  },
  setLoading: (b) => set({ loading: b }),
  setError: (e) => set({ error: e }),
  pushStreamEvent: (ev) => set((s) => ({ streamEvents: [...s.streamEvents, ev] })),
  clearStreamEvents: () => set({ streamEvents: [] }),

  // AI provider
  setAiProvider: (p) => {
    localStorage.setItem("kw2_ai_provider", p)
    set({ aiProvider: p })
  },

  // Console log (global across all phases)
  pushLog: (text, opts = {}) =>
    set((s) => ({
      consoleLogs: [...s.consoleLogs.slice(-499), { time: _ts(), ts: Date.now(), text, ...opts }],
    })),
  // Update the last log entry in-place (for streaming progress updates)
  updateLastLog: (text, opts = {}) =>
    set((s) => {
      if (!s.consoleLogs.length) return {}
      const updated = [...s.consoleLogs]
      updated[updated.length - 1] = { ...updated[updated.length - 1], text, ...opts }
      return { consoleLogs: updated }
    }),
  clearLogs: () => set({ consoleLogs: [] }),

  // Toast notifications
  addToast: (message, type = "success", duration = 4500) => {
    const id = Date.now() + Math.random()
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }))
    if (duration > 0) {
      setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), duration)
    }
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  // Compute current phase from session flags
  getCurrentPhase: () => {
    const s = get().session
    if (!s) return 1
    return inferInitialPhase(s)
  },

  reset: () =>
    set({
      sessionId: null,
      projectId: null,
      session: null,
      mode: "brand",
      flow: getFlowForMode("brand"),
      profile: null,
      universeCount: 0,
      validatedCount: 0,
      top100: [],
      tree: null,
      graph: null,
      links: [],
      calendar: [],
      strategy: null,
      dashboard: null,
      activePhase: 1,
      loading: false,
      error: null,
      streamEvents: [],
      consoleLogs: [],
      toasts: [],
    }),
}))

// Expose pushLog globally so API/SSE errors are captured without prop drilling
if (typeof window !== "undefined") {
  window._kw2pushLog = (text, opts) => useKw2Store.getState().pushLog(text, opts)
  window._kw2updateLastLog = (text, opts) => useKw2Store.getState().updateLastLog(text, opts)

  // Capture unhandled JS errors → push to console store
  window.addEventListener("error", (ev) => {
    useKw2Store.getState().pushLog(
      `[JS Error] ${ev.message} (${ev.filename?.split("/").pop() || "?"}:${ev.lineno})`,
      { badge: "BROWSER", type: "error" }
    )
  })
  window.addEventListener("unhandledrejection", (ev) => {
    const msg = ev.reason?.message || String(ev.reason) || "Unhandled Promise rejection"
    useKw2Store.getState().pushLog(`[Promise] ${msg}`, { badge: "BROWSER", type: "error" })
  })

  // Intercept console.error so frontend errors appear in the console panel
  const _origError = console.error.bind(console)
  console.error = (...args) => {
    _origError(...args)
    const msg = args.map(a => (typeof a === "object" ? (a?.message || JSON.stringify(a).slice(0, 200)) : String(a))).join(" ")
    if (!msg.includes("[React]") && !msg.includes("Warning:")) {
      useKw2Store.getState().pushLog(`[console.error] ${msg.slice(0, 300)}`, { badge: "BROWSER", type: "error" })
    }
  }
  const _origWarn = console.warn.bind(console)
  console.warn = (...args) => {
    _origWarn(...args)
    const msg = args.map(a => (typeof a === "object" ? (a?.message || JSON.stringify(a).slice(0, 200)) : String(a))).join(" ")
    if (!msg.includes("Warning:") && !msg.includes("React does not recognize")) {
      useKw2Store.getState().pushLog(`[console.warn] ${msg.slice(0, 200)}`, { badge: "BROWSER", type: "warning" })
    }
  }
}

export default useKw2Store
