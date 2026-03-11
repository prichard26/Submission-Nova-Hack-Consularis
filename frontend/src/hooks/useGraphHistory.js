import { useCallback, useRef, useState } from 'react'

const MAX_HISTORY = 30

/**
 * Client-side undo/redo for graph snapshots.
 * Stores raw graph JSON objects (the API response format) so undo/redo is instant
 * without a backend round-trip.
 */
export function useGraphHistory() {
  const pastRef = useRef([])
  const futureRef = useRef([])
  const [revision, setRevision] = useState(0)

  const pushState = useCallback((graphSnapshot) => {
    if (!graphSnapshot) return
    pastRef.current = [...pastRef.current.slice(-(MAX_HISTORY - 1)), graphSnapshot]
    futureRef.current = []
    setRevision((r) => r + 1)
  }, [])

  const undo = useCallback((currentGraph) => {
    if (pastRef.current.length === 0 || !currentGraph) return null
    const previous = pastRef.current[pastRef.current.length - 1]
    pastRef.current = pastRef.current.slice(0, -1)
    futureRef.current = [...futureRef.current, currentGraph]
    setRevision((r) => r + 1)
    return previous
  }, [])

  const redo = useCallback((currentGraph) => {
    if (futureRef.current.length === 0 || !currentGraph) return null
    const next = futureRef.current[futureRef.current.length - 1]
    futureRef.current = futureRef.current.slice(0, -1)
    pastRef.current = [...pastRef.current, currentGraph]
    setRevision((r) => r + 1)
    return next
  }, [])

  const clear = useCallback(() => {
    pastRef.current = []
    futureRef.current = []
    setRevision((r) => r + 1)
  }, [])

  return {
    pushState,
    undo,
    redo,
    clear,
    canUndo: pastRef.current.length > 0,
    canRedo: futureRef.current.length > 0,
  }
}
