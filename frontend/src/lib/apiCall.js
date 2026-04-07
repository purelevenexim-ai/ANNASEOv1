import fetchDebug from "./fetchDebug"

const API = import.meta.env.VITE_API_URL || ""

export { API }

export default async function apiCall(path, method = "GET", body = null) {
  const token = localStorage.getItem("annaseo_token")
  const url = `${API}${path}`
  try {
    const { res, parsed: data } = await fetchDebug(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
    if (!res.ok) {
      const msg = data?.detail || data?.error || `API ${method} ${path} failed (${res.status})`
      // Push to kw2 debug console if available
      if (typeof window._kw2pushLog === "function") {
        window._kw2pushLog(`[API ${res.status}] ${method} ${path} → ${msg}`, { badge: "API", type: "error" })
      }
      throw new Error(msg)
    }
    return data
  } catch (e) {
    // Network-level errors (no response)
    if (e.name === "TypeError" && typeof window._kw2pushLog === "function") {
      window._kw2pushLog(`[NETWORK] ${method} ${path} → ${e.message}`, { badge: "NET", type: "error" })
    }
    throw e
  }
}
