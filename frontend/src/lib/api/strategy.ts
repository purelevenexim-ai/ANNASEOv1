const API = import.meta.env.VITE_API_URL || "";
import fetchDebug from "../fetchDebug"

export async function enrichKeyword(keyword: string) {
  const { res, parsed } = await fetchDebug(`${API}/api/enrich?keyword=${encodeURIComponent(keyword)}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      ...(localStorage.getItem("annaseo_token") ? { Authorization: `Bearer ${localStorage.getItem("annaseo_token")}` } : {}),
    },
  })
  if (!res.ok) throw new Error(`Failed enrichment (${res.status})`)
  return parsed
}

export async function createStrategyJob(projectId: string, payload: any) {
  const { res, parsed } = await fetchDebug(`${API}/api/strategy/${projectId}/jobs/create`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(localStorage.getItem("annaseo_token") ? { Authorization: `Bearer ${localStorage.getItem("annaseo_token")}` } : {}),
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`Failed to create job (${res.status})`)
  return parsed
}

export async function getJobStatus(projectId: string, jobId: string) {
  const { res, parsed } = await fetchDebug(`${API}/api/strategy/${projectId}/jobs/${jobId}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      ...(localStorage.getItem("annaseo_token") ? { Authorization: `Bearer ${localStorage.getItem("annaseo_token")}` } : {}),
    },
  })
  if (!res.ok) throw new Error(`Failed job fetch (${res.status})`)
  return parsed
}
