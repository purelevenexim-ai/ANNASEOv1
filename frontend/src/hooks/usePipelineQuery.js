import { useQuery } from "@tanstack/react-query"
import { api } from "../App"

/**
 * Shared pipeline polling hook.
 * All consumers (PipelinePanel, compact list item, PipelineLogsView) share
 * one in-flight request via React Query's key deduplication.
 *
 * Polling schedule:
 *   - not generating: off
 *   - generating + paused: every 5s
 *   - generating + running: every 2s
 */
export function usePipelineQuery(articleId) {
  return useQuery({
    queryKey: ["pipeline", articleId],
    queryFn: () => api.get(`/api/content/${articleId}/pipeline`),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!articleId || !data || data.status !== "generating") return false
      return data.is_paused ? 5000 : 2000
    },
    enabled: !!articleId,
    staleTime: 0,
  })
}
