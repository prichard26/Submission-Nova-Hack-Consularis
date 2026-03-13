import { useCallback, useRef, useState, useEffect } from 'react'
import Robot from '../components/Robot'
import { initSession } from '../services/api'
import './Landing.css'

const TEMPLATE_OPTIONS = [
  { id: 'pharmacy', label: 'Pharmacy' },
  { id: 'logistics', label: 'Logistics' },
  { id: 'manufacturing', label: 'Manufacturing' },
  { id: 'retail', label: 'Retail shops' },
  { id: 'restaurant', label: 'Restaurant' },
  { id: 'electrician', label: 'Electrician' },
  { id: 'plumber', label: 'Plumber' },
  { id: 'cleaning', label: 'Cleaning services' },
  { id: 'blank', label: 'From blank' },
]

const BOT_INTRO =
  "I'm Aurelius, your process advisor. I'll help you map how your company works and build a graph you can refine by chatting with me."

const BOT_ASK_COMPANY = "What's your company name?"
const BOT_ASK_CHOOSE_TEMPLATE =
  "We have pre-loaded templates you can start from, or you can start from a blank canvas."
const BOT_GENERATING = (name) => `Perfect. Generating ${name}'s process graph… One moment.`
const BOT_CREATING_BLANK = "Creating your blank canvas… One moment."

const GENERATING_DELAY_MS = 2500

export default function Landing({ onSubmit }) {
  const [step, setStep] = useState('name') // 'name' | 'choose_template' | 'generating' | 'done'
  const [nameInput, setNameInput] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [templateId, setTemplateId] = useState(null)
  const inputRef = useRef(null)
  const generatingTimerRef = useRef(null)

  const handleSendName = useCallback(
    (e) => {
      e?.preventDefault()
      const name = nameInput.trim()
      if (!name || step !== 'name') return
      setCompanyName(name)
      setStep('choose_template')
      setNameInput('')
      inputRef.current?.focus()
    },
    [nameInput, step]
  )

  const handleChooseTemplate = useCallback(
    (id) => {
      if (step !== 'choose_template') return
      setTemplateId(id)
      setStep('generating')
    },
    [step]
  )

  useEffect(() => {
    if (step !== 'generating' || templateId == null) return
    const fromBlank = templateId === 'blank'
    const doSubmit = () => {
      setStep('done')
      onSubmit({
        companyName,
        sector: fromBlank ? 'pharmacy' : templateId,
        fromBlank,
      })
    }
    const sessionId = companyName
    const initOptions = fromBlank ? {} : { templateId }
    initSession(sessionId, fromBlank, initOptions)
      .then(() => {
        generatingTimerRef.current = setTimeout(doSubmit, GENERATING_DELAY_MS)
      })
      .catch(() => {
        doSubmit()
      })
    return () => {
      if (generatingTimerRef.current) {
        clearTimeout(generatingTimerRef.current)
        generatingTimerRef.current = null
      }
    }
  }, [step, templateId, companyName, onSubmit])

  const robotMessage =
    step === 'name'
      ? BOT_INTRO + '\n\n' + BOT_ASK_COMPANY
      : step === 'choose_template'
        ? BOT_ASK_CHOOSE_TEMPLATE
        : ''

  const isGeneratingOrDone = step === 'generating' || step === 'done'
  const fromBlank = templateId === 'blank'
  const generatingMessage = isGeneratingOrDone
    ? step === 'done'
      ? 'Taking you to your graph…'
      : fromBlank
        ? BOT_CREATING_BLANK
        : BOT_GENERATING(companyName)
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
          {/* Single fixed slot: same robot size and position for every step */}
          <div className="landing__robot-slot">
            {(step === 'name' || step === 'choose_template') && (
              <Robot speaking message={robotMessage} size="small" />
            )}
            {isGeneratingOrDone && (
              <Robot
                speaking={step === 'generating'}
                message={generatingMessage}
                size="small"
              />
            )}
          </div>

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

            {step === 'choose_template' && (
              <div className="landing__actions landing__actions--templates">
                {TEMPLATE_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className={
                      opt.id === 'blank'
                        ? 'landing__action-btn landing__action-btn--secondary'
                        : `landing__action-btn landing__action-btn--tint landing__action-btn--tint-${opt.id}`
                    }
                    onClick={() => handleChooseTemplate(opt.id)}
                  >
                    {opt.label}
                  </button>
                ))}
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
