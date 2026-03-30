import { create } from "zustand"

export const useNotification = create((set) => ({
  message: null,
  type: "error",
  show: false,

  setNotification: (msg, type = "error") => set({ message: msg, type, show: true }),

  clear: () => set({ show: false, message: null }),
}))

export default useNotification
