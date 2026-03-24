// ============================================================================
// ANNASEO — REACT FRONTEND  (src/App.jsx)
// All 8 pages in one file for initial development.
// Split into separate files during Week 7 build.
//
// Stack: React 18 + Vite + TailwindCSS + Zustand + React Query
//        D3.js (keyword tree) + Chart.js (rankings)
// API:   http://localhost:8000 (annaseo_main.py)
// ============================================================================

import { useState, useEffect, useRef, useCallback, createContext, useContext } from "react"
import { create } from "zustand"
import { useQuery, useMutation, useQueryClient, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import KeywordInputPage from "./KeywordInput"

const API = import.meta.env.VITE_API_URL || ""
const qc  = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } })

// ─────────────────────────────────────────────────────────────────────────────
// GLOBAL STORE (Zustand)
// ─────────────────────────────────────────────────────────────────────────────
const useStore = create((set, get) => ({
  user:         null,
  token:        localStorage.getItem("annaseo_token") || null,
  activeProject:localStorage.getItem("annaseo_project") || null,
  sidebarOpen:  true,
  currentPage:  "dashboard",

  setUser:    (u)  => set({ user: u }),
  setToken:   (t)  => { localStorage.setItem("annaseo_token", t || ""); set({ token: t }) },
  setProject: (id) => { localStorage.setItem("annaseo_project", id || ""); set({ activeProject: id }) },
  setPage:    (p)  => set({ currentPage: p }),
  toggleSidebar: () => set(s => ({ sidebarOpen: !s.sidebarOpen })),
  logout: () => {
    localStorage.removeItem("annaseo_token")
    localStorage.removeItem("annaseo_project")
    set({ user: null, token: null, activeProject: null, currentPage: "login" })
  },
}))

// ─────────────────────────────────────────────────────────────────────────────
// API CLIENT
// ─────────────────────────────────────────────────────────────────────────────
const api = {
  get: async (path) => {
    const token = useStore.getState().token
    const r = await fetch(`${API}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    if (r.status === 401) { useStore.getState().logout(); return null }
    return r.json()
  },
  post: async (path, body) => {
    const token = useStore.getState().token
    const r = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body),
    })
    if (r.status === 401) { useStore.getState().logout(); return null }
    const text = await r.text()
    try { return text ? JSON.parse(text) : {} } catch { return { error: text } }
  },
  put: async (path, body) => {
    const token = useStore.getState().token
    const r = await fetch(`${API}${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body),
    })
    if (r.status === 401) { useStore.getState().logout(); return null }
    const text = await r.text()
    try { return text ? JSON.parse(text) : {} } catch { return { error: text } }
  },
  delete: async (path) => {
    const token = useStore.getState().token
    const r = await fetch(`${API}${path}`, {
      method: "DELETE",
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
    if (r.status === 401) { useStore.getState().logout(); return null }
    const text = await r.text()
    try { return text ? JSON.parse(text) : {} } catch { return { error: text } }
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// DESIGN TOKENS
// ─────────────────────────────────────────────────────────────────────────────
const T = {
  purple: "#7F77DD",
  purpleLight: "#EEEDFE",
  purpleDark: "#534AB7",
  teal: "#1D9E75",
  tealLight: "#E1F5EE",
  red: "#E24B4A",
  amber: "#BA7517",
  amberLight: "#FAEEDA",
  green: "#639922",
  greenLight: "#EAF3DE",
  gray: "#888780",
  grayLight: "#F1EFE8",
}

// ─────────────────────────────────────────────────────────────────────────────
// SHARED COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

function Badge({ children, color = "purple", size = "sm" }) {
  const colors = {
    purple: { bg: T.purpleLight, text: T.purpleDark },
    green:  { bg: T.greenLight,  text: T.green },
    red:    { bg: "#FCEBEB",     text: T.red },
    amber:  { bg: T.amberLight,  text: T.amber },
    teal:   { bg: T.tealLight,   text: T.teal },
    gray:   { bg: T.grayLight,   text: T.gray },
  }
  const c = colors[color] || colors.purple
  return (
    <span style={{
      background: c.bg, color: c.text,
      fontSize: size === "xs" ? 9 : 10, fontWeight: 500,
      padding: size === "xs" ? "1px 5px" : "2px 7px",
      borderRadius: 99, whiteSpace: "nowrap", display: "inline-block",
    }}>{children}</span>
  )
}

function Card({ children, style = {}, onClick }) {
  return (
    <div onClick={onClick} style={{
      background: "var(--color-bg, #fff)",
      border: "0.5px solid rgba(0,0,0,0.1)",
      borderRadius: 12, padding: "12px 14px",
      cursor: onClick ? "pointer" : "default",
      ...style
    }}>{children}</div>
  )
}

function StatCard({ label, value, sub, color = T.purple }) {
  return (
    <Card style={{ textAlign: "center" }}>
      <div style={{ fontSize: 26, fontWeight: 600, color, lineHeight: 1 }}>{value ?? "—"}</div>
      {sub && <div style={{ fontSize: 10, color: T.gray, marginTop: 2 }}>{sub}</div>}
      <div style={{ fontSize: 11, color: T.gray, marginTop: 4 }}>{label}</div>
    </Card>
  )
}

function Btn({ children, onClick, variant = "default", small, disabled, style = {} }) {
  const styles = {
    default: { background: "transparent", color: T.gray, border: `0.5px solid rgba(0,0,0,0.15)` },
    primary: { background: T.purple, color: "#fff", border: `1px solid ${T.purpleDark}` },
    danger:  { background: "transparent", color: T.red, border: `0.5px solid ${T.red}` },
    success: { background: "transparent", color: T.teal, border: `0.5px solid ${T.teal}` },
  }
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: small ? "3px 9px" : "6px 14px",
      borderRadius: 8, fontSize: small ? 11 : 12, fontWeight: 500,
      cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1,
      ...styles[variant], ...style
    }}>{children}</button>
  )
}

function ScoreRing({ score, size = 44 }) {
  const r = (size - 6) / 2
  const circ = 2 * Math.PI * r
  const dash = (score / 100) * circ
  const color = score >= 75 ? T.teal : score >= 50 ? T.amber : T.red
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={T.grayLight} strokeWidth={4}/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={4}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"/>
      <text x={size/2} y={size/2} textAnchor="middle" dominantBaseline="central"
        style={{ fontSize: 11, fontWeight: 600, fill: color, transform: "rotate(90deg)", transformOrigin: `${size/2}px ${size/2}px` }}>
        {score}
      </text>
    </svg>
  )
}

function StatusDot({ status }) {
  const c = { healthy: T.teal, good: T.teal, degraded: T.amber, critical: T.red, error: T.red }[status] || T.gray
  return <span style={{ width: 7, height: 7, borderRadius: "50%", background: c, display: "inline-block" }}/>
}

function SSEConsole({ events }) {
  const ref = useRef()
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight }, [events])
  const levelColor = { data: T.teal, error: T.red, gate: T.amber, phase_log: T.purple, complete: T.teal }
  return (
    <div ref={ref} style={{
      background: "#0f1117", borderRadius: 8, padding: "10px 12px",
      fontFamily: "monospace", fontSize: 11, lineHeight: 1.7,
      maxHeight: 320, overflowY: "auto", color: "#a8b0c0",
    }}>
      {events.length === 0 && <span style={{ color: "#555" }}>Waiting for run to start...</span>}
      {events.map((e, i) => (
        <div key={i} style={{ display: "flex", gap: 8 }}>
          <span style={{ color: "#444", minWidth: 52 }}>
            {e.timestamp ? new Date(e.timestamp).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",second:"2-digit"}) : ""}
          </span>
          <span style={{ color: levelColor[e.type] || "#666", minWidth: 14 }}>▸</span>
          <span style={{ color: e.type === "error" ? T.red : e.type === "complete" ? T.teal : "#c8d0e0" }}>
            {e.phase ? `[${e.phase}] ` : ""}{e.msg || e.message || e.error || JSON.stringify(e).slice(0, 120)}
          </span>
        </div>
      ))}
    </div>
  )
}

function LoadingSpinner() {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 40 }}>
      <div style={{
        width: 28, height: 28, border: `3px solid ${T.purpleLight}`,
        borderTopColor: T.purple, borderRadius: "50%",
        animation: "spin 0.7s linear infinite"
      }}/>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MODAL — Edit Project
// ─────────────────────────────────────────────────────────────────────────────
function EditProjectModal({ project, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: project.name || "",
    description: project.description || "",
    seed_keywords: JSON.parse(project.seed_keywords || "[]").join(", "),
    language: project.language || "english",
    region: project.region || "india",
    religion: project.religion || "general",
    wp_url: project.wp_url || "",
    wp_user: project.wp_user || "",
    wp_password: "",
  })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    await api.put(`/api/projects/${project.project_id}`, {
      ...form,
      seed_keywords: form.seed_keywords.split(",").map(s => s.trim()).filter(Boolean),
    })
    setSaving(false)
    onSaved()
    onClose()
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{ background: "#fff", borderRadius: 14, padding: 24, width: 440, maxHeight: "80vh", overflowY: "auto" }}>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Edit project</div>
        {[
          ["Project name", "name", "text"],
          ["Description", "description", "text"],
          ["Seed keywords (comma-separated)", "seed_keywords", "text"],
          ["WordPress URL", "wp_url", "text"],
          ["WordPress user", "wp_user", "text"],
          ["WordPress password", "wp_password", "password"],
        ].map(([label, key, type]) => (
          <div key={key} style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 11, color: T.gray, display: "block", marginBottom: 3 }}>{label}</label>
            <input type={type} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })}
              style={{ width: "100%", padding: "7px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 12, boxSizing: "border-box" }}/>
          </div>
        ))}
        {[
          ["Language", "language", ["english","malayalam","hindi","tamil","arabic"]],
          ["Region", "region", ["india","kerala","wayanad","global","south_india"]],
          ["Religion context", "religion", ["general","ayurveda","halal","unani","hindu","christian"]],
        ].map(([label, key, opts]) => (
          <div key={key} style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 11, color: T.gray, display: "block", marginBottom: 3 }}>{label}</label>
            <select value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })}
              style={{ width: "100%", padding: "7px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 12, boxSizing: "border-box" }}>
              {opts.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
        ))}
        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn onClick={save} variant="primary" disabled={saving} style={{ flex: 1 }}>
            {saving ? "Saving..." : "Save changes"}
          </Btn>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MODAL — Confirm delete
// ─────────────────────────────────────────────────────────────────────────────
function ConfirmModal({ message, onConfirm, onClose }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{ background: "#fff", borderRadius: 14, padding: 24, width: 320 }}>
        <div style={{ fontSize: 14, marginBottom: 20 }}>{message}</div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn onClick={onClose} style={{ flex: 1 }}>Cancel</Btn>
          <Btn onClick={onConfirm} variant="danger" style={{ flex: 1 }}>Delete</Btn>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: LOGIN
// ─────────────────────────────────────────────────────────────────────────────
function LoginPage() {
  const [email, setEmail] = useState("")
  const [pw, setPw] = useState("")
  const [mode, setMode] = useState("login")
  const [name, setName] = useState("")
  const [err, setErr] = useState("")
  const { setToken, setUser, setPage } = useStore()

  const submit = async () => {
    setErr("")
    if (mode === "login") {
      const fd = new FormData()
      fd.append("username", email); fd.append("password", pw)
      const r = await fetch(`${API}/api/auth/login`, { method: "POST", body: fd })
      if (!r.ok) { setErr("Invalid credentials"); return }
      const data = await r.json()
      setToken(data.access_token)
      setUser({ email, user_id: data.user_id, role: data.role })
      setPage("dashboard")
    } else {
      const data = await api.post("/api/auth/register", { email, password: pw, name })
      if (data.error) { setErr(data.error); return }
      setToken(data.access_token)
      setUser({ email, name })
      setPage("dashboard")
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: T.grayLight }}>
      <div style={{ width: 360 }}>
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div style={{ fontSize: 28, fontWeight: 700, color: T.purple, letterSpacing: -1 }}>AnnaSEO</div>
          <div style={{ fontSize: 13, color: T.gray, marginTop: 4 }}>AI Keyword & Content OS</div>
        </div>
        <Card style={{ padding: 24 }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
            {["login","register"].map(m => (
              <button key={m} onClick={() => setMode(m)} style={{
                flex: 1, padding: "6px 0", borderRadius: 8, fontSize: 12, fontWeight: 500,
                border: "none", cursor: "pointer",
                background: mode === m ? T.purple : T.purpleLight,
                color: mode === m ? "#fff" : T.purpleDark,
              }}>{m === "login" ? "Sign in" : "Register"}</button>
            ))}
          </div>
          {mode === "register" && (
            <input value={name} onChange={e=>setName(e.target.value)} placeholder="Full name"
              style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 13, marginBottom: 8, boxSizing: "border-box" }}/>
          )}
          <input value={email} onChange={e=>setEmail(e.target.value)} placeholder="Email" type="email"
            style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 13, marginBottom: 8, boxSizing: "border-box" }}/>
          <input value={pw} onChange={e=>setPw(e.target.value)} placeholder="Password" type="password"
            onKeyDown={e => e.key === "Enter" && submit()}
            style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 13, marginBottom: 12, boxSizing: "border-box" }}/>
          {err && <div style={{ color: T.red, fontSize: 11, marginBottom: 8 }}>{err}</div>}
          <Btn onClick={submit} variant="primary" style={{ width: "100%" }}>
            {mode === "login" ? "Sign in" : "Create account"}
          </Btn>
        </Card>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: DASHBOARD (P1)
// ─────────────────────────────────────────────────────────────────────────────
function DashboardPage() {
  const { activeProject, setPage, setProject } = useStore()
  const qclient = useQueryClient()
  const [editingProject, setEditingProject] = useState(null)
  const [deletingProject, setDeletingProject] = useState(null)
  const { data: projects, isLoading } = useQuery({ queryKey: ["projects"], queryFn: () => api.get("/api/projects") })
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: () => api.get("/api/health"), refetchInterval: 30000 })
  const { data: costs } = useQuery({ queryKey: ["costs", activeProject], queryFn: () => activeProject ? api.get(`/api/costs/${activeProject}`) : null, enabled: !!activeProject })
  const { data: kwStats } = useQuery({ queryKey: ["kw-stats", activeProject], queryFn: () => activeProject ? api.get(`/api/projects/${activeProject}/keyword-stats`) : null, enabled: !!activeProject })

  if (isLoading) return <LoadingSpinner/>

  return (
    <div>
      <div style={{ marginBottom: 20, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 600, color: "#1a1a1a" }}>Dashboard</div>
          <div style={{ fontSize: 12, color: T.gray, marginTop: 2 }}>
            {projects?.length || 0} project{projects?.length !== 1 ? "s" : ""}
          </div>
        </div>
        <Btn onClick={() => setPage("new-project")} variant="primary">+ New project</Btn>
      </div>

      {/* Engine health */}
      {health && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
            Engine health
            <StatusDot status={health.all_ok ? "healthy" : "degraded"}/>
            <span style={{ fontSize: 11, color: health.all_ok ? T.teal : T.amber }}>
              {health.all_ok ? "All systems operational" : "Some engines need attention"}
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 6 }}>
            {Object.entries(health.engines || {}).map(([name, status]) => (
              <div key={name} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11 }}>
                <StatusDot status={status === "ok" ? "healthy" : "error"}/>
                <span style={{ color: T.gray, fontSize: 10 }}>{name}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Universe hierarchy summary */}
      {kwStats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16 }}>
          {[
            { label: "Universes", count: kwStats.universe_count || 1, color: T.purple, icon: "🌐" },
            { label: "Pillars", count: kwStats.pillar_count || 0, color: T.purpleDark, icon: "📌" },
            { label: "Clusters", count: kwStats.cluster_count || 0, color: T.teal, icon: "🔗" },
            { label: "Keywords", count: kwStats.total || 0, color: T.green, icon: "🔑" },
          ].map(item => (
            <Card key={item.label} style={{ padding: 12 }}>
              <div style={{ fontSize: 11, color: T.gray, marginBottom: 4 }}>{item.icon} {item.label}</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: item.color }}>{item.count?.toLocaleString()}</div>
            </Card>
          ))}
        </div>
      )}

      {/* Projects grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12, marginBottom: 20 }}>
        {(projects || []).map(p => (
          <Card key={p.project_id}
            style={{ cursor: "pointer", borderColor: activeProject === p.project_id ? T.purple : "rgba(0,0,0,0.1)", borderWidth: activeProject === p.project_id ? 1.5 : 0.5 }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
              <div onClick={() => { setProject(p.project_id); setPage("keywords") }} style={{ flex: 1, cursor: "pointer" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#1a1a1a" }}>{p.name}</div>
                <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>{p.industry}</div>
              </div>
              <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                <Badge color={p.status === "active" ? "teal" : "gray"}>{p.status}</Badge>
                <button onClick={e => { e.stopPropagation(); setEditingProject(p) }}
                  style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, color: T.gray, padding: "0 3px" }} title="Edit">✎</button>
                <button onClick={e => { e.stopPropagation(); setDeletingProject(p) }}
                  style={{ background: "none", border: "none", cursor: "pointer", fontSize: 12, color: T.red, padding: "0 3px" }} title="Delete">✕</button>
              </div>
            </div>
            <div style={{ marginTop: 10, fontSize: 11, color: T.gray }}>
              {JSON.parse(p.seed_keywords || "[]").slice(0,3).join(", ") || "No seeds yet"}
            </div>
          </Card>
        ))}
      </div>

      {editingProject && (
        <EditProjectModal project={editingProject} onClose={() => setEditingProject(null)}
          onSaved={() => qclient.invalidateQueries(["projects"])}/>
      )}
      {deletingProject && (
        <ConfirmModal message={`Delete project "${deletingProject.name}"? This cannot be undone.`}
          onClose={() => setDeletingProject(null)}
          onConfirm={async () => {
            await api.delete(`/api/projects/${deletingProject.project_id}`)
            qclient.invalidateQueries(["projects"])
            setDeletingProject(null)
          }}/>
      )}

      {/* Cost overview */}
      {costs && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
          <StatCard label="Total cost" value={`$${costs.total_usd}`} color={T.purple}/>
          <StatCard label="Articles" value={costs.articles_generated} color={T.teal}/>
          <StatCard label="Per article" value={`$${costs.cost_per_article}`} color={T.green}/>
          <StatCard label="Est. monthly" value={`$${costs.monthly_estimate}`} color={T.gray}/>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: KEYWORDS / UNIVERSE (P2) — with SSE console
// ─────────────────────────────────────────────────────────────────────────────
// PAGE: KEYWORD UNIVERSE — 20-phase runner with editable gates
// ─────────────────────────────────────────────────────────────────────────────
function KeywordsPage() {
  const { activeProject } = useStore()
  const qclient = useQueryClient()
  const [seed, setSeed] = useState("")
  const [runId, setRunId] = useState(null)
  const [events, setEvents] = useState([])
  const [runStatus, setRunStatus] = useState("idle") // idle | running | waiting_gate | complete | error
  const [gateData, setGateData] = useState(null)
  const [gateName, setGateName] = useState(null)
  // editable state per gate
  const [editedKeywords, setEditedKeywords] = useState("")       // textarea for universe_keywords
  const [editedClusters, setEditedClusters] = useState([])       // [{name,checked}] for pillars
  const esRef = useRef(null)
  const { data: runs, refetch: refetchRuns } = useQuery({ queryKey: ["runs", activeProject], queryFn: () => api.get(`/api/projects/${activeProject}/runs`), enabled: !!activeProject })

  const startRun = async () => {
    if (!seed.trim() || !activeProject) return
    setEvents([]); setRunStatus("running"); setGateData(null); setGateName(null)
    const data = await api.post(`/api/projects/${activeProject}/runs`, { seed: seed.trim(), language: "english", region: "india" })
    if (!data?.run_id) { setRunStatus("error"); return }
    setRunId(data.run_id)
    if (esRef.current) esRef.current.close()
    const es = new EventSource(`${API}${data.stream_url}`)
    esRef.current = es
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data)
      ev.ts = new Date().toLocaleTimeString()
      setEvents(prev => [...prev, ev])
      if (ev.type === "gate") {
        setGateData(ev.data); setGateName(ev.gate); setRunStatus("waiting_gate")
        if (ev.gate === "universe_keywords") {
          setEditedKeywords((ev.data?.keywords || []).join("\n"))
        }
        if (ev.gate === "pillars") {
          setEditedClusters((ev.data?.clusters || []).map(c => ({ name: c, checked: true })))
        }
      }
      if (ev.type === "complete") { setRunStatus("complete"); es.close(); refetchRuns() }
      if (ev.type === "error") { setRunStatus("error"); es.close(); refetchRuns() }
    }
    es.onerror = () => { setRunStatus("error"); es.close() }
  }

  const confirmGate = async (payload) => {
    await api.post(`/api/runs/${runId}/confirm/${gateName}`, payload)
    setRunStatus("running"); setGateData(null); setGateName(null)
  }

  const confirmKeywords = () => {
    const kws = editedKeywords.split("\n").map(k => k.trim()).filter(Boolean)
    confirmGate({ keywords: kws })
  }

  const confirmPillars = () => {
    const removed = editedClusters.filter(c => !c.checked).map(c => c.name)
    confirmGate({ removed_clusters: removed })
  }

  const statusColor = { idle: T.gray, running: T.teal, waiting_gate: T.amber, complete: T.teal, error: T.red }

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>Keyword Universe</div>

      {/* Run starter */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10 }}>Run 20-phase keyword universe</div>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={seed} onChange={e=>setSeed(e.target.value)} placeholder="Enter seed keyword (e.g. turmeric)"
            onKeyDown={e => e.key === "Enter" && startRun()}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 13 }}/>
          <Btn onClick={startRun} variant="primary" disabled={runStatus === "running"}>
            {runStatus === "running" ? "Running..." : "Start run"}
          </Btn>
        </div>
      </Card>

      {/* Gate: universe_keywords — editable keyword list after P3 */}
      {runStatus === "waiting_gate" && gateName === "universe_keywords" && (
        <Card style={{ marginBottom: 16, border: `1.5px solid ${T.amber}` }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.amber }}>Gate A — P3 Keywords</div>
              <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>
                {editedKeywords.split("\n").filter(Boolean).length} keywords ready for P4–P9.
                Edit the list below — remove irrelevant ones, add new ones (one per line).
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <Btn onClick={() => confirmGate({ keywords: gateData?.keywords || [] })} small>Skip edits</Btn>
              <Btn onClick={confirmKeywords} variant="success" small>
                ✓ Confirm {editedKeywords.split("\n").filter(Boolean).length} keywords → P4
              </Btn>
            </div>
          </div>
          <textarea
            value={editedKeywords}
            onChange={e => setEditedKeywords(e.target.value)}
            rows={12}
            style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)",
                     fontSize: 12, fontFamily: "monospace", resize: "vertical", boxSizing: "border-box",
                     background: "#fafafa", lineHeight: 1.6 }}
            placeholder="One keyword per line…"
          />
          <div style={{ marginTop: 6, fontSize: 11, color: T.gray }}>
            Tip: Remove keywords that are off-topic, too broad, or low-value before continuing.
          </div>
        </Card>
      )}

      {/* Gate: pillars — cluster checklist after P9 */}
      {runStatus === "waiting_gate" && gateName === "pillars" && (
        <Card style={{ marginBottom: 16, border: `1.5px solid ${T.amber}` }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.amber }}>Gate B — Pillar Review</div>
              <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>
                {editedClusters.filter(c=>c.checked).length}/{editedClusters.length} pillars selected.
                Uncheck any pillar to remove it from the content plan.
              </div>
            </div>
            <Btn onClick={confirmPillars} variant="success" small>
              ✓ Confirm {editedClusters.filter(c=>c.checked).length} pillars → P10
            </Btn>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            {editedClusters.map((c, i) => (
              <label key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                borderRadius: 8, background: c.checked ? T.tealLight : "#f5f5f5",
                cursor: "pointer", fontSize: 12, fontWeight: c.checked ? 500 : 400,
                color: c.checked ? T.teal : T.gray, border: `0.5px solid ${c.checked ? T.teal : "transparent"}` }}>
                <input type="checkbox" checked={c.checked}
                  onChange={() => setEditedClusters(prev => prev.map((x,j) => j===i ? {...x,checked:!x.checked} : x))}
                  style={{ accentColor: T.teal }}/>
                {c.name}
              </label>
            ))}
          </div>
        </Card>
      )}

      {/* Gate: content_calendar — confirm calendar */}
      {runStatus === "waiting_gate" && gateName === "content_calendar" && (
        <Card style={{ marginBottom: 16, border: `1.5px solid ${T.amber}` }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.amber }}>Gate C — Content Calendar</div>
              <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>
                {gateData?.calendar_count || 0} articles planned. Review and confirm to start generation.
              </div>
            </div>
            <Btn onClick={() => confirmGate(gateData || {})} variant="success" small>
              ✓ Confirm and generate content
            </Btn>
          </div>
          <pre style={{ fontSize: 11, color: T.gray, background: "#f8f8f8", padding: 10, borderRadius: 8,
                        maxHeight: 200, overflow: "auto", margin: 0 }}>
            {JSON.stringify(gateData, null, 2)}
          </pre>
        </Card>
      )}

      {/* SSE Console */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8, display: "flex", alignItems: "center", gap: 8 }}>
          Engine console
          {runStatus === "running" && <span style={{ width: 7, height: 7, borderRadius: "50%", background: T.teal, display: "inline-block", animation: "pulse 1s infinite" }}/>}
          {runStatus === "waiting_gate" && <Badge color="amber">Waiting for review</Badge>}
          {runStatus === "complete" && <Badge color="teal">Complete</Badge>}
          {runStatus === "error" && <Badge color="red">Error</Badge>}
        </div>
        <SSEConsole events={events}/>
      </Card>

      {/* Past runs */}
      {runs?.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10 }}>Recent runs</div>
          {runs.slice(0,8).map(r => (
            <div key={r.run_id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 12 }}>
              <StatusDot status={r.status === "complete" ? "healthy" : r.status === "error" ? "error" : "degraded"}/>
              <span style={{ flex: 1, fontWeight: 500 }}>{r.seed}</span>
              <Badge color={r.status === "complete" ? "teal" : r.status === "error" ? "red" : "amber"}>{r.status}</Badge>
              <span style={{ color: T.gray, fontSize: 11 }}>{r.started_at?.slice(0,16)}</span>
              <button onClick={async () => {
                if (!window.confirm(`Delete run "${r.seed}"?`)) return
                await api.delete(`/api/runs/${r.run_id}`)
                qclient.invalidateQueries(["runs", activeProject])
              }} style={{ background:"none",border:"none",cursor:"pointer",color:T.red,fontSize:13 }} title="Delete run">✕</button>
            </div>
          ))}
        </Card>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: KEYWORD TREE (P3) — D3.js universe explorer
// ─────────────────────────────────────────────────────────────────────────────
function KeywordTreePage() {
  const { activeProject } = useStore()
  const svgRef = useRef()
  const [filter, setFilter] = useState("")
  const [intentFilter, setIntentFilter] = useState("all")

  const { data: graphData, isLoading } = useQuery({
    queryKey: ["knowledge-graph", activeProject],
    queryFn: () => activeProject ? api.get(`/api/projects/${activeProject}/knowledge-graph`) : Promise.resolve(null),
    enabled: !!activeProject
  })

  const treeData = graphData || {
    name: activeProject ? "Keyword Universe" : "Select a project",
    children: []
  }

  useEffect(() => {
    // D3 tree rendering would go here
    // Simplified version using SVG directly
    const svg = svgRef.current
    if (!svg) return
    // D3 is loaded via CDN in index.html
  }, [treeData])

  const renderNode = (node, depth = 0, index = 0, total = 1) => {
    const colors = { pillar: T.purple, cluster: T.teal, keyword: T.gray }
    const c = colors[node.type] || T.gray
    const visible = !filter || node.name.toLowerCase().includes(filter.toLowerCase())
    if (!visible) return null
    return (
      <div key={node.name} style={{ marginLeft: depth * 20, marginBottom: 3 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "5px 8px", borderRadius: 7,
          background: depth === 0 ? T.grayLight : "transparent", cursor: "pointer" }}
          onClick={() => {}}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: c, flexShrink: 0 }}/>
          <span style={{ fontSize: 12, color: depth === 0 ? "#1a1a1a" : T.gray, fontWeight: depth < 2 ? 500 : 400 }}>
            {node.name}
          </span>
          {node.type && <Badge color={node.type === "pillar" ? "purple" : node.type === "cluster" ? "teal" : "gray"} size="xs">{node.type}</Badge>}
          {node.intent && <Badge color={node.intent === "transactional" ? "amber" : "gray"} size="xs">{node.intent}</Badge>}
          {node.score && <span style={{ marginLeft: "auto", fontSize: 10, color: node.score >= 80 ? T.teal : T.amber }}>{node.score}</span>}
        </div>
        {node.children?.map((child, i) => renderNode(child, depth + 1, i, node.children.length))}
      </div>
    )
  }

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>Keyword Tree</div>
      <Card style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter keywords..."
            style={{ flex: 1, padding: "6px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 12 }}/>
          {["all","informational","transactional","question","comparison"].map(i => (
            <Btn key={i} small onClick={() => setIntentFilter(i)}
              variant={intentFilter === i ? "primary" : "default"}>{i}</Btn>
          ))}
        </div>
      </Card>
      <Card style={{ minHeight: 400 }}>
        <svg ref={svgRef} style={{ display: "none" }}/>
        {isLoading ? (
          <LoadingSpinner/>
        ) : !treeData.children || treeData.children.length === 0 ? (
          <div style={{ color: T.gray, padding: 20, textAlign: "center", fontSize: 13 }}>No keyword universe data yet. Run a keyword extraction first.</div>
        ) : (
          renderNode(treeData)
        )}
      </Card>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: CONTENT (P4 + P6 combined) — generate + blog editor
// ─────────────────────────────────────────────────────────────────────────────
function ContentPage() {
  const { activeProject } = useStore()
  const qclient = useQueryClient()
  const [kw, setKw] = useState("")
  const [selected, setSelected] = useState(null)
  const [editingArticle, setEditingArticle] = useState(null) // {article_id, title, meta_title, meta_desc}
  const { data: articles, isLoading } = useQuery({
    queryKey: ["articles", activeProject],
    queryFn: () => activeProject ? api.get(`/api/projects/${activeProject}/content`) : [],
    enabled: !!activeProject
  })

  const generate = useMutation({
    mutationFn: () => api.post("/api/content/generate", { keyword: kw, project_id: activeProject }),
    onSuccess: () => { qclient.invalidateQueries(["articles", activeProject]); setKw("") }
  })

  const approve = useMutation({
    mutationFn: (id) => api.post(`/api/content/${id}/approve`),
    onSuccess: () => qclient.invalidateQueries(["articles", activeProject])
  })

  const statusColor = { draft: "gray", generating: "amber", review: "purple", approved: "teal", publishing: "amber", published: "teal", failed: "red" }

  if (!activeProject) return <div style={{ color: T.gray, padding: 20 }}>Select a project to manage content.</div>

  const lifecycle = ["draft","generating","review","approved","publishing","published","failed"]
  const lifeCounts = lifecycle.reduce((acc, s) => {
    acc[s] = (articles || []).filter(a => a.status === s).length; return acc
  }, {})

  return (
    <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 1fr" : "1fr", gap: 16 }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 12 }}>Content</div>
        {/* Lifecycle pipeline */}
        <Card style={{ marginBottom: 12, padding: "10px 14px" }}>
          <div style={{ fontSize: 11, color: T.gray, marginBottom: 8, fontWeight: 500 }}>Content lifecycle</div>
          <div style={{ display: "flex", gap: 0, alignItems: "center", overflowX: "auto" }}>
            {lifecycle.filter(s => s !== "failed").map((s, i, arr) => (
              <div key={s} style={{ display: "flex", alignItems: "center" }}>
                <div style={{
                  padding: "4px 10px", borderRadius: 20, fontSize: 11, fontWeight: 500, whiteSpace: "nowrap",
                  background: lifeCounts[s] > 0 ? {
                    draft:T.purpleLight,generating:"#FFF3CD",review:T.purpleLight,
                    approved:T.tealLight,publishing:"#FFF3CD",published:T.tealLight
                  }[s] : "rgba(0,0,0,0.04)",
                  color: lifeCounts[s] > 0 ? {
                    draft:T.purple,generating:T.amber,review:T.purpleDark,
                    approved:T.teal,publishing:T.amber,published:T.teal
                  }[s] : T.gray,
                }}>
                  {s} {lifeCounts[s] > 0 && <strong>({lifeCounts[s]})</strong>}
                </div>
                {i < arr.length-1 && <span style={{ color: T.gray, padding: "0 2px", fontSize: 10 }}>→</span>}
              </div>
            ))}
            {lifeCounts.failed > 0 && (
              <div style={{ marginLeft: 8, padding: "4px 10px", borderRadius: 20, fontSize: 11, background:"#FEE2E2", color: T.red }}>
                failed ({lifeCounts.failed})
              </div>
            )}
          </div>
        </Card>
        <Card style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={kw} onChange={e=>setKw(e.target.value)} placeholder="Keyword to generate article for..."
              style={{ flex: 1, padding: "7px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 12 }}/>
            <Btn onClick={() => generate.mutate()} variant="primary" disabled={!kw.trim() || generate.isPending}>
              {generate.isPending ? "Generating..." : "Generate"}
            </Btn>
          </div>
        </Card>

        {isLoading ? <LoadingSpinner/> : (articles || []).map(a => (
          <div key={a.article_id}>
            {editingArticle?.article_id === a.article_id ? (
              <Card style={{ marginBottom: 8, border: `1.5px solid ${T.purple}` }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: T.purple, marginBottom: 8 }}>Editing: {a.keyword}</div>
                {[["Title", "title"], ["Meta title", "meta_title"], ["Meta description", "meta_desc"]].map(([label, field]) => (
                  <div key={field} style={{ marginBottom: 7 }}>
                    <label style={{ fontSize: 10, color: T.gray, display: "block", marginBottom: 2 }}>{label}</label>
                    <input value={editingArticle[field] || ""} onChange={e => setEditingArticle({ ...editingArticle, [field]: e.target.value })}
                      style={{ width: "100%", padding: "6px 8px", borderRadius: 7, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 11, boxSizing: "border-box" }}/>
                  </div>
                ))}
                <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <Btn small onClick={() => setEditingArticle(null)}>Cancel</Btn>
                  <Btn small variant="primary" onClick={async () => {
                    await api.put(`/api/content/${a.article_id}`, {
                      title: editingArticle.title,
                      meta_title: editingArticle.meta_title,
                      meta_desc: editingArticle.meta_desc,
                    })
                    qclient.invalidateQueries(["articles", activeProject])
                    setEditingArticle(null)
                  }}>Save</Btn>
                </div>
              </Card>
            ) : (
              <Card onClick={() => setSelected(a)}
                style={{ marginBottom: 8, cursor: "pointer", borderColor: selected?.article_id === a.article_id ? T.purple : "rgba(0,0,0,0.1)" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: "#1a1a1a" }}>{a.title || a.keyword}</div>
                    <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>{a.keyword}</div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                      <Badge color={statusColor[a.status] || "gray"}>{a.status}</Badge>
                      <button onClick={e => { e.stopPropagation(); setEditingArticle({ article_id: a.article_id, title: a.title || "", meta_title: a.meta_title || "", meta_desc: a.meta_desc || "" }) }}
                        style={{ background:"none",border:"none",cursor:"pointer",color:T.gray,fontSize:13 }} title="Edit">✎</button>
                      <button onClick={e => { e.stopPropagation(); if(window.confirm("Delete this article?")) { api.delete(`/api/content/${a.article_id}`).then(() => qclient.invalidateQueries(["articles", activeProject])) }}}
                        style={{ background:"none",border:"none",cursor:"pointer",color:T.red,fontSize:12 }} title="Delete">✕</button>
                    </div>
                    {a.seo_score > 0 && <div style={{ display: "flex", gap: 4 }}>
                      {[["SEO", a.seo_score], ["EEAT", a.eeat_score], ["GEO", a.geo_score]].map(([l, s]) => (
                        <span key={l} style={{ fontSize: 9, color: (s||0) >= 75 ? T.teal : T.amber }}>
                          {l}:{Math.round(s||0)}
                        </span>
                      ))}
                    </div>}
                  </div>
                </div>
              </Card>
            )}
          </div>
        ))}
      </div>

      {selected && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <div style={{ flex: 1, fontSize: 14, fontWeight: 600 }}>{selected.title || selected.keyword}</div>
            <Btn small onClick={() => setSelected(null)}>✕</Btn>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
            <StatCard label="SEO" value={Math.round(selected.seo_score||0)} color={selected.seo_score >= 75 ? T.teal : T.amber}/>
            <StatCard label="E-E-A-T" value={Math.round(selected.eeat_score||0)} color={selected.eeat_score >= 75 ? T.teal : T.amber}/>
            <StatCard label="GEO" value={Math.round(selected.geo_score||0)} color={selected.geo_score >= 75 ? T.teal : T.amber}/>
          </div>
          <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
            {selected.status === "draft" && <Btn small variant="primary" onClick={() => {}}>Send to review</Btn>}
            {selected.status === "review" && <Btn small variant="success" onClick={() => approve.mutate(selected.article_id)}>✓ Approve</Btn>}
            {selected.status === "approved" && <Btn small variant="primary" onClick={() => {}}>Publish</Btn>}
            {!selected.frozen && <Btn small onClick={() => {}}>🔒 Freeze</Btn>}
            {selected.frozen && <Btn small variant="danger">Frozen</Btn>}
          </div>
          <Card style={{ maxHeight: 400, overflowY: "auto" }}>
            <pre style={{ fontSize: 11, whiteSpace: "pre-wrap", wordBreak: "break-word", color: T.gray, margin: 0 }}>
              {selected.body ? selected.body.slice(0, 2000) + (selected.body.length > 2000 ? "..." : "") : "No content yet"}
            </pre>
          </Card>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: CALENDAR (P5)
// ─────────────────────────────────────────────────────────────────────────────
function CalendarPage() {
  const { activeProject } = useStore()
  const qclient = useQueryClient()
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
  const [year] = useState(new Date().getFullYear())
  const [selectedMonth, setSelectedMonth] = useState(null)

  const { data: cal, isLoading } = useQuery({
    queryKey: ["calendar", activeProject],
    queryFn: () => activeProject ? api.get(`/api/projects/${activeProject}/calendar-items`) : null,
    enabled: !!activeProject,
    refetchInterval: 60000,
  })

  const freeze = async (id) => {
    await api.post(`/api/content/${id}/freeze`)
    qclient.invalidateQueries(["calendar", activeProject])
  }
  const unfreeze = async (id) => {
    await api.post(`/api/content/${id}/unfreeze`)
    qclient.invalidateQueries(["calendar", activeProject])
  }

  if (!activeProject) return <div style={{ color: T.gray, padding: 20 }}>Select a project to view calendar.</div>
  if (isLoading) return <LoadingSpinner/>

  const byMonth = cal?.by_month || {}

  // Build month-indexed summary
  const monthSummary = months.map((m, i) => {
    const ym = `${year}-${String(i+1).padStart(2,"0")}`
    const items = byMonth[ym] || []
    const published = items.filter(x => x.status === "published").length
    const frozen = items.filter(x => x.frozen).length
    return { label: m, ym, items, published, frozen, count: items.length }
  })

  const displayItems = selectedMonth
    ? (byMonth[selectedMonth] || [])
    : (cal?.items || []).filter(x => {
        const sd = x.schedule_date || x.created_at || ""
        return sd.startsWith(String(year))
      }).slice(0, 20)

  const statusColor = { draft:"gray", generating:"amber", review:"purple", approved:"teal", publishing:"amber", published:"teal", failed:"red" }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ fontSize: 20, fontWeight: 600 }}>Content Calendar {year}</div>
        <div style={{ display: "flex", gap: 10, fontSize: 12, color: T.gray }}>
          <span>{cal?.total || 0} total</span>
          <span style={{ color: T.teal }}>{cal?.published || 0} published</span>
          <span style={{ color: T.amber }}>{cal?.frozen || 0} frozen</span>
        </div>
      </div>

      {/* 12-month grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16 }}>
        {monthSummary.map(({ label, ym, count, published, frozen }) => {
          const isPast = months.indexOf(label) < new Date().getMonth() && year === new Date().getFullYear()
          const isSelected = selectedMonth === ym
          return (
            <Card key={ym} onClick={() => setSelectedMonth(isSelected ? null : ym)}
              style={{ opacity: isPast && count === 0 ? 0.5 : 1, cursor: "pointer",
                borderColor: isSelected ? T.purple : "rgba(0,0,0,0.1)", borderWidth: isSelected ? 1.5 : 0.5 }}>
              <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8 }}>{label} {year}</div>
              {count > 0 ? (
                <>
                  <div style={{ fontSize: 22, fontWeight: 600, color: T.purple }}>{count}</div>
                  <div style={{ fontSize: 10, color: T.gray }}>articles</div>
                  <div style={{ marginTop: 8 }}>
                    <div style={{ display: "flex", height: 4, borderRadius: 99, overflow: "hidden", background: T.purpleLight }}>
                      <div style={{ width: `${count ? (published/count)*100 : 0}%`, background: T.teal }}/>
                    </div>
                    <div style={{ fontSize: 10, color: T.teal, marginTop: 3 }}>{published} published · {frozen} frozen</div>
                  </div>
                </>
              ) : (
                <div style={{ fontSize: 11, color: T.gray }}>No articles</div>
              )}
            </Card>
          )
        })}
      </div>

      {/* Article list */}
      <Card>
        <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10 }}>
          {selectedMonth ? `Articles — ${selectedMonth}` : "Upcoming articles"}
          {selectedMonth && <Btn small onClick={() => setSelectedMonth(null)} style={{ marginLeft: 8 }}>Clear</Btn>}
        </div>
        {displayItems.length === 0 ? (
          <div style={{ fontSize: 12, color: T.gray, padding: "12px 0" }}>No articles scheduled.</div>
        ) : displayItems.map((a, i) => (
          <div key={a.article_id || i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0",
            borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 12 }}>
            <span style={{ color: T.gray, minWidth: 72, fontSize: 11 }}>
              {(a.schedule_date || a.created_at || "").slice(0,10)}
            </span>
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {a.title || a.keyword}
            </span>
            <Badge color={statusColor[a.status] || "gray"}>{a.status}</Badge>
            {a.frozen
              ? <Btn small variant="danger" onClick={() => unfreeze(a.article_id)}>Unfreeze</Btn>
              : <Btn small onClick={() => freeze(a.article_id)}>Freeze</Btn>
            }
          </div>
        ))}
      </Card>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: SEO CHECKER (P7)
// ─────────────────────────────────────────────────────────────────────────────
function SEOCheckerPage() {
  const [url, setUrl] = useState("")
  const [auditId, setAuditId] = useState(null)
  const [polling, setPolling] = useState(false)
  const { data: audit } = useQuery({
    queryKey: ["audit", auditId],
    queryFn: () => auditId ? api.get(`/api/audit/${auditId}`) : null,
    enabled: !!auditId && polling,
    refetchInterval: (data) => data?.status === "done" || data?.status === "error" ? false : 2000,
    onSuccess: (data) => { if (data?.status === "done" || data?.status === "error") setPolling(false) }
  })

  const runAudit = async () => {
    if (!url.trim()) return
    setPolling(true)
    const data = await api.post("/api/audit", { url: url.trim() })
    if (data?.audit_id) setAuditId(data.audit_id)
  }

  const findings = audit?.findings ? JSON.parse(audit.findings) : []

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>SEO Checker</div>
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://yoursite.com"
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 13 }}/>
          <Btn onClick={runAudit} variant="primary" disabled={polling}>
            {polling ? "Auditing..." : "Run audit"}
          </Btn>
        </div>
      </Card>

      {audit && audit.status === "done" && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16 }}>
            <StatCard label="Overall score" value={Math.round(audit.score||0)} color={T.purple}/>
            <StatCard label="Grade" value={audit.grade || "—"} color={T.teal}/>
            <StatCard label="INP (ms)" value={Math.round(audit.cwv_inp||0)} color={(audit.cwv_inp||0) < 200 ? T.teal : T.red}/>
            <StatCard label="AI visibility" value={`${Math.round(audit.ai_score||0)}%`} color={T.purple}/>
          </div>
          <Card>
            <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10 }}>
              Findings ({findings.length})
            </div>
            {findings.map((f, i) => (
              <div key={i} style={{ padding: "8px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 3 }}>
                  <Badge color={{ critical:"red",warning:"amber",info:"teal",pass:"green" }[f.severity] || "gray"}>{f.severity}</Badge>
                  <span style={{ fontSize: 12, fontWeight: 500 }}>{f.title}</span>
                </div>
                <div style={{ fontSize: 11, color: T.gray }}>{f.finding}</div>
                {f.fix && <div style={{ fontSize: 11, color: T.teal, marginTop: 3 }}>Fix: {f.fix}</div>}
              </div>
            ))}
          </Card>
        </>
      )}
      {audit?.status === "running" && <LoadingSpinner/>}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: RANKINGS (P8)
// ─────────────────────────────────────────────────────────────────────────────
function RankingsPage() {
  const { activeProject } = useStore()
  const { data: rankings } = useQuery({
    queryKey: ["rankings", activeProject],
    queryFn: () => activeProject ? api.get(`/api/rankings/${activeProject}`) : [],
    enabled: !!activeProject
  })
  const { data: gscStatus } = useQuery({
    queryKey: ["gsc-status", activeProject],
    queryFn: () => activeProject ? api.get(`/api/gsc/${activeProject}/status`) : null,
    enabled: !!activeProject
  })

  const syncGSC = async () => { await api.post(`/api/gsc/${activeProject}/sync`, {}) }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ fontSize: 20, fontWeight: 600 }}>Rankings</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {gscStatus?.connected ? (
            <>
              <Badge color="teal">GSC connected</Badge>
              <Btn small onClick={syncGSC}>Sync now</Btn>
            </>
          ) : (
            <Btn small variant="primary" onClick={async () => {
              const data = await api.get(`/api/gsc/${activeProject}/auth-url`)
              if (data?.auth_url) window.open(data.auth_url, "_blank")
            }}>Connect GSC</Btn>
          )}
        </div>
      </div>

      {rankings?.length > 0 ? (
        <>
          {/* Position distribution summary */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginBottom: 16 }}>
            {[
              { label: "Top 3", count: rankings.filter(r=>r.position<=3).length, color: T.teal },
              { label: "Top 10", count: rankings.filter(r=>r.position<=10).length, color: T.purple },
              { label: "Top 30", count: rankings.filter(r=>r.position<=30).length, color: T.gray },
            ].map(b => (
              <Card key={b.label} style={{ padding: 12, textAlign: "center" }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: b.color }}>{b.count}</div>
                <div style={{ fontSize: 11, color: T.gray }}>{b.label}</div>
              </Card>
            ))}
          </div>
          <Card>
            <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10 }}>Keyword positions ({rankings.length})</div>
            {rankings.slice(0, 30).map((r, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 12 }}>
                <div style={{
                  width: 26, height: 26, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11, fontWeight: 600,
                  background: r.position <= 3 ? T.tealLight : r.position <= 10 ? T.purpleLight : T.grayLight,
                  color: r.position <= 3 ? T.teal : r.position <= 10 ? T.purple : T.gray,
                }}>{Math.round(r.position)}</div>
                <span style={{ flex: 1 }}>{r.keyword}</span>
                {/* Mini position bar */}
                <div style={{ width: 60, height: 4, background: "rgba(0,0,0,0.06)", borderRadius: 2, overflow:"hidden" }}>
                  <div style={{ width: `${Math.max(0,100-r.position*3)}%`, height: "100%",
                    background: r.position<=3?T.teal:r.position<=10?T.purple:T.gray }}/>
                </div>
                <span style={{ fontSize: 11, color: T.gray, minWidth: 50, textAlign:"right" }}>{r.clicks} clicks</span>
                <span style={{ fontSize: 11, color: T.gray, minWidth: 55, textAlign:"right" }}>{(r.ctr * 100).toFixed(1)}% CTR</span>
              </div>
            ))}
          </Card>
        </>
      ) : (
        <Card style={{ textAlign: "center", padding: 40 }}>
          <div style={{ fontSize: 13, color: T.gray }}>No ranking data yet.</div>
          <div style={{ fontSize: 12, color: T.gray, marginTop: 6 }}>Connect Google Search Console to import positions.</div>
        </Card>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: QUALITY DASHBOARD (P9) — QI + RSD
// ─────────────────────────────────────────────────────────────────────────────
function QualityDashboard() {
  const { activeProject } = useStore()
  const [tab, setTab] = useState("review")
  const qclient = useQueryClient()
  const { data: qi } = useQuery({
    queryKey: ["qi-dashboard", activeProject],
    queryFn: () => api.get(`/api/qi/dashboard?project_id=${activeProject}`),
    enabled: !!activeProject
  })
  const { data: tunings } = useQuery({
    queryKey: ["tunings"],
    queryFn: () => api.get("/api/qi/tunings?status=pending")
  })
  const { data: phases } = useQuery({
    queryKey: ["phases", activeProject],
    queryFn: () => api.get(`/api/qi/phases?project_id=${activeProject}`),
    enabled: !!activeProject
  })

  const feedback = useMutation({
    mutationFn: ({ output_id, label, reason }) =>
      api.post("/api/qi/feedback", { output_id, project_id: activeProject, label, reason }),
    onSuccess: () => qclient.invalidateQueries(["qi-dashboard", activeProject])
  })

  const approveTuning = useMutation({
    mutationFn: (tid) => api.post(`/api/qi/tunings/${tid}/approve`, { approved_by: "admin" }),
    onSuccess: () => qclient.invalidateQueries(["tunings"])
  })

  const stats = qi?.quality_stats || {}
  const queue = qi?.review_queue || []
  const phasesData = phases || []

  const tabs = ["review","phases","tunings"]

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 12 }}>Quality Intelligence</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 14 }}>
        <StatCard label="Quality rate" value={`${stats.quality_rate || 0}%`} color={T.teal}/>
        <StatCard label="Good items" value={stats.good || 0} color={T.teal}/>
        <StatCard label="Bad items" value={stats.bad || 0} color={T.red}/>
        <StatCard label="Pending tunings" value={tunings?.length || 0} color={T.amber}/>
      </div>

      <div style={{ display: "flex", gap: 4, borderBottom: "0.5px solid rgba(0,0,0,0.1)", marginBottom: 12 }}>
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "5px 12px", fontSize: 11, fontWeight: 500, cursor: "pointer",
            background: "none", border: "none", borderBottom: tab === t ? `2px solid ${T.purple}` : "2px solid transparent",
            color: tab === t ? T.purple : T.gray, marginBottom: -1,
          }}>{t === "review" ? "Review queue" : t === "phases" ? "Phase health" : `Tuning approvals (${tunings?.length || 0})`}</button>
        ))}
      </div>

      {tab === "review" && (
        <div>
          {queue.slice(0, 20).map((item, i) => (
            <ReviewItem key={i} item={item} onFeedback={(label, reason) =>
              feedback.mutate({ output_id: item.output_id, label, reason })}/>
          ))}
          {queue.length === 0 && <div style={{ color: T.gray, fontSize: 12, padding: "16px 0" }}>All items reviewed. Good work.</div>}
        </div>
      )}

      {tab === "phases" && (
        <div>
          {phasesData.map((p, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 10px", background: "white", borderRadius: 8, marginBottom: 5, border: "0.5px solid rgba(0,0,0,0.08)", fontSize: 11 }}>
              <StatusDot status={p.status}/>
              <span style={{ flex: 1, fontWeight: 500 }}>{p.phase}</span>
              <span style={{ color: T.gray, fontSize: 10 }}>{p.engine_file}</span>
              <div style={{ width: 60, height: 4, borderRadius: 99, background: T.grayLight, overflow: "hidden" }}>
                <div style={{ width: `${p.quality}%`, height: "100%", background: p.quality >= 80 ? T.teal : p.quality >= 60 ? T.amber : T.red }}/>
              </div>
              <span style={{ minWidth: 32, textAlign: "right", color: p.quality >= 80 ? T.teal : T.amber }}>
                {Math.round(p.quality)}
              </span>
              <span style={{ color: T.red, minWidth: 48, textAlign: "right" }}>{p.bad}/{p.total_items}</span>
            </div>
          ))}
        </div>
      )}

      {tab === "tunings" && (
        <div>
          {(tunings || []).map((t, i) => (
            <Card key={i} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 6, marginBottom: 5 }}>
                    <Badge color="purple">{t.tuning_type}</Badge>
                    <Badge color="gray">{t.phase}</Badge>
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 3 }}>{t.problem?.slice(0,80)}</div>
                  <div style={{ fontSize: 11, color: T.gray }}>{t.engine_file} → {t.fn_target}</div>
                </div>
                <div style={{ display: "flex", gap: 5 }}>
                  <Btn small variant="success" onClick={() => approveTuning.mutate(t.tuning_id)}>✓ Approve</Btn>
                  <Btn small variant="danger">✕</Btn>
                </div>
              </div>
            </Card>
          ))}
          {(!tunings || tunings.length === 0) && <div style={{ color: T.gray, fontSize: 12, padding: "16px 0" }}>No pending tunings.</div>}
        </div>
      )}
    </div>
  )
}

function ReviewItem({ item, onFeedback }) {
  const [showReason, setShowReason] = useState(false)
  const [reason, setReason] = useState("")
  const score = Math.round(item.quality_score || item.score || 50)
  const scoreColor = score >= 75 ? T.teal : score >= 50 ? T.amber : T.red

  return (
    <Card style={{ marginBottom: 7 }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", gap: 5, marginBottom: 4, flexWrap: "wrap" }}>
            <Badge color="gray" size="xs">{item.item_type}</Badge>
            <Badge color="gray" size="xs">{item.phase}</Badge>
            {item.quality_label && item.quality_label !== "unreviewed" && (
              <Badge color={item.quality_label === "good" ? "teal" : "red"} size="xs">{item.quality_label}</Badge>
            )}
          </div>
          <div style={{ fontSize: 12, fontWeight: 500, color: "#1a1a1a" }}>{item.item_value?.slice(0,80)}</div>
          <div style={{ fontSize: 10, color: T.gray, marginTop: 2 }}>{item.engine_file}</div>
          {showReason && (
            <div style={{ marginTop: 7 }}>
              <input value={reason} onChange={e => setReason(e.target.value)}
                placeholder="Why is this wrong? (trains the exact engine that produced it)"
                onKeyDown={e => { if (e.key === "Enter" && reason.trim()) { onFeedback("bad", reason); setShowReason(false); setReason("") }}}
                style={{ width: "100%", padding: "5px 8px", borderRadius: 7, border: `1px solid ${T.red}`, fontSize: 11, boxSizing: "border-box" }}
                autoFocus/>
            </div>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 5 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: scoreColor,
            background: score >= 75 ? T.tealLight : score >= 50 ? T.amberLight : "#FCEBEB",
            padding: "1px 7px", borderRadius: 99 }}>{score}</span>
          <div style={{ display: "flex", gap: 4 }}>
            <Btn small variant="success" onClick={() => onFeedback("good", "")}>✓</Btn>
            <Btn small variant="danger" onClick={() => setShowReason(true)}>✗ Bad</Btn>
          </div>
        </div>
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: RESEARCH & SELF-DEVELOPMENT (RSD) — Engine health + intelligence
// ─────────────────────────────────────────────────────────────────────────────
function RSDPage() {
  const [tab, setTab] = useState("health")
  const { data: health } = useQuery({
    queryKey: ["rsd-health"],
    queryFn: () => api.get("/api/rsd/health"),
    refetchInterval: 30000
  })
  const { data: intelligence } = useQuery({
    queryKey: ["rsd-intelligence"],
    queryFn: () => api.get("/api/rsd/intelligence-items"),
  })
  const { data: gaps } = useQuery({
    queryKey: ["rsd-gaps"],
    queryFn: () => api.get("/api/rsd/gaps"),
  })
  const { data: implementations } = useQuery({
    queryKey: ["rsd-implementations"],
    queryFn: () => api.get("/api/rsd/implementations"),
  })

  const scanAll = useMutation({
    mutationFn: () => api.post("/api/rsd/scan/all", {}),
  })

  const tabs = ["health", "intelligence", "gaps", "implementations"]

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ fontSize: 20, fontWeight: 600 }}>Research & Self-Development</div>
        <Btn onClick={() => scanAll.mutate()} variant="primary" disabled={scanAll.isPending}>
          {scanAll.isPending ? "Scanning..." : "Scan all engines"}
        </Btn>
      </div>

      <div style={{ display: "flex", gap: 4, borderBottom: "0.5px solid rgba(0,0,0,0.1)", marginBottom: 12 }}>
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "5px 12px", fontSize: 11, fontWeight: 500, cursor: "pointer",
            background: "none", border: "none", borderBottom: tab === t ? `2px solid ${T.purple}` : "2px solid transparent",
            color: tab === t ? T.purple : T.gray, marginBottom: -1,
            textTransform: "capitalize"
          }}>{t}</button>
        ))}
      </div>

      {tab === "health" && (
        <div>
          {health && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10, marginBottom: 16 }}>
                {Object.entries(health.engines || {}).map(([name, status]) => (
                  <Card key={name} style={{ padding: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <StatusDot status={status === "healthy" ? "healthy" : status === "degraded" ? "degraded" : "error"}/>
                      <span style={{ fontSize: 12, fontWeight: 500, textTransform: "capitalize", flex: 1 }}>{name}</span>
                    </div>
                    <div style={{ fontSize: 10, color: T.gray }}>
                      {status === "healthy" ? "All systems operational" : status === "degraded" ? "Needs optimization" : "Error detected"}
                    </div>
                  </Card>
                ))}
              </div>
              <Card>
                <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8 }}>System Status</div>
                <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
                  <Badge color="teal">Last scan: {health.last_scan}</Badge>
                  <Badge color="amber">{health.pending_approvals} pending approvals</Badge>
                </div>
              </Card>
            </>
          )}
        </div>
      )}

      {tab === "intelligence" && (
        <div>
          {intelligence && intelligence.items && intelligence.items.length > 0 ? (
            <div>
              {intelligence.items.map((item, i) => (
                <Card key={i} style={{ marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 4 }}>{item.title || item.type}</div>
                      <div style={{ fontSize: 11, color: T.gray }}>{item.description || "Intelligence item"}</div>
                    </div>
                    <Badge color="purple">{item.source || "internal"}</Badge>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <div style={{ color: T.gray, padding: 20, textAlign: "center", fontSize: 13 }}>No intelligence items yet. Run a scan to collect data.</div>
          )}
        </div>
      )}

      {tab === "gaps" && (
        <div>
          {gaps && gaps.gaps && gaps.gaps.length > 0 ? (
            <div>
              {gaps.gaps.map((gap, i) => (
                <Card key={i} style={{ marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 4 }}>{gap.title || "Knowledge gap"}</div>
                      <div style={{ fontSize: 11, color: T.gray }}>{gap.description}</div>
                      <div style={{ fontSize: 10, color: T.gray, marginTop: 4 }}>Affects: {gap.affected_engines?.join(", ") || "unknown"}</div>
                    </div>
                    <Badge color="amber">gap</Badge>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <div style={{ color: T.gray, padding: 20, textAlign: "center", fontSize: 13 }}>No knowledge gaps detected. System is learning well.</div>
          )}
        </div>
      )}

      {tab === "implementations" && (
        <div>
          {implementations && implementations.implementations && implementations.implementations.length > 0 ? (
            <div>
              {implementations.implementations.map((impl, i) => (
                <Card key={i} style={{ marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 4 }}>{impl.title || "Implementation"}</div>
                      <div style={{ fontSize: 11, color: T.gray }}>{impl.description}</div>
                      <div style={{ fontSize: 10, color: T.teal, marginTop: 4 }}>Applied to: {impl.target_engine}</div>
                    </div>
                    <Badge color="teal">✓ Applied</Badge>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <div style={{ color: T.gray, padding: 20, textAlign: "center", fontSize: 13 }}>No implementations applied yet. Gaps will be addressed automatically.</div>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// NEW PROJECT WIZARD
// ─────────────────────────────────────────────────────────────────────────────
function NewProjectPage() {
  const { setPage, setProject } = useStore()
  const qclient = useQueryClient()
  const [step, setStep] = useState(0)
  const [form, setForm] = useState({
    name: "", industry: "food_spices", description: "",
    seed_keywords: "", competitor_urls: "", language: "english",
    region: "india", religion: "general",
    wp_url: "", wp_user: "", wp_password: "",
  })
  const industries = ["food_spices","tourism","healthcare","ecommerce","agriculture","education","real_estate","tech_saas","wellness","restaurant","fashion","general"]

  const create = useMutation({
    mutationFn: () => api.post("/api/projects", {
      ...form,
      seed_keywords: form.seed_keywords.split(",").map(s=>s.trim()).filter(Boolean),
    }),
    onSuccess: (data) => {
      qclient.invalidateQueries(["projects"])
      setProject(data.project_id)
      setPage("keywords")
    }
  })

  const steps = [
    { label: "Business", icon: "①" },
    { label: "Universe", icon: "②" },
    { label: "Context", icon: "③" },
    { label: "Publishing", icon: "④" },
  ]

  return (
    <div style={{ maxWidth: 520, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 24 }}>
        <Btn small onClick={() => setPage("dashboard")}>← Back</Btn>
        <div style={{ fontSize: 18, fontWeight: 600 }}>New project</div>
      </div>

      {/* Step indicators */}
      <div style={{ display: "flex", gap: 4, marginBottom: 24 }}>
        {steps.map((s, i) => (
          <div key={i} style={{ flex: 1, textAlign: "center", fontSize: 11,
            color: i === step ? T.purple : T.gray,
            borderBottom: `2px solid ${i === step ? T.purple : "rgba(0,0,0,0.1)"}`,
            paddingBottom: 6 }}>
            {s.icon} {s.label}
          </div>
        ))}
      </div>

      {step === 0 && (
        <Card style={{ padding: 20 }}>
          <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Business name *</label>
          <input value={form.name} onChange={e=>setForm({...form,name:e.target.value})}
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,marginBottom:12,boxSizing:"border-box" }}/>
          <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Industry</label>
          <select value={form.industry} onChange={e=>setForm({...form,industry:e.target.value})}
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,marginBottom:12,boxSizing:"border-box" }}>
            {industries.map(i => <option key={i} value={i}>{i.replace("_"," ")}</option>)}
          </select>
          <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Description</label>
          <textarea value={form.description} onChange={e=>setForm({...form,description:e.target.value})} rows={3}
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,resize:"vertical",boxSizing:"border-box" }}/>
          <Btn onClick={() => setStep(1)} variant="primary" style={{ marginTop: 16, width: "100%" }} disabled={!form.name}>Continue →</Btn>
        </Card>
      )}

      {step === 1 && (
        <Card style={{ padding: 20 }}>
          <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Universe seeds — one keyword per line or comma-separated *</label>
          <textarea value={form.seed_keywords} onChange={e=>setForm({...form,seed_keywords:e.target.value})} rows={4}
            placeholder="black pepper&#10;cinnamon&#10;cardamom"
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,resize:"vertical",marginBottom:12,boxSizing:"border-box" }}/>
          <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Competitor URLs (one per line — used for pillar extraction)</label>
          <textarea value={form.competitor_urls} onChange={e=>setForm({...form,competitor_urls:e.target.value})} rows={3}
            placeholder="https://competitor1.com&#10;https://competitor2.com"
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,resize:"vertical",marginBottom:12,boxSizing:"border-box" }}/>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={() => setStep(0)}>← Back</Btn>
            <Btn onClick={() => setStep(2)} variant="primary" style={{ flex: 1 }} disabled={!form.seed_keywords}>Continue →</Btn>
          </div>
        </Card>
      )}

      {step === 2 && (
        <Card style={{ padding: 20 }}>
          <div style={{ fontSize: 12, color: T.gray, marginBottom: 12 }}>Language, region and religion — used for content variants and keyword expansion.</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 16 }}>
            <div>
              <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Language</label>
              <select value={form.language} onChange={e=>setForm({...form,language:e.target.value})}
                style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,boxSizing:"border-box" }}>
                {["english","malayalam","hindi","tamil","arabic"].map(l=><option key={l}>{l}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Region</label>
              <select value={form.region} onChange={e=>setForm({...form,region:e.target.value})}
                style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,boxSizing:"border-box" }}>
                {["india","kerala","wayanad","global","south_india"].map(r=><option key={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Religion context</label>
              <select value={form.religion} onChange={e=>setForm({...form,religion:e.target.value})}
                style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,boxSizing:"border-box" }}>
                {["general","ayurveda","halal","unani","hindu","christian"].map(r=><option key={r}>{r}</option>)}
              </select>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={() => setStep(1)}>← Back</Btn>
            <Btn onClick={() => setStep(3)} variant="primary" style={{ flex: 1 }}>Continue →</Btn>
          </div>
        </Card>
      )}

      {step === 3 && (
        <Card style={{ padding: 20 }}>
          <div style={{ fontSize: 12, color: T.gray, marginBottom: 12 }}>WordPress publishing (optional — can add later)</div>
          <input value={form.wp_url} onChange={e=>setForm({...form,wp_url:e.target.value})} placeholder="https://yoursite.com"
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,marginBottom:8,boxSizing:"border-box" }}/>
          <input value={form.wp_user} onChange={e=>setForm({...form,wp_user:e.target.value})} placeholder="WordPress username"
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,marginBottom:8,boxSizing:"border-box" }}/>
          <input value={form.wp_password} onChange={e=>setForm({...form,wp_password:e.target.value})} placeholder="Application password" type="password"
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,marginBottom:16,boxSizing:"border-box" }}/>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={() => setStep(2)}>← Back</Btn>
            <Btn onClick={() => create.mutate()} variant="primary" style={{ flex: 1 }} disabled={create.isPending}>
              {create.isPending ? "Creating..." : "Create project"}
            </Btn>
          </div>
        </Card>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SIDEBAR + LAYOUT
// ─────────────────────────────────────────────────────────────────────────────

const NAV = [
  { id: "dashboard",    label: "Dashboard",    icon: "⬛" },
  { id: "kw-input",     label: "KW Input",     icon: "⬛" },
  { id: "keywords",     label: "Keywords",     icon: "⬛" },
  { id: "keyword-tree", label: "Keyword tree", icon: "⬛" },
  { id: "content",      label: "Content",      icon: "⬛" },
  { id: "calendar",     label: "Calendar",     icon: "⬛" },
  { id: "seo-checker",  label: "SEO checker",  icon: "⬛" },
  { id: "rankings",     label: "Rankings",     icon: "⬛" },
  { id: "quality",      label: "Quality",      icon: "⬛" },
  { id: "rsd",          label: "Research & Dev", icon: "⬛" },
  { id: "bug-fixer",    label: "Bug Fixer",    icon: "⬛" },
  { id: "settings",     label: "Settings",     icon: "⬛" },
]

function Sidebar({ page, setPage }) {
  const { activeProject, logout } = useStore()
  const dotColors = { dashboard:"purple",keywords:"teal","keyword-tree":"teal",content:"purple",calendar:"amber",
    "seo-checker":"purple",rankings:"teal",quality:"amber",rsd:"teal" }
  return (
    <div style={{ width: 196, flexShrink: 0, borderRight: "0.5px solid rgba(0,0,0,0.1)",
      height: "100vh", display: "flex", flexDirection: "column", padding: "16px 0", position: "sticky", top: 0 }}>
      <div style={{ padding: "0 16px 16px", borderBottom: "0.5px solid rgba(0,0,0,0.08)", marginBottom: 8 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: T.purple, letterSpacing: -0.5 }}>AnnaSEO</div>
      </div>
      <div style={{ flex: 1, overflow: "auto" }}>
        {NAV.map(n => (
          <button key={n.id} onClick={() => setPage(n.id)} style={{
            display: "flex", alignItems: "center", gap: 9, padding: "7px 16px",
            width: "100%", border: "none", cursor: "pointer", fontSize: 12, fontWeight: 500,
            background: page === n.id ? T.purpleLight : "transparent",
            color: page === n.id ? T.purpleDark : T.gray,
            borderLeft: `3px solid ${page === n.id ? T.purple : "transparent"}`,
            textAlign: "left",
          }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%",
              background: page === n.id ? T.purple : "rgba(0,0,0,0.1)", flexShrink: 0 }}/>
            {n.label}
          </button>
        ))}
      </div>
      <div style={{ padding: "12px 16px", borderTop: "0.5px solid rgba(0,0,0,0.08)" }}>
        <button onClick={logout} style={{ fontSize: 11, color: T.gray, background: "none", border: "none", cursor: "pointer" }}>
          Sign out
        </button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SETTINGS PAGE — API Keys, AI configuration
// ─────────────────────────────────────────────────────────────────────────────

function SettingsPage() {
  const [keys, setKeys] = useState({
    groq_key: "", gemini_key: "", anthropic_key: "", openai_key: "",
    ollama_url: "http://localhost:11434", ollama_model: "deepseek-r1:7b",
    groq_model: "llama-3.3-70b-versatile",
  })
  const [status, setStatus] = useState({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState("")
  const { data: current } = useQuery({
    queryKey: ["api-keys"],
    queryFn: () => api.get("/api/settings/api-keys"),
  })

  const save = async () => {
    setSaving(true); setMsg("")
    const toSave = {}
    Object.entries(keys).forEach(([k,v]) => { if(v.trim()) toSave[k] = v.trim() })
    const r = await api.post("/api/settings/api-keys", toSave)
    setSaving(false)
    setMsg(r?.status === "ok" ? `✓ Saved ${r.saved?.length || 0} keys` : "Error saving")
  }

  const testKeys = async () => {
    setTesting(true)
    const r = await api.post("/api/settings/test-keys", {})
    setStatus(r || {})
    setTesting(false)
  }

  const Field = ({ label, k, type="text", placeholder="" }) => (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <label style={{ fontSize: 12, fontWeight: 500 }}>{label}</label>
        {current?.[k] !== undefined && (
          <Badge color={current[k] ? "teal" : "red"}>{current[k] ? "configured" : "not set"}</Badge>
        )}
      </div>
      <input type={type} value={keys[k] || ""} onChange={e=>setKeys({...keys,[k]:e.target.value})}
        placeholder={placeholder || `Enter ${label}...`}
        style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",
                 fontSize:12,boxSizing:"border-box",fontFamily:"monospace" }}/>
    </div>
  )

  return (
    <div style={{ maxWidth: 640 }}>
      <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 4 }}>Settings</div>
      <div style={{ fontSize: 12, color: T.gray, marginBottom: 24 }}>API keys are encrypted before storage. They are never exposed in logs.</div>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16, color: T.purple }}>
          AI Model Configuration
        </div>
        <div style={{ fontSize: 11, color: T.gray, background: T.purpleLight, borderRadius: 6, padding: "8px 12px", marginBottom: 16 }}>
          <strong>Routing:</strong> Groq Llama (primary, free) → Ollama/DeepSeek (offline fallback) → Claude (quality gates ≤1000 tokens only)
        </div>
        <Field label="Groq API Key (primary — free tier)" k="groq_key" type="password"
               placeholder="gsk_..." />
        <Field label="Groq Model" k="groq_model" placeholder="llama-3.3-70b-versatile" />
        <Field label="Ollama URL (local DeepSeek)" k="ollama_url" placeholder="http://localhost:11434" />
        <Field label="Ollama Model" k="ollama_model" placeholder="deepseek-r1:7b" />
        <Field label="Google Gemini API Key" k="gemini_key" type="password"
               placeholder="AIzaSy..." />
        <Field label="Anthropic Claude Key (verification only)" k="anthropic_key" type="password"
               placeholder="sk-ant-..." />
        <Field label="OpenAI API Key (optional)" k="openai_key" type="password"
               placeholder="sk-..." />

        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <Btn onClick={save} variant="primary" disabled={saving}>{saving ? "Saving..." : "Save keys"}</Btn>
          <Btn onClick={testKeys} disabled={testing}>{testing ? "Testing..." : "Test connection"}</Btn>
        </div>
        {msg && <div style={{ marginTop: 10, fontSize: 12, color: msg.startsWith("✓") ? T.teal : T.red }}>{msg}</div>}

        {Object.keys(status).length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8 }}>Connection test results:</div>
            {Object.entries(status).map(([k,v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, padding: "4px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)" }}>
                <span style={{ fontWeight: 500 }}>{k}</span>
                <Badge color={v === "ok" ? "teal" : v.startsWith("not") ? "gray" : "red"}>{v}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>AI Routing Priority</div>
        {[
          { model: "Groq Llama-3.3-70b", use: "Bulk analysis: intent, clusters, scoring, universe generation", cost: "Free", badge: "teal" },
          { model: "Ollama/DeepSeek-R1:7b", use: "Offline fallback when Groq unavailable", cost: "Free (local)", badge: "teal" },
          { model: "Claude Sonnet", use: "Quality gates only — pillar validation, content quality check", cost: "~$0.001/check (≤1000 tokens)", badge: "amber" },
          { model: "Google Gemini Flash", use: "P9 clustering, P10 pillar identification", cost: "Free tier", badge: "teal" },
        ].map(r => (
          <div key={r.model} style={{ display: "flex", gap: 12, padding: "8px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 500 }}>{r.model}</div>
              <div style={{ fontSize: 11, color: T.gray }}>{r.use}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <Badge color={r.badge}>{r.cost}</Badge>
            </div>
          </div>
        ))}
      </Card>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: BUG FIXER — error collector + AI fix proposals
// ─────────────────────────────────────────────────────────────────────────────
function BugFixerPage() {
  const [tab, setTab] = useState("errors")
  const qclient = useQueryClient()

  const { data: errors, isLoading: errLoading } = useQuery({
    queryKey: ["errors"],
    queryFn: () => api.get("/api/errors?limit=50"),
    refetchInterval: 15000,
  })
  const { data: fixes, isLoading: fixLoading } = useQuery({
    queryKey: ["fixes"],
    queryFn: () => api.get("/api/fixes?limit=50"),
    refetchInterval: 15000,
  })

  const analyze = useMutation({
    mutationFn: (id) => api.post(`/api/errors/${id}/analyze`, {}),
    onSuccess: () => { setTimeout(() => qclient.invalidateQueries(["errors"]), 2000) }
  })
  const approveFix = useMutation({
    mutationFn: (id) => api.post(`/api/fixes/${id}/approve`, {}),
    onSuccess: () => qclient.invalidateQueries(["fixes"])
  })
  const rejectFix = useMutation({
    mutationFn: (id) => api.post(`/api/fixes/${id}/reject`, {}),
    onSuccess: () => qclient.invalidateQueries(["fixes"])
  })
  const rollbackFix = useMutation({
    mutationFn: (id) => api.post(`/api/fixes/${id}/rollback`, {}),
    onSuccess: () => qclient.invalidateQueries(["fixes"])
  })

  const statusColor = {
    new: "gray", analyzing: "amber", fix_ready: "purple",
    approved: "teal", applied: "teal", rejected: "red", rolled_back: "gray"
  }
  const verdictColor = { approved: "teal", rejected: "red", pending: "amber" }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ fontSize: 20, fontWeight: 600 }}>Bug Fixer</div>
        <div style={{ fontSize: 12, color: T.gray }}>
          {(errors || []).filter(e => e.status === "new").length} new errors ·
          {" "}{(fixes || []).filter(f => f.status === "pending").length} fixes awaiting approval
        </div>
      </div>

      <div style={{ display: "flex", gap: 4, borderBottom: "0.5px solid rgba(0,0,0,0.1)", marginBottom: 14 }}>
        {["errors","fixes"].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "5px 14px", fontSize: 11, fontWeight: 500, cursor: "pointer",
            background: "none", border: "none",
            borderBottom: tab === t ? `2px solid ${T.purple}` : "2px solid transparent",
            color: tab === t ? T.purple : T.gray, marginBottom: -1,
          }}>{t === "errors" ? `Errors (${(errors||[]).length})` : `Fix Proposals (${(fixes||[]).length})`}</button>
        ))}
      </div>

      {tab === "errors" && (
        <div>
          {errLoading ? <LoadingSpinner/> : (errors || []).length === 0 ? (
            <div style={{ color: T.gray, fontSize: 13, padding: "20px 0", textAlign: "center" }}>No errors recorded yet.</div>
          ) : (errors || []).map(e => (
            <Card key={e.error_id} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
                    <Badge color={e.source === "browser" ? "amber" : "purple"}>{e.source}</Badge>
                    <Badge color={statusColor[e.status] || "gray"}>{e.status}</Badge>
                    <span style={{ fontSize: 10, color: T.gray }}>{e.created_at?.slice(0,16)}</span>
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: "#1a1a1a", marginBottom: 3 }}>
                    {e.message?.slice(0, 120)}
                  </div>
                  {e.traceback && (
                    <div style={{ fontSize: 10, color: T.gray, fontFamily: "monospace",
                      background: "#f5f5f5", borderRadius: 6, padding: "4px 8px", marginTop: 4,
                      maxHeight: 60, overflow: "hidden" }}>
                      {e.traceback?.slice(0, 200)}
                    </div>
                  )}
                </div>
                {["new","fix_ready"].includes(e.status) && (
                  <Btn small variant="primary" disabled={analyze.isPending || e.status === "analyzing"}
                    onClick={() => analyze.mutate(e.error_id)}>
                    {e.status === "analyzing" ? "Analyzing..." : "Analyze"}
                  </Btn>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {tab === "fixes" && (
        <div>
          {fixLoading ? <LoadingSpinner/> : (fixes || []).length === 0 ? (
            <div style={{ color: T.gray, fontSize: 13, padding: "20px 0", textAlign: "center" }}>No fix proposals yet. Analyze an error first.</div>
          ) : (fixes || []).map(f => (
            <Card key={f.fix_id} style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap", alignItems: "center" }}>
                <Badge color={statusColor[f.status] || "gray"}>{f.status}</Badge>
                <Badge color={verdictColor[f.claude_verdict] || "gray"}>Claude: {f.claude_verdict}</Badge>
                <span style={{ fontSize: 11, color: T.gray }}>{f.target_file} → {f.target_function}</span>
                <span style={{ fontSize: 10, color: T.gray, marginLeft: "auto" }}>{f.created_at?.slice(0,16)}</span>
              </div>

              {f.claude_reason && (
                <div style={{ fontSize: 11, color: f.claude_verdict === "approved" ? T.teal : T.amber,
                  background: f.claude_verdict === "approved" ? T.tealLight : T.amberLight,
                  borderRadius: 6, padding: "5px 10px", marginBottom: 8 }}>
                  Claude: {f.claude_reason}
                </div>
              )}

              {/* Diff view */}
              {f.diff_text && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: 10, color: T.red, fontWeight: 500, marginBottom: 3 }}>Original</div>
                    <pre style={{ fontSize: 10, background: "#FFF5F5", borderRadius: 6, padding: "6px 8px",
                      maxHeight: 120, overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-all",
                      margin: 0, color: T.red }}>
                      {f.original_snippet?.slice(0, 400) || "(not extracted)"}
                    </pre>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: T.teal, fontWeight: 500, marginBottom: 3 }}>Proposed fix</div>
                    <pre style={{ fontSize: 10, background: "#F0FFF4", borderRadius: 6, padding: "6px 8px",
                      maxHeight: 120, overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-all",
                      margin: 0, color: T.teal }}>
                      {f.proposed_snippet?.slice(0, 400)}
                    </pre>
                  </div>
                </div>
              )}

              {f.status === "pending" && (
                <div style={{ display: "flex", gap: 6 }}>
                  <Btn small variant="success" disabled={approveFix.isPending}
                    onClick={() => approveFix.mutate(f.fix_id)}>✓ Approve & Apply</Btn>
                  <Btn small variant="danger" disabled={rejectFix.isPending}
                    onClick={() => rejectFix.mutate(f.fix_id)}>✕ Reject</Btn>
                </div>
              )}
              {f.status === "applied" && (
                <Btn small variant="danger" disabled={rollbackFix.isPending}
                  onClick={() => { if(window.confirm("Roll back this fix?")) rollbackFix.mutate(f.fix_id) }}>
                  ↩ Rollback
                </Btn>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ROOT APP
// ─────────────────────────────────────────────────────────────────────────────

function App() {
  const { token, currentPage, setPage, activeProject } = useStore()

  // Browser error capture → send to /api/errors/report
  useEffect(() => {
    const onError = (e) => {
      api.post("/api/errors/report", {
        source: "browser",
        message: e.message || String(e),
        traceback: `${e.filename || ""}:${e.lineno || 0}`,
        context: { colno: e.colno, type: e.type },
      }).catch(() => {})
    }
    const onUnhandled = (e) => {
      api.post("/api/errors/report", {
        source: "browser",
        message: String(e.reason || "Unhandled promise rejection"),
        traceback: "",
        context: {},
      }).catch(() => {})
    }
    window.addEventListener("error", onError)
    window.addEventListener("unhandledrejection", onUnhandled)
    return () => {
      window.removeEventListener("error", onError)
      window.removeEventListener("unhandledrejection", onUnhandled)
    }
  }, [])

  if (!token || currentPage === "login") return <LoginPage/>

  const pages = {
    dashboard:    <DashboardPage/>,
    "kw-input":   <KeywordInputPage projectId={activeProject}/>,
    "keywords":   <KeywordsPage/>,
    "keyword-tree":<KeywordTreePage/>,
    content:      <ContentPage/>,
    calendar:     <CalendarPage/>,
    "seo-checker":<SEOCheckerPage/>,
    rankings:     <RankingsPage/>,
    quality:      <QualityDashboard/>,
    "rsd":        <RSDPage/>,
    "bug-fixer":  <BugFixerPage/>,
    "new-project":<NewProjectPage/>,
    settings:     <SettingsPage/>,
  }

  return (
    <>
      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #fafafa; color: #1a1a1a; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
        input, select, textarea, button { font-family: inherit; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.15); border-radius: 99px; }
      `}</style>
      <div style={{ display: "flex", minHeight: "100vh" }}>
        <Sidebar page={currentPage} setPage={setPage}/>
        <main style={{ flex: 1, padding: "24px 28px", overflowY: "auto", maxHeight: "100vh" }}>
          {pages[currentPage] || <DashboardPage/>}
        </main>
      </div>
    </>
  )
}

export default function Root() {
  return (
    <QueryClientProvider client={qc}>
      <App/>
    </QueryClientProvider>
  )
}
