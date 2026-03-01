import { useState, useCallback, useRef } from 'react'
import AureliusChat from '../components/AureliusChat'
import GraphCanvas from '../components/GraphCanvas'
import './Dashboard.css'

export default function Dashboard({ companyName }) {
  const [bpmnRefreshTrigger, setBpmnRefreshTrigger] = useState(0)
  const [chatOpen, setChatOpen] = useState(false)
  const [latestBpmnXml, setLatestBpmnXml] = useState('')
  const [graphViewMode, setGraphViewMode] = useState('custom')
  const latestEditorXmlRef = useRef('')

  const handleExternalGraphUpdate = useCallback((newBpmnXml) => {
    if (typeof newBpmnXml === 'string' && newBpmnXml.trim()) {
      setLatestBpmnXml(newBpmnXml)
    }
    setBpmnRefreshTrigger((t) => t + 1)
  }, [])

  const handleEditorXmlChange = useCallback((newBpmnXml) => {
    // Keep a local copy without triggering viewer re-import on every edit.
    if (typeof newBpmnXml === 'string' && newBpmnXml.trim()) {
      latestEditorXmlRef.current = newBpmnXml
    }
  }, [])

  return (
    <div className="dashboard">
      {/* ── Top bar ── */}
      <header className="dashboard__topbar">
        <div className="dashboard__topbar-left">
          <span className="dashboard__logo">
            Consularis<span className="dashboard__logo-dot">.</span>
          </span>
          <span className="dashboard__company">{companyName}</span>
          <span className="dashboard__badge">Pharmacy</span>
          <div className="dashboard__view-toggle" role="tablist" aria-label="Graph view mode">
            <button
              className={`view-toggle-btn ${graphViewMode === 'custom' ? 'view-toggle-btn--active' : ''}`}
              onClick={() => setGraphViewMode('custom')}
              role="tab"
              aria-selected={graphViewMode === 'custom'}
            >
              Process
            </button>
            <button
              className={`view-toggle-btn ${graphViewMode === 'bpmn' ? 'view-toggle-btn--active' : ''}`}
              onClick={() => setGraphViewMode('bpmn')}
              role="tab"
              aria-selected={graphViewMode === 'bpmn'}
            >
              BPMN
            </button>
          </div>
        </div>

        <button
          className={`dashboard__chat-toggle ${chatOpen ? 'dashboard__chat-toggle--active' : ''}`}
          onClick={() => setChatOpen(o => !o)}
        >
          <span>🤖</span> Aurelius
        </button>
      </header>

      {/* ── Main canvas ── */}
      <div className="dashboard__canvas">
        <GraphCanvas
          viewMode={graphViewMode}
          sessionId={companyName}
          refreshTrigger={bpmnRefreshTrigger}
          xmlOverride={latestBpmnXml}
          onGraphUpdate={handleEditorXmlChange}
          panelFooter={
            graphViewMode === 'bpmn' ? (
              <AureliusChat
                sessionId={companyName}
                onGraphUpdate={handleExternalGraphUpdate}
                onClose={() => setChatOpen(false)}
              />
            ) : null
          }
        />
      </div>

      {/* ── Aurelius chat panel (overlay when not in BPMN view) ── */}
      {chatOpen && graphViewMode !== 'bpmn' && (
        <AureliusChat
          sessionId={companyName}
          onGraphUpdate={handleExternalGraphUpdate}
          onClose={() => setChatOpen(false)}
        />
      )}
    </div>
  )
}
