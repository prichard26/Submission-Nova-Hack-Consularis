/**
 * useProcessGraph: fetch session graph JSON for a given sessionId and processId.
 * Uses useFetchResource; on error for a non-global process falls back to baseline. refreshTrigger forces refetch.
 */
import { useMemo } from 'react'
import { getGraphJson, getBaselineJson } from '../services/api'
import { useFetchResource } from './useFetchResource'

export function useProcessGraph(sessionId, processId = 'global', refreshTrigger = 0) {
  const fetcher = useMemo(() => {
    if (!sessionId) return null
    return (signal) =>
      getGraphJson(sessionId, { processId, signal })
        .catch((err) => {
          if (err?.name === 'AbortError') throw err
          if (processId && processId !== 'global') throw err
          return getBaselineJson({ processId, signal })
        })
  }, [sessionId, processId])

  const state = useFetchResource(fetcher, [fetcher, refreshTrigger], {
    dataKey: 'graph',
    errorMessage: 'Failed to fetch graph',
  })

  if (!sessionId) {
    return { graph: null, loading: false, error: 'No session' }
  }

  return state
}
