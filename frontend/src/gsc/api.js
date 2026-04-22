/**
 * GSC Frontend API helpers.
 */
import apiCall from "../lib/apiCall"

const GSC = "/api/gsc"

export const getStatus = (projectId) =>
  apiCall(`${GSC}/${projectId}/status`)

export const getAuthUrl = (projectId) =>
  apiCall(`${GSC}/${projectId}/auth/url`)

export const disconnect = (projectId) =>
  apiCall(`${GSC}/${projectId}/disconnect`, "DELETE")

export const listSites = (projectId) =>
  apiCall(`${GSC}/${projectId}/sites`)

export const setSite = (projectId, siteUrl) =>
  apiCall(`${GSC}/${projectId}/site`, "POST", { site_url: siteUrl })

export const syncData = (projectId, days = 90) =>
  apiCall(`${GSC}/${projectId}/sync`, "POST", { days })

export const processKeywords = (projectId, pillars = []) =>
  apiCall(`${GSC}/${projectId}/process`, "POST", { pillars })

export const getKeywords = (projectId, pillar = null) => {
  const params = pillar ? `?pillar=${encodeURIComponent(pillar)}` : ""
  return apiCall(`${GSC}/${projectId}/keywords${params}`)
}

export const getTop100 = (projectId) =>
  apiCall(`${GSC}/${projectId}/top100`)

export const getTree = (projectId) =>
  apiCall(`${GSC}/${projectId}/tree`)

// ── Project Intelligence Config ───────────────────────────────────────────────

export const generateConfig = (projectId, body) =>
  apiCall(`${GSC}/${projectId}/config/generate`, "POST", body)

export const getConfig = (projectId) =>
  apiCall(`${GSC}/${projectId}/config`)

export const updateConfig = (projectId, updates) =>
  apiCall(`${GSC}/${projectId}/config`, "PUT", updates)

// ── Phase 2: Intelligence Layer ───────────────────────────────────────────────

export const runIntelligence = (projectId, forceEmbeddings = false) =>
  apiCall(`${GSC}/${projectId}/intelligence/run`, "POST", { force_embeddings: forceEmbeddings })

export const getClusters = (projectId) =>
  apiCall(`${GSC}/${projectId}/clusters`)

export const getGraph = (projectId, minSimilarity = 0.3) =>
  apiCall(`${GSC}/${projectId}/graph?min_similarity=${minSimilarity}`)

export const getInsights = (projectId, type = null) => {
  const params = type ? `?type=${encodeURIComponent(type)}` : ""
  return apiCall(`${GSC}/${projectId}/insights${params}`)
}

export const getAuthority = (projectId) =>
  apiCall(`${GSC}/${projectId}/authority`)

// ── Phase 3: Product + Execution Layer ────────────────────────────────────────

export const validateKey = (apiKey) =>
  apiCall(`${GSC}/validate-key`, "POST", { api_key: apiKey })

export const getStageData = (projectId) =>
  apiCall(`${GSC}/${projectId}/stage-data`)

export const importFromStages = (projectId) =>
  apiCall(`${GSC}/${projectId}/import-stages`, "POST")

export const generateIntelligenceSummary = (projectId) =>
  apiCall(`${GSC}/${projectId}/intelligence-summary`, "POST")

export const getIntelligenceSummary = (projectId) =>
  apiCall(`${GSC}/${projectId}/intelligence-summary`)

export const getTasks = (projectId, status = null) => {
  const params = status ? `?status=${encodeURIComponent(status)}` : ""
  return apiCall(`${GSC}/${projectId}/tasks${params}`)
}

export const createTask = (projectId, task) =>
  apiCall(`${GSC}/${projectId}/tasks`, "POST", task)

export const updateTask = (projectId, taskId, updates) =>
  apiCall(`${GSC}/${projectId}/tasks/${taskId}`, "PUT", updates)

export const deleteTask = (projectId, taskId) =>
  apiCall(`${GSC}/${projectId}/tasks/${taskId}`, "DELETE")

export const exportData = (projectId, type = "full") =>
  apiCall(`${GSC}/${projectId}/export`, "POST", { type })

export const testConnection = (projectId) =>
  apiCall(`${GSC}/${projectId}/test-connection`)

export const searchKeyword = (projectId, query, days = 90, limit = 100) =>
  apiCall(`${GSC}/${projectId}/search`, "POST", { query, days, limit })

