/**
 * Shared design tokens and tiny UI primitives for kw3.
 * Style: clean, minimal, lots of whitespace, single accent color.
 */
import React from "react"

export const T = {
  bg:        "#fafbfc",
  card:      "#ffffff",
  border:    "#e5e7eb",
  borderHi:  "#d1d5db",
  text:      "#111827",
  textSoft:  "#6b7280",
  textMute:  "#9ca3af",
  primary:   "#2563eb",
  primaryHi: "#1d4ed8",
  primaryBg: "#eff6ff",
  success:   "#10b981",
  successBg: "#f0fdf4",
  warn:      "#f59e0b",
  warnBg:    "#fffbeb",
  error:     "#ef4444",
  errorBg:   "#fef2f2",
}

export function Card({ children, style, ...rest }) {
  return (
    <div
      style={{
        background: T.card,
        border: `1px solid ${T.border}`,
        borderRadius: 10,
        padding: 20,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  )
}

export function Btn({ variant = "primary", children, disabled, style, ...rest }) {
  const v = {
    primary:   { bg: T.primary,   bgHover: T.primaryHi, color: "#fff" },
    secondary: { bg: "#f3f4f6",   bgHover: "#e5e7eb",   color: T.text },
    ghost:     { bg: "transparent", bgHover: "#f3f4f6", color: T.textSoft },
    danger:    { bg: T.errorBg,   bgHover: "#fee2e2",   color: T.error },
    success:   { bg: T.success,   bgHover: "#059669",   color: "#fff" },
  }[variant] || { bg: T.primary, color: "#fff" }
  return (
    <button
      disabled={disabled}
      style={{
        background: disabled ? "#e5e7eb" : v.bg,
        color: disabled ? T.textMute : v.color,
        border: variant === "ghost" ? `1px solid ${T.border}` : "none",
        padding: "8px 16px",
        borderRadius: 7,
        fontSize: 13,
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background .15s",
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  )
}

export function Input({ style, ...rest }) {
  return (
    <input
      style={{
        width: "100%",
        padding: "8px 12px",
        border: `1px solid ${T.border}`,
        borderRadius: 7,
        fontSize: 13,
        outline: "none",
        boxSizing: "border-box",
        ...style,
      }}
      onFocus={e => { e.target.style.borderColor = T.primary }}
      onBlur={e => { e.target.style.borderColor = T.border }}
      {...rest}
    />
  )
}

export function Textarea({ style, ...rest }) {
  return (
    <textarea
      style={{
        width: "100%",
        padding: "8px 12px",
        border: `1px solid ${T.border}`,
        borderRadius: 7,
        fontSize: 13,
        outline: "none",
        boxSizing: "border-box",
        resize: "vertical",
        minHeight: 80,
        fontFamily: "inherit",
        ...style,
      }}
      onFocus={e => { e.target.style.borderColor = T.primary }}
      onBlur={e => { e.target.style.borderColor = T.border }}
      {...rest}
    />
  )
}

export function Label({ children, hint }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{children}</div>
      {hint && <div style={{ fontSize: 11, color: T.textMute, marginTop: 2 }}>{hint}</div>}
    </div>
  )
}

export function Stat({ label, value, color = T.primary }) {
  return (
    <div style={{
      flex: 1, minWidth: 100,
      background: T.card, border: `1px solid ${T.border}`,
      borderRadius: 10, padding: "12px 16px", textAlign: "center",
    }}>
      <div style={{ fontSize: 22, fontWeight: 700, color, lineHeight: 1.1 }}>{value}</div>
      <div style={{ fontSize: 10, color: T.textSoft, marginTop: 4, textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
    </div>
  )
}

export function Badge({ children, color = T.primary, bg }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 8px",
      borderRadius: 10,
      fontSize: 10,
      fontWeight: 600,
      color,
      background: bg || (color + "20"),
    }}>{children}</span>
  )
}

export function Empty({ icon = "📂", title, hint, action }) {
  return (
    <div style={{
      textAlign: "center",
      padding: "48px 24px",
      background: T.card,
      border: `1px dashed ${T.border}`,
      borderRadius: 10,
    }}>
      <div style={{ fontSize: 36, marginBottom: 10 }}>{icon}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: T.text, marginBottom: 6 }}>{title}</div>
      {hint && <div style={{ fontSize: 12, color: T.textSoft, marginBottom: 14, maxWidth: 380, margin: "0 auto 14px" }}>{hint}</div>}
      {action}
    </div>
  )
}

export function Spinner({ size = 14, color = T.primary }) {
  return (
    <span style={{
      display: "inline-block",
      width: size, height: size,
      border: `2px solid ${color}30`,
      borderTopColor: color,
      borderRadius: "50%",
      animation: "kw3spin .8s linear infinite",
    }}>
      <style>{`@keyframes kw3spin { to { transform: rotate(360deg); } }`}</style>
    </span>
  )
}

export function ProgressBar({ pct = 0, color = T.primary, height = 6 }) {
  const v = Math.max(0, Math.min(100, pct))
  return (
    <div style={{ width: "100%", height, background: T.border, borderRadius: height / 2, overflow: "hidden" }}>
      <div style={{
        width: `${v}%`, height: "100%", background: color, borderRadius: height / 2,
        transition: "width 0.4s ease",
      }} />
    </div>
  )
}

/** Comma-or-newline list editor (chips). */
export function ChipList({ items, onChange, placeholder = "Type and press Enter" }) {
  const [val, setVal] = React.useState("")
  const add = () => {
    const v = val.trim()
    if (!v) return
    if (items.includes(v)) { setVal(""); return }
    onChange([...items, v])
    setVal("")
  }
  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
        {items.map((it, i) => (
          <span key={i} style={{
            background: T.primaryBg, color: T.primary,
            padding: "3px 10px", borderRadius: 12, fontSize: 12,
            display: "flex", alignItems: "center", gap: 6,
          }}>
            {it}
            <button
              onClick={() => onChange(items.filter((_, j) => j !== i))}
              style={{ background: "none", border: "none", color: T.primary, cursor: "pointer", padding: 0, fontSize: 14, lineHeight: 1 }}
            >×</button>
          </span>
        ))}
      </div>
      <Input
        value={val}
        onChange={e => setVal(e.target.value)}
        onKeyDown={e => {
          if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add() }
          else if (e.key === "Backspace" && !val && items.length > 0) {
            onChange(items.slice(0, -1))
          }
        }}
        onBlur={add}
        placeholder={placeholder}
      />
    </div>
  )
}
