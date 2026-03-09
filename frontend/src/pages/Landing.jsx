import { useCallback, useRef, useState, useEffect } from 'react'
import Robot from '../components/Robot'
import { initSession } from '../services/api'
import './Landing.css'

const SECTORS = [
  { id: 'pharmacy', label: 'Pharmacy', available: true },
  { id: 'logistics', label: 'Logistics', available: false },
  { id: 'manufacturing', label: 'Manufacturing', available: false },
  { id: 'finance', label: 'Finance', available: false },
]

const BOT_INTRO =
  "I'm Aurelius, your process advisor. I'll help you map how your company works and build a graph you can refine by chatting with me."

const BOT_ASK_COMPANY = "What's your company name?"
const BOT_ASK_SECTOR = (companyName) => `What type of company is ${companyName}? Pick one.`
const BOT_ASK_START_FROM = "Do you want to start from a template (pre-filled process for your sector) or from a blank canvas (just start and end nodes)?"
const BOT_GENERATING = (name) => `Perfect. Generating ${name}'s process graph… One moment.`
const BOT_CREATING_BLANK = "Creating your blank canvas… One moment."

const GENERATING_DELAY_MS = 2500

export default function Landing({ onSubmit }) {
  const [step, setStep] = useState('name') // 'name' | 'sector' | 'start_from' | 'generating' | 'done'
  const [nameInput, setNameInput] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [selectedSector, setSelectedSector] = useState(null)
  const [fromBlank, setFromBlank] = useState(false)
  const inputRef = useRef(null)
  const generatingTimerRef = useRef(null)

  const handleSendName = useCallback(
    (e) => {
      e?.preventDefault()
      const name = nameInput.trim()
      if (!name || step !== 'name') return
      setCompanyName(name)
      setStep('sector')
      setNameInput('')
      inputRef.current?.focus()
    },
    [nameInput, step]
  )

  const handleSelectSector = useCallback(
    (sector) => {
      if (!sector.available || step !== 'sector') return
      setSelectedSector(sector)
      setStep('start_from')
    },
    [step]
  )

  const handleStartFromTemplate = useCallback(() => {
    if (step !== 'start_from') return
    setFromBlank(false)
    setStep('generating')
  }, [step])

  const handleStartFromBlank = useCallback(() => {
    if (step !== 'start_from') return
    setFromBlank(true)
    setStep('generating')
  }, [step])

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

  const robotMessage = step === 'name'
    ? BOT_INTRO + '\n\n' + BOT_ASK_COMPANY
    : step === 'sector'
      ? BOT_ASK_SECTOR(companyName)
      : step === 'start_from'
        ? BOT_ASK_START_FROM
        : ''

  return (
    <div className="landing">
      <div className="landing__bg-glow" />

      <header className="landing__header">
        <span className="landing__logo">
          <img className="landing__logo-img" src="/logo.png" alt="Consularis" width="24" height="24" />
          Consularis.ai
        </span>
      </header>

      <main className="landing__main">
        <div className="landing__chat">
          {(step === 'name' || step === 'sector' || step === 'start_from') && (
            <div className={step === 'name' ? 'landing__robot-hero' : 'landing__robot-prompt'}>
              <Robot speaking message={robotMessage} size={step === 'name' ? 'normal' : 'small'} />
            </div>
          )}

          {(step === 'generating' || step === 'done') && (
            <div className="landing__robot-prompt">
              <Robot
                speaking={step === 'generating'}
                message={step === 'done' ? 'Taking you to your graph…' : (fromBlank ? BOT_CREATING_BLANK : BOT_GENERATING(companyName))}
                size="small"
              />
            </div>
          )}

          <div className="landing__chat-input-area">
            {step === 'name' && (
              <form className="landing__chat-form" onSubmit={handleSendName}>
                <input
                  ref={inputRef}
                  type="text"
                  className="landing__chat-input"
                  placeholder="Company name..."
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  autoFocus
                  aria-label="Company name"
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
              <div className="landing__actions">
                {SECTORS.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className={`landing__action-btn ${s.available ? 'landing__action-btn--primary' : 'landing__action-btn--secondary landing__action-btn--disabled'}`}
                    onClick={() => handleSelectSector(s)}
                    disabled={!s.available}
                  >
                    {s.label}
                    {!s.available && <span className="landing__action-badge">Soon</span>}
                  </button>
                ))}
              </div>
            )}

            {step === 'start_from' && (
              <div className="landing__actions">
                <button
                  type="button"
                  className="landing__action-btn landing__action-btn--primary"
                  onClick={handleStartFromTemplate}
                >
                  From template
                </button>
                <button
                  type="button"
                  className="landing__action-btn landing__action-btn--secondary"
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
