import { useState, useCallback, useRef, useEffect } from 'react'
import { renameProcess } from '../services/api'

/**
 * Inline-rename logic for LaneNode lane titles.
 */
export function useInlineRename({ currentName, sessionId, processId, onRequestRefresh }) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(currentName)
  const [saving, setSaving] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    setEditValue(currentName)
  }, [currentName])

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  const handleSave = useCallback(async () => {
    const trimmed = (editValue || '').trim()
    if (trimmed === currentName || !sessionId || !onRequestRefresh) {
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
  }, [editValue, currentName, sessionId, processId, onRequestRefresh])

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        handleSave()
      }
      if (e.key === 'Escape') {
        setEditValue(currentName)
        setEditing(false)
      }
    },
    [handleSave, currentName],
  )

  const startEditing = useCallback(() => setEditing(true), [])

  return { editing, editValue, setEditValue, saving, inputRef, startEditing, handleSave, handleKeyDown }
}
