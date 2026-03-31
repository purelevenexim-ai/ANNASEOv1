// ============================================================================
// PILLAR CONFIRMATION COMPONENT (Gate 2)
// Allows customers to review, edit, and confirm pillars identified in P10
// ============================================================================

import { useState, useEffect } from "react"
import fetchDebug from "../lib/fetchDebug"

const API = import.meta.env.VITE_API_URL || ""

async function apiCall(path, method = "GET", body = null) {
  const token = localStorage.getItem("annaseo_token")
  const url = `${API}${path}`
  const opts = { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) } }
  if (body) opts.body = JSON.stringify(body)
  const { res, parsed } = await fetchDebug(url, opts)
  return parsed
}

// ─────────────────────────────────────────────────────────────────────────────
// DESIGN TOKENS
// ─────────────────────────────────────────────────────────────────────────────

const T = {
  purple: "#7c3aed",
  purpleLight: "#f5f3ff",
  teal: "#0d9488",
  tealLight: "#f0fdfa",
  orange: "#ea580c",
  orangeLight: "#fff7ed",
  red: "#dc2626",
  green: "#16a34a",
  gray: "#6b7280",
  grayLight: "#f9fafb",
  border: "rgba(0,0,0,0.09)",
  text: "#111827",
  textSoft: "#6b7280",
}

// ─────────────────────────────────────────────────────────────────────────────
// SHARED UI COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

function Card({ children, style }) {
  return (
    <div
      style={{
        background: "#fff",
        border: `1px solid ${T.border}`,
        borderRadius: 12,
        padding: 20,
        marginBottom: 16,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

function Btn({ children, onClick, variant = "default", disabled, small, style }) {
  const base = {
    padding: small ? "5px 12px" : "8px 16px",
    borderRadius: 8,
    fontSize: small ? 11 : 13,
    fontWeight: 500,
    cursor: disabled ? "not-allowed" : "pointer",
    border: "none",
    transition: "all 0.15s",
    opacity: disabled ? 0.6 : 1,
    ...style,
  }

  const variants = {
    default: {
      background: T.purple,
      color: "#fff",
    },
    secondary: {
      background: T.grayLight,
      color: T.text,
    },
    success: {
      background: T.green,
      color: "#fff",
    },
    danger: {
      background: T.red,
      color: "#fff",
    },
    outline: {
      background: "transparent",
      border: `1px solid ${T.border}`,
      color: T.text,
    },
  }

  return (
    <button style={{ ...base, ...variants[variant] }} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  )
}

function InputField({ label, value, onChange, placeholder, type = "text", style }) {
  return (
    <div style={{ marginBottom: 12, ...style }}>
      {label && (
        <label
          style={{
            display: "block",
            fontSize: 12,
            fontWeight: 600,
            marginBottom: 6,
            color: T.gray,
          }}
        >
          {label}
        </label>
      )}
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        style={{
          width: "100%",
          padding: "8px 12px",
          borderRadius: 6,
          border: `1px solid ${T.border}`,
          fontSize: 13,
          fontFamily: "inherit",
          boxSizing: "border-box",
        }}
      />
    </div>
  )
}

function Badge({ children, variant = "default", style }) {
  const variants = {
    default: { background: T.purpleLight, color: T.purple },
    teal: { background: T.tealLight, color: T.teal },
    orange: { background: T.orangeLight, color: T.orange },
    outline: { background: "transparent", border: `1px solid ${T.border}` },
  }

  return (
    <span
      style={{
        display: "inline-block",
        padding: "3px 8px",
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 500,
        ...variants[variant],
        ...style,
      }}
    >
      {children}
    </span>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

export default function PillarConfirmation({ runId, onConfirmed, onCancel }) {
  const [pillars, setPillars] = useState([])
  const [loading, setLoading] = useState(true)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [editingIndex, setEditingIndex] = useState(null)
  const [notes, setNotes] = useState("")

  // NEW PILLAR FORM
  const [showNewForm, setShowNewForm] = useState(false)
  const [newPillar, setNewPillar] = useState({
    cluster_name: "",
    pillar_title: "",
    pillar_keyword: "",
    topics: [],
    article_count: 0,
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // LOAD PILLARS ON MOUNT
  // ─────────────────────────────────────────────────────────────────────────────

  useEffect(() => {
    loadPillars()
  }, [runId])

  async function loadPillars() {
    try {
      setLoading(true)
      const response = await apiCall(`/api/runs/${runId}/gate-2`)

      if (response.error) {
        setError(response.error)
        return
      }

      if (response.pillars && Array.isArray(response.pillars)) {
        setPillars(response.pillars)
      } else {
        setError("No pillars found for this run")
      }
    } catch (err) {
      setError(`Failed to load pillars: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // PILLAR OPERATIONS
  // ─────────────────────────────────────────────────────────────────────────────

  function editPillar(index, field, value) {
    const updated = [...pillars]
    updated[index] = { ...updated[index], [field]: value }
    setPillars(updated)
  }

  function removePillar(index) {
    setPillars(pillars.filter((_, i) => i !== index))
    setSuccess("")
  }

  function addNewPillar() {
    if (!newPillar.pillar_keyword.trim()) {
      setError("Pillar keyword required")
      return
    }

    setPillars([
      ...pillars,
      {
        cluster_name: newPillar.cluster_name || newPillar.pillar_keyword,
        pillar_title: newPillar.pillar_title || newPillar.pillar_keyword,
        pillar_keyword: newPillar.pillar_keyword,
        topics: newPillar.topics || [],
        article_count: newPillar.article_count || 0,
      },
    ])

    setNewPillar({
      cluster_name: "",
      pillar_title: "",
      pillar_keyword: "",
      topics: [],
      article_count: 0,
    })
    setShowNewForm(false)
    setSuccess("Pillar added successfully")
    setTimeout(() => setSuccess(""), 3000)
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // CONFIRM AND SUBMIT
  // ─────────────────────────────────────────────────────────────────────────────

  async function handleConfirm() {
    if (!pillars.length) {
      setError("At least one pillar is required")
      return
    }

    try {
      setConfirming(true)
      setError("")

      const response = await apiCall(`/api/runs/${runId}/gate-2`, "POST", {
        pillars: pillars,
        confirmed_by: localStorage.getItem("user_email") || "user",
        notes: notes,
      })

      if (response.error) {
        setError(response.error)
        return
      }

      setSuccess(`✓ Confirmed ${pillars.length} pillars successfully`)

      // Call parent callback
      if (onConfirmed) {
        setTimeout(() => onConfirmed(pillars), 500)
      }
    } catch (err) {
      setError(`Confirmation failed: ${err.message}`)
    } finally {
      setConfirming(false)
    }
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <Card style={{ textAlign: "center", padding: 40 }}>
        <div style={{ fontSize: 14, color: T.textSoft }}>Loading pillars...</div>
      </Card>
    )
  }

  return (
    <div style={{ maxWidth: 1000 }}>
      {/* HEADER */}
      <Card style={{ background: T.tealLight, border: `1px solid ${T.teal}` }}>
        <h2 style={{ margin: "0 0 8px 0", color: T.teal, fontSize: 20 }}>✓ Gate 2: Pillar Confirmation</h2>
        <p style={{ margin: 0, fontSize: 12, color: T.textSoft }}>
          Review and confirm the pillars generated by P10. Edit as needed, then submit to proceed to P11 (Knowledge Graph).
        </p>
      </Card>

      {/* ERROR */}
      {error && (
        <Card style={{ background: "#fed7d7", border: `1px solid ${T.red}`, padding: 12 }}>
          <div style={{ fontSize: 12, color: T.red, fontWeight: 500 }}>⚠ {error}</div>
        </Card>
      )}

      {/* SUCCESS */}
      {success && (
        <Card style={{ background: "#dcfce7", border: `1px solid ${T.green}`, padding: 12 }}>
          <div style={{ fontSize: 12, color: T.green, fontWeight: 500 }}>{success}</div>
        </Card>
      )}

      {/* PILLARS LIST */}
      {pillars.map((pillar, idx) => (
        <Card key={idx} style={{ borderLeft: `4px solid ${T.orange}` }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: 12 }}>
            <div style={{ flex: 1 }}>
              <InputField
                label="Pillar Title"
                value={pillar.pillar_title}
                onChange={e => editPillar(idx, "pillar_title", e.target.value)}
                placeholder="Pillar title (e.g., Cinnamon Health Benefits)"
              />
              <InputField
                label="Pillar Keyword"
                value={pillar.pillar_keyword}
                onChange={e => editPillar(idx, "pillar_keyword", e.target.value)}
                placeholder="Primary keyword"
              />
              <InputField
                label="Cluster Name"
                value={pillar.cluster_name}
                onChange={e => editPillar(idx, "cluster_name", e.target.value)}
                placeholder="Cluster grouping"
              />
            </div>
            <div style={{ marginLeft: 16 }}>
              <Btn
                small
                variant="danger"
                onClick={() => removePillar(idx)}
                style={{ marginBottom: 8, width: 80 }}
              >
                Remove
              </Btn>
            </div>
          </div>

          {/* TOPICS */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 6, color: T.gray }}>
              Topics ({pillar.topics?.length || 0})
            </label>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {pillar.topics && pillar.topics.length > 0 ? (
                pillar.topics.map((topic, i) => (
                  <Badge key={i} variant="teal">
                    {topic}
                  </Badge>
                ))
              ) : (
                <span style={{ fontSize: 12, color: T.textSoft }}>No topics assigned</span>
              )}
            </div>
          </div>

          {/* ARTICLE COUNT */}
          <InputField
            label="Expected Articles"
            type="number"
            value={pillar.article_count || 0}
            onChange={e => editPillar(idx, "article_count", parseInt(e.target.value) || 0)}
            placeholder="0"
          />
        </Card>
      ))}

      {/* ADD NEW PILLAR */}
      {!showNewForm ? (
        <Btn variant="outline" onClick={() => setShowNewForm(true)} style={{ marginBottom: 16, width: "100%" }}>
          + Add New Pillar
        </Btn>
      ) : (
        <Card style={{ background: T.grayLight }}>
          <h3 style={{ margin: "0 0 16px 0", fontSize: 14, color: T.text }}>Add New Pillar</h3>

          <InputField
            label="Pillar Title"
            value={newPillar.pillar_title}
            onChange={e => setNewPillar({ ...newPillar, pillar_title: e.target.value })}
            placeholder="Pillar title"
          />
          <InputField
            label="Pillar Keyword *"
            value={newPillar.pillar_keyword}
            onChange={e => setNewPillar({ ...newPillar, pillar_keyword: e.target.value })}
            placeholder="Primary keyword (required)"
          />
          <InputField
            label="Cluster Name"
            value={newPillar.cluster_name}
            onChange={e => setNewPillar({ ...newPillar, cluster_name: e.target.value })}
            placeholder="Cluster grouping"
          />
          <InputField
            label="Expected Articles"
            type="number"
            value={newPillar.article_count}
            onChange={e => setNewPillar({ ...newPillar, article_count: parseInt(e.target.value) || 0 })}
            placeholder="0"
          />

          <div style={{ display: "flex", gap: 8 }}>
            <Btn small variant="success" onClick={addNewPillar}>
              Add
            </Btn>
            <Btn small variant="secondary" onClick={() => setShowNewForm(false)}>
              Cancel
            </Btn>
          </div>
        </Card>
      )}

      {/* NOTES */}
      <Card>
        <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 8, color: T.gray }}>
          Notes (Optional)
        </label>
        <textarea
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Any notes on pillar confirmations..."
          style={{
            width: "100%",
            minHeight: 80,
            padding: 12,
            borderRadius: 6,
            border: `1px solid ${T.border}`,
            fontSize: 13,
            fontFamily: "inherit",
            boxSizing: "border-box",
          }}
        />
      </Card>

      {/* ACTION BUTTONS */}
      <div style={{ display: "flex", gap: 12, justifyContent: "flex-end", marginTop: 20 }}>
        <Btn variant="secondary" onClick={onCancel} disabled={confirming}>
          Cancel
        </Btn>
        <Btn
          variant="success"
          onClick={handleConfirm}
          disabled={confirming || pillars.length === 0}
          style={{ minWidth: 120 }}
        >
          {confirming ? "Confirming..." : `✓ Confirm (${pillars.length})`}
        </Btn>
      </div>

      {/* PILLAR SUMMARY */}
      <Card style={{ background: T.purpleLight, marginTop: 16, fontSize: 12 }}>
        <strong style={{ color: T.purple }}>Summary:</strong>
        <div style={{ margin: "8px 0 0 0", color: T.text }}>
          • <strong>{pillars.length}</strong> pillars confirmed
          <br />
          • <strong>{pillars.reduce((sum, p) => sum + (p.article_count || 0), 0)}</strong> expected articles
          <br />
          • Ready to proceed to P11 (Knowledge Graph)
        </div>
      </Card>
    </div>
  )
}
