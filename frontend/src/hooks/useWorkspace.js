import { useEffect, useState } from 'react'
import { getWorkspace } from '../services/api'

export function useWorkspace(sessionId, refreshTrigger = 0) {
  const [state, setState] = useState({ workspace: null, loading: false, error: null })

  useEffect(() => {
    if (!sessionId) return

    const controller = new AbortController()
    setState((prev) => ({ ...prev, loading: true, error: null }))

    getWorkspace(sessionId, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return
        setState({ workspace: data, loading: false, error: null })
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return
        setState({ workspace: null, loading: false, error: err?.message || 'Failed to fetch workspace' })
      })

    return () => controller.abort()
  }, [sessionId, refreshTrigger])

  if (!sessionId) {
    return { workspace: null, loading: false, error: 'No session' }
  }
  return state
}
