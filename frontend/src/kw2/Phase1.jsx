/**
 * Phase 1 — Business Analysis.
 * User provides domain + optional manual inputs, AI analyzes and builds profile.
 */
import React, { useState, useEffect } from "react"
import useKw2Store from "./store"
import * as api from "./api"
import { Card, RunButton, Badge, StatsRow, usePhaseRunner, PhaseResult, NotificationList, ConsolePanel } from "./shared"

export default function Phase1({ projectId, sessionId, onComplete }) {
  const { profile, setProfile, setActivePhase } = useKw2Store()
  const { loading, setLoading, error, setError, notifications, log, toast } = usePhaseRunner("P1")

  const [form, setForm] = useState({
    domain: "",
    pillars: "",
    product_catalog: "",
    modifiers: "",
    negative_scope: "",
    audience: "",
    geo_scope: "",
    business_type: "",
    competitor_urls: "",
  })

  useEffect(() => {
    if (profile) {
      setForm((f) => ({
        ...f,
        domain: profile.domain || "",
        pillars: (profile.pillars || []).join(", "),
        product_catalog: (profile.product_catalog || []).join(", "),
        modifiers: (profile.modifiers || []).join(", "),
        negative_scope: (profile.negative_scope || []).join(", "),
        audience: (profile.audience || []).join(", "),
        geo_scope: profile.geo_scope || "",
        business_type: profile.business_type || "",
      }))
    }
  }, [profile])

  const run = async () => {
    setLoading(true)
    setError(null)
    log(`Analyzing ${form.domain}...`, "info")
    try {
      const body = {
        domain: form.domain.trim(),
        pillars: form.pillars.split(",").map((s) => s.trim()).filter(Boolean),
        product_catalog: form.product_catalog.split(",").map((s) => s.trim()).filter(Boolean),
        modifiers: form.modifiers.split(",").map((s) => s.trim()).filter(Boolean),
        negative_scope: form.negative_scope.split(",").map((s) => s.trim()).filter(Boolean),
        audience: form.audience.split(",").map((s) => s.trim()).filter(Boolean),
        geo_scope: form.geo_scope.trim(),
        business_type: form.business_type.trim(),
        competitor_urls: form.competitor_urls.split(",").map((s) => s.trim()).filter(Boolean),
      }
      const { profile: result } = await api.runPhase1(projectId, sessionId, body)
      setProfile(result)
      const pillars = (result.pillars || []).length
      const products = (result.product_catalog || []).length
      const confidence = ((result.confidence_score || 0) * 100).toFixed(0)
      log(`Analysis complete: ${pillars} pillars, ${products} products, confidence ${confidence}%`, "success")
      toast(`Business analysis complete — ${pillars} pillars found`, "success")
      onComplete()
    } catch (e) {
      setError(e.message)
      log(`Analysis failed: ${e.message}`, "error")
      toast(`Phase 1 failed: ${e.message}`, "error")
    }
    setLoading(false)
  }

  const fieldStyle = {
    width: "100%", padding: "8px 10px", border: "1px solid #d1d5db",
    borderRadius: 6, fontSize: 13, marginBottom: 8,
  }

  return (
    <Card title="Phase 1: Business Analysis" actions={
      <RunButton onClick={run} loading={loading} disabled={!form.domain}>
        Analyze Business
      </RunButton>
    }>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Domain *</label>
          <input style={fieldStyle} placeholder="https://example.com" value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} />
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Business Type</label>
          <select style={fieldStyle} value={form.business_type} onChange={(e) => setForm({ ...form, business_type: e.target.value })}>
            <option value="">Auto-detect</option>
            <option value="Ecommerce">Ecommerce</option>
            <option value="B2B">B2B</option>
            <option value="D2C">D2C</option>
            <option value="SaaS">SaaS</option>
            <option value="Local">Local</option>
          </select>
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Pillars (comma-sep)</label>
          <input style={fieldStyle} placeholder="organic spices, whole spices" value={form.pillars} onChange={(e) => setForm({ ...form, pillars: e.target.value })} />
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Geo Scope</label>
          <input style={fieldStyle} placeholder="India, USA" value={form.geo_scope} onChange={(e) => setForm({ ...form, geo_scope: e.target.value })} />
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Product Catalog (comma-sep)</label>
          <input style={fieldStyle} placeholder="turmeric powder, cardamom pods" value={form.product_catalog} onChange={(e) => setForm({ ...form, product_catalog: e.target.value })} />
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Modifiers</label>
          <input style={fieldStyle} placeholder="organic, wholesale, bulk" value={form.modifiers} onChange={(e) => setForm({ ...form, modifiers: e.target.value })} />
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Audience</label>
          <input style={fieldStyle} placeholder="restaurant owners, home cooks" value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} />
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Negative Scope</label>
          <input style={fieldStyle} placeholder="recipe, benefits, how to" value={form.negative_scope} onChange={(e) => setForm({ ...form, negative_scope: e.target.value })} />
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Competitor URLs</label>
          <input style={fieldStyle} placeholder="https://competitor.com" value={form.competitor_urls} onChange={(e) => setForm({ ...form, competitor_urls: e.target.value })} />
        </div>
      </div>

      {error && <p style={{ color: "#dc2626", marginTop: 8, fontSize: 13 }}>{error}</p>}

      {profile && (
        <div style={{ marginTop: 16 }}>
          <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>Business Profile</h4>
          <StatsRow items={[
            { label: "Pillars", value: (profile.pillars || []).length, color: "#3b82f6" },
            { label: "Products", value: (profile.product_catalog || []).length, color: "#10b981" },
            { label: "Modifiers", value: (profile.modifiers || []).length, color: "#8b5cf6" },
            { label: "Confidence", value: `${((profile.confidence_score || 0) * 100).toFixed(0)}%`, color: profile.confidence_score >= 0.7 ? "#10b981" : "#f59e0b" },
          ]} />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <Badge color="blue">{profile.universe || "Universe"}</Badge>
            <Badge color="green">{profile.business_type || "Unknown type"}</Badge>
            {profile.geo_scope && <Badge color="gray">{profile.geo_scope}</Badge>}
          </div>
          <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.7 }}>
            {(profile.pillars || []).length > 0 && (
              <div style={{ marginBottom: 6 }}>
                <strong>Pillars:</strong>{" "}
                {profile.pillars.map((p, i) => <Badge key={i} color="blue">{p}</Badge>).reduce((a, b) => [a, " ", b])}
              </div>
            )}
            {(profile.product_catalog || []).length > 0 && (
              <div style={{ marginBottom: 6 }}><strong>Products:</strong> {profile.product_catalog.join(", ")}</div>
            )}
            {(profile.modifiers || []).length > 0 && (
              <div style={{ marginBottom: 6 }}><strong>Modifiers:</strong> {profile.modifiers.join(", ")}</div>
            )}
            {(profile.audience || []).length > 0 && (
              <div style={{ marginBottom: 6 }}><strong>Audience:</strong> {profile.audience.join(", ")}</div>
            )}
          </div>

          <PhaseResult
            phaseNum={1}
            stats={[
              { label: "Pillars", value: (profile.pillars || []).length, color: "#3b82f6" },
              { label: "Products", value: (profile.product_catalog || []).length, color: "#10b981" },
              { label: "Confidence", value: `${((profile.confidence_score || 0) * 100).toFixed(0)}%`, color: "#8b5cf6" },
            ]}
            onNext={() => setActivePhase(2)}
          />
        </div>
      )}

      <NotificationList notifications={notifications} title="Run Notifications" />
      <ConsolePanel filterBadge="P1" />
    </Card>
  )
}
