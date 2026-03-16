/**
 * React context for process canvas: sessionId, processId, onRequestRefresh (used by nodes to trigger graph refetch).
 */
import { createContext } from 'react'

export const ProcessCanvasContext = createContext({
  sessionId: null,
  processId: null,
  onRequestRefresh: null,
})
