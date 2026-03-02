import { useState, useCallback, useMemo } from 'react'
import AureliusChat from '../components/AureliusChat'
import ProcessCanvas from '../components/ProcessCanvas'
import ProcessBreadcrumb from '../components/ProcessBreadcrumb'
import DetailPanel from '../components/DetailPanel'
import LandscapeView from '../components/LandscapeView'
import { useWorkspace } from '../hooks/useWorkspace'
import './Dashboard.css'

const DEFAULT_PROCESS_ID = 'Process_Global'

export default function Dashboard({ companyName, sector = 'pharmacy' }) {
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [chatOpen, setChatOpen] = useState(false)
  const [activeProcessId, setActiveProcessId] = useState(DEFAULT_PROCESS_ID)
  const [selectedStep, setSelectedStep] = useState(null)
  const [viewMode, setViewMode] = useState('detail')

  const { workspace } = useWorkspace(companyName)

  const sectorLabel = useMemo(
    () => `${sector.charAt(0).toUpperCase()}${sector.slice(1)}`,
    [sector],
  )

  const workspaceProcesses = useMemo(() => {
    return workspace?.process_tree?.processes || {}
  }, [workspace])

  const handleExternalGraphUpdate = useCallback(() => {
    setRefreshTrigger((t) => t + 1)
  }, [])

  const handleDrillDown = useCallback((processId) => {
    setActiveProcessId(processId)
    setSelectedStep(null)
  }, [])

  const handleBreadcrumbNav = useCallback((processId) => {
    setActiveProcessId(processId)
    setSelectedStep(null)
  }, [])

  const handleStepSelect = useCallback((step) => {
    setSelectedStep(step)
  }, [])

  const handleCloseDetail = useCallback(() => {
    setSelectedStep(null)
  }, [])

  const handleStepUpdate = useCallback(() => {
    setRefreshTrigger((t) => t + 1)
  }, [])

  const panelFooter = useMemo(
    () => (
      <AureliusChat
        sessionId={companyName}
        processId={activeProcessId}
        onGraphUpdate={handleExternalGraphUpdate}
        onClose={() => setChatOpen(false)}
      />
    ),
    [companyName, activeProcessId, handleExternalGraphUpdate],
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

        <div className="dashboard__topbar-right">
          <button
            className={`dashboard__view-toggle ${viewMode === 'landscape' ? 'dashboard__view-toggle--active' : ''}`}
            onClick={() => setViewMode(viewMode === 'landscape' ? 'detail' : 'landscape')}
          >
            {viewMode === 'landscape' ? 'Process View' : 'Landscape'}
          </button>
          <button
            className={`dashboard__chat-toggle ${chatOpen ? 'dashboard__chat-toggle--active' : ''}`}
            onClick={() => setChatOpen(o => !o)}
          >
            <span>🤖</span> Aurelius
          </button>
        </div>
      </header>

      {/* ── Breadcrumb ── */}
      {viewMode === 'detail' && (
        <ProcessBreadcrumb
          workspaceProcesses={workspaceProcesses}
          activeProcessId={activeProcessId}
          onNavigate={handleBreadcrumbNav}
        />
      )}

      {/* ── Main content ── */}
      <div className="dashboard__canvas">
        {viewMode === 'landscape' ? (
          <LandscapeView
            sessionId={companyName}
            workspace={workspace}
            onProcessSelect={handleDrillDown}
          />
        ) : (
          <ProcessCanvas
            sessionId={companyName}
            processId={activeProcessId}
            refreshTrigger={refreshTrigger}
            onStepSelect={handleStepSelect}
            onDrillDown={handleDrillDown}
            onRequestRefresh={handleExternalGraphUpdate}
            panelFooter={panelFooter}
            workspaceProcesses={workspaceProcesses}
          />
        )}
      </div>

      {/* ── Detail Panel slide-in ── */}
      {selectedStep && (
        <DetailPanel
          step={selectedStep}
          sessionId={companyName}
          processId={activeProcessId}
          onClose={handleCloseDetail}
          onUpdate={handleStepUpdate}
        />
      )}

      {/* ── Aurelius chat overlay ── */}
      {chatOpen && (
        <AureliusChat
          sessionId={companyName}
          processId={activeProcessId}
          onGraphUpdate={handleExternalGraphUpdate}
          onClose={() => setChatOpen(false)}
          isOverlay
        />
      )}
    </div>
  )
}
