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
import KeywordWorkflow from "./KeywordWorkflow"
import StrategyPage from "./StrategyPage"
import StrategyIntelligenceHub from "./StrategyIntelligenceHub"
import DashboardPage from "./DashboardPage"
import ContentPage from "./ContentPage"
import PromptEditorPage from "./PromptEditorPage"
import KwPage from "./kw2/KwPage"
import AuditPage from "./AuditPage"
import PagesPage from "./PagesPage"
import GscSetupPage from "./gsc/GscSetupPage"
import GscSearchPage from "./gsc/GscSearchPage"
import Notification from "./components/Notification"
import DebugPanel from "./components/DebugPanel"
import useDebug from "./store/debug"
import fetchDebug from "./lib/fetchDebug"
import useWorkflowContext from "./store/workflowContext"

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
  setProject: (id) => {
    const current = get().activeProject
    localStorage.setItem("annaseo_project", id || "")
    set({ activeProject: id })
    // Reset workflow context when switching to a different project to prevent data bleed
    if (id !== current) {
      try { useWorkflowContext.getState().reset() } catch (_) {}
    }
  },
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
    const url = `${API}${path}`
    const start = Date.now()
    const { res, parsed } = await fetchDebug(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    const duration = Date.now() - start
    if (res.status === 401) { useStore.getState().logout(); return null }
    return parsed
  },
  post: async (path, body) => {
    const token = useStore.getState().token
    const url = `${API}${path}`
    const start = Date.now()
    const { res, parsed } = await fetchDebug(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body),
    })
    const duration = Date.now() - start
    if (res.status === 401) { useStore.getState().logout(); return null }
    return parsed
  },
  put: async (path, body) => {
    const token = useStore.getState().token
    const url = `${API}${path}`
    const start = Date.now()
    const { res, parsed } = await fetchDebug(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body),
    })
    const duration = Date.now() - start
    if (res.status === 401) { useStore.getState().logout(); return null }
    return parsed
  },
  delete: async (path) => {
    const token = useStore.getState().token
    const url = `${API}${path}`
    const start = Date.now()
    const { res, parsed } = await fetchDebug(url, {
      method: "DELETE",
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
    const duration = Date.now() - start
    if (res.status === 401) { useStore.getState().logout(); return null }
    return parsed
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// DESIGN TOKENS
// ─────────────────────────────────────────────────────────────────────────────
const T = {
  // Apple System Blue as primary accent
  purple: "#007AFF",
  purpleLight: "rgba(0,122,255,0.1)",
  purpleDark: "#0040DD",
  // Apple Green
  teal: "#34C759",
  tealLight: "rgba(52,199,89,0.1)",
  // Apple Red
  red: "#FF3B30",
  // Apple Orange
  amber: "#FF9500",
  amberLight: "rgba(255,149,0,0.1)",
  // Same as teal
  green: "#34C759",
  greenLight: "rgba(52,199,89,0.1)",
  // Apple neutral scale
  gray: "#8E8E93",
  grayLight: "#F2F2F7",
  border: "rgba(60,60,67,0.12)",
  text: "#000000",
  textSoft: "rgba(60,60,67,0.55)",
  // Sidebar — clean white
  sidebarBg: "#FFFFFF",
  sidebarText: "rgba(60,60,67,0.75)",
  sidebarActive: "#007AFF",
  sidebarHover: "rgba(0,0,0,0.04)",
  // Meta
  cardShadow: "0 1px 2px rgba(0,0,0,0.05), 0 0 0 0.5px rgba(0,0,0,0.07)",
  displayFont: "-apple-system, BlinkMacSystemFont, 'Plus Jakarta Sans', 'Helvetica Neue', sans-serif",
  bodyFont:    "-apple-system, BlinkMacSystemFont, 'Plus Jakarta Sans', 'Helvetica Neue', sans-serif",
  articleFont: "'Lora', Georgia, serif",
}

// ─────────────────────────────────────────────────────────────────────────────
// SHARED COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

function Badge({ children, color = "purple", size = "sm" }) {
  const colors = {
    purple: { bg: "rgba(0,122,255,0.1)",    text: "#007AFF" },
    green:  { bg: "rgba(52,199,89,0.1)",    text: "#34C759" },
    red:    { bg: "rgba(255,59,48,0.1)",    text: "#FF3B30" },
    amber:  { bg: "rgba(255,149,0,0.1)",    text: "#FF9500" },
    teal:   { bg: "rgba(52,199,89,0.1)",    text: "#34C759" },
    gray:   { bg: "rgba(142,142,147,0.12)", text: "#8E8E93" },
  }
  const c = colors[color] || colors.purple
  return (
    <span style={{
      background: c.bg, color: c.text,
      fontSize: size === "xs" ? 9 : 10, fontWeight: 600,
      padding: size === "xs" ? "1px 6px" : "2px 8px",
      borderRadius: 99, whiteSpace: "nowrap", display: "inline-block",
      letterSpacing: 0.1,
    }}>{children}</span>
  )
}

function Card({ children, style = {}, onClick }) {
  return (
    <div onClick={onClick} style={{
      background: "#FFFFFF",
      borderRadius: 13,
      boxShadow: T.cardShadow,
      padding: "12px 14px",
      cursor: onClick ? "pointer" : "default",
      ...style
    }}>{children}</div>
  )
}

function StatCard({ label, value, sub, color = T.purple }) {
  return (
    <Card style={{ textAlign: "center", padding: "14px 10px" }}>
      <div style={{ fontSize: 28, fontWeight: 700, color, lineHeight: 1, letterSpacing: -0.5 }}>{value ?? "—"}</div>
      {sub && <div style={{ fontSize: 10, color: T.gray, marginTop: 3 }}>{sub}</div>}
      <div style={{ fontSize: 11, color: T.textSoft, marginTop: 5, fontWeight: 500 }}>{label}</div>
    </Card>
  )
}

function Btn({ children, onClick, variant = "default", small, disabled, style = {} }) {
  const styles = {
    default: { background: "#F2F2F7",                    color: "#000000",  border: "none" },
    primary: { background: "#007AFF",                    color: "#FFFFFF",  border: "none" },
    danger:  { background: "rgba(255,59,48,0.1)",        color: "#FF3B30",  border: "none" },
    success: { background: "rgba(52,199,89,0.1)",        color: "#34C759",  border: "none" },
  }
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: small ? "4px 11px" : "7px 16px",
      borderRadius: 10, fontSize: small ? 11 : 13, fontWeight: 500,
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.45 : 1,
      transition: "opacity 0.15s ease",
      lineHeight: 1.3,
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

// ── Shared exports for external page components ───────────────────────────────
export { T, api, useStore, Badge, Card, StatCard, Btn, LoadingSpinner, ScoreRing, StatusDot }
// EditProjectModal and ConfirmModal exported below after their definitions

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
        width: 24, height: 24,
        border: `2.5px solid rgba(0,122,255,0.15)`,
        borderTopColor: "#007AFF",
        borderRadius: "50%",
        animation: "spin 0.65s linear infinite"
      }}/>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MODAL — Edit Project
// ─────────────────────────────────────────────────────────────────────────────
function EditProjectModal({ project, onClose, onSaved }) {
  const _tryParse = (v, fallback) => { try { return JSON.parse(v || "[]") } catch { return fallback } }
  const [form, setForm] = useState({
    name:             project.name || "",
    description:      project.description || "",
    seed_keywords:    _tryParse(project.seed_keywords, []).join(", "),
    language:         project.language || "english",
    region:           project.region || "india",
    religion:         project.religion || "general",
    wp_url:           project.wp_url || "",
    wp_user:          project.wp_user || "",
    wp_password:      "",
    business_type:    project.business_type || "B2C",
    usp:              project.usp || "",
    target_locations: _tryParse(project.target_locations, []),
    target_languages: _tryParse(project.target_languages, []),
    audience_personas:_tryParse(project.audience_personas, []),
  })
  const [saving, setSaving] = useState(false)

  const toggleArr = (key, val) => setForm(f => ({
    ...f, [key]: f[key].includes(val) ? f[key].filter(x => x !== val) : [...f[key], val]
  }))

  const save = async () => {
    setSaving(true)
    await api.put(`/api/projects/${project.project_id}`, {
      ...form,
      seed_keywords: form.seed_keywords.split(",").map(s => s.trim()).filter(Boolean),
    })
    setSaving(false); onSaved(); onClose()
  }

  const FS = { width: "100%", padding: "7px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 12, boxSizing: "border-box" }
  const Lbl = ({ children }) => <label style={{ fontSize: 11, color: T.gray, display: "block", marginBottom: 3 }}>{children}</label>
  const ChipGroup = ({ label, fieldKey, opts }) => (
    <div style={{ marginBottom: 12 }}>
      <label style={{ fontSize: 11, color: T.gray, display: "block", marginBottom: 4 }}>{label}</label>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
        {opts.map(o => {
          const active = (form[fieldKey] || []).includes(o)
          return (
            <button key={o} onClick={() => toggleArr(fieldKey, o)} style={{
              padding: "3px 9px", borderRadius: 99, fontSize: 11, cursor: "pointer", border: "none",
              background: active ? T.purple : T.grayLight, color: active ? "#fff" : T.gray,
            }}>{o}</button>
          )
        })}
      </div>
    </div>
  )

  const basicFields = [
    ["Project name","name","text"],["Description","description","text"],
    ["Seed keywords (comma-separated)","seed_keywords","text"],
    ["WordPress URL","wp_url","text"],["WordPress user","wp_user","text"],
    ["WordPress password","wp_password","password"],
  ]
  const selectFields = [
    ["Language","language",["english","malayalam","hindi","tamil","arabic","kannada","telugu"]],
    ["Region","region",["india","kerala","wayanad","global","south_india","malabar"]],
    ["Religion context","religion",["general","ayurveda","halal","unani","hindu","christian","muslim"]],
    ["Business type","business_type",["B2C","B2B","D2C","Service","Marketplace"]],
  ]

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{ background: "#fff", borderRadius: 14, padding: 24, width: 480, maxHeight: "85vh", overflowY: "auto" }}>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Edit project</div>

        {basicFields.map(([label, fkey, type]) => (
          <div key={fkey} style={{ marginBottom: 10 }}>
            <Lbl>{label}</Lbl>
            <input type={type} value={form[fkey]} onChange={e => setForm({...form,[fkey]:e.target.value})} style={FS}/>
          </div>
        ))}

        {selectFields.map(([label, fkey, opts]) => (
          <div key={fkey} style={{ marginBottom: 10 }}>
            <Lbl>{label}</Lbl>
            <select value={form[fkey]} onChange={e => setForm({...form,[fkey]:e.target.value})} style={FS}>
              {opts.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
        ))}

        <div style={{ marginBottom: 10 }}>
          <Lbl>USP (Unique Selling Proposition)</Lbl>
          <textarea value={form.usp} onChange={e => setForm({...form, usp: e.target.value})} rows={2}
            placeholder="What makes you unique?" style={{...FS, resize: "vertical"}}/>
        </div>

        <ChipGroup label="Target Locations" fieldKey="target_locations"
          opts={["global","india","south_india","kerala","malabar","kochi","kozhikode","wayanad","national"]} />
        <ChipGroup label="Target Languages" fieldKey="target_languages"
          opts={["english","malayalam","hindi","tamil","kannada","telugu","arabic"]} />

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

export { EditProjectModal, ConfirmModal }

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
      const { res, parsed: data } = await fetchDebug(`${API}/api/auth/login`, { method: "POST", body: fd })
      if (!res.ok) { setErr("Invalid credentials"); return }
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

  const inputStyle = {
    width: "100%", padding: "10px 12px", borderRadius: 10,
    background: "#F2F2F7", border: "none",
    fontSize: 15, marginBottom: 8, boxSizing: "border-box",
    color: "#000", outline: "none",
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#F2F2F7" }}>
      <div style={{ width: 360 }}>
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div style={{ fontSize: 30, fontWeight: 700, color: "#000000", letterSpacing: -0.8 }}>
            Anna<span style={{ color: "#007AFF" }}>SEO</span>
          </div>
          <div style={{ fontSize: 13, color: "rgba(60,60,67,0.55)", marginTop: 5 }}>AI Keyword & Content OS</div>
        </div>
        <Card style={{ padding: "24px 20px", borderRadius: 16 }}>
          {/* Mode toggle */}
          <div style={{
            display: "flex", background: "#F2F2F7", borderRadius: 10,
            padding: 2, marginBottom: 20,
          }}>
            {["login","register"].map(m => (
              <button key={m} onClick={() => setMode(m)} style={{
                flex: 1, padding: "7px 0", borderRadius: 8, fontSize: 13, fontWeight: 500,
                border: "none", cursor: "pointer", transition: "background 0.15s",
                background: mode === m ? "#fff" : "transparent",
                color: mode === m ? "#000" : "rgba(60,60,67,0.55)",
                boxShadow: mode === m ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
              }}>{m === "login" ? "Sign in" : "Register"}</button>
            ))}
          </div>
          {mode === "register" && (
            <input value={name} onChange={e=>setName(e.target.value)} placeholder="Full name" style={inputStyle}/>
          )}
          <input value={email} onChange={e=>setEmail(e.target.value)} placeholder="Email" type="email" style={inputStyle}/>
          <input value={pw} onChange={e=>setPw(e.target.value)} placeholder="Password" type="password"
            onKeyDown={e => e.key === "Enter" && submit()}
            style={{ ...inputStyle, marginBottom: 14 }}/>
          {err && <div style={{ color: "#FF3B30", fontSize: 12, marginBottom: 10 }}>{err}</div>}
          <Btn onClick={submit} variant="primary" style={{ width: "100%", padding: "12px", fontSize: 15, borderRadius: 12 }}>
            {mode === "login" ? "Sign in" : "Create account"}
          </Btn>
        </Card>
      </div>
    </div>
  )
}

// DashboardPage is imported from ./DashboardPage

// ─────────────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// RUN CARDS — expandable cards for past/running runs
// ─────────────────────────────────────────────────────────────────────────────
function RunCards({ runs, activeProject, onResumeRun }) {
  const qclient = useQueryClient()
  const [expanded, setExpanded] = useState({})

  const toggle = (id) => setExpanded(p => ({ ...p, [id]: !p[id] }))

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {runs.slice(0, 10).map(r => {
        const isOpen = expanded[r.run_id]
        const isRunning = r.status === "running" || r.status === "queued"
        const isError = r.status === "error"
        const isComplete = r.status === "complete"
        let result = {}
        try { result = r.result ? JSON.parse(r.result) : {} } catch {}

        const statusColor = isComplete ? T.teal : isError ? T.red : T.amber
        const borderColor = isOpen ? statusColor : T.border

        return (
          <div key={r.run_id} style={{ border: `1px solid ${borderColor}`, borderRadius: 8, overflow: "hidden", transition: "border-color 0.15s" }}>
            {/* Header row */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", cursor: "pointer", background: isOpen ? "#fafafa" : "#fff" }}
                 onClick={() => toggle(r.run_id)}>
              <StatusDot status={isComplete ? "healthy" : isError ? "error" : "degraded"}/>
              <span style={{ flex: 1, fontWeight: 600, fontSize: 13 }}>{r.seed}</span>
              {isRunning && (
                <button onClick={e => { e.stopPropagation(); onResumeRun(r) }}
                  style={{ padding: "3px 10px", background: T.amber, color: "#fff", border: "none", borderRadius: 5, fontSize: 11, fontWeight: 700, cursor: "pointer" }}>
                  Resume view
                </button>
              )}
              <Badge color={statusColor}>{r.status}</Badge>
              <span style={{ color: T.gray, fontSize: 11 }}>{r.started_at?.slice(0,16)}</span>
              <button onClick={e => { e.stopPropagation()
                if (!window.confirm(`Delete run "${r.seed}"?`)) return
                api.delete(`/api/runs/${r.run_id}`).then(() => qclient.invalidateQueries(["runs", activeProject]))
              }} style={{ background:"none",border:"none",cursor:"pointer",color:T.red,fontSize:13 }}>✕</button>
              <span style={{ color: T.gray, fontSize: 11 }}>{isOpen ? "▲" : "▼"}</span>
            </div>

            {/* Expanded detail */}
            {isOpen && (
              <div style={{ padding: "12px 14px", borderTop: `1px solid ${T.border}`, background: "#fafafa" }}>
                {isError && r.error && (
                  <div style={{ background: "#fff0f0", border: "1px solid #fecaca", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: T.red, fontFamily: "monospace", marginBottom: 10, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                    {r.error}
                  </div>
                )}
                {isComplete && (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 10 }}>
                    {[
                      { label: "Keywords", value: result.keyword_count || 0, color: T.purple },
                      { label: "Pillars",  value: result.pillar_count  || 0, color: T.teal },
                      { label: "Clusters", value: result.cluster_count || 0, color: T.amber },
                      { label: "Articles", value: result.calendar_count|| 0, color: T.green },
                    ].map(s => (
                      <div key={s.label} style={{ background: "#fff", border: `1px solid ${T.border}`, borderRadius: 6, padding: "8px 10px", textAlign: "center" }}>
                        <div style={{ fontSize: 18, fontWeight: 700, color: s.color }}>{s.value}</div>
                        <div style={{ fontSize: 10, color: T.textSoft }}>{s.label}</div>
                      </div>
                    ))}
                  </div>
                )}
                {isComplete && result.calendar_preview?.length > 0 && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Scheduled articles (first 5)</div>
                    {result.calendar_preview.map((a, i) => (
                      <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", padding: "5px 0", borderBottom: `1px solid ${T.border}`, fontSize: 12 }}>
                        <span style={{ width: 18, height: 18, background: T.purpleLight, color: T.purple, borderRadius: "50%",
                          display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, flexShrink: 0 }}>{i+1}</span>
                        <span style={{ flex: 1, fontWeight: 500 }}>{a.keyword || a.title || a.article_id}</span>
                        {a.intent && <Badge color={T.purple}>{a.intent}</Badge>}
                        {a.scheduled_date && <span style={{ color: T.gray, fontSize: 10 }}>{a.scheduled_date?.slice(0,10)}</span>}
                      </div>
                    ))}
                  </div>
                )}
                {isRunning && (
                  <div style={{ fontSize: 12, color: T.amber }}>Run in progress — click "Resume view" to watch the SSE console.</div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

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

  const startSSE = (rid) => {
    if (esRef.current) esRef.current.close()
    const es = new EventSource(`${API}/api/runs/${rid}/stream`)
    esRef.current = es
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data)
      ev.ts = new Date().toLocaleTimeString()
      setEvents(prev => [...prev, ev])
      if (ev.type === "gate") {
        setGateData(ev.data); setGateName(ev.gate); setRunStatus("waiting_gate")
        if (ev.gate === "universe_keywords") setEditedKeywords((ev.data?.keywords || []).join("\n"))
        if (ev.gate === "pillars") setEditedClusters((ev.data?.clusters || []).map(c => ({ name: c, checked: true })))
      }
      if (ev.type === "complete") { setRunStatus("complete"); es.close(); refetchRuns() }
      if (ev.type === "error") { setRunStatus("error"); es.close(); refetchRuns() }
    }
    es.onerror = () => { setRunStatus("error"); es.close() }
  }

  const startRun = async () => {
    if (!seed.trim() || !activeProject) return
    setEvents([]); setRunStatus("running"); setGateData(null); setGateName(null)
    const data = await api.post(`/api/projects/${activeProject}/runs`, { seed: seed.trim(), language: "english", region: "india" })
    if (!data?.run_id) { setRunStatus("error"); return }
    setRunId(data.run_id)
    startSSE(data.run_id)
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

      {/* Past runs — expandable cards */}
      {runs?.length > 0 && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10 }}>Recent runs</div>
          <RunCards runs={runs} activeProject={activeProject} onResumeRun={(r) => {
            setSeed(r.seed)
            setRunId(r.run_id)
            setRunStatus(r.status)
            setEvents([{ type: "phase_log", payload: { msg: `Resumed view of run: ${r.seed}` } }])
            startSSE(r.run_id)
          }} />
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
// UNIFIED KEYWORD PAGE — tabs: Workflow | Keyword Tree | Rankings
// ─────────────────────────────────────────────────────────────────────────────
function KeywordsUnifiedPage() {
  const { activeProject, setPage } = useStore()
  const [tab, setTab] = useState("workflow")
  const [strategySummary, setStrategySummary] = useState(null)

  useEffect(() => {
    let active = true
    if (!activeProject) return
    api.get(`/api/strategy/${activeProject}/latest`).then(r => {
      if (!active) return
      setStrategySummary(r)
    }).catch(() => {})
    return () => { active = false }
  }, [activeProject])

  const TABS = [
    { id: "workflow", label: "Workflow",     desc: "7-step keyword wizard" },
    { id: "tree",     label: "Keyword Tree", desc: "Explore universe visually" },
    { id: "rankings", label: "Rankings",     desc: "GSC keyword positions" },
  ]

  return (
    <div>
      <div style={{ fontSize: 18, fontWeight: 700, color: T.text, marginBottom: 16 }}>Keywords</div>

      {strategySummary && strategySummary.result_json && (
        <div style={{ marginBottom: 14 }}>
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>Strategy: {strategySummary.result_json.strategy?.strategy_summary?.headline || '—'}</div>
                <div style={{ fontSize: 12, color: T.gray }}>{(strategySummary.result_json.strategy?.priority_personas || []).slice(0,3).map(p => p.persona || p).join(', ')}</div>
              </div>
              <div>
                <Btn small onClick={() => setPage('strategy')}>Edit Strategy</Btn>
              </div>
            </div>
          </Card>
        </div>
      )}
      {/* Tab bar */}
      <div style={{ display: "flex", gap: 0, borderBottom: `2px solid ${T.border}`, marginBottom: 24 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: "10px 20px", border: "none", background: "none", cursor: "pointer",
            fontSize: 13, fontWeight: tab === t.id ? 700 : 500,
            color: tab === t.id ? T.purple : T.gray,
            borderBottom: `3px solid ${tab === t.id ? T.purple : "transparent"}`,
            marginBottom: -2, transition: "color 0.12s",
          }}>
            {t.label}
            {tab !== t.id && <div style={{ fontSize: 10, color: T.gray, fontWeight: 400, marginTop: 1 }}>{t.desc}</div>}
          </button>
        ))}
      </div>

      {tab === "workflow" && <KeywordWorkflow projectId={activeProject} onGoToCalendar={() => setPage("blogs")} setPage={setPage}/>}
      {tab === "tree"     && <KeywordTreePage/>}
      {tab === "rankings" && <RankingsPage/>}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTENT PIPELINE TAB — P13, P15, P16, P17, P19, P20
// ─────────────────────────────────────────────────────────────────────────────

const CONTENT_PHASES = [
  { key: "P13", name: "Content Calendar",  group: "planning", color: "#2563eb" },
  { key: "P15", name: "Blog Suggestions",  group: "content",  color: "#7c3aed" },
  { key: "P16", name: "Content Generation",group: "content",  color: "#7c3aed" },
  { key: "P17", name: "SEO Optimisation",  group: "content",  color: "#7c3aed" },
  { key: "P19", name: "Publishing",        group: "publish",  color: "#dc2626" },
  { key: "P20", name: "Feedback Loop",     group: "publish",  color: "#dc2626" },
]

const CONTENT_PHASE_ETA = {
  P13: 2000, P15: 3000, P16: 8000, P17: 3000, P19: 2000, P20: 1000,
}

export function ContentPipelineTab({ projectId }) {
  const [pillarStatus, setPillarStatus]   = useState([])
  const [selectedPillars, setSelectedPillars] = useState([])
  const [runs, setRuns]                   = useState([])
  const [phaseProgress, setPhaseProgress] = useState({}) // runId → [events]
  const [running, setRunning]             = useState(false)
  const [error, setError]                 = useState("")
  const [expandedRun, setExpandedRun]     = useState(null)
  const [tick, setTick]                   = useState(0)
  const sseRef                            = useRef({})
  const phaseStartRef                     = useRef({}) // runId+phase → start timestamp

  // Live tick for elapsed timers
  useEffect(() => {
    const t = setInterval(() => setTick(v => v + 1), 1000)
    return () => clearInterval(t)
  }, [])

  // Cleanup SSE on unmount
  useEffect(() => () => Object.values(sseRef.current).forEach(es => es?.close()), [])

  // Load pillar status
  const { data: psData, isLoading: psLoading } = useQuery({
    queryKey: ["pillar-status-content", projectId],
    queryFn: () => projectId ? api.get(`/api/ki/${projectId}/pillar-status`) : null,
    enabled: !!projectId,
    refetchInterval: running ? 5000 : false,
  })

  useEffect(() => {
    if (psData?.pillars) setPillarStatus(psData.pillars)
  }, [psData])

  const startSSE = (runId) => {
    if (sseRef.current[runId]) return
    const es = new EventSource(`${API}/api/runs/${runId}/stream`)
    es.addEventListener("message", (e) => {
      try {
        const payload = JSON.parse(e.data)
        if (payload.type === "phase_log") {
          if (payload.status === "starting") {
            const key = `${runId}:${payload.phase}`
            if (!phaseStartRef.current[key]) phaseStartRef.current[key] = Date.now()
          }
          setPhaseProgress(prev => ({
            ...prev,
            [runId]: [...(prev[runId] || []), payload]
          }))
          if (payload.status === "complete" && payload.phase === "P20") {
            es.close()
            setRunning(false)
          }
        }
        if (payload.type === "run_complete" || payload.type === "error") {
          es.close()
          setRunning(false)
        }
      } catch {}
    })
    es.addEventListener("error", () => { es.close() })
    sseRef.current[runId] = es
  }

  const runContentPipeline = async () => {
    if (!selectedPillars.length) { setError("Select at least one pillar"); return }
    setError(""); setRunning(true)
    try {
      const r = await api.post(`/api/ki/${projectId}/run-pipeline`, { selected_pillars: selectedPillars })
      if (r?.runs) {
        setRuns(r.runs.map(run => ({ ...run, status: "queued" })))
        const exp = {}
        r.runs.forEach(run => { exp[run.run_id] = true; startSSE(run.run_id) })
        setExpandedRun(r.runs[0]?.run_id || null)
      } else {
        setError(typeof r?.detail === 'string' ? r.detail : Array.isArray(r?.detail) ? r.detail.map(e=>e.msg||String(e)).join('; ') : "Failed to start pipeline")
        setRunning(false)
      }
    } catch (e) { setError(String(e)); setRunning(false) }
  }

  const togglePillar = (kw) => setSelectedPillars(prev =>
    prev.includes(kw) ? prev.filter(k => k !== kw) : [...prev, kw]
  )
  const selectAll = () => setSelectedPillars(pillarStatus.map(p => p.keyword))
  const clearAll  = () => setSelectedPillars([])

  // Phase summary per run
  const phaseSummary = (runId) => {
    const events = phaseProgress[runId] || []
    const map = {}
    events.forEach(ev => {
      if (!map[ev.phase]) map[ev.phase] = {}
      map[ev.phase][ev.status] = ev
    })
    return map
  }

  const phaseIcon = (summary) => {
    if (summary?.complete) return { icon: "✓", color: "#16a34a" }
    if (summary?.error)    return { icon: "✕", color: "#dc2626" }
    if (summary?.starting) return { icon: "●", color: "#7c3aed" }
    return { icon: "○", color: "#d1d5db" }
  }

  if (!projectId) return <div style={{ color: T.gray, padding: 20 }}>Select a project first.</div>

  const allDone = runs.length > 0 && !running

  return (
    <div>
      {/* Phase strip */}
      <Card style={{ marginBottom: 12, padding: "14px 16px" }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: T.gray, textTransform: "uppercase",
                      letterSpacing: ".06em", marginBottom: 10 }}>Content Pipeline Phases</div>
        <div style={{ display: "flex", gap: 0, alignItems: "center", overflowX: "auto" }}>
          {CONTENT_PHASES.map((ph, i) => (
            <div key={ph.key} style={{ display: "flex", alignItems: "center" }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
                            padding: "6px 12px", borderRadius: 8, background: ph.color + "12",
                            border: `1px solid ${ph.color}33`, minWidth: 90 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: ph.color }}>{ph.key}</span>
                <span style={{ fontSize: 10, color: "#374151", textAlign: "center", marginTop: 2 }}>{ph.name}</span>
              </div>
              {i < CONTENT_PHASES.length - 1 && (
                <div style={{ width: 20, height: 1, background: "#e5e7eb", flexShrink: 0 }}/>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* Pillar selection */}
      {!running && runs.length === 0 && (
        <Card style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Select Pillars to Run</div>
            <div style={{ display: "flex", gap: 6 }}>
              <Btn small onClick={selectAll}>Select All</Btn>
              <Btn small onClick={clearAll}>Clear</Btn>
            </div>
          </div>

          {psLoading ? (
            <div style={{ color: T.gray, fontSize: 12 }}>Loading pillars…</div>
          ) : pillarStatus.length === 0 ? (
            <div style={{ color: T.gray, fontSize: 12, padding: "10px 0" }}>
              No confirmed pillars found. Complete Steps 1–5 in the Keyword Workflow first.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {pillarStatus.map(p => (
                <label key={p.keyword} style={{ display: "flex", alignItems: "center", gap: 10,
                                                padding: "8px 10px", borderRadius: 8, cursor: "pointer",
                                                background: selectedPillars.includes(p.keyword) ? "#f5f3ff" : T.grayLight,
                                                border: `1px solid ${selectedPillars.includes(p.keyword) ? "#7c3aed33" : "transparent"}` }}>
                  <input type="checkbox" checked={selectedPillars.includes(p.keyword)}
                    onChange={() => togglePillar(p.keyword)} style={{ accentColor: "#7c3aed" }}/>
                  <span style={{ fontSize: 13, fontWeight: 500, flex: 1 }}>{p.keyword}</span>
                  {p.status && (
                    <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 99,
                                   background: p.status === "complete" ? "#f0fdf4" : "#fffbeb",
                                   color: p.status === "complete" ? "#16a34a" : "#d97706", fontWeight: 600 }}>
                      {p.status === "complete" ? "✓ Step 5 done" : p.status}
                    </span>
                  )}
                  {p.cluster_count > 0 && (
                    <span style={{ fontSize: 10, color: T.gray }}>{p.cluster_count} clusters</span>
                  )}
                </label>
              ))}
            </div>
          )}

          {error && (
            <div style={{ color: "#dc2626", fontSize: 12, marginTop: 10, padding: "8px 12px",
                          background: "#fef2f2", borderRadius: 8 }}>⚠ {error}</div>
          )}

          <div style={{ marginTop: 12 }}>
            <Btn variant="primary" onClick={runContentPipeline}
                 disabled={!selectedPillars.length || psLoading}
                 style={{ background: "#7c3aed" }}>
              ▶ Run Content Generation ({selectedPillars.length} pillar{selectedPillars.length !== 1 ? "s" : ""})
            </Btn>
          </div>
        </Card>
      )}

      {/* Run progress cards */}
      {runs.map(run => {
        const summary = phaseSummary(run.run_id)
        const isExpanded = expandedRun === run.run_id
        const completedCount = CONTENT_PHASES.filter(ph => summary[ph.key]?.complete).length
        const currentPhase = CONTENT_PHASES.find(ph => summary[ph.key]?.starting && !summary[ph.key]?.complete)

        return (
          <Card key={run.run_id} style={{ marginBottom: 10 }}>
            {/* Card header */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: isExpanded ? 12 : 0,
                          cursor: "pointer" }}
                 onClick={() => setExpandedRun(isExpanded ? null : run.run_id)}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{run.seed || run.run_id}</div>
                <div style={{ fontSize: 11, color: T.gray, marginTop: 1 }}>
                  {currentPhase
                    ? `Running: ${currentPhase.name}…`
                    : completedCount === CONTENT_PHASES.length
                    ? "All content phases complete"
                    : `${completedCount}/${CONTENT_PHASES.length} phases`}
                </div>
              </div>
              {/* Mini phase dots */}
              <div style={{ display: "flex", gap: 4 }}>
                {CONTENT_PHASES.map(ph => {
                  const { icon, color } = phaseIcon(summary[ph.key])
                  return (
                    <span key={ph.key} title={ph.name}
                          style={{ fontSize: 10, color, fontWeight: 700 }}>{icon}</span>
                  )
                })}
              </div>
              <span style={{ fontSize: 10, color: T.gray }}>{isExpanded ? "▲" : "▼"}</span>
            </div>

            {/* Expanded phase list */}
            {isExpanded && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {CONTENT_PHASES.map(ph => {
                  const s = summary[ph.key]
                  const isRunningNow = s?.starting && !s?.complete && !s?.error
                  const startKey = `${run.run_id}:${ph.key}`
                  const startTs = phaseStartRef.current[startKey]
                  const liveElapsed = startTs && isRunningNow
                    ? Math.floor((Date.now() - startTs) / 1000)
                    : (s?.complete?.elapsed_ms ? Math.round(s.complete.elapsed_ms / 1000) : 0)
                  const etaMs = CONTENT_PHASE_ETA[ph.key] || 3000
                  const fillPct = isRunningNow
                    ? Math.min(liveElapsed * 1000 / etaMs * 100, 95)
                    : s?.complete ? 100 : 0

                  return (
                    <div key={ph.key} style={{ borderRadius: 8, border: "1px solid #e5e7eb",
                                               overflow: "hidden" }}>
                      {/* Phase header row */}
                      <div style={{ display: "flex", alignItems: "center", gap: 8,
                                    padding: "8px 12px", background: isRunningNow ? ph.color + "08" : "transparent" }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: ph.color, width: 28 }}>{ph.key}</span>
                        <span style={{ fontSize: 12, fontWeight: 500, flex: 1 }}>{ph.name}</span>
                        {isRunningNow && (
                          <span style={{ fontSize: 10, color: ph.color, animation: "pulse 1.5s infinite" }}>● running</span>
                        )}
                        {s?.complete && (
                          <span style={{ fontSize: 10, color: "#16a34a" }}>✓ done</span>
                        )}
                        {s?.error && (
                          <span style={{ fontSize: 10, color: "#dc2626" }}>✕ error</span>
                        )}
                        {!s && (
                          <span style={{ fontSize: 10, color: "#9ca3af" }}>pending</span>
                        )}
                        {liveElapsed > 0 && (
                          <span style={{ fontSize: 10, color: T.gray }}>{liveElapsed}s</span>
                        )}
                        {s?.complete?.output_count > 0 && (
                          <span style={{ fontSize: 10, color: "#7c3aed", fontWeight: 600 }}>
                            {s.complete.output_count} items
                          </span>
                        )}
                      </div>
                      {/* Progress bar */}
                      {(isRunningNow || s?.complete) && (
                        <div style={{ height: 3, background: "#f3f4f6" }}>
                          <div style={{ height: "100%", width: `${fillPct}%`,
                                        background: s?.complete ? "#16a34a" : ph.color,
                                        transition: isRunningNow ? "none" : "width 0.3s" }}/>
                        </div>
                      )}
                      {/* Message */}
                      {(s?.complete?.msg || s?.starting?.msg) && (
                        <div style={{ padding: "4px 12px 6px", fontSize: 10, color: T.gray }}>
                          {s?.complete?.msg || s?.starting?.msg}
                        </div>
                      )}
                    </div>
                  )
                })}

                {/* "Run more" button after done */}
                {completedCount === CONTENT_PHASES.length && (
                  <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
                    <Btn small onClick={() => { setRuns([]); setPhaseProgress({}); setSelectedPillars([]) }}>
                      ← Run Another Pillar
                    </Btn>
                  </div>
                )}
              </div>
            )}
          </Card>
        )
      })}

      {/* Running spinner */}
      {running && (
        <div style={{ textAlign: "center", padding: 16, color: "#7c3aed", fontSize: 12 }}>
          <span style={{ marginRight: 8 }}>⏳</span>
          Content pipeline running — P13 → P15 → P16 → P17 → P19 → P20
        </div>
      )}

      {allDone && (
        <div style={{ padding: "12px 16px", background: "#f0fdf4", borderRadius: 8,
                      border: "1px solid #bbf7d0", fontSize: 12, color: "#15803d" }}>
          ✓ Content pipeline complete. Check the Articles tab for generated content.
        </div>
      )}
    </div>
  )
}

// ContentPage is imported from ./ContentPage

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
  const qclient = useQueryClient()
  const [tab, setTab] = useState("overview")
  const [severityFilter, setSeverityFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [diagnosing, setDiagnosing] = useState({})
  const [diagnoses, setDiagnoses] = useState({})

  const { data: rankings } = useQuery({
    queryKey: ["rankings", activeProject],
    queryFn: () => activeProject ? api.get(`/api/rankings/${activeProject}`) : [],
    enabled: !!activeProject,
  })
  const { data: dashboard } = useQuery({
    queryKey: ["rankings-dashboard", activeProject],
    queryFn: () => activeProject ? api.get(`/api/rankings/${activeProject}/dashboard`) : null,
    enabled: !!activeProject, refetchInterval: 300000,
  })
  const { data: alerts } = useQuery({
    queryKey: ["ranking-alerts", activeProject, severityFilter, statusFilter],
    queryFn: () => {
      let path = `/api/rankings/${activeProject}/alerts?`
      if (severityFilter !== "all") path += `severity=${severityFilter}&`
      if (statusFilter !== "all") path += `status=${statusFilter}`
      return api.get(path)
    },
    enabled: !!activeProject && tab === "alerts", refetchInterval: 60000,
  })
  const { data: predictions } = useQuery({
    queryKey: ["ranking-predictions", activeProject],
    queryFn: () => api.get(`/api/rankings/${activeProject}/predictions`),
    enabled: !!activeProject && tab === "predictions",
  })
  const { data: topMovers } = useQuery({
    queryKey: ["top-movers", activeProject],
    queryFn: () => api.get(`/api/rankings/${activeProject}/top-movers`),
    enabled: !!activeProject && tab === "overview",
  })
  const { data: gscStatus } = useQuery({
    queryKey: ["gsc-status", activeProject],
    queryFn: () => activeProject ? api.get(`/api/gsc/${activeProject}/status`) : null,
    enabled: !!activeProject,
  })

  const syncGSC = async () => {
    await api.post(`/api/gsc/${activeProject}/sync`, {})
    qclient.invalidateQueries(["rankings", activeProject])
    qclient.invalidateQueries(["rankings-dashboard", activeProject])
  }
  const checkAlerts = async () => {
    await api.post(`/api/rankings/${activeProject}/check-alerts`, {})
    qclient.invalidateQueries(["ranking-alerts", activeProject])
    qclient.invalidateQueries(["rankings-dashboard", activeProject])
  }
  const acknowledge = async (alertId) => {
    await api.post(`/api/rankings/${activeProject}/alerts/${alertId}/acknowledge`, {})
    qclient.invalidateQueries(["ranking-alerts", activeProject])
    qclient.invalidateQueries(["rankings-dashboard", activeProject])
  }
  const diagnose = async (alert) => {
    setDiagnosing(d => ({...d, [alert.id]: true}))
    const r = await api.post(`/api/rankings/${activeProject}/alerts/${alert.id}/diagnose`, {})
    setDiagnosing(d => ({...d, [alert.id]: false}))
    setDiagnoses(d => ({...d, [alert.id]: r}))
    qclient.invalidateQueries(["ranking-alerts", activeProject])
  }

  const currentRankings = dashboard?.current_rankings || rankings || []
  const activeAlerts = dashboard?.active_alerts || []
  const activeAlertCount = dashboard?.alert_count || 0

  const posColor = (p) => p <= 3 ? T.teal : p <= 10 ? T.purple : p <= 20 ? T.amber : T.red
  const SevColor = { critical: "red", high: "amber", warning: "purple" }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 20, fontWeight: 600 }}>
          Rankings Intelligence
          {activeAlertCount > 0 && (
            <Badge color="red" style={{ marginLeft: 8 }}>{activeAlertCount} alerts</Badge>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {gscStatus?.connected ? (
            <>
              <Badge color="teal">GSC connected</Badge>
              <Btn small onClick={syncGSC}>Sync GSC</Btn>
            </>
          ) : (
            <Btn small variant="primary" onClick={async () => {
              const data = await api.get(`/api/gsc/${activeProject}/auth-url`)
              if (data?.auth_url) window.open(data.auth_url, "_blank")
            }}>Connect GSC</Btn>
          )}
          <Btn small onClick={checkAlerts}>Check Alerts</Btn>
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 14 }}>
        {[
          { label: "Top 3",      count: currentRankings.filter(r=>r.position<=3).length,  color: T.teal },
          { label: "Top 10",     count: currentRankings.filter(r=>r.position<=10).length, color: T.purple },
          { label: "Top 20",     count: currentRankings.filter(r=>r.position<=20).length, color: T.amber },
          { label: "Alerts",     count: activeAlertCount,                                  color: T.red },
        ].map(s => (
          <Card key={s.label} style={{ textAlign: "center", padding: 10 }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.count}</div>
            <div style={{ fontSize: 11, color: T.gray }}>{s.label}</div>
          </Card>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, borderBottom: "0.5px solid rgba(0,0,0,0.1)", marginBottom: 14 }}>
        {[["overview","Overview"],["alerts",`Alerts${activeAlertCount>0?" ("+activeAlertCount+")":""}`],["predictions","Predictions"]].map(([id,label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            padding: "7px 16px", border: "none", cursor: "pointer", fontSize: 12, fontWeight: 500,
            background: "transparent", color: tab === id ? T.purple : T.gray,
            borderBottom: tab === id ? `2px solid ${T.purple}` : "2px solid transparent", marginBottom: -1,
          }}>{label}</button>
        ))}
      </div>

      {/* Overview */}
      {tab === "overview" && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 14 }}>
            {/* Keyword list */}
            <Card>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10 }}>Current Positions ({currentRankings.length})</div>
              {currentRankings.length === 0 ? (
                <div style={{ fontSize: 12, color: T.gray, padding: "8px 0" }}>
                  No ranking data. Connect GSC or import manually.
                </div>
              ) : currentRankings.slice(0, 40).map((r, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8,
                  padding: "5px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 12 }}>
                  <div style={{ width: 26, height: 26, borderRadius: "50%", display: "flex", alignItems: "center",
                    justifyContent: "center", fontSize: 11, fontWeight: 600, flexShrink: 0,
                    background: r.position <= 3 ? "#E1F5EE" : r.position <= 10 ? "#EEEDFE" : "#F1EFE8",
                    color: posColor(r.position),
                  }}>{Math.round(r.position)}</div>
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.keyword}</span>
                  <div style={{ width: 60, height: 3, background: "rgba(0,0,0,0.06)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ width: `${Math.max(0, 100-r.position*3)}%`, height: "100%", background: posColor(r.position) }}/>
                  </div>
                  <span style={{ fontSize: 10, color: T.gray, minWidth: 46, textAlign: "right" }}>{r.clicks} clicks</span>
                  <span style={{ fontSize: 10, color: T.gray, minWidth: 40, textAlign: "right" }}>{(r.ctr*100).toFixed(1)}%</span>
                </div>
              ))}
            </Card>

            {/* Top movers */}
            <div>
              {activeAlertCount > 0 && (
                <Card style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Active Alerts</div>
                  {activeAlerts.slice(0, 5).map(a => (
                    <div key={a.id} style={{ padding: "5px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 11 }}>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ fontWeight: 500 }}>{a.keyword}</span>
                        <Badge color={SevColor[a.severity] || "gray"}>{a.severity}</Badge>
                      </div>
                      <div style={{ color: T.red, marginTop: 2 }}>
                        #{Math.round(a.old_position)} → #{Math.round(a.new_position)}
                        <span style={{ marginLeft: 4 }}>(▼{Math.round(a.change)})</span>
                      </div>
                    </div>
                  ))}
                  <Btn small style={{ marginTop: 8 }} onClick={() => setTab("alerts")}>View all alerts</Btn>
                </Card>
              )}
              <Card>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Top Movers (7d)</div>
                {!topMovers?.length ? (
                  <div style={{ fontSize: 11, color: T.gray }}>No movement data yet.</div>
                ) : topMovers.slice(0, 10).map((m, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0",
                    borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 11 }}>
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.keyword}</span>
                    <span style={{ color: T.amber, flexShrink: 0 }}>±{Math.round(m.swing)}</span>
                  </div>
                ))}
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* Alerts */}
      {tab === "alerts" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <select value={severityFilter} onChange={e => setSeverityFilter(e.target.value)}
              style={{ padding: "5px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 12 }}>
              <option value="all">All severity</option>
              {["critical","high","warning"].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              style={{ padding: "5px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 12 }}>
              <option value="all">All status</option>
              {["new","acknowledged","diagnosed"].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          {!alerts?.length ? (
            <Card style={{ textAlign: "center", padding: 30 }}>
              <div style={{ fontSize: 12, color: T.gray }}>No alerts. Rankings are stable.</div>
            </Card>
          ) : alerts.map(a => (
            <Card key={a.id} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <div>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{a.keyword}</span>
                  <span style={{ fontSize: 11, color: T.red, marginLeft: 8 }}>
                    #{Math.round(a.old_position)} → #{Math.round(a.new_position)} (▼{Math.round(a.change)})
                  </span>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <Badge color={SevColor[a.severity] || "gray"}>{a.severity}</Badge>
                  <Badge color={a.status === "new" ? "red" : a.status === "diagnosed" ? "teal" : "gray"}>{a.status}</Badge>
                </div>
              </div>
              <div style={{ fontSize: 10, color: T.gray, marginBottom: 8 }}>{a.created_at?.slice(0,10)}</div>

              {/* Diagnosis result */}
              {(diagnoses[a.id] || a.diagnosis_json?.root_cause) && (() => {
                const diag = diagnoses[a.id] || a.diagnosis_json
                return (
                  <div style={{ background: "#fafafa", borderRadius: 8, padding: "10px 12px", marginBottom: 8, fontSize: 11 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Root cause: {diag.root_cause}</div>
                    {diag.fixes?.slice(0, 3).map((f, i) => (
                      <div key={i} style={{ display: "flex", gap: 8, padding: "4px 0",
                        borderTop: i > 0 ? "0.5px solid rgba(0,0,0,0.06)" : "none" }}>
                        <Badge color={f.priority === "do_now" ? "red" : f.priority === "do_this_week" ? "amber" : "gray"}>
                          {f.priority}
                        </Badge>
                        <div>
                          <div style={{ fontWeight: 500 }}>{f.action}</div>
                          <div style={{ color: T.gray }}>{f.specific_instruction}</div>
                        </div>
                      </div>
                    ))}
                    {diag.estimated_recovery_weeks > 0 && (
                      <div style={{ marginTop: 6, color: T.gray }}>Estimated recovery: {diag.estimated_recovery_weeks} weeks</div>
                    )}
                  </div>
                )
              })()}

              <div style={{ display: "flex", gap: 6 }}>
                {a.status === "new" && (
                  <Btn small onClick={() => acknowledge(a.id)}>Acknowledge</Btn>
                )}
                <Btn small variant="primary" onClick={() => diagnose(a)} loading={diagnosing[a.id]}>
                  Diagnose with Claude
                </Btn>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Predictions */}
      {tab === "predictions" && (
        <div>
          {!predictions?.length ? (
            <Card style={{ textAlign: "center", padding: 30 }}>
              <div style={{ fontSize: 12, color: T.gray }}>
                No predictions yet. Run a Final Claude Strategy to generate 12-month predictions.
              </div>
            </Card>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px,1fr))", gap: 10 }}>
              {predictions.map((p, i) => (
                <Card key={i}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: T.gray, marginBottom: 4 }}>{p.predicted_month}</div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{p.keyword}</div>
                  <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>
                    Pillar: {p.pillar || "—"}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, alignItems: "center" }}>
                    <div style={{ fontSize: 20, fontWeight: 700, color: posColor(p.predicted_rank) }}>
                      #{Math.round(p.predicted_rank)}
                    </div>
                    <Badge color={p.confidence > 0.7 ? "teal" : p.confidence > 0.4 ? "amber" : "gray"}>
                      {p.confidence > 0 ? `${(p.confidence*100).toFixed(0)}% conf` : "low conf"}
                    </Badge>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
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
    language: "english", region: "india", religion: "general",
    business_type: "B2C", usp: "",
    target_locations: [], target_languages: [],
    wp_url: "", wp_user: "", wp_password: "",
  })

  const toggleArr = (field, val) => {
    const arr = form[field] || []
    setForm({ ...form, [field]: arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val] })
  }
  const industries = ["food_spices","tourism","healthcare","ecommerce","agriculture","education","real_estate","tech_saas","wellness","restaurant","fashion","general"]

  const create = useMutation({
    mutationFn: () => api.post("/api/projects", { ...form }),
    onSuccess: (data) => {
      qclient.invalidateQueries(["projects"])
      setProject(data.project_id)
      setPage("keywords")
    }
  })

  const steps = [
    { label: "Business", icon: "①" },
    { label: "Context", icon: "②" },
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
          <div style={{ marginTop: 10, padding: "8px 12px", background: T.purpleLight,
                        borderRadius: 8, fontSize: 11, color: T.purple }}>
            Pillar keywords, supporting keywords, and competitor URLs are collected in the Keywords workflow after project creation.
          </div>
          <Btn onClick={() => setStep(1)} variant="primary" style={{ marginTop: 16, width: "100%" }} disabled={!form.name}>Continue →</Btn>
        </Card>
      )}

      {step === 1 && (
        <Card style={{ padding: 20 }}>
          <div style={{ fontSize: 12, color: T.gray, marginBottom: 12 }}>Audience context — drives keyword expansion, content variants, and strategy targeting.</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 12 }}>
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
          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 10, marginBottom: 12 }}>
            <div>
              <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Business type</label>
              <select value={form.business_type} onChange={e=>setForm({...form,business_type:e.target.value})}
                style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,boxSizing:"border-box" }}>
                {["B2C","B2B","D2C","Service","Marketplace"].map(b=><option key={b}>{b}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 4 }}>Unique selling proposition</label>
              <input value={form.usp} onChange={e=>setForm({...form,usp:e.target.value})} maxLength={200}
                placeholder="What makes you unique?"
                style={{ width:"100%",padding:"8px 10px",borderRadius:8,border:"0.5px solid rgba(0,0,0,0.15)",fontSize:13,boxSizing:"border-box" }}/>
            </div>
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 6 }}>Target locations</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
              {["global","india","south_india","kerala","malabar","kochi","kozhikode","wayanad","national"].map(o => {
                const active = (form.target_locations || []).includes(o)
                return <button key={o} onClick={() => toggleArr("target_locations", o)} style={{
                  padding:"3px 9px",borderRadius:99,fontSize:11,cursor:"pointer",border:"none",
                  background: active ? T.purple : "rgba(0,0,0,0.07)", color: active ? "#fff" : T.gray,
                }}>{o}</button>
              })}
            </div>
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 12, color: T.gray, display: "block", marginBottom: 6 }}>Target languages (multi)</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
              {["english","malayalam","hindi","tamil","kannada","telugu","arabic"].map(o => {
                const active = (form.target_languages || []).includes(o)
                return <button key={o} onClick={() => toggleArr("target_languages", o)} style={{
                  padding:"3px 9px",borderRadius:99,fontSize:11,cursor:"pointer",border:"none",
                  background: active ? T.teal : "rgba(0,0,0,0.07)", color: active ? "#fff" : T.gray,
                }}>{o}</button>
              })}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={() => setStep(0)}>← Back</Btn>
            <Btn onClick={() => setStep(2)} variant="primary" style={{ flex: 1 }}>Continue →</Btn>
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

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: BLOG CONTENT CALENDAR (content_blogs freeze system)
// ─────────────────────────────────────────────────────────────────────────────
function BlogCalendarPage() {
  const { activeProject } = useStore()
  const qclient = useQueryClient()
  const [tab, setTab] = useState("calendar")
  const [selectedYM, setSelectedYM] = useState(null)
  const [selectedPillar, setSelectedPillar] = useState("all")
  const [editBlog, setEditBlog] = useState(null)
  const [editBody, setEditBody] = useState({})
  const [batchPillar, setBatchPillar] = useState("")
  const [batchCount, setBatchCount] = useState(10)
  const [generating, setGenerating] = useState(false)
  const [populating, setPopulating] = useState(false)
  const [msg, setMsg] = useState("")
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
  const year = new Date().getFullYear()

  const { data: stats } = useQuery({
    queryKey: ["blog-stats", activeProject],
    queryFn: () => api.get(`/api/blogs/${activeProject}/stats`),
    enabled: !!activeProject, refetchInterval: 10000,
  })
  const { data: calendar } = useQuery({
    queryKey: ["blog-calendar", activeProject],
    queryFn: () => api.get(`/api/blogs/${activeProject}/calendar`),
    enabled: !!activeProject, refetchInterval: 10000,
  })
  const { data: queue } = useQuery({
    queryKey: ["freeze-queue", activeProject],
    queryFn: () => api.get(`/api/blogs/${activeProject}/freeze-queue?days=14`),
    enabled: !!activeProject && tab === "queue", refetchInterval: 30000,
  })
  const { data: dueToday } = useQuery({
    queryKey: ["due-today", activeProject],
    queryFn: () => api.get(`/api/blogs/${activeProject}/due-today`),
    enabled: !!activeProject,
  })

  const monthData = months.map((m, i) => {
    const ym = `${year}-${String(i+1).padStart(2,"0")}`
    const items = (calendar || {})[ym] || []
    const filtered = selectedPillar === "all" ? items : items.filter(b => b.pillar === selectedPillar)
    const published = filtered.filter(b => b.status === "published").length
    const frozen    = filtered.filter(b => b.status === "frozen").length
    const draft     = filtered.filter(b => b.status === "draft" || b.status === "generating").length
    return { m, ym, items: filtered, published, frozen, draft, total: filtered.length }
  })

  const pillars = Object.keys(stats?.by_pillar || {})

  const openEdit = (b) => { setEditBlog(b); setEditBody({ title: b.title, meta_desc: b.meta_desc }) }

  const saveBlog = async () => {
    if (!editBlog) return
    await api.put(`/api/blogs/${activeProject}/${editBlog.blog_id}`, editBody)
    qclient.invalidateQueries(["blog-calendar", activeProject])
    qclient.invalidateQueries(["blog-stats", activeProject])
    setEditBlog(null)
  }

  const freezeBlog = async (blogId, scheduledDate) => {
    await api.post(`/api/blogs/${activeProject}/${blogId}/freeze`, { scheduled_date: scheduledDate || "" })
    qclient.invalidateQueries(["blog-calendar", activeProject])
    qclient.invalidateQueries(["freeze-queue", activeProject])
    qclient.invalidateQueries(["blog-stats", activeProject])
  }

  const publishBlog = async (blogId) => {
    setMsg("Publishing...")
    const r = await api.post(`/api/blogs/${activeProject}/${blogId}/publish`, {})
    setMsg(r?.published ? `Published! ${r.url || ""}` : "Publish failed")
    qclient.invalidateQueries(["blog-calendar", activeProject])
    qclient.invalidateQueries(["due-today", activeProject])
  }

  const generateBatch = async () => {
    if (!batchPillar) { setMsg("Enter a pillar name first."); return }
    setGenerating(true); setMsg("")
    const r = await api.post(`/api/blogs/${activeProject}/generate-batch`, {
      pillar: batchPillar, count: batchCount, language: "english",
    })
    setGenerating(false)
    setMsg(r?.created ? `${r.created} blogs queued for generation.` : "Error")
    qclient.invalidateQueries(["blog-stats", activeProject])
  }

  const populateFromStrategy = async () => {
    setPopulating(true); setMsg("")
    const r = await api.post(`/api/blogs/${activeProject}/populate-calendar`, { weeks: 12, blogs_per_week: 15 })
    setPopulating(false)
    setMsg(r?.created ? `Created ${r.created} blog stubs from strategy.` : (typeof r?.detail === 'string' ? r.detail : "Error — run strategy first"))
    qclient.invalidateQueries(["blog-calendar", activeProject])
  }

  const StatusColor = { published: "teal", frozen: "purple", draft: "gray", generating: "amber", approved: "green", error: "red" }

  if (!activeProject) return <div style={{ color: T.gray, padding: 20 }}>Select a project first.</div>

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 20, fontWeight: 600 }}>Content Calendar</div>
        <div style={{ display: "flex", gap: 8 }}>
          {msg && <span style={{ fontSize: 11, color: T.teal, alignSelf: "center" }}>{msg}</span>}
          <Btn small variant="primary" onClick={populateFromStrategy} disabled={populating}>
            {populating ? "..." : "Populate from Strategy"}
          </Btn>
        </div>
      </div>

      {/* Stats bar */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 16 }}>
        {[
          { label: "Total Blogs",    value: stats?.total || 0,     color: T.purple },
          { label: "Frozen",         value: stats?.frozen || 0,    color: T.purpleDark },
          { label: "Published",      value: stats?.published || 0, color: T.teal },
          { label: "Due Today",      value: dueToday?.length || 0, color: T.amber },
        ].map(s => (
          <Card key={s.label} style={{ textAlign: "center", padding: 10 }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 11, color: T.gray }}>{s.label}</div>
          </Card>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, borderBottom: "0.5px solid rgba(0,0,0,0.1)", marginBottom: 16 }}>
        {[["calendar","Calendar"],["queue","Upcoming Queue"],["generate","Generate"],["due","Due Today"]].map(([id,label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            padding: "7px 16px", border: "none", cursor: "pointer", fontSize: 12, fontWeight: 500,
            background: "transparent", color: tab === id ? T.purple : T.gray,
            borderBottom: tab === id ? `2px solid ${T.purple}` : "2px solid transparent", marginBottom: -1,
          }}>{label}</button>
        ))}
      </div>

      {/* Tab: Calendar grid */}
      {tab === "calendar" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
            <select value={selectedPillar} onChange={e => setSelectedPillar(e.target.value)}
              style={{ padding: "5px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 12 }}>
              <option value="all">All pillars</option>
              {pillars.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 16 }}>
            {monthData.map(({ m, ym, total, published, frozen, draft }) => (
              <Card key={ym} onClick={() => setSelectedYM(selectedYM === ym ? null : ym)}
                style={{ cursor: "pointer", borderColor: selectedYM === ym ? T.purple : "rgba(0,0,0,0.1)", borderWidth: selectedYM === ym ? 1.5 : 0.5 }}>
                <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 6 }}>{m} {year}</div>
                {total > 0 ? (
                  <>
                    <div style={{ fontSize: 22, fontWeight: 700, color: T.purple }}>{total}</div>
                    <div style={{ height: 4, borderRadius: 99, overflow: "hidden", background: T.grayLight, margin: "6px 0" }}>
                      <div style={{ width: `${total ? (published/total)*100 : 0}%`, height: "100%", background: T.teal }}/>
                    </div>
                    <div style={{ fontSize: 10, color: T.gray }}>
                      <span style={{ color: T.teal }}>{published} pub</span> ·{" "}
                      <span style={{ color: T.purpleDark }}>{frozen} frozen</span> ·{" "}
                      <span>{draft} draft</span>
                    </div>
                  </>
                ) : <div style={{ fontSize: 11, color: T.gray }}>Empty</div>}
              </Card>
            ))}
          </div>

          {selectedYM && (
            <Card>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10 }}>
                {selectedYM} — {(calendar || {})[selectedYM]?.length || 0} articles
                <Btn small onClick={() => setSelectedYM(null)} style={{ marginLeft: 8 }}>Clear</Btn>
              </div>
              {((calendar || {})[selectedYM] || []).map((b, i) => (
                <div key={b.blog_id} style={{ display: "flex", alignItems: "center", gap: 8,
                  padding: "7px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 12 }}>
                  <span style={{ fontSize: 10, color: T.gray, minWidth: 85 }}>{b.scheduled_date}</span>
                  <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {b.title || b.keyword}
                  </span>
                  {b.pillar && <Badge color="purple">{b.pillar}</Badge>}
                  <Badge color={StatusColor[b.status] || "gray"}>{b.status}</Badge>
                  <Btn small onClick={() => openEdit(b)}>Edit</Btn>
                  {b.status !== "frozen" && b.status !== "published" &&
                    <Btn small variant="primary" onClick={() => freezeBlog(b.blog_id, "")}>Freeze</Btn>}
                  {b.status === "frozen" &&
                    <Btn small variant="success" onClick={() => publishBlog(b.blog_id)}>Publish</Btn>}
                </div>
              ))}
            </Card>
          )}
        </div>
      )}

      {/* Tab: Upcoming queue */}
      {tab === "queue" && (
        <Card>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10 }}>Next 14 Days — Frozen & Scheduled</div>
          {!queue?.length ? (
            <div style={{ fontSize: 12, color: T.gray }}>Nothing scheduled yet. Freeze blogs to add them here.</div>
          ) : queue.map((b, i) => (
            <div key={b.blog_id} style={{ display: "flex", alignItems: "center", gap: 8,
              padding: "7px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 12 }}>
              <span style={{ fontSize: 11, color: T.gray, minWidth: 85 }}>{b.scheduled_date}</span>
              <span style={{ flex: 1 }}>{b.title || b.keyword}</span>
              {b.pillar && <Badge color="purple">{b.pillar}</Badge>}
              <Btn small variant="success" onClick={() => publishBlog(b.blog_id)}>Publish now</Btn>
            </div>
          ))}
        </Card>
      )}

      {/* Tab: Generate batch */}
      {tab === "generate" && (
        <Card style={{ maxWidth: 480 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Generate Blog Batch</div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, fontWeight: 500, color: T.gray, display: "block", marginBottom: 4 }}>Pillar</label>
            <input value={batchPillar} onChange={e => setBatchPillar(e.target.value)} placeholder="e.g. turmeric"
              style={{ width: "100%", padding: "7px 10px", border: "0.5px solid rgba(0,0,0,0.15)", borderRadius: 8, fontSize: 12 }} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 11, fontWeight: 500, color: T.gray, display: "block", marginBottom: 4 }}>Count (max 20)</label>
            <input type="number" value={batchCount} min={1} max={20} onChange={e => setBatchCount(parseInt(e.target.value) || 10)}
              style={{ width: "100%", padding: "7px 10px", border: "0.5px solid rgba(0,0,0,0.15)", borderRadius: 8, fontSize: 12 }} />
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Btn variant="primary" onClick={generateBatch} disabled={generating}>{generating ? "Generating..." : "Generate Batch"}</Btn>
            {msg && <span style={{ fontSize: 11, color: T.teal }}>{msg}</span>}
          </div>
          <div style={{ marginTop: 16, fontSize: 11, color: T.gray }}>
            Blogs will be generated in the background using your keyword list. Check the Calendar tab for progress.
          </div>

          {/* By-pillar stats */}
          {pillars.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Pillar Status</div>
              {pillars.map(p => {
                const counts = stats?.by_pillar?.[p] || {}
                return (
                  <div key={p} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0",
                    borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 11 }}>
                    <span style={{ fontWeight: 500 }}>{p}</span>
                    <span style={{ color: T.gray }}>
                      <span style={{ color: T.teal }}>{counts.published || 0} pub</span>
                      {" · "}{counts.frozen || 0} frozen
                      {" · "}{(counts.draft || 0) + (counts.generating || 0)} draft
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      )}

      {/* Tab: Due today */}
      {tab === "due" && (
        <Card>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Due Today</div>
          {!dueToday?.length ? (
            <div style={{ fontSize: 12, color: T.gray }}>No blogs due today.</div>
          ) : dueToday.map(b => (
            <div key={b.blog_id} style={{ display: "flex", alignItems: "center", gap: 8,
              padding: "7px 0", borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 12 }}>
              <span style={{ flex: 1 }}>{b.title || b.keyword}</span>
              {b.pillar && <Badge color="purple">{b.pillar}</Badge>}
              <Btn small variant="success" onClick={() => publishBlog(b.blog_id)}>Publish now</Btn>
            </div>
          ))}
        </Card>
      )}

      {/* Edit modal */}
      {editBlog && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 1000,
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "#fff", borderRadius: 12, padding: 24, width: "min(600px,95vw)", maxHeight: "85vh", overflowY: "auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Edit Blog</div>
              <Btn small onClick={() => setEditBlog(null)}>Close</Btn>
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 11, fontWeight: 500, color: T.gray, display: "block", marginBottom: 4 }}>Title</label>
              <input value={editBody.title || ""} onChange={e => setEditBody(b => ({...b, title: e.target.value}))}
                style={{ width: "100%", padding: "7px 10px", border: "0.5px solid rgba(0,0,0,0.15)", borderRadius: 8, fontSize: 12 }} />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, fontWeight: 500, color: T.gray, display: "block", marginBottom: 4 }}>Meta Description</label>
              <textarea value={editBody.meta_desc || ""} onChange={e => setEditBody(b => ({...b, meta_desc: e.target.value}))} rows={2}
                style={{ width: "100%", padding: "7px 10px", border: "0.5px solid rgba(0,0,0,0.15)", borderRadius: 8, fontSize: 12, resize: "vertical" }} />
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <Btn variant="primary" onClick={saveBlog}>Save</Btn>
              <Btn onClick={() => setEditBlog(null)}>Cancel</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PAGE: SYSTEM GRAPH (D3 force-directed universe → pillar → cluster → keyword)
// ─────────────────────────────────────────────────────────────────────────────
import * as d3 from "d3"

function SystemGraphPage() {
  const { activeProject } = useStore()
  const svgRef = useRef(null)
  const [selected, setSelected] = useState(null)
  const [filter, setFilter] = useState({ universe: true, pillar: true, cluster: true, keyword: true })
  const [search, setSearch] = useState("")
  const [pillarFilter, setPillarFilter] = useState("all")

  const { data: graph, isLoading, refetch } = useQuery({
    queryKey: ["graph", activeProject],
    queryFn: () => api.get(`/api/graph/${activeProject}`),
    enabled: !!activeProject,
  })

  const { data: graphStats } = useQuery({
    queryKey: ["graph-stats", activeProject],
    queryFn: () => api.get(`/api/graph/${activeProject}/stats`),
    enabled: !!activeProject,
  })

  const invalidate = async () => {
    await api.post(`/api/graph/${activeProject}/invalidate`, {})
    refetch()
  }

  const NodeColor = {
    universe: "#7F77DD", pillar: "#1D9E75", cluster: "#BA7517",
    keyword: "#4A90D9", info_gap: "#E07070", product: "#E24B4A",
  }
  const EdgeColor = {
    universe_pillar: "#1D9E75", pillar_cluster: "#BA7517",
    cluster_keyword: "#4A90D9", pillar_keyword: "#4A90D9",
    universe_keyword: "#7F77DD",
  }
  const StatusFill = {
    published: "#639922", frozen: "#7F77DD", draft: "#aaa",
    generating: "#BA7517", approved: "#1D9E75",
  }

  useEffect(() => {
    if (!graph || !svgRef.current) return

    const nodes = graph.nodes.filter(n => filter[n.type] !== false)
    const nodeIds = new Set(nodes.map(n => n.id))
    const links = graph.edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target))

    const pillarSet = new Set(nodes.filter(n => n.type === "pillar").map(n => n.label))

    const filteredNodes = pillarFilter === "all"
      ? nodes
      : nodes.filter(n => {
          if (n.type === "universe") return true
          if (n.type === "pillar") return n.label === pillarFilter
          // For clusters/keywords find their pillar via links
          const parentEdge = links.find(e => e.target === n.id)
          if (!parentEdge) return false
          const parentNode = nodes.find(nd => nd.id === parentEdge.source)
          if (!parentNode) return false
          if (parentNode.type === "pillar") return parentNode.label === pillarFilter
          const grandparentEdge = links.find(e => e.target === parentEdge.source)
          const grandparent = grandparentEdge && nodes.find(nd => nd.id === grandparentEdge.source)
          return grandparent?.label === pillarFilter
        })

    const filteredIds = new Set(filteredNodes.map(n => n.id))
    const filteredLinks = links.filter(e => filteredIds.has(e.source) && filteredIds.has(e.target))

    const svg = d3.select(svgRef.current)
    svg.selectAll("*").remove()

    const width = svgRef.current.clientWidth || 800
    const height = 550

    const zoom = d3.zoom().scaleExtent([0.1, 4]).on("zoom", e => g.attr("transform", e.transform))
    svg.call(zoom)

    const g = svg.append("g")

    const simulation = d3.forceSimulation(filteredNodes)
      .force("link", d3.forceLink(filteredLinks).id(d => d.id).distance(d => {
        if (d.type === "universe_pillar") return 120
        if (d.type === "pillar_cluster") return 80
        return 50
      }))
      .force("charge", d3.forceManyBody().strength(-80))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(d => d.type === "universe" ? 30 : d.type === "pillar" ? 18 : 10))

    const link = g.append("g").selectAll("line").data(filteredLinks).join("line")
      .attr("stroke", d => EdgeColor[d.type] || "#ccc")
      .attr("stroke-width", d => d.type === "universe_pillar" ? 2 : 1)
      .attr("stroke-opacity", 0.5)

    const node = g.append("g").selectAll("circle").data(filteredNodes).join("circle")
      .attr("r", d => d.type === "universe" ? 22 : d.type === "pillar" ? 14 : d.type === "cluster" ? 10 : 6)
      .attr("fill", d => {
        if (d.type === "keyword" && d.status) return StatusFill[d.status] || NodeColor.keyword
        return NodeColor[d.type] || "#999"
      })
      .attr("stroke", d => search && d.label.toLowerCase().includes(search.toLowerCase()) ? "#FF6B35" : "none")
      .attr("stroke-width", 3)
      .attr("opacity", d => search && !d.label.toLowerCase().includes(search.toLowerCase()) ? 0.3 : 1)
      .style("cursor", "pointer")
      .call(d3.drag()
        .on("start", (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y })
        .on("drag", (e, d) => { d.fx=e.x; d.fy=e.y })
        .on("end", (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx=null; d.fy=null })
      )
      .on("click", (e, d) => setSelected(d))

    const label = g.append("g").selectAll("text").data(filteredNodes.filter(n => n.type !== "keyword")).join("text")
      .text(d => d.label.length > 16 ? d.label.slice(0,16)+"…" : d.label)
      .attr("font-size", d => d.type === "universe" ? 11 : d.type === "pillar" ? 10 : 9)
      .attr("fill", "#333")
      .attr("text-anchor", "middle")
      .attr("dy", d => -(d.type === "universe" ? 26 : d.type === "pillar" ? 18 : 14))
      .style("pointer-events", "none")

    simulation.on("tick", () => {
      link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x).attr("y2", d => d.target.y)
      node.attr("cx", d => d.x).attr("cy", d => d.y)
      label.attr("x", d => d.x).attr("y", d => d.y)
    })

    return () => simulation.stop()
  }, [graph, filter, search, pillarFilter])

  const pillars = graph?.nodes.filter(n => n.type === "pillar").map(n => n.label) || []

  if (!activeProject) return <div style={{ color: T.gray, padding: 20 }}>Select a project first.</div>

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 20, fontWeight: 600 }}>System Graph</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {graphStats && (
            <span style={{ fontSize: 11, color: T.gray }}>
              {graphStats.node_count} nodes · {graphStats.edge_count} edges
            </span>
          )}
          <Btn small onClick={invalidate}>Refresh</Btn>
        </div>
      </div>

      {/* Controls */}
      <div style={{ display: "flex", gap: 10, marginBottom: 10, flexWrap: "wrap", alignItems: "center" }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search keyword..."
          style={{ padding: "5px 10px", border: "0.5px solid rgba(0,0,0,0.15)", borderRadius: 8, fontSize: 12, width: 180 }} />
        <select value={pillarFilter} onChange={e => setPillarFilter(e.target.value)}
          style={{ padding: "5px 10px", borderRadius: 8, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 12 }}>
          <option value="all">All pillars</option>
          {pillars.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        {Object.entries(NodeColor).map(([type, color]) => (
          <label key={type} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, cursor: "pointer" }}>
            <input type="checkbox" checked={filter[type] !== false}
              onChange={e => setFilter(f => ({...f, [type]: e.target.checked}))} />
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }}/>
            {type}
          </label>
        ))}
      </div>

      <div style={{ display: "flex", gap: 12 }}>
        {/* Graph canvas */}
        <div style={{ flex: 1, border: "0.5px solid rgba(0,0,0,0.1)", borderRadius: 12, overflow: "hidden", background: "#fafafa" }}>
          {isLoading ? (
            <div style={{ height: 550, display: "flex", alignItems: "center", justifyContent: "center", color: T.gray }}>
              Loading graph...
            </div>
          ) : !graph?.nodes?.length ? (
            <div style={{ height: 550, display: "flex", alignItems: "center", justifyContent: "center", color: T.gray, textAlign: "center" }}>
              No graph data yet.<br/>
              <span style={{ fontSize: 11 }}>Run a keyword pipeline to build the graph.</span>
            </div>
          ) : (
            <svg ref={svgRef} width="100%" height="550" />
          )}
        </div>

        {/* Selected node panel */}
        {selected && (
          <div style={{ width: 220, flexShrink: 0 }}>
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <Badge color={selected.type === "keyword" ? "purple" : selected.type === "pillar" ? "teal" : "amber"}>
                  {selected.type}
                </Badge>
                <button onClick={() => setSelected(null)} style={{ background: "none", border: "none", cursor: "pointer", color: T.gray }}>×</button>
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, wordBreak: "break-word" }}>{selected.label}</div>
              {selected.status && <div style={{ fontSize: 11, color: T.gray, marginBottom: 4 }}>Status: {selected.status}</div>}
              {selected.rank != null && <div style={{ fontSize: 11, color: T.gray, marginBottom: 4 }}>Rank: #{selected.rank}</div>}
              {selected.word_count > 0 && <div style={{ fontSize: 11, color: T.gray, marginBottom: 4 }}>Words: {selected.word_count}</div>}
              {selected.seo_score > 0 && <div style={{ fontSize: 11, color: T.gray }}>SEO: {selected.seo_score?.toFixed(1)}</div>}
              {selected.blog_count != null && <div style={{ fontSize: 11, color: T.teal }}>Blogs: {selected.blog_count}</div>}
            </Card>

            {/* Legend */}
            <Card style={{ marginTop: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 8 }}>Legend</div>
              {Object.entries(NodeColor).map(([t, c]) => (
                <div key={t} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: c, flexShrink: 0 }}/>
                  <span style={{ fontSize: 10 }}>{t}</span>
                </div>
              ))}
              <div style={{ borderTop: "0.5px solid rgba(0,0,0,0.08)", marginTop: 8, paddingTop: 8, fontSize: 10, color: T.gray }}>
                Node color by status:<br/>
                {Object.entries(StatusFill).map(([s, c]) => (
                  <div key={s} style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: c }}/>
                    {s}
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ENHANCED RANKINGS PAGE — trend chart + alerts + predictions
// ─────────────────────────────────────────────────────────────────────────────

const NAV = [
  { id: "dashboard",    label: "Dashboard" },
  { id: "keywords",     label: "Keywords" },
  { id: "kw2",          label: "Keywords v2" },
  { id: "strategy-hub", label: "Strategy Hub" },
  { id: "content",      label: "Content" },
  { id: "audit",        label: "🔬 Audit" },
  { id: "blogs",        label: "Content Calendar" },
  { id: "graph",        label: "System Graph" },
  { id: "seo-checker",  label: "SEO Checker" },
  { id: "quality",      label: "Quality" },
  { id: "prompts",      label: "Prompts" },
  { id: "rsd",          label: "Research & Dev" },
  { id: "bug-fixer",    label: "Bug Fixer" },
  { id: "queue",        label: "Queue" },
  { id: "errors",       label: "Errors" },
  { id: "gsc-setup",    label: "🔍 GSC Setup" },
  { id: "gsc-search",   label: "🔎 GSC Search" },
  { id: "pages",        label: "📄 Pages" },
  { id: "settings",     label: "⚙ Settings" },
]

function Sidebar({ page: currentPage, setPage }) {
  const { user } = useStore()
  const logout = () => { localStorage.removeItem("annaseo_token"); localStorage.removeItem("annaseo_project"); window.location.reload() }
  return (
    <div style={{
      width: 218,
      background: "#FFFFFF",
      borderRight: "0.5px solid rgba(60,60,67,0.12)",
      display: "flex",
      flexDirection: "column",
      minHeight: "100vh",
      flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: "18px 16px 14px", borderBottom: "0.5px solid rgba(60,60,67,0.08)" }}>
        <div style={{
          fontSize: 18, fontWeight: 700, color: "#000000",
          letterSpacing: -0.4, lineHeight: 1,
        }}>
          Anna<span style={{ color: "#007AFF" }}>SEO</span>
        </div>
        <div style={{ fontSize: 11, color: "rgba(60,60,67,0.4)", marginTop: 3, letterSpacing: 0.1 }}>
          AI Content Intelligence
        </div>
      </div>

      {/* Nav */}
      <div style={{ flex: 1, padding: "8px 8px", overflowY: "auto" }}>
        {NAV.map(n => {
          const isActive = currentPage === n.id
          return (
            <button key={n.id} onClick={() => setPage(n.id)} style={{
              display: "flex", alignItems: "center", gap: 8, padding: "7px 10px",
              width: "100%", border: "none", cursor: "pointer",
              fontSize: 13, fontWeight: isActive ? 600 : 400,
              borderRadius: 9, marginBottom: 1, textAlign: "left",
              background: isActive ? "rgba(0,122,255,0.1)" : "transparent",
              color: isActive ? "#007AFF" : "rgba(60,60,67,0.75)",
              transition: "background 0.1s, color 0.1s",
            }}
            onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = "rgba(0,0,0,0.04)" }}
            onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "transparent" }}
            >
              <span style={{
                width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                background: isActive ? "#007AFF" : "rgba(60,60,67,0.2)",
              }}/>
              {n.label}
            </button>
          )
        })}
      </div>

      {/* Footer */}
      <div style={{ padding: "12px 16px", borderTop: "0.5px solid rgba(60,60,67,0.08)" }}>
        {user?.email && (
          <div style={{
            fontSize: 11, color: "rgba(60,60,67,0.45)", marginBottom: 7,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {user.email}
          </div>
        )}
        <button onClick={logout} style={{
          fontSize: 12, color: "#FF3B30", background: "none",
          border: "none", cursor: "pointer", padding: 0, fontWeight: 400,
        }}>
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
    groq_key: "", groq_model: "",
    gemini_key: "", gemini_paid_key: "",
    anthropic_key: "", anthropic_paid_key: "",
    openai_key: "", openai_paid_key: "",
    openrouter_key: "", openrouter_model: "",
    ollama_url: "", ollama_model: "",
  })
  const [status, setStatus] = useState({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState("")
  const { data: current } = useQuery({
    queryKey: ["api-keys"],
    queryFn: () => api.get("/api/settings/api-keys"),
  })

  // Pre-populate non-secret fields (url, models) from server when loaded
  useEffect(() => {
    if (!current) return
    setKeys(prev => ({
      ...prev,
      ollama_url:   current.ollama_url   || prev.ollama_url   || "http://172.235.16.165:11434",
      ollama_model: current.ollama_model || prev.ollama_model || "qwen2.5:3b",
      groq_model:   current.groq_model   || prev.groq_model   || "llama-3.3-70b-versatile",
      openrouter_model: current.openrouter_model || prev.openrouter_model || "openai/gpt-4o",
      google_redirect_uri: current.google_redirect_uri || prev.google_redirect_uri || "",
    }))
  }, [current])

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

  const TierGroup = ({ label, freeKey, paidKey, freePlaceholder, paidPlaceholder }) => (
    <div style={{ marginBottom: 18, padding: "12px 14px", borderRadius: 8, background: "rgba(0,0,0,0.02)", border: "0.5px solid rgba(0,0,0,0.08)" }}>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10, color: T.purple }}>{label}</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <label style={{ fontSize: 11, fontWeight: 500, color: T.teal }}>Free Tier</label>
            {current?.[freeKey] !== undefined && (
              <Badge color={current[freeKey] ? "teal" : "red"}>{current[freeKey] ? "set" : "not set"}</Badge>
            )}
          </div>
          <input type="password" value={keys[freeKey] || ""}
            onChange={e=>setKeys({...keys,[freeKey]:e.target.value})}
            placeholder={freePlaceholder || "Free tier key..."}
            style={{ width:"100%",padding:"7px 9px",borderRadius:6,border:"0.5px solid rgba(0,150,100,0.3)",
                     fontSize:11,boxSizing:"border-box",fontFamily:"monospace" }}/>
          <div style={{ fontSize: 10, color: T.gray, marginTop: 3 }}>General AI use · all features</div>
        </div>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <label style={{ fontSize: 11, fontWeight: 500, color: "#e67e22" }}>Paid Tier</label>
            {current?.[paidKey] !== undefined && (
              <Badge color={current[paidKey] ? "amber" : "gray"}>{current[paidKey] ? "set" : "not set"}</Badge>
            )}
          </div>
          <input type="password" value={keys[paidKey] || ""}
            onChange={e=>setKeys({...keys,[paidKey]:e.target.value})}
            placeholder={paidPlaceholder || "Paid tier key..."}
            style={{ width:"100%",padding:"7px 9px",borderRadius:6,border:"0.5px solid rgba(230,126,34,0.3)",
                     fontSize:11,boxSizing:"border-box",fontFamily:"monospace" }}/>
          <div style={{ fontSize: 10, color: T.gray, marginTop: 3 }}>Content generation only</div>
        </div>
      </div>
    </div>
  )

  return (
    <div style={{ maxWidth: 680 }}>
      <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 4 }}>Settings</div>
      <div style={{ fontSize: 12, color: T.gray, marginBottom: 24 }}>API keys are encrypted before storage. They are never exposed in logs.</div>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16, color: T.purple }}>
          AI Model Configuration
        </div>
        <div style={{ fontSize: 11, color: T.gray, background: T.purpleLight, borderRadius: 6, padding: "8px 12px", marginBottom: 16 }}>
          <strong>Routing:</strong> Groq Llama (primary, free) → Ollama/DeepSeek (offline fallback) → Claude (quality gates ≤1000 tokens only).<br/>
          <strong>Paid tier keys</strong> are used exclusively for content generation to preserve free-tier quotas.
        </div>

        {/* Groq */}
        <Field label="Groq API Key (primary — free tier)" k="groq_key" type="password" placeholder="gsk_..." />
        <Field label="Groq Model" k="groq_model" placeholder="llama-3.3-70b-versatile" />

        {/* Ollama */}
        <Field label="Ollama URL (Remote Server)" k="ollama_url" placeholder="http://172.235.16.165:11434" />
        <Field label="Ollama Model" k="ollama_model" placeholder="deepseek-r1:7b" />

        {/* Gemini tiers */}
        <TierGroup
          label="Google Gemini"
          freeKey="gemini_key"
          paidKey="gemini_paid_key"
          freePlaceholder="AIzaSy... (free tier)"
          paidPlaceholder="AIzaSy... (paid tier)"
        />

        {/* ChatGPT / OpenAI tiers */}
        <TierGroup
          label="ChatGPT / OpenAI"
          freeKey="openai_key"
          paidKey="openai_paid_key"
          freePlaceholder="sk-... (free tier)"
          paidPlaceholder="sk-... (paid tier)"
        />

        {/* Anthropic tiers */}
        <TierGroup
          label="Anthropic Claude"
          freeKey="anthropic_key"
          paidKey="anthropic_paid_key"
          freePlaceholder="sk-ant-... (free tier)"
          paidPlaceholder="sk-ant-... (paid tier)"
        />

        {/* OpenRouter */}
        <div style={{ marginBottom: 18, padding: "12px 14px", borderRadius: 8, background: "rgba(0,0,0,0.02)", border: "0.5px solid rgba(0,0,0,0.08)" }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10, color: T.purple }}>🌐 OpenRouter (Multi-Model Gateway)</div>
          <div style={{ fontSize: 10, color: T.gray, marginBottom: 10 }}>
            Access 100+ models (GPT-4o, Claude, Gemini, Llama, Mistral) with a single API key from openrouter.ai
          </div>
          <Field label="OpenRouter API Key" k="openrouter_key" type="password" placeholder="sk-or-v1-..." />
          <Field label="OpenRouter Model" k="openrouter_model" placeholder="openai/gpt-4o" />
        </div>

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
                <Badge color={v === "ok" ? "teal" : v.startsWith("not") ? "gray" : v.includes("configured") ? "amber" : "red"}>{v}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10, color: T.purple }}>
          🔍 Google Search Console (OAuth)
        </div>
        <div style={{ fontSize: 10, color: T.gray, marginBottom: 12 }}>
          Required to connect GSC and fetch real search data. Get credentials from{" "}
          <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer" style={{ color: T.teal }}>Google Cloud Console</a>.
        </div>
        <Field label="Google Client ID" k="google_client_id" placeholder="123456789-xxx.apps.googleusercontent.com" />
        <Field label="Google Client Secret" k="google_client_secret" type="password" placeholder="GOCSPX-..." />
        <Field label="Redirect URI" k="google_redirect_uri" placeholder="https://annaseo.pureleven.com/api/gsc/auth/callback" />
      </Card>

      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>AI Routing Priority</div>
        {[
          { model: "Groq Llama-3.3-70b", use: "Bulk analysis: intent, clusters, scoring, universe generation", cost: "Free", badge: "teal" },
          { model: "Ollama (local)", use: "Offline fallback when Groq unavailable", cost: "Free (local)", badge: "teal" },
          { model: "Gemini Free Tier", use: "General AI: research, structure, verify, links, references", cost: "Free quota", badge: "teal" },
          { model: "Gemini Paid Tier", use: "Content generation: Draft, Redevelop, Quality Loop", cost: "Pay-per-use", badge: "amber" },
          { model: "Anthropic Claude", use: "Content polish pass after Gemini draft — E-E-A-T & readability", cost: "Pay-per-use", badge: "amber" },
          { model: "OpenAI / ChatGPT", use: "Optional additional polish pass (if key configured)", cost: "Pay-per-use", badge: "amber" },
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

      <OllamaServersSection />
    </div>
  )
}

// ── Ollama Servers Management Component ─────────────────────────────────────
function OllamaServersSection() {
  const [servers, setServers] = useState([])
  const [newServer, setNewServer] = useState({ name: "", url: "", model: "qwen2.5:3b", enabled: true, is_primary: false })
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState("")

  const qclient = useQueryClient()

  // Load servers
  useEffect(() => {
    fetchServers()
  }, [])

  const fetchServers = async () => {
    try {
      const r = await api.get("/api/settings/ollama-servers")
      setServers(r || [])
    } catch (e) {
      console.error("Failed to fetch ollama servers:", e)
    }
  }

  const addServer = async () => {
    if (!newServer.name.trim() || !newServer.url.trim()) {
      setMsg("Name and URL required")
      return
    }
    setLoading(true)
    setMsg("")
    try {
      const r = await api.post("/api/settings/ollama-servers", newServer)
      if (r?.status === "added") {
        setNewServer({ name: "", url: "", model: "qwen2.5:3b", enabled: true, is_primary: false })
        await fetchServers()
        setMsg("✓ Server added")
        setTimeout(() => setMsg(""), 3000)
      }
    } catch (e) {
      setMsg("Error adding server: " + e.message)
    } finally {
      setLoading(false)
    }
  }

  const updateServer = async (id, updates) => {
    try {
      const r = await api.put(`/api/settings/ollama-servers/${id}`, updates)
      if (r?.status === "updated") {
        await fetchServers()
      }
    } catch (e) {
      console.error("Failed to update server:", e)
    }
  }

  const deleteServer = async (id) => {
    if (!confirm("Delete this server?")) return
    try {
      const r = await api.delete(`/api/settings/ollama-servers/${id}`)
      if (r?.status === "deleted") {
        await fetchServers()
      }
    } catch (e) {
      console.error("Failed to delete server:", e)
    }
  }

  const testServer = async (id) => {
    try {
      const r = await api.post(`/api/settings/ollama-servers/${id}/test`)
      const srv = servers.find(s => s.server_id === id)
      if (srv) {
        srv._test_result = r
        setServers([...servers])
      }
    } catch (e) {
      const srv = servers.find(s => s.server_id === id)
      if (srv) {
        srv._test_result = { status: "error", message: e.message }
        setServers([...servers])
      }
    }
  }

  return (
    <Card style={{ marginTop: 16 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16, color: T.purple }}>
        🖥️ External Ollama Servers
      </div>
      <div style={{ fontSize: 11, color: T.gray, background: T.purpleLight, borderRadius: 6, padding: "8px 12px", marginBottom: 16 }}>
        Add remote Ollama servers to distribute load or provide failover redundancy. Servers are tested before use.
      </div>

      {/* Add new server form */}
      <div style={{ background: "rgba(255,255,255,0.5)", border: "0.5px dashed rgba(0,0,0,0.1)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10, color: T.darkGray }}>Add New Server</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
          <input
            type="text"
            placeholder="Server name (e.g., Main Ollama)"
            value={newServer.name}
            onChange={(e) => setNewServer({ ...newServer, name: e.target.value })}
            style={{ padding: "7px 10px", borderRadius: 6, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 11, boxSizing: "border-box" }}
          />
          <input
            type="text"
            placeholder="URL (e.g., http://172.235.16.165:11434)"
            value={newServer.url}
            onChange={(e) => setNewServer({ ...newServer, url: e.target.value })}
            style={{ padding: "7px 10px", borderRadius: 6, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 11, boxSizing: "border-box" }}
          />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
          <input
            type="text"
            placeholder="Model (e.g., qwen2.5:3b)"
            value={newServer.model}
            onChange={(e) => setNewServer({ ...newServer, model: e.target.value })}
            style={{ padding: "7px 10px", borderRadius: 6, border: "0.5px solid rgba(0,0,0,0.15)", fontSize: 11, boxSizing: "border-box" }}
          />
          <label style={{ display: "flex", alignItems: "center", fontSize: 11, gap: 6 }}>
            <input
              type="checkbox"
              checked={newServer.enabled}
              onChange={(e) => setNewServer({ ...newServer, enabled: e.target.checked })}
            />
            Enabled
          </label>
          <label style={{ display: "flex", alignItems: "center", fontSize: 11, gap: 6 }}>
            <input
              type="checkbox"
              checked={newServer.is_primary}
              onChange={(e) => setNewServer({ ...newServer, is_primary: e.target.checked })}
            />
            Set as Primary
          </label>
        </div>
        <Btn onClick={addServer} variant="primary" disabled={loading} style={{ marginTop: 10 }}>
          {loading ? "Adding..." : "Add Server"}
        </Btn>
        {msg && <div style={{ marginTop: 8, fontSize: 11, color: msg.startsWith("✓") ? T.teal : T.red }}>{msg}</div>}
      </div>

      {/* List of servers */}
      {servers.length > 0 ? (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: T.darkGray }}>Configured Servers</div>
          {servers.map((srv) => (
            <div key={srv.server_id} style={{ background: "rgba(0,0,0,0.02)", border: "0.5px solid rgba(0,0,0,0.08)", borderRadius: 8, padding: 12, marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    {srv.name}
                    {srv.is_primary && <Badge style={{ marginLeft: 8 }} color="teal">Primary</Badge>}
                    {!srv.enabled && <Badge style={{ marginLeft: 8 }} color="gray">Disabled</Badge>}
                  </div>
                  <div style={{ fontSize: 11, color: T.gray, marginTop: 3, fontFamily: "monospace" }}>{srv.url}</div>
                  <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>Model: {srv.model}</div>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <Btn size="sm" onClick={() => testServer(srv.server_id)}>Test</Btn>
                  <Btn size="sm" onClick={() => deleteServer(srv.server_id)}>Delete</Btn>
                </div>
              </div>
              {srv._test_result && (
                <div style={{ background: srv._test_result.status === "ok" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)", borderRadius: 6, padding: "6px 10px", fontSize: 11, marginTop: 8 }}>
                  <Badge color={srv._test_result.status === "ok" ? "teal" : "red"}>{srv._test_result.status}</Badge>
                  <div style={{ marginTop: 4 }}>{srv._test_result.message}</div>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 11, color: T.gray, padding: "12px 0" }}>No external servers configured. Add one to get started.</div>
      )}
    </Card>
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
// QUEUE DASHBOARD PAGE
// ─────────────────────────────────────────────────────────────────────────────

function QueueDashboard() {
  const [metrics, setMetrics] = useState(null)
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const { token } = useStore()

  const apiBase = API || ""

  const fetchData = async () => {
    setLoading(true)
    try {
      const { res: _mRes, parsed: m } = await fetchDebug(`${apiBase}/api/queue/metrics`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      const { res: _jRes, parsed: j } = await fetchDebug(`${apiBase}/api/queue/jobs`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      setMetrics(m)
      setJobs(Array.isArray(j) ? j : j?.jobs || [])
    } catch (e) {
      console.error("QueueDashboard fetch error", e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [token])

  const action = async (jobId, type) => {
    await fetchDebug(`${apiBase}/api/jobs/${jobId}/${type}`, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {} })
    fetchData()
  }

  const statusColor = { running: T.teal, queued: T.amber, paused: T.purple, complete: T.teal, error: T.red, cancelled: T.gray }

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>Queue Dashboard</div>
      {loading && <LoadingSpinner/>}

      {metrics && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 10, marginBottom: 16 }}>
          {Object.entries(metrics).map(([k, v]) => (
            <Card key={k} style={{ textAlign: "center", padding: 12 }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: T.purple }}>{v}</div>
              <div style={{ fontSize: 10, color: T.gray, marginTop: 2, textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</div>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 10 }}>Jobs ({jobs.length})</div>
        {jobs.length === 0 ? (
          <div style={{ color: T.gray, fontSize: 12, padding: "12px 0" }}>No jobs in queue.</div>
        ) : jobs.map((job) => (
          <div key={job.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0",
            borderBottom: "0.5px solid rgba(0,0,0,0.06)", fontSize: 12 }}>
            <span style={{ fontFamily: "monospace", fontSize: 10, color: T.gray, minWidth: 60 }}>{String(job.id).slice(0,8)}</span>
            <Badge color={statusColor[job.status] || "gray"}>{job.status}</Badge>
            <span style={{ flex: 1, color: T.gray, fontSize: 11 }}>
              Step: {job.last_completed_step || "—"} · Control: {job.control_state || "—"}
            </span>
            <span style={{ fontSize: 10, color: T.gray }}>{job.retry_count || 0}/{job.max_retries || 3} retries</span>
            <span style={{ fontSize: 10, color: T.gray, minWidth: 80 }}>{(job.updated_at || "").slice(0, 16)}</span>
            <div style={{ display: "flex", gap: 4 }}>
              <Btn small onClick={() => action(job.id, "pause")}>Pause</Btn>
              <Btn small variant="success" onClick={() => action(job.id, "resume")}>Resume</Btn>
              <Btn small variant="danger" onClick={() => action(job.id, "cancel")}>Cancel</Btn>
            </div>
          </div>
        ))}
      </Card>
    </div>
  )
}



function ErrorsDashboard() {
  const [errors, setErrors] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState({})
  const { token } = useStore()
  const apiBase = API || ""

  const fetchErrors = async () => {
    setLoading(true)
    try {
      const { res, parsed: json } = await fetchDebug(`${apiBase}/api/errors/realtime?limit=200`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      setErrors(json.errors || [])
    } catch (err) {
      console.error('fetchErrors', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchErrors()
    const interval = setInterval(fetchErrors, 10000)
    return () => clearInterval(interval)
  }, [token])

  const typeColor = { "ValueError": T.amber, "KeyError": T.amber, "TypeError": T.amber,
    "RuntimeError": T.red, "500": T.red, "404": T.gray, "ConnectionError": T.red }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div style={{ fontSize: 20, fontWeight: 600 }}>Error Log</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 11, color: T.gray }}>{errors.length} errors</span>
          <Btn small onClick={fetchErrors}>Refresh</Btn>
        </div>
      </div>
      {loading && <LoadingSpinner/>}

      {errors.length === 0 ? (
        <Card style={{ textAlign: "center", padding: 30 }}>
          <div style={{ fontSize: 13, color: T.gray }}>No errors recorded. System is healthy.</div>
        </Card>
      ) : errors.map((e, idx) => (
        <Card key={idx} style={{ marginBottom: 6, padding: "10px 14px", cursor: "pointer" }}
              onClick={() => setExpanded(p => ({...p, [idx]: !p[idx]}))}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 10, color: T.gray, minWidth: 120, flexShrink: 0 }}>
              {e.timestamp ? new Date(e.timestamp).toLocaleString() : "—"}
            </span>
            <Badge color={typeColor[e.type] || "amber"}>{e.type || "error"}</Badge>
            <span style={{ flex: 1, fontSize: 12, fontWeight: 500, color: "#1a1a1a",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: expanded[idx] ? "normal" : "nowrap" }}>
              {e.error}
            </span>
            <span style={{ fontSize: 10, color: T.gray, flexShrink: 0 }}>{e.path || ""}</span>
            <span style={{ color: T.gray, fontSize: 11 }}>{expanded[idx] ? "▲" : "▼"}</span>
          </div>
          {expanded[idx] && e.traceback && (
            <pre style={{ marginTop: 8, fontSize: 10, fontFamily: "monospace", background: "#f5f5f5",
              borderRadius: 6, padding: "8px 10px", whiteSpace: "pre-wrap", wordBreak: "break-all",
              color: T.red, maxHeight: 200, overflow: "auto" }}>
              {e.traceback}
            </pre>
          )}
        </Card>
      ))}
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
    "keywords":   <KeywordsUnifiedPage/>,
    "kw2":        <KwPage projectId={activeProject}/>,
    strategy:     <StrategyPage projectId={activeProject} setPage={setPage}/>,
    "strategy-hub": <StrategyIntelligenceHub projectId={activeProject} setPage={setPage}/>,
    content:      <ContentPage/>,
    blogs:        <BlogCalendarPage/>,
    graph:        <SystemGraphPage/>,
    "seo-checker":<SEOCheckerPage/>,
    quality:      <QualityDashboard/>,
    prompts:      <PromptEditorPage/>,
    "rsd":        <RSDPage/>,
    "bug-fixer":  <BugFixerPage/>,
    "new-project":<NewProjectPage/>,
    queue:        <QueueDashboard/>,
    errors:       <ErrorsDashboard/>,
    "gsc-setup":  <GscSetupPage projectId={activeProject}/>,
    "gsc-search": <GscSearchPage projectId={activeProject}/>,
    settings:     <SettingsPage/>,
    pages:        <PagesPage setPage={setPage}/>,
    audit:        <AuditPage/>,
  }

  return (
    <>
      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Plus Jakarta Sans', 'Helvetica Neue', sans-serif;
          background: #F2F2F7;
          color: #000000;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
        @keyframes pageIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        input, select, textarea, button { font-family: inherit; }
        input:focus, textarea:focus, select:focus { outline: 2px solid rgba(0,122,255,0.5); outline-offset: 0; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(60,60,67,0.18); border-radius: 99px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(60,60,67,0.28); }
      `}</style>
      <div style={{ display: "flex", minHeight: "100vh" }}>
        <Sidebar page={currentPage} setPage={setPage}/>
        <main style={{
          flex: 1,
          padding: "24px 28px",
          overflowY: "auto",
          maxHeight: "100vh",
          background: "#F2F2F7",
          animation: "pageIn 0.2s ease both",
        }}>
          {pages[currentPage] || <DashboardPage/>}
        </main>
      </div>
    </>
  )
}

export default function Root() {
  return (
    <QueryClientProvider client={qc}>
      <Notification />
      <DebugPanel />
      <App/>
    </QueryClientProvider>
  )
}
