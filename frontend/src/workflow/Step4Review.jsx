// Step 4 — Keyword Review (card view, log at top, working filters)

import { useState, useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNotification } from "../store/notification"
import useWorkflowContext from "../store/workflowContext"
import { apiCall, T, Card, Btn, Spinner, LiveConsole, intentColor } from "./shared"

// ── Per-pillar keyword card ────────────────────────────────────────────────
function PillarCard({ projectId, sessionId, pillar, intentFilter, sortBy, onLog, onRefreshSummary }) {
  const qc = useQueryClient()
  const notify = useNotification(s => s.notify)
  const [expanded, setExpanded] = useState(false)
  const [working, setWorking] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["ki-pillar-kws", projectId, sessionId, pillar.pillar, intentFilter, sortBy],
    queryFn: () => {
      const p = new URLSearchParams({ limit: 200, offset: 0, sort_by: sortBy, pillar: pillar.pillar })
      if (intentFilter !== "all") p.set("intent", intentFilter)
      return apiCall(`/api/ki/${projectId}/review/${sessionId}?${p}`)
    },
    enabled: expanded,
    refetchInterval: false,
  })

  const keywords = data?.keywords || []

  const refreshAll = () => {
    refetch()
    onRefreshSummary()
  }

  const doAction = async (item_id, action) => {
    try {
      await apiCall(`/api/ki/${projectId}/review/${sessionId}/action`, "POST",
        { keyword_id: item_id, action })
      refreshAll()
    } catch (e) { notify("Action failed: " + e.message, "error") }
  }

  const acceptAll = async () => {
    setWorking(true)
    try {
      const r = await apiCall(`/api/ki/${projectId}/review/${sessionId}/accept-all`, "POST",
        { pillar: pillar.pillar })
      onLog(`"${pillar.pillar}": ${r.accepted} keywords accepted`, "success")
      refreshAll()
    } catch (e) { onLog("Accept failed: " + e.message, "error") }
    finally { setWorking(false) }
  }

  const rejectAll = async () => {
    setWorking(true)
    try {
      const r = await apiCall(`/api/ki/${projectId}/review/${sessionId}/bulk-action`, "POST",
        { action: "reject", pillar: pillar.pillar })
      onLog(`"${pillar.pillar}": ${r.affected} keywords rejected`, "success")
      refreshAll()
    } catch (e) { onLog("Reject failed: " + e.message, "error") }
    finally { setWorking(false) }
  }

  const acceptedPct = pillar.total > 0 ? Math.round((pillar.accepted / pillar.total) * 100) : 0
  const pendingCount = pillar.pending || 0

  return (
    <div style={{
      border: `1px solid ${T.border}`, borderRadius: 10, marginBottom: 10, overflow: "hidden",
      background: "#fff",
    }}>
      {/* Card header */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
        background: pillar.accepted === pillar.total && pillar.total > 0 ? "#f0fdf4" : "#fafafa",
        cursor: "pointer", userSelect: "none",
      }} onClick={() => setExpanded(e => !e)}>
        <span style={{ fontSize: 16, color: T.textSoft, lineHeight: 1 }}>{expanded ? "▾" : "▸"}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 13, textTransform: "capitalize" }}>
            {pillar.pillar}
          </div>
          <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2, display: "flex", gap: 10 }}>
            <span>Total: <strong>{pillar.total}</strong></span>
            <span style={{ color: "#065f46" }}>✓ {pillar.accepted}</span>
            {pillar.rejected > 0 && <span style={{ color: "#991b1b" }}>✗ {pillar.rejected}</span>}
            {pendingCount > 0 && <span style={{ color: T.amber }}>⏳ {pendingCount}</span>}
            <span style={{ color: T.textSoft }}>avg score: {pillar.avg_opp_score ?? "—"}</span>
          </div>
        </div>
        {/* Progress bar */}
        <div style={{ width: 80, height: 6, background: T.grayLight, borderRadius: 3, flexShrink: 0 }}>
          <div style={{
            height: "100%", borderRadius: 3, background: acceptedPct === 100 ? T.green : T.purple,
            width: `${acceptedPct}%`, transition: "width 0.3s",
          }} />
        </div>
        <span style={{ fontSize: 11, color: T.textSoft, width: 32, textAlign: "right" }}>{acceptedPct}%</span>
        {/* Action buttons (stop propagation so they don't toggle expand) */}
        <div style={{ display: "flex", gap: 6 }} onClick={e => e.stopPropagation()}>
          {pendingCount > 0 && (
            <Btn small variant="teal" onClick={acceptAll} disabled={working}>
              {working ? "…" : `✓ All (${pendingCount})`}
            </Btn>
          )}
          {pillar.accepted > 0 && (
            <Btn small variant="danger" onClick={rejectAll} disabled={working}>
              ✗ All
            </Btn>
          )}
        </div>
      </div>

      {/* Card body */}
      {expanded && (
        <div style={{ padding: "8px 14px 12px", borderTop: `1px solid ${T.border}` }}>
          {isLoading && <div style={{ padding: 12, textAlign: "center" }}><Spinner /></div>}
          {!isLoading && keywords.length === 0 && (
            <div style={{ fontSize: 12, color: T.textSoft, padding: "8px 0" }}>
              No keywords match the current filter.
            </div>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {keywords.map(kw => {
              const score = kw.opportunity_score ?? kw.final_score
              const scoreColor = score >= 75 ? "#065f46" : score >= 50 ? "#92400e" : "#991b1b"
              const scoreBg   = score >= 75 ? "#d1fae5" : score >= 50 ? "#fef3c7" : "#fee2e2"
              const isAcc = kw.status === "accepted"
              const isRej = kw.status === "rejected"
              return (
                <div key={kw.item_id} style={{
                  display: "flex", alignItems: "center", gap: 5,
                  padding: "4px 8px", borderRadius: 20, fontSize: 11, border: `1px solid ${T.border}`,
                  background: isAcc ? "#f0fdf4" : isRej ? "#fff7f7" : "#fff",
                }}>
                  <span style={{ fontWeight: 500, color: T.text }}>{kw.edited_keyword || kw.keyword}</span>
                  {kw.intent && (
                    <span style={{
                      fontSize: 10, padding: "1px 4px", borderRadius: 3,
                      background: intentColor(kw.intent) + "22", color: intentColor(kw.intent),
                    }}>{kw.intent[0].toUpperCase()}</span>
                  )}
                  {score != null && (
                    <span style={{ fontSize: 10, padding: "1px 4px", borderRadius: 3, background: scoreBg, color: scoreColor, fontWeight: 600 }}>
                      {score}
                    </span>
                  )}
                  <button
                    onClick={() => doAction(kw.item_id, isAcc ? "reject" : "accept")}
                    title={isAcc ? "Click to reject" : "Click to accept"}
                    style={{
                      border: "none", borderRadius: "50%", width: 18, height: 18, cursor: "pointer",
                      fontSize: 10, display: "flex", alignItems: "center", justifyContent: "center",
                      background: isAcc ? "#d1fae5" : isRej ? "#fee2e2" : T.grayLight,
                      color: isAcc ? "#065f46" : isRej ? "#991b1b" : T.textSoft,
                    }}>
                    {isAcc ? "✓" : isRej ? "✗" : "○"}
                  </button>
                </div>
              )
            })}
          </div>
          {data?.total > 200 && (
            <div style={{ fontSize: 11, color: T.textSoft, marginTop: 8 }}>
              Showing 200 of {data.total} keywords — use pillar accept-all to accept remaining.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main Step 4 ──────────────────────────────────────────────────────────────
export default function Step4Review({ projectId, onComplete, onBack }) {
  const notify = useNotification(s => s.notify)
  const ctx = useWorkflowContext()
  const queryClient = useQueryClient()

  const sessionId = ctx.sessionId

  const [intentFilter, setIntentFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [sortBy, setSortBy] = useState("opp_desc")
  const [search, setSearch] = useState("")
  const [reviewLogs, setReviewLogs] = useState([])
  const [scoreJobId, setScoreJobId] = useState(null)
  const [scoreProgress, setScoreProgress] = useState(null)

  const addLog = (msg, level = "info") =>
    setReviewLogs(prev => [...prev.slice(-299), { msg, level }])

  // ── Pillar summary ─────────────────────────────────────────────────────────
  const { data: pillarData, refetch: refetchPillars } = useQuery({
    queryKey: ["ki-pillars-summary", projectId, sessionId],
    queryFn: () => apiCall(`/api/ki/${projectId}/universe/${sessionId}/by-pillar`),
    enabled: !!sessionId,
    refetchInterval: false,
  })

  // ── Global stats (1-row query) ──────────────────────────────────────────────
  const { data: statsData, refetch: refetchStats } = useQuery({
    queryKey: ["ki-global-stats", projectId, sessionId],
    queryFn: () => apiCall(`/api/ki/${projectId}/review/${sessionId}?limit=1&offset=0`),
    enabled: !!sessionId,
    refetchInterval: false,
  })

  const refetchSummary = () => {
    refetchPillars()
    refetchStats()
  }

  // ── Score job polling ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!scoreJobId) return
    const iv = setInterval(async () => {
      try {
        const r = await apiCall(`/api/ki/${projectId}/score/${sessionId}/${scoreJobId}`)
        setScoreProgress({ scored: r.scored, total: r.total, status: r.status })
        if (r.status === "completed" || r.status === "failed") {
          clearInterval(iv)
          setScoreJobId(null)
          refetchSummary()
          queryClient.invalidateQueries(["ki-pillar-kws"])
          if (r.status === "completed") {
            addLog("Scoring complete — scores updated", "success")
            notify("Scoring complete", "success")
          } else {
            addLog("Scoring failed", "error")
          }
        }
      } catch (e) {
        clearInterval(iv)
        addLog("Score poll error: " + (e?.message || ""), "error")
      }
    }, 2000)
    return () => clearInterval(iv)
  }, [scoreJobId])

  const startScoring = async () => {
    addLog("Starting scoring job…", "info")
    try {
      const r = await apiCall(`/api/ki/${projectId}/score/${sessionId}`, "POST", {})
      setScoreJobId(r.job_id)
      setScoreProgress({ scored: 0, total: r.total, status: "running" })
      addLog(`Scoring ${r.total} keywords…`, "info")
      notify("Scoring started", "info")
    } catch (e) {
      addLog("Score start failed: " + (e?.message || ""), "error")
      notify("Score failed: " + (e?.message || ""), "error")
    }
  }

  const acceptAllGlobal = async () => {
    addLog("Accepting all pending keywords…", "info")
    try {
      const r = await apiCall(`/api/ki/${projectId}/review/${sessionId}/accept-all`, "POST", {})
      refetchSummary()
      queryClient.invalidateQueries(["ki-pillar-kws"])
      addLog(`${r.accepted} keywords accepted`, "success")
      notify(`${r.accepted} keywords accepted`, "success")
    } catch (e) {
      addLog("Accept-all failed: " + (e?.message || ""), "error")
    }
  }

  // ── Derived ────────────────────────────────────────────────────────────────
  const stats = statsData?.stats || {}
  const totalCount   = stats.total   || 0
  const acceptedCount = stats.accepted || 0
  const rejectedCount = stats.rejected || 0
  const pendingCount  = stats.pending  || 0
  const canRunPipeline = acceptedCount >= 5

  // Filter pillar list by status + search
  let pillars = pillarData?.pillars || []
  if (search.trim()) {
    const q = search.toLowerCase()
    pillars = pillars.filter(p => p.pillar?.toLowerCase().includes(q))
  }
  if (statusFilter === "pending") pillars = pillars.filter(p => (p.pending || 0) > 0)
  if (statusFilter === "accepted") pillars = pillars.filter(p => (p.accepted || 0) > 0)
  if (statusFilter === "rejected") pillars = pillars.filter(p => (p.rejected || 0) > 0)
  if (statusFilter === "incomplete") pillars = pillars.filter(p => (p.accepted || 0) < p.total)

  const INTENTS = ["all","transactional","informational","commercial","comparison","local"]
  const intentChipColor = { all: T.textSoft, transactional: "#007AFF", informational: "#0ea5e9", commercial: "#f59e0b", comparison: "#10b981", local: "#ef4444" }

  if (!sessionId) {
    return (
      <Card>
        <div style={{ fontSize: 14, color: T.gray, textAlign: "center", padding: 30 }}>
          No session — complete Steps 1–2 first.
        </div>
        <div style={{ display: "flex", justifyContent: "center", marginTop: 12 }}>
          <Btn onClick={onBack}>← Back</Btn>
        </div>
      </Card>
    )
  }

  return (
    <div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <Card>
        {/* ── Header ── */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>Step 4 — Keyword Review</div>
            <div style={{ fontSize: 12, color: T.textSoft }}>
              Review and accept keywords. Pipeline uses accepted keywords only.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <Btn onClick={onBack} small>← Back</Btn>
            <Btn onClick={startScoring} small disabled={!!scoreJobId}>
              {scoreJobId ? "Scoring…" : "Score Keywords"}
            </Btn>
            <Btn variant="primary" onClick={acceptAllGlobal} small>Accept All Pending</Btn>
            {canRunPipeline && onComplete && (
              <Btn variant="teal" onClick={onComplete}>
                Next: Pipeline ({acceptedCount} accepted) →
              </Btn>
            )}
          </div>
        </div>

        {/* ── REVIEW LOG — moved to top ── */}
        <LiveConsole logs={reviewLogs} running={!!scoreJobId} maxHeight={120} title="REVIEW LOG" />

        {/* ── Score progress ── */}
        {scoreProgress && (
          <div style={{ margin: "8px 0", padding: "8px 12px", background: "#eff6ff", borderRadius: 8, fontSize: 12 }}>
            <strong>Scoring:</strong> {scoreProgress.scored}/{scoreProgress.total} — {scoreProgress.status}
            {scoreProgress.status === "running" && (
              <div style={{ marginTop: 4, height: 4, borderRadius: 2, background: "#dbeafe", overflow: "hidden" }}>
                <div style={{
                  height: "100%", background: T.purple, transition: "width 0.3s",
                  width: `${scoreProgress.total ? (scoreProgress.scored / scoreProgress.total) * 100 : 0}%`,
                }} />
              </div>
            )}
          </div>
        )}

        {/* ── Stats bar ── */}
        <div style={{
          display: "flex", gap: 16, margin: "8px 0 12px", padding: "8px 12px",
          background: T.grayLight, borderRadius: 8, fontSize: 12, flexWrap: "wrap",
        }}>
          <span>Total: <strong>{totalCount}</strong></span>
          <span style={{ color: "#065f46" }}>✓ Accepted: <strong>{acceptedCount}</strong></span>
          <span style={{ color: "#991b1b" }}>✗ Rejected: <strong>{rejectedCount}</strong></span>
          <span style={{ color: T.amber }}>⏳ Pending: <strong>{pendingCount}</strong></span>
          <span style={{ color: T.textSoft }}>Pillars: <strong>{pillarData?.pillars?.length || 0}</strong></span>
        </div>

        {/* ── Filters ── */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
          {/* Search pillar */}
          <input
            placeholder="Search pillar…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12, width: 160 }}
          />

          {/* Status filter */}
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            style={{ padding: "5px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12 }}>
            <option value="all">All Pillars</option>
            <option value="incomplete">Incomplete (has pending)</option>
            <option value="pending">Has Pending</option>
            <option value="accepted">Has Accepted</option>
            <option value="rejected">Has Rejected</option>
          </select>

          {/* Sort */}
          <select value={sortBy} onChange={e => setSortBy(e.target.value)}
            style={{ padding: "5px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12 }}>
            <option value="opp_desc">Opportunity ↓</option>
            <option value="score_desc">Score ↓</option>
            <option value="volume_desc">Volume ↓</option>
            <option value="alpha">A → Z</option>
          </select>

          {/* Intent chips */}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {INTENTS.map(intent => (
              <button key={intent} onClick={() => setIntentFilter(intent)} style={{
                padding: "4px 10px", borderRadius: 20, fontSize: 11, cursor: "pointer",
                border: `1px solid ${intentFilter === intent ? intentChipColor[intent] : T.border}`,
                background: intentFilter === intent ? intentChipColor[intent] + "18" : "#fff",
                color: intentFilter === intent ? intentChipColor[intent] : T.textSoft,
                fontWeight: intentFilter === intent ? 600 : 400,
              }}>
                {intent === "all" ? "All Intents" : intent}
              </button>
            ))}
          </div>
        </div>

        {/* ── Pillar cards ── */}
        <div>
          {!pillarData && (
            <div style={{ textAlign: "center", padding: 24 }}><Spinner /></div>
          )}
          {pillars.length === 0 && pillarData && (
            <div style={{ fontSize: 13, color: T.textSoft, textAlign: "center", padding: 20 }}>
              No pillars match current filters.
            </div>
          )}
          {pillars.map(p => (
            <PillarCard
              key={p.pillar}
              projectId={projectId}
              sessionId={sessionId}
              pillar={p}
              intentFilter={intentFilter}
              sortBy={sortBy}
              onLog={addLog}
              onRefreshSummary={refetchSummary}
            />
          ))}
        </div>
      </Card>
    </div>
  )
}
