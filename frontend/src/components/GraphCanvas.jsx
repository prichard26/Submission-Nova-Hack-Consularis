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
  processId = 'Process_Global',
  refreshTrigger = 0,
  xmlOverride = '',
  panelFooter,
  onDrillDown,
}) {
  if (viewMode === 'bpmn') {
    return (
      <BpmnViewer
        sessionId={sessionId}
        processId={processId}
        refreshTrigger={refreshTrigger}
        xmlOverride={xmlOverride}
        panelFooter={panelFooter}
        onDrillDown={onDrillDown}
      />
    )
  }

  return (
    <ProcessGraphViewer
      sessionId={sessionId}
      processId={processId}
      refreshTrigger={refreshTrigger}
    />
  )
}

export default memo(GraphCanvas)
