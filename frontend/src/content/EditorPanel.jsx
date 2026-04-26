import { useState, useRef, useCallback, useEffect } from "react"
import { T, api, Badge, Btn } from "../App"
import TiptapEditor from "../components/TiptapEditor"
import { PipelineLogsView } from "./PipelinePanel"
import HumanizePanel from "./HumanizePanel"

// ── Status helpers ─────────────────────────────────────────────────────────────
const STATUS_COLOR = {
  draft: "gray", generating: "amber", review: "purple",
  approved: "teal", publishing: "amber", published: "teal", failed: "red",
}

// ── Story view: renders article body with light-green plot/snippet highlights ─
function StoryView({ articleId, body }) {
  const [score, setScore] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null)
    api.get(`/api/content/${articleId}/story-score`)
      .then(d => { if (!cancelled) setScore(d) })
      .catch(e => { if (!cancelled) setError(e?.message || "Failed to load story score") })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [articleId])

  // Build a regex-safe escape
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")

  // Highlight plot/snippet sentences in the body HTML
  let highlighted = body || ""
  if (score?.highlights?.length) {
    score.highlights.forEach(h => {
      if (!h.sentence) return
      const text = h.sentence.trim().slice(0, 200)
      // Take a substring (first 50 chars) for matching to avoid HTML interference
      const probe = text.slice(0, 60)
      try {
        const re = new RegExp(`(${esc(probe)}[^<]*?\\.)`, "i")
        const bg = h.kind === "plot" ? "#bbf7d0" : h.kind === "snippet" ? "#dcfce7" : "#f0fdf4"
        const border = h.kind === "plot" ? "#16a34a" : "#86efac"
        highlighted = highlighted.replace(re, (m) =>
          `<mark style="background:${bg};border-left:3px solid ${border};padding:1px 4px;border-radius:3px;display:inline" data-story-kind="${h.kind}">${m}</mark>`
        )
      } catch { /* skip bad regex */ }
    })
  }

  const totalScore = score?.score ?? 0
  const scoreColor = totalScore >= 9 ? "#16a34a" : totalScore >= 7 ? "#65a30d" : totalScore >= 5 ? "#d97706" : "#dc2626"

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Header strip with score */}
      <div style={{
        display: "flex", alignItems: "center", gap: 16, padding: "10px 16px",
        background: "#f0fdf4", borderBottom: "1px solid #bbf7d0", flexShrink: 0,
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#166534", letterSpacing: 0.5 }}>STORY PLOT INTEGRATION</div>
        <div style={{ fontSize: 22, fontWeight: 800, color: scoreColor, lineHeight: 1 }}>
          {loading ? "…" : `${totalScore}`}<span style={{ fontSize: 12, fontWeight: 500, color: "#666" }}>/10</span>
        </div>
        {score?.breakdown && (
          <div style={{ display: "flex", gap: 8, fontSize: 10 }}>
            {Object.entries(score.breakdown).map(([dim, v]) => (
              <div key={dim} title={v.notes} style={{
                padding: "3px 8px", borderRadius: 6,
                background: v.score >= v.max * 0.7 ? "#dcfce7" : v.score >= v.max * 0.4 ? "#fef3c7" : "#fecaca",
                color: "#374151", fontWeight: 600,
              }}>
                {dim.replace(/_/g, " ")}: {v.score}/{v.max}
              </div>
            ))}
          </div>
        )}
        <div style={{ marginLeft: "auto", fontSize: 10, color: "#166534", fontWeight: 500 }}>
          <span style={{ display: "inline-block", width: 10, height: 10, background: "#bbf7d0", borderRadius: 2, marginRight: 4, verticalAlign: "middle" }}></span>
          plot lines
          <span style={{ display: "inline-block", width: 10, height: 10, background: "#dcfce7", borderRadius: 2, margin: "0 4px 0 10px", verticalAlign: "middle" }}></span>
          brand snippets
        </div>
      </div>

      {/* Issues bar (if any) */}
      {score?.issues?.length > 0 && (
        <div style={{ padding: "6px 16px", background: "#fef3c7", borderBottom: "1px solid #fcd34d", fontSize: 11, color: "#92400e", flexShrink: 0 }}>
          <strong>Issues:</strong> {score.issues.join(" · ")}
        </div>
      )}

      {/* Article body with highlights */}
      <div style={{
        flex: 1, overflow: "auto", padding: "20px 32px",
        fontFamily: T.bodyFont, fontSize: 15, lineHeight: 1.7, color: "#1f2937",
      }}>
        {error && <div style={{ color: T.red, padding: 12 }}>Failed to load story score: {error}</div>}
        <div dangerouslySetInnerHTML={{ __html: highlighted }} className="story-view-body" />
      </div>
    </div>
  )
}

function DetectorView({ body, detectorData, loading, onRemovePassage }) {
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  let highlighted = body || ""

  if (detectorData?.flagged_passages?.length) {
    detectorData.flagged_passages.forEach(item => {
      const snippet = (item.snippet || "").trim()
      if (!snippet) return
      const probe = snippet.slice(0, 60)
      try {
        const re = new RegExp(`(${esc(probe)}[^<]*?[.!?]?)`, "i")
        highlighted = highlighted.replace(re, (m) =>
          `<mark style="background:#fee2e2;border-left:3px solid #dc2626;padding:1px 4px;border-radius:3px;display:inline" data-detector-kind="${item.issue_type}">${m}</mark>`
        )
      } catch {}
    })
  }

  const scores = detectorData?.detector_scores || {}
  const aiScore = detectorData?.ai_score ?? scores.combined_ai_score ?? 0
  const risk = detectorData?.risk_level || "unknown"
  const riskBg = risk === "high" ? "#fef2f2" : risk === "medium" ? "#fff7ed" : risk === "low" ? "#fefce8" : "#f0fdf4"
  const riskColor = risk === "high" ? "#dc2626" : risk === "medium" ? "#ea580c" : risk === "low" ? "#a16207" : "#15803d"

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px", background: "#fff1f2", borderBottom: "1px solid #fecdd3", flexShrink: 0 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#9f1239", letterSpacing: 0.5 }}>DETECTOR REVIEW</div>
        <div style={{ fontSize: 22, fontWeight: 800, color: riskColor, lineHeight: 1 }}>
          {loading ? "…" : `${aiScore}`}<span style={{ fontSize: 12, fontWeight: 500, color: "#666" }}>/100</span>
        </div>
        <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: riskColor, background: riskBg, borderRadius: 99, padding: "3px 10px" }}>{risk}</div>
        <div style={{ display: "flex", gap: 8, fontSize: 10 }}>
          <div style={{ padding: "3px 8px", borderRadius: 6, background: "#fff", border: "1px solid #fecaca" }}>GPTZero: {scores.gptzero_style ?? 0}</div>
          <div style={{ padding: "3px 8px", borderRadius: 6, background: "#fff", border: "1px solid #fecaca" }}>Turnitin: {scores.turnitin_style ?? 0}</div>
          <div style={{ padding: "3px 8px", borderRadius: 6, background: "#fff", border: "1px solid #fecaca" }}>Originality: {scores.originality_style ?? 0}</div>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 10, color: "#9f1239", fontWeight: 500 }}>
          <span style={{ display: "inline-block", width: 10, height: 10, background: "#fee2e2", borderRadius: 2, marginRight: 4, verticalAlign: "middle", border: "1px solid #fca5a5" }}></span>
          dehumanized areas highlighted
        </div>
      </div>

      {!!detectorData?.flagged_passages?.length && (
        <div style={{ padding: "8px 16px", background: "#fff", borderBottom: "1px solid #fecdd3", display: "flex", flexDirection: "column", gap: 6, maxHeight: 180, overflow: "auto", flexShrink: 0 }}>
          {detectorData.flagged_passages.map((item, idx) => (
            <div key={`${item.issue_type}-${idx}`} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 11, color: T.text }}>
              <span style={{ fontSize: 9, fontWeight: 700, color: "#fff", background: item.severity === "high" ? "#dc2626" : "#ea580c", borderRadius: 4, padding: "2px 5px", textTransform: "uppercase", marginTop: 1 }}>{item.severity}</span>
              <div style={{ flex: 1 }}>
                <div style={{ color: T.text }}>{item.reason}</div>
                <div style={{ color: T.textSoft, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.snippet}</div>
              </div>
              {item.removable && (
                <button onClick={() => onRemovePassage?.(item)} style={{ padding: "4px 8px", borderRadius: 6, fontSize: 10, fontWeight: 600, border: "1px solid #fca5a5", background: "#fff", color: "#b91c1c", cursor: "pointer" }}>
                  Remove
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={{ flex: 1, overflow: "auto", padding: "20px 32px", fontFamily: T.bodyFont, fontSize: 15, lineHeight: 1.7, color: "#1f2937" }}>
        <div dangerouslySetInnerHTML={{ __html: highlighted || "<p><em>No content yet.</em></p>" }} />
      </div>
    </div>
  )
}

// ── AI Review panel ────────────────────────────────────────────────────────────
const SEV_COLORS = { critical: "#dc2626", high: "#ea580c", medium: "#d97706", low: "#9ca3af" }

const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3 }

function ReviewPanel({ data, loading, onRunReview, onFixIssues, fixing, onFixRule, fixingRule, fixStats }) {
  const pct = data?.percentage ?? data?.score ?? null
  const scoreColor = pct === null ? T.gray : pct >= 70 ? T.teal : pct >= 45 ? T.amber : T.red
  const [expandedCat, setExpandedCat] = useState(null)
  const [showAllIssues, setShowAllIssues] = useState(false)
  const [fixProvider, setFixProvider] = useState("auto")

  const categories = data?.categories ? Object.entries(data.categories) : []
  const issues = (data?.issues || []).slice().sort((a, b) =>
    (SEV_ORDER[a.severity] ?? 4) - (SEV_ORDER[b.severity] ?? 4)
  )

  // Group issues by category for bar expansion
  const issuesByCat = {}
  issues.forEach(iss => {
    const cat = iss.category || "general"
    if (!issuesByCat[cat]) issuesByCat[cat] = []
    issuesByCat[cat].push(iss)
  })

  const criticalCount = issues.filter(i => i.severity === "critical").length
  const highCount = issues.filter(i => i.severity === "high").length
  const shownIssues = showAllIssues ? issues : issues.filter(i => i.severity === "critical" || i.severity === "high")

  return (
    <div style={{ padding: "16px 14px", height: "100%", overflowY: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>Content Score</div>

      {/* Score dial */}
      {pct !== null ? (
        <div style={{ textAlign: "center", padding: "12px 0" }}>
          <div style={{ fontSize: 54, fontWeight: 700, color: scoreColor, lineHeight: 1, letterSpacing: -2 }}>
            {pct}
          </div>
          <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4 }}>%{data?.total_earned ? ` · ${data.total_earned}/${data.max_possible} pts` : ""}</div>
          <div style={{
            marginTop: 8, fontSize: 10, fontWeight: 600, color: scoreColor,
            background: `${scoreColor}15`, borderRadius: 99, padding: "2px 10px", display: "inline-block",
          }}>
            {pct >= 80 ? "Excellent" : pct >= 65 ? "Good" : pct >= 45 ? "Needs Improvement" : "Poor"}
          </div>
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: "12px 0" }}>
          <div style={{ fontSize: 38, fontWeight: 700, color: T.gray, lineHeight: 1 }}>—</div>
          <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4 }}>Not reviewed yet</div>
        </div>
      )}

      {/* 8-category breakdown bars */}
      {categories.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {categories.map(([key, cat]) => {
            const pct = cat.max > 0 ? Math.round((cat.score / cat.max) * 100) : 0
            const barColor = pct >= 70 ? T.teal : pct >= 45 ? T.amber : "#dc2626"
            const catIssues = issuesByCat[key] || []
            const isExpanded = expandedCat === key
            return (
              <div key={key}>
                <div
                  style={{ display: "flex", justifyContent: "space-between", marginBottom: 3, cursor: catIssues.length > 0 ? "pointer" : "default" }}
                  onClick={() => catIssues.length > 0 && setExpandedCat(isExpanded ? null : key)}
                >
                  <span style={{ fontSize: 10, fontWeight: 500, color: T.text }}>
                    {cat.label || key}
                    {catIssues.length > 0 && <span style={{ color: T.textSoft, marginLeft: 4 }}>({catIssues.length})</span>}
                  </span>
                  <span style={{ fontSize: 10, color: T.textSoft }}>{cat.score} / {cat.max}</span>
                </div>
                <div style={{ height: 5, background: T.grayLight, borderRadius: 99 }}>
                  <div style={{
                    height: 5, borderRadius: 99,
                    width: `${pct}%`,
                    background: barColor,
                    transition: "width 0.6s ease",
                  }} />
                </div>
                {/* Expanded issues for this category */}
                {isExpanded && catIssues.length > 0 && (
                  <div style={{ marginTop: 6, paddingLeft: 4, display: "flex", flexDirection: "column", gap: 5 }}>
                    {catIssues.map((iss, i) => (
                      <div key={i} style={{ fontSize: 10, color: T.textSoft, lineHeight: 1.5, display: "flex", gap: 6, alignItems: "flex-start" }}>
                        <span style={{
                          fontSize: 8, fontWeight: 700, color: "#fff", flexShrink: 0, textTransform: "uppercase",
                          background: SEV_COLORS[iss.severity] || SEV_COLORS.medium,
                          borderRadius: 3, padding: "1px 4px", lineHeight: "14px", marginTop: 1,
                        }}>{iss.severity?.[0]?.toUpperCase()}</span>
                        <div>
                          <div style={{ color: T.text }}>{iss.description}</div>
                          {iss.fix && <div style={{ color: T.teal, fontSize: 9, marginTop: 1 }}>→ {iss.fix}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* AI Detection Risk Badge */}
      {data?.ai_detection_risk && data.ai_detection_risk !== "unknown" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{
              fontSize: 9, fontWeight: 700, padding: "2px 10px", borderRadius: 99,
              textTransform: "uppercase", letterSpacing: 0.5,
              background: data.ai_detection_risk === "critical" ? "#fef2f2" :
                          data.ai_detection_risk === "high" ? "#fff7ed" :
                          data.ai_detection_risk === "medium" ? "#fefce8" : "#f0fdf4",
              color: data.ai_detection_risk === "critical" ? "#dc2626" :
                     data.ai_detection_risk === "high" ? "#ea580c" :
                     data.ai_detection_risk === "medium" ? "#ca8a04" : "#16a34a",
              border: `1px solid ${data.ai_detection_risk === "critical" ? "#fca5a5" : data.ai_detection_risk === "high" ? "#fdba74" : data.ai_detection_risk === "medium" ? "#fde047" : "#86efac"}`,
            }}>
              AI Risk: {data.ai_detection_risk}
            </span>
          </div>
          {data.ai_detection_signals?.length > 0 && (
            <div style={{ fontSize: 9, color: T.textSoft, lineHeight: 1.5, paddingLeft: 2 }}>
              {data.ai_detection_signals.slice(0, 4).join(" · ")}
            </div>
          )}
        </div>
      )}

      {/* Critical/High Issues list — always visible */}
      <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 10 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: T.text }}>
            Issues
            {criticalCount > 0 && (
              <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 700, color: "#dc2626",
                background: "#fef2f2", borderRadius: 99, padding: "1px 6px" }}>
                {criticalCount} critical
              </span>
            )}
            {highCount > 0 && (
              <span style={{ marginLeft: 4, fontSize: 9, fontWeight: 700, color: "#ea580c",
                background: "#fff7ed", borderRadius: 99, padding: "1px 6px" }}>
                {highCount} high
              </span>
            )}
          </div>
          {issues.length > shownIssues.length && (
            <button onClick={() => setShowAllIssues(v => !v)} style={{
              fontSize: 9, color: T.purple, background: "none", border: "none",
              cursor: "pointer", fontWeight: 500, padding: 0,
            }}>
              {showAllIssues ? "Show critical only" : `+${issues.length - shownIssues.length} more`}
            </button>
          )}
        </div>

        {issues.length === 0 ? (
          <div style={{ fontSize: 10, color: T.textSoft, textAlign: "center", padding: "8px 0" }}>
            {data ? "All rules passed or run review to see issues" : "Run review to see issues"}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {shownIssues.map((iss, i) => {
              const ruleId = iss.rule || iss.rule_id || iss.description?.match(/^\[([A-Z0-9.]+)\]/)?.[1] || ""
              const isFixing = fixingRule === ruleId
              return (
              <div key={i} style={{
                display: "flex", gap: 6, alignItems: "flex-start",
                fontSize: 10, lineHeight: 1.45,
                padding: "5px 7px", borderRadius: 7,
                background: iss.severity === "critical" ? "#fef2f2" :
                            iss.severity === "high" ? "#fff7ed" :
                            iss.severity === "medium" ? "#fefce8" : "#f9f9f9",
              }}>
                <span style={{
                  fontSize: 8, fontWeight: 700, color: "#fff", flexShrink: 0,
                  textTransform: "uppercase",
                  background: SEV_COLORS[iss.severity] || SEV_COLORS.medium,
                  borderRadius: 3, padding: "1px 4px", lineHeight: "14px", marginTop: 1,
                }}>{iss.severity?.[0]?.toUpperCase()}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ color: T.text, fontWeight: 500 }}>{iss.description}</div>
                  {iss.fix && (
                    <div style={{ color: T.teal, fontSize: 9, marginTop: 2 }}>→ {iss.fix}</div>
                  )}
                </div>
                {ruleId && onFixRule && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onFixRule(ruleId, iss) }}
                    disabled={!!fixingRule}
                    style={{
                      flexShrink: 0, fontSize: 8, fontWeight: 600, padding: "2px 7px",
                      borderRadius: 4, border: "1px solid #6366f1", cursor: fixingRule ? "wait" : "pointer",
                      background: isFixing ? "#6366f1" : "#fff", color: isFixing ? "#fff" : "#6366f1",
                      opacity: fixingRule && !isFixing ? 0.4 : 1, marginTop: 1,
                    }}
                  >
                    {isFixing ? "Fixing…" : "Fix"}
                  </button>
                )}
              </div>
              )
            })}
          </div>
        )}
      </div>

      {/* AI Verdict */}
      {data?.verdict && (
        <div style={{ background: "#F2F2F7", borderRadius: 8, padding: "8px 10px" }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: T.purple, marginBottom: 3, textTransform: "uppercase", letterSpacing: 0.5 }}>AI Verdict</div>
          <div style={{ fontSize: 11, color: T.textSoft, lineHeight: 1.6 }}>{data.verdict}</div>
        </div>
      )}

      {/* AI Provider selector for fixing */}
      {issues.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 9, color: T.textSoft, fontWeight: 600, whiteSpace: "nowrap" }}>Fix with:</span>
          <select value={fixProvider} onChange={e => setFixProvider(e.target.value)}
            style={{ flex: 1, fontSize: 10, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.border}`, background: "#fff", cursor: "pointer" }}>
            <option value="auto">Auto (Groq → Gemini → Ollama)</option>
            <option value="groq">⚡ Groq</option>
            <option value="gemini_paid">💎 Gemini Paid</option>
            <option value="gemini_free">💎 Gemini Free</option>
            <option value="anthropic">🧠 Claude</option>
            <option value="openai_paid">🤖 ChatGPT</option>
            <option value="ollama">🦙 Ollama</option>
          </select>
        </div>
      )}

      {/* Fix Progress Stats */}
      {fixStats && (fixing || fixStats.applied > 0 || fixStats.failed > 0) && (
        <div style={{
          display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap",
          padding: "6px 10px", borderRadius: 8,
          background: fixing ? "#eff6ff" : fixStats.failed > 0 ? "#fff7ed" : "#f0fdf4",
          border: `1px solid ${fixing ? "#bfdbfe" : fixStats.failed > 0 ? "#fed7aa" : "#bbf7d0"}`,
        }}>
          {fixing && (
            <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#1d4ed8", fontWeight: 600 }}>
              <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "#3b82f6", animation: "pulse 1s infinite" }} />
              Running {fixStats.running}
            </div>
          )}
          {fixStats.applied > 0 && (
            <div style={{ fontSize: 10, color: "#15803d", fontWeight: 600 }}>
              ✓ Applied {fixStats.applied}
            </div>
          )}
          {fixStats.failed > 0 && (
            <div style={{ fontSize: 10, color: "#c2410c", fontWeight: 600 }}>
              ✗ Failed {fixStats.failed}
            </div>
          )}
          {!fixing && fixStats.total > 0 && (
            <div style={{ fontSize: 9, color: T.textSoft, marginLeft: "auto" }}>
              of {Math.min(fixStats.total, 8)} attempted
            </div>
          )}
        </div>
      )}

      {/* Fix issues button — always shown, greyed if no issues */}
      <Btn
        onClick={() => issues.length > 0 ? onFixIssues(issues, fixProvider) : onRunReview()}
        variant="primary"
        disabled={fixing || (loading && issues.length === 0)}
        style={{
          width: "100%",
          background: issues.length > 0 ? "#dc2626" : undefined,
          borderColor: issues.length > 0 ? "#dc2626" : undefined,
          opacity: issues.length === 0 ? 0.5 : 1,
        }}
      >
        {fixing
          ? `Fixing Issues… (${fixStats?.running ?? "?"}/${Math.min(fixStats?.total ?? 0, 8)} running)`
          : issues.length > 0
            ? `Fix All ${issues.length} Issues with AI`
            : "Run Review to Find Issues"}
      </Btn>

      <Btn
        onClick={onRunReview}
        variant="primary"
        disabled={loading}
        style={{ width: "100%" }}
      >
        {loading ? "Analyzing..." : pct !== null ? "Re-Run Review" : "Run Review"}
      </Btn>
    </div>
  )
}

// ── Per-rule compliance panel ──────────────────────────────────────────────────
const PILLAR_ICONS = {
  golden: "⭐", strategic: "🎯", eeat: "🛡️", structure: "🏗️", linguistic: "✍️",
  visual: "📊", data: "📈", engagement: "💬", tech_seo: "⚙️", topic_authority: "📚", ai_detection: "🤖",
}

function RulesPanel({ articleId, data, sectionScores, loading, onReAnalyze }) {
  const [expandedPillar, setExpandedPillar] = useState(null)
  const percentage = data?.percentage ?? null
  const pillars = data?.pillars || []
  const summary = data?.summary || {}
  const scoreColor = percentage === null ? T.gray : percentage >= 70 ? T.teal : percentage >= 45 ? T.amber : "#dc2626"

  return (
    <div style={{ padding: "16px 14px", height: "100%", overflowY: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>Rules Compliance</div>

      {/* Score */}
      {percentage !== null ? (
        <div style={{ textAlign: "center", padding: "8px 0" }}>
          <div style={{ fontSize: 44, fontWeight: 700, color: scoreColor, lineHeight: 1, letterSpacing: -2 }}>
            {percentage}%
          </div>
          <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4 }}>
            {data?.total_earned ?? 0} / {data?.max_possible ?? 0} pts · {summary.passed_count ?? 0}/{summary.total_rules ?? 0} rules
          </div>
          <div style={{
            marginTop: 6, fontSize: 10, fontWeight: 600, color: scoreColor,
            background: `${scoreColor}15`, borderRadius: 99, padding: "2px 10px", display: "inline-block",
          }}>
            {percentage >= 80 ? "Excellent" : percentage >= 65 ? "Good" : percentage >= 45 ? "Needs Work" : "Poor"}
          </div>
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: "8px 0" }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: T.gray, lineHeight: 1 }}>—</div>
          <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4 }}>Not scored yet</div>
        </div>
      )}

      {/* Pillar breakdown */}
      {pillars.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {pillars.map(p => {
            const pct = p.max > 0 ? Math.round((p.earned / p.max) * 100) : 0
            const barColor = pct >= 70 ? T.teal : pct >= 45 ? T.amber : "#dc2626"
            const isExpanded = expandedPillar === p.id
            const icon = PILLAR_ICONS[p.id] || "📋"
            return (
              <div key={p.id}>
                <div
                  style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3, cursor: "pointer" }}
                  onClick={() => setExpandedPillar(isExpanded ? null : p.id)}
                >
                  <span style={{ fontSize: 11, flexShrink: 0 }}>{icon}</span>
                  <span style={{ fontSize: 10, fontWeight: 500, color: T.text, flex: 1 }}>
                    {p.name}
                    <span style={{ color: T.textSoft, marginLeft: 4, fontWeight: 400 }}>
                      {p.passed}/{p.total}
                    </span>
                  </span>
                  <span style={{ fontSize: 10, color: T.textSoft }}>{p.earned}/{p.max}</span>
                  <span style={{ fontSize: 9, color: T.textSoft }}>{isExpanded ? "▾" : "▸"}</span>
                </div>
                <div style={{ height: 4, background: T.grayLight, borderRadius: 99 }}>
                  <div style={{
                    height: 4, borderRadius: 99, width: `${pct}%`,
                    background: barColor, transition: "width 0.5s ease",
                  }} />
                </div>
                {/* Expanded rules for this pillar */}
                {isExpanded && p.rules && (
                  <div style={{ marginTop: 6, paddingLeft: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                    {p.rules.map(r => (
                      <div key={r.id} style={{
                        display: "flex", alignItems: "flex-start", gap: 6,
                        fontSize: 10, color: T.textSoft, lineHeight: 1.5,
                        padding: "3px 6px", borderRadius: 6,
                        background: r.passed ? `${T.teal}08` : "#fef2f208",
                      }}>
                        <span style={{
                          fontSize: 10, fontWeight: 700, flexShrink: 0,
                          color: r.passed ? T.teal : "#dc2626",
                        }}>
                          {r.passed ? "✓" : "✗"}
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ color: T.text, fontWeight: 500 }}>
                            <span style={{ color: T.textSoft, fontWeight: 400 }}>[{r.id}]</span> {r.name}
                            <span style={{ color: T.textSoft, fontWeight: 400, marginLeft: 4 }}>{r.points}pt</span>
                          </div>
                          <div style={{ fontSize: 9, color: r.passed ? T.textSoft : "#dc2626", marginTop: 1 }}>
                            {r.detail}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Section scores */}
      {sectionScores?.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: T.text, marginBottom: 2 }}>Section Quality</div>
          {sectionScores.map((s, i) => {
            const sc = s.score ?? 100
            const barColor = sc >= 70 ? T.teal : sc >= 45 ? T.amber : "#dc2626"
            const failures = s.contract_failures || []
            return (
              <div key={i} style={{ marginBottom: 2 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                  <span style={{ fontSize: 10, color: T.text, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 160 }}>
                    {s.heading || `Section ${i + 1}`}
                  </span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: barColor, flexShrink: 0 }}>{sc}%</span>
                </div>
                <div style={{ height: 3, background: T.grayLight, borderRadius: 99 }}>
                  <div style={{ height: 3, borderRadius: 99, width: `${sc}%`, background: barColor, transition: "width 0.5s ease" }} />
                </div>
                {failures.map((f, j) => (
                  <div key={j} style={{ fontSize: 9, color: "#dc2626", marginTop: 2, paddingLeft: 4 }}>
                    ⚠ {f.detail}
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      )}

      {/* Re-analyze button */}
      <Btn
        onClick={onReAnalyze}
        variant="primary"
        disabled={loading}
        style={{ width: "100%", marginTop: "auto" }}
      >
        {loading ? "Analyzing..." : percentage !== null ? "Re-Analyze Rules" : "Analyze Rules"}
      </Btn>
    </div>
  )
}


// ── EditorPanel ────────────────────────────────────────────────────────────────
// Props:
// article — the selected article object
// projectId
// onStatusChange — called when status mutates (triggers article list refresh)

export default function EditorPanel({ article, projectId, onStatusChange }) {
  // ── Editor state ───────────────────────────────────────────────────────────
  const [viewMode, setViewMode] = useState("editor") // "editor" | "html" | "logs" | "story"
  const [htmlContent, setHtmlContent] = useState("")
  const [isDirty, setIsDirty] = useState(false)
  const [reviewData, setReviewData] = useState(null)
  const [reviewing, setReviewing] = useState(false)
  const [rewriting, setRewriting] = useState(false)
  const [rewriteInstruction, setRewriteInstruction] = useState("")
  const [showInstruction, setShowInstruction] = useState(false)
  const [rulesData, setRulesData] = useState(null)
  const [sectionScores, setSectionScores] = useState([])
  const [analyzingRules, setAnalyzingRules] = useState(false)
  const [logs, setLogs] = useState(null)
  const [detectorData, setDetectorData] = useState(null)
  const [detectorLoading, setDetectorLoading] = useState(false)

  // Bug #9 — mutual exclusion: one panel open at a time
  const [openPanel, setOpenPanel] = useState(null) // "review" | "rules" | "humanize" | null
  const reviewOpen = openPanel === "review"
  const rulesOpen = openPanel === "rules"
  const humanizeOpen = openPanel === "humanize"

  const toggleReview = () => setOpenPanel(p => p === "review" ? null : "review")
  const toggleRules = () => {
    if (openPanel !== "rules") fetchRules()
    setOpenPanel(p => p === "rules" ? null : "rules")
  }
  const toggleHumanize = () => setOpenPanel(p => p === "humanize" ? null : "humanize")

  // Fix state
  const [fixing, setFixing] = useState(false)
  const [fixingRule, setFixingRule] = useState(null)
  const [ruleDiff, setRuleDiff] = useState(null)
  const [fixStats, setFixStats] = useState(null)

  const [articleCost, setArticleCost] = useState(null)

  // Refs
  const editorRef = useRef(null)
  const saveTimer = useRef(null)

  // Reset editor state when selecting a new article
  useEffect(() => {
    setViewMode("editor")
    setHtmlContent("")
    setIsDirty(false)
    setReviewData(null)
    setRulesData(null)
    setSectionScores([])
    setOpenPanel(null)
    setLogs(null)
    setRuleDiff(null)
    setArticleCost(null)
    setDetectorData(null)

    // Clear pending auto-save timer from previous article
    if (saveTimer.current) {
      clearTimeout(saveTimer.current)
      saveTimer.current = null
    }

    let cancelled = false
    let needsRulesFetch = false

    // Fetch pipeline logs from schema_json
    if (article?.article_id) {
      setDetectorLoading(true)
      api.get(`/api/content/${article.article_id}`)
        .then(data => {
          if (!cancelled && data?.detector_analysis) {
            setDetectorData(data.detector_analysis)
          }
        })
        .catch(() => {})
        .finally(() => { if (!cancelled) setDetectorLoading(false) })

      api.get(`/api/content/${article.article_id}/pipeline`)
        .then(data => {
          if (!cancelled && data?.logs) {
            setLogs(data.logs)
          }
        })
        .catch(() => {})

      api.get(`/api/content/${article.article_id}/generation-summary`)
        .then(data => { if (!cancelled && data) setArticleCost(data.total_cost_usd ?? null) })
        .catch(() => {})
    }

    if (article?.review_score > 0 && article?.review_breakdown) {
      try {
        const bd = JSON.parse(article.review_breakdown || "{}")
        const notes = JSON.parse(article.review_notes || "{}")
        const storedRules = bd.rules || []
        if (storedRules.length === 0) needsRulesFetch = true
        const derivedIssues = storedRules
          .filter(r => !r.passed)
          .map(r => {
            const ruleId = r.id || r.rule_id || ""
            const pts = r.points ?? ((r.points_max || 0) - (r.points_earned || 0))
            const detail = r.detail || r.name || ""
            return {
              rule: ruleId,
              category: r.pillar,
              severity: pts >= 3 ? "critical" : pts >= 2 ? "high" : pts >= 1 ? "medium" : "low",
              description: ruleId ? `[${ruleId}] ${r.name}: ${detail}` : r.name,
              fix: `Fix to earn back ${pts} pt${pts !== 1 ? 's' : ''}`,
            }
          })
        setReviewData({
          score: article.review_score,
          percentage: notes.percentage || article.review_score,
          total_earned: notes.total_earned,
          max_possible: notes.max_possible,
          categories: bd.categories || bd,
          issues: derivedIssues,
          verdict: notes.verdict || "",
          top_strength: notes.strength || "",
          biggest_weakness: notes.weakness || "",
          ai_detection_risk: notes.ai_risk || null,
          ai_detection_signals: notes.ai_signals || [],
        })
        if (bd.rules && bd.pillars) {
          setRulesData({
            percentage: notes.percentage || article.review_score,
            total_earned: notes.total_earned,
            max_possible: notes.max_possible,
            rules: bd.rules,
            pillars: bd.pillars,
          })
        }
        if (notes.section_scores?.length) {
          setSectionScores(notes.section_scores)
        }
      } catch (_) {}
    } else if (article?.review_score > 0) {
      needsRulesFetch = true
      setReviewData({ score: article.review_score, percentage: article.review_score, issues: [] })
    }

    // Auto-fetch per-rule breakdown for articles lacking stored rules
    if (needsRulesFetch && article?.article_id) {
      api.get(`/api/content/${article.article_id}/rules`)
        .then(rd => {
          if (cancelled || !rd?.rules) return
          const fetchedIssues = rd.rules.filter(r => !r.passed).map(r => {
            const ruleId = r.id || r.rule_id || ""
            const pts = r.points ?? ((r.points_max || 0) - (r.points_earned || 0))
            const detail = r.detail || r.name || ""
            return {
              rule: ruleId,
              category: r.pillar,
              severity: pts >= 3 ? "critical" : pts >= 2 ? "high" : pts >= 1 ? "medium" : "low",
              description: ruleId ? `[${ruleId}] ${r.name}: ${detail}` : r.name,
              fix: `Fix to earn back ${pts} pt${pts !== 1 ? 's' : ''}`,
            }
          })
          setReviewData(prev => prev ? { ...prev, issues: fetchedIssues,
            percentage: rd.percentage ?? prev.percentage,
            total_earned: rd.total_earned,
            max_possible: rd.max_possible,
          } : null)
          setRulesData(rd)
        })
        .catch(() => {})
    }

    return () => { cancelled = true }
  }, [article?.article_id]) // eslint-disable-line

  // ── Auto-save (debounced 1.5s) ─────────────────────────────────────────────
  const handleEditorChange = useCallback((html) => {
    setIsDirty(true)
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(async () => {
      if (article?.article_id) {
        try {
          await api.put(`/api/content/${article.article_id}`, { body: html })
          setIsDirty(false)
        } catch (_) {
          // Save failed silently — will retry on next edit
        }
      }
    }, 1500)
  }, [article])

  // ── View mode toggle ───────────────────────────────────────────────────────
  const switchToHtml = () => {
    if (editorRef.current) setHtmlContent(editorRef.current.getHTML())
    setViewMode("html")
  }
  const switchToEditor = () => {
    if (editorRef.current && htmlContent) {
      editorRef.current.commands.setContent(htmlContent, false)
    }
    setViewMode("editor")
  }

  // ── Drag and drop images ───────────────────────────────────────────────────
  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file && file.type.startsWith("image/") && editorRef.current) {
      const reader = new FileReader()
      reader.onload = (ev) => {
        editorRef.current.chain().focus().setImage({ src: ev.target.result }).run()
      }
      reader.readAsDataURL(file)
    }
  }, [])

  // ── AI Review ─────────────────────────────────────────────────────────────
  const runReview = async () => {
    if (!article?.article_id) return
    setReviewing(true)
    try {
      const res = await api.post(`/api/content/${article.article_id}/review`, {})
      if (res?.score !== undefined) {
        setReviewData(res)
        setOpenPanel("review")
        // Also update rules data if per-rule results are in the response
        if (res?.rules && res?.pillars) {
          setRulesData(res)
        }
        onStatusChange?.()
      }
    } catch (e) {
      alert(`Review failed: ${e?.message || "AI providers unavailable. Try again."}`)
    }
    setReviewing(false)
  }

  // ── Fetch per-rule compliance ────────────────────────────────────────────────
  const fetchRules = async () => {
    if (!article?.article_id) return
    setAnalyzingRules(true)
    try {
      const res = await api.get(`/api/content/${article.article_id}/rules`)
      if (res?.pillars) {
        setRulesData(res)
      }
    } catch (e) { console.warn("Rules fetch failed:", e) }
    setAnalyzingRules(false)
  }

  // ── Fix Single Rule ─────────────────────────────────────────────────────────
  const fixSingleRule = async (ruleId, issue) => {
    if (!article?.article_id || fixingRule) return
    setFixingRule(ruleId)
    setRuleDiff(null)
    setFixStats(s => s ? { ...s, running: (s.running || 0) + 1 } : { running: 1, applied: 0, failed: 0, total: 1 })
    try {
      const res = await api.post(`/api/content/${article.article_id}/fix-rule`, {
        rule_id: ruleId,
        rule_name: issue.description || "",
        rule_detail: issue.description || "",
        fix_hint: issue.fix || "",
      })
      if (res?.new_body) {
        setRuleDiff({
          rule_id: ruleId,
          original: res.original_snippet || "",
          fixed: res.fixed_snippet || "",
          new_body: res.new_body,
          description: res.description || "",
          action: res.action || "fix",
        })
        setFixStats(s => s ? { ...s, running: Math.max(0, (s.running || 1) - 1), applied: (s.applied || 0) + 1 } : null)
      } else {
        setFixStats(s => s ? { ...s, running: Math.max(0, (s.running || 1) - 1), failed: (s.failed || 0) + 1 } : null)
        alert(`Fix failed for ${ruleId}: ${res?.detail || "No result"}`)
      }
    } catch (e) {
      setFixStats(s => s ? { ...s, running: Math.max(0, (s.running || 1) - 1), failed: (s.failed || 0) + 1 } : null)
      alert(`Fix failed: ${e?.message || "AI providers unavailable"}`)
    }
    setFixingRule(null)
  }

  // Bug #8 — acceptRuleFix awaits runReview
  const acceptRuleFix = async () => {
    if (!ruleDiff?.new_body || !article?.article_id) return
    try {
      const res = await api.post(`/api/content/${article.article_id}/apply-fix`, {
        new_body: ruleDiff.new_body,
      })
      if (res?.saved && editorRef.current) {
        editorRef.current.commands.setContent(ruleDiff.new_body, false)
        handleEditorChange(ruleDiff.new_body)
        onStatusChange?.()
        try {
          await runReview()
        } catch (e) {
          console.warn("Review after fix failed:", e)
        }
      }
    } catch (e) {
      alert(`Save failed: ${e?.message || "Unknown error"}`)
    }
    setRuleDiff(null)
  }

  const rejectRuleFix = () => setRuleDiff(null)

  const fixIssues = async (issues, provider = "auto") => {
    if (!article?.article_id || fixing) return
    setFixing(true)
    setFixStats({ total: issues.length, running: issues.length, applied: 0, failed: 0 })
    try {
      const res = await api.post(`/api/content/${article.article_id}/rewrite`, {
        mode: "fix_issues", issues, preferred_provider: provider !== "auto" ? provider : undefined,
      })
      if (res?.rewritten_content && editorRef.current) {
        const applied = (res.fixes_applied || []).length
        const failed = (res.fixes_failed || []).length
        setFixStats({ total: issues.length, running: 0, applied, failed })
        editorRef.current.commands.setContent(res.rewritten_content, false)
        handleEditorChange(res.rewritten_content)
        runReview()
      } else if (res?.reason || res?.detail) {
        setFixStats(s => s ? { ...s, running: 0, failed: s.total } : null)
        alert(`AI Fix failed: ${res.reason || res.detail}`)
      }
    } catch (e) {
      setFixStats(s => s ? { ...s, running: 0, failed: s.total } : null)
      alert(`AI Fix failed: ${e?.message || "All AI providers rate-limited. Wait 60s and try again."}`)
    }
    setFixing(false)
  }

  // ── AI Rewrite — full article ──────────────────────────────────────────────
  const rewriteFull = async () => {
    if (!article?.article_id || rewriting) return
    setRewriting(true)
    try {
      const res = await api.post(`/api/content/${article.article_id}/rewrite`, {
        mode: "full",
        instruction: rewriteInstruction,
      })
      if (res?.rewritten_content && editorRef.current) {
        editorRef.current.commands.setContent(res.rewritten_content, false)
        handleEditorChange(res.rewritten_content)
      }
      setShowInstruction(false)
      setRewriteInstruction("")
    } catch (e) {
      alert(`Rewrite failed: ${e?.message || "AI providers unavailable. Try again."}`)
    }
    setRewriting(false)
  }

  // ── AI Rewrite — selected text ─────────────────────────────────────────────
  const rewriteSelection = async () => {
    if (!editorRef.current || !article?.article_id) return
    const { from, to } = editorRef.current.state.selection
    if (from === to) {
      alert("Select some text in the editor first, then click Rewrite Selection.")
      return
    }
    const selectedText = editorRef.current.state.doc.textBetween(from, to, " ")
    setRewriting(true)
    try {
      const res = await api.post(`/api/content/${article.article_id}/rewrite`, {
        mode: "selection",
        selected_text: selectedText,
        instruction: rewriteInstruction,
      })
      if (res?.rewritten_content) {
        editorRef.current.chain().focus()
          .deleteRange({ from, to })
          .insertContentAt(from, res.rewritten_content)
          .run()
        setIsDirty(true)
      }
    } catch (e) {
      alert(`Rewrite failed: ${e?.message || "AI providers unavailable. Try again."}`)
    }
    setRewriting(false)
  }

  // ── Shopify export ─────────────────────────────────────────────────────────
  const exportShopify = () => {
    const html = editorRef.current ? editorRef.current.getHTML() : htmlContent
    const clean = html
      .replace(/ data-[\w-]+="[^"]*"/g, "")
      .replace(/<p><\/p>/g, "")
      .replace(/<img /g, '<img loading="lazy" ')
    const shopifyHtml = `<!-- AnnaSEO Export: ${article?.title || article?.keyword || "article"} -->\n<!-- Generated: ${new Date().toISOString().slice(0, 10)} -->\n\n${clean}`
    navigator.clipboard.writeText(shopifyHtml).then(() => {
      alert("Shopify HTML copied to clipboard!")
    }).catch(() => {
      const blob = new Blob([shopifyHtml], { type: "text/html" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${(article?.keyword || "article").replace(/\s+/g, "-")}.html`
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  const removeDetectorPassage = async (item) => {
    if (!item?.snippet || !article?.article_id) return
    const currentHtml = editorRef.current ? editorRef.current.getHTML() : (article.body || "")
    let newBody = currentHtml

    if (newBody.includes(item.snippet)) {
      newBody = newBody.replace(item.snippet, "")
    } else {
      const probe = item.snippet.slice(0, 80)
      const idx = newBody.indexOf(probe)
      if (idx === -1) {
        alert("Could not locate the highlighted passage in the current article body.")
        return
      }
      newBody = newBody.slice(0, idx) + newBody.slice(idx + probe.length)
    }

    newBody = newBody.replace(/<p>\s*<\/p>/g, "")
    try {
      await api.put(`/api/content/${article.article_id}`, { body: newBody })
      if (editorRef.current) editorRef.current.commands.setContent(newBody, false)
      setIsDirty(false)
      const refreshed = await api.get(`/api/content/${article.article_id}`)
      setDetectorData(refreshed?.detector_analysis || null)
      onStatusChange?.()
    } catch (e) {
      alert(`Remove failed: ${e?.message || "Unknown error"}`)
    }
  }

  return (
    <>
      {/* Editor header toolbar */}
      <div style={{
        padding: "10px 14px",
        borderBottom: `1px solid ${T.border}`,
        display: "flex",
        alignItems: "center",
        gap: 8,
        flexWrap: "wrap",
        flexShrink: 0,
        background: "#FFFFFF",
      }}>
        {/* Article title + status */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 13, fontWeight: 600, color: T.text,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {article.title || article.keyword}
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 2 }}>
            <Badge color={STATUS_COLOR[article.status] || "gray"}>{article.status}</Badge>
            {isDirty && <span style={{ fontSize: 9, color: T.amber, fontStyle: "italic" }}>Saving...</span>}
            {!isDirty && article.body && <span style={{ fontSize: 9, color: T.teal }}>Saved</span>}
            {article.word_count > 0 && (
              <span style={{ fontSize: 9, color: T.textSoft }}>
                {article.word_count.toLocaleString()} words · ~{Math.ceil(article.word_count / 250)} min read
              </span>
            )}
            {articleCost !== null && (
              <span style={{ fontSize: 9, fontWeight: 600, color: articleCost === 0 ? T.teal : "#6366f1" }}>
                {articleCost === 0 ? "Free" : `$${articleCost.toFixed(4)}`}
              </span>
            )}
          </div>
        </div>

        {/* View mode toggle */}
        <div style={{ display: "flex", gap: 2, background: T.grayLight, borderRadius: 8, padding: 2 }}>
          {[["editor", "Editor"], ["html", "HTML"], ["preview", "Preview"], ["story", "Story"], ["detector", "Detector"], ["logs", "Logs"]].map(([m, label]) => (
            <button key={m} onClick={() => {
              if (m === "html") switchToHtml()
              else if (m === "editor") switchToEditor()
              else setViewMode(m)
            }} style={{
              padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 500,
              border: "none", cursor: "pointer",
              background: viewMode === m ? "#fff" : "transparent",
              color: viewMode === m ? T.purple : T.gray,
              boxShadow: viewMode === m ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
            }}>{label}</button>
          ))}
        </div>

        {/* Action buttons */}
        <Btn small onClick={toggleReview} style={{ background: reviewOpen ? T.purpleLight : undefined, color: reviewOpen ? T.purple : undefined }}>
          {reviewOpen ? "Close Review" : "AI Review"}
        </Btn>
        <Btn small onClick={toggleRules} style={{ background: rulesOpen ? T.purpleLight : undefined, color: rulesOpen ? T.purple : undefined }}>
          {rulesOpen ? "Close Rules" : "Rules"}
        </Btn>
        <Btn small onClick={toggleHumanize} style={{ background: humanizeOpen ? "#7c3aed22" : undefined, color: humanizeOpen ? "#7c3aed" : undefined }}>
          {humanizeOpen ? "Close Humanize" : "Humanize"}
        </Btn>
        <Btn small onClick={() => setShowInstruction(v => !v)} disabled={rewriting}>Options</Btn>
        <Btn small onClick={rewriteSelection} disabled={rewriting}>Rewrite Selection</Btn>
        <Btn small variant="primary" onClick={rewriteFull} disabled={rewriting}>
          {rewriting ? "Rewriting..." : "Rewrite Article"}
        </Btn>
        <Btn small onClick={exportShopify} variant="success">Shopify</Btn>

        {/* Bug #1 — use article prop, fix || 0 */}
        {article.status === "draft" && (article.review_score || article.seo_score || 0) < 65 && (
          <>
            <Btn
              small
              variant="primary"
              onClick={() => { if (window.confirm("Re-run pipeline step-by-step? You can pause, review, and change AI at each step.")) {
                api.post(`/api/content/${article.article_id}/regenerate`, { step_mode: "pause" }).then(() => onStatusChange?.())
              }}}
              style={{ background: "#d97706", borderColor: "#d97706" }}
            >
              🔄 Regenerate (Step-by-Step)
            </Btn>
            <Btn
              small
              onClick={() => { if (window.confirm("Re-run entire pipeline automatically?")) {
                api.post(`/api/content/${article.article_id}/regenerate`, { step_mode: "auto" }).then(() => onStatusChange?.())
              }}}
              style={{ fontSize: 10 }}
            >
              ⏩ Auto
            </Btn>
          </>
        )}

        {/* Article status actions */}
        {article.status === "draft" && (
          <Btn small variant="default" onClick={() => api.post(`/api/content/${article.article_id}/approve`).then(() => onStatusChange?.())}>
            Approve
          </Btn>
        )}
        {article.status === "review" && (
          <Btn small variant="success" onClick={() => api.post(`/api/content/${article.article_id}/approve`).then(() => onStatusChange?.())}>✓ Approve</Btn>
        )}
      </div>

      {/* Optional instruction bar */}
      {showInstruction && (
        <div style={{ padding: "8px 14px", borderBottom: `1px solid ${T.border}`, background: T.amberLight, display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 11, color: T.amber, fontWeight: 600, flexShrink: 0 }}>AI instruction:</span>
          <input
            value={rewriteInstruction}
            onChange={e => setRewriteInstruction(e.target.value)}
            placeholder="e.g. make it more conversational, add more stats..."
            style={{ flex: 1, padding: "4px 8px", borderRadius: 6, border: `1px solid ${T.amber}`, fontSize: 11, fontFamily: "inherit", outline: "none" }}
          />
        </div>
      )}

      {/* Rule fix diff preview */}
      {ruleDiff && (
        <div style={{
          padding: "10px 14px", borderBottom: `1px solid ${T.border}`,
          background: "#f0fdf4", display: "flex", flexDirection: "column", gap: 8,
          maxHeight: 200, overflow: "auto",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: T.teal }}>
              Rule Fix Preview: [{ruleDiff.rule_id}]
            </span>
            <span style={{ fontSize: 10, color: T.textSoft }}>{ruleDiff.description}</span>
            <div style={{ flex: 1 }} />
            <button onClick={acceptRuleFix} style={{
              padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 600,
              border: "none", cursor: "pointer", background: T.teal, color: "#fff",
            }}>✓ Accept Fix</button>
            <button onClick={rejectRuleFix} style={{
              padding: "4px 12px", borderRadius: 6, fontSize: 11, fontWeight: 500,
              border: `1px solid ${T.border}`, cursor: "pointer", background: "#fff", color: T.red,
            }}>✕ Reject</button>
          </div>
          {ruleDiff.original && (
            <div style={{ display: "flex", gap: 8, fontSize: 10, fontFamily: "monospace" }}>
              <div style={{ flex: 1, padding: 6, borderRadius: 6, background: "#fef2f2", border: "1px solid #fca5a530", whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 100, overflow: "auto" }}>
                <div style={{ fontSize: 9, fontWeight: 600, color: "#dc2626", marginBottom: 3 }}>Original</div>
                {ruleDiff.original}
              </div>
              <div style={{ flex: 1, padding: 6, borderRadius: 6, background: "#f0fdf4", border: "1px solid #86efac30", whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 100, overflow: "auto" }}>
                <div style={{ fontSize: 9, fontWeight: 600, color: T.teal, marginBottom: 3 }}>Fixed</div>
                {ruleDiff.fixed}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Editor body area */}
      <div
        style={{ flex: 1, display: "flex", overflow: "auto", minHeight: 0 }}
        onDrop={handleDrop}
        onDragOver={e => e.preventDefault()}
      >
        {/* Editor or HTML source or Logs */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: viewMode === "html" || viewMode === "logs" ? 16 : 0, minHeight: 0 }}>
          {viewMode === "editor" ? (
            <TiptapEditor
              content={article.body || ""}
              articleId={article.article_id}
              onChange={handleEditorChange}
              onEditorReady={ed => { editorRef.current = ed }}
              placeholder="Start writing your article here..."
            />
          ) : viewMode === "html" ? (
            <>
              <div style={{ fontSize: 10, color: T.textSoft, marginBottom: 6 }}>
                HTML Source — edit directly, then switch back to Editor to apply
              </div>
              <textarea
                value={htmlContent}
                onChange={e => setHtmlContent(e.target.value)}
                style={{
                  flex: 1,
                  padding: 16,
                  fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
                  fontSize: 12,
                  lineHeight: 1.7,
                  background: "#0f1117",
                  color: "#e2e8f0",
                  border: "none",
                  outline: "none",
                  resize: "none",
                  borderRadius: 10,
                  minHeight: 400,
                }}
              />
            </>
          ) : viewMode === "preview" ? (
            <div style={{ flex: 1, overflowY: "auto", padding: "32px 48px", background: "#fff" }}>
              <article style={{ maxWidth: 720, margin: "0 auto", fontFamily: "Georgia, 'Times New Roman', serif", color: "#1a1a1a", lineHeight: 1.8 }}>
                <style>{`
                  .blog-preview h1 { font-size: 2.2em; font-weight: 700; line-height: 1.3; margin: 0 0 12px; color: #111; }
                  .blog-preview h2 { font-size: 1.5em; font-weight: 700; margin: 2em 0 0.6em; color: #222; border-bottom: 2px solid #f0f0f0; padding-bottom: 4px; }
                  .blog-preview h3 { font-size: 1.15em; font-weight: 600; margin: 1.4em 0 0.4em; color: #333; }
                  .blog-preview p { margin: 0.8em 0; font-size: 1.05em; }
                  .blog-preview ul, .blog-preview ol { margin: 0.6em 0 0.6em 1.4em; }
                  .blog-preview li { margin: 0.3em 0; }
                  .blog-preview table { width: 100%; border-collapse: collapse; margin: 1.4em 0; font-size: 0.93em; font-family: sans-serif; }
                  .blog-preview th { background: #f5f5f5; font-weight: 600; text-align: left; padding: 8px 12px; border: 1px solid #e0e0e0; }
                  .blog-preview td { padding: 7px 12px; border: 1px solid #e0e0e0; }
                  .blog-preview blockquote { border-left: 4px solid #7c3aed; margin: 1.2em 0; padding: 10px 16px; background: #faf8ff; color: #444; font-style: italic; border-radius: 0 6px 6px 0; }
                  .blog-preview a { color: #7c3aed; }
                  .blog-preview strong { color: #111; }
                  .blog-preview .key-takeaway, .blog-preview [class*="takeaway"] { background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 12px 16px; margin: 1em 0; }
                  .blog-preview nav.toc { background: #f8f8f8; border: 1px solid #eee; border-radius: 8px; padding: 14px 18px; margin: 1em 0; font-size: 0.9em; font-family: sans-serif; }
                `}</style>
                <div className="blog-preview" dangerouslySetInnerHTML={{ __html: article.body || "<p><em>No content yet.</em></p>" }} />
              </article>
            </div>
          ) : viewMode === "story" ? (
            /* Story View — article body with light-green plot/snippet highlights */
            <StoryView articleId={article.article_id} body={article.body || ""} />
          ) : viewMode === "detector" ? (
            <DetectorView
              body={article.body || ""}
              detectorData={detectorData}
              loading={detectorLoading}
              onRemovePassage={removeDetectorPassage}
            />
          ) : (
            /* Logs View — shows pipeline logs from polling + stored logs */
            <PipelineLogsView articleId={article.article_id} storedLogs={logs} />
          )}
        </div>

        {/* Right: AI review panel */}
        <div style={{
          width: reviewOpen ? 310 : 0,
          minWidth: reviewOpen ? 310 : 0,
          overflow: "hidden",
          transition: "width 0.25s ease, min-width 0.25s ease",
          borderLeft: reviewOpen ? `1px solid ${T.border}` : "none",
          background: "#F2F2F7",
        }}>
          {reviewOpen && (
            <ReviewPanel
              data={reviewData}
              loading={reviewing}
              onRunReview={runReview}
              onFixIssues={fixIssues}
              fixing={fixing}
              onFixRule={fixSingleRule}
              fixingRule={fixingRule}
              fixStats={fixStats}
            />
          )}
        </div>

        {/* Right: Rules compliance panel */}
        <div style={{
          width: rulesOpen ? 310 : 0,
          minWidth: rulesOpen ? 310 : 0,
          overflow: "hidden",
          transition: "width 0.25s ease, min-width 0.25s ease",
          borderLeft: rulesOpen ? `1px solid ${T.border}` : "none",
          background: "#F2F2F7",
        }}>
          {rulesOpen && (
            <RulesPanel
              articleId={article?.article_id}
              data={rulesData}
              sectionScores={sectionScores}
              loading={analyzingRules}
              onReAnalyze={fetchRules}
            />
          )}
        </div>

        {/* Right: Humanize panel */}
        <div style={{
          width: humanizeOpen ? 310 : 0,
          minWidth: humanizeOpen ? 310 : 0,
          overflow: "hidden",
          transition: "width 0.25s ease, min-width 0.25s ease",
          borderLeft: humanizeOpen ? `1px solid ${T.border}` : "none",
          background: "#F2F2F7",
        }}>
          {humanizeOpen && (
            <HumanizePanel
              articleId={article?.article_id}
              onHumanized={(res) => {
                if (res?.humanized_html && editorRef.current) {
                  editorRef.current.commands?.setContent(res.humanized_html)
                  setHtmlContent(res.humanized_html)
                }
              }}
            />
          )}
        </div>
      </div>
    </>
  )
}
