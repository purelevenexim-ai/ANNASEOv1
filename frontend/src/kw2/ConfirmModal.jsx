import React from "react"

/**
 * App-native confirmation modal (replaces browser confirm()).
 *
 * Usage:
 *   <ConfirmModal
 *     open={showConfirm}
 *     title="Delete keyword?"
 *     message="This action cannot be undone."
 *     confirmLabel="Delete"
 *     danger
 *     onConfirm={() => { doDelete(); setShowConfirm(false) }}
 *     onCancel={() => setShowConfirm(false)}
 *   />
 */
export default function ConfirmModal({
  open,
  title = "Are you sure?",
  message = "",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "rgba(0,0,0,0.35)",
      }}
      onClick={onCancel}
    >
      <div
        style={{
          background: "#fff", borderRadius: 10, padding: "24px 28px",
          minWidth: 340, maxWidth: 460, boxShadow: "0 8px 30px rgba(0,0,0,0.18)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ fontSize: 16, fontWeight: 600, color: "#111827", margin: "0 0 8px" }}>
          {title}
        </h3>
        {message && (
          <p style={{ fontSize: 13, color: "#6b7280", margin: "0 0 20px", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
            {message}
          </p>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button
            onClick={onCancel}
            style={{
              padding: "7px 16px", borderRadius: 6, border: "1px solid #d1d5db",
              background: "#fff", color: "#374151", fontSize: 13, cursor: "pointer",
            }}
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: "7px 16px", borderRadius: 6, border: "none",
              background: danger ? "#dc2626" : "#2563eb",
              color: "#fff", fontSize: 13, fontWeight: 500, cursor: "pointer",
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
