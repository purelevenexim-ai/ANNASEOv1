/**
 * ContentGenerationFlow.jsx
 * 10-Step SEO Content Generation Pipeline UI
 * Shows real-time progress through all 10 steps with detailed status
 */

import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'

const T = {
  purple: "#7F77DD", teal: "#1D9E75", purpleDark: "#534AB7", amber: "#D97706",
  border: "#E5E3DC", text: "#1A1A1A", textSoft: "#666", purpleLight: "#EEEDFE",
  red: "#DC2626", grayLight: "#F8F7F4", gray: "#999"
}

const STEPS = [
  { num: 1, name: "Topic Analysis", icon: "🔍", desc: "Crawl & analyze topic" },
  { num: 2, name: "Structure", icon: "📋", desc: "Generate outline" },
  { num: 3, name: "Verification", icon: "✓", desc: "Verify structure" },
  { num: 4, name: "Internal Links", icon: "🔗", desc: "Plan linking" },
  { num: 5, name: "References", icon: "📚", desc: "Gather sources" },
  { num: 6, name: "Writing", icon: "✍️", desc: "Draft content" },
  { num: 7, name: "AI Review", icon: "🤖", desc: "Review quality" },
  { num: 8, name: "Issue Check", icon: "⚠️", desc: "Identify issues" },
  { num: 9, name: "Redevelop", icon: "🔨", desc: "Fix issues" },
  { num: 10, name: "Final Polish", icon: "⭐", desc: "Final review" },
]

function ContentGenerationFlow({ projectId, keyword, onComplete }) {
  const [runId, setRunId] = useState(null)
  const [steps, setSteps] = useState(STEPS.map(s => ({ ...s, status: "pending", progress: 0 })))
  const [finalContent, setFinalContent] = useState(null)
  const [error, setError] = useState(null)

  // Start pipeline
  const startMut = useMutation({
    mutationFn: () => fetch(`/api/content/${projectId}/generate-advanced`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, intent: "informational" })
    }).then(r => r.json()),
    onSuccess: (data) => {
      setRunId(data.run_id)
      subscribeToProgress(data.run_id)
    },
    onError: (err) => setError(err.message)
  })

  // Subscribe to SSE stream
  const subscribeToProgress = (id) => {
    const eventSource = new EventSource(`/api/content/${projectId}/generate-advanced/${id}/stream`)
    
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      
      if (data.status === "completed") {
        eventSource.close()
        fetchFinalContent(id)
      } else if (data.status === "failed") {
        eventSource.close()
        setError(data.error)
      } else if (data.step) {
        // Update step progress
        setSteps(prev => {
          const updated = [...prev]
          const stepIdx = data.step - 1
          if (updated[stepIdx]) {
            updated[stepIdx].status = data.status
            updated[stepIdx].progress = data.status === "completed" ? 100 : 50
          }
          return updated
        })
      }
    }
    
    eventSource.onerror = () => {
      eventSource.close()
      setError("Connection lost")
    }
  }

  // Fetch final article
  const fetchFinalContent = async (id) => {
    try {
      const res = await fetch(`/api/content/${projectId}/generate-advanced/${id}/final`)
      if (!res.ok) throw new Error("Failed to fetch final content")
      const data = await res.json()
      setFinalContent(data)
      onComplete?.(data)
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    if (!runId) return
    
    // Poll for state updates
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/content/${projectId}/generate-advanced/${runId}/state`)
        if (res.status === 404) {
          clearInterval(interval)
          return
        }
        if (res.ok) {
          const state = await res.json()
          // Update step statuses based on versions
          if (state.versions) {
            setSteps(prev => prev.map(s => ({
              ...s,
              status: state.versions.some(v => v.step === s.num) ? "completed" : "pending"
            })))
          }
        }
      } catch (e) {
        // Silent
      }
    }, 1000)
    
    return () => clearInterval(interval)
  }, [runId, projectId])

  const completedCount = steps.filter(s => s.status === "completed").length
  const inProgressStep = steps.find(s => s.status === "in_progress")

  return (
    <div style={{ padding: "20px" }}>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 22, color: T.text }}>10-Step Content Generation</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: T.textSoft }}>
          Comprehensive SEO blog generation: Research → Structure → Writing → Review → Polish
        </p>
      </div>

      {error && (
        <div style={{ padding: 12, background: "#FEE2E2", border: `1px solid ${T.red}`, borderRadius: 8, marginBottom: 16, color: T.red, fontSize: 12 }}>
          Error: {error}
        </div>
      )}

      {!runId && (
        <button
          onClick={() => startMut.mutate()}
          disabled={startMut.isPending}
          style={{
            padding: "10px 20px",
            background: T.purple,
            color: "white",
            border: "none",
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
            marginBottom: 24
          }}
        >
          {startMut.isPending ? "Starting..." : "Start Generation"}
        </button>
      )}

      {runId && (
        <>
          {/* Progress bar */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: T.text, marginBottom: 6 }}>
              Progress: {completedCount} / 10 steps complete
            </div>
            <div style={{ width: "100%", height: 8, background: T.grayLight, borderRadius: 4, overflow: "hidden" }}>
              <div style={{
                width: `${(completedCount / 10) * 100}%`,
                height: "100%",
                background: T.teal,
                transition: "width 0.3s ease"
              }} />
            </div>
          </div>

          {/* Step indicator timeline */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(80px, 1fr))",
            gap: 8,
            marginBottom: 24
          }}>
            {steps.map((step, i) => (
              <div key={step.num} style={{ textAlign: "center" }}>
                <div style={{
                  width: 48,
                  height: 48,
                  margin: "0 auto 6px",
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 20,
                  background: step.status === "completed" ? T.teal + "20" : step.status === "in_progress" ? T.amber + "20" : T.grayLight,
                  border: `2px solid ${step.status === "completed" ? T.teal : step.status === "in_progress" ? T.amber : T.border}`,
                  fontWeight: 700,
                  color: step.status === "completed" ? T.teal : step.status === "in_progress" ? T.amber : T.gray
                }}>
                  {step.status === "completed" ? "✓" : `${step.num}`}
                </div>
                <div style={{ fontSize: 10, fontWeight: 600, color: T.text }}>{step.name}</div>
                <div style={{ fontSize: 9, color: T.textSoft }}>{step.icon}</div>
              </div>
            ))}
          </div>

          {/* Detailed steps */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {steps.map((step) => (
              <div key={step.num} style={{
                padding: 12,
                background: step.status === "completed" ? T.purpleLight : "#fff",
                border: `1px solid ${step.status === "completed" ? T.purple + "30" : T.border}`,
                borderRadius: 8,
                display: "flex",
                alignItems: "center",
                gap: 12
              }}>
                <div style={{
                  width: 36,
                  height: 36,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: step.status === "completed" ? T.teal : step.status === "in_progress" ? T.amber : T.grayLight,
                  color: step.status === "in_progress" || step.status === "completed" ? "#fff" : T.gray,
                  fontWeight: 700,
                  fontSize: 14,
                  flexShrink: 0
                }}>
                  {step.status === "completed" ? "✓" : step.status === "in_progress" ? "◐" : step.num}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>
                    {step.icon} {step.name}
                  </div>
                  <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
                    {step.desc}
                  </div>
                  {step.status === "in_progress" && (
                    <div style={{ marginTop: 6, width: "100%", height: 4, background: T.grayLight, borderRadius: 2, overflow: "hidden" }}>
                      <div style={{
                        height: "100%",
                        background: T.amber,
                        animation: "pulse 1.5s ease-in-out infinite",
                        width: "60%"
                      }} />
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Final article preview */}
          {finalContent && (
            <div style={{ marginTop: 24 }}>
              <h3 style={{ margin: 0, fontSize: 16, color: T.text, marginBottom: 12 }}>Generated Article</h3>
              <div style={{
                padding: 16,
                background: T.purpleLight,
                border: `1px solid ${T.purple}40`,
                borderRadius: 8
              }}>
                <div style={{ fontSize: 11, color: T.textSoft, marginBottom: 8 }}>
                  <strong>Keyword:</strong> {finalContent.keyword} | <strong>Words:</strong> {finalContent.word_count} | <strong>Version:</strong> {finalContent.version}
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, color: T.purple, marginBottom: 8 }}>
                  SEO Score: {finalContent.scores.seo_score || 0}/100
                </div>
                <div style={{
                  maxHeight: 300,
                  overflowY: "auto",
                  padding: 12,
                  background: "#fff",
                  borderRadius: 4,
                  fontSize: 12,
                  lineHeight: 1.5,
                  dangerouslySetInnerHTML: { __html: finalContent.content_html }
                }} />
              </div>
            </div>
          )}
        </>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1 }
          50% { opacity: 0.5 }
        }
      `}</style>
    </div>
  )
}

export default ContentGenerationFlow
