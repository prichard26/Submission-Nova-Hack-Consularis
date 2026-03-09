import { useState, useCallback, useRef, useEffect } from 'react'
import { renameProcess } from '../services/api'

export default function ProcessNameHeader({
  breadcrumb,
  processDisplayName,
  processId,
  sessionId,
  onDrillDown,
  onRequestRefresh,
}) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(processDisplayName)
  const [saving, setSaving] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    setEditValue(processDisplayName)
  }, [processDisplayName])

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  const handleSave = useCallback(async () => {
    const trimmed = (editValue || '').trim()
    if (trimmed === processDisplayName || !sessionId || !onRequestRefresh) {
      setEditing(false)
      return
    }
    setSaving(true)
    try {
      await renameProcess(sessionId, processId, trimmed)
      onRequestRefresh()
      setEditing(false)
    } catch (err) {
      console.warn('Rename process failed', err)
    } finally {
      setSaving(false)
    }
  }, [editValue, processDisplayName, sessionId, processId, onRequestRefresh])

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        handleSave()
      }
      if (e.key === 'Escape') {
        setEditValue(processDisplayName)
        setEditing(false)
      }
    },
    [handleSave, processDisplayName],
  )

  return (
    <section className="panel-info">
      <nav className="panel-info__path" aria-label="Process path">
        {breadcrumb.slice(0, -1).map((part) => (
          <span key={part.id} className="panel-info__path-item">
            <button className="panel-info__path-link" onClick={() => onDrillDown?.(part.id)}>{part.name}</button>
            <span className="panel-info__path-sep">›</span>
          </span>
        ))}
        <span className="panel-info__current">
          {editing ? (
            <input
              ref={inputRef}
              type="text"
              className="panel-info__name-input"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onBlur={handleSave}
              onKeyDown={handleKeyDown}
              disabled={saving}
              aria-label="Process name"
            />
          ) : (
            <>
              <span className="panel-info__name-display" title={processDisplayName}>{processDisplayName}</span>
              {sessionId && onRequestRefresh && (
              <button
                type="button"
                className="panel-info__name-edit"
                onClick={() => setEditing(true)}
                title="Edit process name"
                aria-label="Edit process name"
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M7 2L10 5L4 11H1V8L7 2Z" />
                </svg>
              </button>
              )}
            </>
          )}
        </span>
      </nav>
    </section>
  )
}
