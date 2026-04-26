// Business Story Tab — R1 Foundation
// Captures structured business truth that gets injected into content prompts (P1, P2, P6).
// Inline-styles only, matches existing T-token design system.

import { useState, useEffect, useMemo } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { T, api, useStore } from "../App"

const VOICE_OPTIONS = [
  { v: "friendly",    label: "Friendly",    desc: "Warm, conversational, accessible" },
  { v: "traditional", label: "Traditional", desc: "Heritage, time-honoured, grounded" },
  { v: "modern",      label: "Modern",      desc: "Clean, contemporary, direct" },
  { v: "expert",      label: "Expert",      desc: "Authoritative, technical, precise" },
]

const FIELD_LIMITS = {
  founder_story:    4000,
  origin_story:     3000,
  mission:          1500,
  values_text:      1500,
  what_we_dont_do:  1500,
  free_text_extras: 6000,
}

// ── Reusable bits ─────────────────────────────────────────────────────────────

function Section({ title, subtitle, children, footer }) {
  return (
    <div style={{
      background: "#fff", border: `1px solid ${T.border}`, borderRadius: 12,
      padding: 18, marginBottom: 16,
    }}>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: T.text, letterSpacing: -0.2 }}>{title}</div>
        {subtitle && (
          <div style={{ fontSize: 11, color: T.textSoft, marginTop: 3, lineHeight: 1.45 }}>{subtitle}</div>
        )}
      </div>
      {children}
      {footer}
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: T.textSoft, textTransform: "uppercase",
        letterSpacing: 0.4, marginBottom: 5 }}>{label}</div>
      {children}
      {hint && <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4 }}>{hint}</div>}
    </div>
  )
}

function Input({ value, onChange, placeholder, maxLength }) {
  return (
    <input
      value={value || ""}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      maxLength={maxLength}
      style={{
        width: "100%", padding: "8px 10px", fontSize: 13, color: T.text,
        border: `1px solid ${T.border}`, borderRadius: 8, background: "#fff",
        outline: "none", fontFamily: T.bodyFont, boxSizing: "border-box",
      }}
    />
  )
}

function TextArea({ value, onChange, placeholder, rows = 4, maxLength }) {
  const len = (value || "").length
  return (
    <div>
      <textarea
        value={value || ""}
        onChange={e => onChange(e.target.value.slice(0, maxLength || 99999))}
        placeholder={placeholder}
        rows={rows}
        style={{
          width: "100%", padding: "8px 10px", fontSize: 13, color: T.text,
          border: `1px solid ${T.border}`, borderRadius: 8, background: "#fff",
          outline: "none", fontFamily: T.bodyFont, resize: "vertical", boxSizing: "border-box",
          lineHeight: 1.45,
        }}
      />
      {maxLength && (
        <div style={{ fontSize: 10, color: len > maxLength * 0.9 ? T.amber : T.textSoft,
          textAlign: "right", marginTop: 2 }}>
          {len} / {maxLength}
        </div>
      )}
    </div>
  )
}

function Button({ children, onClick, color = "purple", disabled, size = "md" }) {
  const bg = color === "purple" ? T.purple
    : color === "red" ? T.red
    : color === "ghost" ? "transparent"
    : "#F2F2F7"
  const fg = color === "ghost" ? T.text : (color === "purple" || color === "red" ? "#fff" : T.text)
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: size === "sm" ? "5px 12px" : "8px 16px",
        fontSize: size === "sm" ? 11 : 13, fontWeight: 600,
        background: disabled ? T.grayLight : bg, color: disabled ? T.textSoft : fg,
        border: color === "ghost" ? `1px solid ${T.border}` : "none",
        borderRadius: 8, cursor: disabled ? "not-allowed" : "pointer",
        whiteSpace: "nowrap",
      }}
    >{children}</button>
  )
}

// ── Process Builder Row ───────────────────────────────────────────────────────
// Auto-saves: text fields on blur, checkboxes on change, benefits on add/remove.
// No explicit "Save" button — clearer UX and avoids losing keystrokes during round-trips.

function ProcessRow({ proc, onSaveField, onSaveBenefits, onDelete, isSaving }) {
  const [name, setName] = useState(proc.name || "")
  const [description, setDescription] = useState(proc.description || "")
  const [benefitInput, setBenefitInput] = useState("")

  // Sync local field state when server data changes for this row (different updated_at)
  useEffect(() => { setName(proc.name || "") }, [proc.id, proc.updated_at])
  useEffect(() => { setDescription(proc.description || "") }, [proc.id, proc.updated_at])

  const benefits = proc.benefits || []
  const nameDirty = name !== (proc.name || "")
  const descDirty = description !== (proc.description || "")

  const saveName = () => {
    if (!nameDirty) return
    if (!name.trim()) { setName(proc.name || ""); return }   // empty → revert
    onSaveField({ name: name.trim() })
  }
  const saveDescription = () => {
    if (!descDirty) return
    onSaveField({ description })
  }
  const toggleManual = (v) => onSaveField({ is_manual: v })
  const toggleTraditional = (v) => onSaveField({ is_traditional: v })

  const addBenefit = () => {
    const v = benefitInput.trim()
    if (!v) return
    if (benefits.some(b => b.benefit_key === v.toLowerCase().replace(/[^a-z0-9]+/g, "_"))) {
      setBenefitInput(""); return
    }
    onSaveBenefits([...benefits, { benefit_key: v, description: "" }])
    setBenefitInput("")
  }
  const removeBenefit = (idx) => {
    onSaveBenefits(benefits.filter((_, i) => i !== idx))
  }

  return (
    <div style={{
      border: `1px solid ${T.border}`, borderRadius: 10, padding: 12, marginBottom: 10,
      background: "#fff", position: "relative",
    }}>
      {isSaving && (
        <div style={{ position: "absolute", top: 8, right: 12, fontSize: 10,
          color: T.textSoft, fontStyle: "italic" }}>Saving…</div>
      )}
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          onBlur={saveName}
          onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); e.target.blur() } }}
          placeholder="Process name (e.g. Sun-dry pepper)"
          style={{ flex: 1, padding: "6px 9px", fontSize: 13, fontWeight: 600,
            border: `1px solid ${nameDirty ? T.amber : T.border}`, borderRadius: 6, outline: "none" }}
        />
        <Button color="ghost" size="sm" onClick={() => onDelete(proc.id)}>✕</Button>
      </div>
      <textarea
        value={description}
        onChange={e => setDescription(e.target.value.slice(0, 1500))}
        onBlur={saveDescription}
        placeholder="Describe this process. Be factual — what is actually done, in plain words."
        rows={2}
        style={{ width: "100%", padding: "6px 9px", fontSize: 12, lineHeight: 1.4,
          border: `1px solid ${descDirty ? T.amber : T.border}`, borderRadius: 6, outline: "none",
          marginBottom: 8, boxSizing: "border-box", fontFamily: T.bodyFont, resize: "vertical" }}
      />
      <div style={{ display: "flex", gap: 14, fontSize: 11, color: T.textSoft, marginBottom: 10 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}>
          <input type="checkbox" checked={!!proc.is_manual}
            onChange={e => toggleManual(e.target.checked)} />
          Manual
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}>
          <input type="checkbox" checked={!!proc.is_traditional}
            onChange={e => toggleTraditional(e.target.checked)} />
          Traditional
        </label>
      </div>
      <div>
        <div style={{ fontSize: 10, fontWeight: 600, color: T.textSoft, textTransform: "uppercase",
          letterSpacing: 0.4, marginBottom: 5 }}>Benefits ({benefits.length})</div>
        {benefits.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 6 }}>
            {benefits.map((b, i) => (
              <span key={`${b.id || i}-${b.benefit_key}`} style={{
                background: T.purpleLight, color: T.purple, fontSize: 11, fontWeight: 500,
                padding: "3px 9px", borderRadius: 99, display: "inline-flex", alignItems: "center", gap: 4,
              }}>
                {b.benefit_key}
                <button onClick={() => removeBenefit(i)}
                  title="Remove benefit"
                  style={{
                    background: "transparent", border: "none", color: T.purple, cursor: "pointer",
                    fontSize: 14, padding: 0, lineHeight: 1, fontWeight: 700,
                  }}>×</button>
              </span>
            ))}
          </div>
        )}
        <div style={{ display: "flex", gap: 6 }}>
          <input
            value={benefitInput}
            onChange={e => setBenefitInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addBenefit() } }}
            placeholder="Add benefit (e.g. low_moisture) and press Enter"
            style={{ flex: 1, padding: "5px 9px", fontSize: 12,
              border: `1px solid ${T.border}`, borderRadius: 6, outline: "none" }}
          />
          <Button color="ghost" size="sm" onClick={addBenefit} disabled={!benefitInput.trim()}>Add</Button>
        </div>
      </div>
    </div>
  )
}

// Inline form for adding a NEW process. Only POSTs on submit — no dummy rows.
function AddProcessForm({ onAdd, isAdding }) {
  const [name, setName] = useState("")
  const [open, setOpen] = useState(false)

  if (!open) {
    return <Button color="ghost" onClick={() => setOpen(true)}>+ Add process</Button>
  }
  const submit = () => {
    const n = name.trim()
    if (!n) return
    onAdd({ name: n })
    setName("")
    setOpen(false)
  }
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center",
      padding: 10, border: `1px dashed ${T.purple}`, borderRadius: 10,
      background: T.purpleLight }}>
      <input
        autoFocus
        value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => {
          if (e.key === "Enter") { e.preventDefault(); submit() }
          else if (e.key === "Escape") { setName(""); setOpen(false) }
        }}
        placeholder="Process name (e.g. Sun-dry pepper)"
        maxLength={120}
        style={{ flex: 1, padding: "7px 10px", fontSize: 13, fontWeight: 600,
          border: `1px solid ${T.border}`, borderRadius: 6, outline: "none", background: "#fff" }}
      />
      <Button color="purple" size="sm" onClick={submit} disabled={!name.trim() || isAdding}>
        {isAdding ? "Adding…" : "Add"}
      </Button>
      <Button color="ghost" size="sm" onClick={() => { setName(""); setOpen(false) }}>Cancel</Button>
    </div>
  )
}

// ── Main Tab ──────────────────────────────────────────────────────────────────

export default function BusinessStoryTab() {
  const { activeProject } = useStore()
  const qclient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["business-story", activeProject],
    queryFn: () => api.get(`/api/business-story/${activeProject}`),
    enabled: !!activeProject,
  })

  const [profile, setProfile] = useState({})
  const [savedAt, setSavedAt] = useState(null)
  const [error, setError] = useState("")

  useEffect(() => {
    if (data?.profile) setProfile(data.profile)
  }, [data])

  const processes = data?.processes || []

  const upsertProfile = useMutation({
    mutationFn: (body) => api.put(`/api/business-story/${activeProject}`, body),
    onSuccess: (resp) => {
      qclient.setQueryData(["business-story", activeProject], resp)
      setSavedAt(new Date().toLocaleTimeString())
      setError("")
    },
    onError: (e) => setError(e?.message || "Save failed"),
  })

  const createProc = useMutation({
    mutationFn: (body) => api.post(`/api/business-story/${activeProject}/processes`, body),
    onSuccess: (resp) => { qclient.setQueryData(["business-story", activeProject], resp); setError("") },
    onError: (e) => setError(e?.message || "Add process failed"),
  })

  const updateProc = useMutation({
    mutationFn: ({ id, body }) => api.put(`/api/business-story/${activeProject}/processes/${id}`, body),
    onSuccess: (resp) => { qclient.setQueryData(["business-story", activeProject], resp); setError("") },
    onError: (e) => setError(e?.message || "Save failed"),
  })

  const deleteProc = useMutation({
    mutationFn: (id) => api.delete(`/api/business-story/${activeProject}/processes/${id}`),
    onSuccess: (resp) => { qclient.setQueryData(["business-story", activeProject], resp); setError("") },
    onError: (e) => setError(e?.message || "Delete failed"),
  })

  const updateField = (k, v) => setProfile(p => ({ ...p, [k]: v }))

  const completion = useMemo(() => {
    if (!profile) return 0
    const fields = ["brand_name", "founder_name", "founder_story", "origin_story",
      "mission", "region", "country", "what_we_dont_do"]
    const filled = fields.filter(f => (profile[f] || "").toString().trim()).length
    const procPts = Math.min(processes.length, 3)  // up to 3 processes counts
    return Math.round(((filled + procPts) / (fields.length + 3)) * 100)
  }, [profile, processes])

  if (!activeProject) {
    return <div style={{ padding: 24, color: T.textSoft, fontSize: 13 }}>Select a project.</div>
  }

  if (isLoading) {
    return <div style={{ padding: 24, color: T.textSoft, fontSize: 13 }}>Loading business story…</div>
  }

  const saveProfile = () => upsertProfile.mutate(profile)

  return (
    <div style={{ padding: "8px 4px", maxWidth: 920, margin: "0 auto" }}>

      {/* Header strip */}
      <div style={{
        background: "#fff", border: `1px solid ${T.border}`, borderRadius: 12,
        padding: "12px 16px", marginBottom: 14, display: "flex", alignItems: "center", gap: 14,
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>Your Business Story</div>
          <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>
            Capture the truth about your brand, processes and region. The content engine
            weaves these naturally into every article — keyword by keyword.
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: completion >= 70 ? T.teal : T.amber }}>
            {completion}%
          </div>
          <div style={{ fontSize: 10, color: T.textSoft, marginTop: 1 }}>complete</div>
        </div>
      </div>

      {error && (
        <div style={{ background: "rgba(255,59,48,0.08)", color: T.red, padding: "8px 12px",
          borderRadius: 8, fontSize: 12, marginBottom: 12 }}>{error}</div>
      )}

      {/* Brand Identity */}
      <Section title="Brand Identity"
        subtitle="The basics. Keep it real — no superlatives, no 'best in the world'.">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="Brand name">
            <Input value={profile.brand_name} onChange={v => updateField("brand_name", v)}
              placeholder="e.g. Mama Kerala Spices" maxLength={120} />
          </Field>
          <Field label="Founder name">
            <Input value={profile.founder_name} onChange={v => updateField("founder_name", v)}
              placeholder="e.g. Anjali Nair" maxLength={120} />
          </Field>
        </div>
        <Field label="Founder story" hint="Why they started, the problem they faced, the turning point. Stay grounded.">
          <TextArea value={profile.founder_story} onChange={v => updateField("founder_story", v)}
            placeholder="My grandmother grew pepper in our backyard for 40 years before…"
            rows={4} maxLength={FIELD_LIMITS.founder_story} />
        </Field>
        <Field label="Origin story" hint="How the business itself came together (separate from founder).">
          <TextArea value={profile.origin_story} onChange={v => updateField("origin_story", v)}
            placeholder="In 2018 we started shipping from a single farm in…"
            rows={3} maxLength={FIELD_LIMITS.origin_story} />
        </Field>
      </Section>

      {/* Mission & Values */}
      <Section title="Mission & Values"
        subtitle="What you stand for, in plain words.">
        <Field label="Mission">
          <TextArea value={profile.mission} onChange={v => updateField("mission", v)}
            placeholder="To bring single-origin Kerala spices direct to home kitchens, with no middlemen."
            rows={2} maxLength={FIELD_LIMITS.mission} />
        </Field>
        <Field label="Values">
          <TextArea value={profile.values_text} onChange={v => updateField("values_text", v)}
            placeholder="Honesty about sourcing. Slow processing. No artificial colour or polish."
            rows={2} maxLength={FIELD_LIMITS.values_text} />
        </Field>
        <Field label="What we DON'T do" hint="Important — the engine will avoid claiming these. e.g. 'no machine drying', 'no chemical treatment'.">
          <TextArea value={profile.what_we_dont_do} onChange={v => updateField("what_we_dont_do", v)}
            placeholder="No bleaching. No machine polishing. No claims of medical benefits."
            rows={2} maxLength={FIELD_LIMITS.what_we_dont_do} />
        </Field>
      </Section>

      {/* Region & Voice */}
      <Section title="Region & Brand Voice"
        subtitle="Geographic identity and the tone the engine should use.">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          <Field label="Region / district">
            <Input value={profile.region} onChange={v => updateField("region", v)}
              placeholder="e.g. Wayanad" maxLength={80} />
          </Field>
          <Field label="State">
            <Input value={profile.state} onChange={v => updateField("state", v)}
              placeholder="e.g. Kerala" maxLength={80} />
          </Field>
          <Field label="Country">
            <Input value={profile.country} onChange={v => updateField("country", v)}
              placeholder="e.g. India" maxLength={80} />
          </Field>
        </div>
        <Field label="Brand voice">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
            {VOICE_OPTIONS.map(v => {
              const active = (profile.brand_voice || "friendly") === v.v
              return (
                <button key={v.v} onClick={() => updateField("brand_voice", v.v)}
                  style={{
                    textAlign: "left", padding: "10px 12px", borderRadius: 8, cursor: "pointer",
                    border: `1px solid ${active ? T.purple : T.border}`,
                    background: active ? T.purpleLight : "#fff",
                  }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: active ? T.purple : T.text }}>
                    {v.label}
                  </div>
                  <div style={{ fontSize: 11, color: T.textSoft, marginTop: 2 }}>{v.desc}</div>
                </button>
              )
            })}
          </div>
        </Field>
      </Section>

      {/* Processes */}
      <Section title="Processes — the goldmine"
        subtitle="Each process you actually do becomes a reusable story plot. e.g. 'wash → cleanliness', 'sun-dry → low moisture'. Add the steps that make you different. Changes save automatically.">
        {processes.length === 0 && (
          <div style={{ padding: "12px 14px", border: `1px dashed ${T.border}`, borderRadius: 8,
            color: T.textSoft, fontSize: 12, marginBottom: 10 }}>
            No processes yet. Add your first one below — pepper-washing, hand-sorting, sun-drying, anything specific to how you work.
          </div>
        )}
        {processes.map(p => (
          <ProcessRow key={p.id}
            proc={p}
            isSaving={updateProc.isPending && updateProc.variables?.id === p.id}
            onSaveField={(patch) => updateProc.mutate({
              id: p.id,
              body: {
                name: p.name,
                description: p.description || "",
                is_manual: !!p.is_manual,
                is_traditional: !!p.is_traditional,
                sort_order: p.sort_order || 0,
                ...patch,
              },
            })}
            onSaveBenefits={(benefits) => updateProc.mutate({
              id: p.id,
              body: {
                name: p.name,
                description: p.description || "",
                is_manual: !!p.is_manual,
                is_traditional: !!p.is_traditional,
                sort_order: p.sort_order || 0,
                benefits,
              },
            })}
            onDelete={(id) => { if (window.confirm(`Delete "${p.name}"?`)) deleteProc.mutate(id) }}
          />
        ))}
        <AddProcessForm
          isAdding={createProc.isPending}
          onAdd={({ name }) => createProc.mutate({
            name, description: "", is_manual: true, is_traditional: true,
            sort_order: processes.length, benefits: [],
          })}
        />
      </Section>

      {/* Free-text Extras */}
      <Section title="Anything else?"
        subtitle="Free-form. Anything we missed — quirks, specialties, family practices. The engine will mine this for context.">
        <TextArea value={profile.free_text_extras} onChange={v => updateField("free_text_extras", v)}
          placeholder="My uncle taught us to dry pepper on raised bamboo mats so air flows under it…"
          rows={5} maxLength={FIELD_LIMITS.free_text_extras} />
      </Section>

      {/* Save bar */}
      <div style={{
        position: "sticky", bottom: 0, background: "#fff", borderTop: `1px solid ${T.border}`,
        padding: "10px 14px", display: "flex", alignItems: "center", gap: 12, marginTop: 8,
        borderRadius: "0 0 12px 12px",
      }}>
        <div style={{ flex: 1, fontSize: 11, color: T.textSoft }}>
          {savedAt
            ? `Saved at ${savedAt}`
            : "Changes to identity / mission / region need a save. Process changes save individually."}
        </div>
        <Button color="purple" onClick={saveProfile} disabled={upsertProfile.isPending}>
          {upsertProfile.isPending ? "Saving…" : "Save profile"}
        </Button>
      </div>

    </div>
  )
}
