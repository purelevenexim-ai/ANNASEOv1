/**
 * Tab 4: Strategy & Plan
 *
 * Single "Generate strategy" button runs Phases 5 → 6 → 7 → 8 → 9 sequentially.
 * Then displays four sub-views: Tree, Links, Calendar, Strategy doc.
 */
import React, { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  runPhase5, runPhase6, runPhase7, runPhase8, runPhase9,
  getTree, getLinks, getCalendar, getStrategy,
} from "./api"
import { Card, Btn, Spinner, T, Stat, Badge, Empty } from "./ui"

const SUB = [
  { id: "tree",     label: "🌳 Tree" },
  { id: "links",    label: "🔗 Links" },
  { id: "calendar", label: "📅 Calendar" },
  { id: "strategy", label: "📋 Strategy" },
]

const STEPS = [
  { key: "p5", label: "Build content tree (Phase 5)",      run: runPhase5, doneFlag: "phase5_done" },
  { key: "p6", label: "Build knowledge graph (Phase 6)",   run: runPhase6, doneFlag: "phase6_done" },
  { key: "p7", label: "Generate internal links (Phase 7)", run: runPhase7, doneFlag: "phase7_done" },
  { key: "p8", label: "Build content calendar (Phase 8)",  run: runPhase8, doneFlag: "phase8_done" },
  { key: "p9", label: "Compose strategy doc (Phase 9)",    run: runPhase9, doneFlag: "phase9_done", optional: true },
]

export default function TabStrategy({ projectId, sessionId, session }) {
  const qc = useQueryClient()
  const [active, setActive] = useState("tree")
  const [running, setRunning] = useState(null)   // step key currently running
  const [error, setError] = useState("")
  const [stepLog, setStepLog] = useState({})     // { key: "ok"|"fail" }

  const treeQ = useQuery({
    queryKey: ["kw3", projectId, "tree", sessionId],
    queryFn: () => getTree(projectId, sessionId),
    enabled: !!sessionId && !!session?.phase5_done,
  })
  const linksQ = useQuery({
    queryKey: ["kw3", projectId, "links", sessionId],
    queryFn: () => getLinks(projectId, sessionId),
    enabled: !!sessionId && !!session?.phase7_done,
  })
  const calQ = useQuery({
    queryKey: ["kw3", projectId, "calendar", sessionId],
    queryFn: () => getCalendar(projectId, sessionId),
    enabled: !!sessionId && !!session?.phase8_done,
  })
  const stratQ = useQuery({
    queryKey: ["kw3", projectId, "strategy", sessionId],
    queryFn: () => getStrategy(projectId, sessionId),
    enabled: !!sessionId && !!session?.phase9_done,
  })

  const runAll = async () => {
    setError("")
    setStepLog({})
    for (const step of STEPS) {
      if (session?.[step.doneFlag]) {
        setStepLog(s => ({ ...s, [step.key]: "skip" }))
        continue
      }
      setRunning(step.key)
      try {
        await step.run(projectId, sessionId)
        setStepLog(s => ({ ...s, [step.key]: "ok" }))
        await qc.invalidateQueries({ queryKey: ["kw3", projectId, "session", sessionId] })
      } catch (e) {
        setStepLog(s => ({ ...s, [step.key]: "fail" }))
        if (step.optional) {
          // Optional steps don't halt the chain; surface as a non-blocking warning.
          setError(prev => prev
            ? `${prev}; ${step.label}: ${e?.message || e}`
            : `${step.label} failed (optional, continuing): ${e?.message || e}`)
          continue
        }
        setError(`${step.label}: ${e?.message || e}`)
        setRunning(null)
        return
      }
    }
    setRunning(null)
    qc.invalidateQueries({ queryKey: ["kw3", projectId] })
  }

  const allDone = STEPS.every(s => session?.[s.doneFlag])
  const anyDone = STEPS.some(s => session?.[s.doneFlag])

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Card>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>Strategy & Plan</div>
            <div style={{ fontSize: 12, color: T.textSoft, marginTop: 2 }}>
              Builds tree, links, calendar, and a polished strategy document from your approved keywords.
            </div>
          </div>
          <div>
            <Btn onClick={runAll} disabled={!!running || !session?.phase4_done}>
              {running
                ? <><Spinner color="#fff" /> &nbsp;Running…</>
                : allDone ? "Re-run all" : anyDone ? "Continue from where left off" : "Generate strategy"}
            </Btn>
          </div>
        </div>

        {!session?.phase4_done && (
          <div style={{ marginTop: 12, padding: 10, background: T.warnBg, color: T.warn, borderRadius: 7, fontSize: 12 }}>
            ⚠ Score & approve keywords first (Tab 3).
          </div>
        )}
        {error && (
          <div style={{ marginTop: 12, padding: 10, background: T.errorBg, color: T.error, borderRadius: 7, fontSize: 12 }}>
            ❌ {error}
          </div>
        )}

        {/* Step status grid */}
        <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 8 }}>
          {STEPS.map(s => {
            const isRun = running === s.key
            const isDone = session?.[s.doneFlag]
            const log = stepLog[s.key]
            const status = isRun ? "running" : isDone ? "done" : log === "fail" ? "fail" : "pending"
            return (
              <div key={s.key} style={{
                border: `1px solid ${T.border}`,
                borderRadius: 7, padding: "8px 10px",
                background: status === "done" ? T.successBg
                          : status === "fail" ? T.errorBg
                          : status === "running" ? T.primaryBg
                          : T.card,
              }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: T.text }}>{s.label}</div>
                <div style={{ fontSize: 10, marginTop: 4, color:
                  status === "done" ? T.success
                  : status === "fail" ? T.error
                  : status === "running" ? T.primary
                  : T.textMute,
                }}>
                  {status === "running" && <><Spinner size={10} /> &nbsp;Running…</>}
                  {status === "done" && "✓ Complete"}
                  {status === "fail" && "✗ Failed"}
                  {status === "pending" && "Waiting"}
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      {/* Sub-tab nav */}
      <div style={{ display: "flex", gap: 4, padding: 4, background: T.card, border: `1px solid ${T.border}`, borderRadius: 10 }}>
        {SUB.map(s => {
          const isActive = active === s.id
          return (
            <button
              key={s.id}
              onClick={() => setActive(s.id)}
              style={{
                flex: 1, padding: "8px 14px",
                background: isActive ? T.primary : "transparent",
                color: isActive ? "#fff" : T.text,
                border: "none", borderRadius: 7, cursor: "pointer",
                fontSize: 12, fontWeight: 600,
              }}
            >{s.label}</button>
          )
        })}
      </div>

      {active === "tree"     && <TreeView     q={treeQ}  done={!!session?.phase5_done} />}
      {active === "links"    && <LinksView    q={linksQ} done={!!session?.phase7_done} />}
      {active === "calendar" && <CalendarView q={calQ}   done={!!session?.phase8_done} />}
      {active === "strategy" && <StrategyView q={stratQ} done={!!session?.phase9_done} />}
    </div>
  )
}

// ─── Sub-views ──────────────────────────────────────────────────────────────
function Loading()  { return <Card><div style={{ textAlign: "center", padding: 20 }}><Spinner /></div></Card> }
function NotYet({ what }) {
  return <Empty icon="⏳" title={`${what} not built yet`} hint="Run the strategy generation above first." />
}

function TreeView({ q, done }) {
  if (!done) return <NotYet what="Content tree" />
  if (q.isLoading) return <Loading />
  const tree = q.data?.tree
  if (!tree) return <NotYet what="Content tree" />

  // Tree shape: { tree: { universe: { name, type, pillars: [...] } } } OR { tree: { pillars: [...] } }
  const root    = tree.universe || tree
  const pillars = root.pillars || root.children || tree.nodes || []
  return (
    <Card>
      <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 12 }}>
        Content tree <Badge color={T.textSoft}>{pillars.length} pillars</Badge>
      </div>
      {pillars.length === 0
        ? <div style={{ fontSize: 12, color: T.textSoft }}>Empty tree.</div>
        : pillars.map((p, i) => <PillarNode key={i} node={p} />)}
    </Card>
  )
}

function PillarNode({ node }) {
  const name = node.name || node.pillar || node.label || node.keyword || "(unnamed)"
  const children = node.children || node.clusters || node.subtopics || node.topics || []
  return (
    <div style={{ borderLeft: `3px solid ${T.primary}`, paddingLeft: 12, marginBottom: 12 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>{name}</div>
      {children.length > 0 && (
        <div style={{ marginTop: 6, marginLeft: 8 }}>
          {children.map((c, i) => {
            const cn = c.name || c.cluster || c.label || c.keyword || ""
            const kws = c.keywords || c.children || []
            return (
              <div key={i} style={{ marginBottom: 6 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: T.textSoft }}>↳ {cn}</div>
                {kws.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4, marginLeft: 14 }}>
                    {kws.slice(0, 30).map((k, j) => (
                      <span key={j} style={{
                        background: T.primaryBg, color: T.primary,
                        padding: "1px 8px", borderRadius: 10, fontSize: 11,
                      }}>{typeof k === "string" ? k : (k.keyword || k.name)}</span>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function LinksView({ q, done }) {
  if (!done) return <NotYet what="Internal links" />
  if (q.isLoading) return <Loading />
  const links = q.data?.items || []
  if (!links.length) return <NotYet what="Internal links" />
  return (
    <Card>
      <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 12 }}>
        Internal links <Badge color={T.textSoft}>{links.length}</Badge>
      </div>
      <div style={{ maxHeight: 600, overflowY: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead style={{ position: "sticky", top: 0, background: T.card }}>
            <tr style={{ borderBottom: `1px solid ${T.border}`, color: T.textSoft, textTransform: "uppercase", fontSize: 10 }}>
              <th style={{ padding: 8, textAlign: "left" }}>Source</th>
              <th style={{ padding: 8, textAlign: "left" }}>Anchor</th>
              <th style={{ padding: 8, textAlign: "left" }}>Target</th>
              <th style={{ padding: 8, textAlign: "center" }}>Type</th>
            </tr>
          </thead>
          <tbody>
            {links.slice(0, 200).map((l, i) => (
              <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }}>
                <td style={{ padding: 8 }}>{l.from_page || l.source_url || l.source || l.from}</td>
                <td style={{ padding: 8, color: T.primary }}>{l.anchor_text || l.anchor}</td>
                <td style={{ padding: 8 }}>{l.to_page || l.target_url || l.target || l.to}</td>
                <td style={{ padding: 8, textAlign: "center" }}>
                  <Badge>{l.link_type || l.type || "—"}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function CalendarView({ q, done }) {
  if (!done) return <NotYet what="Content calendar" />
  if (q.isLoading) return <Loading />
  const items = q.data?.items || []
  if (!items.length) return <NotYet what="Content calendar" />
  return (
    <Card>
      <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 12 }}>
        Content calendar <Badge color={T.textSoft}>{items.length} entries</Badge>
      </div>
      <div style={{ maxHeight: 600, overflowY: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead style={{ position: "sticky", top: 0, background: T.card }}>
            <tr style={{ borderBottom: `1px solid ${T.border}`, color: T.textSoft, textTransform: "uppercase", fontSize: 10 }}>
              <th style={{ padding: 8, width: 90, textAlign: "left" }}>Date</th>
              <th style={{ padding: 8, width: 110, textAlign: "left" }}>Pillar</th>
              <th style={{ padding: 8, textAlign: "left" }}>Title</th>
              <th style={{ padding: 8, width: 100, textAlign: "left" }}>Keyword</th>
            </tr>
          </thead>
          <tbody>
            {items.slice(0, 300).map((it, i) => (
              <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }}>
                <td style={{ padding: 8 }}>{it.scheduled_date || it.publish_date || it.date}</td>
                <td style={{ padding: 8 }}><Badge>{it.pillar}</Badge></td>
                <td style={{ padding: 8, fontWeight: 500 }}>{it.title || it.suggested_title}</td>
                <td style={{ padding: 8, color: T.textSoft }}>{it.keyword || it.primary_keyword}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function StrategyView({ q, done }) {
  if (!done) return <NotYet what="Strategy document" />
  if (q.isLoading) return <Loading />
  const strat = q.data?.strategy
  if (!strat) return <NotYet what="Strategy document" />

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {/* ── Strategy Summary card ──────────────────────────────────── */}
      {strat.strategy_summary && (
        <Card>
          <div style={{ fontSize: 15, fontWeight: 700, color: T.text, marginBottom: 8 }}>
            {strat.strategy_summary.headline || "SEO Strategy"}
          </div>
          {strat.strategy_summary.biggest_opportunity && (
            <div style={{ marginBottom: 6, fontSize: 13, color: T.text }}>
              <span style={{ fontWeight: 600 }}>Opportunity: </span>
              {strat.strategy_summary.biggest_opportunity}
            </div>
          )}
          {strat.strategy_summary.why_we_win && (
            <div style={{ fontSize: 13, color: T.text }}>
              <span style={{ fontWeight: 600 }}>Advantage: </span>
              {strat.strategy_summary.why_we_win}
            </div>
          )}
        </Card>
      )}

      {/* Executive summary fallback */}
      {strat.executive_summary && !strat.strategy_summary && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 8 }}>Executive Summary</div>
          <div style={{ fontSize: 13, color: T.text, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
            {strat.executive_summary}
          </div>
        </Card>
      )}

      {/* ── Stats row ─────────────────────────────────────────────── */}
      {(strat.total_keywords != null || strat.total_blogs != null || strat.duration_weeks != null) && (
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {strat.total_keywords  != null && <Stat label="Keywords"  value={strat.total_keywords} />}
          {strat.total_blogs     != null && <Stat label="Blogs"     value={strat.total_blogs}    color={T.success} />}
          {strat.duration_weeks  != null && <Stat label="Duration"  value={`${strat.duration_weeks}w`} />}
          {strat.priority_pillars?.length > 0 && <Stat label="Pillars" value={strat.priority_pillars.length} color={T.primary} />}
          {strat.quick_wins?.length      > 0 && <Stat label="Quick Wins" value={strat.quick_wins.length} color="#f59e0b" />}
        </div>
      )}

      {/* ── Priority Pillars ──────────────────────────────────────── */}
      {strat.priority_pillars?.length > 0 && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 10 }}>Priority Pillars</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {strat.priority_pillars.map((p, i) => {
              const label = typeof p === "string" ? p : p.pillar || p.name || JSON.stringify(p)
              return (
                <span key={i} style={{
                  padding: "4px 12px", borderRadius: 20,
                  background: i === 0 ? T.successBg : T.primaryBg,
                  color: i === 0 ? T.success : T.primary,
                  fontSize: 12, fontWeight: 600,
                }}>
                  {i + 1}. {label}
                </span>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── Quick Wins ────────────────────────────────────────────── */}
      {strat.quick_wins?.length > 0 && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 10 }}>
            Quick Wins <Badge color={T.textSoft}>{strat.quick_wins.length}</Badge>
          </div>
          <ul style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 4 }}>
            {strat.quick_wins.map((kw, i) => {
              const text = typeof kw === "string" ? kw : kw.keyword || kw.title || kw.topic || JSON.stringify(kw)
              const diff = typeof kw === "object" ? (kw.difficulty || kw.competition || "") : ""
              return (
                <li key={i} style={{ fontSize: 12, color: T.text }}>
                  {text}
                  {diff && (
                    <span style={{
                      marginLeft: 8, padding: "1px 7px", borderRadius: 10,
                      background: T.warnBg, color: T.warn, fontSize: 10,
                    }}>{diff}</span>
                  )}
                </li>
              )
            })}
          </ul>
        </Card>
      )}

      {/* ── Content Gaps ──────────────────────────────────────────── */}
      {strat.content_gaps?.length > 0 && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 10 }}>
            Content Gaps <Badge color={T.textSoft}>{strat.content_gaps.length}</Badge>
          </div>
          <ul style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 4 }}>
            {strat.content_gaps.map((g, i) => (
              <li key={i} style={{ fontSize: 12, color: T.text }}>
                {typeof g === "string" ? g : g.topic || g.gap || g.title || JSON.stringify(g)}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* ── Pillar Strategy ───────────────────────────────────────── */}
      {strat.pillar_strategy?.length > 0 && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 10 }}>Pillar Strategy</div>
          <div style={{ display: "grid", gap: 10 }}>
            {strat.pillar_strategy.map((ps, i) => {
              const name = typeof ps === "string" ? ps : ps.pillar || ps.name || `Pillar ${i + 1}`
              const focus = typeof ps === "object" ? (ps.focus || ps.approach || ps.strategy || "") : ""
              const kws = typeof ps === "object" ? (ps.keywords || ps.top_keywords || []) : []
              return (
                <details key={i} style={{ border: `1px solid ${T.border}`, borderRadius: 7 }}>
                  <summary style={{ padding: "8px 12px", fontSize: 13, fontWeight: 600, cursor: "pointer", color: T.text }}>
                    {name}
                  </summary>
                  <div style={{ padding: "8px 12px", fontSize: 12, color: T.text }}>
                    {focus && <div style={{ marginBottom: 6 }}>{focus}</div>}
                    {kws.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {kws.slice(0, 20).map((k, j) => (
                          <span key={j} style={{
                            background: T.primaryBg, color: T.primary,
                            padding: "1px 8px", borderRadius: 10, fontSize: 11,
                          }}>
                            {typeof k === "string" ? k : k.keyword || k.name || k}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </details>
              )
            })}
          </div>
        </Card>
      )}

      {/* ── Weekly Plan ───────────────────────────────────────────── */}
      {strat.weekly_plan?.length > 0 && (
        <Card>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 10 }}>
            Weekly Plan <Badge color={T.textSoft}>{strat.weekly_plan.length} weeks</Badge>
          </div>
          <div style={{ maxHeight: 400, overflowY: "auto", display: "grid", gap: 8 }}>
            {strat.weekly_plan.slice(0, 16).map((week, wi) => (
              <div key={wi} style={{ padding: 10, background: T.card, border: `1px solid ${T.border}`, borderRadius: 7 }}>
                <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 6, display: "flex", gap: 8, alignItems: "center" }}>
                  Week {week.week ?? wi + 1}
                  {week.focus_pillar && <Badge>{week.focus_pillar}</Badge>}
                </div>
                {(week.articles || week.content || []).map((a, ai) => (
                  <div key={ai} style={{ fontSize: 12, color: T.textSoft, marginLeft: 4, marginBottom: 2 }}>
                    • {typeof a === "string" ? a : a.title || a.keyword || JSON.stringify(a)}
                    {typeof a === "object" && a.primary_keyword && (
                      <span style={{ color: T.textMute, marginLeft: 6 }}>({a.primary_keyword})</span>
                    )}
                  </div>
                ))}
              </div>
            ))}
            {strat.weekly_plan.length > 16 && (
              <div style={{ fontSize: 11, color: T.textMute, textAlign: "center" }}>
                Showing 16 of {strat.weekly_plan.length} weeks
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  )
}

function SectionBlock({ section }) {
  const title = section.title || section.name || ""
  const content = section.content ?? section.body ?? section.text ?? section
  const text = typeof content === "string" ? content : JSON.stringify(content, null, 2)
  return (
    <details open style={{ marginBottom: 12, border: `1px solid ${T.border}`, borderRadius: 7 }}>
      <summary style={{ padding: 10, fontSize: 13, fontWeight: 600, cursor: "pointer", color: T.text, background: "#f9fafb" }}>
        {title}
      </summary>
      <pre style={{
        padding: 12, fontSize: 12, lineHeight: 1.5,
        whiteSpace: "pre-wrap", wordBreak: "break-word",
        margin: 0, color: T.text, background: T.card,
        fontFamily: "inherit",
      }}>{text}</pre>
    </details>
  )
}
