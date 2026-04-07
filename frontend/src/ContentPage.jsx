import { useState, useEffect } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { T, api, useStore, Badge } from "./App"
import { ContentPipelineTab } from "./App"
import AIHub from "./AIHub"
import MetaEditModal from "./content/MetaEditModal"
import PromptsDrawer from "./content/PromptsDrawer"
import ArticleListPanel from "./content/ArticleListPanel"
import EditorPanel from "./content/EditorPanel"
import { useArticlePolling } from "./hooks/useArticlePolling"
import NewArticleModal from "./content/NewArticleModal"
import PipelinePanel from "./content/PipelinePanel"

// ── Main ContentPage ───────────────────────────────────────────────────────────
export default function ContentPage() {
  const { activeProject } = useStore()
  const qclient = useQueryClient()

  // UI state
  const [tab, setTab] = useState("articles")
  const [showGenModal, setShowGenModal] = useState(false)
  const [showPrompts, setShowPrompts] = useState(false)
  const [testKeyword, setTestKeyword] = useState("")
  const [selected, setSelected] = useState(null)
  const [editingMeta, setEditingMeta] = useState(null)

  // Queries — share the same cache key as ArticleListPanel via useArticlePolling
  const { data: articles } = useArticlePolling(activeProject)

  // Mutations
  const generate = useMutation({
    mutationFn: (payload) => api.post("/api/content/generate", { ...payload, project_id: activeProject }),
    onSuccess: () => { qclient.invalidateQueries(["articles", activeProject]); setShowGenModal(false) },
  })

  const retry = useMutation({
    mutationFn: (id) => api.post(`/api/content/${id}/retry`),
    onSuccess: () => qclient.invalidateQueries(["articles", activeProject]),
  })

  // Sync selected article when list refreshes
  useEffect(() => {
    if (selected && articles) {
      const updated = articles.find(a => a.article_id === selected.article_id)
      if (updated) setSelected(updated)
    }
  }, [articles]) // eslint-disable-line

  if (!activeProject) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300, color: T.textSoft, fontSize: 13 }}>
        Select a project to manage content.
      </div>
    )
  }

  const tabBtn = (t, label) => (
    <button onClick={() => setTab(t)} style={{
      padding: "5px 14px", borderRadius: 99, fontSize: 12, fontWeight: 500,
      border: "none", cursor: "pointer",
      background: tab === t ? T.purple : "transparent",
      color: tab === t ? "#fff" : T.gray,
    }}>{label}</button>
  )

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 48px)", overflow: "hidden" }}>
      {/* Page header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexShrink: 0 }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: T.text, letterSpacing: -0.3 }}>Content</div>
        <div style={{ display: "flex", gap: 4 }}>
          {tabBtn("articles", "Articles")}
          {tabBtn("pipeline", "Pipeline")}
          {tabBtn("aihub", "AI Hub")}
        </div>
      </div>

      {/* Pipeline tab */}
      {tab === "pipeline" && (
        <div style={{ flex: 1, overflowY: "auto" }}>
          <ContentPipelineTab projectId={activeProject} />
        </div>
      )}

      {/* AI Hub tab */}
      {tab === "aihub" && (
        <div style={{ flex: 1, display: "flex", overflow: "hidden", borderRadius: 12, border: `1px solid ${T.border}`, background: "#F2F2F7" }}>
          <AIHub />
        </div>
      )}

      {/* Articles tab */}
      {tab === "articles" && (
        <div style={{ display: "flex", flex: 1, gap: 0, overflow: "hidden", borderRadius: 12, border: `1px solid ${T.border}`, background: "#fff" }}>

          {/* Left: article list */}
          <ArticleListPanel
            projectId={activeProject}
            selected={selected}
            onSelect={setSelected}
            onEditMeta={setEditingMeta}
            onShowGenModal={() => setShowGenModal(true)}
            onShowPrompts={() => setShowPrompts(true)}
            onTestKeyword={setTestKeyword}
          />

          {/* Center: editor area */}
          {selected ? (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>

              {/* ── GENERATING VIEW ── show pipeline progress + console */}
              {selected.status === "generating" ? (
                <>
                  {/* Thin header with keyword */}
                  <div style={{
                    padding: "10px 16px", borderBottom: `1px solid ${T.border}`,
                    background: "#fff", display: "flex", alignItems: "center", gap: 8,
                    flexShrink: 0,
                  }}>
                    <div style={{ flex: 1, fontSize: 13, fontWeight: 600, color: T.text,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {selected.keyword}
                    </div>
                    <Badge color="amber">generating</Badge>
                    <button
                      onClick={() => {
                        if (window.confirm("Stop generation and keep current progress?")) {
                          api.post(`/api/content/${selected.article_id}/pipeline/cancel`).then(() => {
                            qclient.invalidateQueries(["pipeline", selected.article_id])
                            qclient.invalidateQueries(["articles", activeProject])
                          })
                        }
                      }}
                      style={{ background: "none", border: `1px solid ${T.red}`, borderRadius: 6,
                        cursor: "pointer", color: T.red, fontSize: 11, padding: "2px 8px" }}>
                      ⏹ Stop
                    </button>
                    <button
                      onClick={() => retry.mutate(selected.article_id)}
                      disabled={retry.isPending}
                      style={{ background: "none", border: `1px solid ${T.gray}`, borderRadius: 6,
                        cursor: retry.isPending ? "wait" : "pointer", color: T.gray, fontSize: 11, padding: "2px 8px",
                        opacity: retry.isPending ? 0.5 : 1 }}>
                      {retry.isPending ? "Restarting..." : "🔄 Restart"}
                    </button>
                  </div>
                  <PipelinePanel
                    articleId={selected.article_id}
                    onComplete={() => {
                      qclient.invalidateQueries(["articles", activeProject])
                      setSelected(null)
                    }}
                  />
                </>
              ) : (
                <EditorPanel
                  article={selected}
                  projectId={activeProject}
                  onStatusChange={() => qclient.invalidateQueries(["articles", activeProject])}
                />
              )}
            </div>
          ) : (
            /* No article selected — placeholder */
            <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: T.textSoft }}>
              <div style={{ fontSize: 18, fontWeight: 600, color: T.gray, marginBottom: 8 }}>
                Select an article
              </div>
              <div style={{ fontSize: 13 }}>
                Choose an article from the list to open the editor.
              </div>
            </div>
          )}
        </div>
      )}

      {/* Meta edit modal */}
      {editingMeta && (
        <MetaEditModal
          article={editingMeta}
          onClose={() => setEditingMeta(null)}
          onSave={async (data) => {
            await api.put(`/api/content/${editingMeta.article_id}`, data)
            qclient.invalidateQueries(["articles", activeProject])
            setEditingMeta(null)
          }}
        />
      )}

      {/* Prompts drawer */}
      {showPrompts && (
        <PromptsDrawer
          onClose={() => setShowPrompts(false)}
          onTest={(kw) => { setTestKeyword(kw); setShowPrompts(false); setShowGenModal(true) }}
        />
      )}

      {/* New article intake modal */}
      {showGenModal && (
        <NewArticleModal
          onClose={() => { setShowGenModal(false); setTestKeyword("") }}
          onGenerate={(payload) => generate.mutate(payload)}
          isPending={generate.isPending}
          initialKeyword={testKeyword}
        />
      )}
    </div>
  )
}
