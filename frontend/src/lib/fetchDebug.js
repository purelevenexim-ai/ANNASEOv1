import useDebug from "../store/debug"

export default async function fetchDebug(url, options = {}) {
  const start = Date.now()
  try {
    const res = await fetch(url, options)
    const duration = Date.now() - start
    const text = await res.text()
    let parsed
    try { parsed = text ? JSON.parse(text) : {} } catch { parsed = { error: text } }

    try {
      const dbg = useDebug.getState()
      if (dbg && dbg.enabled) dbg.pushLog({ id: `fd_${Date.now()}`, ts: start, path: url, method: options.method || 'GET', duration, status: res.status, ok: res.ok, reqBody: options.body ? String(options.body).slice(0,1000) : null, resSnippet: JSON.stringify(parsed).slice(0,400) })
    } catch (e) { /* ignore debug errors */ }

    return { res, parsed }
  } catch (e) {
    const duration = Date.now() - start
    try { const dbg = useDebug.getState(); if (dbg && dbg.enabled) dbg.pushLog({ id: `fd_err_${Date.now()}`, ts: start, path: url, method: options.method || 'GET', duration, ok: false, error: e?.message || String(e) }) } catch (ee) {}
    throw e
  }
}
