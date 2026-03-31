import { create } from "zustand"

let _timers = {}

export const useNotification = create((set, get) => ({
  notifications: [],

  // Notify: adds a toast and auto-dismisses unless `persistent` is true
  notify: (message, type = "info", opts = {}) => {
    const { duration = 5000, persistent = false } = opts || {}
    const id = `n_${Date.now()}_${Math.floor(Math.random() * 10000)}`
    const item = { id, message, type, duration, persistent }
    set((s) => ({ notifications: [...s.notifications, item] }))

    if (!persistent && duration > 0) {
      _timers[id] = setTimeout(() => {
        set((s) => ({ notifications: s.notifications.filter(n => n.id !== id) }))
        delete _timers[id]
      }, duration)
    }

    return id
  },

  // Clear one or all notifications
  clear: (id) => {
    if (id) {
      if (_timers[id]) { clearTimeout(_timers[id]); delete _timers[id] }
      set((s) => ({ notifications: s.notifications.filter(n => n.id !== id) }))
    } else {
      Object.values(_timers).forEach(t => clearTimeout(t))
      _timers = {}
      set({ notifications: [] })
    }
  },

  // Pause auto-dismiss for a toast (hover behavior)
  pause: (id) => {
    if (_timers[id]) { clearTimeout(_timers[id]); delete _timers[id] }
  },

  // Resume auto-dismiss for a toast (hover leave)
  resume: (id) => {
    const s = get()
    const n = s.notifications.find(x => x.id === id)
    if (!n || n.persistent) return
    if (_timers[id]) return
    _timers[id] = setTimeout(() => {
      set((s2) => ({ notifications: s2.notifications.filter(x => x.id !== id) }))
      delete _timers[id]
    }, n.duration || 5000)
  },
}))

export default useNotification
