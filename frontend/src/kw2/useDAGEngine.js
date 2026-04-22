/**
 * useDAGEngine — React hook for the KW2 DAG phase engine.
 *
 * Fetches DAG topology from the backend, tracks phase statuses,
 * exposes runPhase / approveGate actions, and computes which phases
 * are currently runnable.
 */
import { useState, useEffect, useCallback, useMemo } from "react"
import * as api from "./api"
import useKw2Store from "./store"

export default function useDAGEngine() {
  const { projectId, sessionId, mode } = useKw2Store()
  const pushLog = useKw2Store((s) => s.pushLog)
  const addToast = useKw2Store((s) => s.addToast)

  const [dag, setDag] = useState(null)          // full DAG state from backend
  const [statuses, setStatuses] = useState({})   // phase_id → status
  const [running, setRunning] = useState(null)   // phase currently running
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // ── Fetch DAG state ──────────────────────────────────────────────────

  const fetchDag = useCallback(async () => {
    if (!projectId || !sessionId) return
    setLoading(true)
    try {
      const data = await api.getDagState(projectId, sessionId)
      setDag(data)
      setStatuses(data.statuses || {})
      setError(null)
    } catch (err) {
      setError(err.message || "Failed to load DAG")
      pushLog?.(`[DAG] Load error: ${err.message}`, { badge: "DAG", type: "error" })
    } finally {
      setLoading(false)
    }
  }, [projectId, sessionId, pushLog])

  useEffect(() => {
    fetchDag()
  }, [fetchDag])

  // ── Runnable phases ──────────────────────────────────────────────────

  const runnablePhases = useMemo(() => {
    if (!dag?.phases) return []
    return dag.phases.filter((p) => {
      if (statuses[p.id] === "done" || statuses[p.id] === "running") return false
      // Check all deps are done
      const deps = p.dependencies || []
      return deps.every((d) => statuses[d] === "done")
    }).map((p) => p.id)
  }, [dag, statuses])

  // ── Run a single phase ───────────────────────────────────────────────

  const runPhase = useCallback(async (phaseId) => {
    if (!projectId || !sessionId) return
    setRunning(phaseId)
    setStatuses((prev) => ({ ...prev, [phaseId]: "running" }))
    pushLog?.(`[DAG] Running phase: ${phaseId}`, { badge: "DAG" })

    try {
      const result = await api.runDagPhase(projectId, sessionId, phaseId)
      if (result.status === "waiting") {
        setStatuses((prev) => ({ ...prev, [phaseId]: "waiting" }))
        addToast?.(`${phaseId} waiting for approval`, "info")
      } else {
        setStatuses((prev) => ({ ...prev, [phaseId]: "done" }))
        addToast?.(`${phaseId} completed`, "success")
      }
      pushLog?.(`[DAG] Phase ${phaseId}: ${result.status}`, { badge: "DAG" })
      return result
    } catch (err) {
      setStatuses((prev) => ({ ...prev, [phaseId]: "failed" }))
      pushLog?.(`[DAG] Phase ${phaseId} failed: ${err.message}`, { badge: "DAG", type: "error" })
      addToast?.(`${phaseId} failed: ${err.message}`, "error")
      throw err
    } finally {
      setRunning(null)
    }
  }, [projectId, sessionId, pushLog, addToast])

  // ── Approve a human gate ─────────────────────────────────────────────

  const approveGate = useCallback(async (phaseId, data = {}) => {
    if (!projectId || !sessionId) return
    try {
      const result = await api.approveDagGate(projectId, sessionId, phaseId, data)
      setStatuses((prev) => ({ ...prev, [phaseId]: "done" }))
      pushLog?.(`[DAG] Gate ${phaseId} approved`, { badge: "DAG" })
      addToast?.(`${phaseId} approved`, "success")
      return result
    } catch (err) {
      pushLog?.(`[DAG] Gate ${phaseId} approval failed: ${err.message}`, { badge: "DAG", type: "error" })
      throw err
    }
  }, [projectId, sessionId, pushLog, addToast])

  // ── Refresh helper ───────────────────────────────────────────────────

  const refresh = useCallback(() => fetchDag(), [fetchDag])

  return {
    dag,
    statuses,
    running,
    loading,
    error,
    runnablePhases,
    runPhase,
    approveGate,
    refresh,
  }
}
