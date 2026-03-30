const API = import.meta.env.VITE_API_URL || "";

export async function enrichKeyword(keyword: string) {
  const res = await fetch(`${API}/api/enrich?keyword=${encodeURIComponent(keyword)}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      ...(localStorage.getItem("annaseo_token") ? { Authorization: `Bearer ${localStorage.getItem("annaseo_token")}` } : {}),
    },
  });
  if (!res.ok) {
    throw new Error(`Failed enrichment (${res.status})`);
  }
  return res.json();
}

export async function createStrategyJob(projectId: string, payload: any) {
  const res = await fetch(`${API}/api/strategy/${projectId}/jobs/create`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(localStorage.getItem("annaseo_token") ? { Authorization: `Bearer ${localStorage.getItem("annaseo_token")}` } : {}),
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to create job (${res.status})`);
  }
  return res.json();
}

export async function getJobStatus(projectId: string, jobId: string) {
  const res = await fetch(`${API}/api/strategy/${projectId}/jobs/${jobId}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      ...(localStorage.getItem("annaseo_token") ? { Authorization: `Bearer ${localStorage.getItem("annaseo_token")}` } : {}),
    },
  });
  if (!res.ok) {
    throw new Error(`Failed job fetch (${res.status})`);
  }
  return res.json();
}
