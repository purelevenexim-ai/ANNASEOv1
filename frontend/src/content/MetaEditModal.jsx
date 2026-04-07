import { useState } from "react"
import { T, Btn } from "../App"

export default function MetaEditModal({ article, onClose, onSave }) {
  const [data, setData] = useState({
    title: article.title || "",
    meta_title: article.meta_title || "",
    meta_desc: article.meta_desc || "",
  })

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{ background: "#fff", borderRadius: 14, padding: 24, width: 480, boxShadow: "0 8px 40px rgba(0,0,0,0.15)" }}>
        <div style={{ fontSize: 17, fontWeight: 600, marginBottom: 16, color: T.text }}>Edit Metadata</div>
        {[["Title", "title"], ["Meta title", "meta_title"], ["Meta description", "meta_desc"]].map(([label, field]) => (
          <div key={field} style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, color: T.textSoft, display: "block", marginBottom: 4 }}>{label}</label>
            {field === "meta_desc" ? (
              <textarea
                value={data[field]}
                onChange={e => setData({ ...data, [field]: e.target.value })}
                rows={3}
                style={{ width: "100%", padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, boxSizing: "border-box", resize: "vertical", fontFamily: "inherit" }}
              />
            ) : (
              <input
                value={data[field]}
                onChange={e => setData({ ...data, [field]: e.target.value })}
                style={{ width: "100%", padding: "7px 10px", borderRadius: 8, border: `1px solid ${T.border}`, fontSize: 12, boxSizing: "border-box" }}
              />
            )}
          </div>
        ))}
        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <Btn onClick={onClose} style={{ flex: 1 }}>Cancel</Btn>
          <Btn onClick={() => onSave(data)} variant="primary" style={{ flex: 1 }}>Save</Btn>
        </div>
      </div>
    </div>
  )
}
