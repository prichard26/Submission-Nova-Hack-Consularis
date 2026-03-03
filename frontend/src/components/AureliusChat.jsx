import { useState, useRef, useEffect } from 'react'
import { sendChat } from '../services/api'
import BotFace from './BotFace'
import './AureliusChat.css'

export const WELCOME_MSG = "Salve! I am Aurelius, your process consul. Describe your process or tell me what you'd like to change — I shall refine your graph accordingly."

const MIN_INPUT_ROWS = 1
const MAX_INPUT_ROWS = 8

export default function AureliusChat({
  sessionId,
  processId = 'Process_Global',
  onGraphUpdate,
  onClose,
  isOverlay = false,
  compact = false,
  messages: controlledMessages,
  onSend: controlledOnSend,
  input: controlledInput,
  onInputChange,
  loading: controlledLoading,
}) {
  const [uncontrolledMessages, setUncontrolledMessages] = useState([
    { id: 1, role: 'assistant', text: WELCOME_MSG }
  ])
  const [uncontrolledInput, setUncontrolledInput] = useState('')
  const [uncontrolledLoading, setUncontrolledLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  const isControlled = controlledMessages != null && controlledOnSend != null
  const messages = isControlled ? controlledMessages : uncontrolledMessages
  const input = isControlled ? (controlledInput ?? '') : uncontrolledInput
  const setInput = isControlled ? (onInputChange ?? (() => {})) : setUncontrolledInput
  const loading = isControlled ? (controlledLoading ?? false) : uncontrolledLoading

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function resizeInput() {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    const lineHeight = parseInt(getComputedStyle(el).lineHeight, 10) || 20
    const rows = Math.min(MAX_INPUT_ROWS, Math.max(MIN_INPUT_ROWS, Math.floor(el.scrollHeight / lineHeight)))
    el.style.height = `${rows * lineHeight}px`
  }

  useEffect(resizeInput, [input])

  async function handleSendUncontrolled(e) {
    e.preventDefault()
    if (!uncontrolledInput.trim() || uncontrolledLoading) return
    const userText = uncontrolledInput.trim()
    setUncontrolledInput('')
    resizeInput()
    setUncontrolledMessages((prev) => [...prev, { id: Date.now(), role: 'user', text: userText }])
    setUncontrolledLoading(true)
    try {
      const data = await sendChat(sessionId, userText, { processId })
      const reply = data.message || 'I could not process that. Please try again.'
      setUncontrolledMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', text: reply }])
      if (data.graph_json && onGraphUpdate) onGraphUpdate()
    } catch (err) {
      const text = err.status ? `Request failed (${err.status}). Please try again.` : 'The consul is temporarily unavailable. Please ensure the backend is running (e.g. ./run.sh) and try again.'
      setUncontrolledMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', text }])
    } finally {
      setUncontrolledLoading(false)
    }
  }

  function handleSendControlled(e) {
    e.preventDefault()
    if (!input.trim() || loading) return
    controlledOnSend(input.trim())
    resizeInput()
  }

  const handleSend = isControlled ? handleSendControlled : handleSendUncontrolled

  function onInputKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend(e)
    }
  }

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
            <div className="chat-msg__bubble">{msg.text}</div>
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
        <textarea
          ref={inputRef}
          className="chat-panel__input chat-panel__input--textarea"
          placeholder="Describe a change or ask a question… (Shift+Enter: new line)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onInputKeyDown}
          disabled={loading}
          rows={MIN_INPUT_ROWS}
        />
        <button className="chat-panel__send" type="submit" disabled={!input.trim() || loading} aria-label="Send message">
          ↑
        </button>
      </form>
    </div>
  )
}
