import { useEffect } from 'react'
import { useInlineRename } from '../hooks/useInlineRename'

export default function ProcessNameHeader({
  breadcrumb,
  processDisplayName,
  processId,
  sessionId,
  onDrillDown,
  onRequestRefresh,
  beginRenameTrigger = 0,
}) {
  const {
    editing, editValue, setEditValue, saving, inputRef, startEditing, handleSave, handleKeyDown,
  } = useInlineRename({ currentName: processDisplayName, sessionId, processId, onRequestRefresh })

  useEffect(() => {
    if (beginRenameTrigger > 0) startEditing()
  }, [beginRenameTrigger, startEditing])

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
    }
  }, [editing, inputRef])

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
                onClick={startEditing}
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
