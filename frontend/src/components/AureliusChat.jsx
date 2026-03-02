import { useState, useRef, useEffect } from 'react'
import { sendChat } from '../services/api'
import './AureliusChat.css'

export const WELCOME_MSG = "Salve! I am Aurelius, your process consul. Describe your process or tell me what you'd like to change — I shall refine your graph accordingly."

export default function AureliusChat({
  sessionId,
  processId = 'Process_Global',
  onGraphUpdate,
  onClose,
  isOverlay = false,
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

  const isControlled = controlledMessages != null && controlledOnSend != null
  const messages = isControlled ? controlledMessages : uncontrolledMessages
  const input = isControlled ? (controlledInput ?? '') : uncontrolledInput
  const setInput = isControlled ? (onInputChange ?? (() => {})) : setUncontrolledInput
  const loading = isControlled ? (controlledLoading ?? false) : uncontrolledLoading

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSendUncontrolled(e) {
    e.preventDefault()
    if (!uncontrolledInput.trim() || uncontrolledLoading) return
    const userText = uncontrolledInput.trim()
    setUncontrolledInput('')
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
  }

  const handleSend = isControlled ? handleSendControlled : handleSendUncontrolled

  return (
    <div
      className="chat-panel"
      role={isOverlay ? 'dialog' : undefined}
      aria-modal={isOverlay || undefined}
      aria-label={isOverlay ? 'Aurelius assistant chat' : undefined}
    >
      <div className="chat-panel__header">
        <div className="chat-panel__title-row">
          <div className="chat-panel__avatar">A</div>
          <div>
            <div className="chat-panel__name">Aurelius</div>
            <div className="chat-panel__status">{loading ? 'Thinking…' : 'Process consul'}</div>
          </div>
        </div>
        {isOverlay && onClose && (
          <button className="chat-panel__close" onClick={onClose} aria-label="Close chat">✕</button>
        )}
      </div>

      <div className="chat-panel__messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-msg chat-msg--${msg.role}`}>
            {msg.role === 'assistant' && <div className="chat-msg__avatar">A</div>}
            <div className="chat-msg__bubble">{msg.text}</div>
          </div>
        ))}
        {loading && (
          <div className="chat-msg chat-msg--assistant">
            <div className="chat-msg__avatar">A</div>
            <div className="chat-msg__bubble chat-msg__typing">…</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form className="chat-panel__form" onSubmit={handleSend}>
        <input
          className="chat-panel__input"
          type="text"
          placeholder="Describe a change or ask a question…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
        />
        <button className="chat-panel__send" type="submit" disabled={!input.trim() || loading} aria-label="Send message">
          ↑
        </button>
      </form>
    </div>
  )
}
