import { useState, useCallback, useMemo, useEffect } from 'react'
import AureliusChat, { WELCOME_MSG } from '../components/AureliusChat'
import ProcessCanvas from '../components/ProcessCanvas'
import ProcessBreadcrumb from '../components/ProcessBreadcrumb'
import DetailPanel from '../components/DetailPanel'
import LandscapeView from '../components/LandscapeView'
import { useWorkspace } from '../hooks/useWorkspace'
import { sendChat } from '../services/api'
import './Dashboard.css'

const DEFAULT_PROCESS_ID = 'Process_Global'

export default function Dashboard({ companyName, sector = 'pharmacy' }) {
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [activeProcessId, setActiveProcessId] = useState(DEFAULT_PROCESS_ID)
  const [selectedStep, setSelectedStep] = useState(null)
  const [viewMode, setViewMode] = useState('detail')
  const [chatMessages, setChatMessages] = useState([
    { id: 1, role: 'assistant', text: WELCOME_MSG }
  ])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)

  const { workspace } = useWorkspace(companyName, refreshTrigger)

  const sectorLabel = `${sector.charAt(0).toUpperCase()}${sector.slice(1)}`

  const workspaceProcesses = useMemo(() => {
    return workspace?.process_tree?.processes || {}
  }, [workspace])

  const handleExternalGraphUpdate = useCallback(() => {
    setRefreshTrigger((t) => t + 1)
  }, [])

  const navigateToProcess = useCallback((processId) => {
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

  const handleChatSend = useCallback(
    async (userText) => {
      setChatInput('')
      setChatMessages((prev) => [...prev, { id: Date.now(), role: 'user', text: userText }])
      setChatLoading(true)
      try {
        const data = await sendChat(companyName, userText, { processId: activeProcessId })
        const reply = data.message || 'I could not process that. Please try again.'
        setChatMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', text: reply }])
        if (data.graph_json) handleExternalGraphUpdate()
      } catch (err) {
        const text = err.status ? `Request failed (${err.status}). Please try again.` : 'The consul is temporarily unavailable. Please ensure the backend is running (e.g. ./run.sh) and try again.'
        setChatMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', text }])
      } finally {
        setChatLoading(false)
      }
    },
    [companyName, activeProcessId, handleExternalGraphUpdate],
  )

  const panelFooter = (
    <AureliusChat
      sessionId={companyName}
      processId={activeProcessId}
      onGraphUpdate={handleExternalGraphUpdate}
      messages={chatMessages}
      onSend={handleChatSend}
      input={chatInput}
      onInputChange={setChatInput}
      loading={chatLoading}
    />
  )

  useEffect(() => {
    function onKeyDown(e) {
      if (e.key !== 'Escape') return
      if (selectedStep) {
        setSelectedStep(null)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedStep])

  return (
    <div className="dashboard">
      <header className="dashboard__topbar">
        <div className="dashboard__topbar-left">
          <span className="dashboard__logo">
            <svg
              className="dashboard__logo-icon"
              viewBox="0 0 24 24"
              width="16"
              height="16"
              aria-hidden="true"
            >
              <rect x="2" y="3" width="5" height="18" rx="1.5" />
              <rect x="9.5" y="3" width="5" height="18" rx="1.5" />
              <rect x="17" y="3" width="5" height="18" rx="1.5" />
            </svg>
            Consularis.ai
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
        </div>
      </header>

      {viewMode === 'detail' && (
        <ProcessBreadcrumb
          workspaceProcesses={workspaceProcesses}
          activeProcessId={activeProcessId}
          onNavigate={navigateToProcess}
        />
      )}

      <div className="dashboard__canvas">
        {viewMode === 'landscape' ? (
          <LandscapeView
            sessionId={companyName}
            workspace={workspace}
            onProcessSelect={navigateToProcess}
          />
        ) : (
          <ProcessCanvas
            sessionId={companyName}
            processId={activeProcessId}
            refreshTrigger={refreshTrigger}
            onStepSelect={handleStepSelect}
            onDrillDown={navigateToProcess}
            onRequestRefresh={handleExternalGraphUpdate}
            panelFooter={panelFooter}
            workspaceProcesses={workspaceProcesses}
          />
        )}
      </div>

      {selectedStep && (
        <>
          <div className="dashboard__backdrop" onClick={handleCloseDetail} aria-hidden />
          <DetailPanel
            step={selectedStep}
            sessionId={companyName}
            processId={activeProcessId}
            onClose={handleCloseDetail}
            onUpdate={handleStepUpdate}
          />
        </>
      )}
    </div>
  )
}
