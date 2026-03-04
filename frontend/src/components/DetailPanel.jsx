import { memo, useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { updateStepFields } from '../services/api'
import './DetailPanel.css'

const TEXT_FIELDS = [
  { key: 'actor', label: 'Actor / Role' },
  { key: 'duration_min', label: 'Duration' },
  { key: 'frequency', label: 'Frequency' },
  { key: 'annual_volume', label: 'Annual Volume' },
  { key: 'cost_per_execution', label: 'Cost per Execution' },
  { key: 'error_rate_percent', label: 'Error Rate %' },
  { key: 'sla_target', label: 'SLA Target' },
  { key: 'current_state', label: 'Current State' },
  { key: 'data_format', label: 'Data Format' },
]

const TEXTAREA_FIELDS = [
  { key: 'description', label: 'Description' },
  { key: 'automation_notes', label: 'Automation Notes' },
]

const AUTOMATION_OPTIONS = ['', 'high', 'medium', 'low', 'none']

const LIST_FIELDS = [
  { key: 'inputs', label: 'Inputs' },
  { key: 'outputs', label: 'Outputs' },
  { key: 'risks', label: 'Risks' },
  { key: 'current_systems', label: 'Current Systems' },
  { key: 'external_dependencies', label: 'External Dependencies' },
  { key: 'regulatory_constraints', label: 'Regulatory Constraints' },
  { key: 'pain_points', label: 'Pain Points' },
]

const AccordionSection = memo(function AccordionSection({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <section className="detail-panel__section">
      <button
        type="button"
        className="detail-panel__section-toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="detail-panel__section-title">{title}</span>
        <svg
          className={`detail-panel__chevron ${open ? 'detail-panel__chevron--open' : ''}`}
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M3 4.5L6 7.5L9 4.5" />
        </svg>
      </button>
      {open && <div className="detail-panel__section-body">{children}</div>}
    </section>
  )
})

export default function DetailPanel({ step, sessionId, processId, onClose, onUpdate }) {
  const [form, setForm] = useState({})
  const saveTimerRef = useRef(null)

  useEffect(() => {
    if (!step) return
    const initial = {}
    initial.name = step.name || ''
    for (const f of TEXT_FIELDS) initial[f.key] = step[f.key] || ''
    for (const f of TEXTAREA_FIELDS) initial[f.key] = step[f.key] || ''
    initial.automation_potential = step.automation_potential || ''
    for (const f of LIST_FIELDS) initial[f.key] = Array.isArray(step[f.key]) ? step[f.key].join(', ') : (step[f.key] || '')
    setForm(initial)
  }, [step])

  const persistChanges = useCallback(
    (updates) => {
      clearTimeout(saveTimerRef.current)
      saveTimerRef.current = setTimeout(() => {
        const payload = {}
        for (const [k, v] of Object.entries(updates)) {
          const listField = LIST_FIELDS.find((f) => f.key === k)
          if (listField) {
            payload[k] = v
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean)
          } else {
            payload[k] = v
          }
        }
        updateStepFields(sessionId, processId, step.id, payload)
          .then(() => onUpdate?.())
          .catch((err) => console.warn('Save failed', err))
      }, 800)
    },
    [sessionId, processId, step, onUpdate],
  )

  const handleChange = useCallback((key, value) => {
    setForm((prev) => {
      const next = { ...prev, [key]: value }
      persistChanges({ [key]: value })
      return next
    })
  }, [persistChanges])

  const autoResizeTextarea = useCallback((el) => {
    if (!el) return
    el.style.height = 'auto'
    el.style.height = el.scrollHeight + 'px'
  }, [])

  if (!step) return null

  const isNameOnly = step.type === 'decision' || step.type === 'subprocess'

  return (
    <div className="detail-panel" role="complementary" aria-label="Element details">
      <div className="detail-panel__header">
        <div className="detail-panel__title-row">
          <span className="detail-panel__short-id">{step.short_id || step.id}</span>
          <span className="detail-panel__type-badge">{step.type}</span>
          <button className="detail-panel__close" onClick={onClose} aria-label="Deselect element">✕</button>
        </div>
        <input
          className="detail-panel__name-input"
          type="text"
          value={form.name ?? ''}
          onChange={(e) => handleChange('name', e.target.value)}
          placeholder={isNameOnly ? `${step.type} name` : 'Step name'}
        />
      </div>

      {!isNameOnly && (
        <div className="detail-panel__body">
          <AccordionSection title="Core" defaultOpen>
            {TEXT_FIELDS.slice(0, 2).map((f) => (
              <label key={f.key} className="detail-panel__field">
                <span className="detail-panel__label">{f.label}</span>
                <input
                  type="text"
                  className="detail-panel__input"
                  value={form[f.key] ?? ''}
                  onChange={(e) => handleChange(f.key, e.target.value)}
                />
              </label>
            ))}
            {TEXTAREA_FIELDS.slice(0, 1).map((f) => (
              <label key={f.key} className="detail-panel__field">
                <span className="detail-panel__label">{f.label}</span>
                <textarea
                  className="detail-panel__textarea detail-panel__textarea--autosize"
                  value={form[f.key] ?? ''}
                  onChange={(e) => {
                    handleChange(f.key, e.target.value)
                    autoResizeTextarea(e.target)
                  }}
                  ref={(el) => el && autoResizeTextarea(el)}
                  rows={1}
                />
              </label>
            ))}
          </AccordionSection>

          <AccordionSection title="Metrics">
            {TEXT_FIELDS.slice(2).map((f) => (
              <label key={f.key} className="detail-panel__field">
                <span className="detail-panel__label">{f.label}</span>
                <input
                  type="text"
                  className="detail-panel__input"
                  value={form[f.key] ?? ''}
                  onChange={(e) => handleChange(f.key, e.target.value)}
                />
              </label>
            ))}
          </AccordionSection>

          <AccordionSection title="Automation">
            <label className="detail-panel__field">
              <span className="detail-panel__label">Potential</span>
              <select
                className="detail-panel__select"
                value={form.automation_potential ?? ''}
                onChange={(e) => handleChange('automation_potential', e.target.value)}
              >
                {AUTOMATION_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt || '—'}
                  </option>
                ))}
              </select>
            </label>
            {TEXTAREA_FIELDS.slice(1).map((f) => (
              <label key={f.key} className="detail-panel__field">
                <span className="detail-panel__label">{f.label}</span>
                <textarea
                  className="detail-panel__textarea"
                  value={form[f.key] ?? ''}
                  onChange={(e) => handleChange(f.key, e.target.value)}
                  rows={2}
                />
              </label>
            ))}
          </AccordionSection>

          <AccordionSection title="Lists">
            <p className="detail-panel__hint">Comma-separated values</p>
            {LIST_FIELDS.map((f) => (
              <label key={f.key} className="detail-panel__field">
                <span className="detail-panel__label">{f.label}</span>
                <textarea
                  className="detail-panel__textarea"
                  value={form[f.key] ?? ''}
                  onChange={(e) => handleChange(f.key, e.target.value)}
                  rows={2}
                />
              </label>
            ))}
          </AccordionSection>
        </div>
      )}
    </div>
  )
}
