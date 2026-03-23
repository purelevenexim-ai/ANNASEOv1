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
    return r.json()
  },
  put: async (path, body) => {
    const token = useStore.getState().token
    const r = await fetch(`${API}${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body),
    })
    return r.json()
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

      {/* Keyword mix overview */}
      {kwStats && kwStats.total > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 12 }}>Keyword distribution</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
            {[
              { label: "Pillars", count: kwStats.pillar_count, pct: kwStats.distribution.pillar, color: T.purple },
              { label: "Clusters", count: kwStats.cluster_count, pct: kwStats.distribution.cluster, color: T.teal },
              { label: "Supporting", count: kwStats.supporting_count, pct: kwStats.distribution.supporting, color: T.green },
            ].map(item => (
              <div key={item.label} style={{ padding: 12, borderRadius: 8, background: "rgba(0,0,0,0.02)", display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ fontSize: 11, color: T.gray }}>{item.label}</div>
                <div style={{ fontSize: 18, fontWeight: 600, color: item.color }}>{item.count}</div>
                <div style={{ fontSize: 10, color: item.color }}>{item.pct}% of total</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Projects grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12, marginBottom: 20 }}>
        {(projects || []).map(p => (
          <Card key={p.project_id} onClick={() => { setProject(p.project_id); setPage("keywords") }}
            style={{ cursor: "pointer", borderColor: activeProject === p.project_id ? T.purple : "rgba(0,0,0,0.1)", borderWidth: activeProject === p.project_id ? 1.5 : 0.5 }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#1a1a1a" }}>{p.name}</div>
                <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>{p.industry}</div>
              </div>
              <Badge color={p.status === "active" ? "teal" : "gray"}>{p.status}</Badge>
            </div>
            <div style={{ marginTop: 10, fontSize: 11, color: T.gray }}>
              {JSON.parse(p.seed_keywords || "[]").slice(0,3).join(", ") || "No seeds yet"}
            </div>
          </Card>
        ))}
      </div>

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
function KeywordsPage() {
  const { activeProject } = useStore()
  const [seed, setSeed] = useState("")
  const [runId, setRunId] = useState(null)
  const [events, setEvents] = useState([])
  const [runStatus, setRunStatus] = useState("idle") // idle | running | waiting_gate | complete | error
  const [gateData, setGateData] = useState(null)
  const [gateName, setGateName] = useState(null)
  const esRef = useRef(null)
  const { data: runs } = useQuery({ queryKey: ["runs", activeProject], queryFn: () => api.get(`/api/projects/${activeProject}/runs`), enabled: !!activeProject })

  const startRun = async () => {
    if (!seed.trim() || !activeProject) return
    setEvents([]); setRunStatus("running")
    const data = await api.post(`/api/projects/${activeProject}/runs`, { seed: seed.trim(), language: "english", region: "india" })
    if (!data?.run_id) { setRunStatus("error"); return }
    setRunId(data.run_id)
    // Connect SSE
    if (esRef.current) esRef.current.close()
    const es = new EventSource(`${API}${data.stream_url}`)
    esRef.current = es
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data)
      ev.timestamp = new Date().toISOString()
      setEvents(prev => [...prev, ev])
      if (ev.type === "gate") { setGateData(ev.data); setGateName(ev.gate); setRunStatus("waiting_gate") }
      if (ev.type === "complete") { setRunStatus("complete"); es.close() }
      if (ev.type === "error") { setRunStatus("error"); es.close() }
    }
    es.onerror = () => { setRunStatus("error"); es.close() }
  }

  const confirmGate = async () => {
    await api.post(`/api/runs/${runId}/confirm/${gateName}`, gateData || {})
    setRunStatus("running"); setGateData(null); setGateName(null)
  }

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>Keyword Universe</div>

      {/* Run starter */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10 }}>Run 20-phase keyword universe</div>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={seed} onChange={e=>setSeed(e.target.value)} placeholder="Enter seed keyword (e.g. cinnamon)"
            onKeyDown={e => e.key === "Enter" && startRun()}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 13 }}/>
          <Btn onClick={startRun} variant="primary" disabled={runStatus === "running"}>
            {runStatus === "running" ? "Running..." : "Start run"}
          </Btn>
        </div>
        {runStatus === "waiting_gate" && (
          <div style={{ marginTop: 12, padding: "10px 12px", background: T.amberLight, borderRadius: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 500, color: T.amber, marginBottom: 6 }}>
              Gate {gateName} — review and confirm to continue
            </div>
            <div style={{ fontSize: 11, color: T.gray, marginBottom: 8 }}>
              {gateData ? JSON.stringify(gateData).slice(0, 200) : ""}
            </div>
            <Btn onClick={confirmGate} variant="success" small>✓ Confirm and continue</Btn>
          </div>
        )}
      </Card>

      {/* SSE Console */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8, display: "flex", alignItems: "center", gap: 8 }}>
          Engine console
          {runStatus === "running" && <span style={{ width: 7, height: 7, borderRadius: "50%", background: T.teal, display: "inline-block", animation: "pulse 1s infinite" }}/>}
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

  return (
    <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 1fr" : "1fr", gap: 16 }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>Content</div>
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
          <Card key={a.article_id} onClick={() => setSelected(a)}
            style={{ marginBottom: 8, cursor: "pointer", borderColor: selected?.article_id === a.article_id ? T.purple : "rgba(0,0,0,0.1)" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 500, color: "#1a1a1a" }}>{a.title || a.keyword}</div>
                <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>{a.keyword}</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                <Badge color={statusColor[a.status] || "gray"}>{a.status}</Badge>
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
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
  const [year] = useState(new Date().getFullYear())

  // Mock data — replace with /api/projects/{id}/calendar
  const mockItems = [
    { month: 0, count: 4, published: 2 },
    { month: 1, count: 6, published: 3 },
    { month: 2, count: 8, published: 5 },
    { month: 3, count: 5, published: 0 },
  ]

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>Content Calendar {year}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16 }}>
        {months.map((m, i) => {
          const d = mockItems.find(x => x.month === i)
          const isPast = i < new Date().getMonth()
          return (
            <Card key={m} style={{ opacity: isPast ? 0.7 : 1 }}>
              <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8 }}>{m} {year}</div>
              {d ? (
                <>
                  <div style={{ fontSize: 22, fontWeight: 600, color: T.purple }}>{d.count}</div>
                  <div style={{ fontSize: 10, color: T.gray }}>articles planned</div>
                  <div style={{ marginTop: 8 }}>
                    <div style={{ display: "flex", height: 5, borderRadius: 99, overflow: "hidden", background: T.purpleLight }}>
                      <div style={{ width: `${(d.published/d.count)*100}%`, background: T.teal }}/>
                    </div>
                    <div style={{ fontSize: 10, color: T.teal, marginTop: 3 }}>{d.published} published</div>
                  </div>
                </>
              ) : (
                <div style={{ fontSize: 11, color: T.gray }}>No articles scheduled</div>
              )}
            </Card>
          )
        })}
      </div>
      <Card>
        <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10 }}>Upcoming articles</div>
        {[
          { kw: "ceylon cinnamon health benefits", date: "Apr 5", status: "approved" },
          { kw: "buy cinnamon online kerala", date: "Apr 8", status: "draft" },
          { kw: "cinnamon vs cassia difference", date: "Apr 12", status: "generating" },
          { kw: "organic cinnamon wholesale price", date: "Apr 15", status: "draft" },
        ].map((a, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 12 }}>
            <span style={{ color: T.gray, minWidth: 40, fontSize: 11 }}>{a.date}</span>
            <span style={{ flex: 1 }}>{a.kw}</span>
            <Badge color={{ approved:"teal",draft:"gray",generating:"amber" }[a.status] || "gray"}>{a.status}</Badge>
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
              <span style={{ fontSize: 11, color: T.gray }}>{r.clicks} clicks</span>
              <span style={{ fontSize: 11, color: T.gray }}>{(r.ctr * 100).toFixed(1)}% CTR</span>
            </div>
          ))}
        </Card>
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
    seed_keywords: "", language: "english", region: "india",
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
    { label: "Keywords", icon: "②" },
    { label: "Publishing", icon: "③" },
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
          <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Seed keywords (comma-separated) *</label>
          <textarea value={form.seed_keywords} onChange={e=>setForm({...form,seed_keywords:e.target.value})} rows={3}
            placeholder="cinnamon, black pepper, cardamom"
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,resize:"vertical",marginBottom:12,boxSizing:"border-box" }}/>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
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
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={() => setStep(0)}>← Back</Btn>
            <Btn onClick={() => setStep(2)} variant="primary" style={{ flex: 1 }} disabled={!form.seed_keywords}>Continue →</Btn>
          </div>
        </Card>
      )}

      {step === 2 && (
        <Card style={{ padding: 20 }}>
          <div style={{ fontSize: 12, color: T.gray, marginBottom: 12 }}>WordPress publishing (optional — can add later)</div>
          <input value={form.wp_url} onChange={e=>setForm({...form,wp_url:e.target.value})} placeholder="https://yoursite.com"
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,marginBottom:8,boxSizing:"border-box" }}/>
          <input value={form.wp_user} onChange={e=>setForm({...form,wp_user:e.target.value})} placeholder="WordPress username"
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,marginBottom:8,boxSizing:"border-box" }}/>
          <input value={form.wp_password} onChange={e=>setForm({...form,wp_password:e.target.value})} placeholder="Application password" type="password"
            style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,marginBottom:16,boxSizing:"border-box" }}/>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={() => setStep(1)}>← Back</Btn>
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
  { id: "keywords",     label: "Keywords",     icon: "⬛" },
  { id: "keyword-tree", label: "Keyword tree", icon: "⬛" },
  { id: "content",      label: "Content",      icon: "⬛" },
  { id: "calendar",     label: "Calendar",     icon: "⬛" },
  { id: "seo-checker",  label: "SEO checker",  icon: "⬛" },
  { id: "rankings",     label: "Rankings",     icon: "⬛" },
  { id: "quality",      label: "Quality",     icon: "⬛" },
  { id: "rsd",          label: "Research & Dev",     icon: "⬛" },
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
// ROOT APP
// ─────────────────────────────────────────────────────────────────────────────

function App() {
  const { token, currentPage, setPage } = useStore()

  if (!token || currentPage === "login") return <LoginPage/>

  const pages = {
    dashboard:    <DashboardPage/>,
    "keywords":   <KeywordsPage/>,
    "keyword-tree":<KeywordTreePage/>,
    content:      <ContentPage/>,
    calendar:     <CalendarPage/>,
    "seo-checker":<SEOCheckerPage/>,
    rankings:     <RankingsPage/>,
    quality:      <QualityDashboard/>,
    "rsd":        <RSDPage/>,
    "new-project":<NewProjectPage/>,
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
