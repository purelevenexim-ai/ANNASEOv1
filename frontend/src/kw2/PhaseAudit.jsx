/**
 * PhaseAudit — Pillar + Modifier Extraction Audit
 * Tests PillarExtractor and ModifierExtractor against the current session profile.
 * Shows diffs, test results, and timing. Saves report to server.
 */
import React, { useState } from "react"
import { runPillarAudit } from "./api"

// ── Helpers ──────────────────────────────────────────────────────────────────

function Badge({ children, color = "#6b7280" }) {
  return (
    <span style={{
      display: "inline-block", padding: "1px 7px", borderRadius: 10,
      fontSize: 11, fontWeight: 600, background: color + "22", color,
    }}>
      {children}
    </span>
  )
}

function Section({ title, icon, children, border = "#e5e7eb" }) {
  return (
    <div style={{ border: `1px solid ${border}`, borderRadius: 10, overflow: "hidden", marginBottom: 16 }}>
      <div style={{
        padding: "10px 16px", background: "#f9fafb", borderBottom: `1px solid ${border}`,
        fontWeight: 700, fontSize: 14, display: "flex", alignItems: "center", gap: 8,
      }}>
        <span>{icon}</span> {title}
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  )
}

function PillarRow({ label, items, color }) {
  if (!items || items.length === 0) return null
  return (
    <div style={{ marginBottom: 8 }}>
      <span style={{ fontSize: 12, color: "#6b7280", fontWeight: 600, marginRight: 8 }}>{label}</span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 4 }}>
        {items.map((p) => (
          <span key={p} style={{
            padding: "2px 9px", borderRadius: 12, fontSize: 12, fontWeight: 500,
            background: color + "18", color, border: `1px solid ${color}44`,
          }}>{p}</span>
        ))}
      </div>
    </div>
  )
}

function TestRow({ result }) {
  const icon = result.pass ? "✅" : "❌"
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "24px 1fr 120px 120px",
      gap: 8, alignItems: "start", padding: "6px 0",
      borderBottom: "1px solid #f3f4f6", fontSize: 13,
    }}>
      <span>{icon}</span>
      <span style={{ color: "#374151" }}>{result.input}</span>
      <span style={{ color: "#6b7280", fontFamily: "monospace" }}>{result.expected}</span>
      <span style={{
        fontFamily: "monospace",
        color: result.pass ? "#059669" : "#dc2626", fontWeight: result.pass ? 400 : 600,
      }}>{result.got || "(empty)"}</span>
    </div>
  )
}

function StatBox({ label, value, sub, color = "#1d4ed8" }) {
  return (
    <div style={{
      background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 8,
      padding: "12px 16px", minWidth: 110,
    }}>
      <div style={{ fontSize: 22, fontWeight: 800, color }}>{value}</div>
      <div style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PhaseAudit({ projectId, sessionId }) {
  const [running, setRunning] = useState(false)
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)

  async function run() {
    setRunning(true)
    setError(null)
    setReport(null)
    try {
      const data = await runPillarAudit(projectId, sessionId)
      setReport(data)
    } catch (e) {
      setError(e?.message || "Audit failed")
    } finally {
      setRunning(false)
    }
  }

  const s = report?.summary
  const p = report?.pillars
  const m = report?.modifiers
  const t = report?.tests

  const testPassRate = t ? Math.round((t.passed / t.total) * 100) : 0
  const testColor = testPassRate >= 85 ? "#059669" : testPassRate >= 60 ? "#d97706" : "#dc2626"

  return (
    <div style={{ maxWidth: 820, margin: "0 auto", padding: 24 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "#111827" }}>
            🔬 Pillar &amp; Modifier Audit
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6b7280" }}>
            Tests PillarExtractor and ModifierExtractor against your current profile.
          </p>
        </div>
        <button
          onClick={run}
          disabled={running}
          style={{
            padding: "9px 20px", borderRadius: 8, border: "none",
            background: running ? "#9ca3af" : "#1d4ed8", color: "#fff",
            fontWeight: 700, fontSize: 14, cursor: running ? "not-allowed" : "pointer",
          }}
        >
          {running ? "Running…" : "▶ Run Audit"}
        </button>
      </div>

      {error && (
        <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: 12, color: "#dc2626", marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!report && !running && (
        <div style={{ textAlign: "center", padding: 60, color: "#9ca3af", fontSize: 14 }}>
          Click <strong>Run Audit</strong> to test extraction against your current profile.
        </div>
      )}

      {running && (
        <div style={{ textAlign: "center", padding: 60, color: "#6b7280", fontSize: 14 }}>
          ⏳ Running extraction engines…
        </div>
      )}

      {report && (
        <>
          {/* Summary bar */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
            <StatBox label="Products" value={s.products_count} sub="in catalog" color="#1d4ed8" />
            <StatBox label="Stored Pillars" value={s.stored_pillars} sub="in profile" color="#7c3aed" />
            <StatBox label="Fresh Pillars" value={s.fresh_pillars} sub="re-extracted" color="#0f766e" />
            <StatBox label="Pillar Match" value={`${s.pillar_match_pct}%`} sub="stored ∩ fresh" color={s.pillar_match_pct >= 80 ? "#059669" : "#d97706"} />
            <StatBox label="Tests" value={`${s.tests_passed}/${s.tests_total}`} sub="pass rate" color={testColor} />
            <StatBox label="Speed" value={`${s.pillar_ms}ms`} sub="pillar extract" color="#6b7280" />
          </div>

          {/* Pillars */}
          <Section title="Pillar Extraction" icon="🏷️" border="#dbeafe">
            <PillarRow label="Stored (profile)" items={p.stored} color="#7c3aed" />
            <PillarRow label="Fresh (re-extracted)" items={p.fresh} color="#0f766e" />
            {p.diff.only_stored.length > 0 && (
              <PillarRow
                label="⚠ Only in stored — may be stale or manual"
                items={p.diff.only_stored}
                color="#d97706"
              />
            )}
            {p.diff.only_fresh.length > 0 && (
              <PillarRow
                label="✨ Only in fresh — not stored yet"
                items={p.diff.only_fresh}
                color="#2563eb"
              />
            )}
            <div style={{ marginTop: 10, fontSize: 12, color: "#9ca3af" }}>
              Extracted in {p.timing_ms}ms · {p.diff.matched.length} matched, {p.diff.only_stored.length} stale, {p.diff.only_fresh.length} new
            </div>
          </Section>

          {/* Modifiers */}
          <Section title="Modifier Extraction" icon="🎛️" border="#d1fae5">
            <PillarRow label="Stored" items={m.stored} color="#374151" />
            {m.fresh_flat.length > 0 ? (
              <>
                <PillarRow label="Intent" items={m.fresh_structured?.intent || []} color="#1d4ed8" />
                <PillarRow label="Quality" items={m.fresh_structured?.quality || []} color="#059669" />
                <PillarRow label="Geo" items={m.fresh_structured?.geo || []} color="#7c3aed" />
                <PillarRow label="Audience" items={m.fresh_structured?.audience || []} color="#d97706" />
                {m.diff.only_stored.length > 0 && (
                  <PillarRow label="⚠ Only stored" items={m.diff.only_stored} color="#dc2626" />
                )}
                {m.diff.only_fresh.length > 0 && (
                  <PillarRow label="✨ Only fresh" items={m.diff.only_fresh} color="#2563eb" />
                )}
              </>
            ) : (
              <div style={{ color: "#9ca3af", fontSize: 13 }}>
                No modifiers extracted — run Phase 2 first to build keyword universe.
              </div>
            )}
            <div style={{ marginTop: 10, fontSize: 12, color: "#9ca3af" }}>
              Input: {m.input_count} {m.input_source === "universe" ? "universe keywords" : "stored modifiers"} · {m.timing_ms}ms
            </div>
          </Section>

          {/* Test Cases */}
          <Section title="Extraction Test Cases" icon="🧪" border={testColor + "44"}>
            <div style={{ display: "grid", gridTemplateColumns: "24px 1fr 120px 120px", gap: 8, marginBottom: 6 }}>
              <span />
              <span style={{ fontSize: 11, fontWeight: 700, color: "#9ca3af", textTransform: "uppercase" }}>Input</span>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#9ca3af", textTransform: "uppercase" }}>Expected</span>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#9ca3af", textTransform: "uppercase" }}>Got</span>
            </div>
            {t.results.map((r, i) => <TestRow key={i} result={r} />)}
            <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontWeight: 700, fontSize: 14, color: testColor }}>
                {t.passed}/{t.total} passed ({testPassRate}%)
              </span>
              {testPassRate < 100 && (
                <span style={{ fontSize: 12, color: "#9ca3af" }}>
                  — failing tests indicate noise words need tuning in PillarExtractor
                </span>
              )}
            </div>
          </Section>

          {/* File saved */}
          {report.saved_to && (
            <div style={{
              background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8,
              padding: "10px 16px", fontSize: 13, color: "#15803d",
            }}>
              ✅ Report saved → <code style={{ fontFamily: "monospace" }}>{report.saved_to}</code>
            </div>
          )}
        </>
      )}
    </div>
  )
}
