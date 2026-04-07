import { useQuery } from "@tanstack/react-query"
import { api } from "../App"

/**
 * Adaptive article list polling.
 * Polls every 3s while any article is generating; stops otherwise.
 * Paused articles retain status "generating" so they continue at 3s (intentional).
 */
export function useArticlePolling(projectId) {
  return useQuery({
    queryKey: ["articles", projectId],
    queryFn: () =>
      projectId
        ? api.get(`/api/projects/${projectId}/content`).then(d => Array.isArray(d) ? d : [])
        : Promise.resolve([]),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const articles = query.state.data || []
      return articles.some(a => a.status === "generating") ? 3000 : false
    },
  })
}
