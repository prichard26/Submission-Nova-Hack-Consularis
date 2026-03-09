import { useEffect, useState } from 'react'

/**
 * Generic hook for fetching a resource with abort, loading, and error state.
 * @param {Function} fetcher - Called with (signal) => Promise<data>. Return null to skip.
 * @param {Array} deps - Dependency array for re-fetching.
 * @param {object} opts
 * @param {string} opts.dataKey - Key name for the data in the returned state (default: 'data').
 * @param {string} opts.errorMessage - Fallback error message.
 */
export function useFetchResource(fetcher, deps, { dataKey = 'data', errorMessage = 'Failed to fetch' } = {}) {
  const [state, setState] = useState({ [dataKey]: null, loading: false, error: null })

  useEffect(() => {
    if (!fetcher) return

    const controller = new AbortController()
    setState((prev) => ({ ...prev, loading: true, error: null }))

    fetcher(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setState({ [dataKey]: data ?? null, loading: false, error: data ? null : 'Empty response' })
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return
        setState({ [dataKey]: null, loading: false, error: err?.message || errorMessage })
      })

    return () => controller.abort()
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps

  return state
}
