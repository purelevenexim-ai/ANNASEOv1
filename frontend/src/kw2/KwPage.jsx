/**
 * KwPage — Main container for Keyword Research v2.
 * Manages session lifecycle, persistent LiveConsole, and toast notifications.
 */
import React, { useEffect, useState, useCallback } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { PhaseStepper, Spinner, Card, RunButton, LiveConsole, ToastContainer } from "./shared"
import AISettingsModal from "./AISettingsModal"

import Phase1 from "./Phase1"
import Phase2 from "./Phase2"
import Phase3 from "./Phase3"
import Phase3Review from "./Phase3Review"
import Phase4 from "./Phase4"
import Phase5 from "./Phase5"
import Phase6 from "./Phase6"
import Phase7 from "./Phase7"
import Phase8 from "./Phase8"
import Phase9 from "./Phase9"

const PHASE_COMPONENTS = {
  1: Phase1,
  2: Phase2,
  3: Phase3,
  REVIEW: Phase3Review,
  4: Phase4,
  5: Phase5,
  6: Phase6,
  7: Phase7,
  8: Phase8,
  9: Phase9,
}

const PROVIDER_LABELS = { auto: "Auto", groq: "Groq", ollama: "Ollama", gemini: "Gemini", claude: "Claude" }

export default function KwPage({ projectId }) {
  const store = useKw2Store()
  const [initLoading, setInitLoading] = useState(true)
  const [showAISettings, setShowAISettings] = useState(false)

  // Initialize: load or create session
  useEffect(() => {
    if (!projectId) return
    let cancelled = false

    async function init() {
      setInitLoading(true)
      store.setError(null)
      try {
        // Try to load existing session
        const { session } = await api.getLatestSession(projectId)
        if (!cancelled && session) {
          store.setSession(session.id, projectId)
          store.setSessionData(session)
          const phase = store.getCurrentPhase()
          store.setActivePhase(phase)

          // Load profile if phase1 done
          if (session.phase1_done) {
            const { profile } = await api.getProfile(projectId)
            if (profile) store.setProfile(profile)
          }
        }
      } catch {
        // No session yet — that's fine
      }
      if (!cancelled) setInitLoading(false)
    }
    init()
    return () => { cancelled = true }
  }, [projectId])

  const createSession = useCallback(async () => {
    store.setLoading(true)
    store.setError(null)
    try {
      const { session_id } = await api.createSession(projectId)
      const { session } = await api.getSession(projectId, session_id)
      store.setSession(session_id, projectId)
      store.setSessionData(session)
      store.setActivePhase(1)
      store.pushLog("Session created", { badge: "SESSION", type: "success" })
    } catch (e) {
      store.setError(e.message)
    }
    store.setLoading(false)
  }, [projectId])

  const refreshSession = useCallback(async () => {
    if (!store.sessionId) return
    try {
      const { session } = await api.getSession(projectId, store.sessionId)
      if (session) store.setSessionData(session)
    } catch { /* ignore */ }
  }, [projectId, store.sessionId])

  if (!projectId) {
    return <Card title="Keyword Research v2"><p>Select a project first.</p></Card>
  }

  if (initLoading) return <Spinner text="Loading session..." />

  // No session yet
  if (!store.sessionId) {
    return (
      <Card title="Keyword Research v2">
        <p style={{ color: "#6b7280", marginBottom: 12 }}>
          Start a new keyword research session for this project.
        </p>
        <RunButton onClick={createSession} loading={store.loading}>
          Start New Research
        </RunButton>
        {store.error && <p style={{ color: "#dc2626", marginTop: 8 }}>{store.error}</p>}
      </Card>
    )
  }

  const completed = store.session
    ? Math.max(...[1,2,3,4,5,6,7,8,9].filter(i => store.session[`phase${i}_done`]), 0)
    : 0

  const ActivePhase = PHASE_COMPONENTS[store.activePhase] || Phase1

  return (
    <div>
      {/* Toast notifications */}
      <ToastContainer toasts={store.toasts} onDismiss={store.dismissToast} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>Keyword Research v2</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button
            onClick={() => setShowAISettings(true)}
            title="Configure AI provider"
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "4px 12px", borderRadius: 6, border: "1px solid #d1d5db",
              background: "#f9fafb", cursor: "pointer", fontSize: 12, fontWeight: 500,
            }}
          >
            <span>⚙</span>
            <span>AI: {PROVIDER_LABELS[store.aiProvider] || store.aiProvider}</span>
          </button>
          <span style={{ fontSize: 12, color: "#9ca3af" }}>Session: {store.sessionId}</span>
        </div>
      </div>

      {showAISettings && (
        <AISettingsModal
          projectId={projectId}
          sessionId={store.sessionId}
          onClose={() => setShowAISettings(false)}
        />
      )}

      <PhaseStepper
        current={store.activePhase}
        completed={completed}
        onSelect={(n) => store.setActivePhase(n)}
      />

      <ActivePhase
        projectId={projectId}
        sessionId={store.sessionId}
        onComplete={refreshSession}
      />

      {/* Persistent Live Console at bottom */}
      <LiveConsole logs={store.consoleLogs} />
    </div>
  )
}
