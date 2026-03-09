import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import { sendChat, confirmChatPlan } from '../services/api'
import BotFace from './BotFace'
import './AureliusChat.css'

export const WELCOME_MSG = "Here you're looking at an example process graph. I can help you understand it—which steps do what, who is responsible, how the flow runs—and modify it: add or remove steps, change actors or durations, connect or disconnect flows, and add subprocesses. Describe what you see, ask questions, or tell me what you'd like to change, and I'll update the graph accordingly."

const MIN_INPUT_ROWS = 1
const MAX_INPUT_ROWS = 8

export default function AureliusChat({
  sessionId,
  processId = 'global',
  onGraphUpdate,
  onClose,
  isOverlay = false,
  compact = false,
  messages: controlledMessages,
  onSend: controlledOnSend,
  input: controlledInput,
  onInputChange,
  loading: controlledLoading,
  pendingMessageId: controlledPendingMessageId,
  onApplyPlan: controlledOnApplyPlan,
  onCancelPlan: controlledOnCancelPlan,
  confirmLoading: controlledConfirmLoading,
}) {
  const [uncontrolledMessages, setUncontrolledMessages] = useState([
    { id: 1, role: 'assistant', text: WELCOME_MSG }
  ])
  const [uncontrolledInput, setUncontrolledInput] = useState('')
  const [uncontrolledLoading, setUncontrolledLoading] = useState(false)
  const [uncontrolledPendingMessageId, setUncontrolledPendingMessageId] = useState(null)
  const [confirmLoading, setConfirmLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  const isControlled = controlledMessages != null && controlledOnSend != null
  const messages = isControlled ? controlledMessages : uncontrolledMessages
  const input = isControlled ? (controlledInput ?? '') : uncontrolledInput
  const setInput = isControlled ? (onInputChange ?? (() => {})) : setUncontrolledInput
  const loading = isControlled ? (controlledLoading ?? false) : uncontrolledLoading
  const pendingMessageId = isControlled ? (controlledPendingMessageId ?? null) : uncontrolledPendingMessageId
  const confirmLoadingState = isControlled ? (controlledConfirmLoading ?? false) : confirmLoading

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const resizeInput = useCallback(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    const lineHeight = parseInt(getComputedStyle(el).lineHeight, 10) || 20
    const rows = Math.min(MAX_INPUT_ROWS, Math.max(MIN_INPUT_ROWS, Math.floor(el.scrollHeight / lineHeight)))
    el.style.height = `${rows * lineHeight}px`
  }, [])

  useEffect(() => {
    resizeInput()
  }, [input, resizeInput])

  const handleSendUncontrolled = useCallback(async (e) => {
    e.preventDefault()
    if (!uncontrolledInput.trim() || uncontrolledLoading) return
    const userText = uncontrolledInput.trim()
    setUncontrolledInput('')
    resizeInput()
    setUncontrolledMessages((prev) => [...prev, { id: Date.now(), role: 'user', text: userText }])
    setUncontrolledLoading(true)
    setPendingMessageId(null)
    try {
      const data = await sendChat(sessionId, userText, { processId })
      const reply = data.message || 'I could not process that. Please try again.'
      const assistantId = Date.now() + 1
      setUncontrolledMessages((prev) => [...prev, { id: assistantId, role: 'assistant', text: reply }])
      if (data.meta?.requires_confirmation && data.meta?.pending_plan) {
        setUncontrolledPendingMessageId(assistantId)
      }
      if (data.graph_json && onGraphUpdate) onGraphUpdate()
    } catch (err) {
      const text = err.status ? `Request failed (${err.status}). Please try again.` : 'The consul is temporarily unavailable. Please ensure the backend is running (e.g. ./run.sh) and try again.'
      setUncontrolledMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', text }])
    } finally {
      setUncontrolledLoading(false)
    }
  }, [uncontrolledInput, uncontrolledLoading, processId, resizeInput, sessionId, onGraphUpdate])

  const handleApplyPlanUncontrolled = useCallback(async () => {
    if (confirmLoading || !uncontrolledPendingMessageId) return
    setConfirmLoading(true)
    try {
      const data = await confirmChatPlan(sessionId, { processId })
      const reply = data.message || 'Plan applied.'
      setUncontrolledMessages((prev) => [...prev, { id: Date.now(), role: 'assistant', text: reply }])
      setUncontrolledPendingMessageId(null)
      if (data.graph_json && onGraphUpdate) onGraphUpdate()
    } catch (err) {
      const text = err?.message || err?.status ? `Request failed (${err.status}). Please try again.` : 'Could not apply plan. Please try again.'
      setUncontrolledMessages((prev) => [...prev, { id: Date.now(), role: 'assistant', text }])
      setUncontrolledPendingMessageId(null)
    } finally {
      setConfirmLoading(false)
    }
  }, [sessionId, processId, uncontrolledPendingMessageId, confirmLoading, onGraphUpdate])

  const handleCancelPlanUncontrolled = useCallback(() => {
    setUncontrolledPendingMessageId(null)
  }, [])

  const handleApplyPlan = isControlled ? (controlledOnApplyPlan ?? (() => {})) : handleApplyPlanUncontrolled
  const handleCancelPlan = isControlled ? (controlledOnCancelPlan ?? (() => {})) : handleCancelPlanUncontrolled

  const handleSendControlled = useCallback((e) => {
    e.preventDefault()
    if (!input.trim() || loading) return
    controlledOnSend(input.trim())
    resizeInput()
  }, [controlledOnSend, input, loading, resizeInput])

  const handleSend = isControlled ? handleSendControlled : handleSendUncontrolled

  const onInputKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend(e)
    }
  }, [handleSend])

  const panelClass = [
    'chat-panel',
    isOverlay && 'chat-panel--overlay',
    compact && 'chat-panel--compact',
  ].filter(Boolean).join(' ')

  return (
    <div
      className={panelClass}
      role={isOverlay ? 'dialog' : undefined}
      aria-modal={isOverlay || undefined}
      aria-label={isOverlay ? 'Aurelius assistant chat' : undefined}
    >
      {!compact && (
        <div className="chat-panel__header">
          <div className="chat-panel__title-row">
            <div className="chat-panel__avatar">
              <BotFace talking={loading} size={28} />
            </div>
            <div>
              <div className="chat-panel__name">Aurelius</div>
              <div className="chat-panel__status">{loading ? 'Thinking…' : 'Process consul'}</div>
            </div>
          </div>
          {isOverlay && onClose && (
            <button className="chat-panel__close" onClick={onClose} aria-label="Close chat">✕</button>
          )}
        </div>
      )}

      <div className="chat-panel__messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-msg chat-msg--${msg.role}`}>
            {msg.role === 'assistant' && (
              <div className="chat-msg__avatar">
                <BotFace talking={false} size={22} />
              </div>
            )}
            <div className="chat-msg__bubble-wrap">
              <div className="chat-msg__bubble chat-msg__bubble--md">
                {msg.role === 'assistant' ? (
                  <ReactMarkdown>{msg.text}</ReactMarkdown>
                ) : (
                  msg.text
                )}
              </div>
              {msg.role === 'assistant' && msg.id === pendingMessageId && (
                <div className="chat-msg__actions">
                  <button
                    type="button"
                    className="chat-msg__action chat-msg__action--primary"
                    onClick={handleApplyPlan}
                    disabled={confirmLoadingState}
                  >
                    {confirmLoadingState ? 'Applying…' : 'Apply plan'}
                  </button>
                  <button
                    type="button"
                    className="chat-msg__action chat-msg__action--secondary"
                    onClick={handleCancelPlan}
                    disabled={confirmLoadingState}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="chat-msg chat-msg--assistant">
            <div className="chat-msg__avatar">
              <BotFace talking={true} size={22} />
            </div>
            <div className="chat-msg__bubble chat-msg__typing">…</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form className="chat-panel__form" onSubmit={handleSend}>
        {pendingMessageId && (
          <p className="chat-panel__hint">You can also type <strong>Apply</strong> or <strong>Confirm</strong> to apply the plan.</p>
        )}
        <div className="chat-panel__input-row">
          <textarea
            ref={inputRef}
            className="chat-panel__input chat-panel__input--textarea"
            placeholder={pendingMessageId ? "Type 'Apply' or 'Confirm', or ask for changes…" : "Describe a change or ask a question… (Shift+Enter: new line)"}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onInputKeyDown}
            disabled={loading}
            rows={MIN_INPUT_ROWS}
          />
          <button className="chat-panel__send" type="submit" disabled={!input.trim() || loading} aria-label="Send message">
            ↑
          </button>
        </div>
      </form>
    </div>
  )
}
