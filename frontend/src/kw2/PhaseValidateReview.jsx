/**
 * PhaseValidateReview — merged Phase3 (Validation) + Phase3Review.
 * Stacked layout: validation progress/button on top, keyword edit table below.
 * Validation section collapses to a summary when done. Review always visible.
 * "Proceed" in Review section advances the pipeline.
 */
import React, { useState, useCallback } from "react"
import Phase3 from "./Phase3"
import Phase3Review from "./Phase3Review"

export default function PhaseValidateReview({ projectId, sessionId, onComplete, onContinue }) {
  const [validationDone, setValidationDone] = useState(false)
  const [reviewKey, setReviewKey] = useState(0)

  const handleValidationComplete = useCallback(() => {
    setValidationDone(true)
    setReviewKey((k) => k + 1) // force Phase3Review to reload keywords
  }, [])

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ── Validation Section ─────────────────────────────────── */}
      <Phase3
        projectId={projectId}
        sessionId={sessionId}
        onComplete={handleValidationComplete}
        onSwitchToReview={handleValidationComplete}
      />

      {/* ── Divider ────────────────────────────────────────────── */}
      <div style={{ borderTop: "2px solid #e5e7eb", margin: "4px 0" }} />

      {/* ── Review / Edit Section ──────────────────────────────── */}
      <Phase3Review
        key={reviewKey}
        projectId={projectId}
        sessionId={sessionId}
        onProceed={onContinue || onComplete}  // onContinue = store.goNextPhase() → advances to Phase 4
        onRegenerate={() => { setValidationDone(false); setReviewKey((k) => k + 1) }}
        onComplete={onComplete}
      />
    </div>
  )
}
