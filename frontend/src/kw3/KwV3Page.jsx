/**
 * Keyword V3 — Clean 4-tab keyword pipeline.
 *
 * Tabs:
 *   1. Business Analysis  (Phase 1)
 *   2. Generate           (Autosuggest + Phase 2 stream)
 *   3. Score & Validate   (Phase 3 + Phase 4 + top-20/pillar approve/delete)
 *   4. Strategy           (Phase 5 + 6 + 7 + 8 + 9 bundled)
 */
import React, { useEffect, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  listSessions, createSession, deleteSession, getSession,
} from "./api"
import { T, Btn, Spinner, Empty, Badge } from "./ui"
import TabBusiness from "./TabBusiness"
import TabGenerate from "./TabGenerate"
import TabValidateScore from "./TabValidateScore"
import TabStrategy from "./TabStrategy"

const TABS = [
  { id: "business", label: "1. Business Analysis", icon: "🏢" },
  { id: "generate", label: "2. Generate",          icon: "🔍" },
  { id: "validate", label: "3. Score & Validate",  icon: "✓" },
  { id: "strategy", label: "4. Strategy & Plan",   icon: "🌳" },
]

const LS_TAB = "kw3:activeTab"
const LS_SID = "kw3:activeSession"

export default function KwV3Page({ projectId, setPage }) {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem(LS_TAB) || "business")
  const [activeSid, setActiveSid] = useState(() => localStorage.getItem(LS_SID) || "")

  useEffect(() => { localStorage.setItem(LS_TAB, activeTab) }, [activeTab])
  useEffect(() => { if (activeSid) localStorage.setItem(LS_SID, activeSid) }, [activeSid])

  // ── Sessions list ─────────────────────────────────────────────────────────
  const sessionsQ = useQuery({
    queryKey: ["kw3", projectId, "sessions"],
    queryFn: () => listSessions(projectId),
    enabled: !!projectId,
    staleTime: 10_000,
  })
  const sessions = sessionsQ.data?.sessions || []

  // Pick a sensible default session
  useEffect(() => {
    if (!sessions.length) { return }
    const exists = sessions.some(s => s.id === activeSid)
    if (!exists) setActiveSid(sessions[0].id)
  }, [sessions, activeSid])

  const sessionQ = useQuery({
    queryKey: ["kw3", projectId, "session", activeSid],
    queryFn: () => getSession(projectId, activeSid),
    enabled: !!(projectId && activeSid),
    staleTime: 5_000,
  })
  const session = sessionQ.data?.session || sessionQ.data || null

  const createMut = useMutation({
    mutationFn: (name) => createSession(projectId, name),
    onSuccess: (res) => {
      const sid = res?.session_id || res?.session?.id
      if (sid) setActiveSid(sid)
      qc.invalidateQueries({ queryKey: ["kw3", projectId, "sessions"] })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (sid) => deleteSession(projectId, sid),
    onSuccess: () => {
      setActiveSid("")
      qc.invalidateQueries({ queryKey: ["kw3", projectId, "sessions"] })
    },
  })

  if (!projectId) {
    return (
      <div style={{ padding: 32 }}>
        <Empty
          icon="📁"
          title="Select a project to begin"
          hint="Choose a project from the dashboard, then come back to start the keyword pipeline."
          action={<Btn onClick={() => setPage?.("dashboard")}>Go to Dashboard</Btn>}
        />
      </div>
    )
  }

  // ── Phase status helper ───────────────────────────────────────────────────
  const phase = {
    p1: !!session?.phase1_done,
    p2: !!session?.phase2_done,
    p3: !!session?.phase3_done,
    p4: !!session?.phase4_done,
    p5: !!session?.phase5_done,
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ background: T.bg, minHeight: "100vh", padding: "20px 24px" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 16, gap: 16, flexWrap: "wrap",
      }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: T.text }}>Keywords V3</div>
          <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
            Clean 4-step keyword pipeline
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <SessionPicker
            sessions={sessions}
            activeSid={activeSid}
            onSelect={setActiveSid}
            loading={sessionsQ.isLoading}
          />
          <Btn
            variant="secondary"
            onClick={() => {
              const name = prompt("Session name (optional):", "")
              if (name === null) return
              createMut.mutate(name)
            }}
            disabled={createMut.isPending}
          >
            {createMut.isPending ? <Spinner /> : "+ New session"}
          </Btn>
          {activeSid && (
            <Btn
              variant="ghost"
              onClick={() => {
                if (confirm("Delete this session? This cannot be undone.")) {
                  deleteMut.mutate(activeSid)
                }
              }}
              disabled={deleteMut.isPending}
            >
              🗑
            </Btn>
          )}
        </div>
      </div>

      {/* Tab navigation */}
      <div style={{
        display: "flex", gap: 4, padding: 4,
        background: T.card, border: `1px solid ${T.border}`,
        borderRadius: 10, marginBottom: 16,
      }}>
        {TABS.map(t => {
          const active = activeTab === t.id
          const done = ({
            business: phase.p1, generate: phase.p2,
            validate: phase.p4, strategy: !!session?.phase9_done,
          })[t.id]
          return (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              style={{
                flex: 1, padding: "10px 14px",
                background: active ? T.primary : "transparent",
                color: active ? "#fff" : T.text,
                border: "none", borderRadius: 7, cursor: "pointer",
                fontSize: 13, fontWeight: 600,
                display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                transition: "all .15s",
              }}
            >
              <span>{t.icon}</span>
              <span>{t.label}</span>
              {done && !active && <Badge color={T.success}>✓</Badge>}
            </button>
          )
        })}
      </div>

      {/* Body */}
      {!activeSid ? (
        <Empty
          icon="📝"
          title="No session yet"
          hint="Create a new session to start a fresh keyword pipeline run."
          action={
            <Btn onClick={() => createMut.mutate("")} disabled={createMut.isPending}>
              {createMut.isPending ? <Spinner /> : "Create first session"}
            </Btn>
          }
        />
      ) : sessionQ.isLoading ? (
        <div style={{ padding: 40, textAlign: "center" }}><Spinner size={20} /></div>
      ) : (
        <div>
          {activeTab === "business" && (
            <TabBusiness
              projectId={projectId} sessionId={activeSid} session={session}
              onDone={() => setActiveTab("generate")}
            />
          )}
          {activeTab === "generate" && (
            <TabGenerate
              projectId={projectId} sessionId={activeSid} session={session}
              onDone={() => setActiveTab("validate")}
            />
          )}
          {activeTab === "validate" && (
            <TabValidateScore
              projectId={projectId} sessionId={activeSid} session={session}
              onDone={() => setActiveTab("strategy")}
            />
          )}
          {activeTab === "strategy" && (
            <TabStrategy
              projectId={projectId} sessionId={activeSid} session={session}
            />
          )}
        </div>
      )}
    </div>
  )
}

function SessionPicker({ sessions, activeSid, onSelect, loading }) {
  if (loading) return <Spinner />
  if (!sessions.length) return <span style={{ fontSize: 12, color: T.textMute }}>No sessions yet</span>
  return (
    <select
      value={activeSid || ""}
      onChange={e => onSelect(e.target.value)}
      style={{
        padding: "8px 12px", border: `1px solid ${T.border}`,
        borderRadius: 7, fontSize: 13, background: T.card,
        color: T.text, minWidth: 200, cursor: "pointer",
      }}
    >
      {sessions.map(s => (
        <option key={s.id} value={s.id}>
          {s.name || `Session ${(s.id || "").slice(0, 8)}`} · {fmtDate(s.created_at)}
        </option>
      ))}
    </select>
  )
}

function fmtDate(s) {
  if (!s) return ""
  try {
    const d = new Date(s)
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
  } catch { return "" }
}
