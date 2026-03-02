import { useEffect, useState } from 'react'
import { getBaselineBpmnXml, getBpmnXml } from '../services/api'

export function useBpmnXml(sessionId, processId = 'Process_Global', refreshTrigger = 0) {
  const [state, setState] = useState({ xml: '', loading: true, error: null })

  useEffect(() => {
    if (!sessionId) return

    const controller = new AbortController()
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setState((prev) => ({ ...prev, loading: true, error: null }))
      }
    })

    getBpmnXml(sessionId, { processId, signal: controller.signal })
      .catch((err) => {
        if (err?.name === 'AbortError') throw err
        return getBaselineBpmnXml({ processId, signal: controller.signal })
      })
      .then((nextXml) => {
        if (controller.signal.aborted) return
        if (!nextXml?.trim()) {
          setState({ xml: '', loading: false, error: 'Empty BPMN XML' })
          return
        }
        setState({ xml: nextXml, loading: false, error: null })
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return
        setState({ xml: '', loading: false, error: err?.message || 'Failed to fetch BPMN' })
      })

    return () => {
      controller.abort()
    }
  }, [sessionId, processId, refreshTrigger])

  if (!sessionId) {
    return { xml: '', loading: false, error: 'No session' }
  }

  return state
}
