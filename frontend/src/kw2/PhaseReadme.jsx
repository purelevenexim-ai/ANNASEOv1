/**
 * PhaseReadme — In-app guide / README for Keyword Research v2
 *
 * Describes every phase, what it does, what it requires, what it produces,
 * and how to use it. Shown as the "📖 Guide" tab in the KW2 stepper.
 */
import React, { useState } from "react"

/* ── Design tokens ── */
const T = {
  blue:   "#3b82f6",
  green:  "#10b981",
  orange: "#f59e0b",
  purple: "#8b5cf6",
  red:    "#ef4444",
  gray:   "#6b7280",
  bg:     "#f9fafb",
  card:   "#ffffff",
  border: "#e5e7eb",
}

/* ── Phase data ── */
const PHASES = [
  {
    id: "1",
    icon: "🔍",
    label: "1. Analyze — Business Analysis",
    color: "#3b82f6",
    bg: "#eff6ff",
    time: "~30s",
    input: "Domain URL, Business Type, Pillars, Product Catalog, Modifiers, Audience, Geo Scope, Competitor URLs",
    output: "Business profile stored in DB — used by all subsequent phases",
    description:
      "The foundation of every keyword research session. Fills in the business profile from your inputs and uses AI to understand your niche, audience, and competitive landscape. The profile is reused in every later phase — so every change here flows downstream.",
    tips: [
      "Enter pillars as comma-separated themes (e.g. 'organic spices, whole spices, export spices')",
      "Geo Scope narrows intent scoring to your actual markets (e.g. 'India, USA')",
      "Competitor URLs improve negative scope detection and gap analysis",
      "You can re-run this anytime; it creates a new session version",
    ],
  },
  {
    id: "BI",
    icon: "🧠",
    label: "Intel — Business Intelligence Engine",
    color: "#8b5cf6",
    bg: "#f5f3ff",
    time: "~1–2 min",
    input: "Business profile from Phase 1",
    output: "Market intel: competitor gaps, audience segments, trending topics, SERP opportunities, seasonal patterns",
    description:
      "Runs a multi-layer AI analysis to build your market intelligence layer. Expands competitor analysis, identifies content gaps, maps audience segments with buying triggers, and detects seasonal keyword peaks. The intel feeds into all validation and scoring phases.",
    tips: [
      "Run this after Phase 1 completes — it unlocks richer keyword scoring downstream",
      "Competitor gap highlights keyword categories your site is missing vs competitors",
      "Seasonal patterns feed Phase 8 (Content Calendar) automatically",
    ],
  },
  {
    id: "2",
    icon: "✨",
    label: "2. Generate — Keyword Generation",
    color: "#10b981",
    bg: "#f0fdf4",
    time: "~1–3 min",
    input: "Business profile + BI intel",
    output: "Raw keyword list (hundreds) covering head terms, long-tail, and question-style queries",
    description:
      "Uses AI to generate a comprehensive keyword universe from your business profile. Produces head terms, long-tail variations, question formats (how/what/where/why), and commercial modifiers. Each keyword is tagged with a pillar, intent type, and generation source.",
    tips: [
      "More specific pillars → more targeted keywords",
      "Run Phase 1 and Intel first for best coverage",
      "You can re-run to get a fresh batch if the first run missed key terms",
    ],
  },
  {
    id: "3",
    icon: "✅",
    label: "3. Validate — Keyword Validation",
    color: "#f59e0b",
    bg: "#fffbeb",
    time: "~1–2 min",
    input: "Generated keyword list from Phase 2",
    output: "Filtered keyword list — removed duplicates, spammy, off-topic, or very low-quality terms",
    description:
      "Runs quality filters over the raw generated keywords. Removes duplicates, near-duplicates, overly broad terms, spam patterns, and keywords that violate your negative scope. Uses the business profile to score relevance and apply automated threshold cuts.",
    tips: [
      "Check the Review tab after this phase — it shows exactly what was kept and removed",
      "Adjust Negative Scope in Phase 1 → re-run Validate to change what gets filtered",
      "Informational queries (how to, benefits, recipe) are filtered by default if you're an e-commerce store",
    ],
  },
  {
    id: "REVIEW",
    icon: "📋",
    label: "3. Review — Pillar Confirmation (Gate 2)",
    color: "#f59e0b",
    bg: "#fffbeb",
    time: "Your decision",
    input: "Validated keywords, grouped by pillar",
    output: "Customer-confirmed pillar list — locked into the session for Phases 4-9",
    description:
      "A human checkpoint before keyword scoring begins. Shows validated keywords grouped into pillars. You can rename pillars, move keywords between pillars, or delete irrelevant terms. Confirming locks the pillar structure for the rest of the session.",
    tips: [
      "This Gate 2 confirmation is permanent — changes downstream phases won't alter your pillar structure",
      "Merge small pillars if they have fewer than 5 keywords",
      "Rename AI-generated pillar names to match your actual site taxonomy",
    ],
  },
  {
    id: "4",
    icon: "🏆",
    label: "4. Score — Keyword Scoring",
    color: "#3b82f6",
    bg: "#eff6ff",
    time: "~1–2 min",
    input: "Confirmed pillar keywords",
    output: "Scored keywords: SEO score, intent score, opportunity score, competition estimate",
    description:
      "Applies a multi-factor scoring model to every keyword. Factors include: search intent alignment, estimated competition, business relevance (from your profile), topical authority fit, pillar alignment, and geo-scope match. Output is a ranked list per pillar.",
    tips: [
      "Sort by Opportunity Score to find high-value, low-competition targets",
      "Purchase-intent keywords get a scoring bonus — good for product pages",
      "Keywords scoring below 40 are typically not worth targeting unless they're branded terms",
    ],
  },
  {
    id: "5",
    icon: "🌳",
    label: "5. Tree — Keyword Cluster Tree",
    color: "#10b981",
    bg: "#f0fdf4",
    time: "~30s",
    input: "Scored keyword list",
    output: "Visual hierarchical tree: pillars → topic clusters → individual keywords",
    description:
      "Builds a keyword hierarchy tree showing how individual keywords relate to each other and their parent pillar. Useful for planning site architecture, internal linking, and content clustering strategy. You can collapse/expand nodes and export the tree structure.",
    tips: [
      "Each top-level node = a site pillar (matches your Phase 1 input)",
      "Second-level clusters suggest content hub pages",
      "Leaf nodes (individual keywords) map to specific blog posts or product pages",
    ],
  },
  {
    id: "6",
    icon: "🕸",
    label: "6. Graph — Keyword Relationship Graph",
    color: "#8b5cf6",
    bg: "#f5f3ff",
    time: "~30s",
    input: "Cluster tree from Phase 5",
    output: "Interactive D3 force graph showing semantic relationships between keywords",
    description:
      "Renders an interactive D3 force-directed graph showing keyword co-occurrence, semantic proximity, and pillar clustering. Helps visualize the competitive landscape and identify unexplored topic islands that no competitor has claimed.",
    tips: [
      "Drag nodes to explore clusters — tightly grouped nodes are semantically related",
      "Isolated or peripheral nodes are niche opportunity keywords (low competition)",
      "Color coding matches pillars set in Phase 1",
    ],
  },
  {
    id: "7",
    icon: "🔗",
    label: "7. Links — Internal Linking Map",
    color: "#ef4444",
    bg: "#fef2f2",
    time: "~1 min",
    input: "Scored keywords + cluster tree",
    output: "Recommended internal linking structure: hub pages → spoke pages → supporting content",
    description:
      "Generates an SEO-optimized internal linking architecture based on your keywords. Identifies cornerstone pages (hubs), supporting content (spokes), and anchor text recommendations. Follows the hub-and-spoke model for maximum topical authority flow.",
    tips: [
      "Hub pages should target your highest-volume, most competitive head terms",
      "Spoke pages target long-tail variations and funnel traffic to the hub",
      "Use the anchor text suggestions exactly — they're optimized for relevance, not brand repetition",
    ],
  },
  {
    id: "8",
    icon: "📅",
    label: "8. Calendar — Content Calendar",
    color: "#f59e0b",
    bg: "#fffbeb",
    time: "~1 min",
    input: "Scored keywords + seasonal intel from BI engine",
    output: "12-month content publishing calendar with priority order, format, and keyword targets",
    description:
      "Creates a prioritized 12-month content calendar matching keywords to optimal publishing windows. Uses the seasonal patterns from the Intel engine to schedule product-focused content before buying peaks, and informational content during off-peak months to build authority.",
    tips: [
      "High-score purchase-intent keywords scheduled before seasonal peaks (e.g. spices before winter holidays)",
      "Informational content fills low-competition months to build topical authority",
      "Calendar output maps directly to your content team's sprint planning",
    ],
  },
  {
    id: "9",
    icon: "🎯",
    label: "9. Strategy — SEO Strategy Report",
    color: "#6366f1",
    bg: "#eef2ff",
    time: "~2 min",
    input: "All phase outputs combined",
    output: "Full executive strategy report: positioning, priority actions, 90-day roadmap, competitor gaps",
    description:
      "The final synthesis phase. Combines everything — business profile, keywords, scores, links, and calendar — into a single actionable SEO strategy document. Includes a 90-day priority action plan, competitive positioning statement, and pillar content roadmap.",
    tips: [
      "This report is designed to share directly with clients or your SEO team",
      "The 90-day plan is prioritized by ROI potential — follow the order",
      "Download as PDF or copy to your project management tool",
    ],
  },
]

/* ── Accordion item ── */
function PhaseCard({ phase, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={{
      borderRadius: 12, border: `1.5px solid ${open ? phase.color : T.border}`,
      background: open ? phase.bg : T.card,
      marginBottom: 10, overflow: "hidden",
      transition: "all .2s",
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", padding: "14px 16px", background: "transparent", border: "none",
          display: "flex", alignItems: "center", gap: 12, cursor: "pointer", textAlign: "left",
        }}
      >
        <span style={{ fontSize: 20 }}>{phase.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: open ? phase.color : "#1c1c1e" }}>{phase.label}</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{
            padding: "2px 9px", borderRadius: 8, fontSize: 11, fontWeight: 600,
            background: phase.color + "20", color: phase.color,
          }}>{phase.time}</span>
          <span style={{ color: open ? phase.color : T.gray, fontSize: 16 }}>{open ? "▲" : "▼"}</span>
        </div>
      </button>

      {open && (
        <div style={{ padding: "0 16px 16px" }}>
          {/* Description */}
          <p style={{ fontSize: 13, color: "#374151", lineHeight: 1.7, marginBottom: 14 }}>{phase.description}</p>

          {/* Input / Output */}
          <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
            <div style={{
              flex: 1, minWidth: 200, padding: "10px 12px", borderRadius: 8,
              background: "#f0fdf4", border: "1px solid #bbf7d0",
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#166534", marginBottom: 4, textTransform: "uppercase", letterSpacing: .5 }}>Input</div>
              <div style={{ fontSize: 12, color: "#374151", lineHeight: 1.6 }}>{phase.input}</div>
            </div>
            <div style={{
              flex: 1, minWidth: 200, padding: "10px 12px", borderRadius: 8,
              background: "#eff6ff", border: "1px solid #bfdbfe",
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#1e40af", marginBottom: 4, textTransform: "uppercase", letterSpacing: .5 }}>Output</div>
              <div style={{ fontSize: 12, color: "#374151", lineHeight: 1.6 }}>{phase.output}</div>
            </div>
          </div>

          {/* Tips */}
          <div style={{ background: "#fffbeb", borderRadius: 8, padding: "10px 12px", border: "1px solid #fde68a" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: "#854d0e", marginBottom: 6, textTransform: "uppercase", letterSpacing: .5 }}>💡 Tips</div>
            {phase.tips.map((tip, i) => (
              <div key={i} style={{ fontSize: 12, color: "#374151", lineHeight: 1.6, display: "flex", gap: 6, marginBottom: 3 }}>
                <span style={{ color: "#d97706", flexShrink: 0 }}>•</span>
                <span>{tip}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Workflow flow diagram ── */
function FlowDiagram() {
  const steps = [
    { n: "1", label: "Analyze", color: "#3b82f6" },
    { n: "BI", label: "Intel", color: "#8b5cf6" },
    { n: "🔎", label: "Search", color: "#0ea5e9" },
    { n: "2", label: "Generate", color: "#10b981" },
    { n: "3", label: "Validate", color: "#f59e0b" },
    { n: "✓", label: "Review", color: "#f59e0b" },
    { n: "4", label: "Score", color: "#3b82f6" },
    { n: "5", label: "Tree", color: "#10b981" },
    { n: "6", label: "Graph", color: "#8b5cf6" },
    { n: "7", label: "Links", color: "#ef4444" },
    { n: "8", label: "Calendar", color: "#f59e0b" },
    { n: "9", label: "Strategy", color: "#6366f1" },
  ]
  return (
    <div style={{ overflowX: "auto", paddingBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 0, minWidth: 600 }}>
        {steps.map((s, i) => (
          <React.Fragment key={s.n}>
            <div style={{
              display: "flex", flexDirection: "column", alignItems: "center", gap: 4, flexShrink: 0,
            }}>
              <div style={{
                width: 36, height: 36, borderRadius: "50%", background: s.color,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 800, fontSize: 12, color: "#fff",
              }}>{s.n}</div>
              <span style={{ fontSize: 10, fontWeight: 600, color: "#374151", whiteSpace: "nowrap" }}>{s.label}</span>
            </div>
            {i < steps.length - 1 && (
              <div style={{ width: 20, height: 2, background: "#d1d5db", flexShrink: 0, marginBottom: 14 }} />
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}

/* ── PDF export ── */
function downloadPDF() {
  const phases = PHASES
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Keyword Research v2 — Guide</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 13px; color: #1c1c1e; padding: 40px; line-height: 1.6; }
  h1 { font-size: 24px; font-weight: 800; margin-bottom: 6px; }
  h2 { font-size: 15px; font-weight: 700; margin: 24px 0 6px; color: #1e40af; }
  h3 { font-size: 13px; font-weight: 700; margin: 14px 0 4px; }
  p  { margin-bottom: 10px; color: #374151; }
  .subtitle { font-size: 13px; color: #6b7280; margin-bottom: 24px; }
  .qs { background: #eff6ff; border: 1.5px solid #bfdbfe; border-radius: 10px; padding: 14px 18px; margin-bottom: 20px; }
  .qs ol { padding-left: 20px; }
  .qs li { margin-bottom: 4px; }
  .flow { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; margin-bottom: 24px; padding: 14px; border: 1px solid #e5e7eb; border-radius: 10px; }
  .flow-node { text-align: center; }
  .flow-circle { width: 32px; height: 32px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: 800; font-size: 11px; color: #fff; }
  .flow-label { font-size: 10px; font-weight: 600; color: #374151; margin-top: 3px; }
  .flow-arrow { width: 16px; height: 2px; background: #d1d5db; margin-bottom: 14px; }
  .phase { border: 1.5px solid #e5e7eb; border-radius: 10px; margin-bottom: 14px; padding: 14px 16px; page-break-inside: avoid; }
  .phase-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .phase-icon { font-size: 18px; }
  .phase-title { font-weight: 700; font-size: 14px; }
  .phase-time { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 6px; }
  .io { display: flex; gap: 10px; margin-bottom: 12px; }
  .io-box { flex: 1; padding: 10px 12px; border-radius: 8px; }
  .io-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
  .tips { background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 10px 12px; }
  .tips-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px; color: #854d0e; margin-bottom: 6px; }
  .tip { display: flex; gap: 6px; margin-bottom: 3px; font-size: 12px; color: #374151; }
  .gsc { background: #f5f3ff; border: 1.5px solid #ddd6fe; border-radius: 10px; padding: 14px 18px; margin-top: 16px; }
  .gsc h2 { color: #6d28d9; margin-top: 0; }
  .gsc ul { padding-left: 20px; }
  .gsc li { margin-bottom: 4px; }
  @media print { body { padding: 20px; } }
</style>
</head>
<body>
<h1>📖 Keyword Research v2 — Guide</h1>
<p class="subtitle">A 9-phase AI-powered pipeline that takes your business domain and turns it into a complete SEO keyword strategy: scored keywords, content clusters, internal linking map, and a publishing calendar.</p>

<div class="qs">
  <h2 style="margin:0 0 8px;color:#1e40af">⚡ Quick Start</h2>
  <ol>
    <li>Click <strong>+ New Analysis</strong> (top right) to start a session</li>
    <li>Choose mode: <strong>Develop for Brand</strong>, <strong>Expand Keyword Search</strong>, or <strong>Review Keywords</strong></li>
    <li>For Brand mode: run <strong>Analyze → Intel</strong></li>
    <li>Run <strong>Search</strong> (Global + My GSC Data options)</li>
    <li>Run <strong>Generate → Validate</strong> to build your keyword set</li>
    <li>Confirm pillars in the <strong>Review</strong> tab (Gate 2)</li>
    <li>Let <strong>Score → Tree → Graph → Links → Calendar → Strategy</strong> run sequentially</li>
    <li>Download the Strategy report</li>
  </ol>
</div>

<div class="flow">
${[
  {n:"1",label:"Analyze",color:"#3b82f6"},
  {n:"BI",label:"Intel",color:"#8b5cf6"},
  {n:"🔎",label:"Search",color:"#0ea5e9"},
  {n:"2",label:"Generate",color:"#10b981"},
  {n:"3",label:"Validate",color:"#f59e0b"},
  {n:"✓",label:"Review",color:"#f59e0b"},
  {n:"4",label:"Score",color:"#3b82f6"},
  {n:"5",label:"Tree",color:"#10b981"},
  {n:"6",label:"Graph",color:"#8b5cf6"},
  {n:"7",label:"Links",color:"#ef4444"},
  {n:"8",label:"Calendar",color:"#f59e0b"},
  {n:"9",label:"Strategy",color:"#6366f1"},
].map((s,i,arr) => `
  <div class="flow-node">
    <div class="flow-circle" style="background:${s.color}">${s.n}</div>
    <div class="flow-label">${s.label}</div>
  </div>${i < arr.length-1 ? '<div class="flow-arrow"></div>' : ''}`).join("")}
</div>

<h2 style="margin-top:0">Phase Reference</h2>
${phases.map(p => `
<div class="phase" style="border-color:${p.color}20">
  <div class="phase-header">
    <span class="phase-icon">${p.icon}</span>
    <span class="phase-title" style="color:${p.color}">${p.label}</span>
    <span class="phase-time" style="background:${p.color}20;color:${p.color}">⏱ ${p.time}</span>
  </div>
  <p>${p.description}</p>
  <div class="io">
    <div class="io-box" style="background:#f0fdf4;border:1px solid #bbf7d0">
      <div class="io-label" style="color:#166534">Input</div>
      <div style="font-size:12px;color:#374151">${p.input}</div>
    </div>
    <div class="io-box" style="background:#eff6ff;border:1px solid #bfdbfe">
      <div class="io-label" style="color:#1e40af">Output</div>
      <div style="font-size:12px;color:#374151">${p.output}</div>
    </div>
  </div>
  <div class="tips">
    <div class="tips-label">💡 Tips</div>
    ${p.tips.map(t => `<div class="tip"><span style="color:#d97706">•</span><span>${t}</span></div>`).join("")}
  </div>
</div>`).join("")}

<div class="gsc">
  <h2>🔎 Search Stage (Integrated)</h2>
  <p>Search is now an integrated stage in the workflow. It supports two sources: <strong>Global Google Suggest</strong> for expansion and <strong>My GSC Data</strong> for authority/performance checks.</p>
  <ul>
    <li><strong>Brand mode:</strong> Analyze → Intel → Generate (Search is built into Generate)</li>
    <li><strong>Expand mode:</strong> Search (Global) → Generate</li>
    <li><strong>Review mode:</strong> Search (My GSC Data only)</li>
    <li>Use GSC metrics (impressions/clicks/position) to prioritize quick wins</li>
  </ul>
</div>

<script>window.onload = function(){ window.print(); }</script>
</body>
</html>`

  const w = window.open("", "_blank", "width=900,height=700")
  w.document.write(html)
  w.document.close()
}

/* ── Main component ── */
export default function PhaseReadme() {
  return (
    <div style={{ maxWidth: 860, margin: "0 auto" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20, gap: 12, flexWrap: "wrap" }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: -0.5, marginBottom: 4 }}>
            📖 Keyword Research v2 — Guide
          </div>
          <div style={{ fontSize: 13, color: T.gray, lineHeight: 1.7 }}>
            A 9-phase AI-powered pipeline that takes your business domain and turns it into
            a complete SEO keyword strategy: scored keywords, content clusters, internal linking map, and a publishing calendar.
          </div>
        </div>
        <button onClick={downloadPDF} style={{
          flexShrink: 0, padding: "8px 18px", borderRadius: 8, border: "none",
          background: "#1e40af", color: "#fff", fontWeight: 700, fontSize: 13,
          cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
        }}>
          📄 Download PDF
        </button>
      </div>

      {/* Quick-start */}
      <div style={{
        padding: "14px 16px", borderRadius: 12, background: "#eff6ff",
        border: "1.5px solid #bfdbfe", marginBottom: 16,
      }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: "#1e40af", marginBottom: 6 }}>⚡ Quick Start</div>
        <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: "#374151", lineHeight: 2 }}>
          <li>Click <strong>+ New Analysis</strong> (top right) to start a session</li>
          <li>Choose mode: <strong>Develop for Brand</strong>, <strong>Expand Keyword Search</strong>, or <strong>Review Keywords</strong></li>
          <li>For Brand mode: run <strong>Analyze → Intel</strong></li>
          <li>Run <strong>Search</strong> (Global + My GSC Data options)</li>
          <li>Run <strong>Generate → Validate</strong> to build your keyword list</li>
          <li>Confirm pillars in the <strong>Review</strong> tab (Gate 2)</li>
          <li>Let <strong>Score → Tree → Graph → Links → Calendar → Strategy</strong> run sequentially</li>
          <li>Download the Strategy report</li>
        </ol>
      </div>

      {/* Workflow diagram */}
      <div style={{
        padding: "14px 16px", borderRadius: 12, background: T.card,
        border: `1px solid ${T.border}`, marginBottom: 20,
      }}>
        <div style={{ fontWeight: 700, fontSize: 13, color: "#374151", marginBottom: 12 }}>Workflow Overview</div>
        <FlowDiagram />
        <div style={{ display: "flex", gap: 16, marginTop: 12, flexWrap: "wrap" }}>
          {[
            { color: "#eff6ff", border: "#bfdbfe", label: "Analysis & Setup" },
            { color: "#f0fdf4", border: "#bbf7d0", label: "Generation & Filtering" },
            { color: "#fffbeb", border: "#fde68a", label: "Human Checkpoints" },
            { color: "#fef2f2", border: "#fecaca", label: "Content Structure" },
          ].map(l => (
            <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 12, height: 12, borderRadius: 3, background: l.color, border: `1px solid ${l.border}` }} />
              <span style={{ fontSize: 11, color: T.gray }}>{l.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Phase cards */}
      <div style={{ fontSize: 13, fontWeight: 700, color: "#374151", marginBottom: 10 }}>
        Phase Reference — click any phase to expand
      </div>
      {PHASES.map((p, i) => (
        <PhaseCard key={p.id} phase={p} defaultOpen={i === 0} />
      ))}

      {/* Search stage note */}
      <div style={{
        marginTop: 16, padding: "14px 16px", borderRadius: 12,
        background: "#f5f3ff", border: "1.5px solid #ddd6fe",
      }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: "#6d28d9", marginBottom: 6 }}>
          🔎 Search Stage (Integrated)
        </div>
        <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.7 }}>
          Search is now part of the main workflow and supports both global discovery and site-performance review:
        </div>
        <ul style={{ margin: "8px 0 0", paddingLeft: 20, fontSize: 13, color: "#374151", lineHeight: 2 }}>
          <li><strong>Brand mode:</strong> Analyze → Intel → Generate (Search is built into Generate)</li>
          <li><strong>Expand mode:</strong> Search (Global) → Generate</li>
          <li><strong>Review mode:</strong> Search (My GSC Data only)</li>
          <li>Use GSC metrics for quick-win optimization and pillar authority review</li>
        </ul>
      </div>
    </div>
  )
}
