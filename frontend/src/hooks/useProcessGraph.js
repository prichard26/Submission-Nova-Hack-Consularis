import { useEffect, useState } from 'react'
import { getGraphJson, getBaselineJson } from '../services/api'

export function useProcessGraph(sessionId, processId = 'Process_Global', refreshTrigger = 0) {
  const [state, setState] = useState({ graph: null, loading: true, error: null })

  useEffect(() => {
    if (!sessionId) return

    const controller = new AbortController()
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setState((prev) => ({ ...prev, loading: true, error: null }))
      }
    })

    getGraphJson(sessionId, { processId, signal: controller.signal })
      .catch((err) => {
        if (err?.name === 'AbortError') throw err
        return getBaselineJson({ processId, signal: controller.signal })
      })
      .then((data) => {
        if (controller.signal.aborted) return
        if (!data) {
          setState({ graph: null, loading: false, error: 'Empty graph' })
          return
        }
        setState({ graph: data, loading: false, error: null })
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return
        setState({ graph: null, loading: false, error: err?.message || 'Failed to fetch graph' })
      })

    return () => {
      controller.abort()
    }
  }, [sessionId, processId, refreshTrigger])

  if (!sessionId) {
    return { graph: null, loading: false, error: 'No session' }
  }

  return state
}
