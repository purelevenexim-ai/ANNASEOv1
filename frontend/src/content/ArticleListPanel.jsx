import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { T, api, Badge, Btn, LoadingSpinner } from "../App"
import { useArticlePolling } from "../hooks/useArticlePolling"
import { usePipelineQuery } from "../hooks/usePipelineQuery"

// ── Status helpers ─────────────────────────────────────────────────────────────
const STATUS_COLOR = {
  draft: "gray", generating: "amber", review: "purple",
  approved: "teal", publishing: "amber", published: "teal", failed: "red",
}
const LIFECYCLE = ["draft", "generating", "review", "approved", "publishing", "published"]

// ── Lifecycle strip ────────────────────────────────────────────────────────────
function LifecycleStrip({ articles }) {
  const counts = LIFECYCLE.reduce((acc, s) => {
    acc[s] = (articles || []).filter(a => a.status === s).length; return acc
  }, {})
  const failedCount = (articles || []).filter(a => a.status === "failed").length

  const accent = { draft: T.gray, generating: T.amber, review: T.purple, approved: T.teal, publishing: T.amber, published: T.teal }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0, overflowX: "auto", paddingBottom: 2 }}>
      {LIFECYCLE.map((s, i) => (
        <div key={s} style={{ display: "flex", alignItems: "center" }}>
          <div style={{
            padding: "3px 9px", borderRadius: 99, fontSize: 10, fontWeight: 500, whiteSpace: "nowrap",
            background: counts[s] > 0 ? `${accent[s]}22` : "rgba(0,0,0,0.04)",
            color: counts[s] > 0 ? accent[s] : T.gray,
          }}>
            {s} {counts[s] > 0 && <strong>({counts[s]})</strong>}
          </div>
          {i < LIFECYCLE.length - 1 && (
            <span style={{ color: T.gray, padding: "0 2px", fontSize: 9 }}>›</span>
          )}
        </div>
      ))}
      {failedCount > 0 && (
        <div style={{ marginLeft: 8, padding: "3px 9px", borderRadius: 99, fontSize: 10, background: "#FEE2E2", color: T.red }}>
          failed ({failedCount})
        </div>
      )}
    </div>
  )
}

// ── Compact pipeline progress (inline in article list) ─────────────────────────
function CompactPipelineProgress({ articleId }) {
  const { data, isLoading } = usePipelineQuery(articleId)
  const steps = data?.steps || []
  const isPaused = data?.is_paused || false
  const doneCount = steps.filter(s => s.status === "done").length
  const runningStep = steps.find(s => s.status === "running")
  const pausedStep = steps.find(s => s.status === "paused")
  const totalSteps = 11
  const pct = Math.round((doneCount / totalSteps) * 100)

  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
        <div style={{ fontSize: 9, color: isPaused ? T.purple : T.amber, fontWeight: 600, flexShrink: 0 }}>
          {isPaused ? "⏸ Paused" : runningStep ? `Step ${runningStep.step}/${totalSteps}: ${runningStep.name}` : isLoading ? "Starting…" : `${doneCount}/${totalSteps} steps`}
        </div>
        <div style={{ fontSize: 9, color: T.textSoft, marginLeft: "auto" }}>{pct}%</div>
      </div>
      <div style={{ height: 3, background: `${T.amber}22`, borderRadius: 99 }}>
        <div style={{ height: 3, borderRadius: 99, width: `${pct}%`, background: isPaused ? T.purple : T.amber, transition: "width 0.6s ease" }} />
      </div>
      <div style={{ display: "flex", gap: 3, marginTop: 5 }}>
        {Array.from({ length: totalSteps }, (_, i) => i + 1).map(n => {
          const s = steps.find(st => st.step === n)
          const isDone = s?.status === "done"
          const isRunning = s?.status === "running"
          const isError = s?.status === "error"
          const isPausedStep = s?.status === "paused"
          return (
            <div key={n} title={`Step ${n}`} style={{
              width: 14, height: 14, borderRadius: "50%", flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 8, fontWeight: 700,
              background: isDone ? T.teal : isRunning ? T.amber : isError ? "#ef4444" : isPausedStep ? T.purple : `${T.gray}33`,
              color: isDone || isRunning || isError || isPausedStep ? "#fff" : T.gray,
              boxShadow: isRunning ? `0 0 0 2px ${T.amber}50` : isPausedStep ? `0 0 0 2px ${T.purple}50` : "none",
              animation: isRunning ? "pulse 1s infinite" : "none",
            }}>
              {isDone ? "✓" : isError ? "✕" : isPausedStep ? "⏸" : n}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Article list item ──────────────────────────────────────────────────────────
function ArticleItem({ article: a, isSelected, onSelect, onRetry, onDelete, onEdit, onRegenerate, isChecked, onCheck }) {
  const ptIcon = { article: "📝", homepage: "🏠", product: "🛍", about: "👥", landing: "🎯", service: "🔧" }[a.page_type] || ""
  return (
    <div
      onClick={onSelect}
      style={{
        padding: "11px 14px",
        cursor: "pointer",
        borderBottom: `1px solid ${T.border}`,
        background: isSelected ? T.purpleLight : "transparent",
        borderLeft: `3px solid ${isSelected ? T.purple : a.status === "generating" ? T.amber : "transparent"}`,
        transition: "background 0.1s",
      }}
      onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = "#F2F2F7" }}
      onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = "transparent" }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        {/* Checkbox for bulk selection */}
        <input
          type="checkbox"
          checked={isChecked || false}
          onClick={e => e.stopPropagation()}
          onChange={e => { e.stopPropagation(); onCheck?.(a.article_id, e.target.checked) }}
          style={{ marginTop: 2, cursor: "pointer" }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 12, fontWeight: 500, color: T.text,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            display: "flex", alignItems: "center", gap: 4,
          }}>
            {ptIcon && <span style={{ fontSize: 11 }}>{ptIcon}</span>}
            {a.title || a.keyword}
          </div>
          <div style={{ fontSize: 10, color: T.textSoft, marginTop: 2 }}>{a.keyword}</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3, flexShrink: 0 }}>
          <Badge color={STATUS_COLOR[a.status] || "gray"}>{a.status}</Badge>
          {(a.review_score > 0) && (
            <span style={{
              fontSize: 10, fontWeight: 700,
              color: a.review_score >= 70 ? T.teal : a.review_score >= 45 ? T.amber : T.red,
            }}>
              {a.review_score}<span style={{ fontSize: 9, fontWeight: 400, color: T.textSoft }}>%</span>
            </span>
          )}
          {a.seo_score > 0 && a.review_score === 0 && (
            <span style={{ fontSize: 9, color: T.textSoft }}>
              Score:{Math.round(a.seo_score)}
            </span>
          )}
        </div>
      </div>
      {/* Mini pipeline progress for generating articles */}
      {a.status === "generating" && (
        <CompactPipelineProgress articleId={a.article_id} />
      )}
      <div style={{ display: "flex", gap: 4, marginTop: 6, justifyContent: "flex-end" }}>
        {(a.status === "failed" || a.status === "generating") && (
          <button onClick={e => { e.stopPropagation(); onRetry() }}
            style={{ background: "none", border: `1px solid ${T.gray}`, borderRadius: 5, cursor: "pointer", color: T.gray, fontSize: 10, padding: "1px 6px" }}>
            {a.status === "generating" ? "Restart" : "Retry"}
          </button>
        )}
        {/* Bug #1 fix: use || 0 instead of || 100 to avoid false positive */}
        {a.status === "draft" && (a.review_score || a.seo_score || 0) < 65 && (
          <button onClick={e => { e.stopPropagation(); onRegenerate() }}
            style={{ background: "none", border: `1px solid ${T.amber}`, borderRadius: 5, cursor: "pointer", color: T.amber, fontSize: 10, padding: "1px 6px" }} title="Regenerate with poor quality">
            🔄 Regen
          </button>
        )}
        <button onClick={e => { e.stopPropagation(); onEdit() }}
          style={{ background: "none", border: "none", cursor: "pointer", color: T.textSoft, fontSize: 12 }} title="Edit meta">✎</button>
        <button onClick={e => { e.stopPropagation(); if (window.confirm("Delete this article?")) onDelete() }}
          style={{ background: "none", border: "none", cursor: "pointer", color: T.red, fontSize: 11 }} title="Delete">✕</button>
      </div>
    </div>
  )
}

// ── Article List Panel ─────────────────────────────────────────────────────────
export default function ArticleListPanel({ projectId, selected, onSelect, onEditMeta, onShowGenModal, onShowPrompts, onTestKeyword }) {
  const [bulkSelected, setBulkSelected] = useState([])
  const qclient = useQueryClient()

  const { data: articles, isLoading } = useArticlePolling(projectId)

  const retry = useMutation({
    mutationFn: (id) => api.post(`/api/content/${id}/retry`),
    onSuccess: () => qclient.invalidateQueries(["articles", projectId]),
  })

  const regenerate = useMutation({
    mutationFn: async ({ id, step_mode = "pause" }) => {
      let ai_routing = null
      try {
        const saved = await api.get("/api/ai/routing")
        if (saved && typeof saved === "object" && saved.research) ai_routing = saved
      } catch (_) {}
      return api.post(`/api/content/${id}/regenerate`, { step_mode, ai_routing })
    },
    onSuccess: () => qclient.invalidateQueries(["articles", projectId]),
  })

  // Bug #7 fix: use mutation variables (ids) instead of stale closure (bulkSelected)
  const bulkDelete = useMutation({
    mutationFn: (ids) => Promise.all(ids.map(id => api.delete(`/api/content/${id}`))),
    onSuccess: (_data, ids) => {
      qclient.invalidateQueries(["articles", projectId])
      setBulkSelected([])
      if (selected && ids.includes(selected.article_id)) onSelect(null)
    },
  })

  const bulkRetry = useMutation({
    mutationFn: (ids) => Promise.all(ids.map(id => api.post(`/api/content/${id}/retry`))),
    onSuccess: () => {
      qclient.invalidateQueries(["articles", projectId])
      setBulkSelected([])
    },
  })

  return (
    <div style={{ width: 300, flexShrink: 0, borderRight: `1px solid ${T.border}`, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* List header: lifecycle + generate */}
      <div style={{ padding: "12px 14px", borderBottom: `1px solid ${T.border}` }}>
        <LifecycleStrip articles={articles} />
      </div>
      <div style={{ padding: "10px 12px", borderBottom: `1px solid ${T.border}`, display: "flex", gap: 6 }}>
        <Btn
          onClick={onShowGenModal}
          variant="primary"
          style={{ flex: 1 }}
        >
          + New Article
        </Btn>
        <button
          onClick={onShowPrompts}
          title="Edit AI prompts"
          style={{
            padding: "7px 10px", borderRadius: 8, fontSize: 12, cursor: "pointer",
            border: `1px solid ${T.border}`, background: "transparent", color: T.textSoft,
            flexShrink: 0,
          }}
        >
          ✏️
        </button>
      </div>

      {/* Bulk action toolbar */}
      {bulkSelected.length > 0 && (
        <div style={{ padding: "8px 12px", borderBottom: `1px solid ${T.border}`, background: T.purpleLight, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: T.purple }}>{bulkSelected.length} selected</span>
          <button onClick={() => setBulkSelected([])} style={{ fontSize: 11, padding: "2px 6px", border: `1px solid ${T.purple}`, borderRadius: 4, background: "transparent", cursor: "pointer", color: T.purple }}>Deselect All</button>
          <Btn small variant="default" onClick={() => bulkRetry.mutate(bulkSelected)} disabled={bulkRetry.isPending} style={{ fontSize: 10 }}>
            {bulkRetry.isPending ? "Restarting..." : "🔄 Restart"}
          </Btn>
          <Btn small variant="danger" onClick={() => {
            if (window.confirm(`Delete ${bulkSelected.length} article(s)?`)) {
              bulkDelete.mutate(bulkSelected)
            }
          }} disabled={bulkDelete.isPending} style={{ fontSize: 10 }}>
            {bulkDelete.isPending ? "Deleting..." : "✕ Delete"}
          </Btn>
        </div>
      )}

      {/* Article list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {isLoading ? (
          <LoadingSpinner />
        ) : (articles || []).length === 0 ? (
          <div style={{ padding: 20, textAlign: "center", color: T.textSoft, fontSize: 12 }}>
            No articles yet. Generate your first one above.
          </div>
        ) : (
          (articles || []).map(a => (
            <ArticleItem
              key={a.article_id}
              article={a}
              isSelected={selected?.article_id === a.article_id}
              onSelect={() => onSelect(a)}
              onRetry={() => retry.mutate(a.article_id)}
              onRegenerate={() => regenerate.mutate({ id: a.article_id, step_mode: "pause" })}
              onDelete={() => api.delete(`/api/content/${a.article_id}`).then(() => {
                qclient.invalidateQueries(["articles", projectId])
                if (selected?.article_id === a.article_id) onSelect(null)
              })}
              onEdit={() => onEditMeta(a)}
              isChecked={bulkSelected.includes(a.article_id)}
              onCheck={(id, checked) => {
                if (checked) {
                  setBulkSelected(prev => [...prev, id])
                } else {
                  setBulkSelected(prev => prev.filter(bid => bid !== id))
                }
              }}
            />
          ))
        )}
      </div>
    </div>
  )
}
