import { createContext } from 'react'

export const ProcessCanvasContext = createContext({
  sessionId: null,
  processId: null,
  onRequestRefresh: null,
})
