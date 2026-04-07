// Step 6 — Final Review
// Lists generated content articles from pipeline runs.
// Approve, freeze, or schedule articles. Toggle calendar view.
// "Complete & Go to Calendar" exits the workflow.

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNotification } from "../store/notification"
import { apiCall, T, Card, Btn, Spinner } from "./shared"

export default function Step6FinalReview({ projectId, onBack, onGoToCalendar }) {
  const notify = useNotification(s => s.notify)

  const [filterStatus, setFilterStatus]     = useState("all")
  const [viewMode, setViewMode]             = useState("list")  // list | calendar
  const [calendarMonth, setCalendarMonth]   = useState(() => new Date().toISOString().slice(0, 7))
  const [schedulingId, setSchedulingId]     = useState(null)
  const [scheduleDateInput, setScheduleDateInput] = useState("")

  // ── Data queries ───────────────────────────────────────────────────────────
  const { data: articles = [], isLoading, refetch } = useQuery({
    queryKey:  ["content-articles", projectId],
    queryFn:   () => apiCall(`/api/projects/${projectId}/content?limit=100`),
    enabled:   !!projectId,
    refetchInterval: 10_000,
  })

  const { data: calendarData, refetch: refetchCalendar } = useQuery({
    queryKey: ["calendar-items", projectId, calendarMonth],
    queryFn:  () => apiCall(`/api/projects/${projectId}/calendar-items?month=${calendarMonth}`),
    enabled:  !!projectId && viewMode === "calendar",
  })

  // ── Actions ────────────────────────────────────────────────────────────────
  const doApprove = async (articleId) => {
    try {
      await apiCall(`/api/content/${articleId}/approve`, "POST")
      refetch()
      notify("Article approved", "success")
    } catch (e) {
      notify("Approve failed: " + e.message, "error")
    }
  }

  const doFreeze = async (articleId, frozen) => {
    try {
      await apiCall(`/api/content/${articleId}/${frozen ? "unfreeze" : "freeze"}`, "POST")
      refetch()
      notify(frozen ? "Article unfrozen" : "Article frozen", "success")
    } catch (e) {
      notify("Action failed: " + e.message, "error")
    }
  }

  const doSchedule = async (articleId, date) => {
    if (!date) { notify("Pick a date first", "error"); return }
    try {
      await apiCall(`/api/content/${articleId}/schedule?schedule_date=${date}`, "PUT")
      setSchedulingId(null)
      setScheduleDateInput("")
      refetch()
      refetchCalendar()
      notify("Article scheduled", "success")
    } catch (e) {
      notify("Schedule failed: " + e.message, "error")
    }
  }

  // ── Derived ────────────────────────────────────────────────────────────────
  const filtered = filterStatus === "all"
    ? articles
    : articles.filter(a => a.status === filterStatus)

  const statusColor = { pending: T.amber, approved: T.teal, published: T.green, draft: T.gray }
  const statusBg    = { pending: "#fef3c7", approved: "#d1fae5", published: "#dcfce7", draft: T.grayLight }

  return (
    <div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <Card>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>Step 6 — Final Review</div>
            <div style={{ fontSize: 12, color: T.textSoft }}>
              Review generated content articles. Approve, schedule, or freeze each article.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={onBack} small>← Back</Btn>
            <Btn small
              style={{ background: viewMode === "list" ? T.purple : undefined, color: viewMode === "list" ? "#fff" : undefined }}
              onClick={() => setViewMode("list")}>
              List
            </Btn>
            <Btn small
              style={{ background: viewMode === "calendar" ? T.teal : undefined, color: viewMode === "calendar" ? "#fff" : undefined }}
              onClick={() => setViewMode("calendar")}>
              Calendar
            </Btn>
          </div>
        </div>

        {/* Stats bar */}
        {articles.length > 0 && (
          <div style={{
            display: "flex", gap: 16, marginBottom: 12, padding: "8px 12px",
            background: T.grayLight, borderRadius: 8, fontSize: 12,
          }}>
            <span>Total: <strong>{articles.length}</strong></span>
            <span style={{ color: T.teal }}>Approved: <strong>{articles.filter(a => a.status === "approved").length}</strong></span>
            <span style={{ color: T.green }}>Published: <strong>{articles.filter(a => a.status === "published").length}</strong></span>
            <span style={{ color: T.amber }}>Pending: <strong>{articles.filter(a => !["approved","published"].includes(a.status)).length}</strong></span>
            <span style={{ color: T.textSoft }}>Frozen: <strong>{articles.filter(a => a.frozen).length}</strong></span>
          </div>
        )}

        {/* ── List View ────────────────────────────────────────────────────── */}
        {viewMode === "list" && (
          <>
            {articles.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
                  style={{ padding: "5px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12 }}>
                  <option value="all">All Statuses</option>
                  <option value="pending">Pending</option>
                  <option value="draft">Draft</option>
                  <option value="approved">Approved</option>
                  <option value="published">Published</option>
                </select>
              </div>
            )}

            {isLoading ? (
              <div style={{ textAlign: "center", padding: 30 }}><Spinner /></div>
            ) : filtered.length === 0 ? (
              <div style={{ textAlign: "center", padding: 30, color: T.textSoft }}>
                {articles.length === 0
                  ? "No articles generated yet — pipeline may still be running."
                  : "No articles match the selected filter."}
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${T.border}`, textAlign: "left" }}>
                      <th style={{ padding: "6px 8px" }}>Keyword</th>
                      <th style={{ padding: "6px 8px" }}>Title</th>
                      <th style={{ padding: "6px 8px" }}>Words</th>
                      <th style={{ padding: "6px 8px" }}>Status</th>
                      <th style={{ padding: "6px 8px" }}>Scheduled</th>
                      <th style={{ padding: "6px 8px" }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(article => (
                      <tr key={article.article_id}
                        style={{ borderBottom: `1px solid ${T.grayLight}` }}>
                        <td style={{ padding: "6px 8px", fontWeight: 500, maxWidth: 160,
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {article.keyword}
                        </td>
                        <td style={{ padding: "6px 8px", maxWidth: 220,
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {article.title || <span style={{ color: T.textSoft }}>—</span>}
                        </td>
                        <td style={{ padding: "6px 8px", color: T.textSoft }}>
                          {article.word_count || "—"}
                        </td>
                        <td style={{ padding: "6px 8px" }}>
                          <span style={{
                            fontSize: 10, padding: "2px 6px", borderRadius: 4, fontWeight: 600,
                            background: statusBg[article.status] || T.grayLight,
                            color:      statusColor[article.status] || T.textSoft,
                          }}>
                            {article.status || "draft"}
                            {article.frozen ? " 🔒" : ""}
                          </span>
                        </td>
                        <td style={{ padding: "6px 8px" }}>
                          {schedulingId === article.article_id ? (
                            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                              <input type="date" value={scheduleDateInput}
                                onChange={e => setScheduleDateInput(e.target.value)}
                                style={{ fontSize: 11, padding: "2px 6px", border: `1px solid ${T.border}`, borderRadius: 4 }} />
                              <Btn small variant="teal"
                                onClick={() => doSchedule(article.article_id, scheduleDateInput)}
                                disabled={!scheduleDateInput}>
                                Set
                              </Btn>
                              <Btn small onClick={() => setSchedulingId(null)}>×</Btn>
                            </div>
                          ) : (
                            <span style={{ color: article.schedule_date ? T.text : T.textSoft }}>
                              {article.schedule_date || "—"}
                            </span>
                          )}
                        </td>
                        <td style={{ padding: "6px 8px" }}>
                          <div style={{ display: "flex", gap: 4 }}>
                            {article.status !== "approved" && article.status !== "published" && (
                              <Btn small variant="teal" onClick={() => doApprove(article.article_id)}>
                                Approve
                              </Btn>
                            )}
                            <Btn small onClick={() => doFreeze(article.article_id, article.frozen)}>
                              {article.frozen ? "Unfreeze" : "Freeze"}
                            </Btn>
                            {schedulingId !== article.article_id && (
                              <Btn small onClick={() => {
                                setSchedulingId(article.article_id)
                                setScheduleDateInput(article.schedule_date || "")
                              }}>
                                📅
                              </Btn>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {/* ── Calendar View ─────────────────────────────────────────────────── */}
        {viewMode === "calendar" && (
          <div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 14 }}>
              <input type="month" value={calendarMonth}
                onChange={e => setCalendarMonth(e.target.value)}
                style={{ padding: "5px 8px", borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 12 }} />
            </div>

            {!calendarData ? (
              <div style={{ textAlign: "center", padding: 20 }}><Spinner /></div>
            ) : Object.keys(calendarData.by_month || {}).length === 0 ? (
              <div style={{ textAlign: "center", padding: 20, color: T.textSoft }}>
                No scheduled articles for this period.
              </div>
            ) : (
              Object.entries(calendarData.by_month || {}).map(([ym, items]) => (
                <div key={ym} style={{ marginBottom: 18 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: T.purple, marginBottom: 6 }}>
                    {ym}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {items.map(item => (
                      <div key={item.article_id} style={{
                        display: "flex", gap: 10, alignItems: "center",
                        padding: "6px 10px", borderRadius: 6, fontSize: 12,
                        background: statusBg[item.status] || T.grayLight,
                      }}>
                        <span style={{ color: T.textSoft, minWidth: 70, fontSize: 11 }}>
                          {item.schedule_date?.slice(5) || "—"}
                        </span>
                        <span style={{ flex: 1, fontWeight: 500,
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {item.keyword}
                        </span>
                        {item.title && (
                          <span style={{ color: T.textSoft, fontSize: 11, maxWidth: 200,
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {item.title}
                          </span>
                        )}
                        <span style={{
                          fontSize: 10, padding: "1px 5px", borderRadius: 3, fontWeight: 600,
                          color: statusColor[item.status] || T.textSoft,
                        }}>
                          {item.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Complete session */}
        <div style={{ marginTop: 18, display: "flex", justifyContent: "flex-end" }}>
          <Btn variant="teal" onClick={onGoToCalendar}>
            Complete &amp; Go to Calendar →
          </Btn>
        </div>
      </Card>
    </div>
  )
}
