import { useCallback, useEffect, useRef, useMemo, useState } from 'react'
import {
  ReactFlow,
  MiniMap,
  Background,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  useReactFlow,
  MarkerType,
  ConnectionLineType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { toPng } from 'html-to-image'
import { useProcessGraph } from '../hooks/useProcessGraph'
import { toReactFlowData, autoArrangeNodes } from '../services/graphTransform'
import { nodeTypes } from './nodes/nodeTypes'
import {
  undoGraph,
  redoGraph,
  resetToBaseline,
  updatePositions,
  createNode,
  createSubprocessPage,
  createEdge,
  updateEdge,
  deleteEdge,
  deleteNode,
  exportBpmnXml,
} from '../services/api'
import DataViewState from './DataViewState'
import './ProcessCanvas.css'

const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.userAgent)

function Canvas({
  sessionId,
  processId = 'Process_Global',
  refreshTrigger = 0,
  onStepSelect,
  onDrillDown,
  onRequestRefresh,
  panelFooter,
  workspaceProcesses = {},
  viewMode,
  onViewModeChange,
}) {
  const { screenToFlowPosition, zoomIn, zoomOut, fitView } = useReactFlow()
  const { graph, loading, error } = useProcessGraph(sessionId, processId, refreshTrigger)
  const [undoBotPending, setUndoBotPending] = useState(false)
  const [redoPending, setRedoPending] = useState(false)
  const [resetPending, setResetPending] = useState(false)
  const [panelWidth, setPanelWidth] = useState(340)
  const [resizing, setResizing] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [flowFocused, setFlowFocused] = useState(false)
  const [pendingAddType, setPendingAddType] = useState(null)
  const [subprocessStatus, setSubprocessStatus] = useState('')
  const [edgeEditor, setEdgeEditor] = useState(null)
  const [edgeEditorSaving, setEdgeEditorSaving] = useState(false)
  const [processDisplayName, setProcessDisplayName] = useState('')
  const [tbPos, setTbPos] = useState({ x: 16, y: 16 })
  const [tbLayout, setTbLayout] = useState('vertical')
  const [tbCollapsed, setTbCollapsed] = useState(false)
  const [tbDragging, setTbDragging] = useState(false)
  const canvasRef = useRef(null)
  const tbRef = useRef(null)
  const flowWrapper = useRef(null)
  const panelRef = useRef(null)
  const posTimerRef = useRef(null)
  const pendingPositions = useRef({})
  const tbDragStart = useRef({ mx: 0, my: 0, ox: 0, oy: 0, moved: false })

  useEffect(() => {
    if (!resizing) return
    function onMove(e) {
      if (!panelRef.current) return
      const container = panelRef.current.parentElement
      if (!container) return
      const rect = container.getBoundingClientRect()
      const newWidth = rect.right - e.clientX
      setPanelWidth(() => Math.min(720, Math.max(280, newWidth)))
    }
    function onUp() { setResizing(false) }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [resizing])

  useEffect(() => {
    if (!tbDragging) return
    function onMove(e) {
      const dx = e.clientX - tbDragStart.current.mx
      const dy = e.clientY - tbDragStart.current.my
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) tbDragStart.current.moved = true
      if (tbDragStart.current.moved) {
        let nx = tbDragStart.current.ox + dx
        let ny = tbDragStart.current.oy + dy
        const container = canvasRef.current
        const tb = tbRef.current
        if (container && tb) {
          const cw = container.clientWidth
          const ch = container.clientHeight
          const tw = tb.offsetWidth
          const th = tb.offsetHeight
          nx = Math.max(0, Math.min(nx, cw - tw))
          ny = Math.max(0, Math.min(ny, ch - th))
        }
        setTbPos({ x: nx, y: ny })
      }
    }
    function onUp() {
      const didMove = tbDragStart.current.moved
      setTbDragging(false)
      if (!didMove) setTbCollapsed((prev) => !prev)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [tbDragging])

  const onTbGrab = useCallback((e) => {
    e.preventDefault()
    tbDragStart.current = { mx: e.clientX, my: e.clientY, ox: tbPos.x, oy: tbPos.y, moved: false }
    setTbDragging(true)
  }, [tbPos])

  useEffect(() => {
    if (!subprocessStatus) return
    const t = setTimeout(() => setSubprocessStatus(''), 3500)
    return () => clearTimeout(t)
  }, [subprocessStatus])

  const { initialNodes, initialEdges } = useMemo(() => {
    if (!graph) return { initialNodes: [], initialEdges: [] }
    const { nodes, edges } = toReactFlowData(graph, workspaceProcesses)
    return { initialNodes: nodes, initialEdges: edges }
  }, [graph, workspaceProcesses])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  useEffect(() => {
    const entry = workspaceProcesses[processId]
    const name = entry?.name || processId.replace(/^Process_/, '').replace(/_/g, ' ')
    setProcessDisplayName(name)
  }, [processId, workspaceProcesses])

  const stats = useMemo(() => ({
    steps: nodes.filter((n) => n.type === 'step').length,
    decisions: nodes.filter((n) => n.type === 'decision').length,
    subprocesses: nodes.filter((n) => n.type === 'subprocess').length,
    connections: edges.length,
    lanes: graph?.lanes?.length || 0,
  }), [nodes, edges, graph])

  const breadcrumb = useMemo(() => {
    const parts = []
    let current = processId
    while (current) {
      const info = workspaceProcesses[current]
      if (!info) break
      parts.unshift({ id: current, name: info.name })
      const segments = (info.path || '').split('/').filter(Boolean)
      const parent = segments.length >= 2 ? segments[segments.length - 2] : null
      if (!parent || parent === current) break
      current = parent
    }
    return parts
  }, [processId, workspaceProcesses])

  const handleNodesChange = useCallback(
    (changes) => {
      onNodesChange(changes)
      const posChanges = changes.filter((c) => c.type === 'position' && c.position)
      if (posChanges.length === 0) return
      for (const c of posChanges) {
        if (c.id.startsWith('lane_')) continue
        pendingPositions.current[c.id] = { x: Math.round(c.position.x), y: Math.round(c.position.y) }
      }
      clearTimeout(posTimerRef.current)
      posTimerRef.current = setTimeout(() => {
        const positions = { ...pendingPositions.current }
        pendingPositions.current = {}
        if (Object.keys(positions).length > 0) {
          updatePositions(sessionId, processId, positions).catch((err) => {
            console.warn('Position update failed', err)
          })
        }
      }, 500)
    },
    [onNodesChange, sessionId, processId],
  )

  const handleNodeClick = useCallback(
    (_event, node) => {
      setSelectedNodeId(node.id)
      if (node.type === 'subprocess') {
        if (onDrillDown && node.data?.called_element) {
          onDrillDown(node.data.called_element)
          return
        }
        if (onStepSelect) {
          onStepSelect(node.data)
        }
        return
      }
      if ((node.type === 'step' || node.type === 'decision') && onStepSelect) {
        onStepSelect(node.data)
      }
    },
    [onStepSelect, onDrillDown],
  )

  const handleUndoBot = useCallback(async () => {
    if (!sessionId || undoBotPending || !onRequestRefresh) return
    setUndoBotPending(true)
    try {
      await undoGraph(sessionId, { processId })
      onRequestRefresh()
    } catch (err) {
      if (err?.status !== 404) console.warn('Undo bot failed', err)
    } finally {
      setUndoBotPending(false)
    }
  }, [sessionId, processId, onRequestRefresh, undoBotPending])

  const handleRedo = useCallback(async () => {
    if (!sessionId || redoPending || !onRequestRefresh) return
    setRedoPending(true)
    try {
      await redoGraph(sessionId, { processId })
      onRequestRefresh()
    } catch (err) {
      if (err?.status !== 404) console.warn('Redo failed', err)
    } finally {
      setRedoPending(false)
    }
  }, [sessionId, processId, onRequestRefresh, redoPending])

  const handleReset = useCallback(async () => {
    if (!sessionId || resetPending || !onRequestRefresh) return
    if (!window.confirm('Reset to original graph? All changes will be lost.')) return
    setResetPending(true)
    try {
      await resetToBaseline(sessionId, { processId })
      onRequestRefresh()
    } catch (err) {
      console.warn('Reset failed', err)
    } finally {
      setResetPending(false)
    }
  }, [sessionId, processId, onRequestRefresh, resetPending])

  const handleAddNode = useCallback((type) => {
    setPendingAddType(type)
    setSelectedNodeId(null)
  }, [])

  const handlePlaceNode = useCallback(
    async (event) => {
      if (!pendingAddType || !graph?.lanes?.length) {
        setSelectedNodeId(null)
        return
      }
      const laneId = graph.lanes[0].id
      const name =
        pendingAddType === 'step'
          ? 'New Step'
          : pendingAddType === 'decision'
            ? 'New Decision'
            : 'New Subprocess'
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
      try {
        const createdNode = await createNode(sessionId, processId, laneId, name, pendingAddType, position)
        if (pendingAddType === 'subprocess' && createdNode?.id) {
          try {
            const created = await createSubprocessPage(
              sessionId,
              processId,
              createdNode.id,
              createdNode.name || name,
            )
            const linkedProcessId = created?.process_id
            setSubprocessStatus(
              linkedProcessId
                ? `Subprocess page created and linked (${linkedProcessId}).`
                : 'Subprocess page linked.',
            )
          } catch (linkErr) {
            console.warn('Subprocess page creation failed', linkErr)
            setSubprocessStatus('Subprocess node created, but page linking failed.')
          }
        } else {
          setSubprocessStatus('')
        }
        setPendingAddType(null)
        onRequestRefresh?.()
      } catch (err) {
        console.warn('Create node failed', err)
      }
    },
    [pendingAddType, graph, screenToFlowPosition, sessionId, processId, onRequestRefresh],
  )

  const handleAutoArrange = useCallback(async () => {
    const { nodes: nextNodes, positions } = autoArrangeNodes(nodes, edges)
    if (Object.keys(positions).length === 0) return
    setNodes(nextNodes)
    try {
      await updatePositions(sessionId, processId, positions)
      onRequestRefresh?.()
    } catch (err) {
      console.warn('Auto-arrange position update failed', err)
    }
  }, [nodes, edges, sessionId, processId, setNodes, onRequestRefresh])

  const handleConnect = useCallback(
    (connection) => {
      if (!connection?.source || !connection?.target) return
      setEdgeEditor({
        mode: 'create',
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle || null,
        targetHandle: connection.targetHandle || null,
        label: '',
      })
    },
    [],
  )

  const handleEdgeDoubleClick = useCallback(
    (_event, edge) => {
      setEdgeEditor({
        mode: 'edit',
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle || null,
        targetHandle: edge.targetHandle || null,
        label: edge.label || '',
      })
    },
    [],
  )

  const handleEdgeEditorClose = useCallback(() => {
    if (edgeEditorSaving) return
    setEdgeEditor(null)
  }, [edgeEditorSaving])

  const handleEdgeEditorSave = useCallback(async () => {
    if (!edgeEditor || edgeEditorSaving) return
    setEdgeEditorSaving(true)
    try {
      if (edgeEditor.mode === 'create') {
        await createEdge(sessionId, processId, edgeEditor.source, edgeEditor.target, edgeEditor.label || '', {
          sourceHandle: edgeEditor.sourceHandle,
          targetHandle: edgeEditor.targetHandle,
        })
      } else {
        await updateEdge(sessionId, processId, edgeEditor.source, edgeEditor.target, { label: edgeEditor.label || '' })
      }
      setEdgeEditor(null)
      onRequestRefresh?.()
    } catch (err) {
      console.warn('Edge label save failed', err)
    } finally {
      setEdgeEditorSaving(false)
    }
  }, [edgeEditor, edgeEditorSaving, sessionId, processId, onRequestRefresh])

  const handleEdgesDelete = useCallback(
    async (deletedEdges) => {
      for (const edge of deletedEdges) {
        try {
          await deleteEdge(sessionId, processId, edge.source, edge.target)
        } catch (err) {
          console.warn('Delete edge failed', err)
        }
      }
      onRequestRefresh?.()
    },
    [sessionId, processId, onRequestRefresh],
  )

  const handleNodesDelete = useCallback(
    async (deletedNodes) => {
      const nonLaneNodes = deletedNodes.filter((node) => !node.id.startsWith('lane_'))
      for (const node of nonLaneNodes) {
        if (node.type === 'start' || node.type === 'end') continue
        try {
          await deleteNode(sessionId, processId, node.id)
        } catch (err) {
          console.warn('Delete node failed', err)
        }
      }
      onRequestRefresh?.()
    },
    [sessionId, processId, onRequestRefresh],
  )

  const handleReconnect = useCallback(
    async (oldEdge, newConnection) => {
      if (!newConnection?.source || !newConnection?.target) return
      try {
        const reconnectsSamePair =
          oldEdge.source === newConnection.source && oldEdge.target === newConnection.target
        await createEdge(sessionId, processId, newConnection.source, newConnection.target, '', {
          sourceHandle: newConnection.sourceHandle,
          targetHandle: newConnection.targetHandle,
        })
        if (!reconnectsSamePair) {
          await deleteEdge(sessionId, processId, oldEdge.source, oldEdge.target)
        }
        onRequestRefresh?.()
      } catch (err) {
        console.warn('Reconnect edge failed', err)
      }
    },
    [sessionId, processId, onRequestRefresh],
  )

  const handleExportPng = useCallback(async () => {
    if (!flowWrapper.current) return
    try {
      const dataUrl = await toPng(flowWrapper.current, { backgroundColor: '#ffffff' })
      const link = document.createElement('a')
      link.download = `${processId}.png`
      link.href = dataUrl
      link.click()
    } catch (err) {
      console.warn('PNG export failed', err)
    }
  }, [processId])

  const handleExportBpmn = useCallback(async () => {
    try {
      const xml = await exportBpmnXml(sessionId, { processId })
      const blob = new Blob([xml], { type: 'application/xml' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.download = `${processId}.bpmn`
      link.href = url
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.warn('BPMN export failed', err)
    }
  }, [sessionId, processId])

  useEffect(() => {
    function onKeyDown(e) {
      const active = document.activeElement
      const tag = active?.tagName?.toLowerCase()
      const isTypingTarget = tag === 'textarea' || tag === 'input' || active?.isContentEditable
      if (isTypingTarget || !flowFocused || loading || error) return
      const key = e.key.toLowerCase()
      const metaOrCtrl = e.metaKey || e.ctrlKey
      if (metaOrCtrl && key === 'z') {
        e.preventDefault()
        if (e.shiftKey) { handleRedo() } else { handleUndoBot() }
        return
      }
      if (key === 's') { e.preventDefault(); handleAddNode('step') }
      else if (key === 'd') { e.preventDefault(); handleAddNode('decision') }
      else if (key === 'p') { e.preventDefault(); handleAddNode('subprocess') }
      else if (key === 'a') { e.preventDefault(); handleAutoArrange() }
      else if (key === 'escape') { setPendingAddType(null) }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [flowFocused, loading, error, handleAddNode, handleAutoArrange, handleUndoBot, handleRedo])

  const disabled = loading || !!error
  const undoTip = 'Undo \u00b7 ' + (IS_MAC ? '\u2318Z' : 'Ctrl+Z')
  const redoTip = 'Redo \u00b7 ' + (IS_MAC ? '\u2318\u21e7Z' : 'Ctrl+\u21e7+Z')
  const tbCls = 'floating-toolbar floating-toolbar--' + tbLayout + (tbCollapsed ? ' floating-toolbar--collapsed' : '')

  return (
    <div className="process-canvas" ref={canvasRef}>
      {/* ── Floating draggable toolbar ── */}
      <div ref={tbRef} className={tbCls} style={{ left: tbPos.x, top: tbPos.y, visibility: loading || error ? 'hidden' : 'visible' }}>
        {tbCollapsed ? (
          <div className="ftb__toggle" onMouseDown={onTbGrab} data-tip="Expand toolbar">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg>
          </div>
        ) : (
          <>
            <div className="ftb__toggle" onMouseDown={onTbGrab} data-tip="Drag to move · Click to collapse">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M3 4h10M3 8h10M3 12h10" /></svg>
            </div>
            <span className="ftb__sep" />
            <button type="button" className="ftb__btn" onClick={() => zoomIn()} data-tip="Zoom in">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg>
            </button>
            <button type="button" className="ftb__btn" onClick={() => zoomOut()} data-tip="Zoom out">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true"><path d="M3 8h10" /></svg>
            </button>
            <button type="button" className="ftb__btn" onClick={() => fitView()} data-tip="Fit to view">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2 6V3.5A1.5 1.5 0 0 1 3.5 2H6M10 2h2.5A1.5 1.5 0 0 1 14 3.5V6M14 10v2.5a1.5 1.5 0 0 1-1.5 1.5H10M6 14H3.5A1.5 1.5 0 0 1 2 12.5V10" /></svg>
            </button>
            <span className="ftb__sep" />
            <button type="button" className={'ftb__btn' + (pendingAddType === 'step' ? ' ftb__btn--active' : '')} onClick={() => handleAddNode('step')} disabled={disabled} data-tip="Add Step &middot; S">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="2" y="3" width="12" height="10" rx="2" /><path d="M8 6v4M6 8h4" strokeLinecap="round" /></svg>
            </button>
            <button type="button" className={'ftb__btn' + (pendingAddType === 'decision' ? ' ftb__btn--active' : '')} onClick={() => handleAddNode('decision')} disabled={disabled} data-tip="Add Decision &middot; D">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M8 2L14 8L8 14L2 8Z" strokeLinejoin="round" /><path d="M8 6v4M6 8h4" strokeLinecap="round" /></svg>
            </button>
            <button type="button" className={'ftb__btn' + (pendingAddType === 'subprocess' ? ' ftb__btn--active' : '')} onClick={() => handleAddNode('subprocess')} disabled={disabled} data-tip="Add Subprocess &middot; P">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="1.5" y="2.5" width="9" height="7" rx="1.5" /><rect x="5.5" y="6.5" width="9" height="7" rx="1.5" /></svg>
            </button>
            <span className="ftb__sep" />
            <button type="button" className="ftb__btn" onClick={handleAutoArrange} disabled={disabled || !onRequestRefresh} data-tip="Auto-arrange &middot; A">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="2" y="2" width="4" height="4" rx="1" /><rect x="10" y="2" width="4" height="4" rx="1" /><rect x="2" y="10" width="4" height="4" rx="1" /><rect x="10" y="10" width="4" height="4" rx="1" /></svg>
            </button>
            <button type="button" className="ftb__btn" onClick={handleUndoBot} disabled={disabled || undoBotPending || !onRequestRefresh} data-tip={undoTip}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 6h7a3 3 0 0 1 0 6H8" /><path d="M6 3L3 6l3 3" /></svg>
            </button>
            <button type="button" className="ftb__btn" onClick={handleRedo} disabled={disabled || redoPending || !onRequestRefresh} data-tip={redoTip}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M13 6H6a3 3 0 0 0 0 6h2" /><path d="M10 3l3 3-3 3" /></svg>
            </button>
            <button type="button" className="ftb__btn" onClick={handleReset} disabled={disabled || resetPending || !onRequestRefresh} data-tip="Reset to baseline">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2.5 8a5.5 5.5 0 0 1 9.3-4" /><path d="M13.5 8a5.5 5.5 0 0 1-9.3 4" /><path d="M11.5 2l.3 2.2-2.2.3" /><path d="M4.5 14l-.3-2.2 2.2-.3" /></svg>
            </button>
            <span className="ftb__sep" />
            <button type="button" className="ftb__btn" onClick={handleExportPng} disabled={disabled} data-tip="Export PNG">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="2" y="2" width="12" height="12" rx="2" /><circle cx="6" cy="6" r="1.5" fill="currentColor" stroke="none" /><path d="M2 11l3.5-4 2.5 3 2-2 4 3" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
            <button type="button" className="ftb__btn" onClick={handleExportBpmn} disabled={disabled} data-tip="Export BPMN">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" aria-hidden="true"><path d="M4 2h5.5L13 5.5V14H4V2Z" /><path d="M9.5 2v3.5H13" /><path d="M6.5 9.5L8 11l1.5-1.5" strokeLinecap="round" /></svg>
            </button>
            <span className="ftb__sep" />
            <button type="button" className="ftb__btn ftb__btn--meta" onClick={() => setTbLayout((l) => l === 'vertical' ? 'horizontal' : 'vertical')} data-tip={tbLayout === 'vertical' ? 'Horizontal layout' : 'Vertical layout'}>
              {tbLayout === 'vertical' ? (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2 8h12M10 5l3 3-3 3M6 11l-3-3 3-3" /></svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 2v12M5 10l3 3 3-3M11 6l-3-3-3 3" /></svg>
              )}
            </button>
          </>
        )}
      </div>

      {/* ── Right panel ── */}
      <aside ref={panelRef} className="process-canvas__panel" style={{ width: panelWidth, minWidth: panelWidth }}>
        <div className="process-canvas__panel-inner">
          {pendingAddType && (
            <div className="process-canvas__place-hint">Click on canvas to place the new <strong>{pendingAddType}</strong></div>
          )}
          {!pendingAddType && subprocessStatus && (
            <div className="process-canvas__subprocess-status">{subprocessStatus}</div>
          )}

          {/* Action row — high-power buttons */}
          <div className="panel-actions-row">
            <button className="panel-actions-row__btn" onClick={() => onViewModeChange?.('landscape')}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="1.5" y="3" width="5" height="4.5" rx="1" /><rect x="9.5" y="3" width="5" height="4.5" rx="1" /><rect x="5.5" y="9" width="5" height="4.5" rx="1" /></svg>
              Landscape
            </button>
            <button className="panel-actions-row__btn panel-actions-row__btn--accent" disabled>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 1v6M5 4l3-3 3 3" /><path d="M2 8.5a6 6 0 0 0 12 0" /><circle cx="8" cy="12" r="1" fill="currentColor" /></svg>
              Analyze
            </button>
          </div>

          {/* Breadcrumb navigation */}
          {breadcrumb.length > 1 && (
            <nav className="panel-breadcrumb" aria-label="Process path">
              {breadcrumb.map((p, i) => (
                <span key={p.id} className="panel-breadcrumb__item">
                  {i > 0 && <span className="panel-breadcrumb__sep">›</span>}
                  {i < breadcrumb.length - 1 ? (
                    <button className="panel-breadcrumb__link" onClick={() => onDrillDown?.(p.id)}>{p.name}</button>
                  ) : (
                    <span className="panel-breadcrumb__current">{p.name}</span>
                  )}
                </span>
              ))}
            </nav>
          )}

          {/* Page info */}
          <section className="panel-info">
            <div className="panel-info__name-row">
              <input
                className="panel-info__name-input"
                value={processDisplayName}
                onChange={(e) => setProcessDisplayName(e.target.value)}
                placeholder="Process name"
                spellCheck={false}
              />
              <svg className="panel-info__edit-icon" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M11.5 1.5l3 3L5 14H2v-3L11.5 1.5z" /></svg>
            </div>
            <div className="panel-info__stats">
              <div className="panel-info__stat"><span className="panel-info__stat-value">{stats.steps}</span><span className="panel-info__stat-label">Steps</span></div>
              <div className="panel-info__stat"><span className="panel-info__stat-value">{stats.decisions}</span><span className="panel-info__stat-label">Decisions</span></div>
              <div className="panel-info__stat"><span className="panel-info__stat-value">{stats.subprocesses}</span><span className="panel-info__stat-label">Subs</span></div>
              <div className="panel-info__stat"><span className="panel-info__stat-value">{stats.connections}</span><span className="panel-info__stat-label">Edges</span></div>
              <div className="panel-info__stat"><span className="panel-info__stat-value">{stats.lanes}</span><span className="panel-info__stat-label">Lanes</span></div>
            </div>
          </section>

          {panelFooter && <div className="process-canvas__panel-chat">{panelFooter}</div>}
        </div>
      </aside>

      <div className="process-canvas__resize-handle" onMouseDown={() => setResizing(true)} title="Drag to resize panel" aria-label="Resize panel" />

      <DataViewState loading={loading} error={error} loadingText="Loading process\u2026" loadingClassName="process-canvas__loading" errorClassName="process-canvas__error" />

      {edgeEditor && (
        <div className="process-canvas__edge-editor-backdrop" onClick={handleEdgeEditorClose}>
          <div className="process-canvas__edge-editor" onClick={(e) => e.stopPropagation()}>
            <div className="process-canvas__edge-editor-title">{edgeEditor.mode === 'create' ? 'New connection label' : 'Edit connection label'}</div>
            <input
              className="process-canvas__edge-editor-input"
              autoFocus
              placeholder="Enter edge text (optional)"
              value={edgeEditor.label}
              onChange={(e) => setEdgeEditor((prev) => (prev ? { ...prev, label: e.target.value } : prev))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); handleEdgeEditorSave() }
                else if (e.key === 'Escape') { e.preventDefault(); handleEdgeEditorClose() }
              }}
            />
            <div className="process-canvas__edge-editor-actions">
              <button type="button" onClick={handleEdgeEditorClose} disabled={edgeEditorSaving}>Cancel</button>
              <button type="button" onClick={handleEdgeEditorSave} disabled={edgeEditorSaving}>{edgeEditorSaving ? 'Saving\u2026' : 'Save'}</button>
            </div>
          </div>
        </div>
      )}

      <div
        ref={flowWrapper}
        className={'process-canvas__flow' + (pendingAddType ? ' process-canvas__flow--placing' : '')}
        style={{ visibility: loading || error ? 'hidden' : 'visible' }}
        tabIndex={0}
        onMouseDown={() => flowWrapper.current?.focus()}
        onFocus={() => setFlowFocused(true)}
        onBlur={() => setFlowFocused(false)}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={handleConnect}
          onEdgesDelete={handleEdgesDelete}
          onNodesDelete={handleNodesDelete}
          onReconnect={handleReconnect}
          onEdgeDoubleClick={handleEdgeDoubleClick}
          onNodeClick={handleNodeClick}
          onConnectStart={(_, { nodeId }) => setSelectedNodeId(nodeId || null)}
          onPaneClick={handlePlaceNode}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.1}
          maxZoom={4}
          edgesReconnectable
          connectionLineType={ConnectionLineType.SmoothStep}
          defaultEdgeOptions={{ type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--edge-stroke, #c97d3a)' } }}
          proOptions={{ hideAttribution: true }}
          deleteKeyCode={['Backspace', 'Delete']}
        >
          <MiniMap
            position="top-right"
            pannable
            zoomable
            nodeStrokeColor="var(--node-stroke, #c97d3a)"
            nodeColor="var(--node-fill, #f5d4b8)"
            maskColor="rgba(255, 255, 255, 0.7)"
            style={{ width: 180, height: 120, background: 'var(--bg-secondary, #1a1510)' }}
          />
          <Background variant="dots" color="#ccc4b8" gap={20} size={1.5} />
        </ReactFlow>
      </div>
    </div>
  )
}

export default function ProcessCanvas(props) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  )
}
