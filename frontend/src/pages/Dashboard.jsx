import { useState, useCallback, useMemo, useEffect } from 'react'
import AureliusChat, { WELCOME_MSG } from '../components/AureliusChat'
import ProcessCanvas from '../components/ProcessCanvas'
import DetailPanel from '../components/DetailPanel'
import LandscapeView from '../components/LandscapeView'
import { useWorkspace } from '../hooks/useWorkspace'
import { sendChat } from '../services/api'
import './Dashboard.css'

const DEFAULT_PROCESS_ID = 'Process_Global'

export default function Dashboard({ companyName }) {
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
      compact
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
        <span className="dashboard__logo">
          <img className="dashboard__logo-icon" src="/logo.png" alt="Consularis" width="24" height="24" />
          Consularis.ai
        </span>
      </header>

      <div className="dashboard__canvas">
        {viewMode === 'landscape' ? (
          <LandscapeView
            sessionId={companyName}
            workspace={workspace}
            onProcessSelect={(pid) => { navigateToProcess(pid); setViewMode('detail') }}
            onSwitchView={() => setViewMode('detail')}
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
            viewMode={viewMode}
            onViewModeChange={setViewMode}
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
