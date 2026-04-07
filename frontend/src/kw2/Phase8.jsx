/**
 * Phase 8 — Content Calendar.
 */
import React, { useState, useCallback, useEffect } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, StatsRow, usePhaseRunner, PhaseResult, NotificationList, ConsolePanel } from "./shared"

export default function Phase8({ projectId, sessionId, onComplete }) {
  const { calendar, setCalendar, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P8")
  const [config, setConfig] = useState({ blogsPerWeek: 3, durationWeeks: 52, startDate: "" })
  const [stats, setStats] = useState(null)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    log(`Building calendar (${config.blogsPerWeek}/week, ${config.durationWeeks} weeks)...`, "info")
    try {
      const data = await api.runPhase8(projectId, sessionId, config)
      setStats(data.calendar)
      const cData = await api.getCalendar(projectId, sessionId)
      setCalendar(cData.items || [])
      const scheduled = data.calendar?.scheduled || 0
      log(`Complete: ${scheduled} articles over ${data.calendar?.weeks || 0} weeks`, "success")
      toast(`Content calendar: ${scheduled} articles planned`, "success")
      onComplete()
      setActivePhase(9)
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
      toast(`Phase 8 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId, config])

  useEffect(() => {
    async function load() {
      try {
        const data = await api.getCalendar(projectId, sessionId)
        if (data.items) setCalendar(data.items)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  const fieldStyle = { padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13, width: 120 }

  return (
    <Card title="Phase 8: Content Calendar" actions={<RunButton onClick={run} loading={loading}>Build Calendar</RunButton>}>
      <div style={{ display: "flex", gap: 16, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <label style={{ fontSize: 12 }}>
          Blogs/week:
          <input type="number" min={1} max={14} style={{ ...fieldStyle, marginLeft: 4 }} value={config.blogsPerWeek} onChange={(e) => setConfig({ ...config, blogsPerWeek: +e.target.value })} />
        </label>
        <label style={{ fontSize: 12 }}>
          Duration (weeks):
          <input type="number" min={4} max={260} style={{ ...fieldStyle, marginLeft: 4 }} value={config.durationWeeks} onChange={(e) => setConfig({ ...config, durationWeeks: +e.target.value })} />
        </label>
        <label style={{ fontSize: 12 }}>
          Start date:
          <input type="date" style={{ ...fieldStyle, marginLeft: 4, width: 150 }} value={config.startDate} onChange={(e) => setConfig({ ...config, startDate: e.target.value })} />
        </label>
      </div>

      {error && <p style={{ color: "#dc2626", fontSize: 13 }}>{error}</p>}

      {stats && (
        <StatsRow items={[
          { label: "Scheduled", value: stats.scheduled || 0, color: "#10b981" },
          { label: "Per Week", value: stats.blogs_per_week || 0, color: "#3b82f6" },
          { label: "Weeks", value: stats.weeks || 0, color: "#8b5cf6" },
        ]} />
      )}

      {calendar.length > 0 && (
        <div style={{ maxHeight: 350, overflow: "auto", fontSize: 12 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #e5e7eb" }}>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Date</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Keyword</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Pillar</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Type</th>
                <th style={{ textAlign: "right", padding: "4px 6px" }}>Score</th>
              </tr>
            </thead>
            <tbody>
              {calendar.slice(0, 60).map((c, i) => (
                <tr key={c.id || i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                  <td style={{ padding: "4px 6px" }}>{c.scheduled_date}</td>
                  <td style={{ padding: "4px 6px", fontWeight: 500 }}>{c.keyword || c.title}</td>
                  <td style={{ padding: "4px 6px" }}><Badge color="blue">{c.pillar || "-"}</Badge></td>
                  <td style={{ padding: "4px 6px" }}><Badge color={c.article_type === "pillar" ? "green" : "gray"}>{c.article_type}</Badge></td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{(c.score || 0).toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {calendar.length > 60 && <p style={{ color: "#9ca3af", fontSize: 11, marginTop: 4 }}>Showing 60 of {calendar.length}</p>}
        </div>
      )}

      {stats && (
        <PhaseResult
          phaseNum={8}
          stats={[
            { label: "Scheduled", value: stats.scheduled || 0, color: "#10b981" },
            { label: "Weeks", value: stats.weeks || 0, color: "#8b5cf6" },
          ]}
          onNext={() => setActivePhase(9)}
        />
      )}

      <NotificationList notifications={notifications} />
      <ConsolePanel filterBadge="P8" />
    </Card>
  )
}
