import { useCallback } from 'react'

export default function EdgeEditorModal({
  edgeEditor,
  edgeEditorSaving,
  onClose,
  onSave,
  onChangeLabel,
}) {
  const handleKeyDown = useCallback(
    (event) => {
      if (event.key === 'Enter') {
        event.preventDefault()
        onSave()
      } else if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    },
    [onClose, onSave],
  )

  if (!edgeEditor) return null

  return (
    <div className="process-canvas__edge-editor-backdrop" onClick={onClose}>
      <div className="process-canvas__edge-editor" onClick={(event) => event.stopPropagation()}>
        <div className="process-canvas__edge-editor-title">{edgeEditor.mode === 'create' ? 'New connection label' : 'Edit connection label'}</div>
        <input
          className="process-canvas__edge-editor-input"
          autoFocus
          placeholder="Enter edge text (optional)"
          value={edgeEditor.label}
          onChange={(event) => onChangeLabel(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="process-canvas__edge-editor-actions">
          <button type="button" onClick={onClose} disabled={edgeEditorSaving}>Cancel</button>
          <button type="button" onClick={onSave} disabled={edgeEditorSaving}>{edgeEditorSaving ? 'Saving…' : 'Save'}</button>
        </div>
      </div>
    </div>
  )
}
