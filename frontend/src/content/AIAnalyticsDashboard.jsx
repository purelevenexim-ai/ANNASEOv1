/**
 * AIAnalyticsDashboard.jsx
 * ─────────────────────────────────────────────────────────
 * Deep AI cost analytics for content generation.
 * Shows: total cost / tokens / requests, per-provider breakdown,
 * per-step breakdown, per-article detail, and cross-provider
 * cost comparison ("what would it cost on Claude vs Groq?").
 */
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { T, api, useStore } from "../App"

// ── Helpers ────────────────────────────────────────────────────────────────

function fmt$(n) {
  if (!n) return "$0.00"
  if (n < 0.001) return `$${n.toFixed(6)}`
  if (n < 0.01)  return `$${n.toFixed(4)}`
  return `$${n.toFixed(4)}`
}

function fmtTok(n) {
  if (!n) return "0"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

const TIER_COLOR = {
  free:    { bg: "rgba(52,199,89,0.1)",    text: "#34C759" },
  cheap:   { bg: "rgba(0,122,255,0.1)",    text: "#007AFF" },
  paid:    { bg: "rgba(255,149,0,0.1)",    text: "#FF9500" },
  local:   { bg: "rgba(142,142,147,0.12)", text: "#8E8E93" },
}

function TierBadge({ tier }) {
  const c = TIER_COLOR[tier] || TIER_COLOR.cheap
  return (
    <span style={{
      background: c.bg, color: c.text,
      fontSize: 9, fontWeight: 700, letterSpacing: 0.5,
      padding: "2px 7px", borderRadius: 99, textTransform: "uppercase",
    }}>{tier}</span>
  )
}

// ── Summary Cards ──────────────────────────────────────────────────────────

function SummaryCard({ label, value, sub, accent }) {
  return (
    <div style={{
      background: "#fff", borderRadius: 12, padding: "16px 18px",
      boxShadow: T.cardShadow, flex: "1 1 160px", minWidth: 140,
    }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: accent || T.purple }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: T.gray, marginTop: 1 }}>{sub}</div>}
      <div style={{ fontSize: 11, color: T.textSoft, marginTop: 4 }}>{label}</div>
    </div>
  )
}

// ── Section Header ─────────────────────────────────────────────────────────

function SectionTitle({ children }) {
  return <div style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 10, marginTop: 22 }}>{children}</div>
}

// ── Provider Bar Chart ─────────────────────────────────────────────────────

function ProviderBar({ data, maxCost }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {data.map((row, i) => {
        const pct = maxCost > 0 ? ((row.cost || 0) / maxCost) * 100 : 0
        const isZero = !row.cost || row.cost < 0.000001
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 130, fontSize: 11, color: T.text, fontWeight: 500, flexShrink: 0 }}>
              {row.provider || row.model || "—"}
            </div>
            <div style={{ flex: 1, background: T.grayLight, borderRadius: 4, height: 12, overflow: "hidden" }}>
              <div style={{
                width: `${Math.max(pct, isZero ? 0 : 1)}%`,
                height: "100%", borderRadius: 4,
                background: isZero ? T.grayLight : T.purple,
                transition: "width 0.4s",
              }} />
            </div>
            <div style={{ width: 80, fontSize: 11, color: T.textSoft, textAlign: "right", flexShrink: 0 }}>
              {isZero ? "Free" : fmt$(row.cost)}
            </div>
            <div style={{ width: 55, fontSize: 10, color: T.gray, textAlign: "right", flexShrink: 0 }}>
              {(row.requests || 0)} req
            </div>
            <div style={{ width: 70, fontSize: 10, color: T.gray, textAlign: "right", flexShrink: 0 }}>
              {fmtTok((row.input_tok || 0) + (row.output_tok || 0))} tok
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Table ──────────────────────────────────────────────────────────────────

function Table({ headers, rows, emptyMsg = "No data" }) {
  if (!rows || rows.length === 0) {
    return <div style={{ color: T.gray, fontSize: 12, padding: "12px 0" }}>{emptyMsg}</div>
  }
  const thStyle = { padding: "8px 10px", fontSize: 10, fontWeight: 700, color: T.textSoft, textAlign: "left", borderBottom: `1px solid ${T.border}`, letterSpacing: 0.5, textTransform: "uppercase" }
  const tdStyle = { padding: "8px 10px", fontSize: 12, color: T.text, borderBottom: `1px solid ${T.grayLight}`, verticalAlign: "middle" }
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>{headers.map((h, i) => <th key={i} style={{ ...thStyle, textAlign: h.align || "left" }}>{h.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{ background: ri % 2 === 0 ? "#fff" : "#FAFAFA" }}>
              {headers.map((h, ci) => <td key={ci} style={{ ...tdStyle, textAlign: h.align || "left" }}>{row[ci]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Pricing Table ──────────────────────────────────────────────────────────

function PricingTable({ pricing }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {pricing.map((p, i) => (
        <div key={i} style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "8px 10px",
          background: i % 2 === 0 ? "#fff" : "#FAFAFA",
          borderBottom: `1px solid ${T.grayLight}`,
          borderRadius: i === 0 ? "8px 8px 0 0" : i === pricing.length - 1 ? "0 0 8px 8px" : 0,
        }}>
          <div style={{ width: 200, fontSize: 12, color: T.text, fontWeight: 500 }}>{p.label}</div>
          <TierBadge tier={p.tier} />
          <div style={{ flex: 1 }} />
          {p.is_free ? (
            <span style={{ fontSize: 12, color: "#34C759", fontWeight: 700 }}>FREE</span>
          ) : (
            <>
              <div style={{ fontSize: 11, color: T.textSoft, textAlign: "right", width: 100 }}>
                In: ${p.input_per_1m}/1M
              </div>
              <div style={{ fontSize: 11, color: T.textSoft, textAlign: "right", width: 110 }}>
                Out: ${p.output_per_1m}/1M
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Comparison Panel ───────────────────────────────────────────────────────

function ComparisonPanel({ comparison }) {
  if (!comparison || comparison.length === 0) {
    return <div style={{ color: T.gray, fontSize: 12 }}>Generate some content to see cross-provider cost comparison.</div>
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {comparison.map((item, i) => (
        <div key={i} style={{ background: "#fff", borderRadius: 10, padding: 14, boxShadow: T.cardShadow }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>
              {item.actual_provider}
            </div>
            <div style={{ fontSize: 11, color: T.textSoft }}>
              {fmtTok(item.total_input_tokens)} in + {fmtTok(item.total_output_tokens)} out tokens · {item.total_requests} requests
            </div>
            <div style={{ flex: 1 }} />
            <div style={{ fontSize: 14, fontWeight: 700, color: T.purple }}>
              Actual: {fmt$(item.actual_cost_usd)}
            </div>
          </div>
          {/* Top 5 cheapest alternatives */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
            {item.alternatives.slice(0, 8).map((alt, j) => {
              const savings = item.actual_cost_usd - alt.estimated_cost_usd
              const isCheaper = savings > 0.000001
              const isFree = alt.estimated_cost_usd < 0.000001
              return (
                <div key={j} style={{
                  background: isFree ? "rgba(52,199,89,0.06)" : isCheaper ? "rgba(0,122,255,0.05)" : T.grayLight,
                  borderRadius: 8, padding: "8px 10px",
                  border: `1px solid ${isFree ? "rgba(52,199,89,0.2)" : isCheaper ? "rgba(0,122,255,0.15)" : T.border}`,
                }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: T.textSoft, marginBottom: 2 }}>{alt.label}</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: isFree ? "#34C759" : isCheaper ? T.purple : T.amber }}>
                    {isFree ? "Free" : fmt$(alt.estimated_cost_usd)}
                  </div>
                  {isCheaper && savings > 0.000001 && (
                    <div style={{ fontSize: 9, color: "#34C759", marginTop: 2 }}>
                      Save {fmt$(savings)}
                    </div>
                  )}
                  {!isCheaper && !isFree && alt.estimated_cost_usd > 0.000001 && (
                    <div style={{ fontSize: 9, color: T.amber, marginTop: 2 }}>
                      +{fmt$(Math.abs(savings))} more
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Article Detail Modal ───────────────────────────────────────────────────

function ArticleDetailModal({ projectId, articleId, articleKeyword, onClose }) {
  const { data } = useQuery({
    queryKey: ["article-ai-analytics", projectId, articleId],
    queryFn: () => api.get(`/api/projects/${projectId}/ai-analytics/articles/${articleId}`),
    enabled: !!projectId && !!articleId,
  })

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <div style={{
        background: "#fff", borderRadius: 16, padding: 24, maxWidth: 760, width: "90%",
        maxHeight: "85vh", overflowY: "auto", boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16, gap: 10 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: T.text }}>{data?.keyword || articleKeyword}</div>
            <div style={{ fontSize: 11, color: T.textSoft }}>{articleId}</div>
          </div>
          <button onClick={onClose} style={{ background: T.grayLight, border: "none", borderRadius: 8, padding: "5px 12px", cursor: "pointer", fontSize: 13, color: T.gray }}>✕</button>
        </div>

        {data && (
          <>
            {/* Summary */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
              <SummaryCard label="Total Cost" value={fmt$(data.summary.total_cost_usd)} accent={T.purple} />
              <SummaryCard label="Input Tokens" value={fmtTok(data.summary.total_input_tokens)} accent={T.amber} />
              <SummaryCard label="Output Tokens" value={fmtTok(data.summary.total_output_tokens)} accent="#34C759" />
              <SummaryCard label="Pipeline Steps" value={data.summary.total_steps} />
            </div>

            {/* Steps breakdown */}
            <SectionTitle>Cost Per Pipeline Step</SectionTitle>
            <Table
              headers={[
                { label: "Step" }, { label: "Name" }, { label: "Provider" },
                { label: "Input Tok", align: "right" }, { label: "Output Tok", align: "right" },
                { label: "Cost", align: "right" },
              ]}
              rows={(data.steps || []).map(s => [
                s.step, s.step_name, s.provider || s.model,
                fmtTok(s.input_tokens), fmtTok(s.output_tokens),
                fmt$(s.cost_usd),
              ])}
              emptyMsg="No step data recorded for this article."
            />

            {/* Cross-provider costs for this article */}
            <SectionTitle>What Would This Article Cost on Each Provider?</SectionTitle>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
              {(data.cost_comparison || []).slice(0, 12).map((alt, j) => {
                const isFree = alt.estimated_cost_usd < 0.000001
                return (
                  <div key={j} style={{
                    background: isFree ? "rgba(52,199,89,0.06)" : "#FAFAFA",
                    borderRadius: 8, padding: "8px 10px",
                    border: `1px solid ${isFree ? "rgba(52,199,89,0.2)" : T.border}`,
                  }}>
                    <div style={{ fontSize: 9, fontWeight: 700, color: T.textSoft, marginBottom: 3 }}>{alt.label}</div>
                    <TierBadge tier={alt.tier} />
                    <div style={{ fontSize: 15, fontWeight: 700, color: isFree ? "#34C759" : T.text, marginTop: 4 }}>
                      {isFree ? "Free" : fmt$(alt.estimated_cost_usd)}
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}

        {!data && (
          <div style={{ textAlign: "center", padding: 40, color: T.gray }}>Loading...</div>
        )}
      </div>
    </div>
  )
}

// ── MAIN DASHBOARD ─────────────────────────────────────────────────────────

export default function AIAnalyticsDashboard() {
  const { activeProject } = useStore()
  const [days, setDays] = useState(30)
  const [tab, setTab] = useState("overview")
  const [detailArticle, setDetailArticle] = useState(null)

  const { data: analytics, isLoading } = useQuery({
    queryKey: ["ai-analytics", activeProject, days],
    queryFn: () => api.get(`/api/projects/${activeProject}/ai-analytics?days=${days}`),
    enabled: !!activeProject,
    staleTime: 60_000,
  })

  const { data: pricingData } = useQuery({
    queryKey: ["ai-pricing"],
    queryFn: () => api.get("/api/ai-analytics/pricing"),
    staleTime: 3_600_000, // 1 hour — rarely changes
  })

  const { data: compareData } = useQuery({
    queryKey: ["ai-compare", activeProject, "content_generation"],
    queryFn: () => api.get(`/api/projects/${activeProject}/ai-analytics/compare?task_type=content_generation`),
    enabled: !!activeProject && tab === "compare",
    staleTime: 120_000,
  })

  if (!activeProject) {
    return <div style={{ color: T.textSoft, fontSize: 13, padding: 20 }}>Select a project to view AI analytics.</div>
  }

  const tabBtn = (id, label) => (
    <button
      onClick={() => setTab(id)}
      style={{
        padding: "5px 14px", borderRadius: 99, fontSize: 12, fontWeight: 500,
        border: "none", cursor: "pointer",
        background: tab === id ? T.purple : "transparent",
        color: tab === id ? "#fff" : T.gray,
      }}
    >{label}</button>
  )

  const s = analytics?.summary || {}
  const maxProviderCost = Math.max(...(analytics?.by_provider || []).map(r => r.cost || 0), 0.000001)
  const maxModelCost = Math.max(...(analytics?.by_model || []).map(r => r.cost || 0), 0.000001)
  const maxStepCost = Math.max(...(analytics?.by_step || []).map(r => r.cost || 0), 0.000001)

  return (
    <div style={{ fontFamily: T.bodyFont, padding: "0 0 40px 0" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: T.text }}>AI Cost Analytics</div>
          <div style={{ fontSize: 12, color: T.textSoft, marginTop: 1 }}>
            Exact token counts, costs, and cross-provider comparison
          </div>
        </div>
        {/* Days selector */}
        <div style={{ display: "flex", gap: 4 }}>
          {[7, 30, 90, 365].map(d => (
            <button key={d} onClick={() => setDays(d)} style={{
              padding: "4px 10px", borderRadius: 99, fontSize: 11, fontWeight: 500,
              border: `1px solid ${days === d ? T.purple : T.border}`,
              background: days === d ? T.purpleLight : "transparent",
              color: days === d ? T.purple : T.gray, cursor: "pointer",
            }}>{d}d</button>
          ))}
        </div>
        {/* Tabs */}
        <div style={{ display: "flex", gap: 4, background: T.grayLight, borderRadius: 99, padding: 3 }}>
          {tabBtn("overview", "Overview")}
          {tabBtn("steps", "By Step")}
          {tabBtn("articles", "By Article")}
          {tabBtn("compare", "Compare")}
          {tabBtn("pricing", "Pricing")}
        </div>
      </div>

      {isLoading && (
        <div style={{ textAlign: "center", padding: 40, color: T.gray }}>Loading analytics...</div>
      )}

      {/* ── OVERVIEW TAB ── */}
      {tab === "overview" && analytics && (
        <>
          {/* Summary cards */}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
            <SummaryCard label={`Total Cost (${days}d)`} value={fmt$(s.total_cost_usd)} accent={T.purple} />
            <SummaryCard label="Total Requests" value={(s.total_requests || 0).toLocaleString()} accent={T.amber} />
            <SummaryCard label="Total Tokens" value={fmtTok(s.total_tokens)} sub={`In: ${fmtTok(s.total_input_tokens)} · Out: ${fmtTok(s.total_output_tokens)}`} accent="#34C759" />
            <SummaryCard
              label="Cost / Article"
              value={fmt$((analytics?.by_article || []).length > 0 ? (s.total_cost_usd || 0) / (analytics.by_article.length) : 0)}
              sub={`${(analytics?.by_article || []).length} articles`}
            />
          </div>

          {/* By provider */}
          <SectionTitle>Cost by Provider</SectionTitle>
          {(analytics.by_provider || []).length === 0 ? (
            <div style={{ color: T.gray, fontSize: 12 }}>No data yet. Generate some content to track AI usage.</div>
          ) : (
            <div style={{ background: "#fff", borderRadius: 10, padding: 16, boxShadow: T.cardShadow }}>
              <ProviderBar data={analytics.by_provider} maxCost={maxProviderCost} />
            </div>
          )}

          {/* By model */}
          <SectionTitle>Cost by Model</SectionTitle>
          {(analytics.by_model || []).length > 0 && (
            <div style={{ background: "#fff", borderRadius: 10, padding: 16, boxShadow: T.cardShadow }}>
              <ProviderBar data={analytics.by_model} maxCost={maxModelCost} />
            </div>
          )}

          {/* By task type */}
          <SectionTitle>Cost by Task Type</SectionTitle>
          <Table
            headers={[
              { label: "Task Type" }, { label: "Requests", align: "right" },
              { label: "Input Tok", align: "right" }, { label: "Output Tok", align: "right" }, { label: "Cost", align: "right" },
            ]}
            rows={(analytics.by_task_type || []).map(r => [
              r.task_type || "—",
              r.requests,
              fmtTok(r.input_tok),
              fmtTok(r.output_tok),
              fmt$(r.cost),
            ])}
            emptyMsg="No task data recorded yet."
          />

          {/* Recent log */}
          <SectionTitle>Recent AI Calls</SectionTitle>
          <div style={{ background: "#fff", borderRadius: 10, boxShadow: T.cardShadow, overflow: "hidden" }}>
            <Table
              headers={[
                { label: "Time" }, { label: "Provider" }, { label: "Step" },
                { label: "In Tok", align: "right" }, { label: "Out Tok", align: "right" }, { label: "Cost", align: "right" },
              ]}
              rows={(analytics.recent || []).map(r => [
                r.created_at ? new Date(r.created_at).toLocaleTimeString() : "—",
                r.provider || r.model || "—",
                r.step_name || r.purpose || "—",
                fmtTok(r.input_tokens),
                fmtTok(r.output_tokens),
                fmt$(r.cost_usd),
              ])}
              emptyMsg="No recent AI calls."
            />
          </div>
        </>
      )}

      {/* ── STEPS TAB ── */}
      {tab === "steps" && analytics && (
        <>
          <SectionTitle>Cost Per Pipeline Step (content generation, {days}d)</SectionTitle>
          {(analytics.by_step || []).length === 0 ? (
            <div style={{ color: T.gray, fontSize: 12 }}>No step data yet. Generate an article to see per-step breakdown.</div>
          ) : (
            <>
              <div style={{ background: "#fff", borderRadius: 10, padding: 16, boxShadow: T.cardShadow, marginBottom: 12 }}>
                <ProviderBar data={analytics.by_step.map(r => ({ ...r, provider: r.step_name || `Step ${r.step}` }))} maxCost={maxStepCost} />
              </div>
              <div style={{ background: "#fff", borderRadius: 10, boxShadow: T.cardShadow, overflow: "hidden" }}>
                <Table
                  headers={[
                    { label: "#" }, { label: "Step Name" }, { label: "Provider" }, { label: "Requests", align: "right" },
                    { label: "Input Tok", align: "right" }, { label: "Output Tok", align: "right" }, { label: "Cost", align: "right" },
                  ]}
                  rows={(analytics.by_step || []).map(r => [
                    r.step, r.step_name || "—", r.provider || "—",
                    r.requests, fmtTok(r.input_tok), fmtTok(r.output_tok), fmt$(r.cost),
                  ])}
                />
              </div>
            </>
          )}
        </>
      )}

      {/* ── ARTICLES TAB ── */}
      {tab === "articles" && analytics && (
        <>
          <SectionTitle>Most Expensive Articles ({days}d)</SectionTitle>
          {(analytics.by_article || []).length === 0 ? (
            <div style={{ color: T.gray, fontSize: 12 }}>No article data yet.</div>
          ) : (
            <div style={{ background: "#fff", borderRadius: 10, boxShadow: T.cardShadow, overflow: "hidden" }}>
              <Table
                headers={[
                  { label: "Keyword" }, { label: "Status" }, { label: "Requests", align: "right" },
                  { label: "Input Tok", align: "right" }, { label: "Output Tok", align: "right" },
                  { label: "Cost", align: "right" }, { label: "" },
                ]}
                rows={(analytics.by_article || []).map(r => [
                  r.keyword || r.article_id || "—",
                  r.status || "—",
                  r.requests,
                  fmtTok(r.input_tok),
                  fmtTok(r.output_tok),
                  fmt$(r.cost),
                  <button
                    key="detail"
                    onClick={() => setDetailArticle({ id: r.article_id, keyword: r.keyword })}
                    style={{
                      padding: "3px 10px", borderRadius: 6, fontSize: 11,
                      background: T.purpleLight, color: T.purple,
                      border: "none", cursor: "pointer", fontWeight: 600,
                    }}
                  >Detail</button>,
                ])}
              />
            </div>
          )}
        </>
      )}

      {/* ── COMPARE TAB ── */}
      {tab === "compare" && (
        <>
          <SectionTitle>Cross-Provider Cost Comparison</SectionTitle>
          <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 12 }}>
            Shows what your actual token usage (input + output) would have cost on every provider.
          </div>
          {compareData ? (
            <ComparisonPanel comparison={compareData.comparison} />
          ) : (
            <div style={{ color: T.gray, fontSize: 12 }}>Loading comparison...</div>
          )}
        </>
      )}

      {/* ── PRICING TAB ── */}
      {tab === "pricing" && (
        <>
          <SectionTitle>Provider Pricing Reference</SectionTitle>
          <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 12 }}>
            Current pricing per 1M tokens used in ANNA SEO. Prices are approximate and may vary.
          </div>
          {pricingData ? (
            <div style={{ background: "#fff", borderRadius: 10, boxShadow: T.cardShadow, overflow: "hidden" }}>
              <PricingTable pricing={pricingData.pricing} />
            </div>
          ) : (
            <div style={{ color: T.gray, fontSize: 12 }}>Loading pricing...</div>
          )}
        </>
      )}

      {/* Article Detail Modal */}
      {detailArticle && (
        <ArticleDetailModal
          projectId={activeProject}
          articleId={detailArticle.id}
          articleKeyword={detailArticle.keyword}
          onClose={() => setDetailArticle(null)}
        />
      )}
    </div>
  )
}
