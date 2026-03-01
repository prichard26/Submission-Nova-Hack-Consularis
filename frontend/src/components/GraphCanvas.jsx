import { memo } from 'react'
import BpmnViewer from './BpmnViewer'
import ProcessGraphViewer from './ProcessGraphViewer'

/**
 * Unified graph viewer switcher.
 * Both viewer modes share the same session and refresh contract.
 */
function GraphCanvas({
  viewMode,
  sessionId,
  refreshTrigger = 0,
  xmlOverride = '',
  panelFooter,
}) {
  if (viewMode === 'bpmn') {
    return (
      <BpmnViewer
        sessionId={sessionId}
        refreshTrigger={refreshTrigger}
        xmlOverride={xmlOverride}
        panelFooter={panelFooter}
      />
    )
  }

  return (
    <ProcessGraphViewer
      sessionId={sessionId}
      refreshTrigger={refreshTrigger}
    />
  )
}

export default memo(GraphCanvas)
