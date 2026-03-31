import { create } from "zustand"

export const useDebug = create((set, get) => ({
  enabled: localStorage.getItem("annaseo_debug") === "true",
  logs: [],

  toggle: () => {
    const newState = !get().enabled
    localStorage.setItem("annaseo_debug", String(newState))
    set({ enabled: newState, logs: [] })
  },

  addLog: (entry) => {
    set(state => {
      const logs = [...state.logs, entry]
      // Keep only last 100 logs
      return { logs: logs.slice(-100) }
    })
  },

  clear: () => set({ logs: [] }),
}))

export default useDebug
