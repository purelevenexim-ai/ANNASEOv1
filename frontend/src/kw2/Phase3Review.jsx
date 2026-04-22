/**
 * Phase 3 Review — Manual keyword review between validation and scoring.
 * Users can: edit keyword/pillar/intent, delete, add manually, filter by pillar.
 * After review, proceed to Phase 4 scoring.
 */
import React, { useState, useCallback, useEffect } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, Badge, RunButton, Spinner, StatsRow } from "./shared"
import ConfirmModal from "./ConfirmModal"

const INTENT_OPTIONS = ["purchase", "wholesale", "transactional", "commercial", "informational", "navigational"]
const INTENT_COLORS = {
  purchase: "green", wholesale: "purple", transactional: "green",
  commercial: "yellow", informational: "gray", navigational: "blue",
}

function EditRow({ kw, pillars, onSave, onDelete }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ keyword: kw.keyword, pillar: kw.pillar || "", intent: kw.intent || "informational", mapped_page: kw.mapped_page || "" })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    await onSave(kw.id, form)
    setSaving(false)
    setEditing(false)
  }

  if (editing) {
    return (
      <tr style={{ background: "#fafff5", borderBottom: "1px solid #d1fae5" }}>
        <td style={{ padding: "6px 8px" }}>
          <input
            style={{ width: "100%", padding: "4px 6px", border: "1px solid #6ee7b7", borderRadius: 4, fontSize: 12 }}
            value={form.keyword}
            onChange={(e) => setForm({ ...form, keyword: e.target.value })}
          />
        </td>
        <td style={{ padding: "6px 8px" }}>
          <select
            style={{ padding: "4px 6px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 12, width: "100%" }}
            value={form.pillar}
            onChange={(e) => setForm({ ...form, pillar: e.target.value })}
          >
            {pillars.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </td>
        <td style={{ padding: "6px 8px" }}>
          <select
            style={{ padding: "4px 6px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 12 }}
            value={form.intent}
            onChange={(e) => setForm({ ...form, intent: e.target.value })}
          >
            {INTENT_OPTIONS.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
        </td>
        <td style={{ padding: "6px 8px" }}>
          <input
            style={{ padding: "4px 6px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 12, width: "100%" }}
            placeholder="Page URL"
            value={form.mapped_page}
            onChange={(e) => setForm({ ...form, mapped_page: e.target.value })}
          />
        </td>
        <td style={{ padding: "6px 8px", textAlign: "right" }}>{(kw.final_score || 0).toFixed(2)}</td>
        <td style={{ padding: "6px 8px" }}>
          <div style={{ display: "flex", gap: 4 }}>
            <button onClick={save} disabled={saving} style={btnStyle("green")}>{saving ? "..." : "✓"}</button>
            <button onClick={() => setEditing(false)} style={btnStyle("gray")}>✕</button>
          </div>
        </td>
      </tr>
    )
  }

  return (
    <tr style={{ borderBottom: "1px solid #f3f4f6" }}>
      <td style={{ padding: "5px 8px", fontSize: 13 }}>{kw.keyword}</td>
      <td style={{ padding: "5px 8px" }}><Badge color="blue">{kw.pillar || "-"}</Badge></td>
      <td style={{ padding: "5px 8px" }}><Badge color={INTENT_COLORS[kw.intent] || "gray"}>{kw.intent || "-"}</Badge></td>
      <td style={{ padding: "5px 8px", fontSize: 11, color: "#9ca3af", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }}>{kw.mapped_page || "-"}</td>
      <td style={{ padding: "5px 8px", textAlign: "right", fontWeight: 600, fontSize: 12 }}>{(kw.final_score || 0).toFixed(2)}</td>
      <td style={{ padding: "5px 8px" }}>
        <div style={{ display: "flex", gap: 4 }}>
          <button onClick={() => setEditing(true)} style={btnStyle("blue")}>✏</button>
          <button onClick={() => onDelete(kw.id)} style={btnStyle("red")}>🗑</button>
        </div>
      </td>
    </tr>
  )
}

function btnStyle(color) {
  const C = { green: "#10b981", blue: "#3b82f6", red: "#ef4444", gray: "#9ca3af" }
  return {
    background: C[color] || "#9ca3af", color: "#fff", border: "none",
    borderRadius: 4, padding: "3px 7px", cursor: "pointer", fontSize: 12,
  }
}

export default function Phase3Review({ projectId, sessionId, onProceed, onRegenerate, onComplete }) {
  const { setValidatedCount, setActivePhase, pushLog, addToast } = useKw2Store()
  const handleProceed = onProceed || (() => { if (onComplete) onComplete(); setActivePhase(4) })
  const handleRegenerate = onRegenerate || (() => setActivePhase(2))
  const [keywords, setKeywords] = useState([])
  const [loading, setLoading] = useState(true)
  const [pillarFilter, setPillarFilter] = useState("")
  const [search, setSearch] = useState("")
  const [addForm, setAddForm] = useState({ keyword: "", pillar: "", intent: "purchase", mapped_page: "" })
  const [adding, setAdding] = useState(false)
  const [showAddRow, setShowAddRow] = useState(false)
  const [pendingDeleteId, setPendingDeleteId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getValidated(projectId, sessionId)
      setKeywords(data.items || [])
      setValidatedCount((data.items || []).length)
    } catch (e) {
      addToast("Failed to load keywords: " + e.message, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  useEffect(() => { load() }, [])

  const handleSave = useCallback(async (id, form) => {
    await api.updateKeyword(projectId, sessionId, id, form)
    setKeywords((prev) => prev.map((k) => k.id === id ? { ...k, ...form } : k))
    pushLog(`Updated keyword: ${form.keyword}`, { badge: "REVIEW", type: "success" })
  }, [projectId, sessionId])

  const handleDelete = useCallback(async (id) => {
    setPendingDeleteId(id)
  }, [])

  const confirmDelete = useCallback(async () => {
    const id = pendingDeleteId
    setPendingDeleteId(null)
    if (!id) return
    try {
      await api.deleteKeyword(projectId, sessionId, id)
      setKeywords((prev) => prev.filter((k) => k.id !== id))
      setValidatedCount((c) => Math.max(0, c - 1))
      pushLog("Keyword deleted", { badge: "REVIEW", type: "warning" })
    } catch (e) {
      addToast("Delete failed: " + e.message, "error")
    }
  }, [projectId, sessionId, pendingDeleteId])

  const handleAdd = useCallback(async () => {
    if (!addForm.keyword.trim()) return
    setAdding(true)
    try {
      const data = await api.addKeyword(projectId, sessionId, { ...addForm, pillar: addForm.pillar || pillars[0] || "general" })
      setKeywords((prev) => [{ id: data.id, ...addForm, final_score: 0.5, source: "manual" }, ...prev])
      setValidatedCount((c) => c + 1)
      setAddForm({ keyword: "", pillar: addForm.pillar, intent: "purchase", mapped_page: "" })
      setShowAddRow(false)
      pushLog(`Added keyword: ${addForm.keyword}`, { badge: "REVIEW", type: "success" })
      addToast("Keyword added", "success")
    } catch (e) {
      addToast("Failed to add: " + e.message, "error")
    }
    setAdding(false)
  }, [projectId, sessionId, addForm])

  const pillars = [...new Set(keywords.map((k) => k.pillar).filter(Boolean))]
  const filtered = keywords.filter((k) => {
    if (pillarFilter && k.pillar !== pillarFilter) return false
    if (search && !k.keyword.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  // Per-pillar counts for sidebar
  const pillarCounts = pillars.map((p) => ({
    pillar: p,
    count: keywords.filter((k) => k.pillar === p).length,
    target: 100,
  }))

  if (loading) return <Spinner text="Loading validated keywords..." />

  return (
    <div>
      <ConfirmModal
        open={!!pendingDeleteId}
        title="Delete this keyword?"
        message="This action cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setPendingDeleteId(null)}
      />
      {/* Header Card */}
      <Card
        title="Phase 3 Review: Manual Keyword Review"
        actions={
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleRegenerate}
              style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid #f59e0b", background: "#fef3c7", color: "#92400e", fontWeight: 600, fontSize: 13, cursor: "pointer" }}
            >
              ↺ Regenerate from Phase 2
            </button>
            <RunButton onClick={handleProceed}>
              Proceed to Phase 4: Score →
            </RunButton>
          </div>
        }
      >
        <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>
          Review, edit, delete, or add keywords manually. Then proceed to Phase 4 scoring. Target: <strong>100 keywords per pillar</strong>.
        </p>

        {/* Per-pillar progress bars */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          {pillarCounts.map(({ pillar, count, target }) => (
            <div key={pillar} style={{ flex: "1 1 160px", minWidth: 140 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: count >= target ? "#10b981" : "#f59e0b" }}>{pillar}</span>
                <span style={{ fontSize: 11, color: count >= target ? "#10b981" : "#6b7280" }}>{count}/{target}</span>
              </div>
              <div style={{ height: 6, background: "#e5e7eb", borderRadius: 3, overflow: "hidden" }}>
                <div style={{
                  height: "100%", width: `${Math.min(100, (count / target) * 100)}%`,
                  background: count >= target ? "#10b981" : count >= target * 0.7 ? "#f59e0b" : "#ef4444",
                  borderRadius: 3, transition: "width 400ms",
                }} />
              </div>
            </div>
          ))}
        </div>

        <StatsRow items={[
          { label: "Total Keywords", value: keywords.length, color: "#3b82f6" },
          { label: "Pillars", value: pillars.length, color: "#10b981" },
          { label: "At Target (≥100)", value: pillarCounts.filter((p) => p.count >= 100).length, color: "#8b5cf6" },
          { label: "Under Target", value: pillarCounts.filter((p) => p.count < 100).length, color: "#f59e0b" },
        ]} />
      </Card>

      {/* Keyword Table Card */}
      <Card title={`Keywords (${filtered.length} shown)`} actions={
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            style={{ padding: "5px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 12, width: 180 }}
            placeholder="Search keywords..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            style={{ padding: "5px 8px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 12 }}
            value={pillarFilter}
            onChange={(e) => setPillarFilter(e.target.value)}
          >
            <option value="">All pillars ({keywords.length})</option>
            {pillars.map((p) => (
              <option key={p} value={p}>{p} ({keywords.filter((k) => k.pillar === p).length})</option>
            ))}
          </select>
          <button
            onClick={() => setShowAddRow(!showAddRow)}
            style={{ padding: "5px 12px", borderRadius: 6, border: "none", background: "#10b981", color: "#fff", fontWeight: 600, fontSize: 12, cursor: "pointer" }}
          >
            + Add Keyword
          </button>
        </div>
      }>
        {/* Add row */}
        {showAddRow && (
          <div style={{ display: "flex", gap: 8, padding: "10px 0", borderBottom: "2px solid #d1fae5", marginBottom: 8, flexWrap: "wrap" }}>
            <input
              style={{ flex: "2 1 200px", padding: "6px 10px", border: "1px solid #6ee7b7", borderRadius: 6, fontSize: 13 }}
              placeholder="New keyword text..."
              value={addForm.keyword}
              onChange={(e) => setAddForm({ ...addForm, keyword: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            />
            <select
              style={{ flex: "1 1 120px", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 12 }}
              value={addForm.pillar}
              onChange={(e) => setAddForm({ ...addForm, pillar: e.target.value })}
            >
              <option value="">Select pillar...</option>
              {pillars.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <select
              style={{ flex: "1 1 120px", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 12 }}
              value={addForm.intent}
              onChange={(e) => setAddForm({ ...addForm, intent: e.target.value })}
            >
              {INTENT_OPTIONS.map((i) => <option key={i} value={i}>{i}</option>)}
            </select>
            <button onClick={handleAdd} disabled={adding || !addForm.keyword.trim()} style={{ ...btnStyle("green"), padding: "6px 14px", fontSize: 13 }}>
              {adding ? "Adding..." : "Add"}
            </button>
            <button onClick={() => setShowAddRow(false)} style={{ ...btnStyle("gray"), padding: "6px 10px" }}>Cancel</button>
          </div>
        )}

        <div style={{ overflowX: "auto", maxHeight: 520, overflowY: "auto" }}>
          <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
            <thead style={{ position: "sticky", top: 0, background: "#f9fafb", zIndex: 1 }}>
              <tr style={{ borderBottom: "2px solid #e5e7eb" }}>
                <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Keyword</th>
                <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Pillar</th>
                <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Intent</th>
                <th style={{ textAlign: "left", padding: "6px 8px", fontWeight: 600 }}>Page</th>
                <th style={{ textAlign: "right", padding: "6px 8px", fontWeight: 600 }}>Score</th>
                <th style={{ padding: "6px 8px", fontWeight: 600 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((kw) => (
                <EditRow
                  key={kw.id}
                  kw={kw}
                  pillars={pillars}
                  onSave={handleSave}
                  onDelete={handleDelete}
                />
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <p style={{ color: "#9ca3af", textAlign: "center", padding: 20 }}>No keywords match your filter.</p>
          )}
        </div>
        {filtered.length > 0 && (
          <p style={{ fontSize: 11, color: "#9ca3af", textAlign: "right", padding: "4px 0" }}>
            Showing {filtered.length} of {keywords.length} keywords
          </p>
        )}
      </Card>
    </div>
  )
}
