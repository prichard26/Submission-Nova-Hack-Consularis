import { useState } from 'react'
import Robot from '../components/Robot'
import './Landing.css'

const SECTORS = [
  { id: 'pharmacy', label: 'Pharmacy', icon: '⚕️', available: true },
  { id: 'logistics', label: 'Logistics', icon: '🚚', available: false },
  { id: 'manufacturing', label: 'Manufacturing', icon: '🏭', available: false },
  { id: 'finance', label: 'Finance', icon: '📊', available: false },
]

const GREET = "Salve! I'm Aurelius. Let's map your pharmacy operations — tell me your company's name and I'll generate your first process graph."
const CONFIRM = (name) => `Excellent, ${name}. Generating your pharmacy medication circuit now...`

export default function Landing({ onSubmit }) {
  const [companyName, setCompanyName] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [attemptedSubmit, setAttemptedSubmit] = useState(false)
  const [message, setMessage] = useState(GREET)
  const [speaking, setSpeaking] = useState(false)
  const companyNameMissing = attemptedSubmit && !companyName.trim()

  function speak(msg) {
    setSpeaking(true)
    setMessage(msg)
    setTimeout(() => setSpeaking(false), msg.length * 28 + 600)
  }

  function handleSubmit(e) {
    e.preventDefault()
    setAttemptedSubmit(true)
    if (!companyName.trim() || submitted) return
    setSubmitted(true)
    speak(CONFIRM(companyName.trim()))
    setTimeout(() => onSubmit({ sector: 'pharmacy', companyName: companyName.trim() }), 2000)
  }

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
        <div className="landing__robot-area">
          <Robot speaking={speaking} message={message} size="small" />
        </div>

        <div className="landing__form-area">
          <h1 className="landing__title">Map your operations</h1>
          <p className="landing__subtitle">
            Select your sector and we'll generate a baseline process graph you can refine with Aurelius.
          </p>

          <div className="landing__sectors">
            {SECTORS.map(s => (
              <div
                key={s.id}
                className={`sector-tile ${s.available ? 'sector-tile--active' : 'sector-tile--disabled'}`}
              >
                <span className="sector-tile__icon">{s.icon}</span>
                <span className="sector-tile__label">{s.label}</span>
                {!s.available && <span className="sector-tile__badge">Soon</span>}
                {s.available && <span className="sector-tile__check">✓</span>}
              </div>
            ))}
          </div>

          <form className="landing__form" onSubmit={handleSubmit}>
            <input
              className="landing__input"
              type="text"
              placeholder="Company name..."
              value={companyName}
              onChange={e => setCompanyName(e.target.value)}
              disabled={submitted}
              autoFocus
              aria-label="Company name"
              required
              aria-invalid={companyNameMissing}
              aria-describedby={companyNameMissing ? 'company-name-error' : undefined}
            />
            <button
              className="landing__btn"
              type="submit"
              disabled={!companyName.trim() || submitted}
            >
              {submitted ? 'Building graph…' : 'Generate graph →'}
            </button>
          </form>
          {companyNameMissing && (
            <p id="company-name-error" role="alert" className="landing__error">
              Please enter a company name.
            </p>
          )}
        </div>
      </main>
    </div>
  )
}
