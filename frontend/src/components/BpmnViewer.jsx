import { useRef, useEffect, useState, useCallback } from 'react'
import BpmnModeler from 'bpmn-js/lib/Modeler'
import { getBpmnXml, getBaselineBpmnXml } from '../services/api'
import 'diagram-js/assets/diagram-js.css'
import 'bpmn-js/dist/assets/bpmn-js.css'
import 'bpmn-js/dist/assets/bpmn-font/css/bpmn-embedded.css'
import './BpmnViewer.css'

/**
 * Interactable BPMN 2.0 editor (like BA Copilot's AI BPMN Process Map Generator).
 * Uses bpmn-js Modeler: select, drag, connect, palette, context pad, keyboard.
 * Toolbar: zoom, fit, download PNG, export BPMN XML.
 * @see https://github.com/bpmn-io/bpmn-js
 */
export default function BpmnViewer({ sessionId, refreshTrigger = 0, xmlOverride = '', onXmlChange, panelFooter }) {
  const containerRef = useRef(null)
  const paletteContainerRef = useRef(null)
  const modelerRef = useRef(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)

  const getModeler = useCallback(() => modelerRef.current, [])

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

  useEffect(() => {
    if (!sessionId) {
      setLoading(false)
      setError('No session')
      return
    }

    let cancelled = false
    setError(null)
    setLoading(true)

    const loadXml = xmlOverride?.trim()
      ? Promise.resolve(xmlOverride)
      : getBpmnXml(sessionId).catch(() => getBaselineBpmnXml())

    loadXml
      .then((xml) => {
        if (cancelled) return
        if (!xml?.trim()) {
          if (!cancelled) setError('Empty BPMN XML'), setLoading(false)
          return
        }
        const container = containerRef.current
        if (!container) {
          setError('Canvas not ready')
          setLoading(false)
          return
        }
        const modeler = new BpmnModeler({
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
        modelerRef.current = modeler

        const emitXmlChange = () => {
          if (typeof onXmlChange !== 'function') return
          modeler.saveXML({ format: true }).then(({ xml }) => onXmlChange(xml)).catch(() => {})
        }
        const onCommandStackChanged = () => {
          // Defer so React state updates don't run while bpmn-js is mid-update (avoids crash)
          queueMicrotask(() => {
            if (cancelled) return
            try {
              const stack = modeler.get('commandStack')
              setCanUndo(stack.canUndo())
              setCanRedo(stack.canRedo())
            } catch (_) {}
            emitXmlChange()
          })
        }
        modeler._commandStackHandler = onCommandStackChanged
        modeler.on('commandStack.changed', onCommandStackChanged)

        modeler
          .importXML(xml)
          .then((result) => {
            if (cancelled) return
            if (result?.warnings?.length) {
              console.warn('[BpmnViewer] import warnings:', result.warnings)
            }
            setError(null)
            // Ensure connection anchors are on shape borders, not centers
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
            modeler.get('canvas').zoom('fit-viewport')
            // Move palette inside the panel and keep a single instance
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

            setCanUndo(modeler.get('commandStack').canUndo())
            setCanRedo(modeler.get('commandStack').canRedo())

            syncPaletteIntoPanel()
            const observer = new MutationObserver(syncPaletteIntoPanel)
            const canvasContainer = containerRef.current
            if (canvasContainer) observer.observe(canvasContainer, { childList: true, subtree: true })
            modelerRef.current._paletteObserver = observer
            setLoading(false)
          })
          .catch((err) => {
            if (!cancelled) {
              setError(err?.message || 'Failed to load BPMN')
              setLoading(false)
            }
          })
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || 'Failed to fetch BPMN')
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
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
    }
  }, [sessionId, refreshTrigger, xmlOverride, onXmlChange])

  return (
    <div className="bpmn-viewer">
      {/* Right-side panel: one container (editor + palette) + chatbot under */}
      <aside className="bpmn-viewer__panel" aria-label="BPMN tools">
        <div className="bpmn-viewer__panel-inner">
          <div className="bpmn-viewer__panel-toolbar" role="toolbar" aria-label="BPMN editor actions">
            <span className="bpmn-viewer__toolbar-title">BPMN editor</span>
            <div className="bpmn-viewer__toolbar-group">
              <span className="bpmn-viewer__toolbar-label">Edit</span>
              <div className="bpmn-viewer__toolbar-actions">
                <button type="button" onClick={undo} title="Undo" disabled={loading || !!error || !canUndo}>
                  Undo
                </button>
                <button type="button" onClick={redo} title="Redo" disabled={loading || !!error || !canRedo}>
                  Redo
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
      {loading && (
        <div className="bpmn-viewer__loading">
          Loading BPMN…
        </div>
      )}
      {error && (
        <div className="bpmn-viewer__error" role="alert">
          {error}
        </div>
      )}
      <div
        ref={containerRef}
        className="bpmn-viewer__canvas"
        style={{ visibility: loading || error ? 'hidden' : 'visible' }}
      />
    </div>
  )
}
