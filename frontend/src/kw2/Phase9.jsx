/**
 * Phase 9 — Strategy Generation.
 * AI-powered SEO strategy based on full pipeline results.
 */
import React, { useCallback, useEffect, useState, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, usePhaseRunner, PhaseResult, NotificationList } from "./shared"
import BlueprintCard from "../components/BlueprintCard"

const API = import.meta.env.VITE_API_URL || ""
function _token() { return localStorage.getItem("annaseo_token") || "" }

export default function Phase9({ projectId, sessionId, onComplete, autoRun, hideRunButton }) {
  const { strategy, setStrategy } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P9")
  const qc = useQueryClient()

  // ── Blueprints state ─────────────────────────────────────────
  const [blueprints, setBlueprints] = useState([])
  const [bpLoading, setBpLoading] = useState(false)
  const [bpError, setBpError] = useState(null)
  const [bpProgress, setBpProgress] = useState([])
  const [bpGenerating, setBpGenerating] = useState(false)
  const abortRef = useRef(null)

  // Load existing blueprints for this session
  useEffect(() => {
    if (!projectId) return
    const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}&limit=20` : "?limit=20"
    fetch(`${API}/api/strategy-v2/${projectId}/blueprints${qs}`, {
      headers: { Authorization: `Bearer ${_token()}` },
    })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setBlueprints(data.blueprints || []))
      .catch(() => {})
  }, [projectId, sessionId])

  async function generateBlueprints() {
    if (!strategy) return
    // gather keywords from quick_wins + priority_pillars
    const kws = []
    ;(strategy.quick_wins || []).slice(0, 5).forEach(k => {
      const kw = typeof k === "string" ? k : k.keyword || k.title || ""
      if (kw) kws.push(kw)
    })
    if (kws.length === 0) {
      ;(strategy.priority_pillars || []).slice(0, 5).forEach(p => {
        const kw = typeof p === "string" ? p : p.pillar || p.name || ""
        if (kw) kws.push(kw)
      })
    }
    if (kws.length === 0) { setBpError("No keywords found in strategy to generate blueprints"); return }

    setBpGenerating(true)
    setBpError(null)
    setBpProgress([{ id: "start", label: "Starting blueprint generation…", status: "running" }])

    try {
      const controller = new AbortController()
      abortRef.current = controller
      const resp = await fetch(`${API}/api/strategy-v2/${projectId}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${_token()}` },
        body: JSON.stringify({ keywords: kws, session_id: sessionId || "" }),
        signal: controller.signal,
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          let evt; try { evt = JSON.parse(raw) } catch { continue }
          const type = evt.type || evt.event
          if (type === "complete") {
            setBlueprints(evt.blueprints || [])
            setBpProgress(prev => [...prev, { id: "done", label: `✓ ${evt.total} blueprints generated`, status: "done" }])
          } else if (type === "error") {
            setBpProgress(prev => [...prev, { id: `err_${Date.now()}`, label: evt.message, status: "error" }])
          } else if (type === "blueprint_done") {
            setBpProgress(prev => [...prev, { id: `bp_${evt.keyword}_${evt.angle_index}`, label: `Blueprint ready (score ${evt.score})`, status: "done" }])
          } else if (type === "progress") {
            setBpProgress(prev => [...prev, { id: `p_${Date.now()}`, label: evt.message, status: evt.done ? "done" : "running" }])
          }
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") setBpError(e.message || "Unknown error")
    }
    setBpGenerating(false)
  }

  function handleContentStarted() {
    toast("Content generation started!", "success")
  }

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    log("Generating SEO strategy (AI)...", "info")
    try {
      const data = await api.runPhase9(projectId, sessionId)
      setStrategy(data.strategy)
      log("SEO strategy generated successfully", "success")
      toast("SEO strategy generated!", "success")
      // Invalidate Strategy Hub cache so it immediately reflects the new strategy
      qc.invalidateQueries({ queryKey: ["kw2-strategy-sessions", projectId] })
      qc.invalidateQueries({ queryKey: ["kw2-session-strategy", projectId, sessionId] })
      onComplete()
    } catch (e) {
      setError(e.message)
      log(`Failed: ${e.message}`, "error")
      toast(`Phase 9 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }, [projectId, sessionId])

  useEffect(() => {
    async function load() {
      try {
        const data = await api.getStrategy(projectId, sessionId)
        if (data.strategy) setStrategy(data.strategy)
      } catch { /* ignore */ }
    }
    load()
  }, [])

  useEffect(() => { if (autoRun) run() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card title="Phase 9: SEO Strategy" actions={hideRunButton ? null : <RunButton onClick={run} loading={loading}>Generate Strategy</RunButton>}>
      {error && <p style={{ color: "#dc2626", fontSize: 13 }}>{error}</p>}

      {strategy && (
        <div style={{ fontSize: 13 }}>
          {strategy.strategy_summary && (
            <div style={{ marginBottom: 16, padding: 12, background: "#f0fdf4", borderRadius: 6 }}>
              <h4 style={{ margin: "0 0 4px", fontSize: 14 }}>{strategy.strategy_summary.headline}</h4>
              {strategy.strategy_summary.biggest_opportunity && (
                <p style={{ margin: "4px 0", color: "#166534" }}><strong>Opportunity:</strong> {strategy.strategy_summary.biggest_opportunity}</p>
              )}
              {strategy.strategy_summary.why_we_win && (
                <p style={{ margin: "4px 0", color: "#166534" }}><strong>Advantage:</strong> {strategy.strategy_summary.why_we_win}</p>
              )}
            </div>
          )}

          {strategy.executive_summary && !strategy.strategy_summary && (
            <div style={{ marginBottom: 16, padding: 12, background: "#f0fdf4", borderRadius: 6 }}>
              <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{strategy.executive_summary}</p>
            </div>
          )}

          {strategy.priority_pillars?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Priority Pillars</h4>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {strategy.priority_pillars.map((p, i) => {
                  const label = typeof p === "string" ? p : p.pillar || p.name || JSON.stringify(p)
                  return (
                    <Badge key={i} color={i === 0 ? "green" : "blue"}>{i + 1}. {label}</Badge>
                  )
                })}
              </div>
            </div>
          )}

          {strategy.quick_wins?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Quick Wins</h4>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {strategy.quick_wins.map((kw, i) => (
                  <li key={i} style={{ fontSize: 12, color: "#374151" }}>{typeof kw === "string" ? kw : kw.keyword || kw.title}</li>
                ))}
              </ul>
            </div>
          )}

          {strategy.content_gaps?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Content Gaps</h4>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {strategy.content_gaps.map((g, i) => <li key={i} style={{ fontSize: 12, color: "#374151" }}>{typeof g === "string" ? g : g.topic || g.gap || g.title || ""}</li>)}
              </ul>
            </div>
          )}

          {strategy.weekly_plan?.length > 0 && (
            <div>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Weekly Plan</h4>
              <div style={{ maxHeight: 300, overflow: "auto" }}>
                {strategy.weekly_plan.slice(0, 12).map((week) => (
                  <div key={week.week} style={{ marginBottom: 8, padding: 8, background: "#f9fafb", borderRadius: 4 }}>
                    <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 4 }}>
                      Week {week.week} — <Badge color="blue">{week.focus_pillar}</Badge>
                    </div>
                    {(week.articles || []).map((a, i) => (
                      <div key={i} style={{ fontSize: 12, color: "#374151", marginLeft: 12 }}>
                        • {typeof a === "string" ? a : a.title || a.keyword || JSON.stringify(a)} {a.primary_keyword ? <span style={{ color: "#9ca3af" }}>({a.primary_keyword})</span> : null}
                      </div>
                    ))}
                  </div>
                ))}
                {strategy.weekly_plan.length > 12 && (
                  <p style={{ color: "#9ca3af", fontSize: 11 }}>Showing 12 of {strategy.weekly_plan.length} weeks</p>
                )}
              </div>
            </div>
          )}

          <PhaseResult
            phaseNum={9}
            stats={[
              { label: "Pillars", value: strategy.priority_pillars?.length || 0, color: "#3b82f6" },
              { label: "Quick Wins", value: strategy.quick_wins?.length || 0, color: "#10b981" },
              { label: "Weeks Planned", value: strategy.weekly_plan?.length || 0, color: "#8b5cf6" },
            ]}
          />
        </div>
      )}

      {/* ── Content Blueprints Section ── */}
      {strategy && (
        <div style={{ marginTop: 20, borderTop: "1px solid #e5e7eb", paddingTop: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, margin: 0, color: "#111827" }}>
              📋 Content Blueprints
            </h3>
            {!bpGenerating && (
              <button
                onClick={generateBlueprints}
                disabled={bpLoading}
                style={{
                  background: "#2563eb", color: "#fff", border: "none",
                  padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                  fontSize: 12, fontWeight: 600,
                }}
              >
                {blueprints.length > 0 ? "Regenerate Blueprints" : "Generate Blueprints"}
              </button>
            )}
            {bpGenerating && (
              <button
                onClick={() => abortRef.current?.abort()}
                style={{
                  background: "#f3f4f6", color: "#374151", border: "1px solid #d1d5db",
                  padding: "7px 14px", borderRadius: 6, cursor: "pointer", fontSize: 12,
                }}
              >
                Cancel
              </button>
            )}
          </div>

          <p style={{ fontSize: 12, color: "#6b7280", margin: "0 0 12px" }}>
            AI-generated content blueprints from your strategy keywords — uniquely angled, QA scored
          </p>

          {bpError && (
            <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, padding: "8px 12px", marginBottom: 10 }}>
              <p style={{ color: "#dc2626", fontSize: 12, margin: 0 }}>{bpError}</p>
            </div>
          )}

          {bpGenerating && (
            <div style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6, padding: 10, marginBottom: 12 }}>
              {bpProgress.map((item, i) => {
                const color = item.status === "done" ? "#16a34a" : item.status === "error" ? "#dc2626" : "#2563eb"
                const icon = item.status === "done" ? "✓" : item.status === "error" ? "✗" : "⟳"
                return (
                  <div key={item.id || i} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0", fontSize: 12 }}>
                    <span style={{ color, width: 14, display: "inline-block", fontWeight: 700 }}>{icon}</span>
                    <span style={{ color: "#374151" }}>{item.label}</span>
                  </div>
                )
              })}
            </div>
          )}

          {blueprints.length > 0 && !bpGenerating && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(380px,1fr))", gap: 12 }}>
              {blueprints.map((bp, i) => (
                <BlueprintCard
                  key={bp.id || i}
                  blueprint={bp}
                  projectId={projectId}
                  onContentStarted={handleContentStarted}
                />
              ))}
            </div>
          )}

          {blueprints.length === 0 && !bpGenerating && (
            <p style={{ fontSize: 12, color: "#9ca3af", fontStyle: "italic" }}>
              No blueprints yet. Click "Generate Blueprints" to create content blueprints from your strategy keywords.
            </p>
          )}
        </div>
      )}

      <NotificationList notifications={notifications} />
    </Card>
  )
}
