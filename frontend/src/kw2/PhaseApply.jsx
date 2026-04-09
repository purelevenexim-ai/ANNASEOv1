/**
 * PhaseApply (v2) — Internal Links, Content Calendar, Strategy.
 *
 * Three tabs: Links | Calendar | Strategy
 * SSE steps: links, calendar, strategy
 */
import React, { useState, useCallback, useEffect, useRef, useMemo } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, StatsRow, usePhaseRunner, ProgressBar, Badge, Spinner, NotificationList, StrategyTab } from "./shared"
import DataTable from "./DataTable"

// ── Constants ───────────────────────────────────────────────────────────────

const APPLY_STEPS = [
  { key: "links", label: "Internal Links", icon: "🔗" },
  { key: "calendar", label: "Content Calendar", icon: "📅" },
  { key: "strategy", label: "Strategy", icon: "📋" },
]

const PILLAR_COLORS = [
  "#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ef4444",
  "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
]

const LINK_TYPE_COLORS = {
  contextual: "#3b82f6",
  hub_spoke: "#8b5cf6",
  pillar_cluster: "#10b981",
  sibling: "#f59e0b",
  cross_pillar: "#ec4899",
}

function getPillarColor(pillar, pillarList) {
  const idx = (pillarList || []).indexOf(pillar)
  return PILLAR_COLORS[idx >= 0 ? idx % PILLAR_COLORS.length : 0]
}

// ── Links Tab ───────────────────────────────────────────────────────────────

function LinksTab({ links, projectId, sessionId }) {
  const [sortField, setSortField] = useState("priority_score")
  const [sortDir, setSortDir] = useState("desc")
  const [filterType, setFilterType] = useState(null)
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(links || [])

  useEffect(() => { setData(links || []) }, [links])

  const loadByType = useCallback(async (type) => {
    setFilterType(type)
    setLoading(true)
    try {
      const res = await api.v2Links(projectId, sessionId, type)
      setData(Array.isArray(res) ? res : res.links || [])
    } catch { /* keep current data */ }
    setLoading(false)
  }, [projectId, sessionId])

  const sorted = useMemo(() => {
    const d = [...data]
    d.sort((a, b) => {
      const aVal = a[sortField] ?? ""
      const bVal = b[sortField] ?? ""
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDir === "asc" ? aVal - bVal : bVal - aVal
      }
      return sortDir === "asc"
        ? String(aVal).localeCompare(String(bVal))
        : String(bVal).localeCompare(String(aVal))
    })
    return d
  }, [data, sortField, sortDir])

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortField(field)
      setSortDir("desc")
    }
  }

  const linkTypes = [...new Set(data.map((l) => l.link_type).filter(Boolean))]
  const sortIcon = (field) => sortField === field ? (sortDir === "asc" ? " ↑" : " ↓") : ""

  return (
    <div>
      {/* Type filter */}
      <div style={{ display: "flex", gap: 4, marginBottom: 10, flexWrap: "wrap" }}>
        <button
          onClick={() => { setFilterType(null); setData(links || []) }}
          style={{
            padding: "4px 10px", borderRadius: 5, fontSize: 11,
            border: !filterType ? "2px solid #3b82f6" : "1px solid #e5e7eb",
            background: !filterType ? "#eff6ff" : "#fff", color: !filterType ? "#3b82f6" : "#6b7280",
            cursor: "pointer",
          }}
        >
          All
        </button>
        {linkTypes.map((t) => (
          <button
            key={t}
            onClick={() => loadByType(t)}
            style={{
              padding: "4px 10px", borderRadius: 5, fontSize: 11,
              border: filterType === t ? `2px solid ${LINK_TYPE_COLORS[t] || "#6b7280"}` : "1px solid #e5e7eb",
              background: filterType === t ? `${LINK_TYPE_COLORS[t] || "#6b7280"}15` : "#fff",
              color: filterType === t ? LINK_TYPE_COLORS[t] || "#6b7280" : "#6b7280",
              cursor: "pointer",
            }}
          >
            {t.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {loading && <Spinner text="Loading links..." />}

      <div style={{ overflowX: "auto", maxHeight: 500 }}>
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #e5e7eb", background: "#f9fafb" }}>
              {[
                { key: "source_url", label: "Source URL" },
                { key: "target_url", label: "Target URL" },
                { key: "anchor_text", label: "Anchor Text" },
                { key: "link_type", label: "Type" },
                { key: "priority_score", label: "Priority" },
              ].map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  style={{
                    textAlign: "left", padding: "6px 10px", fontSize: 11, fontWeight: 600,
                    color: "#6b7280", cursor: "pointer", userSelect: "none",
                    whiteSpace: "nowrap",
                  }}
                >
                  {col.label}{sortIcon(col.key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 100).map((link, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ ...tdStyle, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={link.source_url}>
                  {link.source_url || "—"}
                </td>
                <td style={{ ...tdStyle, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={link.target_url}>
                  {link.target_url || "—"}
                </td>
                <td style={{ ...tdStyle, fontWeight: 500 }}>{link.anchor_text || "—"}</td>
                <td style={tdStyle}>
                  <Badge color={link.link_type === "contextual" ? "blue" : link.link_type === "hub_spoke" ? "purple" : "gray"}>
                    {(link.link_type || "—").replace(/_/g, " ")}
                  </Badge>
                </td>
                <td style={{ ...tdStyle, fontWeight: 600, color: "#3b82f6" }}>
                  {link.priority_score != null ? Number(link.priority_score).toFixed(1) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {sorted.length > 100 && (
          <p style={{ fontSize: 12, color: "#9ca3af", textAlign: "center", padding: 8 }}>
            Showing 100 of {sorted.length} links
          </p>
        )}
        {sorted.length === 0 && !loading && (
          <p style={{ fontSize: 13, color: "#9ca3af", textAlign: "center", padding: 16 }}>No links generated yet.</p>
        )}
      </div>
    </div>
  )
}

// ── Calendar Tab ────────────────────────────────────────────────────────────

function CalendarTab({ calendar, projectId, sessionId, onReload }) {
  const [activePillar, setActivePillar] = useState(null)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)

  const pillars = [...new Set((calendar || []).map((e) => e.pillar).filter(Boolean))]
  const pillarList = pillars
  const filtered = activePillar
    ? (calendar || []).filter((e) => e.pillar === activePillar)
    : (calendar || [])

  // Group by week
  const weeks = useMemo(() => {
    const map = {}
    filtered.forEach((entry) => {
      const date = new Date(entry.scheduled_date || entry.date)
      if (isNaN(date.getTime())) return  // skip entries with invalid/missing dates
      const weekStart = new Date(date)
      weekStart.setDate(date.getDate() - date.getDay())
      const weekKey = weekStart.toISOString().split("T")[0]
      if (!map[weekKey]) map[weekKey] = []
      map[weekKey].push(entry)
    })
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b))
  }, [filtered])

  const handleSave = async (entryId, updates) => {
    setSaving(true)
    try {
      await api.v2UpdateCalendar(projectId, sessionId, entryId, updates)
      setEditing(null)
      if (onReload) onReload()
    } catch (e) {
      console.error("Update calendar failed:", e)
    }
    setSaving(false)
  }

  return (
    <div>
      {/* Pillar filter */}
      <div style={{ display: "flex", gap: 4, marginBottom: 12, flexWrap: "wrap" }}>
        <button
          onClick={() => setActivePillar(null)}
          style={{
            padding: "4px 10px", borderRadius: 5, fontSize: 11,
            border: !activePillar ? "2px solid #3b82f6" : "1px solid #e5e7eb",
            background: !activePillar ? "#eff6ff" : "#fff",
            color: !activePillar ? "#3b82f6" : "#6b7280", cursor: "pointer",
          }}
        >
          All ({(calendar || []).length})
        </button>
        {pillars.map((p, i) => {
          const count = (calendar || []).filter((e) => e.pillar === p).length
          return (
            <button
              key={p}
              onClick={() => setActivePillar(p)}
              style={{
                padding: "4px 10px", borderRadius: 5, fontSize: 11,
                border: activePillar === p ? `2px solid ${getPillarColor(p, pillarList)}` : "1px solid #e5e7eb",
                background: activePillar === p ? `${getPillarColor(p, pillarList)}15` : "#fff",
                color: activePillar === p ? getPillarColor(p, pillarList) : "#6b7280",
                cursor: "pointer",
              }}
            >
              {p} ({count})
            </button>
          )
        })}
      </div>

      {/* Timeline */}
      {weeks.length === 0 && (
        <p style={{ fontSize: 13, color: "#9ca3af", textAlign: "center", padding: 16 }}>No calendar entries yet.</p>
      )}
      <div style={{ maxHeight: 500, overflowY: "auto" }}>
        {weeks.map(([weekKey, entries]) => (
          <div key={weekKey} style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 6, paddingLeft: 4 }}>
              Week of {weekKey}
            </div>
            {entries.map((entry, i) => {
              const isEditing = editing === (entry.id || entry.entry_id)
              const entryId = entry.id || entry.entry_id
              const color = getPillarColor(entry.pillar, pillarList)

              return (
                <div
                  key={entryId || i}
                  style={{
                    display: "flex", alignItems: "flex-start", gap: 10,
                    padding: "8px 12px", marginBottom: 4, borderRadius: 6,
                    borderLeft: `4px solid ${color}`, background: "#f9fafb",
                  }}
                >
                  {/* Timeline dot */}
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 70 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: "#374151" }}>
                      {(entry.scheduled_date || entry.date || "").split("T")[0]}
                    </span>
                    <Badge color={entry.status === "published" ? "green" : entry.status === "scheduled" ? "blue" : "gray"}>
                      {entry.status || "draft"}
                    </Badge>
                  </div>

                  {/* Content */}
                  <div style={{ flex: 1 }}>
                    {isEditing ? (
                      <EditCalendarEntry
                        entry={entry}
                        onSave={(updates) => handleSave(entryId, updates)}
                        onCancel={() => setEditing(null)}
                        saving={saving}
                      />
                    ) : (
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13 }}>{entry.title || entry.keyword || "Untitled"}</div>
                        {entry.pillar && <Badge color="blue">{entry.pillar}</Badge>}
                        {entry.keyword && entry.keyword !== entry.title && (
                          <span style={{ fontSize: 11, color: "#6b7280", marginLeft: 6 }}>{entry.keyword}</span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Edit button */}
                  {!isEditing && entryId && (
                    <button
                      onClick={() => setEditing(entryId)}
                      style={{
                        border: "1px solid #d1d5db", borderRadius: 4, padding: "3px 8px",
                        fontSize: 11, cursor: "pointer", background: "#fff", color: "#6b7280",
                      }}
                    >
                      Edit
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

function EditCalendarEntry({ entry, onSave, onCancel, saving }) {
  const [title, setTitle] = useState(entry.title || "")
  const [date, setDate] = useState((entry.scheduled_date || entry.date || "").split("T")[0])
  const [status, setStatus] = useState(entry.status || "draft")

  return (
    <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
      <div style={{ flex: 1, minWidth: 160 }}>
        <label style={{ fontSize: 10, color: "#6b7280" }}>Title</label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={{ width: "100%", padding: "4px 8px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 12 }}
        />
      </div>
      <div style={{ minWidth: 120 }}>
        <label style={{ fontSize: 10, color: "#6b7280" }}>Date</label>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          style={{ width: "100%", padding: "4px 8px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 12 }}
        />
      </div>
      <div style={{ minWidth: 90 }}>
        <label style={{ fontSize: 10, color: "#6b7280" }}>Status</label>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          style={{ width: "100%", padding: "4px 8px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 12 }}
        >
          <option value="draft">Draft</option>
          <option value="scheduled">Scheduled</option>
          <option value="published">Published</option>
        </select>
      </div>
      <button
        onClick={() => onSave({ title, scheduled_date: date, status })}
        disabled={saving}
        style={{
          padding: "4px 12px", borderRadius: 4, border: "none",
          background: "#10b981", color: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer",
        }}
      >
        {saving ? "Saving..." : "Save"}
      </button>
      <button
        onClick={onCancel}
        style={{
          padding: "4px 12px", borderRadius: 4, border: "1px solid #d1d5db",
          background: "#fff", color: "#6b7280", fontSize: 11, cursor: "pointer",
        }}
      >
        Cancel
      </button>
    </div>
  )
}

const tdStyle = { padding: "5px 10px", fontSize: 12 }

// ── Main Component ──────────────────────────────────────────────────────────

export default function PhaseApply({ projectId, sessionId, onComplete }) {
  const { aiProvider, setActivePhase } = useKw2Store()
  const { loading, setLoading, streamLoading, setStreamLoading, error, setError, notifications, log, toast } = usePhaseRunner("Apply")

  const [stepStatus, setStepStatus] = useState({})
  const [progress, setProgress] = useState({ current: 0, total: APPLY_STEPS.length })
  const [done, setDone] = useState(false)
  const [activeTab, setActiveTab] = useState("links")

  // Config
  const [blogsPerWeek, setBlogsPerWeek] = useState(3)
  const [durationWeeks, setDurationWeeks] = useState(52)
  const [startDate, setStartDate] = useState("")

  // Data
  const [links, setLinks] = useState([])
  const [calendar, setCalendar] = useState([])
  const [strategy, setStrategy] = useState(null)
  const closeRef = useRef(null)

  const loadResults = useCallback(async () => {
    try {
      const [linksRes, calRes, stratRes] = await Promise.all([
        api.v2Links(projectId, sessionId).catch(() => []),
        api.v2Calendar(projectId, sessionId).catch(() => []),
        api.v2Strategy(projectId, sessionId).catch(() => null),
      ])
      setLinks(Array.isArray(linksRes) ? linksRes : linksRes.links || [])
      setCalendar(Array.isArray(calRes) ? calRes : calRes.entries || calRes.calendar || [])
      setStrategy(stratRes)
    } catch (e) {
      log(`Failed to load results: ${e.message}`, "error")
    }
  }, [projectId, sessionId])

  const runStream = useCallback(async () => {
    setStreamLoading(true)
    setError(null)
    setDone(false)
    setStepStatus({})
    setProgress({ current: 0, total: APPLY_STEPS.length })
    log("Starting apply (streaming)...", "info")

    const close = api.v2ApplyStream(projectId, sessionId, (evt) => {
      if (evt.error) {
        setError(evt.message || "Apply failed")
        log(`Error: ${evt.message}`, "error")
        setStreamLoading(false)
        return
      }

      if (evt.step || evt.layer) {
        const step = evt.step || evt.layer
        setStepStatus((prev) => ({ ...prev, [step]: evt.status || "running" }))
        if (evt.status === "complete" || evt.status === "done") {
          setProgress((prev) => ({ ...prev, current: Math.min(prev.current + 1, prev.total) }))
        }
        log(`${step}: ${evt.message || evt.status || "processing"}`, evt.status === "error" ? "error" : "progress")
      }

      if (evt.done) {
        setStreamLoading(false)
        setDone(true)
        setProgress((prev) => ({ ...prev, current: prev.total }))
        log("Apply complete!", "success")
        toast("Apply finished", "success")
        loadResults()
      }
    }, {
      aiProvider,
      blogsPerWeek,
      durationWeeks,
      startDate: startDate || undefined,
    })

    closeRef.current = close
  }, [projectId, sessionId, aiProvider, blogsPerWeek, durationWeeks, startDate])

  const runSync = useCallback(async () => {
    setLoading(true)
    setError(null)
    log("Running apply (sync)...", "info")
    try {
      await api.v2Apply(projectId, sessionId, {
        ai_provider: aiProvider,
        blogs_per_week: blogsPerWeek,
        duration_weeks: durationWeeks,
        start_date: startDate || null,
      })
      setDone(true)
      log("Apply complete", "success")
      toast("Apply complete", "success")
      await loadResults()
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId, aiProvider, blogsPerWeek, durationWeeks, startDate])

  // Load existing results on mount (e.g. when revisiting the phase)
  useEffect(() => { loadResults() }, [loadResults])

  useEffect(() => {
    return () => { if (closeRef.current) closeRef.current() }
  }, [])

  const isRunning = loading || streamLoading

  const tabs = [
    { key: "links", label: "Links", icon: "🔗", count: links.length },
    { key: "calendar", label: "Calendar", icon: "📅", count: calendar.length },
    { key: "strategy", label: "Strategy", icon: "📋", count: strategy ? 1 : 0 },
  ]

  return (
    <Card
      title="Apply — Links, Calendar & Strategy"
      actions={
        <div style={{ display: "flex", gap: 6 }}>
          <RunButton onClick={runStream} loading={streamLoading} disabled={loading}>
            Stream Apply
          </RunButton>
          <RunButton onClick={runSync} loading={loading} disabled={streamLoading} variant="secondary">
            Sync
          </RunButton>
        </div>
      }
    >
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>
        Generates internal linking plan, content calendar, and SEO strategy document.
      </p>

      {/* Config */}
      <div style={{ display: "flex", gap: 12, marginBottom: 14, flexWrap: "wrap", padding: "10px 14px", background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>
        <div>
          <label style={{ fontSize: 11, color: "#6b7280", display: "block", marginBottom: 2 }}>Blogs/Week</label>
          <input
            type="number"
            min={1}
            max={14}
            value={blogsPerWeek}
            onChange={(e) => setBlogsPerWeek(Number(e.target.value))}
            disabled={isRunning}
            style={{ width: 60, padding: "4px 8px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 13, textAlign: "center" }}
          />
        </div>
        <div>
          <label style={{ fontSize: 11, color: "#6b7280", display: "block", marginBottom: 2 }}>Duration (weeks)</label>
          <input
            type="number"
            min={4}
            max={104}
            value={durationWeeks}
            onChange={(e) => setDurationWeeks(Number(e.target.value))}
            disabled={isRunning}
            style={{ width: 60, padding: "4px 8px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 13, textAlign: "center" }}
          />
        </div>
        <div>
          <label style={{ fontSize: 11, color: "#6b7280", display: "block", marginBottom: 2 }}>Start Date</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            disabled={isRunning}
            style={{ padding: "4px 8px", borderRadius: 4, border: "1px solid #d1d5db", fontSize: 12 }}
          />
        </div>
      </div>

      {error && <p style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>⚠ {error}</p>}

      {/* SSE Progress */}
      {(streamLoading || done) && (
        <div style={{ marginBottom: 16 }}>
          <ProgressBar
            value={progress.current}
            max={progress.total}
            label="Apply Progress"
            color="#10b981"
            animated={streamLoading}
          />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {APPLY_STEPS.map((step) => {
              const status = stepStatus[step.key]
              const bg = status === "complete" || status === "done"
                ? "#dcfce7"
                : status === "running"
                  ? "#dbeafe"
                  : status === "error"
                    ? "#fee2e2"
                    : "#f3f4f6"
              const fg = status === "complete" || status === "done"
                ? "#166534"
                : status === "running"
                  ? "#1e40af"
                  : status === "error"
                    ? "#991b1b"
                    : "#9ca3af"
              return (
                <span
                  key={step.key}
                  style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    padding: "3px 10px", borderRadius: 12, fontSize: 11,
                    background: bg, color: fg, fontWeight: status === "running" ? 600 : 400,
                  }}
                >
                  {step.icon} {step.label}
                  {status === "running" && <span className="kw2-spin" style={{ display: "inline-block", width: 10, height: 10, border: "2px solid #93c5fd", borderTop: "2px solid #3b82f6", borderRadius: "50%" }} />}
                  {(status === "complete" || status === "done") && " ✓"}
                </span>
              )
            })}
            <style>{`.kw2-spin { animation: kw2spin .7s linear infinite; } @keyframes kw2spin { to { transform: rotate(360deg) } }`}</style>
          </div>
        </div>
      )}

      {/* Stats */}
      {done && (
        <StatsRow items={[
          { label: "Links", value: links.length, color: "#3b82f6" },
          { label: "Calendar Entries", value: calendar.length, color: "#8b5cf6" },
          { label: "Strategy", value: strategy ? "Ready" : "—", color: "#10b981" },
        ]} />
      )}

      {/* Tabs */}
      {done && (
        <div>
          <div style={{ display: "flex", gap: 0, marginBottom: 16, borderBottom: "2px solid #e5e7eb" }}>
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                style={{
                  padding: "8px 16px", border: "none", borderBottom: activeTab === tab.key ? "2px solid #3b82f6" : "2px solid transparent",
                  background: "none", color: activeTab === tab.key ? "#3b82f6" : "#6b7280",
                  fontWeight: activeTab === tab.key ? 600 : 400, fontSize: 13, cursor: "pointer",
                  display: "flex", alignItems: "center", gap: 6, marginBottom: -2,
                }}
              >
                {tab.icon} {tab.label}
                {tab.count > 0 && (
                  <span style={{
                    background: activeTab === tab.key ? "#dbeafe" : "#f3f4f6",
                    color: activeTab === tab.key ? "#1e40af" : "#9ca3af",
                    padding: "1px 6px", borderRadius: 8, fontSize: 10,
                  }}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}

            {/* Export */}
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4, padding: "0 8px" }}>
              <button
                style={{
                  padding: "4px 10px", borderRadius: 4, border: "1px solid #d1d5db",
                  background: "#fff", color: "#6b7280", fontSize: 11, cursor: "pointer",
                }}
                onClick={() => {
                  const rows = activeTab === "links"
                    ? links.map(l => [l.source, l.target, l.anchor_text, l.link_type, l.priority].join(","))
                    : activeTab === "calendar"
                    ? calendar.map(c => [c.week, c.date, `"${(c.title || "").replace(/"/g, '""')}"`, c.pillar, c.keyword, c.content_type].join(","))
                    : strategy
                    ? [JSON.stringify(strategy)]
                    : []
                  if (!rows.length) { toast("No data to export", "warn"); return }
                  const header = activeTab === "links"
                    ? "source,target,anchor_text,link_type,priority"
                    : activeTab === "calendar"
                    ? "week,date,title,pillar,keyword,content_type"
                    : "strategy_json"
                  const blob = new Blob([header + "\n" + rows.join("\n")], { type: "text/csv" })
                  const a = document.createElement("a")
                  a.href = URL.createObjectURL(blob)
                  a.download = `kw2_${activeTab}_${sessionId.slice(0, 8)}.csv`
                  a.click()
                  URL.revokeObjectURL(a.href)
                  toast("CSV downloaded", "success")
                }}
              >
                Export CSV
              </button>
            </div>
          </div>

          {/* Tab content */}
          {activeTab === "links" && (
            <>
              <LinksTab links={links} projectId={projectId} sessionId={sessionId} />
              {links.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: "#374151" }}>Links — Bulk Actions</h4>
                  <DataTable
                    columns={[
                      { key: "source", label: "Source", sortable: true, searchable: true },
                      { key: "target", label: "Target", sortable: true, searchable: true },
                      { key: "link_type", label: "Type", sortable: true, filterable: true, type: "badge" },
                      { key: "anchor_text", label: "Anchor", sortable: true, searchable: true },
                      { key: "priority_score", label: "Priority", sortable: true, type: "number", decimals: 1 },
                    ]}
                    data={links.map((l, i) => ({ ...l, id: l.id || `link_${i}` }))}
                    rowKey="id"
                    bulkActions={[]}
                  />
                </div>
              )}
            </>
          )}
          {activeTab === "calendar" && (
            <>
              <CalendarTab
                calendar={calendar}
                projectId={projectId}
                sessionId={sessionId}
                onReload={loadResults}
              />
              {calendar.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: "#374151" }}>Calendar — Bulk Actions</h4>
                  <DataTable
                    columns={[
                      { key: "title", label: "Title", sortable: true, searchable: true },
                      { key: "keyword", label: "Keyword", sortable: true, searchable: true },
                      { key: "pillar", label: "Pillar", sortable: true, filterable: true },
                      { key: "publish_date", label: "Date", sortable: true },
                      { key: "content_type", label: "Type", sortable: true, filterable: true, type: "badge" },
                    ]}
                    data={calendar.map((c, i) => ({ ...c, id: c.id || `cal_${i}` }))}
                    rowKey="id"
                    bulkActions={[]}
                  />
                </div>
              )}
            </>
          )}
          {activeTab === "strategy" && (
            <StrategyTab strategy={strategy} />
          )}
        </div>
      )}

      {/* Complete action */}
      {done && (
        <div style={{ marginTop: 16, padding: "10px 16px", background: "#f0fdf4", borderRadius: 8, border: "1px solid #86efac", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 18 }}>✓</span>
            <span style={{ fontWeight: 600, color: "#166534", fontSize: 14 }}>Apply Complete — All Phases Done!</span>
          </div>
          <button
            onClick={async () => {
              try { await api.updatePhaseStatus(projectId, sessionId, "apply", "done") } catch { /* non-fatal */ }
              if (onComplete) onComplete()
            }}
            style={{
              background: "#10b981", color: "#fff", border: "none",
              borderRadius: 6, padding: "6px 16px", fontWeight: 600,
              fontSize: 13, cursor: "pointer",
            }}
          >
            Finish ✓
          </button>
        </div>
      )}

      <NotificationList notifications={notifications} />

    </Card>
  )
}
