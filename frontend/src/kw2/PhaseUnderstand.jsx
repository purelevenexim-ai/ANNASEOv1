/**
 * PhaseUnderstand (v2) — Merged Business Analysis + Intelligence wizard.
 *
 * Wraps Phase1 (Setup) and PhaseBI (Intelligence) into one super-phase
 * with internal step navigation: Setup → Intelligence → Done
 */
import React, { useState, useCallback } from "react"
import Phase1 from "./Phase1"
import PhaseBI from "./PhaseBI"
import { Card } from "./shared"
import * as api from "./api"

const STEPS = [
  { key: "setup", label: "Business Setup", icon: "🏢", description: "Domain, pillars, products, audience" },
  { key: "intel", label: "Intelligence", icon: "🔍", description: "Crawl, competitors, strategy" },
]

export default function PhaseUnderstand({ projectId, sessionId, onComplete }) {
  const [step, setStep] = useState(0) // 0=setup, 1=intel
  const [setupDone, setSetupDone] = useState(false)

  const handleSetupComplete = useCallback(() => {
    setSetupDone(true)
    setStep(1)
  }, [])

  const handleIntelComplete = useCallback(async () => {
    // Mark understand=done in backend so inferInitialPhase resumes at EXPAND on reload
    try {
      await api.updatePhaseStatus(projectId, sessionId, "understand", "done")
    } catch { /* non-fatal */ }
    // Refresh session data
    if (onComplete) onComplete()
  }, [projectId, sessionId, onComplete])

  return (
    <div>
      {/* Mini stepper */}
      <div style={{
        display: "flex", gap: 0, marginBottom: 16,
        background: "#f9fafb", borderRadius: 10, padding: 4,
        border: "1px solid #e5e7eb",
      }}>
        {STEPS.map((s, i) => {
          const active = step === i
          const done = i === 0 ? setupDone : false
          return (
            <button
              key={s.key}
              onClick={() => {
                if (i === 0 || setupDone) setStep(i)
              }}
              style={{
                flex: 1, display: "flex", alignItems: "center", gap: 8,
                padding: "10px 16px", border: "none", borderRadius: 8,
                background: active ? "#fff" : "transparent",
                boxShadow: active ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                cursor: (i === 0 || setupDone) ? "pointer" : "not-allowed",
                opacity: (i === 0 || setupDone) ? 1 : 0.5,
                transition: "all 0.2s",
              }}
            >
              <span style={{
                width: 28, height: 28, borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14,
                background: done ? "#dcfce7" : active ? "#dbeafe" : "#f3f4f6",
                color: done ? "#166534" : active ? "#1e40af" : "#9ca3af",
                fontWeight: 600,
              }}>
                {done ? "✓" : s.icon}
              </span>
              <div style={{ textAlign: "left" }}>
                <div style={{ fontSize: 13, fontWeight: active ? 600 : 400, color: active ? "#111827" : "#6b7280" }}>
                  {s.label}
                </div>
                <div style={{ fontSize: 11, color: "#9ca3af" }}>{s.description}</div>
              </div>
            </button>
          )
        })}
      </div>

      {/* Step content */}
      {step === 0 && (
        <Phase1
          projectId={projectId}
          sessionId={sessionId}
          onComplete={handleSetupComplete}
          onNext={handleSetupComplete}
        />
      )}
      {step === 1 && (
        <PhaseBI
          projectId={projectId}
          sessionId={sessionId}
          onProceedPhase="UNDERSTAND"
          onComplete={handleIntelComplete}
        />
      )}
    </div>
  )
}
