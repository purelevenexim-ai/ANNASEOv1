/**
 * GscSetupPage — Google Search Console Setup Guide + Credential Management
 *
 * Two sections:
 *   A. Step-by-step guide (expandable steps with screenshots description)
 *   B. Credential management (Client ID, Secret, Redirect URI) + Test button
 */
import React, { useState, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import * as gscApi from "./api"

const REDIRECT_URI = "https://annaseo.pureleven.com/api/gsc/auth/callback"

/* ── Shared primitives ──────────────────────────────────────────────────────── */

const T = {
  blue:   "#007AFF",
  green:  "#34C759",
  red:    "#FF3B30",
  yellow: "#FF9500",
  gray:   "#8E8E93",
  bg:     "#F2F2F7",
  card:   "#FFFFFF",
  border: "rgba(60,60,67,0.12)",
}

function Card({ children, style }) {
  return (
    <div style={{
      background: T.card, borderRadius: 12, padding: "16px 18px",
      border: `0.5px solid ${T.border}`, ...style,
    }}>{children}</div>
  )
}

function Badge({ color = "gray", children }) {
  const C = {
    green:  { bg: "#d1fae5", fg: "#166534" },
    red:    { bg: "#fee2e2", fg: "#dc2626" },
    yellow: { bg: "#fef9c3", fg: "#854d0e" },
    gray:   { bg: "#f3f4f6", fg: "#374151" },
    blue:   { bg: "#dbeafe", fg: "#1e40af" },
  }
  const c = C[color] || C.gray
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: 8,
      fontSize: 11, fontWeight: 600, background: c.bg, color: c.fg,
    }}>{children}</span>
  )
}

function Step({ num, title, done, children, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen || false)
  return (
    <div style={{
      borderBottom: `0.5px solid ${T.border}`,
      paddingBottom: open ? 14 : 0,
      marginBottom: open ? 4 : 0,
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", display: "flex", alignItems: "center", gap: 12,
          padding: "14px 0", background: "none", border: "none", cursor: "pointer",
          textAlign: "left",
        }}
      >
        <div style={{
          width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, fontWeight: 700,
          background: done ? T.green : T.blue,
          color: "#fff",
        }}>
          {done ? "✓" : num}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: "#1c1c1e" }}>{title}</div>
        </div>
        <span style={{ color: T.gray, fontSize: 11 }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && <div style={{ paddingLeft: 40, paddingBottom: 4 }}>{children}</div>}
    </div>
  )
}

function Code({ children }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(children).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8, marginTop: 6, marginBottom: 6,
    }}>
      <code style={{
        flex: 1, display: "block", padding: "8px 12px", borderRadius: 7,
        background: "#1e293b", color: "#e2e8f0",
        fontSize: 12, fontFamily: "monospace", wordBreak: "break-all",
        lineHeight: 1.5,
      }}>{children}</code>
      <button onClick={copy} style={{
        flexShrink: 0, padding: "6px 10px", borderRadius: 6, fontSize: 11,
        background: copied ? T.green : "#e5e7eb", color: copied ? "#fff" : "#374151",
        border: "none", cursor: "pointer", fontWeight: 600,
      }}>{copied ? "✓" : "Copy"}</button>
    </div>
  )
}

/* ── Section A: Step-by-step guide ─────────────────────────────────────────── */

function SetupGuide({ projectId }) {
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [connError, setConnError] = useState(null)

  const handleConnect = useCallback(async () => {
    setConnecting(true); setConnError(null)
    try {
      const { auth_url } = await gscApi.getAuthUrl(projectId)
      const popup = window.open(auth_url, "gsc_auth", "width=600,height=700,scrollbars=yes")
      const onMsg = (e) => {
        if (e.data?.type === "gsc_auth_success") {
          window.removeEventListener("message", onMsg)
          setConnecting(false)
          window.location.reload()
        }
        if (e.data?.type === "gsc_auth_error") {
          window.removeEventListener("message", onMsg)
          setConnError("Auth failed: " + (e.data.error || "unknown error"))
          setConnecting(false)
        }
      }
      window.addEventListener("message", onMsg)
      const poll = setInterval(() => {
        if (popup?.closed) {
          clearInterval(poll)
          setConnecting(false)
          window.removeEventListener("message", onMsg)
        }
      }, 2000)
    } catch (e) { setConnError(e.message); setConnecting(false) }
  }, [projectId])

  const handleTest = useCallback(async () => {
    setTesting(true); setTestResult(null)
    try {
      const r = await gscApi.testConnection(projectId)
      setTestResult(r)
    } catch (e) {
      setTestResult({ ok: false, reason: "api_error", message: e.message })
    }
    setTesting(false)
  }, [projectId])

  return (
    <Card>
      <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 4 }}>
        📋 Setup Guide — Connect Google Search Console
      </div>
      <div style={{ fontSize: 12, color: T.gray, marginBottom: 16 }}>
        Follow these steps once. After setup, AnnaSEO can fetch your real search data automatically.
      </div>

      {/* ─ Step 1 ─ */}
      <Step num={1} title="Open Google Cloud Console and create a project" defaultOpen>
        <ol style={{ fontSize: 12, lineHeight: 2, paddingLeft: 16, color: "#374151" }}>
          <li>Go to <a href="https://console.cloud.google.com" target="_blank" rel="noreferrer" style={{ color: T.blue }}>console.cloud.google.com</a></li>
          <li>Click the project dropdown at the top → <strong>New Project</strong></li>
          <li>Name it anything (e.g. <em>AnnaSEO</em>) → click <strong>Create</strong></li>
          <li>Make sure the new project is selected in the dropdown</li>
        </ol>
      </Step>

      {/* ─ Step 2 ─ */}
      <Step num={2} title="Enable the Google Search Console API">
        <ol style={{ fontSize: 12, lineHeight: 2, paddingLeft: 16, color: "#374151" }}>
          <li>In Cloud Console, go to <strong>APIs &amp; Services → Library</strong></li>
          <li>Search for <strong>"Google Search Console API"</strong></li>
          <li>Click it → click <strong>Enable</strong></li>
        </ol>
        <div style={{ marginTop: 8 }}>
          <a href="https://console.cloud.google.com/apis/library/searchconsole.googleapis.com" target="_blank" rel="noreferrer"
            style={{ fontSize: 12, color: T.blue, fontWeight: 600 }}>
            → Open Search Console API page ↗
          </a>
        </div>
      </Step>

      {/* ─ Step 3 ─ */}
      <Step num={3} title="Configure OAuth Consent Screen">
        <ol style={{ fontSize: 12, lineHeight: 2, paddingLeft: 16, color: "#374151" }}>
          <li>Go to <strong>APIs &amp; Services → OAuth consent screen</strong></li>
          <li>Choose <strong>External</strong> → click <strong>Create</strong></li>
          <li>Fill in:
            <ul style={{ paddingLeft: 16, marginTop: 4 }}>
              <li><strong>App name:</strong> AnnaSEO (or any name)</li>
              <li><strong>User support email:</strong> your email</li>
              <li><strong>Developer contact:</strong> your email</li>
            </ul>
          </li>
          <li>Click <strong>Save and Continue</strong> through all screens</li>
          <li>On the <strong>Test users</strong> screen, add your Google account email</li>
          <li>Click <strong>Save and Continue</strong> → <strong>Back to Dashboard</strong></li>
        </ol>
      </Step>

      {/* ─ Step 4 ─ */}
      <Step num={4} title="Create OAuth 2.0 Client ID credentials">
        <ol style={{ fontSize: 12, lineHeight: 2, paddingLeft: 16, color: "#374151" }}>
          <li>Go to <strong>APIs &amp; Services → Credentials</strong></li>
          <li>Click <strong>+ Create Credentials → OAuth client ID</strong></li>
          <li>Application type: <strong>Web application</strong></li>
          <li>Name: <em>AnnaSEO Web Client</em></li>
          <li>Under <strong>Authorized redirect URIs</strong>, click <strong>+ Add URI</strong> and enter:</li>
        </ol>
        <Code>{REDIRECT_URI}</Code>
        <ol start={6} style={{ fontSize: 12, lineHeight: 2, paddingLeft: 16, color: "#374151" }}>
          <li>Click <strong>Create</strong></li>
          <li>Copy the <strong>Client ID</strong> and <strong>Client Secret</strong> shown in the popup</li>
          <li>Click <strong>Download JSON</strong> to save a backup</li>
        </ol>
      </Step>

      {/* ─ Step 5 ─ */}
      <Step num={5} title="Add credentials to AnnaSEO Settings">
        <p style={{ fontSize: 12, color: "#374151", lineHeight: 1.7, marginBottom: 8 }}>
          Paste the <strong>Client ID</strong> and <strong>Client Secret</strong> into the
          <strong> Credentials</strong> section below (scroll down), then click <strong>Save</strong>.
        </p>
        <p style={{ fontSize: 12, color: "#374151", lineHeight: 1.7 }}>
          The redirect URI is already pre-filled (<code style={{ fontSize: 11, background: "#f3f4f6", padding: "1px 5px", borderRadius: 4 }}>{REDIRECT_URI}</code>).
          It must match <strong>exactly</strong> what you entered in Google Cloud Console.
        </p>
      </Step>

      {/* ─ Step 6 ─ */}
      <Step num={6} title="Authorize AnnaSEO to access your GSC data">
        <p style={{ fontSize: 12, color: "#374151", lineHeight: 1.7, marginBottom: 10 }}>
          Click the button below. A Google sign-in popup will open. Sign in with the
          Google account that owns your Search Console property.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <button
            onClick={handleConnect}
            disabled={connecting}
            style={{
              padding: "9px 20px", borderRadius: 8, fontSize: 13, fontWeight: 700,
              background: connecting ? "#d1d5db" : T.blue, color: "#fff",
              border: "none", cursor: connecting ? "not-allowed" : "pointer",
            }}
          >
            {connecting ? "⟳ Opening..." : "🔗 Connect Google Search Console"}
          </button>
          <button
            onClick={handleTest}
            disabled={testing}
            style={{
              padding: "9px 18px", borderRadius: 8, fontSize: 13, fontWeight: 600,
              background: testing ? "#d1d5db" : "#f3f4f6", color: "#374151",
              border: "1px solid #d1d5db", cursor: testing ? "not-allowed" : "pointer",
            }}
          >
            {testing ? "⟳ Testing..." : "🧪 Test Connection"}
          </button>
        </div>
        {connError && (
          <div style={{ marginTop: 10, padding: "10px 14px", borderRadius: 8, background: "#fee2e2", color: "#dc2626", fontSize: 12 }}>
            <strong>Auth Error:</strong> {connError}
            <div style={{ marginTop: 4, fontSize: 11 }}>
              Common causes:{" "}
              <ul style={{ paddingLeft: 16, marginTop: 2 }}>
                <li>Redirect URI mismatch — check Step 4 above</li>
                <li>Wrong Client ID / Secret — re-check Step 5</li>
                <li>OAuth app not published — add your email as a Test User in Step 3</li>
              </ul>
            </div>
          </div>
        )}
        {testResult && (
          <div style={{
            marginTop: 10, padding: "10px 14px", borderRadius: 8, fontSize: 12,
            background: testResult.ok ? "#f0fdf4" : "#fee2e2",
            border: `1px solid ${testResult.ok ? "#bbf7d0" : "#fecaca"}`,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, marginBottom: testResult.ok ? 6 : 4 }}>
              {testResult.ok ? "✅" : "❌"}
              <span style={{ color: testResult.ok ? "#166534" : "#dc2626" }}>
                {testResult.ok ? "Connection Successful" : "Connection Failed"}
              </span>
            </div>
            <div style={{ color: testResult.ok ? "#166534" : "#dc2626" }}>{testResult.message}</div>
            {testResult.ok && testResult.sites?.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4 }}>Sites in your GSC account:</div>
                {testResult.sites.map((s, i) => (
                  <div key={i} style={{ fontSize: 11, color: "#374151", padding: "2px 0" }}>
                    • {s.url} <span style={{ color: T.gray }}>({s.permission})</span>
                  </div>
                ))}
              </div>
            )}
            {!testResult.ok && (
              <div style={{ marginTop: 8, fontSize: 11, color: "#7f1d1d" }}>
                <strong>Reason:</strong> {testResult.reason === "not_connected" && "Not authorized — complete the OAuth flow (Step 6)"}
                {testResult.reason === "no_token" && "No access token — re-authorize (Step 6)"}
                {testResult.reason === "token_expired" && "Token expired — re-authorize to refresh"}
                {testResult.reason === "api_error" && "API error — check credentials are correct"}
              </div>
            )}
          </div>
        )}
      </Step>

      {/* ─ Step 7 ─ */}
      <Step num={7} title="Select your site and fetch data">
        <p style={{ fontSize: 12, color: "#374151", lineHeight: 1.7 }}>
          After connecting, go to <strong>GSC Engine</strong> in the sidebar →
          <strong> Connect tab</strong>. Click <strong>List My Sites</strong>, select
          your site, then click <strong>Fetch Data</strong> to pull your search queries.
        </p>
      </Step>
    </Card>
  )
}

/* ── Section B: Credential management ──────────────────────────────────────── */

function CredentialManager({ projectId }) {
  const qc = useQueryClient()
  const [keys, setKeys] = useState({ google_client_id: "", google_client_secret: "", google_redirect_uri: REDIRECT_URI })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)
  const [showSecret, setShowSecret] = useState(false)

  const { data: current } = useQuery({
    queryKey: ["api-keys"],
    queryFn: () => fetch("/api/settings/api-keys", {
      headers: { Authorization: "Bearer " + localStorage.getItem("annaseo_token") },
    }).then(r => r.json()),
    onSuccess: (d) => {
      setKeys(prev => ({
        ...prev,
        google_redirect_uri: d.google_redirect_uri || REDIRECT_URI,
      }))
    },
  })

  const handleSave = async () => {
    setSaving(true); setMsg(null)
    const body = {}
    if (keys.google_client_id?.trim())     body.google_client_id     = keys.google_client_id.trim()
    if (keys.google_client_secret?.trim()) body.google_client_secret = keys.google_client_secret.trim()
    if (keys.google_redirect_uri?.trim())  body.google_redirect_uri  = keys.google_redirect_uri.trim()

    try {
      const r = await fetch("/api/settings/api-keys", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + localStorage.getItem("annaseo_token"),
        },
        body: JSON.stringify(body),
      }).then(r => r.json())
      setMsg(r.status === "ok" ? { type: "ok", text: `✓ Saved ${r.saved?.length || 0} credential(s)` } : { type: "err", text: "Error saving" })
      qc.invalidateQueries(["api-keys"])
    } catch (e) {
      setMsg({ type: "err", text: e.message })
    }
    setSaving(false)
  }

  const isSet = (k) => current?.[k] === true

  return (
    <Card style={{ marginTop: 16 }}>
      <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 4 }}>🔑 Google OAuth Credentials</div>
      <div style={{ fontSize: 12, color: T.gray, marginBottom: 16 }}>
        Credentials are stored securely and used only for Google OAuth. Current values are hidden for security — enter new values to update.
      </div>

      {/* Current State */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <div style={{ padding: "8px 14px", borderRadius: 8, background: isSet("google_client_id") ? "#f0fdf4" : "#fef9c3", fontSize: 12, border: `1px solid ${isSet("google_client_id") ? "#bbf7d0" : "#fde68a"}` }}>
          <span style={{ fontWeight: 600 }}>Client ID</span>{" "}
          <Badge color={isSet("google_client_id") ? "green" : "yellow"}>{isSet("google_client_id") ? "configured" : "not set"}</Badge>
        </div>
        <div style={{ padding: "8px 14px", borderRadius: 8, background: isSet("google_client_secret") ? "#f0fdf4" : "#fef9c3", fontSize: 12, border: `1px solid ${isSet("google_client_secret") ? "#bbf7d0" : "#fde68a"}` }}>
          <span style={{ fontWeight: 600 }}>Client Secret</span>{" "}
          <Badge color={isSet("google_client_secret") ? "green" : "yellow"}>{isSet("google_client_secret") ? "configured" : "not set"}</Badge>
        </div>
        <div style={{ padding: "8px 14px", borderRadius: 8, background: current?.google_redirect_uri ? "#f0fdf4" : "#fef9c3", fontSize: 12, border: `1px solid ${current?.google_redirect_uri ? "#bbf7d0" : "#fde68a"}` }}>
          <span style={{ fontWeight: 600 }}>Redirect URI</span>{" "}
          <Badge color={current?.google_redirect_uri ? "green" : "yellow"}>{current?.google_redirect_uri ? "set" : "not set"}</Badge>
        </div>
      </div>

      {/* Form */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, display: "block", marginBottom: 4, color: "#374151" }}>
            Client ID
          </label>
          <input
            value={keys.google_client_id}
            onChange={e => setKeys(k => ({ ...k, google_client_id: e.target.value }))}
            placeholder="222412223287-xxx.apps.googleusercontent.com"
            style={{ width: "100%", padding: "8px 10px", borderRadius: 7, border: "1px solid #d1d5db", fontSize: 12, fontFamily: "monospace" }}
          />
        </div>
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, display: "block", marginBottom: 4, color: "#374151" }}>
            Client Secret{" "}
            <button onClick={() => setShowSecret(s => !s)} style={{ fontSize: 10, color: T.blue, background: "none", border: "none", cursor: "pointer" }}>
              {showSecret ? "hide" : "show"}
            </button>
          </label>
          <input
            type={showSecret ? "text" : "password"}
            value={keys.google_client_secret}
            onChange={e => setKeys(k => ({ ...k, google_client_secret: e.target.value }))}
            placeholder="GOCSPX-..."
            style={{ width: "100%", padding: "8px 10px", borderRadius: 7, border: "1px solid #d1d5db", fontSize: 12, fontFamily: "monospace" }}
          />
        </div>
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, display: "block", marginBottom: 4, color: "#374151" }}>
            Redirect URI
          </label>
          <input
            value={keys.google_redirect_uri}
            onChange={e => setKeys(k => ({ ...k, google_redirect_uri: e.target.value }))}
            placeholder={REDIRECT_URI}
            style={{ width: "100%", padding: "8px 10px", borderRadius: 7, border: "1px solid #d1d5db", fontSize: 12, fontFamily: "monospace" }}
          />
          <div style={{ fontSize: 10, color: T.gray, marginTop: 3 }}>
            Must match exactly what is registered in Google Cloud Console.
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              padding: "8px 20px", borderRadius: 8, fontSize: 13, fontWeight: 700,
              background: saving ? "#d1d5db" : T.blue, color: "#fff",
              border: "none", cursor: saving ? "not-allowed" : "pointer",
            }}
          >
            {saving ? "⟳ Saving..." : "💾 Save Credentials"}
          </button>
          {msg && (
            <span style={{ fontSize: 12, fontWeight: 600, color: msg.type === "ok" ? T.green : T.red }}>
              {msg.text}
            </span>
          )}
        </div>
      </div>

      {/* Current redirect URI reminder */}
      <div style={{ marginTop: 16, padding: "10px 14px", borderRadius: 8, background: "#eff6ff", border: "1px solid #bfdbfe", fontSize: 12 }}>
        <div style={{ fontWeight: 600, color: "#1e40af", marginBottom: 4 }}>⚠ Important: Redirect URI must be registered</div>
        <div style={{ color: "#1e40af", lineHeight: 1.6 }}>
          The redirect URI below <strong>must be added</strong> to your Google Cloud Console OAuth credentials
          under <em>Authorized redirect URIs</em>:
        </div>
        <Code>{REDIRECT_URI}</Code>
        <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer"
          style={{ fontSize: 12, color: T.blue, fontWeight: 600 }}>
          → Open Credentials page in Google Cloud Console ↗
        </a>
      </div>
    </Card>
  )
}

/* ── FAQ / Troubleshooting ──────────────────────────────────────────────────── */

function Troubleshooting() {
  const items = [
    {
      q: "I get 'Access blocked: Authorization Error (invalid_client)'",
      a: "Your Client ID or Secret is wrong. Double-check they are copied from Google Cloud Console → Credentials → your OAuth 2.0 client. Re-save them in the Credentials section above.",
    },
    {
      q: "I get 'redirect_uri_mismatch'",
      a: `The redirect URI you registered in Google Cloud Console doesn't match exactly. It must be: ${REDIRECT_URI} — no trailing slash, HTTPS, exact path.`,
    },
    {
      q: "I get 'This app isn't verified'",
      a: "Click 'Advanced' → 'Go to AnnaSEO (unsafe)'. This appears because the OAuth app is in test mode. Add your Google account as a Test User in OAuth Consent Screen → Test Users.",
    },
    {
      q: "The popup closes but I'm still 'Not Connected'",
      a: "Wait a few seconds and refresh the GSC page. If still not connected, check the server logs — the token exchange may have failed. Try reconnecting.",
    },
    {
      q: "GSC shows my account but no search data",
      a: "Your site may not be verified in Google Search Console. Sign in to search.google.com/search-console and add your site property. Data takes 1–3 days to appear for new properties.",
    },
    {
      q: "Token expired / need to re-authorize",
      a: "Click 'Connect Google Search Console' again. The OAuth flow will refresh all tokens automatically.",
    },
  ]
  const [open, setOpen] = useState(null)
  return (
    <Card style={{ marginTop: 16 }}>
      <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 12 }}>❓ Troubleshooting</div>
      {items.map((item, i) => (
        <div key={i} style={{ borderBottom: `0.5px solid ${T.border}` }}>
          <button
            onClick={() => setOpen(open === i ? null : i)}
            style={{
              width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "12px 0", background: "none", border: "none", cursor: "pointer", textAlign: "left",
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 500, color: "#1c1c1e" }}>{item.q}</span>
            <span style={{ color: T.gray, fontSize: 11, flexShrink: 0, marginLeft: 8 }}>{open === i ? "▲" : "▼"}</span>
          </button>
          {open === i && (
            <p style={{ fontSize: 12, color: "#374151", lineHeight: 1.7, paddingBottom: 12 }}>{item.a}</p>
          )}
        </div>
      ))}
    </Card>
  )
}

/* ── Main export ────────────────────────────────────────────────────────────── */

export default function GscSetupPage({ projectId }) {
  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: -0.5 }}>🔍 GSC Setup &amp; Credentials</div>
        <div style={{ fontSize: 13, color: T.gray, marginTop: 4 }}>
          Connect AnnaSEO to Google Search Console to fetch real keyword traffic data.
        </div>
      </div>

      <SetupGuide projectId={projectId} />
      <CredentialManager projectId={projectId} />
      <Troubleshooting />
    </div>
  )
}
