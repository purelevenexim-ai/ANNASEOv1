import { create } from "zustand"
import apiCall from "../lib/apiCall"

const useWorkflowContext = create((set, get) => ({
  sessionId: null,
  step1: null,  // { pillars[], supports[], customerUrl, competitorUrls[], intent[], profile }
  step2: null,  // { keyword_ids[], keyword_count }
  step3: null,  // { runs[], pipeline_complete }
  step4: null,  // { strategy_json, ai_source, approved }

  setSession: (sid) => set({ sessionId: sid }),

  setStep: (n, data) => set(state => ({ [`step${n}`]: { ...(state[`step${n}`] || {}), ...data } })),

  flush: async (projectId) => {
    const { sessionId, step1, step2, step3, step4 } = get()
    if (!sessionId || !projectId) return
    try {
      await apiCall(`/api/ki/${projectId}/session/${sessionId}/ctx`, "PATCH", {
        step1, step2, step3, step4,
      })
    } catch (e) {
      console.warn("[WorkflowContext] flush failed:", e.message)
    }
  },

  loadFromSession: async (projectId, sessionId) => {
    try {
      const data = await apiCall(`/api/ki/${projectId}/session/${sessionId}/ctx`)
      // Migration: map old 6-step data to new 4-step structure
      const s1 = data.step1 || null
      const s2 = data.step2 || null
      // Old step3 was strategy, old step5 was pipeline — remap
      const s3 = data.step3?.runs ? data.step3 : (data.step5 || null)
      const s4 = data.step4?.strategy_json ? data.step4 : (data.step3?.strategy_json ? data.step3 : (data.step6 || null))
      set({
        sessionId,
        step1: s1,
        step2: s2,
        step3: s3,
        step4: s4,
      })
    } catch (e) {
      // Session may not have ctx yet — just set sessionId
      set({ sessionId })
    }
  },

  reset: () => set({ sessionId: null, step1: null, step2: null, step3: null, step4: null }),
}))

export default useWorkflowContext
