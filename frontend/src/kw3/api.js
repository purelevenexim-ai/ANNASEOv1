/**
 * kw3 API helpers — minimal surface, calls existing /api/kw2 backend.
 * No backend changes required.
 */
import apiCall from "../lib/apiCall"

const KW2 = "/api/kw2"
const API = import.meta.env.VITE_API_URL || ""

// ── Sessions ────────────────────────────────────────────────────────────────
export const listSessions   = (pid)            => apiCall(`${KW2}/${pid}/sessions/list`)
export const getSession     = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}`)
export const createSession  = (pid, name="")   => apiCall(`${KW2}/${pid}/sessions`, "POST", { provider: "auto", mode: "brand", name, seed_keywords: [] })
export const deleteSession  = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}`, "DELETE")
export const renameSession  = (pid, sid, name) => apiCall(`${KW2}/${pid}/sessions/${sid}/name`, "PUT", { name })

// ── Phase 1: Business ───────────────────────────────────────────────────────
export const getProfile     = (pid)            => apiCall(`${KW2}/${pid}/profile`)
export const runPhase1      = (pid, sid, body) => apiCall(`${KW2}/${pid}/sessions/${sid}/phase1`, "POST", body)

// ── Phase 2: Generate ───────────────────────────────────────────────────────
export const getUniverse    = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/universe`)
export const globalSuggest  = (seed, country="us", limit=100) =>
  apiCall(`/api/kw/global-suggest`, "POST", { seed, country, limit })

// ── Phase 3+4: Validate & Score ────────────────────────────────────────────
export const runPhase3      = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/phase3`, "POST", {})
export const runPhase4      = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/phase4`, "POST", {})
export const getValidated   = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/validated`)
export const getTop100      = (pid, sid, pillar=null) => {
  const q = pillar ? `?pillar=${encodeURIComponent(pillar)}` : ""
  return apiCall(`${KW2}/${pid}/sessions/${sid}/top100${q}`)
}
export const updateKeyword  = (pid, sid, kid, body) => apiCall(`${KW2}/${pid}/sessions/${sid}/validated/${kid}`, "PUT", body)
export const deleteKeyword  = (pid, sid, kid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/validated/${kid}`, "DELETE")
export const rejectKeywords = (pid, sid, ids)       => apiCall(`${KW2}/${pid}/sessions/${sid}/keywords/reject`, "POST", { ids })

// ── Phase 5/6/7/8/9: Strategy bundle ───────────────────────────────────────
export const runPhase5      = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/phase5`, "POST", {})
export const runPhase6      = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/phase6`, "POST", {})
export const runPhase7      = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/phase7`, "POST", {})
export const runPhase8      = (pid, sid, cfg={}) => apiCall(`${KW2}/${pid}/sessions/${sid}/phase8`, "POST", cfg)
export const runPhase9      = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/phase9`, "POST", {})
export const getTree        = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/tree`)
export const getGraph       = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/graph`)
export const getLinks       = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/links`)
export const getCalendar    = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/calendar`)
export const getStrategy    = (pid, sid)       => apiCall(`${KW2}/${pid}/sessions/${sid}/strategy`)

// ── Phase 2 SSE stream ──────────────────────────────────────────────────────
export function streamPhase2(pid, sid, pillars, modifiers, onEvent) {
  const controller = new AbortController()
  let aborted = false

  ;(async () => {
    let token = ""
    try {
      const res = await apiCall("/api/auth/stream-token", "POST")
      token = res?.stream_token || ""
    } catch {
      token = localStorage.getItem("annaseo_token") || ""
    }
    const params = new URLSearchParams()
    pillars.forEach(p => params.append("confirmed_pillars", p))
    modifiers.forEach(m => params.append("confirmed_modifiers", m))
    params.set("reset", "true")
    if (token) params.set("token", token)

    const url = `${API}${KW2}/${pid}/sessions/${sid}/phase2/stream?${params}`
    let resp
    try {
      resp = await fetch(url, { signal: controller.signal })
    } catch (e) {
      if (!aborted) onEvent({ type: "error", message: e.message })
      return
    }
    if (!resp.ok) { onEvent({ type: "error", message: `HTTP ${resp.status}` }); return }
    const reader = resp.body.getReader()
    const dec = new TextDecoder()
    let buf = ""
    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done || aborted) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop()
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try { onEvent(JSON.parse(line.slice(6))) } catch {}
          }
        }
      }
    } catch (e) { if (!aborted) onEvent({ type: "error", message: e.message }) }
  })()

  return () => { aborted = true; controller.abort() }
}

// ── Phase 3 SSE stream ──────────────────────────────────────────────────────
export function streamPhase3(pid, sid, onEvent) {
  const controller = new AbortController()
  let aborted = false
  ;(async () => {
    let token = ""
    try {
      const res = await apiCall("/api/auth/stream-token", "POST")
      token = res?.stream_token || ""
    } catch {
      token = localStorage.getItem("annaseo_token") || ""
    }
    const params = new URLSearchParams()
    if (token) params.set("token", token)
    const url = `${API}${KW2}/${pid}/sessions/${sid}/phase3/stream?${params}`
    let resp
    try { resp = await fetch(url, { signal: controller.signal }) }
    catch (e) { if (!aborted) onEvent({ type: "error", message: e.message }); return }
    if (!resp.ok) { onEvent({ type: "error", message: `HTTP ${resp.status}` }); return }
    const reader = resp.body.getReader()
    const dec = new TextDecoder()
    let buf = ""
    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done || aborted) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop()
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try { onEvent(JSON.parse(line.slice(6))) } catch {}
          }
        }
      }
    } catch (e) { if (!aborted) onEvent({ type: "error", message: e.message }) }
  })()
  return () => { aborted = true; controller.abort() }
}

// ── Validated keyword management ────────────────────────────────────────────
export const addKeyword = (pid, sid, body) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/validated/add`, "POST", body)

// ── Business README ─────────────────────────────────────────────────────────
export const getBusinessReadme = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/business-readme`)

export const generateBusinessReadme = (pid, sid, force = false) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/business-readme`, "POST", { force })

