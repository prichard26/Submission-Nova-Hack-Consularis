import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import AureliusChat from '../components/AureliusChat'
import ProcessCanvas from '../components/ProcessCanvas'
import LandscapeView from '../components/LandscapeView'
import DashboardTutorial, { getTutorialDone } from '../components/DashboardTutorial'
import { useWorkspace } from '../hooks/useWorkspace'
import { useChat } from '../hooks/useChat'
import './Dashboard.css'

const DEFAULT_PROCESS_ID = 'global'

export default function Dashboard({ companyName }) {
  const navigate = useNavigate()
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [activeProcessId, setActiveProcessId] = useState(DEFAULT_PROCESS_ID)
  const [selectedStep, setSelectedStep] = useState(null)
  const [viewMode, setViewMode] = useState('detail')
  const [showTutorial, setShowTutorial] = useState(() => !getTutorialDone())
  const topbarRef = useRef(null)
  const canvasAreaRef = useRef(null)
  const panelRef = useRef(null)
  const toolbarRef = useRef(null)
  const minimapRef = useRef(null)
  const panelHeaderRef = useRef(null)
  const panelElementInfoRef = useRef(null)
  const panelChatRef = useRef(null)
  const [structuralChangeFromChat, setStructuralChangeFromChat] = useState(false)
  const [structuralChangeGraph, setStructuralChangeGraph] = useState(null)
  const [workspaceFromChat, setWorkspaceFromChat] = useState(null)

  const { workspace } = useWorkspace(companyName, refreshTrigger)
  const effectiveWorkspace = workspaceFromChat || workspace

  useEffect(() => {
    // Server refetch becomes authoritative again.
    setWorkspaceFromChat(null)
  }, [workspace])

  const workspaceProcesses = useMemo(() => {
    return effectiveWorkspace?.process_tree?.processes || {}
  }, [effectiveWorkspace])

  const handleExternalGraphUpdate = useCallback(() => {
    setRefreshTrigger((t) => t + 1)
  }, [])

  const chat = useChat(companyName, {
    processId: activeProcessId,
    onGraphUpdate: handleExternalGraphUpdate,
    onWorkspaceUpdate: setWorkspaceFromChat,
  })

  useEffect(() => {
    const data = chat.lastResponseData
    if (data?.graph_json && (data.meta?.structural_change || data.meta?.tools_used)) {
      setStructuralChangeGraph(data.graph_json)
      setStructuralChangeFromChat(true)
    }
  }, [chat.lastResponseData])

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

  const panelFooter = useMemo(
    () => (
      <>
        <AureliusChat
          compact
          sessionId={companyName}
          processId={activeProcessId}
          onGraphUpdate={handleExternalGraphUpdate}
          messages={chat.messages}
          onSend={chat.handleSend}
          input={chat.input}
          onInputChange={chat.setInput}
          loading={chat.loading}
          pendingMessageId={chat.pendingMessageId}
          onApplyPlan={chat.handleApplyPlan}
          onCancelPlan={chat.handleCancelPlan}
          confirmLoading={chat.confirmLoading}
        />
        {chat.usage != null && (
          <div className="dashboard-usage" aria-label="API usage">
            <span className="dashboard-usage__turn">
              This turn: {chat.usage.api_calls_this_turn} call{chat.usage.api_calls_this_turn !== 1 ? 's' : ''}, {chat.usage.input_tokens_this_turn.toLocaleString()} in, {chat.usage.output_tokens_this_turn.toLocaleString()} out
            </span>
            {chat.usage.tool_calls_this_turn?.length > 0 && (
              <span className="dashboard-usage__tools">
                Tools: {chat.usage.tool_calls_this_turn.join(', ')}
              </span>
            )}
            <span className="dashboard-usage__total">
              Total: {chat.usage.total_api_calls.toLocaleString()} calls, {chat.usage.total_input_tokens.toLocaleString()} in, {chat.usage.total_output_tokens.toLocaleString()} out ({chat.usage.total_tokens.toLocaleString()} total)
            </span>
          </div>
        )}
      </>
    ),
    [companyName, activeProcessId, handleExternalGraphUpdate, chat],
  )

  const handleProcessSelect = useCallback(
    (processId) => {
      navigateToProcess(processId)
      setViewMode('detail')
    },
    [navigateToProcess],
  )

  const handleSwitchToDetail = useCallback(() => {
    setViewMode('detail')
  }, [])

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
      <header ref={topbarRef} className="dashboard__topbar">
        <span className="dashboard__logo">
          <img className="dashboard__logo-icon" src="/logo.png" alt="Consularis" width="24" height="24" />
          Consularis.ai
        </span>
        <div className="dashboard__topbar-actions">
          <button
            type="button"
            className="dashboard__topbar-btn"
            onClick={() => setViewMode('landscape')}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="1.5" y="3" width="5" height="4.5" rx="1" /><rect x="9.5" y="3" width="5" height="4.5" rx="1" /><rect x="5.5" y="9" width="5" height="4.5" rx="1" /></svg>
            Landscape
          </button>
          <button
            type="button"
            className="dashboard__topbar-btn dashboard__topbar-btn--accent"
            onClick={() => navigate('/dashboard/analyze')}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 1v6M5 4l3-3 3 3" /><path d="M2 8.5a6 6 0 0 0 12 0" /><circle cx="8" cy="12" r="1" fill="currentColor" /></svg>
            Analyze
          </button>
          <button
            type="button"
            className="dashboard__topbar-btn dashboard__topbar-btn--icon"
            onClick={() => {
              setViewMode('detail')
              setShowTutorial(true)
            }}
            title="Show tour"
            aria-label="Show tour"
          >
            <span className="dashboard__topbar-icon-i">i</span>
          </button>
        </div>
      </header>

      <div className="dashboard__canvas">
        {viewMode === 'landscape' ? (
          <LandscapeView
            sessionId={companyName}
            workspace={effectiveWorkspace}
            onProcessSelect={handleProcessSelect}
            onSwitchView={handleSwitchToDetail}
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
            selectedStep={selectedStep}
            onCloseDetail={handleCloseDetail}
            onStepUpdate={handleStepUpdate}
            structuralChangeFromChat={structuralChangeFromChat}
            structuralChangeGraph={structuralChangeGraph}
            onConsumedStructuralChange={() => {
              setStructuralChangeFromChat(false)
              setStructuralChangeGraph(null)
            }}
            canvasAreaRef={canvasAreaRef}
            panelRef={panelRef}
            toolbarRef={toolbarRef}
            minimapRef={minimapRef}
            panelHeaderRef={panelHeaderRef}
            panelElementInfoRef={panelElementInfoRef}
            panelChatRef={panelChatRef}
          />
        )}
      </div>

      {showTutorial && viewMode === 'detail' && (
        <DashboardTutorial
          topbarRef={topbarRef}
          canvasRef={canvasAreaRef}
          panelRef={panelRef}
          toolbarRef={toolbarRef}
          minimapRef={minimapRef}
          panelHeaderRef={panelHeaderRef}
          panelElementInfoRef={panelElementInfoRef}
          panelChatRef={panelChatRef}
          onClose={() => setShowTutorial(false)}
        />
      )}
    </div>
  )
}
