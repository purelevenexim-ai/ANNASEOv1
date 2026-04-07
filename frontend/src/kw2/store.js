/**
 * kw2 Zustand store — manages session, phase progression, and cached data.
 */
import { create } from "zustand"

function _ts() {
  return new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

const useKw2Store = create((set, get) => ({
  // Session
  sessionId: null,
  projectId: null,
  session: null,

  // AI provider setting (persisted locally, synced to session on backend)
  aiProvider: localStorage.getItem("kw2_ai_provider") || "auto",

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
  setSession: (sid, pid) => set({ sessionId: sid, projectId: pid }),
  setSessionData: (data) => set({ session: data }),
  setProfile: (p) => set({ profile: p }),
  setUniverseCount: (n) => set({ universeCount: n }),
  setValidatedCount: (n) => set({ validatedCount: n }),
  setTop100: (items) => set({ top100: items }),
  setTree: (t) => set({ tree: t }),
  setGraph: (g) => set({ graph: g }),
  setLinks: (l) => set({ links: l }),
  setCalendar: (c) => set({ calendar: c }),
  setStrategy: (s) => set({ strategy: s }),
  setDashboard: (d) => set({ dashboard: d }),
  setActivePhase: (n) => set({ activePhase: n }),
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
      consoleLogs: [...s.consoleLogs.slice(-299), { time: _ts(), text, ...opts }],
    })),
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
    for (let i = 9; i >= 1; i--) {
      if (s[`phase${i}_done`]) return Math.min(i + 1, 9)
    }
    return 1
  },

  reset: () =>
    set({
      sessionId: null,
      projectId: null,
      session: null,
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
}

export default useKw2Store
