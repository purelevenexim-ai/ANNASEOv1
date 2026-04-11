/**
 * PagesPage — Application page catalog with health-check auditing.
 * Lists every page in AnnaSEO, pings each page's primary endpoint,
 * and can save a full audit report to audits/pages_{date}/report.json.
 */
import { useState, useCallback } from "react"
import { api, useStore } from "./App"

// ── Design tokens ─────────────────────────────────────────────────────────────
const T = {
  text:   "#111827",
  soft:   "#6b7280",
  border: "#e5e7eb",
  bg:     "#f9fafb",
  blue:   "#1d4ed8",
  green:  "#059669",
  red:    "#dc2626",
  amber:  "#d97706",
  purple: "#7c3aed",
  teal:   "#0f766e",
  gray:   "#374151",
}

// ── Page catalog ──────────────────────────────────────────────────────────────
// endpoint: null = no API check (UI-only page), {p} = replaced with activeProject
const CATALOG = [
  // ── Core
  { id: "dashboard",    label: "Dashboard",         icon: "📊", cat: "Core",
    desc: "Project overview, health metrics, recent activity",
    endpoint: "/api/health", projectRequired: false },

  // ── Research
  { id: "kw2",          label: "Keywords v2",        icon: "🔑", cat: "Research",
    desc: "20-phase keyword universe generation (P1–P20)",
    endpoint: "/api/kw2/{p}/sessions/list", projectRequired: true },

  { id: "keywords",     label: "Keywords (legacy)",  icon: "🗝️", cat: "Research",
    desc: "Original keyword input and workflow pages",
    endpoint: null, projectRequired: false },

  { id: "strategy-hub", label: "Strategy Hub",       icon: "🧠", cat: "Research",
    desc: "Keyword sessions, strategy briefs, audience intelligence",
    endpoint: "/api/ki/{p}/keyword-strategy-brief", projectRequired: true },

  // ── Content
  { id: "content",      label: "Content",            icon: "✍️", cat: "Content",
    desc: "7-pass AI content generation pipeline",
    endpoint: null, projectRequired: true },

  { id: "blogs",        label: "Content Calendar",   icon: "📅", cat: "Content",
    desc: "Blog calendar, publishing queue, freeze management",
    endpoint: "/api/blogs/{p}/calendar", projectRequired: true },

  // ── SEO
  { id: "seo-checker",  label: "SEO Checker",        icon: "🔍", cat: "SEO",
    desc: "On-page SEO audit (INP, LCP, CLS, schema validation)",
    endpoint: "/api/health", projectRequired: false },

  { id: "gsc-setup",    label: "GSC Setup",          icon: "🔗", cat: "SEO",
    desc: "Google Search Console OAuth and property linking",
    endpoint: "/api/gsc/{p}/status", projectRequired: true },

  { id: "gsc-search",   label: "GSC Search",         icon: "📈", cat: "SEO",
    desc: "Search rankings import, trends, query analysis",
    endpoint: "/api/gsc/{p}/keywords", projectRequired: true },

  // ── Quality
  { id: "quality",      label: "Quality",            icon: "🎯", cat: "Quality",
    desc: "QI engine scoring, pending tuning approvals",
    endpoint: "/api/qi/dashboard", projectRequired: false },

  // ── Dev / Tools
  { id: "rsd",          label: "Research & Dev",     icon: "🔬", cat: "Dev",
    desc: "RSD health monitoring, self-improvement intelligence",
    endpoint: "/api/rsd/health", projectRequired: false },

  { id: "bug-fixer",    label: "Bug Fixer",          icon: "🐛", cat: "Dev",
    desc: "Automated code-fix pipeline with human approval gate",
    endpoint: "/api/rsd/approvals", projectRequired: false },

  { id: "prompts",      label: "Prompts",            icon: "💬", cat: "Dev",
    desc: "Prompt version management and live editor",
    endpoint: "/api/prompts", projectRequired: false },

  { id: "graph",        label: "System Graph",       icon: "🕸️", cat: "Dev",
    desc: "Live system dependency and connection graph",
    endpoint: null, projectRequired: true },

  { id: "audit",        label: "kw2 Audit",          icon: "🧪", cat: "Dev",
    desc: "Pillar & modifier extraction quality test suite",
    endpoint: "/api/kw2/{p}/audit", projectRequired: true },

  { id: "pages",        label: "Pages",              icon: "📄", cat: "Dev",
    desc: "Application page catalog with health-check auditing (this page)",
    endpoint: "/api/health", projectRequired: false },

  // ── System
  { id: "queue",        label: "Queue",              icon: "⏳", cat: "System",
    desc: "Background job queue — Ruflo orchestrator status",
    endpoint: "/api/queue/jobs", projectRequired: false },

  { id: "errors",       label: "Errors",             icon: "🚨", cat: "System",
    desc: "Error log dashboard — recent failures and traces",
    endpoint: "/api/errors", projectRequired: false },

  { id: "settings",     label: "Settings",           icon: "⚙️", cat: "System",
    desc: "Project settings, API keys, domain configuration",
    endpoint: "/api/health", projectRequired: false },
]

const CATEGORIES = ["All", "Core", "Research", "Content", "SEO", "Quality", "Dev", "System"]

// ── Status helpers ─────────────────────────────────────────────────────────────
function statusColor(s) {
  if (s === "ok")      return T.green
  if (s === "slow")    return T.amber
  if (s === "error")   return T.red
  if (s === "skip")    return T.soft
  return T.border  // unchecked
}

function statusLabel(s) {
  if (s === "ok")      return "✅ OK"
  if (s === "slow")    return "⚠️ Slow"
  if (s === "error")   return "❌ Error"
  if (s === "skip")    return "— No check"
  return "○ Not checked"
}

function catColor(cat) {
  return {
    Core: T.blue, Research: T.purple, Content: T.teal, SEO: "#0369a1",
    Quality: T.green, Dev: T.gray, System: T.amber,
  }[cat] || T.soft
}

// ── Small components ──────────────────────────────────────────────────────────

function CatBadge({ cat }) {
  const c = catColor(cat)
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 10, fontSize: 11, fontWeight: 600,
      background: c + "18", color: c, border: `1px solid ${c}33`,
    }}>{cat}</span>
  )
}

function StatusPill({ status, ms }) {
  const c = statusColor(status)
  return (
    <span style={{
      fontSize: 12, fontWeight: status === "error" ? 700 : 500,
      color: c,
    }}>
      {statusLabel(status)}
      {ms != null && status !== "skip" && status !== undefined &&
        <span style={{ color: T.soft, fontWeight: 400, marginLeft: 4 }}>({ms}ms)</span>
      }
    </span>
  )
}

function SummaryBar({ results }) {
  const total = CATALOG.length
  const ok      = Object.values(results).filter(r => r.status === "ok").length
  const slow    = Object.values(results).filter(r => r.status === "slow").length
  const error   = Object.values(results).filter(r => r.status === "error").length
  const skipped = Object.values(results).filter(r => r.status === "skip").length
  const checked = ok + slow + error

  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
      {[
        { label: "Total Pages",   value: total,   color: T.blue },
        { label: "Healthy",       value: ok,       color: T.green },
        { label: "Slow",          value: slow,     color: T.amber },
        { label: "Errors",        value: error,    color: T.red },
        { label: "No Endpoint",   value: skipped,  color: T.soft },
      ].map(s => (
        <div key={s.label} style={{
          background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10,
          padding: "10px 16px", minWidth: 110, textAlign: "center",
        }}>
          <div style={{ fontSize: 24, fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.value}</div>
          <div style={{ fontSize: 11, color: T.soft, marginTop: 4 }}>{s.label}</div>
        </div>
      ))}
      {checked > 0 && (
        <div style={{
          background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10,
          padding: "10px 16px", minWidth: 110, textAlign: "center",
        }}>
          <div style={{ fontSize: 24, fontWeight: 800, color: ok === checked ? T.green : T.amber, lineHeight: 1 }}>
            {Math.round((ok / checked) * 100)}%
          </div>
          <div style={{ fontSize: 11, color: T.soft, marginTop: 4 }}>Pass Rate</div>
        </div>
      )}
    </div>
  )
}

// ── Page card ─────────────────────────────────────────────────────────────────

function PageCard({ page, result, checking, projectId, onNavigate, onCheck }) {
  const statusC = statusColor(result?.status)

  return (
    <div style={{
      background: "#fff",
      border: `1px solid ${result?.status === "error" ? T.red + "44" : T.border}`,
      borderTop: `3px solid ${statusC}`,
      borderRadius: 10, padding: "14px 16px",
      display: "flex", flexDirection: "column", gap: 8,
    }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 20 }}>{page.icon}</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: T.text, lineHeight: 1.2 }}>{page.label}</div>
            <CatBadge cat={page.cat} />
          </div>
        </div>
        {page.projectRequired && !projectId && (
          <span style={{ fontSize: 11, color: T.amber, background: T.amber + "18", padding: "2px 8px", borderRadius: 10, flexShrink: 0 }}>
            Needs project
          </span>
        )}
      </div>

      {/* Description */}
      <p style={{ fontSize: 12, color: T.soft, lineHeight: 1.5, margin: 0 }}>{page.desc}</p>

      {/* Endpoint */}
      {page.endpoint && (
        <div style={{ fontSize: 11, fontFamily: "monospace", color: T.soft, background: T.bg, padding: "3px 8px", borderRadius: 6, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {page.endpoint.replace("{p}", projectId || ":project")}
        </div>
      )}

      {/* Status + actions */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 4 }}>
        <StatusPill status={result?.status} ms={result?.ms} />
        <div style={{ display: "flex", gap: 6 }}>
          {page.endpoint && (
            <button
              onClick={() => onCheck(page)}
              disabled={checking || (page.projectRequired && !projectId)}
              style={{
                padding: "4px 10px", borderRadius: 7, border: "none",
                background: T.bg, color: T.text, fontSize: 12, fontWeight: 500,
                cursor: (checking || (page.projectRequired && !projectId)) ? "not-allowed" : "pointer",
                opacity: (checking || (page.projectRequired && !projectId)) ? 0.4 : 1,
              }}
            >
              {checking ? "…" : "Check"}
            </button>
          )}
          <button
            onClick={() => onNavigate(page.id)}
            style={{
              padding: "4px 10px", borderRadius: 7, border: "none",
              background: T.blue, color: "#fff", fontSize: 12, fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Open →
          </button>
        </div>
      </div>

      {/* Error detail */}
      {result?.status === "error" && result?.detail && (
        <div style={{
          fontSize: 11, color: T.red, background: T.red + "0d",
          border: `1px solid ${T.red}33`, borderRadius: 6, padding: "4px 8px",
          fontFamily: "monospace", wordBreak: "break-all",
        }}>
          {result.detail}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PagesPage({ setPage }) {
  const { activeProject } = useStore()
  const [filter, setFilter]   = useState("All")
  const [results, setResults] = useState({})      // { [pageId]: { status, ms, detail } }
  const [checking, setChecking] = useState({})    // { [pageId]: true }
  const [running, setRunning]   = useState(false)
  const [savedTo, setSavedTo]   = useState(null)
  const [saveErr, setSaveErr]   = useState(null)

  const resolveEndpoint = useCallback((endpoint) => {
    if (!endpoint) return null
    return endpoint.replace("{p}", activeProject || "")
  }, [activeProject])

  async function checkOne(page) {
    if (!page.endpoint) return
    if (page.projectRequired && !activeProject) return

    const url = resolveEndpoint(page.endpoint)
    setChecking(c => ({ ...c, [page.id]: true }))

    const t0 = Date.now()
    try {
      const data = await api.get(url)
      const ms = Date.now() - t0
      const status = ms > 2000 ? "slow" : data === null ? "error" : "ok"
      setResults(r => ({ ...r, [page.id]: { status, ms, detail: null, endpoint: url } }))
    } catch (e) {
      const ms = Date.now() - t0
      setResults(r => ({ ...r, [page.id]: { status: "error", ms, detail: String(e?.message || e), endpoint: url } }))
    } finally {
      setChecking(c => { const n = { ...c }; delete n[page.id]; return n })
    }
  }

  async function auditAll() {
    setRunning(true)
    setSavedTo(null)
    setSaveErr(null)

    const eligible = CATALOG.filter(p => p.endpoint && !(p.projectRequired && !activeProject))

    // Run all checks in parallel
    await Promise.all(eligible.map(async (page) => {
      const url = resolveEndpoint(page.endpoint)
      const t0 = Date.now()
      try {
        const data = await api.get(url)
        const ms = Date.now() - t0
        const status = ms > 2000 ? "slow" : data === null ? "error" : "ok"
        setResults(r => ({ ...r, [page.id]: { status, ms, detail: null, endpoint: url } }))
      } catch (e) {
        const ms = Date.now() - t0
        setResults(r => ({ ...r, [page.id]: { status: "error", ms, detail: String(e?.message || e), endpoint: url } }))
      }
    }))

    // Mark pages with no endpoint as "skip"
    CATALOG.filter(p => !p.endpoint).forEach(p => {
      setResults(r => ({ ...r, [p.id]: { status: "skip" } }))
    })

    setRunning(false)
  }

  async function saveReport() {
    setSavedTo(null)
    setSaveErr(null)

    const report = {
      generated_at: new Date().toISOString(),
      project_id: activeProject,
      pages: CATALOG.map(p => ({
        id:       p.id,
        label:    p.label,
        category: p.cat,
        endpoint: p.endpoint ? resolveEndpoint(p.endpoint) : null,
        result:   results[p.id] || { status: "not_checked" },
      })),
      summary: {
        total:   CATALOG.length,
        ok:      Object.values(results).filter(r => r.status === "ok").length,
        slow:    Object.values(results).filter(r => r.status === "slow").length,
        error:   Object.values(results).filter(r => r.status === "error").length,
        skip:    Object.values(results).filter(r => r.status === "skip").length,
      },
    }

    try {
      const resp = await api.post("/api/audit/pages-report", report)
      setSavedTo(resp?.saved_to || "audits/pages_report/")
    } catch (e) {
      setSaveErr(String(e?.message || e))
    }
  }

  const filtered = filter === "All" ? CATALOG : CATALOG.filter(p => p.cat === filter)
  const hasResults = Object.keys(results).length > 0

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: T.text, margin: 0 }}>📄 Pages</h1>
          <p style={{ fontSize: 13, color: T.soft, margin: "4px 0 0" }}>
            Application page catalog · health checks · audit report export
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {hasResults && (
            <button
              onClick={saveReport}
              style={{
                padding: "9px 18px", borderRadius: 8, border: `1px solid ${T.green}`,
                background: T.green + "0d", color: T.green,
                fontWeight: 700, fontSize: 13, cursor: "pointer",
              }}
            >
              💾 Save Report
            </button>
          )}
          <button
            onClick={auditAll}
            disabled={running}
            style={{
              padding: "10px 22px", borderRadius: 8, border: "none",
              background: running ? "#9ca3af" : T.blue, color: "#fff",
              fontWeight: 700, fontSize: 14, cursor: running ? "not-allowed" : "pointer",
            }}
          >
            {running ? "⏳ Running…" : "▶ Audit All"}
          </button>
        </div>
      </div>

      {/* Project warning */}
      {!activeProject && (
        <div style={{
          background: "#fffbeb", border: `1px solid #fcd34d`,
          borderRadius: 8, padding: "10px 16px", color: T.amber,
          fontSize: 13, marginBottom: 16,
        }}>
          No active project — project-dependent checks will be skipped. Select a project from the sidebar.
        </div>
      )}

      {/* Summary */}
      {hasResults && <SummaryBar results={results} />}

      {/* Saved / error */}
      {savedTo && (
        <div style={{
          background: "#f0fdf4", border: `1px solid #bbf7d0`,
          borderRadius: 8, padding: "10px 16px", fontSize: 13, color: "#15803d", marginBottom: 16,
        }}>
          ✅ Report saved → <code style={{ fontFamily: "monospace", fontSize: 12 }}>{savedTo}</code>
        </div>
      )}
      {saveErr && (
        <div style={{
          background: "#fef2f2", border: `1px solid #fca5a5`,
          borderRadius: 8, padding: "10px 16px", fontSize: 13, color: T.red, marginBottom: 16,
        }}>
          Save failed: {saveErr}
        </div>
      )}

      {/* Category filter */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 20 }}>
        {CATEGORIES.map(c => (
          <button key={c} onClick={() => setFilter(c)} style={{
            padding: "5px 14px", borderRadius: 20, border: `1px solid ${filter === c ? T.blue : T.border}`,
            background: filter === c ? T.blue : "#fff",
            color: filter === c ? "#fff" : T.text,
            fontSize: 12, fontWeight: filter === c ? 600 : 400, cursor: "pointer",
          }}>
            {c}
            <span style={{ marginLeft: 5, opacity: 0.65, fontSize: 11 }}>
              {c === "All" ? CATALOG.length : CATALOG.filter(p => p.cat === c).length}
            </span>
          </button>
        ))}
      </div>

      {/* Grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
        gap: 14,
      }}>
        {filtered.map(page => (
          <PageCard
            key={page.id}
            page={page}
            result={results[page.id]}
            checking={!!checking[page.id]}
            projectId={activeProject}
            onNavigate={(id) => setPage && setPage(id)}
            onCheck={checkOne}
          />
        ))}
      </div>

      {/* Empty */}
      {filtered.length === 0 && (
        <div style={{
          background: "#fff", border: `1px solid ${T.border}`, borderRadius: 10,
          padding: 60, textAlign: "center", color: T.soft, fontSize: 14,
        }}>
          No pages in this category.
        </div>
      )}
    </div>
  )
}
