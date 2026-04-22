/**
 * DataTable — Reusable sortable, filterable, searchable table with bulk actions.
 *
 * Props:
 *   columns:     [{key, label, sortable?, filterable?, searchable?, type?, editable?, options?}]
 *   data:        array of row objects
 *   bulkActions: [{label, action(selectedIds), color?, confirm?}]
 *   onRowEdit:   (rowId, field, newValue) => void
 *   rowKey:      string — field name for unique row id (default "id")
 *   pageSize:    number (default 50)
 *   emptyText:   string
 */
import React, { useState, useMemo, useCallback } from "react"
import ConfirmModal from "./ConfirmModal"

const PAGE_SIZES = [25, 50, 100]

export default function DataTable({
  columns = [],
  data = [],
  bulkActions = [],
  onRowEdit,
  rowKey = "id",
  pageSize: defaultPageSize = 50,
  emptyText = "No data",
}) {
  const [sortField, setSortField] = useState(null)
  const [sortDir, setSortDir] = useState("asc")
  const [search, setSearch] = useState("")
  const [filters, setFilters] = useState({})
  const [selected, setSelected] = useState(new Set())
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(defaultPageSize)
  const [editCell, setEditCell] = useState(null) // {row, col}
  const [editValue, setEditValue] = useState("")
  const [pendingBulkAction, setPendingBulkAction] = useState(null)

  // Build filter options from data
  const filterOptions = useMemo(() => {
    const opts = {}
    columns.filter((c) => c.filterable).forEach((c) => {
      const vals = [...new Set(data.map((r) => String(r[c.key] || "—")).filter(Boolean))]
      opts[c.key] = vals.sort()
    })
    return opts
  }, [data, columns])

  // Filter + search + sort
  const processed = useMemo(() => {
    let rows = [...data]

    // Search
    if (search) {
      const q = search.toLowerCase()
      const searchCols = columns.filter((c) => c.searchable !== false).map((c) => c.key)
      rows = rows.filter((r) => searchCols.some((k) => String(r[k] || "").toLowerCase().includes(q)))
    }

    // Column filters
    for (const [key, val] of Object.entries(filters)) {
      if (val) rows = rows.filter((r) => String(r[key] || "—") === val)
    }

    // Sort
    if (sortField) {
      const col = columns.find((c) => c.key === sortField)
      rows.sort((a, b) => {
        let va = a[sortField] ?? ""
        let vb = b[sortField] ?? ""
        if (col?.type === "number") {
          va = parseFloat(va) || 0
          vb = parseFloat(vb) || 0
        } else {
          va = String(va).toLowerCase()
          vb = String(vb).toLowerCase()
        }
        if (va < vb) return sortDir === "asc" ? -1 : 1
        if (va > vb) return sortDir === "asc" ? 1 : -1
        return 0
      })
    }

    return rows
  }, [data, search, filters, sortField, sortDir, columns])

  const totalPages = Math.ceil(processed.length / pageSize)
  const pageRows = processed.slice(page * pageSize, (page + 1) * pageSize)

  const toggleSort = (key) => {
    if (sortField === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortField(key)
      setSortDir("asc")
    }
  }

  const toggleRow = (id) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    const pageIds = new Set(pageRows.map((r) => r[rowKey]))
    const allPageSelected = pageRows.length > 0 && pageRows.every((r) => selected.has(r[rowKey]))
    if (allPageSelected) {
      // Deselect only current page items, keep cross-page selections
      setSelected((prev) => {
        const next = new Set(prev)
        pageIds.forEach((id) => next.delete(id))
        return next
      })
    } else {
      // Select all on current page, keep existing cross-page selections
      setSelected((prev) => new Set([...prev, ...pageIds]))
    }
  }

  const startEdit = (rowId, colKey, currentValue) => {
    if (!onRowEdit) return
    setEditCell({ row: rowId, col: colKey })
    setEditValue(String(currentValue ?? ""))
  }

  const commitEdit = () => {
    if (editCell && onRowEdit) {
      onRowEdit(editCell.row, editCell.col, editValue)
    }
    setEditCell(null)
    setEditValue("")
  }

  const cancelEdit = () => {
    setEditCell(null)
    setEditValue("")
  }

  const handleBulkAction = (action) => {
    const ids = [...selected]
    if (!ids.length) return
    if (action.confirm) {
      setPendingBulkAction({ action, ids })
      return
    }
    action.action(ids)
    setSelected(new Set())
  }

  const confirmBulkAction = () => {
    if (pendingBulkAction) {
      pendingBulkAction.action.action(pendingBulkAction.ids)
      setSelected(new Set())
      setPendingBulkAction(null)
    }
  }

  const exportCSV = () => {
    const header = columns.map((c) => c.label).join(",")
    const rows = processed.map((r) => columns.map((c) => `"${String(r[c.key] ?? "").replace(/"/g, '""')}"`).join(","))
    const csv = [header, ...rows].join("\n")
    const blob = new Blob([csv], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "keywords.csv"
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ marginTop: 12 }}>
      <ConfirmModal
        open={!!pendingBulkAction}
        title="Confirm action"
        message={pendingBulkAction?.action?.confirm || "Are you sure?"}
        confirmLabel={pendingBulkAction?.action?.label || "Confirm"}
        danger
        onConfirm={confirmBulkAction}
        onCancel={() => setPendingBulkAction(null)}
      />
      {/* Toolbar */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0) }}
          placeholder="Search..."
          style={{ flex: "1 1 200px", padding: "5px 10px", borderRadius: 5, border: "1px solid #d1d5db", fontSize: 12, outline: "none" }}
        />
        {columns.filter((c) => c.filterable).map((c) => (
          <select
            key={c.key}
            value={filters[c.key] || ""}
            onChange={(e) => { setFilters((prev) => ({ ...prev, [c.key]: e.target.value })); setPage(0) }}
            style={{ padding: "5px 8px", borderRadius: 5, border: "1px solid #d1d5db", fontSize: 11, background: "#f9fafb" }}
          >
            <option value="">{c.label}: All</option>
            {(filterOptions[c.key] || []).map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        ))}
        <button onClick={exportCSV} style={btnStyle("#6b7280")}>Export CSV</button>
      </div>

      {/* Bulk actions */}
      {selected.size > 0 && bulkActions.length > 0 && (
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8, padding: "6px 10px", background: "#eff6ff", borderRadius: 6, border: "1px solid #bfdbfe" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#1e40af" }}>{selected.size} selected</span>
          {bulkActions.map((a, i) => (
            <button key={i} onClick={() => handleBulkAction(a)} style={btnStyle(a.color || "#3b82f6")}>
              {a.label}
            </button>
          ))}
          <button onClick={() => setSelected(new Set())} style={btnStyle("#6b7280")}>Clear</button>
        </div>
      )}

      {/* Count */}
      <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>
        Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, processed.length)} of {processed.length}
        {processed.length !== data.length && ` (filtered from ${data.length})`}
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto", border: "1px solid #e5e7eb", borderRadius: 8 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "#f9fafb" }}>
              {bulkActions.length > 0 && (
                <th style={{ ...thS, width: 32 }}>
                  <input type="checkbox" checked={pageRows.length > 0 && pageRows.every((r) => selected.has(r[rowKey]))}
                    onChange={toggleAll} />
                </th>
              )}
              {columns.map((c) => (
                <th
                  key={c.key}
                  onClick={() => c.sortable && toggleSort(c.key)}
                  style={{ ...thS, cursor: c.sortable ? "pointer" : "default", userSelect: "none" }}
                >
                  {c.label}
                  {sortField === c.key && (
                    <span style={{ marginLeft: 4, fontSize: 10 }}>{sortDir === "asc" ? "▲" : "▼"}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.length === 0 ? (
              <tr><td colSpan={columns.length + (bulkActions.length > 0 ? 1 : 0)} style={{ ...tdS, color: "#9ca3af", textAlign: "center" }}>{emptyText}</td></tr>
            ) : (
              pageRows.map((row) => {
                const id = row[rowKey]
                return (
                  <tr key={id} style={{ borderBottom: "1px solid #f3f4f6", background: selected.has(id) ? "#eff6ff" : "transparent" }}>
                    {bulkActions.length > 0 && (
                      <td style={{ ...tdS, width: 32 }}>
                        <input type="checkbox" checked={selected.has(id)} onChange={() => toggleRow(id)} />
                      </td>
                    )}
                    {columns.map((c) => {
                      const isEditing = editCell?.row === id && editCell?.col === c.key
                      const val = row[c.key]
                      if (isEditing) {
                        return (
                          <td key={c.key} style={tdS}>
                            {c.options ? (
                              <select value={editValue} onChange={(e) => setEditValue(e.target.value)}
                                onBlur={commitEdit} autoFocus
                                style={{ width: "100%", fontSize: 11, padding: "2px 4px", borderRadius: 3, border: "1px solid #3b82f6" }}>
                                {c.options.map((o) => <option key={o} value={o}>{o}</option>)}
                              </select>
                            ) : (
                              <input value={editValue} onChange={(e) => setEditValue(e.target.value)}
                                onBlur={commitEdit} onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit() }}
                                autoFocus
                                style={{ width: "100%", fontSize: 11, padding: "2px 4px", borderRadius: 3, border: "1px solid #3b82f6" }} />
                            )}
                          </td>
                        )
                      }
                      return (
                        <td
                          key={c.key}
                          style={{ ...tdS, cursor: c.editable ? "pointer" : "default" }}
                          onDoubleClick={() => c.editable && startEdit(id, c.key, val)}
                          title={c.editable ? "Double-click to edit" : undefined}
                        >
                          {c.type === "number" ? (typeof val === "number" ? val.toFixed(c.decimals ?? 2) : val ?? "—")
                            : c.type === "badge" ? <TinyBadge value={val} /> : String(val ?? "—")}
                        </td>
                      )
                    })}
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <button onClick={() => setPage(0)} disabled={page === 0} style={pgBtn}>«</button>
            <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} style={pgBtn}>‹</button>
            <span style={{ fontSize: 12, color: "#6b7280", padding: "0 8px" }}>Page {page + 1} / {totalPages}</span>
            <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1} style={pgBtn}>›</button>
            <button onClick={() => setPage(totalPages - 1)} disabled={page >= totalPages - 1} style={pgBtn}>»</button>
          </div>
          <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(0) }}
            style={{ fontSize: 11, padding: "3px 6px", borderRadius: 4, border: "1px solid #d1d5db" }}>
            {PAGE_SIZES.map((s) => <option key={s} value={s}>{s} / page</option>)}
          </select>
        </div>
      )}
    </div>
  )
}

function TinyBadge({ value }) {
  const colorMap = {
    commercial: { bg: "#dcfce7", fg: "#166534" },
    informational: { bg: "#dbeafe", fg: "#1e40af" },
    navigational: { bg: "#fef9c3", fg: "#854d0e" },
    top100: { bg: "#fef3c7", fg: "#92400e" },
    approved: { bg: "#dcfce7", fg: "#166534" },
    candidate: { bg: "#f3f4f6", fg: "#6b7280" },
    rejected: { bg: "#fee2e2", fg: "#991b1b" },
    pillar: { bg: "#ede9fe", fg: "#5b21b6" },
    supporting: { bg: "#f3f4f6", fg: "#374151" },
    bridge: { bg: "#dbeafe", fg: "#1e40af" },
  }
  const v = String(value || "").toLowerCase()
  const c = colorMap[v] || { bg: "#f3f4f6", fg: "#6b7280" }
  return (
    <span style={{ background: c.bg, color: c.fg, padding: "1px 7px", borderRadius: 8, fontSize: 11, fontWeight: 500 }}>
      {value || "—"}
    </span>
  )
}

const thS = { textAlign: "left", padding: "6px 8px", fontSize: 11, color: "#6b7280", fontWeight: 600, whiteSpace: "nowrap", borderBottom: "1px solid #e5e7eb" }
const tdS = { padding: "5px 8px", fontSize: 12 }
const pgBtn = { padding: "3px 8px", borderRadius: 4, border: "1px solid #d1d5db", background: "#fff", cursor: "pointer", fontSize: 12 }

function btnStyle(color) {
  return { padding: "4px 10px", borderRadius: 5, border: "none", background: color, color: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer" }
}
