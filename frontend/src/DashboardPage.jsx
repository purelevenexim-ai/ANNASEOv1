import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { T, api, useStore, Badge, Btn, LoadingSpinner, EditProjectModal, ConfirmModal } from "./App"

// ── Stat card with large display number ──────────────────────────────────────
function DashStat({ label, value, sub, color, accentColor }) {
  return (
    <div style={{
      background: "#FFFFFF",
      borderRadius: 14,
      padding: "18px 20px",
      boxShadow: T.cardShadow,
      borderTop: `3px solid ${accentColor || color || T.purple}`,
      display: "flex",
      flexDirection: "column",
      gap: 4,
    }}>
      <div style={{ fontSize: 11, color: T.textSoft, fontWeight: 500, letterSpacing: 0.4, textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{
        fontSize: 36,
        fontWeight: 700,
        color: color || T.text,
        lineHeight: 1.05,
        letterSpacing: -1,
      }}>
        {value ?? "—"}
      </div>
      {sub && <div style={{ fontSize: 11, color: T.textSoft }}>{sub}</div>}
    </div>
  )
}

// ── Project card ─────────────────────────────────────────────────────────────
function ProjectCard({ project: p, isActive, onSelect, onEdit, onDelete }) {
  const seeds = (() => {
    try { return JSON.parse(p.seed_keywords || "[]").slice(0, 3) } catch { return [] }
  })()
  const statusAccent = { active: T.teal, paused: T.amber, archived: T.gray }[p.status] || T.gray

  return (
    <div
      onClick={onSelect}
      style={{
        background: isActive ? T.purpleLight : "#fff",
        borderRadius: 14,
        padding: "16px 18px",
        cursor: "pointer",
        boxShadow: T.cardShadow,
        borderLeft: `4px solid ${isActive ? T.purple : statusAccent}`,
        transition: "transform 0.15s ease, box-shadow 0.15s ease",
        position: "relative",
      }}
      onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,0,0,0.1)" }}
      onMouseLeave={e => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.boxShadow = T.cardShadow }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 14,
            fontWeight: 600,
            color: T.text,
            lineHeight: 1.2,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}>
            {p.name}
          </div>
          {p.industry && (
            <div style={{ fontSize: 10, color: T.textSoft, marginTop: 3 }}>{p.industry}</div>
          )}
        </div>
        <div style={{ display: "flex", gap: 4, alignItems: "center", marginLeft: 8, flexShrink: 0 }}>
          <Badge color={p.status === "active" ? "teal" : "gray"}>{p.status}</Badge>
          <button
            onClick={e => { e.stopPropagation(); onEdit() }}
            style={{ background: "none", border: "none", cursor: "pointer", color: T.gray, fontSize: 13, padding: "0 2px", lineHeight: 1 }}
            title="Edit"
          >✎</button>
          <button
            onClick={e => { e.stopPropagation(); onDelete() }}
            style={{ background: "none", border: "none", cursor: "pointer", color: T.red, fontSize: 11, padding: "0 2px", lineHeight: 1 }}
            title="Delete"
          >✕</button>
        </div>
      </div>

      {seeds.length > 0 ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {seeds.map((s, i) => (
            <span key={i} style={{
              fontSize: 10, padding: "2px 7px", borderRadius: 99,
              background: isActive ? "rgba(127,119,221,0.15)" : "rgba(0,0,0,0.05)",
              color: T.textSoft,
            }}>{s}</span>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 10, color: T.textSoft, opacity: 0.6 }}>No seed keywords yet</div>
      )}

      {isActive && (
        <div style={{
          position: "absolute", top: 12, right: 12,
          width: 7, height: 7, borderRadius: "50%",
          background: T.purple,
          boxShadow: `0 0 0 3px ${T.purpleLight}`,
        }}/>
      )}
    </div>
  )
}

// ── Engine health pill row ────────────────────────────────────────────────────
function EngineHealthBar({ health }) {
  if (!health) return null
  const engines = health.engines || {}
  const allOk = health.all_ok

  return (
    <div style={{
      background: "#fff",
      borderRadius: 12,
      padding: "12px 16px",
      boxShadow: T.cardShadow,
      marginBottom: 20,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <div style={{
          width: 8, height: 8, borderRadius: "50%",
          background: allOk ? T.teal : T.amber,
          boxShadow: allOk ? `0 0 0 3px ${T.tealLight}` : `0 0 0 3px ${T.amberLight}`,
        }}/>
        <span style={{ fontSize: 11, fontWeight: 600, color: T.text }}>Engine Health</span>
        <span style={{ fontSize: 10, color: allOk ? T.teal : T.amber }}>
          {allOk ? "All systems operational" : "Some engines need attention"}
        </span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {Object.entries(engines).map(([name, status]) => (
          <span key={name} style={{
            display: "inline-flex", alignItems: "center", gap: 5,
            padding: "3px 9px", borderRadius: 99, fontSize: 10,
            background: status === "ok" ? T.tealLight : "#FEE2E2",
            color: status === "ok" ? T.teal : T.red,
          }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "currentColor" }}/>
            {name}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Cost strip ────────────────────────────────────────────────────────────────
function CostStrip({ costs }) {
  if (!costs) return null
  const items = [
    { label: "Total spent",        value: `$${costs.total_usd ?? "0.00"}` },
    { label: "Articles generated", value: costs.articles_generated ?? 0 },
    { label: "Cost per article",   value: `$${costs.cost_per_article ?? "0.00"}` },
    { label: "Est. monthly",       value: `$${costs.monthly_estimate ?? "0.00"}` },
  ]
  return (
    <div style={{
      background: "#007AFF",
      borderRadius: 16,
      padding: "18px 22px",
      display: "grid",
      gridTemplateColumns: "repeat(4, 1fr)",
      gap: 16,
      marginTop: 20,
    }}>
      {items.map(({ label, value }) => (
        <div key={label}>
          <div style={{
            fontSize: 10, color: "rgba(255,255,255,0.65)",
            marginBottom: 5, textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 500,
          }}>
            {label}
          </div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#fff", lineHeight: 1, letterSpacing: -0.5 }}>
            {value}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { activeProject, setPage, setProject } = useStore()
  const qclient = useQueryClient()
  const [editingProject, setEditingProject] = useState(null)
  const [deletingProject, setDeletingProject] = useState(null)

  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.get("/api/projects").then(r => r?.projects || []),
  })
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get("/api/health"),
    refetchInterval: 30000,
  })
  const { data: costs } = useQuery({
    queryKey: ["costs", activeProject],
    queryFn: () => activeProject ? api.get(`/api/costs/${activeProject}`) : null,
    enabled: !!activeProject,
  })
  const { data: kwStats } = useQuery({
    queryKey: ["kw-stats", activeProject],
    queryFn: () => activeProject ? api.get(`/api/projects/${activeProject}/keyword-stats`) : null,
    enabled: !!activeProject,
  })

  if (isLoading) return <LoadingSpinner />

  const hour = new Date().getHours()
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"

  return (
    <div style={{ maxWidth: 1100 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <div style={{
            fontSize: 28,
            fontWeight: 700,
            color: T.text,
            lineHeight: 1.1,
            letterSpacing: -0.5,
          }}>
            {greeting}
          </div>
          <div style={{ fontSize: 13, color: T.textSoft, marginTop: 4 }}>
            {projects?.length || 0} project{projects?.length !== 1 ? "s" : ""} in your workspace
          </div>
        </div>
        <Btn onClick={() => setPage("new-project")} variant="primary">+ New project</Btn>
      </div>

      {/* Engine health */}
      <EngineHealthBar health={health} />

      {/* Keyword universe stats */}
      {kwStats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
          <DashStat label="Universes" value={(kwStats.universe_count || 1).toLocaleString()} color={T.purple} accentColor={T.purple} />
          <DashStat label="Pillars" value={(kwStats.pillar_count || 0).toLocaleString()} color={T.purpleDark} accentColor={T.purpleDark} />
          <DashStat label="Clusters" value={(kwStats.cluster_count || 0).toLocaleString()} color={T.teal} accentColor={T.teal} />
          <DashStat label="Keywords" value={(kwStats.total || 0).toLocaleString()} color={T.green} accentColor={T.green} />
        </div>
      )}

      {/* Section heading */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ fontSize: 17, fontWeight: 600, color: T.text }}>Your Projects</div>
        {activeProject && (
          <span style={{ fontSize: 11, color: T.textSoft }}>
            Active: <span style={{ color: T.purple, fontWeight: 600 }}>
              {projects?.find(p => p.project_id === activeProject)?.name || activeProject}
            </span>
          </span>
        )}
      </div>

      {/* Projects grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 14, marginBottom: 8 }}>
        {(projects || []).map(p => (
          <ProjectCard
            key={p.project_id}
            project={p}
            isActive={activeProject === p.project_id}
            onSelect={() => { setProject(p.project_id); setPage("content") }}
            onEdit={() => setEditingProject(p)}
            onDelete={() => setDeletingProject(p)}
          />
        ))}
        {(projects || []).length === 0 && (
          <div style={{
            gridColumn: "1 / -1",
            padding: "40px 24px",
            textAlign: "center",
            background: "#fff",
            borderRadius: 14,
            boxShadow: T.cardShadow,
          }}>
            <div style={{ fontSize: 18, fontWeight: 600, color: T.text, marginBottom: 8 }}>
              No projects yet
            </div>
            <div style={{ fontSize: 13, color: T.textSoft, marginBottom: 16 }}>
              Create your first project to start building keyword universes.
            </div>
            <Btn onClick={() => setPage("new-project")} variant="primary">Create first project</Btn>
          </div>
        )}
      </div>

      {/* Cost strip */}
      <CostStrip costs={costs} />

      {/* Modals */}
      {editingProject && (
        <EditProjectModal
          project={editingProject}
          onClose={() => setEditingProject(null)}
          onSaved={() => { qclient.invalidateQueries(["projects"]); setEditingProject(null) }}
        />
      )}
      {deletingProject && (
        <ConfirmModal
          message={`Delete project "${deletingProject.name}"? This cannot be undone.`}
          onClose={() => setDeletingProject(null)}
          onConfirm={async () => {
            await api.delete(`/api/projects/${deletingProject.project_id}`)
            if (activeProject === deletingProject.project_id) {
              setProject(null)
              qclient.removeQueries(["costs", deletingProject.project_id])
              qclient.removeQueries(["kw-stats", deletingProject.project_id])
            }
            qclient.invalidateQueries(["projects"])
            setDeletingProject(null)
          }}
        />
      )}
    </div>
  )
}
