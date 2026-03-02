import { useState, useCallback, useMemo, useEffect } from 'react'
import AureliusChat from '../components/AureliusChat'
import GraphCanvas from '../components/GraphCanvas'
import { getProcessTree } from '../services/api'
import './Dashboard.css'

export default function Dashboard({ companyName, sector = 'pharmacy' }) {
  const [bpmnRefreshTrigger, setBpmnRefreshTrigger] = useState(0)
  const [chatOpen, setChatOpen] = useState(false)
  const [graphViewMode, setGraphViewMode] = useState('custom')
  const [processId, setProcessId] = useState('Process_Global')
  const [processTree, setProcessTree] = useState([])
  const sectorLabel = useMemo(
    () => `${sector.charAt(0).toUpperCase()}${sector.slice(1)}`,
    [sector],
  )

  const handleExternalGraphUpdate = useCallback(() => {
    setBpmnRefreshTrigger((t) => t + 1)
  }, [])

  useEffect(() => {
    if (!companyName) return
    let cancelled = false
    getProcessTree(companyName)
      .then((payload) => {
        if (cancelled) return
        const next = Array.isArray(payload?.processes) ? payload.processes : []
        setProcessTree(next)
      })
      .catch(() => {
        if (!cancelled) setProcessTree([])
      })
    return () => {
      cancelled = true
    }
  }, [companyName, bpmnRefreshTrigger])

  const processOptions = useMemo(() => {
    const out = []
    const walk = (nodes, depth = 0) => {
      nodes.forEach((n) => {
        out.push({
          process_id: n.process_id,
          label: `${'  '.repeat(depth)}${n.name || n.process_id}`,
          name: n.name || n.process_id,
          parent_id: n.parent_id || null,
        })
        if (Array.isArray(n.children) && n.children.length) {
          walk(n.children, depth + 1)
        }
      })
    }
    walk(processTree)
    return out
  }, [processTree])

  const processById = useMemo(() => {
    const m = new Map()
    processOptions.forEach((p) => m.set(p.process_id, p))
    return m
  }, [processOptions])

  const breadcrumb = useMemo(() => {
    const out = []
    let cursor = processById.get(processId)
    while (cursor) {
      out.unshift({ process_id: cursor.process_id, name: cursor.name })
      cursor = cursor.parent_id ? processById.get(cursor.parent_id) : null
    }
    return out
  }, [processById, processId])

  const panelFooter = useMemo(() => {
    if (graphViewMode !== 'bpmn') return null
    return (
      <AureliusChat
        sessionId={companyName}
        processId={processId}
        onGraphUpdate={handleExternalGraphUpdate}
        onClose={() => setChatOpen(false)}
      />
    )
  }, [graphViewMode, companyName, processId, handleExternalGraphUpdate])

  return (
    <div className="dashboard">
      {/* ── Top bar ── */}
      <header className="dashboard__topbar">
        <div className="dashboard__topbar-left">
          <span className="dashboard__logo">
            Consularis<span className="dashboard__logo-dot">.</span>
          </span>
          <span className="dashboard__company">{companyName}</span>
          <span className="dashboard__badge">{sectorLabel}</span>
          <select value={processId} onChange={(e) => setProcessId(e.target.value)} aria-label="Current process">
            {processOptions.length === 0 && <option value="Process_Global">Global</option>}
            {processOptions.map((p) => (
              <option key={p.process_id} value={p.process_id}>
                {p.label}
              </option>
            ))}
          </select>
          {breadcrumb.length > 0 && (
            <nav aria-label="Process breadcrumb">
              {breadcrumb.map((item, idx) => (
                <button
                  key={item.process_id}
                  type="button"
                  onClick={() => setProcessId(item.process_id)}
                >
                  {idx > 0 ? ` / ${item.name}` : item.name}
                </button>
              ))}
            </nav>
          )}
          <div className="dashboard__view-toggle" role="tablist" aria-label="Graph view mode">
            <button
              className={`view-toggle-btn ${graphViewMode === 'custom' ? 'view-toggle-btn--active' : ''}`}
              onClick={() => setGraphViewMode('custom')}
              role="tab"
              aria-selected={graphViewMode === 'custom'}
            >
              Process
            </button>
            <button
              className={`view-toggle-btn ${graphViewMode === 'bpmn' ? 'view-toggle-btn--active' : ''}`}
              onClick={() => setGraphViewMode('bpmn')}
              role="tab"
              aria-selected={graphViewMode === 'bpmn'}
            >
              BPMN
            </button>
          </div>
        </div>

        <button
          className={`dashboard__chat-toggle ${chatOpen ? 'dashboard__chat-toggle--active' : ''}`}
          onClick={() => setChatOpen(o => !o)}
        >
          <span>🤖</span> Aurelius
        </button>
      </header>

      {/* ── Main canvas ── */}
      <div className="dashboard__canvas">
        <GraphCanvas
          viewMode={graphViewMode}
          sessionId={companyName}
          processId={processId}
          refreshTrigger={bpmnRefreshTrigger}
          xmlOverride=""
          panelFooter={panelFooter}
          onDrillDown={(nextProcessId) => setProcessId(nextProcessId)}
        />
      </div>

      {/* ── Aurelius chat panel (overlay when not in BPMN view) ── */}
      {chatOpen && graphViewMode !== 'bpmn' && (
        <AureliusChat
          sessionId={companyName}
          processId={processId}
          onGraphUpdate={handleExternalGraphUpdate}
          onClose={() => setChatOpen(false)}
          isOverlay
        />
      )}
    </div>
  )
}
