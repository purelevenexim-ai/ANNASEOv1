/**
 * KwPage — Main container for Keyword Research v2.
 * Manages session lifecycle, persistent LiveConsole, and toast notifications.
 */
import React, { useEffect, useState, useCallback } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { PhaseStepper, Spinner, Card, RunButton, LiveConsole, ToastContainer } from "./shared"
import AISettingsModal from "./AISettingsModal"
import Kw2PromptStudio from "./Kw2PromptStudio"
import SessionDashboard from "./SessionCards"
import { getFlowForMode, inferInitialPhase, normalizeMode, normalizePhaseKey } from "./flow"

import Phase1 from "./Phase1"
import PhaseReadme from "./PhaseReadme"
import PhaseBI from "./PhaseBI"
import PhaseSearch from "../gsc/PhaseGSC"
import Phase2 from "./Phase2"
import PhaseValidateReview from "./PhaseValidateReview"
import Phase4 from "./Phase4"
import Phase5 from "./Phase5"
import PhaseGraphLinks from "./PhaseGraphLinks"
import PhaseScoreTree from "./PhaseScoreTree"
import PhaseDeliver from "./PhaseDeliver"
import Phase8 from "./Phase8"
import Phase9 from "./Phase9"
import PhaseExpand from "./PhaseExpand"
import PhaseOrganize from "./PhaseOrganize"
import PhaseApply from "./PhaseApply"
import PhaseUnderstand from "./PhaseUnderstand"
import PhaseAudit from "./PhaseAudit"

const PHASE_COMPONENTS = {
  1: Phase1,
  BI: PhaseBI,
  SEARCH: PhaseSearch,
  2: Phase2,
  // Validate+Review merged into stacked layout
  3: PhaseValidateReview,
  VALIDATE: PhaseValidateReview,
  REVIEW: PhaseValidateReview,
  // Score + Tree + Graph merged into PhaseScoreTree
  4: PhaseScoreTree,
  5: PhaseScoreTree,
  SCORETREE: PhaseScoreTree,
  // Links + Calendar + Strategy merged into PhaseDeliver
  6: PhaseDeliver,
  7: PhaseDeliver,
  GRAPHLINKS: PhaseDeliver,
  DELIVER: PhaseDeliver,
  8: PhaseDeliver,
  9: PhaseDeliver,
  UNDERSTAND: PhaseUnderstand,
  EXPAND: PhaseExpand,
  ORGANIZE: PhaseOrganize,
  APPLY: PhaseApply,
  AUDIT: PhaseAudit,
}

const PROVIDER_LABELS = { auto: "Auto", groq: "Groq", ollama: "Ollama", gemini: "Gemini", claude: "Claude" }

export default function KwPage({ projectId }) {
  const store = useKw2Store()
  const [initLoading, setInitLoading] = useState(true)
  const [showAISettings, setShowAISettings] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [showPromptStudio, setShowPromptStudio] = useState(false)
  const [creating, setCreating] = useState(false)

  // On mount: just mark ready — we always show the session dashboard first.
  // User explicitly clicks a card to activate a session.
  useEffect(() => {
    if (!projectId) return
    store.reset()
    store.clearLogs()
    setInitLoading(false)
  }, [projectId])

  const createSession = useCallback(async (mode = "brand", name = "") => {
    setCreating(true)
    store.setError(null)
    try {
      const seeds = []
      const { session_id, session: createdSession } = await api.createSession(
        projectId, store.aiProvider, mode, name, seeds
      )
      const session = createdSession || (await api.getSession(projectId, session_id)).session
      store.setSession(session_id, projectId)
      store.setSessionData(session)
      store.setWorkflow(session?.mode || mode, getFlowForMode(session?.mode || mode))
      store.setActivePhase(inferInitialPhase(session || { mode }))
      store.pushLog(`Session "${name || mode}" created`, { badge: "SESSION", type: "success" })
    } catch (e) {
      store.setError(e.message)
    }
    setCreating(false)
  }, [projectId, store.aiProvider])

  const refreshSession = useCallback(async () => {
    if (!store.sessionId) return
    try {
      const { session } = await api.getSession(projectId, store.sessionId)
      if (session) store.setSessionData(session)
    } catch { /* ignore */ }
  }, [projectId, store.sessionId])

  const loadSessionById = useCallback(async (sid, mode) => {
    store.setLoading(true)
    try {
      const { session } = await api.getSession(projectId, sid)
      if (session) {
        store.setSession(session.id, projectId)
        store.setSessionData(session)
        const m = normalizeMode(session.mode || mode)
        store.setWorkflow(m, getFlowForMode(m))
        store.setActivePhase(inferInitialPhase(session))
        const phaseStatus = typeof session.phase_status === "string"
          ? (() => { try { return JSON.parse(session.phase_status) } catch { return {} } })()
          : (session.phase_status || {})
        if (session.phase1_done || phaseStatus.understand === "done") {
          const { profile } = await api.getProfile(projectId)
          if (profile) store.setProfile(profile)
        }
        store.pushLog(`Switched to session ${sid.slice(0, 8)}`, { badge: "SESSION", type: "info" })
      }
    } catch (e) {
      store.setError(e.message)
    }
    store.setLoading(false)
  }, [projectId])

  useEffect(() => {
    if (!projectId || initLoading) return
    let deepLink = null
    try {
      deepLink = JSON.parse(localStorage.getItem("annaseo_kw2_open_session") || "null")
    } catch {
      deepLink = null
    }
    if (!deepLink || deepLink.projectId !== projectId || !deepLink.sessionId) return
    try { localStorage.removeItem("annaseo_kw2_open_session") } catch {}
    loadSessionById(deepLink.sessionId, deepLink.mode || "brand")
  }, [projectId, initLoading, loadSessionById])

  if (!projectId) {
    return <Card title="Keyword Research v2"><p>Select a project first.</p></Card>
  }

  if (initLoading) return <Spinner text="Loading…" />

  // ── Session Dashboard ── show card grid if no session is active yet
  if (!store.sessionId) {
    return (
      <div>
        <ToastContainer toasts={store.toasts} onDismiss={store.dismissToast} />
        {showAISettings && (
          <AISettingsModal projectId={projectId} sessionId={null} onClose={() => setShowAISettings(false)} />
        )}
        {showPromptStudio && (
          <Kw2PromptStudio filterPhases={[3, 5, 9]} onClose={() => setShowPromptStudio(false)} />
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16, gap: 8 }}>
          <button
            onClick={() => setShowPromptStudio(true)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "6px 14px", borderRadius: 7, border: "1px solid #d1d5db",
              background: "#f9fafb", cursor: "pointer", fontSize: 12, fontWeight: 500,
            }}
          >
            🧪 Prompts
          </button>
          <button
            onClick={() => setShowAISettings(true)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "6px 14px", borderRadius: 7, border: "1px solid #d1d5db",
              background: "#f9fafb", cursor: "pointer", fontSize: 12, fontWeight: 500,
            }}
          >
            ⚙ AI: {PROVIDER_LABELS[store.aiProvider] || store.aiProvider}
          </button>
        </div>
        <SessionDashboard
          projectId={projectId}
          onSelectSession={loadSessionById}
          onCreateSession={createSession}
          creating={creating}
        />
        {store.error && (
          <div style={{ marginTop: 12, color: "#dc2626", fontSize: 13 }}>{store.error}</div>
        )}
      </div>
    )
  }

  const completed = store.session
    ? Math.max(...[1,2,3,4,5,6,7,8,9].filter(i => store.session[`phase${i}_done`]), 0)
    : 0

  const activePhaseKey = normalizePhaseKey(store.activePhase)
  const ActivePhase = PHASE_COMPONENTS[activePhaseKey] || Phase1

  return (
    <div>
      {/* Toast notifications */}
      <ToastContainer toasts={store.toasts} onDismiss={store.dismissToast} />
      {showPromptStudio && (
        <Kw2PromptStudio filterPhases={[3, 5, 9]} onClose={() => setShowPromptStudio(false)} />
      )}

      {/* Active session header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <button
          onClick={() => { store.reset(); store.clearLogs() }}
          style={{
            display: "flex", alignItems: "center", gap: 5,
            padding: "5px 12px", borderRadius: 7, border: "1px solid #e5e7eb",
            background: "#fff", cursor: "pointer", fontSize: 12, fontWeight: 600, color: "#374151",
          }}
        >
          ← All Sessions
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            fontSize: 13, fontWeight: 700, color: "#374151",
            maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {store.session?.name
              || store.session?.seed_keywords?.join(", ")
              || `Session ${(store.sessionId || "").slice(-8)}`
            }
          </span>
          <button
            onClick={() => setShowPromptStudio(true)}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "4px 10px", borderRadius: 6, border: "1px solid #d1d5db",
              background: "#f9fafb", cursor: "pointer", fontSize: 12, fontWeight: 500,
            }}
          >
            🧪 Prompts
          </button>
          <button
            onClick={() => setShowAISettings(true)}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "4px 10px", borderRadius: 6, border: "1px solid #d1d5db",
              background: "#f9fafb", cursor: "pointer", fontSize: 12, fontWeight: 500,
            }}
          >
            ⚙ AI: {PROVIDER_LABELS[store.aiProvider] || store.aiProvider}
          </button>
          <button
            onClick={() => store.setActivePhase("AUDIT")}
            style={{
              display: "flex", alignItems: "center", gap: 4,
              padding: "4px 10px", borderRadius: 6, border: "1px solid #d1d5db",
              background: activePhaseKey === "AUDIT" ? "#eff6ff" : "#f9fafb",
              cursor: "pointer", fontSize: 12, fontWeight: 500,
              color: activePhaseKey === "AUDIT" ? "#1d4ed8" : "#374151",
            }}
            title="Pillar & Modifier Audit"
          >
            🔬 Audit
          </button>
          <button
            onClick={() => setShowHelp(true)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center",
              width: 28, height: 28, borderRadius: "50%", border: "1px solid #d1d5db",
              background: "#f9fafb", cursor: "pointer", fontSize: 14, fontWeight: 700, color: "#6b7280",
            }}
            title="Open Phase Guide"
          >
            ?
          </button>
        </div>
      </div>

      {showHelp && (
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "flex-start", justifyContent: "center",
            paddingTop: 40, overflowY: "auto",
          }}
          onClick={(e) => { if (e.target === e.currentTarget) setShowHelp(false) }}
        >
          <div style={{
            background: "#fff", borderRadius: 12, maxWidth: 820, width: "90%",
            maxHeight: "85vh", overflowY: "auto", padding: 24, position: "relative",
          }}>
            <button
              onClick={() => setShowHelp(false)}
              style={{
                position: "absolute", top: 14, right: 14,
                background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#6b7280",
              }}
            >
              ✕
            </button>
            <PhaseReadme />
          </div>
        </div>
      )}

      {showAISettings && (
        <AISettingsModal
          projectId={projectId}
          sessionId={store.sessionId}
          onClose={() => setShowAISettings(false)}
        />
      )}

      <PhaseStepper
        current={activePhaseKey}
        completed={completed}
        flow={store.flow}
        mode={store.mode}
        phaseStatus={store.session?.phase_status || {}}
        onSelect={(n) => store.setActivePhase(n)}
      />

      <ActivePhase
        projectId={projectId}
        sessionId={store.sessionId}
        onComplete={refreshSession}
        mode={store.mode}
        onContinue={() => store.goNextPhase()}
        allowWorkflowContinue={store.mode !== "review"}
      />

      {/* Persistent Live Console at bottom */}
      <LiveConsole logs={store.consoleLogs} />
    </div>
  )
}
