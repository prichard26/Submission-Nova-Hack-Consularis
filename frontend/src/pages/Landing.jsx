import { useCallback, useRef, useState, useEffect } from 'react'
import BotFace from '../components/BotFace'
import { initSession } from '../services/api'
import './Landing.css'

const SECTORS = [
  { id: 'pharmacy', label: 'Pharmacy', icon: '⚕️', available: true },
  { id: 'logistics', label: 'Logistics', icon: '🚚', available: false },
  { id: 'manufacturing', label: 'Manufacturing', icon: '🏭', available: false },
  { id: 'finance', label: 'Finance', icon: '📊', available: false },
]

const BOT_INTRO =
  "I'm Aurelius. Think of me as your process advisor: I help you map how your company works—steps, who does what, and how it all connects. " +
  "You'll get a living process graph you can refine by chatting with me. Let's start simple."

const BOT_ASK_NAME = "First, what should I call you? Your name, or your company's—either works."
const BOT_ASK_SECTOR = (name) => `Nice to meet you, ${name}. What type of company do you run? Pick one.`
const BOT_ASK_START_FROM = "Do you want to start from a template (pre-filled process for your sector) or from a blank canvas (just start and end nodes)?"
const BOT_GENERATING = (name) => `Perfect. Generating ${name}'s process graph… One moment.`
const BOT_CREATING_BLANK = "Creating your blank canvas… One moment."

const GENERATING_DELAY_MS = 2500

export default function Landing({ onSubmit }) {
  const [messages, setMessages] = useState(() => [
    { id: 1, role: 'bot', content: BOT_INTRO },
    { id: 2, role: 'bot', content: BOT_ASK_NAME },
  ])
  const [step, setStep] = useState('name') // 'name' | 'sector' | 'start_from' | 'generating' | 'done'
  const [nameInput, setNameInput] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [selectedSector, setSelectedSector] = useState(null)
  const [fromBlank, setFromBlank] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const generatingTimerRef = useRef(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, step, scrollToBottom])

  const addBotMessage = useCallback((content) => {
    setMessages((prev) => [
      ...prev,
      { id: prev.length + 1, role: 'bot', content },
    ])
  }, [])

  const addUserMessage = useCallback((content) => {
    setMessages((prev) => [
      ...prev,
      { id: prev.length + 1, role: 'user', content },
    ])
  }, [])

  const handleSendName = useCallback(
    (e) => {
      e?.preventDefault()
      const name = nameInput.trim()
      if (!name || step !== 'name') return
      setCompanyName(name)
      addUserMessage(name)
      addBotMessage(BOT_ASK_SECTOR(name))
      setStep('sector')
      setNameInput('')
      inputRef.current?.focus()
    },
    [nameInput, step, addUserMessage, addBotMessage]
  )

  const handleSelectSector = useCallback(
    (sector) => {
      if (!sector.available || step !== 'sector') return
      setSelectedSector(sector)
      addUserMessage(`${sector.icon} ${sector.label}`)
      addBotMessage(BOT_ASK_START_FROM)
      setStep('start_from')
    },
    [step, addUserMessage, addBotMessage]
  )

  const handleStartFromTemplate = useCallback(() => {
    if (step !== 'start_from') return
    setFromBlank(false)
    addUserMessage('From template')
    addBotMessage(BOT_GENERATING(companyName))
    setStep('generating')
  }, [step, companyName, addUserMessage, addBotMessage])

  const handleStartFromBlank = useCallback(() => {
    if (step !== 'start_from') return
    setFromBlank(true)
    addUserMessage('From blank')
    addBotMessage(BOT_CREATING_BLANK)
    setStep('generating')
  }, [step, addUserMessage, addBotMessage])

  useEffect(() => {
    if (step !== 'generating' || !selectedSector) return
    const doSubmit = () => {
      setStep('done')
      onSubmit({ companyName, sector: selectedSector.id, fromBlank })
    }
    if (fromBlank) {
      initSession(companyName, true).then(() => {
        generatingTimerRef.current = setTimeout(doSubmit, GENERATING_DELAY_MS)
      }).catch(() => {
        doSubmit()
      })
    } else {
      generatingTimerRef.current = setTimeout(doSubmit, GENERATING_DELAY_MS)
    }
    return () => {
      if (generatingTimerRef.current) {
        clearTimeout(generatingTimerRef.current)
        generatingTimerRef.current = null
      }
    }
  }, [step, selectedSector, companyName, fromBlank, onSubmit])

  return (
    <div className="landing">
      <div className="landing__bg-glow" />

      <header className="landing__header">
        <span className="landing__logo">
          <img className="landing__logo-img" src="/logo.png" alt="" width="40" height="40" />
          Consularis<span className="landing__logo-dot">.</span>
        </span>
        <span className="landing__tagline">Process Intelligence</span>
      </header>

      <main className="landing__main">
        <div className="landing__chat">
          <div className="landing__chat-messages">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`landing__msg landing__msg--${msg.role}`}
              >
                {msg.role === 'bot' && (
                  <div className="landing__msg-avatar" aria-hidden="true">
                    <BotFace talking={false} size={32} />
                  </div>
                )}
                <div className="landing__msg-bubble">
                  <p>{msg.content}</p>
                </div>
              </div>
            ))}

            <div ref={messagesEndRef} />
          </div>

          <div className="landing__chat-input-area">
            {step === 'name' && (
              <form className="landing__chat-form" onSubmit={handleSendName}>
                <input
                  ref={inputRef}
                  type="text"
                  className="landing__chat-input"
                  placeholder="Your name or company name..."
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  autoFocus
                  aria-label="Your name"
                />
                <button
                  type="submit"
                  className="landing__chat-send"
                  disabled={!nameInput.trim()}
                  aria-label="Send"
                >
                  Send →
                </button>
              </form>
            )}

            {step === 'sector' && (
              <div className="landing__sectors">
                {SECTORS.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className={`landing__sector-btn ${s.available ? 'landing__sector-btn--active' : 'landing__sector-btn--disabled'}`}
                    onClick={() => handleSelectSector(s)}
                    disabled={!s.available}
                  >
                    <span className="landing__sector-icon">{s.icon}</span>
                    <span className="landing__sector-label">{s.label}</span>
                    {!s.available && (
                      <span className="landing__sector-badge">Soon</span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {step === 'start_from' && (
              <div className="landing__start-from">
                <button
                  type="button"
                  className="landing__start-from-btn landing__start-from-btn--template"
                  onClick={handleStartFromTemplate}
                >
                  From template
                </button>
                <button
                  type="button"
                  className="landing__start-from-btn landing__start-from-btn--blank"
                  onClick={handleStartFromBlank}
                >
                  From blank
                </button>
              </div>
            )}

            {step === 'generating' && (
              <div className="landing__generating" aria-live="polite">
                <span className="landing__generating-dot" />
                <span className="landing__generating-dot" />
                <span className="landing__generating-dot" />
              </div>
            )}

            {step === 'done' && (
              <div className="landing__generating landing__generating--done">
                Taking you to your graph…
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
