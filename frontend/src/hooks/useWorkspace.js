import { useMemo } from 'react'
import { getWorkspace } from '../services/api'
import { useFetchResource } from './useFetchResource'

export function useWorkspace(sessionId, refreshTrigger = 0) {
  const fetcher = useMemo(() => {
    if (!sessionId) return null
    return (signal) => getWorkspace(sessionId, { signal })
  }, [sessionId])

  const state = useFetchResource(fetcher, [fetcher, refreshTrigger], {
    dataKey: 'workspace',
    errorMessage: 'Failed to fetch workspace',
  })

  if (!sessionId) {
    return { workspace: null, loading: false, error: 'No session' }
  }
  return state
}
