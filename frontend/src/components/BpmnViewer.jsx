import { useRef, useEffect, useState, useCallback } from 'react'
import BpmnModeler from 'bpmn-js/lib/Modeler'
import { useBpmnXml } from '../hooks/useBpmnXml'
import { undoGraph } from '../services/api'
import 'diagram-js/assets/diagram-js.css'
import 'bpmn-js/dist/assets/bpmn-js.css'
import 'bpmn-js/dist/assets/bpmn-font/css/bpmn-embedded.css'
import './BpmnViewer.css'
import DataViewState from './DataViewState'

/**
 * Interactable BPMN 2.0 editor (like BA Copilot's AI BPMN Process Map Generator).
 * Uses bpmn-js Modeler: select, drag, connect, palette, context pad, keyboard.
 * Toolbar: zoom, fit, download PNG, export BPMN XML.
 * @see https://github.com/bpmn-io/bpmn-js
 */
export default function BpmnViewer({
  sessionId,
  processId = 'Process_Global',
  refreshTrigger = 0,
  panelFooter,
  onDrillDown,
  onRequestRefresh,
}) {
  const containerRef = useRef(null)
  const paletteContainerRef = useRef(null)
  const modelerRef = useRef(null)
  const isFirstLoadRef = useRef(true)
  const [initializing, setInitializing] = useState(false)
  const [viewerError, setViewerError] = useState(null)
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)
  const [undoBotPending, setUndoBotPending] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [modelerReady, setModelerReady] = useState(false)
  const { xml, loading: xmlLoading, error: xmlError } = useBpmnXml(sessionId, processId, refreshTrigger)

  const getModeler = useCallback(() => modelerRef.current, [])

  const handleUndoBot = useCallback(async () => {
    if (!sessionId || undoBotPending || !onRequestRefresh) return
    setUndoBotPending(true)
    try {
      await undoGraph(sessionId, { processId })
      onRequestRefresh()
    } catch (err) {
      if (err?.status !== 404) {
        console.warn('Undo bot failed', err)
      }
    } finally {
      setUndoBotPending(false)
    }
  }, [sessionId, processId, onRequestRefresh, undoBotPending])

  const undo = useCallback(() => {
    const modeler = getModeler()
    if (!modeler) return
    try {
      modeler.get('commandStack').undo()
    } catch (e) {
      console.warn('Undo failed', e)
    }
  }, [getModeler])

  const redo = useCallback(() => {
    const modeler = getModeler()
    if (!modeler) return
    try {
      modeler.get('commandStack').redo()
    } catch (e) {
      console.warn('Redo failed', e)
    }
  }, [getModeler])

  const zoom = useCallback((action) => {
    const modeler = getModeler()
    if (!modeler) return
    const canvas = modeler.get('canvas')
    if (action === 'fit') {
      canvas.zoom('fit-viewport')
      return
    }
    const current = canvas.zoom()
    if (action === 'in') canvas.zoom(Math.min(current * 1.25, 4))
    else if (action === 'out') canvas.zoom(Math.max(current / 1.25, 0.2))
  }, [getModeler])

  const downloadBpmn = useCallback(async () => {
    const modeler = getModeler()
    if (!modeler) return
    try {
      const { xml } = await modeler.saveXML({ format: true })
      const blob = new Blob([xml], { type: 'application/xml' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'process.bpmn'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Export BPMN failed', e)
    }
  }, [getModeler])

  const downloadPng = useCallback(() => {
    const modeler = getModeler()
    const container = containerRef.current
    if (!modeler || !container) return
    const svg = container.querySelector('svg')
    if (!svg) return
    try {
      const box = svg.getBBox()
      const scale = 2
      const w = Math.ceil(box.width * scale)
      const h = Math.ceil(box.height * scale)
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')
      ctx.fillStyle = '#1e1e1e'
      ctx.fillRect(0, 0, w, h)
      const svgData = new XMLSerializer().serializeToString(svg)
      const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' })
      const url = URL.createObjectURL(svgBlob)
      const img = new Image()
      img.onload = () => {
        ctx.drawImage(img, 0, 0, w, h)
        URL.revokeObjectURL(url)
        canvas.toBlob((blob) => {
          if (!blob) return
          const a = document.createElement('a')
          a.href = URL.createObjectURL(blob)
          a.download = 'process.png'
          a.click()
          URL.revokeObjectURL(a.href)
        }, 'image/png')
      }
      img.onerror = () => URL.revokeObjectURL(url)
      img.src = url
    } catch (e) {
      console.error('Export PNG failed', e)
    }
  }, [getModeler])

  // Destroy modeler when session or process changes (or unmount)
  useEffect(() => {
    return () => {
      const modeler = modelerRef.current
      if (modeler) {
        if (modeler._paletteObserver) {
          modeler._paletteObserver.disconnect()
        }
        if (modeler._commandStackHandler) {
          modeler.off('commandStack.changed', modeler._commandStackHandler)
          modeler._commandStackHandler = null
        }
        modeler.destroy()
      }
      if (paletteContainerRef.current) {
        paletteContainerRef.current.querySelectorAll('.djs-palette').forEach((el) => el.remove())
      }
      modelerRef.current = null
      isFirstLoadRef.current = true
      setModelerReady(false)
    }
  }, [sessionId, processId])

  // View mode: block create/delete (and label edit) when editMode is false.
  // We do NOT block directEditing.activate — it can break selection/zoom.
  // Per bpmn.io forum: use element.dblclick with higher priority + stopPropagation()
  // so the default label-editing handler never runs (https://forum.bpmn.io/t/how-to-remove-double-click-event-to-add-label-in-the-modeler/610).
  useEffect(() => {
    const modeler = modelerRef.current
    if (!modeler || editMode) return

    const block = () => false
    const events = [
      'commandStack.shape.delete.canExecute',
      'commandStack.elements.delete.canExecute',
      'commandStack.connection.delete.canExecute',
      'commandStack.shape.create.canExecute',
      'commandStack.connection.create.canExecute',
    ]
    const eventBus = modeler.get('eventBus')

    const preventLabelEditOnDblClick = (event) => {
      if (typeof event.stopPropagation === 'function') {
        event.stopPropagation()
      }
    }

    events.forEach((e) => eventBus.on(e, 2000, block))
    eventBus.on('element.dblclick', 2000, preventLabelEditOnDblClick)

    return () => {
      events.forEach((e) => eventBus.off(e, block))
      eventBus.off('element.dblclick', preventLabelEditOnDblClick)
    }
  }, [editMode, modelerReady])

  useEffect(() => {
    if (xmlLoading) return
    if (xmlError) return
    if (!xml?.trim()) return

    const container = containerRef.current
    if (!container) {
      setViewerError('Canvas not ready')
      return
    }

    const modeler = modelerRef.current
    const isUpdate = modeler != null

    if (isUpdate) {
      // Reuse existing modeler: preserve viewport, then import new XML
      const canvas = modeler.get('canvas')
      let prevViewbox = null
      try {
        prevViewbox = canvas.viewbox()
      } catch (e) {
        void e
      }

      setViewerError(null)
      setInitializing(true)
      modeler
        .importXML(xml)
        .then((result) => {
          if (result?.warnings?.length) {
            console.warn('[BpmnViewer] import warnings:', result.warnings)
          }
          try {
            const connectionDocking = modeler.get('connectionDocking', false)
            const elementRegistry = modeler.get('elementRegistry')
            const eventBus = modeler.get('eventBus')
            const connections = []
            if (connectionDocking && elementRegistry) {
              elementRegistry.forEach((element) => {
                if (element.waypoints && element.source && element.target) {
                  const cropped = connectionDocking.getCroppedWaypoints(element, element.source, element.target)
                  if (cropped && cropped.length >= 2) {
                    element.waypoints = cropped
                    connections.push(element)
                  }
                }
              })
              if (connections.length && eventBus) {
                eventBus.fire('elements.changed', { elements: connections })
              }
            }
          } catch (e) {
            console.warn('[BpmnViewer] connection dock crop:', e)
          }
          if (prevViewbox && typeof modeler.get('canvas').viewbox === 'function') {
            try {
              modeler.get('canvas').viewbox(prevViewbox)
            } catch (err) {
              void err
            }
          }
          setCanUndo(modeler.get('commandStack').canUndo())
          setCanRedo(modeler.get('commandStack').canRedo())
          setModelerReady(true)
        })
        .catch((err) => {
          setViewerError(err?.message || 'Failed to load BPMN')
        })
        .finally(() => {
          setInitializing(false)
        })
      return
    }

    // First load: create modeler, import, fit-viewport
    let cancelled = false
    const paletteContainer = paletteContainerRef.current
    setViewerError(null)
    setInitializing(true)

    /* Colors must match BpmnViewer.css theme (--bpmn-fill, --bpmn-stroke, --bpmn-text) */
    const newModeler = new BpmnModeler({
      container,
      width: '100%',
      height: '100%',
      position: 'relative',
      bpmnRenderer: {
        defaultFillColor: '#f5d4b8',
        defaultStrokeColor: '#c97d3a',
      },
      textRenderer: {
        defaultStyle: {
          fontFamily: 'Helvetica, Arial, sans-serif',
          fontSize: '14px',
          fontWeight: '700',
          fill: '#4a3020',
        },
      },
    })
    modelerRef.current = newModeler

    const onCommandStackChanged = () => {
      queueMicrotask(() => {
        if (cancelled) return
        try {
          const stack = newModeler.get('commandStack')
          setCanUndo(stack.canUndo())
          setCanRedo(stack.canRedo())
        } catch (err) {
          void err
        }
      })
    }
    newModeler._commandStackHandler = onCommandStackChanged
    newModeler.on('commandStack.changed', onCommandStackChanged)

    newModeler
      .importXML(xml)
      .then((result) => {
        if (cancelled) return
        if (result?.warnings?.length) {
          console.warn('[BpmnViewer] import warnings:', result.warnings)
        }
        setViewerError(null)
        try {
          const connectionDocking = newModeler.get('connectionDocking', false)
          const elementRegistry = newModeler.get('elementRegistry')
          const eventBus = newModeler.get('eventBus')
          const connections = []
          if (connectionDocking && elementRegistry) {
            elementRegistry.forEach((element) => {
              if (element.waypoints && element.source && element.target) {
                const cropped = connectionDocking.getCroppedWaypoints(element, element.source, element.target)
                if (cropped && cropped.length >= 2) {
                  element.waypoints = cropped
                  connections.push(element)
                }
              }
            })
            if (connections.length && eventBus) {
              eventBus.fire('elements.changed', { elements: connections })
            }
          }
        } catch (e) {
          console.warn('[BpmnViewer] connection dock crop:', e)
        }
        newModeler.get('canvas').zoom('fit-viewport')
        isFirstLoadRef.current = false
        setModelerReady(true)

        const syncPaletteIntoPanel = () => {
          const canvasContainer = containerRef.current
          const panelContainer = paletteContainerRef.current
          if (!canvasContainer || !panelContainer) return

          const paletteInCanvas = canvasContainer.querySelector('.djs-palette')
          if (paletteInCanvas) {
            panelContainer.appendChild(paletteInCanvas)
          }

          const palettesInPanel = panelContainer.querySelectorAll('.djs-palette')
          palettesInPanel.forEach((el, idx) => {
            if (idx < palettesInPanel.length - 1) el.remove()
          })
        }

        setCanUndo(newModeler.get('commandStack').canUndo())
        setCanRedo(newModeler.get('commandStack').canRedo())

        syncPaletteIntoPanel()
        const observer = new MutationObserver(syncPaletteIntoPanel)
        const canvasContainer = containerRef.current
        if (canvasContainer) observer.observe(canvasContainer, { childList: true, subtree: true })
        newModeler._paletteObserver = observer
      })
      .catch((err) => {
        if (!cancelled) {
          setViewerError(err?.message || 'Failed to load BPMN')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setInitializing(false)
        }
      })
  }, [xml, xmlLoading, xmlError, sessionId, processId])

  const loading = xmlLoading || initializing
  const error = xmlError || viewerError

  return (
    <div className={`bpmn-viewer ${editMode ? 'bpmn-viewer--edit-mode' : 'bpmn-viewer--view-mode'}`}>
      {/* Right-side panel: one container (editor + palette) + chatbot under */}
      <aside className="bpmn-viewer__panel" aria-label="BPMN tools">
        <div className="bpmn-viewer__panel-inner">
          <div className="bpmn-viewer__panel-toolbar" role="toolbar" aria-label="BPMN editor actions">
            <button
              type="button"
              className={`bpmn-viewer__mode-toggle ${editMode ? 'active' : ''}`}
              onClick={() => setEditMode((m) => !m)}
              title={editMode ? 'Switch to View mode' : 'Switch to Edit mode'}
            >
              {editMode ? 'Editing' : 'View only'}
            </button>
            <span className="bpmn-viewer__toolbar-title">{editMode ? 'Edit mode' : 'View mode'}</span>
            <div className="bpmn-viewer__toolbar-group">
              <span className="bpmn-viewer__toolbar-label">{editMode ? 'Edit' : 'Undo'}</span>
              <div className="bpmn-viewer__toolbar-actions">
                {editMode && (
                  <>
                    <button type="button" onClick={undo} title="Undo" disabled={loading || !!error || !canUndo}>
                      Undo
                    </button>
                    <button type="button" onClick={redo} title="Redo" disabled={loading || !!error || !canRedo}>
                      Redo
                    </button>
                  </>
                )}
                <button
                  type="button"
                  onClick={handleUndoBot}
                  title="Undo last bot change"
                  disabled={loading || !!error || undoBotPending || !onRequestRefresh}
                >
                  Undo (bot)
                </button>
              </div>
            </div>
            <div className="bpmn-viewer__toolbar-group">
              <span className="bpmn-viewer__toolbar-label">Zoom</span>
              <div className="bpmn-viewer__toolbar-actions">
                <button type="button" onClick={() => zoom('fit')} title="Fit to viewport">
                  Fit
                </button>
                <button type="button" onClick={() => zoom('in')} title="Zoom in">
                  +
                </button>
                <button type="button" onClick={() => zoom('out')} title="Zoom out">
                  −
                </button>
              </div>
            </div>
            <div className="bpmn-viewer__toolbar-group">
              <span className="bpmn-viewer__toolbar-label">Export</span>
              <div className="bpmn-viewer__toolbar-actions">
                <button type="button" onClick={downloadPng} title="Download as PNG" disabled={loading || !!error}>
                  PNG
                </button>
                <button type="button" onClick={downloadBpmn} title="Export BPMN XML" disabled={loading || !!error}>
                  BPMN
                </button>
              </div>
            </div>
          </div>
          <div ref={paletteContainerRef} className="bpmn-viewer__panel-palette" aria-label="BPMN elements" />
          {panelFooter && <div className="bpmn-viewer__panel-footer">{panelFooter}</div>}
        </div>
      </aside>
      <DataViewState
        loading={loading}
        error={error}
        loadingText="Loading BPMN…"
        loadingClassName="bpmn-viewer__loading"
        errorClassName="bpmn-viewer__error"
      />
      <div
        ref={containerRef}
        className="bpmn-viewer__canvas"
        style={{ visibility: loading || error ? 'hidden' : 'visible' }}
      />
    </div>
  )
}
