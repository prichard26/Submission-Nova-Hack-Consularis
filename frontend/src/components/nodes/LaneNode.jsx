/** React Flow custom node for lanes: process name with optional inline rename (useInlineRename + ProcessCanvasContext). */
import { memo, useContext } from 'react'
import { ProcessCanvasContext } from '../../contexts/ProcessCanvasContext'
import { useInlineRename } from '../../hooks/useInlineRename'
import './LaneNode.css'

function LaneNode({ data, style = {} }) {
  const title = data.processName ?? data.label ?? ''
  const { width, height, ...rest } = style
  const { sessionId, processId, onRequestRefresh } = useContext(ProcessCanvasContext) || {}
  const canRename = Boolean(title && sessionId && processId && onRequestRefresh && data.processName)

  const {
    editing, editValue, setEditValue, saving, inputRef, startEditing, handleSave, handleKeyDown,
  } = useInlineRename({ currentName: title, sessionId, processId, onRequestRefresh })

  return (
    <div className="lane-node" style={{ width, height, ...rest }}>
      {title && (
        <div className="lane-node__title">
          {canRename && editing ? (
            <input
              ref={inputRef}
              type="text"
              className="lane-node__title-input"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onBlur={handleSave}
              onKeyDown={handleKeyDown}
              disabled={saving}
              aria-label="Process name"
              onClick={(e) => e.stopPropagation()}
            />
          ) : canRename ? (
            <button
              type="button"
              className="lane-node__title-btn"
              onClick={(e) => {
                e.stopPropagation()
                startEditing()
              }}
              title="Click to edit process name"
              aria-label="Edit process name"
            >
              {title}
            </button>
          ) : (
            <span>{title}</span>
          )}
        </div>
      )}
    </div>
  )
}

export default memo(LaneNode)
