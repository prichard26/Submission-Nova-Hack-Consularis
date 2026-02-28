import { useState, useEffect } from 'react'
import Robot from './components/Robot'
import DomainCard from './components/DomainCard'
import Colonnade from './components/Colonnade'
import './App.css'

const DOMAINS = [
  {
    id: 'pharmacy',
    label: 'Pharmacy',
    description: 'Dispensing, compliance, patient care workflows',
  },
  {
    id: 'logistics',
    label: 'Logistics',
    description: 'Supply chain, warehousing, distribution ops',
  },
  {
    id: 'other',
    label: 'Other',
    description: 'Tell us about your industry',
  },
]

const MESSAGES = {
  greeting: "Salve! I'm Aurelius, your process consul. Let's map out how your company operates. First — what industry are you in?",
  selected: (domain) => `${domain} — excellent choice. Now tell me your company's name and we shall begin the analysis.`,
  submitted: (name) => `Welcome aboard, ${name}. Your operational analysis is being prepared. The Senate shall review your processes shortly.`,
}

export default function App() {
  const [step, setStep] = useState('greeting')
  const [selectedDomain, setSelectedDomain] = useState(null)
  const [companyName, setCompanyName] = useState('')
  const [robotMessage, setRobotMessage] = useState('')
  const [speaking, setSpeaking] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      speak(MESSAGES.greeting)
    }, 600)
    return () => clearTimeout(timer)
  }, [])

  function speak(msg) {
    setSpeaking(true)
    setRobotMessage(msg)
    setTimeout(() => setSpeaking(false), msg.length * 30 + 500)
  }

  function handleDomainSelect(domain) {
    setSelectedDomain(domain)
    setStep('name')
    speak(MESSAGES.selected(domain.label))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!companyName.trim() || !selectedDomain) return

    speak(MESSAGES.submitted(companyName.trim()))
    setStep('done')

    try {
      await fetch('http://localhost:8000/api/select-domain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domain: selectedDomain.id,
          company_name: companyName.trim(),
        }),
      })
    } catch {
      // Backend not running yet
    }
  }

  return (
    <div className="app">
      {/* Background */}
      <div className="bg-glow bg-glow--1" />
      <div className="bg-glow bg-glow--2" />

      {/* Header with Roman pediment feel */}
      <header className="header">
        <div className="header__pediment" aria-hidden />
        <div className="header__logo">
          <svg className="header__laurel" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M4 22C6 16 9 8 14 4C19 8 22 16 24 22" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.5"/>
            <path d="M7 20C9 15 11 9 14 6C17 9 19 15 21 20" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.7"/>
            <circle cx="14" cy="4" r="2" fill="currentColor" opacity="0.8"/>
          </svg>
          <span>Consularis<span className="header__logo-accent">.</span></span>
        </div>
        <span className="header__tagline">Process Intelligence</span>
        <span className="header__motto">Ordo ab Chao</span>
      </header>

      {/* Main content: forum between columns */}
      <main className="main">
        <Colonnade>
          <Robot speaking={speaking} message={robotMessage} />

        {/* Domain cards */}
        {(step === 'greeting' || step === 'name') && (
          <div className="domain-cards">
            {DOMAINS.map((d) => (
              <DomainCard
                key={d.id}
                domain={d.id}
                label={d.label}
                description={d.description}
                selected={selectedDomain?.id === d.id}
                onClick={() => handleDomainSelect(d)}
              />
            ))}
          </div>
        )}

        {/* Company name input */}
        {step === 'name' && (
          <form className="name-form" onSubmit={handleSubmit}>
            <input
              type="text"
              className="name-form__input"
              placeholder="Enter your company name..."
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              autoFocus
            />
            <button
              type="submit"
              className="name-form__btn"
              disabled={!companyName.trim()}
            >
              Let's go
              <span className="name-form__btn-arrow">&rarr;</span>
            </button>
          </form>
        )}

        {/* Done state */}
        {step === 'done' && (
          <div className="done-card">
            <div className="done-card__badge">{selectedDomain.label}</div>
            <h2 className="done-card__company">{companyName}</h2>
            <p className="done-card__text">
              Your process analysis workspace is being prepared...
            </p>
            <div className="done-card__loader">
              <div className="done-card__loader-bar" />
            </div>
          </div>
        )}
        </Colonnade>
      </main>
    </div>
  )
}
