/**
 * kw2 API helpers — all /api/kw2/ calls centralized.
 */
import apiCall from "../lib/apiCall"

const KW2 = "/api/kw2"

// ── Session ─────────────────────────────────────────────────────────────────

export const createSession = (projectId, provider = "auto", mode = "brand", name = "", seedKeywords = []) =>
  apiCall(`${KW2}/${projectId}/sessions`, "POST", { provider, mode, name, seed_keywords: seedKeywords })

export const getLatestSession = (projectId) =>
  apiCall(`${KW2}/${projectId}/sessions`)

export const getSession = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}`)

export const listSessions = (projectId) =>
  apiCall(`${KW2}/${projectId}/sessions/list`)

export const renameSession = (projectId, sessionId, name) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/name`, "PUT", { name })

export const importKeywords = (projectId, sessionId, { keywords = [], seeds = [], session_name = "" } = {}) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/import-keywords`, "POST", { keywords, seeds, session_name })

export const updatePhaseStatus = (projectId, sessionId, phase, status = "done") =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase-status`, "PATCH", { phase, status })

export const deleteSession = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}`, "DELETE")

export const bulkDeleteSessions = (projectId, ids) =>
  apiCall(`${KW2}/${projectId}/sessions/bulk-delete`, "POST", { ids })

// ── Phase 1: Business Analysis ──────────────────────────────────────────────

export const runPhase1 = (projectId, sessionId, manualInput) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase1`, "POST", manualInput)

/**
 * Phase 1 SSE streaming — POST body, receives real-time provider/progress events.
 * Returns a cancel function.
 */
export function runPhase1Stream(projectId, sessionId, body, onEvent) {
  let aborted = false
  const controller = new AbortController()

  async function start() {
    const API = import.meta.env.VITE_API_URL || ""
    // Get auth token
    let token = ""
    try {
      const res = await apiCall("/api/auth/stream-token", "POST")
      token = res?.stream_token || ""
    } catch {
      token = localStorage.getItem("annaseo_token") || ""
    }

    // Build auth headers
    const headers = { "Content-Type": "application/json" }
    if (token) headers["Authorization"] = `Bearer ${token}`

    let resp
    try {
      resp = await fetch(`${API}${KW2}/${projectId}/sessions/${sessionId}/phase1/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } catch (e) {
      if (!aborted) onEvent({ type: "error", message: e.message })
      return
    }

    if (!resp.ok) {
      const text = await resp.text().catch(() => resp.statusText)
      onEvent({ type: "error", message: `HTTP ${resp.status}: ${text}` })
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ""

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done || aborted) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop() // keep incomplete last line
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const ev = JSON.parse(line.slice(6))
              onEvent(ev)
              if (ev.type === "session_updated" || ev.type === "error") {
                reader.cancel()
                return
              }
            } catch { /* ignore malformed */ }
          }
        }
      }
    } catch (e) {
      if (!aborted) onEvent({ type: "error", message: e.message })
    }
  }

  start()
  return () => { aborted = true; controller.abort() }
}

export const getProfile = (projectId) =>
  apiCall(`${KW2}/${projectId}/profile`)

export const updateProfile = (projectId, patch) =>
  apiCall(`${KW2}/${projectId}/profile`, "PATCH", patch)

export const suggestFields = (projectId, context) =>
  apiCall(`${KW2}/${projectId}/suggest-fields`, "POST", context)

export const competitorCrawl = (projectId, sessionId, body) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/competitor-crawl`, "POST", body)

export const addToProfile = (projectId, sessionId, keywords, target = "pillars") =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/add-to-profile`, "POST", { keywords, target })

export const analyzeCompetitorKeywords = (projectId, sessionId, keywords) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/analyze-competitor-keywords`, "POST", { keywords })

export const runPillarAudit = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/pillar-audit`)

// ── Phase 2: Keyword Universe ───────────────────────────────────────────────

export const runPhase2 = (projectId, sessionId, confirmedPillars = [], confirmedModifiers = []) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase2`, "POST", {
    confirmed_pillars: confirmedPillars,
    confirmed_modifiers: confirmedModifiers,
  })

export const getUniverse = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/universe`)

export function streamPhase2(projectId, sessionId, onEvent, confirmedPillars = [], confirmedModifiers = [], reset = false) {
  const params = new URLSearchParams()
  if (confirmedPillars.length) params.set("confirmed_pillars", confirmedPillars.join(","))
  if (confirmedModifiers.length) params.set("confirmed_modifiers", confirmedModifiers.join(","))
  if (reset) params.set("reset", "true")
  const qs = params.toString() ? `?${params.toString()}` : ""
  return _streamSSE(`${KW2}/${projectId}/sessions/${sessionId}/phase2/stream${qs}`, onEvent)
}

// ── Business README (Analyze + BI synthesis) ───────────────────────────────

export const getBusinessReadme = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/business-readme`)

export const generateBusinessReadme = (projectId, sessionId, force = false) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/business-readme`, "POST", { force })

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
    pillar_quotas: config.pillarQuotas || {},
    use_strategy_ideas: config.useStrategyIdeas || false,
  })

export const getCalendar = (projectId, sessionId, pillar = null) => {
  const qs = pillar ? `?pillar=${encodeURIComponent(pillar)}` : ""
  return apiCall(`${KW2}/${projectId}/sessions/${sessionId}/calendar${qs}`)
}

export const rebuildCalendar = (projectId, sessionId, startDate) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/calendar/rebuild`, "POST", { start_date: startDate || null })

export const getCalendarSummary = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/calendar/summary`)

// ── Phase 9: Strategy ───────────────────────────────────────────────────────

export const runPhase9 = (projectId, sessionId, contentParams = null, signal = null) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/phase9`, "POST", contentParams || {}, signal)

export const getStrategy = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/strategy`)

export const getSessionAiUsage = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/ai-usage`)

export const getBizContextPreview = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/biz-context-preview`)

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

export const rejectKeywords = (projectId, sessionId, ids) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/keywords/reject`, "POST", { ids })

export const addKeyword = (projectId, sessionId, body) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/validated/add`, "POST", body)

export const getPillarStats = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/pillar-stats`)

// ── Business Intelligence Stage ──────────────────────────────────────────────

export const getBizIntel = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/biz-intel`)

export const saveBizProfile = (projectId, sessionId, body) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/biz-intel/profile`, "POST", body)

export const addBizCompetitor = (projectId, sessionId, domain) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/biz-intel/competitor`, "POST", { domain })

export const removeBizCompetitor = (projectId, sessionId, compId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/biz-intel/competitor/${compId}`, "DELETE")

export const runBizIntelAll = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/biz-intel/run-all`, "POST")

export const getBizIntelProgress = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/biz-intel/progress`)

export function streamBizWebsiteCrawl(projectId, sessionId, onEvent) {
  return _streamSSE(`${KW2}/${projectId}/sessions/${sessionId}/biz-intel/crawl-website/stream`, onEvent)
}

export function streamBizCompetitorCrawl(projectId, sessionId, onEvent) {
  return _streamSSE(`${KW2}/${projectId}/sessions/${sessionId}/biz-intel/crawl-competitors/stream`, onEvent)
}

export function streamBizStrategy(projectId, sessionId, onEvent) {
  return _streamSSE(`${KW2}/${projectId}/sessions/${sessionId}/biz-intel/strategy/stream`, onEvent)
}

// ── DAG Engine ──────────────────────────────────────────────────────────────

export const getDagState = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/dag`)

export const getDagOrder = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/dag/order`)

export const runDagPhase = (projectId, sessionId, phaseId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/dag/run/${phaseId}`, "POST")

export const approveDagGate = (projectId, sessionId, phaseId, body = {}) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/dag/approve/${phaseId}`, "POST", body)

// ── v2 Expand ───────────────────────────────────────────────────────────────

export const v2Expand = (projectId, sessionId, body = {}) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/expand`, "POST", body)

export function v2ExpandStream(projectId, sessionId, onEvent, { competitorUrls = [], aiProvider = "auto" } = {}) {
  const qs = new URLSearchParams()
  if (competitorUrls.length) qs.set("competitor_urls", competitorUrls.join(","))
  if (aiProvider) qs.set("ai_provider", aiProvider)
  const q = qs.toString()
  return _streamSSE(`${KW2}/${projectId}/sessions/${sessionId}/expand/stream${q ? "?" + q : ""}`, onEvent)
}

export const v2ExpandClusters = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/expand/clusters`)

export const v2ExpandReview = (projectId, sessionId, approved = [], rejected = []) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/expand/review`, "POST", {
    approved_cluster_ids: approved,
    rejected_cluster_ids: rejected,
  })

export const v2AddKeyword = (projectId, sessionId, keyword, pillars = []) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/expand/keyword`, "POST", { keyword, pillars })

export const v2MoveKeywordPillar = (projectId, sessionId, keywordId, pillars) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/expand/keyword/${keywordId}/pillars`, "PUT", { pillars })

// ── v2 Bulk CRUD ────────────────────────────────────────────────────────────

export const v2ListKeywords = (projectId, sessionId, params = {}) => {
  const qs = new URLSearchParams(params).toString()
  return apiCall(`${KW2}/${projectId}/sessions/${sessionId}/keywords${qs ? "?" + qs : ""}`)
}

export const v2BulkUpdate = (projectId, sessionId, ids, fields) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/keywords/bulk-update`, "PUT", { ids, fields })

export const v2BulkDelete = (projectId, sessionId, ids) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/keywords/bulk-delete`, "DELETE", { ids })

export const v2BulkApprove = (projectId, sessionId, ids, action, rejectReason = "") =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/keywords/bulk-approve`, "POST", { ids, action, reject_reason: rejectReason })

// ── v2 Organize ─────────────────────────────────────────────────────────────

export const v2Organize = (projectId, sessionId, body = {}) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/organize`, "POST", body)

export function v2OrganizeStream(projectId, sessionId, onEvent, aiProvider = "auto") {
  const qs = aiProvider ? `?ai_provider=${encodeURIComponent(aiProvider)}` : ""
  return _streamSSE(`${KW2}/${projectId}/sessions/${sessionId}/organize/stream${qs}`, onEvent)
}

export const v2Graph = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/organize/graph`)

export const v2Top100 = (projectId, sessionId, pillar = null) => {
  const qs = pillar ? `?pillar=${encodeURIComponent(pillar)}` : ""
  return apiCall(`${KW2}/${projectId}/sessions/${sessionId}/organize/top100${qs}`)
}

export const v2OrganizeSummary = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/organize/summary`)

// ── v2 Apply ────────────────────────────────────────────────────────────────

export const v2Apply = (projectId, sessionId, body = {}) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/apply`, "POST", body)

export function v2ApplyStream(projectId, sessionId, onEvent, opts = {}) {
  const qs = new URLSearchParams()
  if (opts.aiProvider) qs.set("ai_provider", opts.aiProvider)
  if (opts.blogsPerWeek) qs.set("blogs_per_week", opts.blogsPerWeek)
  if (opts.durationWeeks) qs.set("duration_weeks", opts.durationWeeks)
  if (opts.startDate) qs.set("start_date", opts.startDate)
  const q = qs.toString()
  return _streamSSE(`${KW2}/${projectId}/sessions/${sessionId}/apply/stream${q ? "?" + q : ""}`, onEvent)
}

export const v2Links = (projectId, sessionId, linkType = null) => {
  const qs = linkType ? `?link_type=${encodeURIComponent(linkType)}` : ""
  return apiCall(`${KW2}/${projectId}/sessions/${sessionId}/apply/links${qs}`)
}

export const v2Calendar = (projectId, sessionId, pillar = null) => {
  const qs = pillar ? `?pillar=${encodeURIComponent(pillar)}` : ""
  return apiCall(`${KW2}/${projectId}/sessions/${sessionId}/apply/calendar${qs}`)
}

export const v2UpdateCalendar = (projectId, sessionId, entryId, body) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/apply/calendar/${entryId}`, "PUT", body)

export const v2Strategy = (projectId, sessionId) =>
  apiCall(`${KW2}/${projectId}/sessions/${sessionId}/apply/strategy`)

// ── Strategy v2 Versioning ────────────────────────────────────────────────────

export const listStrategyVersions = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/strategy/versions`)

export const getStrategyVersion = (pid, sid, versionId) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/strategy/versions/${versionId}`)

export const activateStrategyVersion = (pid, sid, versionId) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/strategy/activate/${versionId}`, "POST")

export const saveStrategyEdit = (pid, sid, field, value, versionId = null) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/strategy/edit`, "PATCH", { field, value, version_id: versionId })

// ── Intelligence Questions ────────────────────────────────────────────────────

export const runQuestions = (pid, sid, body = {}) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/questions/run`, "POST", body)

export const enrichQuestions = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/questions/enrich`, "POST")

export const listQuestions = (pid, sid, params = {}) => {
  const qs = new URLSearchParams(params).toString()
  return apiCall(`${KW2}/${pid}/sessions/${sid}/questions${qs ? "?" + qs : ""}`)
}

export const getQuestionSummary = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/questions/summary`)

export const deleteQuestion = (pid, sid, questionId) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/questions/${questionId}`, "DELETE")

// ── Expansion Engine ──────────────────────────────────────────────────────────

export const discoverDimensions = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/expansion/discover-dimensions`, "POST")

export const runExpansion = (pid, sid, body = {}) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/expansion/run`, "POST", body)

export const getExpansionConfig = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/expansion/config`)

// ── Dedup + Clustering ────────────────────────────────────────────────────────

export const runDedup = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/dedup/run`, "POST")

export const runClustering = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/dedup/cluster`, "POST")

export const listClusters = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/dedup/clusters`)

// ── Scoring ───────────────────────────────────────────────────────────────────

export const runScoring = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/scoring/run`, "POST")

export const getScoringConfig = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/scoring/config`)

export const updateScoringConfig = (pid, sid, weights) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/scoring/config`, "PATCH", { weights })

export const getRankedQuestions = (pid, sid, params = {}) => {
  const qs = new URLSearchParams(params).toString()
  return apiCall(`${KW2}/${pid}/sessions/${sid}/scoring/ranked${qs ? "?" + qs : ""}`)
}

// ── Selection ─────────────────────────────────────────────────────────────────

export const runSelection = (pid, sid, body = {}) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/selection/run`, "POST", body)

export const listSelected = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/selection/list`)

export const includeQuestion = (pid, sid, questionId) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/selection/include/${questionId}`, "POST")

export const removeSelected = (pid, sid, questionId) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/selection/${questionId}`, "DELETE")

// ── Pipeline status ───────────────────────────────────────────────────────────

export const getPipelineStatus = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/pipeline/status`)

export const generateForPillar = (pid, sid, body = {}) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/intelligence/generate-for-pillar`, "POST", body)

export const getExpansionSeeds = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/expansion/seeds`)

export const expandOneSeed = (pid, sid, body = {}) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/expansion/expand-seed`, "POST", body)

// ── Content Titles ────────────────────────────────────────────────────────────

export const generateTitles = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/content-titles/generate`, "POST")

export const listTitles = (pid, sid, params = {}) => {
  const qs = new URLSearchParams(params).toString()
  return apiCall(`${KW2}/${pid}/sessions/${sid}/content-titles${qs ? "?" + qs : ""}`)
}

export const getTitleStats = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/content-titles/stats`)

export const updateTitle = (pid, sid, titleId, body) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/content-titles/${titleId}`, "PATCH", body)

// ── Prompts ───────────────────────────────────────────────────────────────────

export const listPrompts = () =>
  apiCall(`${KW2}/prompts`)

export const getPromptDetail = (key) =>
  apiCall(`${KW2}/prompts/${key}`)

export const updatePrompt = (key, template) =>
  apiCall(`${KW2}/prompts/${key}`, "PATCH", { template })

export const getPromptVersions = (key) =>
  apiCall(`${KW2}/prompts/${key}/versions`)

export const restorePromptVersion = (key, versionNumber) =>
  apiCall(`${KW2}/prompts/${key}/restore/${versionNumber}`, "POST")

export const getPromptSampleData = (key) =>
  apiCall(`${KW2}/prompts/${key}/sample-data`)

export const testPrompt = (promptKey, template, provider = "ollama", sampleData = null) =>
  apiCall(`${KW2}/prompts/test`, "POST", { prompt_key: promptKey, template, provider, sample_data: sampleData })

// ── Performance / Feedback ────────────────────────────────────────────────────

export const recordPerformance = (pid, sid, body) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/performance/record`, "POST", body)

export const getPerformanceSummary = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/performance/summary`)

export const listPerformance = (pid, sid, limit = 100) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/performance?limit=${limit}`)

export const applyLearnings = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/performance/apply-learnings`, "POST")

// ── Learning Engine (Phase 12 — Pattern Memory + ROI + Decisions) ────────────

export const recordPerformanceV2 = (pid, sid, body) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/performance/record-v2`, "POST", body)

export const runLearning = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/learning/run`, "POST")

export const getLearningPatterns = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/learning/patterns`)

export const getLearningROI = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/learning/roi`)

export const getLearningDecisions = (pid, sid, entityType = null) => {
  const qs = entityType ? `?entity_type=${entityType}` : ""
  return apiCall(`${KW2}/${pid}/sessions/${sid}/learning/decisions${qs}`)
}

export const overrideDecision = (pid, sid, body) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/learning/decisions/override`, "POST", body)

export const getLearningStrategyState = (pid, sid) =>
  apiCall(`${KW2}/${pid}/sessions/${sid}/learning/strategy-state`)



/** Obtain a short-lived stream token from the backend so we never
 *  put the long-lived JWT into a URL query string (B29). */
async function _getStreamToken() {
  try {
    const res = await apiCall("/api/auth/stream-token", "POST")
    return res?.stream_token || ""
  } catch {
    // Fallback: if endpoint doesn't exist yet, degrade to legacy behaviour
    return localStorage.getItem("annaseo_token") || ""
  }
}

const _SSE_MAX_RETRIES = 3
const _SSE_RETRY_DELAY = 2000 // ms

function _streamSSE(path, onEvent) {
  let retries = 0
  let closed = false
  let es = null

  async function connect() {
    const API = import.meta.env.VITE_API_URL || ""
    const streamToken = await _getStreamToken()
    const url = `${API}${path}`
    const fullUrl = `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(streamToken)}`

    es = new EventSource(fullUrl)

    es.onmessage = (e) => {
      retries = 0 // reset on successful message
      try {
        const data = JSON.parse(e.data)
        onEvent(data)
        if (data.done) { closed = true; es.close() }
      } catch (err) {
        if (typeof window._kw2pushLog === "function") {
          window._kw2pushLog(`[SSE] Parse error: ${err.message} — raw: ${String(e.data).slice(0, 100)}`, { badge: "SSE", type: "error" })
        }
      }
    }

    es.onerror = () => {
      es.close()
      if (closed) return
      if (retries < _SSE_MAX_RETRIES) {
        retries++
        if (typeof window._kw2pushLog === "function") {
          window._kw2pushLog(`[SSE] Connection lost on ${path} — retry ${retries}/${_SSE_MAX_RETRIES}`, { badge: "SSE", type: "warn" })
        }
        setTimeout(connect, _SSE_RETRY_DELAY * retries)
      } else {
        if (typeof window._kw2pushLog === "function") {
          window._kw2pushLog(`[SSE] Connection failed on ${path} after ${_SSE_MAX_RETRIES} retries`, { badge: "SSE", type: "error" })
        }
        onEvent({ error: true, done: true, message: "SSE connection failed after retries" })
      }
    }
  }

  connect()
  return () => { closed = true; if (es) es.close() }
}
