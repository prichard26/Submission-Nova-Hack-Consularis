import { useState, useCallback, useMemo, useEffect } from 'react'
import AureliusChat, { WELCOME_MSG } from '../components/AureliusChat'
import ProcessCanvas from '../components/ProcessCanvas'
import LandscapeView from '../components/LandscapeView'
import { useWorkspace } from '../hooks/useWorkspace'
import { sendChat, confirmChatPlan } from '../services/api'
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
  const [structuralChangeFromChat, setStructuralChangeFromChat] = useState(false)
  const [structuralChangeGraph, setStructuralChangeGraph] = useState(null)
  const [usage, setUsage] = useState(null)
  const [pendingMessageId, setPendingMessageId] = useState(null)
  const [confirmLoading, setConfirmLoading] = useState(false)

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
      setPendingMessageId(null)
      try {
        const data = await sendChat(companyName, userText, { processId: activeProcessId })
        const reply = data.message || 'I could not process that. Please try again.'
        const assistantId = Date.now() + 1
        setChatMessages((prev) => [...prev, { id: assistantId, role: 'assistant', text: reply }])
        if (data.meta?.requires_confirmation && data.meta?.pending_plan) {
          setPendingMessageId(assistantId)
        }
        if (data.meta) {
          const toolCalls = data.meta.tool_calls_this_turn ?? []
          if (toolCalls.length > 0) {
            console.log('[Aurelius] Tools called this turn:', toolCalls.join(', '))
          }
          setUsage({
            tool_calls_this_turn: toolCalls,
            api_calls_this_turn: data.meta.api_calls_this_turn ?? 0,
            input_tokens_this_turn: data.meta.input_tokens_this_turn ?? 0,
            output_tokens_this_turn: data.meta.output_tokens_this_turn ?? 0,
            total_api_calls: data.meta.total_api_calls ?? 0,
            total_input_tokens: data.meta.total_input_tokens ?? 0,
            total_output_tokens: data.meta.total_output_tokens ?? 0,
            total_tokens: data.meta.total_tokens ?? 0,
          })
        }
        if (data.meta?.tools_used) {
          handleExternalGraphUpdate()
        }
        if (data.graph_json && data.meta?.structural_change) {
          setStructuralChangeGraph(data.graph_json)
          setStructuralChangeFromChat(true)
        }
      } catch (err) {
        const text = err.status ? `Request failed (${err.status}). Please try again.` : 'The consul is temporarily unavailable. Please ensure the backend is running (e.g. ./run.sh) and try again.'
        setChatMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', text }])
      } finally {
        setChatLoading(false)
      }
    },
    [companyName, activeProcessId, handleExternalGraphUpdate],
  )

  const handleApplyPlan = useCallback(async () => {
    if (confirmLoading) return
    setConfirmLoading(true)
    try {
      const data = await confirmChatPlan(companyName, { processId: activeProcessId })
      const reply = data.message || 'Plan applied.'
      setChatMessages((prev) => [...prev, { id: Date.now(), role: 'assistant', text: reply }])
      setPendingMessageId(null)
      if (data.meta) {
        setUsage({
          tool_calls_this_turn: data.meta.tool_calls_this_turn ?? [],
          api_calls_this_turn: data.meta.api_calls_this_turn ?? 0,
          input_tokens_this_turn: data.meta.input_tokens_this_turn ?? 0,
          output_tokens_this_turn: data.meta.output_tokens_this_turn ?? 0,
          total_api_calls: data.meta.total_api_calls ?? 0,
          total_input_tokens: data.meta.total_input_tokens ?? 0,
          total_output_tokens: data.meta.total_output_tokens ?? 0,
          total_tokens: data.meta.total_tokens ?? 0,
        })
      }
      if (data.meta?.tools_used) {
        handleExternalGraphUpdate()
      }
      if (data.graph_json && data.meta?.structural_change) {
        setStructuralChangeGraph(data.graph_json)
        setStructuralChangeFromChat(true)
      }
    } catch (err) {
      const text = err?.message || (err?.status ? `Request failed (${err.status}). Please try again.` : 'Could not apply plan. Please try again.')
      setChatMessages((prev) => [...prev, { id: Date.now(), role: 'assistant', text }])
      setPendingMessageId(null)
    } finally {
      setConfirmLoading(false)
    }
  }, [companyName, activeProcessId, handleExternalGraphUpdate])

  const handleCancelPlan = useCallback(() => {
    setPendingMessageId(null)
  }, [])

  const panelFooter = useMemo(
    () => (
      <>
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
          pendingMessageId={pendingMessageId}
          onApplyPlan={handleApplyPlan}
          onCancelPlan={handleCancelPlan}
          confirmLoading={confirmLoading}
        />
        {usage != null && (
          <div className="dashboard-usage" aria-label="API usage">
            <span className="dashboard-usage__turn">
              This turn: {usage.api_calls_this_turn} call{usage.api_calls_this_turn !== 1 ? 's' : ''}, {usage.input_tokens_this_turn.toLocaleString()} in, {usage.output_tokens_this_turn.toLocaleString()} out
            </span>
            {usage.tool_calls_this_turn?.length > 0 && (
              <span className="dashboard-usage__tools">
                Tools: {usage.tool_calls_this_turn.join(', ')}
              </span>
            )}
            <span className="dashboard-usage__total">
              Total: {usage.total_api_calls.toLocaleString()} calls, {usage.total_input_tokens.toLocaleString()} in, {usage.total_output_tokens.toLocaleString()} out ({usage.total_tokens.toLocaleString()} total)
            </span>
          </div>
        )}
      </>
    ),
    [companyName, activeProcessId, handleExternalGraphUpdate, chatMessages, handleChatSend, chatInput, chatLoading, usage, pendingMessageId, handleApplyPlan, handleCancelPlan, confirmLoading],
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
          />
        )}
      </div>

    </div>
  )
}
