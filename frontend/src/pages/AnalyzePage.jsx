import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { useReactToPrint } from 'react-to-print'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'
import { getReport, getWorkspace, requestAppointment } from '../services/api'
import { layoutTree } from '../services/landscapeLayout'
import Robot from '../components/Robot'
import DashboardTopBar from '../components/DashboardTopBar'
import './Dashboard.css'
import './AnalyzePage.css'

/* Report palette: orange, red, dark grey */
const REPORT_ORANGE = '#e85d04'
const REPORT_RED = '#c03020'
const REPORT_DARK_GREY = '#2d2d2d'
const REPORT_GREY = '#5a5a5a'

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

const CHART_COLORS = {
  high: REPORT_ORANGE,
  medium: REPORT_GREY,
  low: REPORT_DARK_GREY,
  none: '#888',
  manual: REPORT_RED,
  semi_automated: REPORT_ORANGE,
  automated: REPORT_DARK_GREY,
  unknown: '#888',
}

const AXIS_FONT_SIZE = 14
const PIE_LABEL_FONT_SIZE = 13

function ReportCharts({ metrics }) {
  const perProcess = metrics?.per_process ?? []
  const distAuto = metrics?.distributions?.automation_potential ?? {}
  const distState = metrics?.distributions?.current_state ?? {}

  const costData = perProcess.filter((p) => p.step_count > 0).map((p) => ({
    name: p.name || '—',
    fullName: p.name || '—',
    cost: p.annual_cost,
    volume: p.annual_volume,
    errorRate: p.avg_error_rate,
  }))

  const barH = Math.max(220, costData.length * 36)
  const yAxisWidth = 160

  const pieAutomation = [
    { name: 'High', value: distAuto.high || 0, key: 'high' },
    { name: 'Medium', value: distAuto.medium || 0, key: 'medium' },
    { name: 'Low', value: distAuto.low || 0, key: 'low' },
    { name: 'Not set', value: distAuto.none || 0, key: 'none' },
  ].filter((d) => d.value > 0)

  const pieState = [
    { name: 'Manual', value: distState.manual || 0, key: 'manual' },
    { name: 'Semi-auto', value: distState.semi_automated || 0, key: 'semi_automated' },
    { name: 'Automated', value: distState.automated || 0, key: 'automated' },
    { name: 'Unknown', value: distState.unknown || 0, key: 'unknown' },
  ].filter((d) => d.value > 0)

  const pieH = 200
  const tickStyle = { fontSize: AXIS_FONT_SIZE, fill: REPORT_DARK_GREY }

  const TooltipContent = ({ payload, labelKey, format }) => {
    if (!payload?.[0]) return null
    const p = payload[0].payload
    return (
      <span className="report-chart__tooltip">
        {p.fullName || p.name}: {format ? format(payload[0].value) : Number(payload[0].value).toLocaleString()}
      </span>
    )
  }

  return (
    <div className="report-charts report-charts--compact">
      {costData.length > 0 && (
        <>
          <div className="report-chart">
            <h4 className="report-chart__title">Annual cost by process</h4>
            <ResponsiveContainer width="100%" height={barH}>
              <BarChart layout="vertical" data={costData} margin={{ top: 8, right: 16, left: 8, bottom: 8 }} barSize={24}>
                <CartesianGrid strokeDasharray="2 2" stroke={REPORT_DARK_GREY} opacity={0.2} horizontal={false} />
                <XAxis type="number" tick={tickStyle} />
                <YAxis type="category" dataKey="name" width={yAxisWidth} tick={{ ...tickStyle, width: yAxisWidth - 16 }} />
                <Tooltip content={(props) => <TooltipContent {...props} format={(v) => Number(v).toLocaleString()} />} />
                <Bar dataKey="cost" fill={REPORT_ORANGE} radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="report-chart">
            <h4 className="report-chart__title">Annual volume by process</h4>
            <ResponsiveContainer width="100%" height={barH}>
              <BarChart layout="vertical" data={costData} margin={{ top: 8, right: 16, left: 8, bottom: 8 }} barSize={24}>
                <CartesianGrid strokeDasharray="2 2" stroke={REPORT_DARK_GREY} opacity={0.2} horizontal={false} />
                <XAxis type="number" tick={tickStyle} />
                <YAxis type="category" dataKey="name" width={yAxisWidth} tick={{ ...tickStyle, width: yAxisWidth - 16 }} />
                <Tooltip content={(props) => <TooltipContent {...props} format={(v) => Number(v).toLocaleString()} />} />
                <Bar dataKey="volume" fill={REPORT_DARK_GREY} radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="report-chart">
            <h4 className="report-chart__title">Avg error rate by process (%)</h4>
            <ResponsiveContainer width="100%" height={barH}>
              <BarChart layout="vertical" data={costData} margin={{ top: 8, right: 16, left: 8, bottom: 8 }} barSize={24}>
                <CartesianGrid strokeDasharray="2 2" stroke={REPORT_DARK_GREY} opacity={0.2} horizontal={false} />
                <XAxis type="number" tick={tickStyle} />
                <YAxis type="category" dataKey="name" width={yAxisWidth} tick={{ ...tickStyle, width: yAxisWidth - 16 }} />
                <Tooltip content={(props) => <TooltipContent {...props} format={(v) => `${v}%`} />} />
                <Bar dataKey="errorRate" fill={REPORT_RED} radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
      {pieAutomation.length > 0 && (
        <div className="report-chart report-chart--pie">
          <h4 className="report-chart__title">Automation potential</h4>
          <ResponsiveContainer width="100%" height={pieH}>
            <PieChart>
              <Pie
                data={pieAutomation}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={58}
                paddingAngle={2}
                label={({ name, value }) => `${name}: ${value}`}
                labelLine={{ strokeWidth: 1 }}
              >
                {pieAutomation.map((e) => (
                  <Cell key={e.key} fill={CHART_COLORS[e.key] || CHART_COLORS.none} stroke={REPORT_DARK_GREY} strokeWidth={1} />
                ))}
              </Pie>
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: PIE_LABEL_FONT_SIZE }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
      {pieState.length > 0 && (
        <div className="report-chart report-chart--pie">
          <h4 className="report-chart__title">Current state</h4>
          <ResponsiveContainer width="100%" height={pieH}>
            <PieChart>
              <Pie
                data={pieState}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={58}
                paddingAngle={2}
                label={({ name, value }) => `${name}: ${value}`}
                labelLine={{ strokeWidth: 1 }}
              >
                {pieState.map((e) => (
                  <Cell key={e.key} fill={CHART_COLORS[e.key] || CHART_COLORS.unknown} stroke={REPORT_DARK_GREY} strokeWidth={1} />
                ))}
              </Pie>
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: PIE_LABEL_FONT_SIZE }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

/** Key metrics at a glance: one prominent horizontal bar chart + KPI row. */
function ReportGlanceSection({ metrics }) {
  const perProcess = metrics?.per_process ?? []
  const totals = metrics?.totals ?? {}
  const costData = perProcess.filter((p) => p.step_count > 0).map((p) => ({
    name: p.name || '—',
    fullName: p.name || '—',
    cost: p.annual_cost,
  }))
  const glanceChartHeight = Math.max(280, costData.length * 40)
  const yAxisWidth = 180
  const tickStyle = { fontSize: AXIS_FONT_SIZE, fill: REPORT_DARK_GREY }

  return (
    <section className="report-section report-section--glance" aria-labelledby="glance-heading">
      <h2 id="glance-heading">Key metrics at a glance</h2>
      <div className="report-glance-kpis">
        <div className="report-glance-kpi">
          <span className="report-glance-kpi__value">
            {totals.annual_cost != null ? Number(totals.annual_cost).toLocaleString() : '—'}
          </span>
          <span className="report-glance-kpi__label">Total annual cost</span>
        </div>
        <div className="report-glance-kpi">
          <span className="report-glance-kpi__value">
            {totals.annual_volume != null ? Number(totals.annual_volume).toLocaleString() : '—'}
          </span>
          <span className="report-glance-kpi__label">Total annual volume</span>
        </div>
        <div className="report-glance-kpi">
          <span className="report-glance-kpi__value">{totals.automation_readiness_score ?? '—'}</span>
          <span className="report-glance-kpi__label">Automation readiness</span>
        </div>
        <div className="report-glance-kpi">
          <span className="report-glance-kpi__value">{totals.step_count ?? '—'}</span>
          <span className="report-glance-kpi__label">Steps</span>
        </div>
      </div>
      {costData.length > 0 && (
        <div className="report-glance-chart">
          <h3 className="report-chart__title">Total annual cost by process</h3>
          <ResponsiveContainer width="100%" height={glanceChartHeight}>
            <BarChart layout="vertical" data={costData} margin={{ top: 8, right: 24, left: 8, bottom: 8 }} barSize={28}>
              <CartesianGrid strokeDasharray="2 2" stroke={REPORT_DARK_GREY} opacity={0.2} horizontal={false} />
              <XAxis type="number" tick={tickStyle} />
              <YAxis type="category" dataKey="name" width={yAxisWidth} tick={{ ...tickStyle, width: yAxisWidth - 20 }} />
              <Tooltip
                content={({ payload }) =>
                  payload?.[0] ? (
                    <span className="report-chart__tooltip">
                      {payload[0].payload.fullName}: {Number(payload[0].value).toLocaleString()}
                    </span>
                  ) : null
                }
              />
              <Bar dataKey="cost" fill={REPORT_ORANGE} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}

/** SVG process tree overview (same structure as LandscapeView) for report/PDF. No IDs shown — names only. */
function ReportLandscapeSvg({ workspace, largeLabels = false }) {
  if (!workspace?.process_tree?.processes) return null
  const { nodes, edges } = layoutTree(workspace)
  const processes = workspace.process_tree.processes
  if (nodes.length === 0) return null

  const nameSize = largeLabels ? 22 : 16
  const subSize = largeLabels ? 16 : 13
  const padding = largeLabels ? 32 : 24
  const minX = Math.min(...nodes.map((n) => n.x))
  const minY = Math.min(...nodes.map((n) => n.y))
  const maxX = Math.max(...nodes.map((n) => n.x + n.width))
  const maxY = Math.max(...nodes.map((n) => n.y + n.height))
  const width = maxX - minX + padding * 2
  const height = maxY - minY + padding * 2

  return (
    <div className={`report-landscape-svg-wrap ${largeLabels ? 'report-landscape-svg-wrap--cover' : ''}`}>
      <svg
        className={`report-landscape-svg ${largeLabels ? 'report-landscape-svg--cover' : ''}`}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        aria-label="Process graph overview"
      >
        {edges.map((e) => {
          const src = nodes.find((n) => n.id === e.source)
          const tgt = nodes.find((n) => n.id === e.target)
          if (!src || !tgt) return null
          const x1 = src.x - minX + padding + src.width / 2
          const y1 = src.y - minY + padding + src.height
          const x2 = tgt.x - minX + padding + tgt.width / 2
          const y2 = tgt.y - minY + padding
          return <line key={e.id} x1={x1} y1={y1} x2={x2} y2={y2} stroke={REPORT_DARK_GREY} strokeWidth={largeLabels ? 2 : 1.5} />
        })}
        {nodes.map((n) => {
          const info = processes[n.id] || {}
          const displayName = info.name || '—'
          const label = displayName.length > (largeLabels ? 28 : 20) ? displayName.slice(0, largeLabels ? 26 : 18) + '…' : displayName
          const x = n.x - minX + padding
          const y = n.y - minY + padding
          return (
            <g key={n.id}>
              <rect
                x={x}
                y={y}
                width={n.width}
                height={n.height}
                rx={8}
                fill="#f5f0eb"
                stroke={REPORT_ORANGE}
                strokeWidth={largeLabels ? 2.5 : 2}
              />
              <text x={x + n.width / 2} y={y + n.height / 2 - (largeLabels ? 8 : 6)} textAnchor="middle" fontSize={nameSize} fill={REPORT_DARK_GREY} fontWeight="600">
                {label}
              </text>
              {info.summary?.step_count != null && (
                <text x={x + n.width / 2} y={y + n.height / 2 + (largeLabels ? 14 : 10)} textAnchor="middle" fontSize={subSize} fill={REPORT_GREY}>
                  {info.summary.step_count} steps
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function ProcessCard({ proc }) {
  return (
    <div className="report-process-card">
      <h4 className="report-process-card__name">{proc.name}</h4>
      <div className="report-process-card__meta">
        <span>{proc.owner || '—'}</span>
        <span>{proc.category || '—'}</span>
        <span className="report-process-card__criticality">{proc.criticality || '—'}</span>
      </div>
      <div className="report-process-card__numbers">
        <span>{proc.step_count} steps</span>
        <span>Cost: {Number(proc.annual_cost).toLocaleString()}</span>
        <span>Volume: {Number(proc.annual_volume).toLocaleString()}</span>
        <span>Avg error: {proc.avg_error_rate}%</span>
      </div>
    </div>
  )
}

function ProcessDeepDive({ proc }) {
  const steps = proc?.steps ?? []
  const titleId = `section-${(proc?.name || '').replace(/\s+/g, '-').replace(/[^a-z0-9-]/gi, '')}`
  return (
    <section className="report-deep-dive" aria-labelledby={titleId}>
      <h3 id={titleId} className="report-deep-dive__title">
        {proc?.name}
      </h3>
      {steps.length > 0 && (
        <div className="report-deep-dive__table-wrap">
          <table className="report-steps-table">
            <thead>
              <tr>
                <th>Step</th>
                <th>Actor</th>
                <th>Duration</th>
                <th>Volume</th>
                <th>Cost</th>
                <th>Error %</th>
                <th>Automation</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((s) => (
                <tr key={s.id}>
                  <td>{s.name || '—'}</td>
                  <td>{s.actor || '—'}</td>
                  <td>{s.duration_min || '—'}</td>
                  <td>{s.annual_volume != null ? Number(s.annual_volume).toLocaleString() : '—'}</td>
                  <td>{s.annual_cost != null ? Number(s.annual_cost).toLocaleString() : '—'}</td>
                  <td>{s.error_rate_percent != null ? s.error_rate_percent : '—'}</td>
                  <td>{s.automation_potential || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {steps.some((s) => (s.pain_points?.length || s.risks?.length)) && (
        <div className="report-deep-dive__lists">
          {steps.map(
            (s) =>
              (s.pain_points?.length || s.risks?.length) && (
                <div key={s.id} className="report-deep-dive__step-issues">
                  <strong>{s.name || '—'}</strong>
                  {s.risks?.length > 0 && (
                    <p>
                      <em>Risks:</em> {s.risks.join(', ')}
                    </p>
                  )}
                  {s.pain_points?.length > 0 && (
                    <p>
                      <em>Pain points:</em> {s.pain_points.join(', ')}
                    </p>
                  )}
                </div>
              )
          )}
        </div>
      )}
    </section>
  )
}

function stripSectionHeading(text, headingTitle) {
  if (!text || typeof text !== 'string') return text
  const t = text.trim()
  const re = new RegExp(`^#+\\s*${headingTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\n*`, 'i')
  return t.replace(re, '').trim()
}

/** Remove process/step IDs from markdown so report shows names only (e.g. (P2.1), (S1), process S1). */
function stripIdsFromMarkdown(text) {
  if (!text || typeof text !== 'string') return text
  return text
    .replace(/\bprocess\s+[A-Z]\d+(?:\.\d+)?\b/gi, 'process')
    .replace(/\bstep\s+[A-Z]\d+(?:\.\d+)?\b/gi, 'step')
    .replace(/\s*\([A-Z]\d+(?:\.\d+)?\)\s*/g, ' ')
    .replace(/\b[A-Z]\d+(?:\.\d+)?\b(?=\s*[:\-])/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

export default function AnalyzePage({ sessionId }) {
  const [loading, setLoading] = useState(true)
  const [report, setReport] = useState(null)
  const [workspace, setWorkspace] = useState(null)
  const [error, setError] = useState(null)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [appointmentSending, setAppointmentSending] = useState(false)
  const [appointmentDone, setAppointmentDone] = useState(false)
  const [appointmentError, setAppointmentError] = useState(null)
  const reportRef = useRef(null)

  const runReport = useCallback(() => {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    setReport(null)
    setWorkspace(null)
    Promise.all([getReport(sessionId), getWorkspace(sessionId)])
      .then(([data, ws]) => {
        setReport(data)
        setWorkspace(ws ?? null)
        setError(null)
      })
      .catch((err) => {
        setError(err?.message || 'Report failed. Please try again.')
        setReport(null)
        setWorkspace(null)
      })
      .finally(() => setLoading(false))
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) return
    runReport()
  }, [sessionId, runReport])

  const handlePrint = useReactToPrint({
    contentRef: reportRef,
    documentTitle: report?.metrics?.workspace_name
      ? `Report - ${report.metrics.workspace_name}`
      : 'Company Process Intelligence Report',
    pageStyle: `
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .report-no-print { display: none !important; }
      .analyze-page__main { max-width: 100%; }
    `,
  })

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

  const metrics = report?.metrics
  const narratives = report?.narratives ?? {}
  const totals = metrics?.totals ?? {}
  const perProcess = metrics?.per_process ?? []
  const processWithSteps = perProcess.filter((p) => p.step_count > 0)

  return (
    <div className="analyze-page">
      <DashboardTopBar activeMode="analyze" />

      <main className="analyze-page__main">
        {loading && (
          <div className="analyze-page__loading" aria-live="polite">
            <Robot
              speaking
              message="Generating your Company Process Intelligence Report…"
              size="small"
            />
            <p className="analyze-page__loading-text">
              We&apos;re computing metrics and generating analysis sections.
            </p>
          </div>
        )}

        {error && (
          <div className="analyze-page__error" role="alert">
            {error}
          </div>
        )}

        {!loading && report && (
          <div className="analyze-page__content">
            <div className="report-no-print analyze-page__actions">
              <Link to="/dashboard" className="analyze-page__btn analyze-page__btn--secondary">
                Back to graph
              </Link>
              <button
                type="button"
                className="analyze-page__btn analyze-page__btn--secondary"
                onClick={runReport}
              >
                Re-run report
              </button>
              <button
                type="button"
                className="analyze-page__btn analyze-page__btn--primary"
                onClick={handlePrint}
              >
                Download PDF
              </button>
            </div>

            <div ref={reportRef} className="report-print-root">
              {/* PDF only: header with logo + Consularis on every page */}
              <div className="report-print-header" aria-hidden="true">
                <img src="/logo.png" alt="" className="report-print-header__logo" />
                <span className="report-print-header__name">Consularis</span>
              </div>

              {/* PDF only: clean first page = title + name + graph (large fonts) */}
              <div className="report-cover">
                <h1 className="report-cover__title">Company Process Intelligence Report</h1>
                {metrics?.workspace_name && (
                  <p className="report-cover__subtitle">{metrics.workspace_name}</p>
                )}
                <div className="report-cover__graph">
                  <ReportLandscapeSvg workspace={workspace} largeLabels />
                </div>
              </div>

              <div className="report-body">
                <header className="report-header report-header--no-print">
                  <h1 className="report-title">Company Process Intelligence Report</h1>
                  {metrics?.workspace_name && (
                    <p className="report-subtitle">{metrics.workspace_name}</p>
                  )}
                </header>

                {/* Key metrics at a glance — before Executive Summary */}
                <ReportGlanceSection metrics={metrics} />

                {/* Section 1: Executive Summary */}
                <section className="report-section" aria-labelledby="exec-heading">
                  <h2 id="exec-heading">Executive Summary</h2>
                  <div className="report-section__markdown">
                    <ReactMarkdown>
                      {stripIdsFromMarkdown(
                        stripSectionHeading(narratives.executive_summary, 'Executive Summary') || '*No summary generated.*'
                      )}
                    </ReactMarkdown>
                  </div>
                </section>

                {/* Section 2: Graph overview (landscape) — screen only; PDF has cover */}
                <section className="report-section report-section--overview report-section--no-print" aria-labelledby="overview-heading">
                  <h2 id="overview-heading">Process graph overview</h2>
                  <ReportLandscapeSvg workspace={workspace} />
                </section>

                {/* Section 3: Key Numbers */}
                <section className="report-section" aria-labelledby="key-numbers-heading">
                <h2 id="key-numbers-heading">Key Numbers</h2>
                <div className="report-section__kpis">
                  <div className="report-score-wrap">
                    <ScoreGauge
                      score={totals.automation_readiness_score}
                      label="Automation readiness"
                    />
                  </div>
                  <div className="report-categories">
                    <CategoryCard
                      label="Total annual cost"
                      value={totals.annual_cost != null ? Number(totals.annual_cost).toLocaleString() : '—'}
                    />
                    <CategoryCard
                      label="Total annual volume"
                      value={totals.annual_volume != null ? Number(totals.annual_volume).toLocaleString() : '—'}
                    />
                    <CategoryCard
                      label="Weighted avg error rate"
                      value={totals.weighted_avg_error_rate != null ? `${totals.weighted_avg_error_rate}%` : '—'}
                    />
                    <CategoryCard label="Steps" value={totals.step_count ?? '—'} />
                    <CategoryCard label="Processes" value={totals.process_count ?? '—'} />
                    <CategoryCard label="Decisions" value={totals.decision_count ?? '—'} />
                  </div>
                  <AutomationBars counts={metrics?.counts} />
                </div>
                <ReportCharts metrics={metrics} />
                </section>

                {/* Section 4: Process landscape */}
                <section className="report-section" aria-labelledby="landscape-heading">
                  <h2 id="landscape-heading">Process landscape</h2>
                  <div className="report-landscape">
                    {processWithSteps.map((proc) => (
                      <ProcessCard key={proc.id} proc={proc} />
                    ))}
                  </div>
                </section>

                {/* Section 5: Automation opportunities */}
                <section className="report-section" aria-labelledby="ops-heading">
                  <h2 id="ops-heading">Automation opportunities</h2>
                  <div className="report-section__markdown">
                    <ReactMarkdown>
                      {stripIdsFromMarkdown(
                        stripSectionHeading(
                          stripSectionHeading(narratives.operations_analysis || '', 'Operations Analysis'),
                          'Automation opportunities'
                        ) || narratives.operations_analysis || '*No automation analysis generated.*'
                      )}
                    </ReactMarkdown>
                  </div>
                </section>

                {/* Supplementary: step-level detail */}
                <section className="report-section report-section--supplementary" aria-labelledby="supp-heading">
                  <h2 id="supp-heading">Supplementary — Per-process step detail</h2>
                  {processWithSteps.map((proc) => (
                    <ProcessDeepDive key={proc.id} proc={proc} />
                  ))}
                </section>

                {/* CTA */}
                <section className="analyze-page__cta report-cta" aria-labelledby="cta-heading">
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
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
