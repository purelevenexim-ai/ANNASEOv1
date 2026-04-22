/**
 * SessionDashboard — Full card-grid landing page for Keywords v2.
 * Shown when no session is active. Each card opens its session on click.
 */
import React, { useState, useEffect, useCallback, useRef } from "react"
import * as api from "./api"
import { MODE_META } from "./flow"

// ── helpers ──────────────────────────────────────────────────────────────────

function timeAgo(dateStr) {
  if (!dateStr) return ""
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return days === 1 ? "yesterday" : `${days}d ago`
}

function sessionLabel(s) {
  if (s.name) return s.name
  if (Array.isArray(s.seed_keywords) && s.seed_keywords.length) return s.seed_keywords.join(", ")
  return `Session ${(s.id || "").slice(-6)}`
}

// phases tracked per session row
const PHASE_KEYS = [1,2,3,4,5,6,7,8,9]

const MODE_STYLE = {
  brand:   { bg: "#eff6ff", border: "#bfdbfe", badge: "#1e40af", badgeBg: "#dbeafe", icon: "🏢", label: "Brand Analysis" },
  expand:  { bg: "#f0fdf4", border: "#bbf7d0", badge: "#166534", badgeBg: "#dcfce7", icon: "🌱", label: "Expand Session" },
  review:  { bg: "#faf5ff", border: "#e9d5ff", badge: "#5b21b6", badgeBg: "#ede9fe", icon: "🔍", label: "Review" },
  v2:      { bg: "#f0fdfa", border: "#99f6e4", badge: "#0f766e", badgeBg: "#ccfbf1", icon: "⚡", label: "Smart Workflow" },
}

// ── Phase progress dots ───────────────────────────────────────────────────────

function PhaseDots({ session }) {
  const done = PHASE_KEYS.filter(i => session[`phase${i}_done`])
  const total = PHASE_KEYS.length
  return (
    <div style={{ display: "flex", gap: 3, alignItems: "center", marginTop: 8 }}>
      {PHASE_KEYS.map(i => (
        <div key={i} style={{
          width: 8, height: 8, borderRadius: "50%",
          background: session[`phase${i}_done`] ? "#10b981" : "#e5e7eb",
        }} title={`Phase ${i}`} />
      ))}
      <span style={{ fontSize: 10, color: "#9ca3af", marginLeft: 4 }}>
        {done.length}/{total} phases
      </span>
    </div>
  )
}

// ── New Session inline creation card ─────────────────────────────────────────

const MODES = ["v2", "brand", "expand", "review"]

function NewSessionCard({ onCreate, loading }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [mode, setMode] = useState("v2")
  const nameRef = useRef(null)

  const open_ = () => { setOpen(true); setTimeout(() => nameRef.current?.focus(), 50) }
  const close = () => { setOpen(false); setName(""); setMode("v2") }

  const handleCreate = () => {
    if (!name.trim()) { nameRef.current?.focus(); return }
    onCreate(mode, name.trim())
    close()
  }

  if (!open) {
    return (
      <div
        onClick={open_}
        style={{
          minHeight: 180, borderRadius: 12, border: "2px dashed #d1d5db",
          background: "#fafafa", cursor: "pointer", display: "flex",
          flexDirection: "column", alignItems: "center", justifyContent: "center",
          gap: 8, transition: "all .15s", padding: 24,
        }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = "#3b82f6"; e.currentTarget.style.background = "#eff6ff" }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = "#d1d5db"; e.currentTarget.style.background = "#fafafa" }}
      >
        <div style={{ fontSize: 32, color: "#9ca3af" }}>+</div>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#374151" }}>New Keyword Research</div>
        <div style={{ fontSize: 12, color: "#9ca3af", textAlign: "center" }}>
          Start a fresh session for a product, category, or topic
        </div>
      </div>
    )
  }

  return (
    <div style={{
      minHeight: 180, borderRadius: 12, border: "2px solid #3b82f6",
      background: "#fff", padding: 18, boxShadow: "0 4px 12px rgba(59,130,246,.12)",
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#1e40af" }}>New Session</div>

      {/* Session name */}
      <div>
        <label style={{ fontSize: 11, fontWeight: 600, color: "#374151", display: "block", marginBottom: 4 }}>
          Session Name <span style={{ color: "#ef4444" }}>*</span>
        </label>
        <input
          ref={nameRef}
          value={name}
          onChange={e => setName(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") handleCreate(); if (e.key === "Escape") close() }}
          placeholder="e.g. Turmeric 2026, Spice Export Keywords..."
          style={{
            width: "100%", padding: "8px 10px", borderRadius: 7,
            border: "1px solid #d1d5db", fontSize: 13, boxSizing: "border-box",
            outline: "none",
          }}
        />
      </div>

      {/* Mode picker */}
      <div>
        <label style={{ fontSize: 11, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>Workflow</label>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {MODES.map(m => {
            const meta = MODE_META[m] || {}
            const st = MODE_STYLE[m] || MODE_STYLE.brand
            const active = mode === m
            return (
              <button
                key={m}
                onClick={() => setMode(m)}
                style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                  borderRadius: 7, border: active ? `2px solid ${st.badge}` : "1.5px solid #e5e7eb",
                  background: active ? st.bg : "#fff", cursor: "pointer", textAlign: "left",
                  transition: "all .12s",
                }}
              >
                <span style={{ fontSize: 16 }}>{st.icon}</span>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: active ? st.badge : "#374151" }}>{meta.title || m}</div>
                  <div style={{ fontSize: 11, color: "#6b7280" }}>{meta.subtitle || ""}</div>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 8, marginTop: "auto" }}>
        <button
          onClick={handleCreate}
          disabled={loading || !name.trim()}
          style={{
            flex: 1, padding: "8px 0", borderRadius: 7, fontSize: 13, fontWeight: 700,
            background: loading || !name.trim() ? "#d1d5db" : "#3b82f6",
            color: "#fff", border: "none", cursor: loading || !name.trim() ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Creating…" : "Create Session →"}
        </button>
        <button
          onClick={close}
          style={{
            padding: "8px 14px", borderRadius: 7, fontSize: 12,
            background: "#f3f4f6", color: "#374151", border: "1px solid #e5e7eb", cursor: "pointer",
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Single session card ───────────────────────────────────────────────────────

function SessionCard({ session, onOpen, onRename, selectable, selected, onToggleSelect }) {
  const [editName, setEditName] = useState("")
  const [editing, setEditing] = useState(false)
  const inputRef = useRef(null)
  const st = MODE_STYLE[session.mode] || MODE_STYLE.brand
  const label = sessionLabel(session)
  const validated = session.validated_total || 0
  const universe = session.universe_total || 0

  const startEdit = (e) => {
    e.stopPropagation()
    setEditName(label)
    setEditing(true)
    setTimeout(() => inputRef.current?.focus(), 30)
  }

  const commitEdit = () => {
    if (editName.trim() && editName.trim() !== label) onRename(session.id, editName.trim())
    setEditing(false)
  }

  const handleCardClick = () => {
    if (editing) return
    if (selectable) { onToggleSelect(session.id); return }
    onOpen(session.id, session.mode)
  }

  return (
    <div
      onClick={handleCardClick}
      style={{
        borderRadius: 12,
        border: selected
          ? "2px solid #3b82f6"
          : `1px solid ${st.border}`,
        background: selected ? "#eff6ff" : st.bg,
        padding: 18, cursor: "pointer",
        display: "flex", flexDirection: "column", gap: 0,
        transition: "all .15s", position: "relative",
        boxShadow: selected ? "0 0 0 3px rgba(59,130,246,.15)" : "0 1px 3px rgba(0,0,0,.05)",
        minHeight: 180,
      }}
      onMouseEnter={e => { if (!selected) { e.currentTarget.style.boxShadow = "0 4px 14px rgba(0,0,0,.10)"; e.currentTarget.style.transform = "translateY(-1px)" } }}
      onMouseLeave={e => { if (!selected) { e.currentTarget.style.boxShadow = "0 1px 3px rgba(0,0,0,.05)"; e.currentTarget.style.transform = "none" } }}
    >
      {/* Select checkbox (visible in bulk mode) */}
      {selectable && (
        <div
          onClick={e => { e.stopPropagation(); onToggleSelect(session.id) }}
          style={{
            position: "absolute", top: 12, right: 12, zIndex: 2,
            width: 20, height: 20, borderRadius: 5,
            border: selected ? "2px solid #3b82f6" : "2px solid #d1d5db",
            background: selected ? "#3b82f6" : "#fff",
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "pointer",
          }}
        >
          {selected && <span style={{ color: "#fff", fontSize: 12, lineHeight: 1 }}>✓</span>}
        </div>
      )}

      {/* Mode badge */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10, paddingRight: selectable ? 28 : 0 }}>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 4,
          padding: "2px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700,
          background: st.badgeBg, color: st.badge,
        }}>
          {st.icon} {st.label}
        </span>
        {!selectable && (
          <button
            onClick={startEdit}
            title="Rename"
            style={{
              background: "none", border: "none", cursor: "pointer",
              color: "#9ca3af", fontSize: 13, padding: "2px 4px", borderRadius: 4,
              lineHeight: 1,
            }}
          >✏</button>
        )}
      </div>

      {/* Session name */}
      {editing ? (
        <input
          ref={inputRef}
          value={editName}
          onChange={e => setEditName(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={e => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") setEditing(false) }}
          onClick={e => e.stopPropagation()}
          style={{
            fontSize: 16, fontWeight: 700, color: "#111827", padding: "2px 6px",
            borderRadius: 5, border: `2px solid ${st.badge}`, background: "#fff",
            width: "100%", boxSizing: "border-box", marginBottom: 4,
          }}
        />
      ) : (
        <div style={{
          fontSize: 16, fontWeight: 700, color: "#111827", lineHeight: 1.3,
          marginBottom: 4, wordBreak: "break-word",
        }}>
          {label}
        </div>
      )}

      {/* Seed keywords sub-label */}
      {session.seed_keywords?.length > 0 && !session.name && (
        <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 6 }}>
          {session.seed_keywords.slice(0, 4).join(" · ")}
          {session.seed_keywords.length > 4 && ` +${session.seed_keywords.length - 4}`}
        </div>
      )}

      {/* Keyword stats */}
      <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: st.badge }}>{universe.toLocaleString()}</div>
          <div style={{ fontSize: 10, color: "#6b7280" }}>universe</div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: validated > 0 ? "#10b981" : "#9ca3af" }}>
            {validated.toLocaleString()}
          </div>
          <div style={{ fontSize: 10, color: "#6b7280" }}>validated</div>
        </div>
      </div>

      {/* Phase progress dots */}
      <PhaseDots session={session} />

      {/* Footer */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "auto", paddingTop: 12 }}>
        <span style={{ fontSize: 11, color: "#9ca3af" }}>{timeAgo(session.created_at)}</span>
        {!selectable && (
          <span style={{
            fontSize: 12, fontWeight: 700, color: st.badge,
            display: "flex", alignItems: "center", gap: 3,
          }}>
            Open →
          </span>
        )}
      </div>
    </div>
  )
}

// ── Combined Keywords aggregate card ─────────────────────────────────────────

function CombinedKeywordsCard({ sessions }) {
  const totalUniverse = sessions.reduce((s, sess) => s + (sess.universe_total || 0), 0)
  const totalValidated = sessions.reduce((s, sess) => s + (sess.validated_total || 0), 0)
  const totalPhases = sessions.reduce((s, sess) => s + [1,2,3,4,5,6,7,8,9].filter(i => sess[`phase${i}_done`]).length, 0)
  const completedSessions = sessions.filter(s => [1,2,3,4,5,6,7,8,9].every(i => s[`phase${i}_done`])).length
  const allModes = [...new Set(sessions.map(s => s.mode).filter(Boolean))]

  return (
    <div style={{
      borderRadius: 12,
      border: "2px solid #6366f1",
      background: "linear-gradient(135deg, #f0f4ff 0%, #faf5ff 100%)",
      padding: 18,
      display: "flex", flexDirection: "column", gap: 0,
      boxShadow: "0 4px 16px rgba(99,102,241,.1)",
      minHeight: 180,
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Background accent */}
      <div style={{
        position: "absolute", top: -20, right: -20,
        width: 100, height: 100, borderRadius: "50%",
        background: "rgba(99,102,241,0.06)",
      }} />

      {/* Badge */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 4,
          padding: "2px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700,
          background: "#e0e7ff", color: "#4338ca",
        }}>
          🔗 All Sessions Combined
        </span>
        <span style={{ fontSize: 10, color: "#818cf8", fontWeight: 600 }}>
          {sessions.length} sessions
        </span>
      </div>

      {/* Title */}
      <div style={{ fontSize: 15, fontWeight: 800, color: "#1e1b4b", marginBottom: 4 }}>
        Combined Keywords
      </div>
      <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 10 }}>
        Aggregate across all research sessions
      </div>

      {/* Stats */}
      <div style={{ display: "flex", gap: 14, marginTop: 2, marginBottom: 8 }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: "#4338ca" }}>{totalUniverse.toLocaleString()}</div>
          <div style={{ fontSize: 10, color: "#6b7280" }}>universe</div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: totalValidated > 0 ? "#10b981" : "#9ca3af" }}>
            {totalValidated.toLocaleString()}
          </div>
          <div style={{ fontSize: 10, color: "#6b7280" }}>validated</div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: completedSessions > 0 ? "#8b5cf6" : "#9ca3af" }}>
            {completedSessions}
          </div>
          <div style={{ fontSize: 10, color: "#6b7280" }}>complete</div>
        </div>
      </div>

      {/* Mode badges */}
      {allModes.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
          {allModes.map(m => {
            const st = MODE_STYLE[m] || MODE_STYLE.brand
            return (
              <span key={m} style={{
                fontSize: 9, padding: "1px 6px", borderRadius: 8,
                background: st.badgeBg, color: st.badge, fontWeight: 600,
              }}>{st.icon} {st.label}</span>
            )
          })}
        </div>
      )}

      {/* Phase completion dot summary */}
      <div style={{ display: "flex", gap: 3, alignItems: "center", marginTop: "auto" }}>
        <div style={{ fontSize: 10, color: "#818cf8", fontWeight: 600 }}>
          {totalPhases} phase{totalPhases !== 1 ? "s" : ""} completed across all sessions
        </div>
      </div>
    </div>
  )
}

// ── Delete confirmation dialog ────────────────────────────────────────────────

function DeleteConfirm({ count, onConfirm, onCancel, deleting }) {
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "#fff", borderRadius: 14, padding: 28, maxWidth: 380, width: "90%",
        boxShadow: "0 20px 60px rgba(0,0,0,.25)",
      }}>
        <div style={{ fontSize: 28, marginBottom: 12, textAlign: "center" }}>🗑</div>
        <h3 style={{ margin: "0 0 8px", fontSize: 18, fontWeight: 800, textAlign: "center" }}>
          Delete {count} session{count !== 1 ? "s" : ""}?
        </h3>
        <p style={{ margin: "0 0 20px", fontSize: 13, color: "#6b7280", textAlign: "center", lineHeight: 1.5 }}>
          This will permanently delete the selected session{count !== 1 ? "s" : ""} and all their keyword data.
          This cannot be undone.
        </p>
        <div style={{ display: "flex", gap: 10 }}>
          <button
            onClick={onCancel}
            disabled={deleting}
            style={{
              flex: 1, padding: "10px 0", borderRadius: 8, border: "1px solid #e5e7eb",
              background: "#f9fafb", color: "#374151", fontWeight: 600, fontSize: 14,
              cursor: deleting ? "not-allowed" : "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            style={{
              flex: 1, padding: "10px 0", borderRadius: 8, border: "none",
              background: deleting ? "#fca5a5" : "#dc2626", color: "#fff",
              fontWeight: 700, fontSize: 14, cursor: deleting ? "not-allowed" : "pointer",
            }}
          >
            {deleting ? "Deleting…" : `Delete ${count}`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

export default function SessionDashboard({ projectId, onSelectSession, onCreateSession, creating }) {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [selected, setSelected] = useState(new Set())
  const [selectMode, setSelectMode] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    setError("")
    try {
      const res = await api.listSessions(projectId)
      setSessions(res.sessions || [])
    } catch (e) {
      setError(e?.message || "Failed to load sessions")
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleRename = useCallback(async (sid, name) => {
    try {
      await api.renameSession(projectId, sid, name)
      setSessions(prev => prev.map(s => s.id === sid ? { ...s, name } : s))
      setError("")
    } catch (e) {
      setError(e?.message || "Rename failed")
    }
  }, [projectId])

  const toggleSelect = useCallback((sid) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(sid)) next.delete(sid)
      else next.add(sid)
      return next
    })
  }, [])

  const exitSelectMode = () => {
    setSelectMode(false)
    setSelected(new Set())
  }

  const handleBulkDelete = async () => {
    setDeleting(true)
    try {
      const ids = [...selected]
      await api.bulkDeleteSessions(projectId, ids)
      setSessions(prev => prev.filter(s => !selected.has(s.id)))
      setSelected(new Set())
      setSelectMode(false)
      setConfirmDelete(false)
      setError("")
    } catch (e) {
      setError(e?.message || "Delete failed")
    } finally {
      setDeleting(false)
    }
  }

  const selectAll = () => setSelected(new Set(sessions.map(s => s.id)))

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "#9ca3af", fontSize: 14 }}>
        Loading sessions…
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      {!!error && (
        <div style={{
          border: "1px solid #fecaca",
          background: "#fef2f2",
          color: "#991b1b",
          borderRadius: 10,
          padding: "10px 12px",
          fontSize: 13,
          marginBottom: 12,
        }}>
          {error}
        </div>
      )}

      {confirmDelete && (
        <DeleteConfirm
          count={selected.size}
          onConfirm={handleBulkDelete}
          onCancel={() => setConfirmDelete(false)}
          deleting={deleting}
        />
      )}

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: -0.5 }}>
            🔬 Keyword Research
          </h2>
          <div style={{ fontSize: 13, color: "#6b7280", marginTop: 4 }}>
            {sessions.length > 0
              ? `${sessions.length} session${sessions.length !== 1 ? "s" : ""} for this project`
              : "No sessions yet — create your first one"}
          </div>
        </div>

        {sessions.length > 0 && (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {selectMode ? (
              <>
                <button
                  onClick={selectAll}
                  style={{
                    padding: "6px 12px", borderRadius: 7, border: "1px solid #d1d5db",
                    background: "#f9fafb", fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  Select All ({sessions.length})
                </button>
                {selected.size > 0 && (
                  <button
                    onClick={() => setConfirmDelete(true)}
                    style={{
                      padding: "6px 14px", borderRadius: 7, border: "none",
                      background: "#dc2626", color: "#fff", fontSize: 12,
                      fontWeight: 700, cursor: "pointer",
                      display: "flex", alignItems: "center", gap: 5,
                    }}
                  >
                    🗑 Delete {selected.size}
                  </button>
                )}
                <button
                  onClick={exitSelectMode}
                  style={{
                    padding: "6px 12px", borderRadius: 7, border: "1px solid #e5e7eb",
                    background: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer",
                    color: "#374151",
                  }}
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={() => setSelectMode(true)}
                style={{
                  padding: "6px 14px", borderRadius: 7, border: "1px solid #e5e7eb",
                  background: "#fff", fontSize: 12, fontWeight: 500, cursor: "pointer",
                  color: "#6b7280", display: "flex", alignItems: "center", gap: 5,
                }}
              >
                ☑ Select
              </button>
            )}
          </div>
        )}
      </div>

      {/* Combined keywords aggregate card — shown when 2+ sessions exist */}
      {sessions.length >= 2 && !selectMode && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", marginBottom: 8, textTransform: "uppercase", letterSpacing: ".05em" }}>
            📊 Project Summary
          </div>
          <CombinedKeywordsCard sessions={sessions} />
        </div>
      )}

      {/* Card grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
        gap: 16,
      }}>
        {/* New session card — hidden in select mode */}
        {!selectMode && <NewSessionCard onCreate={onCreateSession} loading={creating} />}

        {/* Existing session cards */}
        {sessions.map(s => (
          <SessionCard
            key={s.id}
            session={s}
            onOpen={onSelectSession}
            onRename={handleRename}
            selectable={selectMode}
            selected={selected.has(s.id)}
            onToggleSelect={toggleSelect}
          />
        ))}
      </div>

      {sessions.length === 0 && (
        <div style={{ textAlign: "center", padding: "40px 0", color: "#9ca3af", fontSize: 13 }}>
          Click the card above to start your first keyword research session.
        </div>
      )}
    </div>
  )
}
