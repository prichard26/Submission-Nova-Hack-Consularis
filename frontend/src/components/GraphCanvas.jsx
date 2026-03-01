import BpmnViewer from './BpmnViewer'
import ProcessGraphViewer from './ProcessGraphViewer'

/**
 * Unified graph viewer switcher.
 * Both viewer modes share the same session and refresh contract.
 * onGraphUpdate: when BPMN is edited in the modeler, pass updated XML (e.g. to keep state in sync).
 */
export default function GraphCanvas({
  viewMode,
  sessionId,
  refreshTrigger = 0,
  xmlOverride = '',
  onGraphUpdate,
  panelFooter,
}) {
  if (viewMode === 'bpmn') {
    return (
      <BpmnViewer
        sessionId={sessionId}
        refreshTrigger={refreshTrigger}
        xmlOverride={xmlOverride}
        onXmlChange={onGraphUpdate}
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
