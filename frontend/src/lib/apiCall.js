import fetchDebug from "./fetchDebug"

const API = import.meta.env.VITE_API_URL || ""
const RETRYABLE_GET_STATUSES = new Set([502, 503, 504])
const RETRY_DELAYS_MS = [500, 1200]

export { API }

function delay(ms, signal = null) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      cleanup()
      resolve()
    }, ms)

    const onAbort = () => {
      cleanup()
      reject(new DOMException("Aborted", "AbortError"))
    }

    const cleanup = () => {
      clearTimeout(timer)
      signal?.removeEventListener?.("abort", onAbort)
    }

    if (signal?.aborted) {
      cleanup()
      reject(new DOMException("Aborted", "AbortError"))
      return
    }

    signal?.addEventListener?.("abort", onAbort, { once: true })
  })
}

function normalizeApiError(method, path, status, data) {
  const raw = data?.detail || data?.error || `API ${method} ${path} failed (${status})`
  const rawText = typeof raw === "string" ? raw.trim() : ""
  const looksLikeHtml = /<html|<head|<body|<title>/i.test(rawText)

  if (looksLikeHtml || RETRYABLE_GET_STATUSES.has(status)) {
    return `Service temporarily unavailable (${status}). Please retry.`
  }

  return rawText || `API ${method} ${path} failed (${status})`
}

export default async function apiCall(path, method = "GET", body = null, signal = null) {
  const token = localStorage.getItem("annaseo_token")
  const url = `${API}${path}`
  const isRetryableGet = method === "GET"

  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      const { res, parsed: data } = await fetchDebug(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
        ...(signal ? { signal } : {}),
      })

      if (!res.ok) {
        const retryableStatus = isRetryableGet && RETRYABLE_GET_STATUSES.has(res.status)
        if (retryableStatus && attempt < RETRY_DELAYS_MS.length) {
          if (typeof window._kw2pushLog === "function") {
            window._kw2pushLog(
              `[API ${res.status}] ${method} ${path} → retry ${attempt + 1}/${RETRY_DELAYS_MS.length}`,
              { badge: "API", type: "warn" },
            )
          }
          await delay(RETRY_DELAYS_MS[attempt], signal)
          continue
        }

        const msg = normalizeApiError(method, path, res.status, data)
        if (typeof window._kw2pushLog === "function") {
          window._kw2pushLog(`[API ${res.status}] ${method} ${path} → ${msg}`, { badge: "API", type: "error" })
        }
        throw new Error(msg)
      }

      return data
    } catch (e) {
      const retryableNetworkError = isRetryableGet && e?.name === "TypeError" && attempt < RETRY_DELAYS_MS.length
      if (retryableNetworkError && !signal?.aborted) {
        if (typeof window._kw2pushLog === "function") {
          window._kw2pushLog(
            `[NETWORK] ${method} ${path} → retry ${attempt + 1}/${RETRY_DELAYS_MS.length}: ${e.message}`,
            { badge: "NET", type: "warn" },
          )
        }
        await delay(RETRY_DELAYS_MS[attempt], signal)
        continue
      }

      if (e.name === "TypeError" && typeof window._kw2pushLog === "function") {
        window._kw2pushLog(`[NETWORK] ${method} ${path} → ${e.message}`, { badge: "NET", type: "error" })
      }
      throw e
    }
  }
}
