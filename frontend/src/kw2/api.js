/**
 * kw2 API helpers — all /api/kw2/ calls centralized.
 */
import apiCall from "../lib/apiCall"

const KW2 = "/api/kw2"

// ── Session ─────────────────────────────────────────────────────────────────

export const createSession = (projectId, provider = "auto") =>
  apiCall(`${KW2}/${projectId}/sessions`, "POST", { provider })

export const getLatestSession = (projectId) =>
  apiCall(`${KW2}/${projectId}/sessions`)

export const getSession = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}`)

// ── Phase 1: Business Analysis ──────────────────────────────────────────────

export const runPhase1 = (projectId, sessionId, manualInput) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase1`, "POST", manualInput)

export const getProfile = (projectId) =>
  apiCall(`${KW2}/${projectId}/profile`)

// ── Phase 2: Keyword Universe ───────────────────────────────────────────────

export const runPhase2 = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase2`, "POST")

export const getUniverse = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/universe`)

export function streamPhase2(projectId, sessionId, onEvent) {
  return _streamSSE(`${KW2}/${projectId}/sessions/${sessionId}/phase2/stream`, onEvent)
}

// ── Phase 3: Validation ─────────────────────────────────────────────────────

export const runPhase3 = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase3`, "POST")

export const getValidated = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/validated`)

export function streamPhase3(projectId, sessionId, onEvent) {
  return _streamSSE(`${KW2}/${projectId}/sessions/${sessionId}/phase3/stream`, onEvent)
}

// ── Phase 4: Score + Cluster ────────────────────────────────────────────────

export const runPhase4 = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase4`, "POST")

// ── Phase 5: Tree + Top 100 ────────────────────────────────────────────────

export const runPhase5 = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase5`, "POST")

export const getTop100 = (projectId, sessionId, pillar = null) => {
  const qs = pillar ? `?pillar=${encodeURIComponent(pillar)}` : ""
  return apiCall(`${KW2}/${projectId}/sessions/${sessionId}/top100${qs}`)
}

export const getTree = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/tree`)

export const getDashboard = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/dashboard`)

export const explainKeyword = (projectId, sessionId, keywordId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/explain/${keywordId}`, "POST")

// ── Phase 6: Knowledge Graph ────────────────────────────────────────────────

export const runPhase6 = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase6`, "POST")

export const getGraph = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/graph`)

// ── Phase 7: Internal Links ─────────────────────────────────────────────────

export const runPhase7 = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase7`, "POST")

export const getLinks = (projectId, sessionId, linkType = null) => {
  const qs = linkType ? `?link_type=${encodeURIComponent(linkType)}` : ""
  return apiCall(`${KW2}/${projectId}/sessions/${sessionId}/links${qs}`)
}

// ── Phase 8: Content Calendar ───────────────────────────────────────────────

export const runPhase8 = (projectId, sessionId, config = {}) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase8`, "POST", {
    blogs_per_week: config.blogsPerWeek || 3,
    duration_weeks: config.durationWeeks || 52,
    start_date: config.startDate || null,
    seasonal_overrides: config.seasonalOverrides || {},
  })

export const getCalendar = (projectId, sessionId, pillar = null) => {
  const qs = pillar ? `?pillar=${encodeURIComponent(pillar)}` : ""
  return apiCall(`${KW2}/${projectId}/sessions/${sessionId}/calendar${qs}`)
}

// ── Phase 9: Strategy ───────────────────────────────────────────────────────

export const runPhase9 = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase9`, "POST")

export const getStrategy = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/strategy`)

// ── Run All ─────────────────────────────────────────────────────────────────

export const runAll = (projectId, sessionId, manualInput) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/run-all`, "POST", manualInput)

// ── AI Provider ──────────────────────────────────────────────────────────────

export const setSessionProvider = (projectId, sessionId, provider) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/provider`, "POST", { provider })

// ── Manual Review ────────────────────────────────────────────────────────────

export const updateKeyword = (projectId, sessionId, kwId, body) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/validated/${kwId}`, "PUT", body)

export const deleteKeyword = (projectId, sessionId, kwId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/validated/${kwId}`, "DELETE")

export const addKeyword = (projectId, sessionId, body) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/validated/add`, "POST", body)

export const getPillarStats = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/pillar-stats`)

// ── SSE helper ──────────────────────────────────────────────────────────────

function _streamSSE(path, onEvent) {
  const API = import.meta.env.VITE_API_URL || ""
  const token = localStorage.getItem("annaseo_token")
  const url = `${API}${path}`
  const fullUrl = `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token || "")}`

  const es = new EventSource(fullUrl)

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      onEvent(data)
      if (data.done) es.close()
    } catch (err) {
      if (typeof window._kw2pushLog === "function") {
        window._kw2pushLog(`[SSE] Parse error: ${err.message} — raw: ${String(e.data).slice(0, 100)}`, { badge: "SSE", type: "error" })
      }
    }
  }

  es.onerror = (err) => {
    if (typeof window._kw2pushLog === "function") {
      window._kw2pushLog(`[SSE] Connection error on ${path}`, { badge: "SSE", type: "error" })
    }
    es.close()
    onEvent({ error: true, done: true, message: "SSE connection failed" })
  }

  return () => es.close()
}
