import { useState, useCallback, useMemo } from 'react'
import AureliusChat from '../components/AureliusChat'
import BpmnViewer from '../components/BpmnViewer'
import './Dashboard.css'

const PROCESS_ID = 'Process_Global'

export default function Dashboard({ companyName, sector = 'pharmacy' }) {
  const [bpmnRefreshTrigger, setBpmnRefreshTrigger] = useState(0)
  const [chatOpen, setChatOpen] = useState(false)
  const sectorLabel = useMemo(
    () => `${sector.charAt(0).toUpperCase()}${sector.slice(1)}`,
    [sector],
  )

  const handleExternalGraphUpdate = useCallback(() => {
    setBpmnRefreshTrigger((t) => t + 1)
  }, [])

  const panelFooter = useMemo(
    () => (
      <AureliusChat
        sessionId={companyName}
        processId={PROCESS_ID}
        onGraphUpdate={handleExternalGraphUpdate}
        onClose={() => setChatOpen(false)}
      />
    ),
    [companyName, handleExternalGraphUpdate],
  )

  return (
    <div className="dashboard">
      {/* ── Top bar ── */}
      <header className="dashboard__topbar">
        <div className="dashboard__topbar-left">
          <span className="dashboard__logo">
            Consularis<span className="dashboard__logo-dot">.</span>
          </span>
          <span className="dashboard__company">{companyName}</span>
          <span className="dashboard__badge">{sectorLabel}</span>
        </div>

        <button
          className={`dashboard__chat-toggle ${chatOpen ? 'dashboard__chat-toggle--active' : ''}`}
          onClick={() => setChatOpen(o => !o)}
        >
          <span>🤖</span> Aurelius
        </button>
      </header>

      {/* ── Main canvas: BPMN ── */}
      <div className="dashboard__canvas">
        <BpmnViewer
          sessionId={companyName}
          processId={PROCESS_ID}
          refreshTrigger={bpmnRefreshTrigger}
          panelFooter={panelFooter}
          onRequestRefresh={handleExternalGraphUpdate}
        />
      </div>

      {/* ── Aurelius chat overlay ── */}
      {chatOpen && (
        <AureliusChat
          sessionId={companyName}
          processId={PROCESS_ID}
          onGraphUpdate={handleExternalGraphUpdate}
          onClose={() => setChatOpen(false)}
          isOverlay
        />
      )}
    </div>
  )
}
