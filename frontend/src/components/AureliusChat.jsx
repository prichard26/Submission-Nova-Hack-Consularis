import { useState, useRef, useEffect } from 'react'
import { sendChat } from '../services/api'
import './AureliusChat.css'

const WELCOME_MSG = "Salve! I am Aurelius, your process consul. Tell me which step you wish to change — use the step id (e.g. P1.2, P3.1) — and what to update. I shall refine your pharmacy graph. If I do not understand, I will ask you to repeat."

export default function AureliusChat({ sessionId, onGraphUpdate, onClose }) {
  const [messages, setMessages] = useState([
    { id: 1, role: 'assistant', text: WELCOME_MSG }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend(e) {
    e.preventDefault()
    if (!input.trim() || loading) return
    const userText = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { id: Date.now(), role: 'user', text: userText }])
    setLoading(true)

    try {
      const data = await sendChat(sessionId, userText)
      const reply = data.message || 'I could not process that. Please try again.'
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: 'assistant', text: reply }])
      // Backend returns authoritative BPMN XML; refresh diagram from this payload.
      if (data.bpmn_xml && onGraphUpdate) {
        onGraphUpdate(data.bpmn_xml)
      }
    } catch (err) {
      const text = err.status ? `Request failed (${err.status}). Please try again.` : 'The consul is temporarily unavailable. Please ensure the backend is running (e.g. ./run.sh) and try again.'
      setMessages((prev) => [
        ...prev,
        { id: Date.now() + 1, role: 'assistant', text }
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-panel__header">
        <div className="chat-panel__title-row">
          <div className="chat-panel__avatar">A</div>
          <div>
            <div className="chat-panel__name">Aurelius</div>
            <div className="chat-panel__status">{loading ? 'Thinking…' : 'Process consul'}</div>
          </div>
        </div>
        <button className="chat-panel__close" onClick={onClose}>✕</button>
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
          placeholder="e.g. Change P1.2 duration to 10 min"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
        />
        <button className="chat-panel__send" type="submit" disabled={!input.trim() || loading}>
          ↑
        </button>
      </form>
    </div>
  )
}
