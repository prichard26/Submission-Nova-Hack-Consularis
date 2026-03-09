import { useState, useCallback } from 'react'
import { sendChat, confirmChatPlan } from '../services/api'
import { WELCOME_MSG } from '../components/AureliusChat'

function getChatErrorText(err, fallback = 'The consul is temporarily unavailable. Please ensure the backend is running (e.g. ./run.sh) and try again.') {
  if (err?.message) return err.message
  if (err?.status) return `Request failed (${err.status}). Please try again.`
  return fallback
}

function extractUsage(meta) {
  if (!meta) return null
  return {
    tool_calls_this_turn: meta.tool_calls_this_turn ?? [],
    api_calls_this_turn: meta.api_calls_this_turn ?? 0,
    input_tokens_this_turn: meta.input_tokens_this_turn ?? 0,
    output_tokens_this_turn: meta.output_tokens_this_turn ?? 0,
    total_api_calls: meta.total_api_calls ?? 0,
    total_input_tokens: meta.total_input_tokens ?? 0,
    total_output_tokens: meta.total_output_tokens ?? 0,
    total_tokens: meta.total_tokens ?? 0,
  }
}

export function useChat(sessionId, { processId = 'global', onGraphUpdate, onWorkspaceUpdate } = {}) {
  const [messages, setMessages] = useState([
    { id: 1, role: 'assistant', text: WELCOME_MSG }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [pendingMessageId, setPendingMessageId] = useState(null)
  const [confirmLoading, setConfirmLoading] = useState(false)
  const [usage, setUsage] = useState(null)
  const [lastResponseData, setLastResponseData] = useState(null)

  const handleSend = useCallback(async (userText) => {
    if (!userText?.trim() || loading) return
    setInput('')
    setMessages((prev) => [...prev, { id: Date.now(), role: 'user', text: userText.trim() }])
    setLoading(true)
    setPendingMessageId(null)
    try {
      const data = await sendChat(sessionId, userText.trim(), { processId })
      const reply = data.message || 'I could not process that. Please try again.'
      const assistantId = Date.now() + 1
      setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', text: reply }])
      if (data.meta?.requires_confirmation && data.meta?.pending_plan) {
        setPendingMessageId(assistantId)
      }
      setUsage(extractUsage(data.meta))
      setLastResponseData(data)
      if (data.workspace && onWorkspaceUpdate) onWorkspaceUpdate(data.workspace)
      if (data.meta?.tools_used && onGraphUpdate) onGraphUpdate()
    } catch (err) {
      const text = getChatErrorText(err)
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', text }])
    } finally {
      setLoading(false)
    }
  }, [sessionId, processId, loading, onGraphUpdate, onWorkspaceUpdate])

  const handleApplyPlan = useCallback(async () => {
    if (confirmLoading || !pendingMessageId) return
    setConfirmLoading(true)
    try {
      const data = await confirmChatPlan(sessionId, { processId })
      const reply = data.message || 'Plan applied.'
      setMessages((prev) => [...prev, { id: Date.now(), role: 'assistant', text: reply }])
      setPendingMessageId(null)
      setUsage(extractUsage(data.meta))
      setLastResponseData(data)
      if (data.workspace && onWorkspaceUpdate) onWorkspaceUpdate(data.workspace)
      if (data.meta?.tools_used && onGraphUpdate) onGraphUpdate()
    } catch (err) {
      const text = getChatErrorText(err, 'Could not apply plan. Please try again.')
      setMessages((prev) => [...prev, { id: Date.now(), role: 'assistant', text }])
      setPendingMessageId(null)
    } finally {
      setConfirmLoading(false)
    }
  }, [sessionId, processId, pendingMessageId, confirmLoading, onGraphUpdate, onWorkspaceUpdate])

  const handleCancelPlan = useCallback(() => {
    setPendingMessageId(null)
  }, [])

  return {
    messages,
    input,
    setInput,
    loading,
    pendingMessageId,
    confirmLoading,
    usage,
    lastResponseData,
    handleSend,
    handleApplyPlan,
    handleCancelPlan,
  }
}
