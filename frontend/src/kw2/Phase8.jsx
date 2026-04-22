/**
 * Phase 8 — Content Calendar (redesigned).
 * Pulls strategy ideas from Phase 9, supports per-pillar quotas,
 * shows month-grouped view and pillar distribution.
 */
import React, { useState, useCallback, useEffect, useMemo } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, StatsRow, usePhaseRunner, PhaseResult, NotificationList } from "./shared"

// ── small helpers ────────────────────────────────────────────────────────────
const PILLAR_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444",
  "#06b6d4", "#84cc16", "#f97316", "#ec4899", "#6366f1",
]
const pillarColor = (i) => PILLAR_COLORS[i % PILLAR_COLORS.length]

const intentBadgeColor = { informational: "blue", commercial: "yellow", transactional: "green", navigational: "gray" }
const sourceBadgeColor = { strategy: "green", intelligence: "blue", keywords: "gray", keyword: "gray" }

function PillarBar({ by_pillar = [], total = 0 }) {
  if (!by_pillar.length) return null
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Articles by Pillar</div>
      {by_pillar.map((row, i) => (
        <div key={row.pillar} style={{ marginBottom: 5 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 2 }}>
            <span style={{ color: "#374151", fontWeight: 500 }}>{row.pillar}</span>
            <span style={{ color: "#6b7280" }}>{row.count} ({row.pct}%)</span>
          </div>
          <div style={{ height: 8, background: "#f3f4f6", borderRadius: 4, overflow: "hidden" }}>
            <div style={{ width: `${row.pct}%`, height: "100%", background: pillarColor(i), borderRadius: 4, transition: "width 0.4s" }} />
          </div>
        </div>
      ))}
    </div>
  )
}

function StrategyIdeasPanel({ ideas }) {
  const [activeTab, setActiveTab] = useState("pillars")
  if (!ideas) return null

  const tabs = [
    { id: "pillars", label: "Priority Pillars", count: ideas.priority_pillars?.length },
    { id: "wins", label: "Quick Wins", count: ideas.quick_wins?.length },
    { id: "gaps", label: "Content Gaps", count: ideas.content_gaps?.length },
    { id: "weekly", label: "Weekly Plan", count: ideas.weekly_plan_preview?.length },
  ]

  return (
    <div style={{ marginBottom: 16, border: "1px solid #bbf7d0", borderRadius: 8, background: "#f0fdf4", overflow: "hidden" }}>
      <div style={{ padding: "10px 14px", borderBottom: "1px solid #bbf7d0", display: "flex", gap: 8, flexWrap: "wrap" }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
            padding: "4px 10px", borderRadius: 4, fontSize: 12, fontWeight: 500, cursor: "pointer",
            background: activeTab === t.id ? "#16a34a" : "transparent",
            color: activeTab === t.id ? "#fff" : "#166534",
            border: activeTab === t.id ? "none" : "1px solid #86efac",
          }}>
            {t.label} {t.count ? `(${t.count})` : ""}
          </button>
        ))}
      </div>
      <div style={{ padding: "10px 14px", maxHeight: 220, overflow: "auto" }}>
        {activeTab === "pillars" && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {(ideas.priority_pillars || []).map((p, i) => {
              const label = typeof p === "string" ? p : p.pillar || p.name || ""
              return <Badge key={i} color={i === 0 ? "green" : "blue"}>{i + 1}. {label}</Badge>
            })}
            {!ideas.priority_pillars?.length && <p style={{ fontSize: 12, color: "#6b7280", margin: 0 }}>No priority pillars in strategy yet.</p>}
          </div>
        )}
        {activeTab === "wins" && (
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
            {(ideas.quick_wins || []).map((w, i) => (
              <li key={i} style={{ color: "#166534", marginBottom: 2 }}>{typeof w === "string" ? w : w.keyword || w.title || ""}</li>
            ))}
            {!ideas.quick_wins?.length && <li style={{ color: "#6b7280" }}>No quick wins yet — run Phase 9 Strategy first.</li>}
          </ul>
        )}
        {activeTab === "gaps" && (
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
            {(ideas.content_gaps || []).map((g, i) => (
              <li key={i} style={{ color: "#374151", marginBottom: 2 }}>{typeof g === "string" ? g : g.topic || g.gap || ""}</li>
            ))}
            {!ideas.content_gaps?.length && <li style={{ color: "#6b7280" }}>No content gaps found yet.</li>}
          </ul>
        )}
        {activeTab === "weekly" && (
          <div>
            {(ideas.weekly_plan_preview || []).map((week) => (
              <div key={week.week} style={{ marginBottom: 8, paddingBottom: 8, borderBottom: "1px solid #dcfce7" }}>
                <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 3 }}>
                  Week {week.week} — <span style={{ color: "#16a34a" }}>{week.focus_pillar}</span>
                </div>
                {(week.articles || []).map((a, i) => (
                  <div key={i} style={{ fontSize: 11, color: "#374151", marginLeft: 10 }}>
                    • {typeof a === "string" ? a : a.title || a.keyword || ""}
                  </div>
                ))}
              </div>
            ))}
            {!ideas.weekly_plan_preview?.length && <p style={{ fontSize: 12, color: "#6b7280", margin: 0 }}>No weekly plan yet — run Phase 9 first.</p>}
          </div>
        )}
      </div>
    </div>
  )
}

function MonthView({ calendar }) {
  const byMonth = useMemo(() => {
    const map = {}
    for (const c of calendar) {
      const ym = (c.scheduled_date || "").slice(0, 7)
      if (!ym) continue
      if (!map[ym]) map[ym] = []
      map[ym].push(c)
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b))
  }, [calendar])

  if (!byMonth.length) return <p style={{ color: "#9ca3af", fontSize: 13 }}>No calendar entries yet.</p>

  return (
    <div style={{ maxHeight: 400, overflow: "auto" }}>
      {byMonth.map(([month, items]) => (
        <div key={month} style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: "#1f2937", marginBottom: 6, padding: "4px 8px", background: "#f9fafb", borderRadius: 4 }}>
            {month} <span style={{ fontWeight: 400, color: "#6b7280", fontSize: 12 }}>— {items.length} articles</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, paddingLeft: 8 }}>
            {items.slice(0, 30).map((c, i) => (
              <div key={c.id || i} style={{
                padding: "4px 8px", borderRadius: 4, fontSize: 11,
                background: c.source === "strategy" ? "#dcfce7" : c.source === "intelligence" ? "#dbeafe" : "#f3f4f6",
                border: `1px solid ${c.source === "strategy" ? "#86efac" : c.source === "intelligence" ? "#bfdbfe" : "#e5e7eb"}`,
                maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }} title={c.title || c.keyword}>
                <span style={{ color: "#6b7280", marginRight: 4 }}>{(c.scheduled_date || "").slice(5)}</span>
                {c.title || c.keyword}
              </div>
            ))}
            {items.length > 30 && <span style={{ fontSize: 11, color: "#9ca3af", alignSelf: "center" }}>+{items.length - 30} more</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

function PillarView({ calendar }) {
  const byPillar = useMemo(() => {
    const map = {}
    for (const c of calendar) {
      const p = c.pillar || "General"
      if (!map[p]) map[p] = []
      map[p].push(c)
    }
    return Object.entries(map).sort(([, a], [, b]) => b.length - a.length)
  }, [calendar])

  if (!byPillar.length) return <p style={{ color: "#9ca3af", fontSize: 13 }}>No calendar entries yet.</p>

  return (
    <div style={{ maxHeight: 400, overflow: "auto" }}>
      {byPillar.map(([pillar, items], pi) => (
        <div key={pillar} style={{ marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
            <div style={{ width: 10, height: 10, borderRadius: "50%", background: pillarColor(pi), flexShrink: 0 }} />
            <span style={{ fontWeight: 600, fontSize: 13, color: "#1f2937" }}>{pillar}</span>
            <span style={{ fontSize: 12, color: "#6b7280" }}>{items.length} articles</span>
          </div>
          <div style={{ paddingLeft: 18, fontSize: 12, display: "flex", flexDirection: "column", gap: 2 }}>
            {items.slice(0, 8).map((c, i) => (
              <div key={c.id || i} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ color: "#9ca3af", width: 60, flexShrink: 0 }}>{c.scheduled_date || ""}</span>
                <span style={{ color: "#374151", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title || c.keyword}</span>
                {c.source && c.source !== "keyword" && (
                  <Badge color={sourceBadgeColor[c.source] || "gray"} style={{ fontSize: 10, padding: "1px 5px" }}>{c.source}</Badge>
                )}
              </div>
            ))}
            {items.length > 8 && <span style={{ color: "#9ca3af" }}>+{items.length - 8} more…</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Phase8({ projectId, sessionId, onComplete, onNext, autoRun, hideRunButton }) {
  const { calendar, setCalendar, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P8")

  // Config
  const [cadenceMode, setCadenceMode] = useState("total") // "total" | "per_pillar"
  const [config, setConfig] = useState({ blogsPerWeek: 3, durationWeeks: 52, startDate: "" })
  const [pillarQuotas, setPillarQuotas] = useState({}) // {pillar: N}
  const [useStrategyIdeas, setUseStrategyIdeas] = useState(false)

  // Loaded data
  const [summary, setSummary] = useState(null)
  const [stats, setStats] = useState(null)
  const [calendarView, setCalendarView] = useState("list") // "list" | "month" | "pillar"
  const [pillarFilter, setPillarFilter] = useState("all")
  const [rebuildLoading, setRebuildLoading] = useState(false)

  // Load summary + existing calendar on mount
  useEffect(() => {
    async function load() {
      try {
        const [calData, sumData] = await Promise.all([
          api.getCalendar(projectId, sessionId),
          api.getCalendarSummary(projectId, sessionId).catch(() => null),
        ])
        if (calData.items) setCalendar(calData.items)
        if (sumData) setSummary(sumData)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    const effectiveBPW = cadenceMode === "per_pillar"
      ? Object.values(pillarQuotas).reduce((s, v) => s + (parseInt(v) || 0), 0) || 3
      : config.blogsPerWeek

    log(`Building calendar (${effectiveBPW}/week, ${config.durationWeeks} weeks)${useStrategyIdeas ? " using Strategy ideas" : ""}…`, "info")
    try {
      const data = await api.runPhase8(projectId, sessionId, {
        blogsPerWeek: config.blogsPerWeek,
        durationWeeks: config.durationWeeks,
        startDate: config.startDate || null,
        pillarQuotas: cadenceMode === "per_pillar" ? pillarQuotas : {},
        useStrategyIdeas,
      })
      setStats(data.calendar)
      const [calData, sumData] = await Promise.all([
        api.getCalendar(projectId, sessionId),
        api.getCalendarSummary(projectId, sessionId).catch(() => null),
      ])
      if (calData.items) setCalendar(calData.items)
      if (sumData) setSummary(sumData)
      const scheduled = data.calendar?.scheduled || 0
      log(`Complete: ${scheduled} articles over ${data.calendar?.weeks || 0} weeks`, "success")
      toast(`Content calendar: ${scheduled} articles planned`, "success")
      onComplete()
      if (onNext) onNext(); else setActivePhase(9)
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
      toast(`Phase 8 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId, config, cadenceMode, pillarQuotas, useStrategyIdeas])

  const handleRebuild = useCallback(async () => {
    setRebuildLoading(true)
    log("Rebuilding calendar from strategy + intelligence + keywords…", "info")
    try {
      const data = await api.rebuildCalendar(projectId, sessionId)
      const [calData, sumData] = await Promise.all([
        api.getCalendar(projectId, sessionId),
        api.getCalendarSummary(projectId, sessionId).catch(() => null),
      ])
      if (calData.items) setCalendar(calData.items)
      if (sumData) setSummary(sumData)
      setStats(data.calendar)
      toast(`Rebuilt: ${data.calendar?.scheduled || 0} articles from strategy`, "success")
      log(`Rebuild complete: ${data.calendar?.scheduled || 0} articles`, "success")
    } catch (e) {
      toast(`Rebuild failed: ${e.message}`, "error")
    }
    setRebuildLoading(false)
  }, [projectId, sessionId])

  // When cadence mode switches to per_pillar, init quotas from profile_pillars
  useEffect(() => {
    if (cadenceMode === "per_pillar" && summary?.profile_pillars?.length) {
      const init = {}
      summary.profile_pillars.forEach((p, i) => {
        init[p] = pillarQuotas[p] ?? (i === 0 ? 2 : 1)
      })
      setPillarQuotas(init)
    }
  }, [cadenceMode, summary?.profile_pillars])

  const fieldStyle = { padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }
  const displayCalendar = pillarFilter === "all" ? calendar : calendar.filter(c => c.pillar === pillarFilter)
  const allPillars = useMemo(() => [...new Set(calendar.map(c => c.pillar).filter(Boolean))], [calendar])
  const strategyAvailable = summary?.strategy_available
  const strategyIdeas = summary?.strategy_ideas

  return (
    <Card
      title="Phase 8: Content Calendar"
      actions={hideRunButton ? null : (
        <div style={{ display: "flex", gap: 8 }}>
          {strategyAvailable && (
            <button
              onClick={handleRebuild}
              disabled={rebuildLoading}
              style={{
                padding: "6px 14px", borderRadius: 6, fontSize: 13, fontWeight: 500, cursor: "pointer",
                background: rebuildLoading ? "#d1d5db" : "#16a34a", color: "#fff", border: "none",
              }}
            >
              {rebuildLoading ? "Rebuilding…" : "↺ Rebuild from Strategy"}
            </button>
          )}
          <RunButton onClick={run} loading={loading}>Build Calendar</RunButton>
        </div>
      )}
    >
      {/* Strategy Banner */}
      {strategyAvailable && (
        <div style={{ marginBottom: 14, padding: "10px 14px", background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 8, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#166534" }}>✓ AI Strategy available</div>
            <div style={{ fontSize: 12, color: "#4b7c5d" }}>
              {strategyIdeas?.strategy_summary?.biggest_opportunity || "Phase 9 strategy has content ideas ready to use."}
            </div>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#166534", cursor: "pointer", flexShrink: 0 }}>
            <input
              type="checkbox"
              checked={useStrategyIdeas}
              onChange={e => setUseStrategyIdeas(e.target.checked)}
              style={{ width: 14, height: 14 }}
            />
            Use strategy ideas
          </label>
        </div>
      )}

      {/* Configuration Panel */}
      <div style={{ marginBottom: 16, padding: 14, background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 10 }}>Calendar Setup</div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
          {/* Basic config */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <label style={{ fontSize: 12 }}>
              Start date
              <div><input type="date" style={{ ...fieldStyle, width: 150, display: "block", marginTop: 3 }} value={config.startDate} onChange={e => setConfig({ ...config, startDate: e.target.value })} /></div>
            </label>
            <label style={{ fontSize: 12 }}>
              Duration (weeks)
              <div><input type="number" min={4} max={260} style={{ ...fieldStyle, width: 90, display: "block", marginTop: 3 }} value={config.durationWeeks} onChange={e => setConfig({ ...config, durationWeeks: +e.target.value })} /></div>
            </label>
          </div>

          {/* Cadence mode toggle */}
          <div>
            <div style={{ fontSize: 12, marginBottom: 6, color: "#374151" }}>Cadence mode</div>
            <div style={{ display: "flex", gap: 0, border: "1px solid #d1d5db", borderRadius: 6, overflow: "hidden" }}>
              {[["total", "Total/week"], ["per_pillar", "Per Pillar"]].map(([mode, label]) => (
                <button key={mode} onClick={() => setCadenceMode(mode)} style={{
                  padding: "5px 12px", fontSize: 12, cursor: "pointer", border: "none",
                  background: cadenceMode === mode ? "#3b82f6" : "#fff",
                  color: cadenceMode === mode ? "#fff" : "#374151",
                }}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Total or per-pillar */}
          {cadenceMode === "total" ? (
            <label style={{ fontSize: 12 }}>
              Blogs/week
              <div><input type="number" min={1} max={21} style={{ ...fieldStyle, width: 80, display: "block", marginTop: 3 }} value={config.blogsPerWeek} onChange={e => setConfig({ ...config, blogsPerWeek: +e.target.value })} /></div>
            </label>
          ) : (
            <div>
              <div style={{ fontSize: 12, marginBottom: 4, color: "#374151" }}>Blogs/week per pillar</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 160, overflow: "auto" }}>
                {(summary?.profile_pillars?.length ? summary.profile_pillars : allPillars).map(p => (
                  <label key={p} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                    <span style={{ width: 130, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "#374151" }}>{p}</span>
                    <input
                      type="number" min={0} max={7}
                      style={{ ...fieldStyle, width: 60, padding: "4px 6px" }}
                      value={pillarQuotas[p] ?? 1}
                      onChange={e => setPillarQuotas(q => ({ ...q, [p]: +e.target.value }))}
                    />
                    <span style={{ color: "#9ca3af" }}>/wk</span>
                  </label>
                ))}
                {cadenceMode === "per_pillar" && (
                  <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4, borderTop: "1px solid #e5e7eb", paddingTop: 4 }}>
                    Total: <strong>{Object.values(pillarQuotas).reduce((s, v) => s + (parseInt(v) || 0), 0)}</strong>/week
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {error && <p style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>{error}</p>}

      {/* Strategy Ideas Panel */}
      {strategyAvailable && strategyIdeas && <StrategyIdeasPanel ideas={strategyIdeas} />}

      {/* Stats after build */}
      {stats && (
        <div style={{ marginBottom: 12 }}>
          <StatsRow items={[
            { label: "Scheduled", value: stats.scheduled || 0, color: "#10b981" },
            { label: "Per Week", value: stats.blogs_per_week || 0, color: "#3b82f6" },
            { label: "Weeks", value: stats.weeks || 0, color: "#8b5cf6" },
            ...(stats.from_strategy ? [{ label: "From Strategy", value: stats.from_strategy, color: "#16a34a" }] : []),
          ]} />
        </div>
      )}

      {/* Per-pillar distribution (after calendar is built) */}
      {summary?.by_pillar?.length > 0 && <PillarBar by_pillar={summary.by_pillar} total={summary.total} />}

      {/* Calendar view */}
      {calendar.length > 0 && (
        <div>
          {/* View controls */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
            <div style={{ display: "flex", gap: 0, border: "1px solid #d1d5db", borderRadius: 6, overflow: "hidden" }}>
              {[["list", "List"], ["month", "By Month"], ["pillar", "By Pillar"]].map(([v, label]) => (
                <button key={v} onClick={() => setCalendarView(v)} style={{
                  padding: "4px 10px", fontSize: 12, cursor: "pointer", border: "none",
                  background: calendarView === v ? "#6366f1" : "#fff",
                  color: calendarView === v ? "#fff" : "#374151",
                }}>
                  {label}
                </button>
              ))}
            </div>
            {calendarView === "list" && allPillars.length > 1 && (
              <select
                value={pillarFilter}
                onChange={e => setPillarFilter(e.target.value)}
                style={{ ...fieldStyle, padding: "4px 8px", fontSize: 12 }}
              >
                <option value="all">All Pillars ({calendar.length})</option>
                {allPillars.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            )}
            <span style={{ fontSize: 12, color: "#9ca3af" }}>
              {displayCalendar.length} articles
            </span>
          </div>

          {/* List view */}
          {calendarView === "list" && (
            <div style={{ maxHeight: 350, overflow: "auto", fontSize: 12, border: "1px solid #e5e7eb", borderRadius: 6 }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead style={{ position: "sticky", top: 0, background: "#f9fafb" }}>
                  <tr style={{ borderBottom: "2px solid #e5e7eb" }}>
                    <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Date</th>
                    <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Title / Keyword</th>
                    <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Pillar</th>
                    <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Type</th>
                    <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Source</th>
                    <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 600 }}>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {displayCalendar.slice(0, 100).map((c, i) => (
                    <tr key={c.id || i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                      <td style={{ padding: "4px 8px", color: "#6b7280", whiteSpace: "nowrap" }}>{c.scheduled_date}</td>
                      <td style={{ padding: "4px 8px", fontWeight: 500, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={c.title || c.keyword}>{c.title || c.keyword}</td>
                      <td style={{ padding: "4px 8px" }}><Badge color="blue">{c.pillar || "—"}</Badge></td>
                      <td style={{ padding: "4px 8px" }}><Badge color={c.article_type === "pillar" ? "green" : "gray"}>{c.article_type}</Badge></td>
                      <td style={{ padding: "4px 8px" }}>
                        {c.source && c.source !== "keyword" && (
                          <Badge color={sourceBadgeColor[c.source] || "gray"}>{c.source}</Badge>
                        )}
                      </td>
                      <td style={{ padding: "4px 8px", textAlign: "right", color: "#6b7280" }}>{(c.score || 0).toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {displayCalendar.length > 100 && (
                <p style={{ color: "#9ca3af", fontSize: 11, margin: "6px 8px" }}>Showing 100 of {displayCalendar.length}</p>
              )}
            </div>
          )}

          {calendarView === "month" && <MonthView calendar={displayCalendar} />}
          {calendarView === "pillar" && <PillarView calendar={calendar} />}
        </div>
      )}

      {stats && (
        <PhaseResult
          phaseNum={8}
          stats={[
            { label: "Scheduled", value: stats.scheduled || 0, color: "#10b981" },
            { label: "Weeks", value: stats.weeks || 0, color: "#8b5cf6" },
          ]}
          onNext={onNext || (() => setActivePhase(9))}
        />
      )}

      <NotificationList notifications={notifications} />
    </Card>
  )
}

