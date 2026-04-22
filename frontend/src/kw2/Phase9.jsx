/**
 * Phase 9 — Strategy Generation.
 * AI-powered SEO strategy based on full pipeline results.
 */
import React, { useCallback, useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, usePhaseRunner, PhaseResult, NotificationList } from "./shared"

export default function Phase9({ projectId, sessionId, onComplete, autoRun, hideRunButton }) {
  const { strategy, setStrategy } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P9")
  const qc = useQueryClient()

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    log("Generating SEO strategy (AI)...", "info")
    try {
      const data = await api.runPhase9(projectId, sessionId)
      setStrategy(data.strategy)
      log("SEO strategy generated successfully", "success")
      toast("SEO strategy generated!", "success")
      // Invalidate Strategy Hub cache so it immediately reflects the new strategy
      qc.invalidateQueries({ queryKey: ["kw2-strategy-sessions", projectId] })
      qc.invalidateQueries({ queryKey: ["kw2-session-strategy", projectId, sessionId] })
      onComplete()
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
      toast(`Phase 9 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  useEffect(() => {
    async function load() {
      try {
        const data = await api.getStrategy(projectId, sessionId)
        if (data.strategy) setStrategy(data.strategy)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  useEffect(() => { if (autoRun) run() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card title="Phase 9: SEO Strategy" actions={hideRunButton ? null : <RunButton onClick={run} loading={loading}>Generate Strategy</RunButton>}>
      {error && <p style={{ color: "#dc2626", fontSize: 13 }}>{error}</p>}

      {strategy && (
        <div style={{ fontSize: 13 }}>
          {strategy.strategy_summary && (
            <div style={{ marginBottom: 16, padding: 12, background: "#f0fdf4", borderRadius: 6 }}>
              <h4 style={{ margin: "0 0 4px", fontSize: 14 }}>{strategy.strategy_summary.headline}</h4>
              {strategy.strategy_summary.biggest_opportunity && (
                <p style={{ margin: "4px 0", color: "#166534" }}><strong>Opportunity:</strong> {strategy.strategy_summary.biggest_opportunity}</p>
              )}
              {strategy.strategy_summary.why_we_win && (
                <p style={{ margin: "4px 0", color: "#166534" }}><strong>Advantage:</strong> {strategy.strategy_summary.why_we_win}</p>
              )}
            </div>
          )}

          {strategy.executive_summary && !strategy.strategy_summary && (
            <div style={{ marginBottom: 16, padding: 12, background: "#f0fdf4", borderRadius: 6 }}>
              <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{strategy.executive_summary}</p>
            </div>
          )}

          {strategy.priority_pillars?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Priority Pillars</h4>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {strategy.priority_pillars.map((p, i) => {
                  const label = typeof p === "string" ? p : p.pillar || p.name || JSON.stringify(p)
                  return (
                    <Badge key={i} color={i === 0 ? "green" : "blue"}>{i + 1}. {label}</Badge>
                  )
                })}
              </div>
            </div>
          )}

          {strategy.quick_wins?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Quick Wins</h4>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {strategy.quick_wins.map((kw, i) => (
                  <li key={i} style={{ fontSize: 12, color: "#374151" }}>{typeof kw === "string" ? kw : kw.keyword || kw.title}</li>
                ))}
              </ul>
            </div>
          )}

          {strategy.content_gaps?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Content Gaps</h4>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {strategy.content_gaps.map((g, i) => <li key={i} style={{ fontSize: 12, color: "#374151" }}>{typeof g === "string" ? g : g.topic || g.gap || g.title || ""}</li>)}
              </ul>
            </div>
          )}

          {strategy.weekly_plan?.length > 0 && (
            <div>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Weekly Plan</h4>
              <div style={{ maxHeight: 300, overflow: "auto" }}>
                {strategy.weekly_plan.slice(0, 12).map((week) => (
                  <div key={week.week} style={{ marginBottom: 8, padding: 8, background: "#f9fafb", borderRadius: 4 }}>
                    <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 4 }}>
                      Week {week.week} — <Badge color="blue">{week.focus_pillar}</Badge>
                    </div>
                    {(week.articles || []).map((a, i) => (
                      <div key={i} style={{ fontSize: 12, color: "#374151", marginLeft: 12 }}>
                        • {typeof a === "string" ? a : a.title || a.keyword || JSON.stringify(a)} {a.primary_keyword ? <span style={{ color: "#9ca3af" }}>({a.primary_keyword})</span> : null}
                      </div>
                    ))}
                  </div>
                ))}
                {strategy.weekly_plan.length > 12 && (
                  <p style={{ color: "#9ca3af", fontSize: 11 }}>Showing 12 of {strategy.weekly_plan.length} weeks</p>
                )}
              </div>
            </div>
          )}

          <PhaseResult
            phaseNum={9}
            stats={[
              { label: "Pillars", value: strategy.priority_pillars?.length || 0, color: "#3b82f6" },
              { label: "Quick Wins", value: strategy.quick_wins?.length || 0, color: "#10b981" },
              { label: "Weeks Planned", value: strategy.weekly_plan?.length || 0, color: "#8b5cf6" },
            ]}
          />
        </div>
      )}

      <NotificationList notifications={notifications} />
    </Card>
  )
}
