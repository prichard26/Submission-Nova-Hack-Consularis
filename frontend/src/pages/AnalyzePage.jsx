import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { analyzeGraph, requestAppointment } from '../services/api'
import Robot from '../components/Robot'
import './AnalyzePage.css'

/** Animated score 0–100 with circular ring */
function ScoreGauge({ score, label = 'Automation score' }) {
  const [displayScore, setDisplayScore] = useState(0)
  const rafRef = useRef(null)
  const startRef = useRef(null)

  useEffect(() => {
    if (score == null) return
    const duration = 1400
    const start = () => {
      startRef.current = performance.now()
      const tick = (now) => {
        const elapsed = now - startRef.current
        const t = Math.min(elapsed / duration, 1)
        const easeOut = 1 - (1 - t) ** 2
        const value = Math.round(easeOut * score)
        setDisplayScore(value)
        if (t < 1) rafRef.current = requestAnimationFrame(tick)
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    setDisplayScore(0)
    start()
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [score])

  const circumference = 2 * Math.PI * 42
  const strokeDash = circumference * (displayScore / 100)

  return (
    <div className="analyze-score">
      <div className="analyze-score__ring">
        <svg viewBox="0 0 100 100" className="analyze-score__svg">
          <circle
            className="analyze-score__bg"
            cx="50"
            cy="50"
            r="42"
            fill="none"
            strokeWidth="8"
          />
          <circle
            className="analyze-score__fill"
            cx="50"
            cy="50"
            r="42"
            fill="none"
            strokeWidth="8"
            strokeDasharray={circumference}
            strokeDashoffset={circumference - strokeDash}
            strokeLinecap="round"
          />
        </svg>
        <span className="analyze-score__value" aria-hidden="true">
          {displayScore}
        </span>
      </div>
      <p className="analyze-score__label">{label}</p>
    </div>
  )
}

/** Category row: label and value */
function CategoryCard({ label, value, sub }) {
  return (
    <div className="analyze-category">
      <span className="analyze-category__label">{label}</span>
      <span className="analyze-category__meta">
        <span className="analyze-category__value">{value}</span>
        {sub != null && sub !== '' && (
          <span className="analyze-category__sub">{sub}</span>
        )}
      </span>
    </div>
  )
}

/** Bar strip for high/medium/low counts */
function AutomationBars({ counts }) {
  const { high = 0, medium = 0, low = 0, none = 0, total_steps = 0 } = counts || {}
  if (total_steps === 0) return null
  const scale = 100 / total_steps
  return (
    <div className="analyze-bars">
      <p className="analyze-bars__title">Steps by automation potential</p>
      <div className="analyze-bars__track">
        {high > 0 && (
          <span
            className="analyze-bars__seg analyze-bars__seg--high"
            style={{ width: `${high * scale}%` }}
            title={`High: ${high}`}
          />
        )}
        {medium > 0 && (
          <span
            className="analyze-bars__seg analyze-bars__seg--medium"
            style={{ width: `${medium * scale}%` }}
            title={`Medium: ${medium}`}
          />
        )}
        {low > 0 && (
          <span
            className="analyze-bars__seg analyze-bars__seg--low"
            style={{ width: `${low * scale}%` }}
            title={`Low: ${low}`}
          />
        )}
        {none > 0 && (
          <span
            className="analyze-bars__seg analyze-bars__seg--none"
            style={{ width: `${none * scale}%` }}
            title={`Not set: ${none}`}
          />
        )}
      </div>
      <div className="analyze-bars__legend">
        <span className="analyze-bars__legend-item analyze-bars__legend-item--high">High</span>
        <span className="analyze-bars__legend-item analyze-bars__legend-item--medium">Medium</span>
        <span className="analyze-bars__legend-item analyze-bars__legend-item--low">Low</span>
        <span className="analyze-bars__legend-item analyze-bars__legend-item--none">Not set</span>
      </div>
    </div>
  )
}

export default function AnalyzePage({ sessionId }) {
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState(null)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [appointmentSending, setAppointmentSending] = useState(false)
  const [appointmentDone, setAppointmentDone] = useState(false)
  const [appointmentError, setAppointmentError] = useState(null)

  const runAnalysis = useCallback(() => {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    setMetrics(null)
    setMessage('')
    analyzeGraph(sessionId)
      .then((data) => {
        setMessage(data.message || '')
        setMetrics(data.metrics ?? null)
        setError(null)
      })
      .catch((err) => {
        setError(err?.message || 'Analysis failed. Please try again.')
        setMessage('')
        setMetrics(null)
      })
      .finally(() => setLoading(false))
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) return
    runAnalysis()
  }, [sessionId, runAnalysis])

  const handleAppointmentSubmit = useCallback(
    (e) => {
      e.preventDefault()
      if (!email.trim() || appointmentSending || appointmentDone) return
      setAppointmentError(null)
      setAppointmentSending(true)
      requestAppointment(sessionId, email.trim(), name.trim() || null)
        .then(() => {
          setAppointmentDone(true)
          setAppointmentError(null)
        })
        .catch((err) => {
          setAppointmentError(err?.message || 'Could not submit. Please try again.')
        })
        .finally(() => setAppointmentSending(false))
    },
    [sessionId, email, name, appointmentSending, appointmentDone]
  )

  return (
    <div className="analyze-page">
      <header className="analyze-page__header">
        <Link to="/dashboard" className="analyze-page__back-btn">
          Back to graph
        </Link>
        <div className="analyze-page__brand">
          <img className="analyze-page__logo" src="/logo.png" alt="" width="32" height="32" />
          <span className="analyze-page__logo-text">Consularis<span className="analyze-page__logo-dot">.</span></span>
        </div>
        <h1 className="analyze-page__title">Automation analysis</h1>
      </header>

      <main className="analyze-page__main">
        {loading && (
          <div className="analyze-page__loading" aria-live="polite">
            <Robot
              speaking
              message="Analyzing your process graph…"
              size="small"
            />
            <p className="analyze-page__loading-text">Aurelius is reviewing your processes and automation potential.</p>
          </div>
        )}

        {error && (
          <div className="analyze-page__error" role="alert">
            {error}
          </div>
        )}

        {!loading && message && (
          <div className="analyze-page__content">
            {metrics && (
              <section className="analyze-page__metrics" aria-labelledby="metrics-heading">
                <h2 id="metrics-heading" className="analyze-page__metrics-title">Automation snapshot</h2>
                <div className="analyze-page__score-wrap">
                  <ScoreGauge
                    score={metrics.overall_score}
                    label="Overall score"
                  />
                </div>
                <div className="analyze-page__categories">
                  <CategoryCard
                    label="Automation potential"
                    value={`${metrics.categories?.automation_potential ?? 0}%`}
                    sub="weighted by step potential"
                  />
                  <CategoryCard
                    label="Process coverage"
                    value={`${metrics.categories?.process_coverage ?? 0}%`}
                    sub="processes with steps"
                  />
                  <CategoryCard
                    label="Steps analyzed"
                    value={metrics.categories?.step_count ?? 0}
                    sub="total across processes"
                  />
                  <CategoryCard
                    label="Processes"
                    value={metrics.categories?.process_count ?? 0}
                    sub="in your workspace"
                  />
                </div>
                <AutomationBars counts={metrics.counts} />
              </section>
            )}

            <div className="analyze-page__actions">
              <Link to="/dashboard" className="analyze-page__btn analyze-page__btn--secondary">
                Back to graph
              </Link>
              <button
                type="button"
                className="analyze-page__btn analyze-page__btn--secondary"
                onClick={runAnalysis}
              >
                Re-run analysis
              </button>
            </div>

            <div className="analyze-page__markdown">
              <ReactMarkdown>{message}</ReactMarkdown>
            </div>

            <section className="analyze-page__cta" aria-labelledby="cta-heading">
              <h2 id="cta-heading">Get help implementing automation</h2>
              <p className="analyze-page__cta-desc">
                Book an appointment with Consularis to get your process automated. We&apos;ll be in touch.
              </p>
              {appointmentDone ? (
                <p className="analyze-page__cta-success">Thanks. We&apos;ll be in touch soon.</p>
              ) : (
                <form className="analyze-page__form" onSubmit={handleAppointmentSubmit}>
                  <input
                    type="text"
                    className="analyze-page__input"
                    placeholder="Your name (optional)"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    aria-label="Your name"
                  />
                  <input
                    type="email"
                    className="analyze-page__input"
                    placeholder="Email *"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    aria-label="Email"
                  />
                  <button
                    type="submit"
                    className="analyze-page__btn analyze-page__btn--primary"
                    disabled={!email.trim() || appointmentSending}
                  >
                    {appointmentSending ? 'Sending…' : 'Request appointment'}
                  </button>
                </form>
              )}
              {appointmentError && (
                <p className="analyze-page__cta-error" role="alert">
                  {appointmentError}
                </p>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  )
}
