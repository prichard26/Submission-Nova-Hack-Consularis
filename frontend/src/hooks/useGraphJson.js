import { useEffect, useState } from 'react'
import { getGraphJson } from '../services/api'

export function useGraphJson(sessionId, processId = 'Process_Global', refreshTrigger = 0) {
  const [state, setState] = useState({ graph: null, loading: true, error: '' })

  useEffect(() => {
    if (!sessionId) return

    const controller = new AbortController()
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setState((prev) => ({ ...prev, loading: true, error: '' }))
      }
    })

    getGraphJson(sessionId, { processId, signal: controller.signal })
      .then((payload) => {
        setState({ graph: payload, loading: false, error: '' })
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
