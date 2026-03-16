/**
 * Aurelius chat UI: message list, input (text + voice), model picker, Apply plan / Cancel plan.
 * Can be controlled (messages/onSend from parent) or uncontrolled (useChat). Supports overlay and compact modes.
 */
import { useRef, useEffect, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import { useChat } from '../hooks/useChat'
import { useVoiceInput } from '../hooks/useVoiceInput'
import { useMicLevels } from '../hooks/useMicLevels'
import BotFace from './BotFace'
import ModelPicker from './ModelPicker'
import './AureliusChat.css'

export const WELCOME_MSG = "This is your process graph. I can explain steps, actors, and flow—and edit it: add or remove steps, change actors or durations, rewire flows, add subprocesses. Say what you want to change and I’ll update the graph."

const MIN_INPUT_ROWS = 1
const MAX_INPUT_ROWS = 8
const VOICE_BAR_COUNT = 5

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
  modelId: controlledModelId,
  onModelIdChange,
  availableModels: controlledAvailableModels,
}) {
  const uncontrolled = useChat(sessionId, { processId, onGraphUpdate: onGraphUpdate })
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const {
    isSupported: isVoiceSupported,
    isListening,
    transcript: voiceTranscript,
    accumulatedLive,
    interimTranscript,
    error: voiceError,
    toggleListening,
  } = useVoiceInput()
  const micLevels = useMicLevels(isListening)

  const voicePlaceholder = useMemo(
    () =>
      isListening
        ? [accumulatedLive, interimTranscript].filter(Boolean).join(' ') || 'Listening…'
        : null,
    [isListening, accumulatedLive, interimTranscript]
  )

  const isControlled = controlledMessages != null && controlledOnSend != null
  const messages = isControlled ? controlledMessages : uncontrolled.messages
  const input = isControlled ? (controlledInput ?? '') : uncontrolled.input
  const setInput = isControlled ? (onInputChange ?? (() => {})) : uncontrolled.setInput
  const loading = isControlled ? (controlledLoading ?? false) : uncontrolled.loading
  const pendingMessageId = isControlled ? (controlledPendingMessageId ?? null) : uncontrolled.pendingMessageId
  const confirmLoadingState = isControlled ? (controlledConfirmLoading ?? false) : uncontrolled.confirmLoading
  const currentModelId = isControlled ? (controlledModelId ?? null) : uncontrolled.modelId
  const setModelId = isControlled ? (onModelIdChange ?? (() => {})) : uncontrolled.setModelId
  const models = isControlled ? (controlledAvailableModels ?? []) : uncontrolled.availableModels

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

  const wasListeningRef = useRef(false)
  const lastCommittedTranscriptRef = useRef('')
  useEffect(() => {
    if (isListening) {
      lastCommittedTranscriptRef.current = ''
      wasListeningRef.current = true
      return
    }
    wasListeningRef.current = false
    if (voiceTranscript && voiceTranscript !== lastCommittedTranscriptRef.current) {
      lastCommittedTranscriptRef.current = voiceTranscript
      setInput((prev) => (prev.trim() ? prev + ' ' + voiceTranscript : voiceTranscript))
      resizeInput()
    }
    // setInput stable; omit to satisfy exhaustive-deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isListening, voiceTranscript, resizeInput])

  const handleSendUncontrolled = useCallback((e) => {
    e.preventDefault()
    if (!uncontrolled.input.trim() || uncontrolled.loading) return
    uncontrolled.handleSend(uncontrolled.input.trim())
    resizeInput()
  }, [uncontrolled, resizeInput])

  const handleApplyPlan = isControlled ? (controlledOnApplyPlan ?? (() => {})) : uncontrolled.handleApplyPlan
  const handleCancelPlan = isControlled ? (controlledOnCancelPlan ?? (() => {})) : uncontrolled.handleCancelPlan

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
          {isListening && (
            <div
              className={`chat-panel__listening-waves ${Array.isArray(micLevels) ? 'chat-panel__listening-waves--live' : ''}`}
              aria-hidden
            >
              <div className="chat-panel__listening-waves__circle">
                {Array.from({ length: VOICE_BAR_COUNT }, (_, i) => (
                  <span
                    key={i}
                    className="chat-panel__listening-waves__bar"
                    style={
                      Array.isArray(micLevels) && micLevels[i] != null
                        ? { transform: `scaleY(${micLevels[i]})` }
                        : undefined
                    }
                  />
                ))}
              </div>
            </div>
          )}
          <textarea
            ref={inputRef}
            className="chat-panel__input chat-panel__input--textarea"
            placeholder={
              pendingMessageId
                ? "Type 'Apply' or 'Confirm', or ask for changes…"
                : voicePlaceholder ?? "Describe a change or ask a question… (Shift+Enter: new line)"
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onInputKeyDown}
            disabled={loading}
            rows={MIN_INPUT_ROWS}
          />
          <div className="chat-panel__button-stack">
            <button className="chat-panel__send" type="submit" disabled={!input.trim() || loading} aria-label="Send message">
              ↑
            </button>
            {isVoiceSupported ? (
              <button
                className={`chat-panel__mic ${isListening ? 'chat-panel__mic--active' : ''}`}
                type="button"
                onClick={toggleListening}
                disabled={loading}
                aria-label={isListening ? 'Stop recording' : 'Start voice input'}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3Z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" y1="19" x2="12" y2="22" />
                </svg>
              </button>
            ) : null}
          </div>
        </div>
        {voiceError && <p className="chat-panel__hint chat-panel__hint--error">{voiceError}</p>}
        <ModelPicker models={models} value={currentModelId} onChange={setModelId} disabled={loading} />
      </form>
    </div>
  )
}
