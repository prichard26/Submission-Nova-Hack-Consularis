import { useCallback, useEffect, useRef, useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  useReactFlow,
  useViewport,
  MarkerType,
  ConnectionLineType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { toPng } from 'html-to-image'
import { useProcessGraph } from '../hooks/useProcessGraph'
import { toReactFlowData, autoArrangeNodes, topLeftToCenter } from '../services/graphTransform'
import { nodeTypes } from './nodes/nodeTypes.jsx'
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
import DetailPanel from './DetailPanel'
import DataViewState from './DataViewState'
import FloatingToolbar from './FloatingToolbar'
import EdgeEditorModal from './EdgeEditorModal'
import ProcessNameHeader from './ProcessNameHeader'
import LandscapeMinimap from './LandscapeMinimap'
import './ProcessCanvas.css'

const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.userAgent)

function Canvas({
  sessionId,
  processId = 'global',
  refreshTrigger = 0,
  onStepSelect,
  onDrillDown,
  onRequestRefresh,
  panelFooter,
  workspaceProcesses = {},
  viewMode,
  onViewModeChange,
  selectedStep,
  onCloseDetail,
  onStepUpdate,
  structuralChangeFromChat = false,
  structuralChangeGraph = null,
  onConsumedStructuralChange,
  canvasAreaRef,
  panelRef: panelRefProp,
  toolbarRef: toolbarRefProp,
  minimapRef: minimapRefProp,
  panelHeaderRef,
  panelElementInfoRef,
  panelChatRef,
}) {
  const { screenToFlowPosition, flowToScreenPosition, zoomIn, zoomOut, fitView } = useReactFlow()
  const { zoom } = useViewport()
  const { graph, loading, error } = useProcessGraph(sessionId, processId, refreshTrigger)
  const [undoBotPending, setUndoBotPending] = useState(false)
  const [redoPending, setRedoPending] = useState(false)
  const [resetPending, setResetPending] = useState(false)
  const [renameTrigger, setRenameTrigger] = useState(0)
  const [panelWidth, setPanelWidth] = useState(340)
  const [resizing, setResizing] = useState(false)
  const [flowFocused, setFlowFocused] = useState(false)
  const [pendingAddType, setPendingAddType] = useState(null)
  const [subprocessStatus, setSubprocessStatus] = useState('')
  const [edgeEditor, setEdgeEditor] = useState(null)
  const [edgeEditorSaving, setEdgeEditorSaving] = useState(false)
  const [tbPos, setTbPos] = useState({ x: 16, y: 16 })
  const [tbLayout, setTbLayout] = useState('vertical')
  const [tbCollapsed, setTbCollapsed] = useState(false)
  const [tbDragging, setTbDragging] = useState(false)
  const [ghostPos, setGhostPos] = useState(null)
  const canvasRef = useRef(null)
  const tbRef = useRef(null)
  const flowWrapper = useRef(null)
  const panelRef = useRef(null)
  const setToolbarRef = useCallback(
    (el) => {
      tbRef.current = el
      if (toolbarRefProp) toolbarRefProp.current = el
    },
    [toolbarRefProp],
  )
  const setFlowRef = useCallback(
    (el) => {
      flowWrapper.current = el
      if (canvasAreaRef) canvasAreaRef.current = el
    },
    [canvasAreaRef],
  )
  const setPanelRef = useCallback(
    (el) => {
      panelRef.current = el
      if (panelRefProp) panelRefProp.current = el
    },
    [panelRefProp],
  )
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

  const processDisplayName = useMemo(() => {
    const entry = workspaceProcesses[processId]
    return entry?.name || processId.replace(/^Process_/, '').replace(/_/g, ' ')
  }, [processId, workspaceProcesses])

  const { initialNodes, initialEdges } = useMemo(() => {
    if (!graph) return { initialNodes: [], initialEdges: [] }
    const { nodes, edges } = toReactFlowData(graph, workspaceProcesses, { processDisplayName })
    return { initialNodes: nodes, initialEdges: edges }
  }, [graph, workspaceProcesses, processDisplayName])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  // Sync graph from refetch to canvas. Always apply auto-arrange as the default layout. Skip when chat just sent a graph so the chat effect can apply it first.
  useEffect(() => {
    if (structuralChangeFromChat && structuralChangeGraph) return
    if (initialNodes.length === 0) {
      setNodes(initialNodes)
      setEdges(initialEdges)
      return
    }
    let cancelled = false
    ;(async () => {
      const { nodes: nextNodes, edges: nextEdges, positions } = await autoArrangeNodes(initialNodes, initialEdges, {
        graph: graph ?? undefined,
        processDisplayName,
      })
      if (cancelled) return
      setNodes(nextNodes)
      setEdges(nextEdges)
      setTimeout(() => fitView({ padding: 0.15 }), 100)
      if (Object.keys(positions).length > 0 && sessionId && processId) {
        try {
          await updatePositions(sessionId, processId, positions)
        } catch (err) {
          console.warn('Auto-arrange on load: position update failed', err)
        }
      }
    })()
    return () => { cancelled = true }
  }, [initialNodes, initialEdges, graph, sessionId, processId, processDisplayName, setNodes, setEdges, fitView, structuralChangeFromChat, structuralChangeGraph])

  // When chat used tools and returned a graph: apply it immediately so nodes update, then optionally run layout.
  useEffect(() => {
    if (!structuralChangeFromChat || !structuralChangeGraph || !onConsumedStructuralChange) return
    const { nodes: arrangeNodes, edges: arrangeEdges } = toReactFlowData(structuralChangeGraph, workspaceProcesses, {
      processDisplayName,
    })
    if (arrangeNodes.length === 0) {
      onConsumedStructuralChange()
      return
    }
    // Apply graph immediately so the user sees updated node data (e.g. actor, duration) right away.
    setNodes(arrangeNodes)
    setEdges(arrangeEdges)
    let cancelled = false
    ;(async () => {
      const { nodes: nextNodes, edges: nextEdges, positions } = await autoArrangeNodes(
        arrangeNodes,
        arrangeEdges,
        { graph: structuralChangeGraph, processDisplayName }
      )
      if (cancelled) {
        onConsumedStructuralChange()
        return
      }
      if (Object.keys(positions).length > 0) {
        setNodes(nextNodes)
        setEdges(nextEdges)
        setTimeout(() => fitView({ padding: 0.15 }), 100)
        try {
          await updatePositions(sessionId, processId, positions)
          onRequestRefresh?.()
        } catch (err) {
          console.warn('Auto-arrange after chat update failed', err)
        }
      }
      onConsumedStructuralChange()
    })()
    return () => { cancelled = true }
  }, [structuralChangeFromChat, structuralChangeGraph, workspaceProcesses, sessionId, processId, processDisplayName, setNodes, setEdges, fitView, onRequestRefresh, onConsumedStructuralChange])

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
        const node = nodes.find((n) => n.id === c.id)
        const center = topLeftToCenter(c.position, node)
        pendingPositions.current[c.id] = { x: Math.round(center.x), y: Math.round(center.y) }
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
    [onNodesChange, sessionId, processId, nodes],
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
    setGhostPos(null)
  }, [])

  const handleCanvasMouseMove = useCallback(
    (e) => {
      if (!pendingAddType || !flowWrapper.current || !flowToScreenPosition) return
      const flowPos = screenToFlowPosition({ x: e.clientX, y: e.clientY })
      const screenPos = flowToScreenPosition(flowPos)
      const rect = flowWrapper.current.getBoundingClientRect()
      setGhostPos({ x: screenPos.x - rect.left, y: screenPos.y - rect.top })
    },
    [pendingAddType, screenToFlowPosition, flowToScreenPosition],
  )

  const handlePlaceNode = useCallback(
    async (event) => {
      if (!pendingAddType || !graph?.lanes?.length) {
        return
      }
      const laneId = graph.lanes[0].id
      const name =
        pendingAddType === 'step'
          ? 'New Step'
          : pendingAddType === 'decision'
            ? 'New Decision'
            : 'New Subprocess'
      const flowTopLeft = screenToFlowPosition({ x: event.clientX, y: event.clientY })
      const position = topLeftToCenter(flowTopLeft, { type: pendingAddType })
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
        setGhostPos(null)
        onRequestRefresh?.()
      } catch (err) {
        console.warn('Create node failed', err)
      }
    },
    [pendingAddType, graph, screenToFlowPosition, sessionId, processId, onRequestRefresh],
  )

  const handleNodeClick = useCallback(
    (event, node) => {
      if (pendingAddType && node.type === 'lane') {
        void handlePlaceNode(event)
        return
      }
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
    [pendingAddType, handlePlaceNode, onStepSelect, onDrillDown],
  )

  const handleAutoArrange = useCallback(async () => {
    const { nodes: nextNodes, edges: nextEdges, positions } = await autoArrangeNodes(nodes, edges, {
      graph: graph ?? undefined,
    })
    if (Object.keys(positions).length === 0) return
    setNodes(nextNodes)
    setEdges(nextEdges)
    setTimeout(() => fitView({ padding: 0.15 }), 100)
    try {
      await updatePositions(sessionId, processId, positions)
      onRequestRefresh?.()
    } catch (err) {
      console.warn('Auto-arrange position update failed', err)
    }
  }, [nodes, edges, graph, sessionId, processId, setNodes, setEdges, fitView, onRequestRefresh])

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
      else if (key === 'escape') { setPendingAddType(null); setGhostPos(null) }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [flowFocused, loading, error, handleAddNode, handleAutoArrange, handleUndoBot, handleRedo])

  const disabled = loading || !!error
  const undoTip = 'Undo \u00b7 ' + (IS_MAC ? '\u2318Z' : 'Ctrl+Z')
  const redoTip = 'Redo \u00b7 ' + (IS_MAC ? '\u2318\u21e7Z' : 'Ctrl+\u21e7+Z')
  const tbCls = 'floating-toolbar floating-toolbar--' + tbLayout + (tbCollapsed ? ' floating-toolbar--collapsed' : '')
  const handleToggleToolbarLayout = useCallback(() => {
    setTbLayout((layout) => (layout === 'vertical' ? 'horizontal' : 'vertical'))
  }, [])
  const handleEdgeEditorLabelChange = useCallback((label) => {
    setEdgeEditor((prev) => (prev ? { ...prev, label } : prev))
  }, [])

  return (
    <div className="process-canvas" ref={canvasRef}>
      <FloatingToolbar
        toolbarRef={setToolbarRef}
        className={tbCls}
        position={tbPos}
        hidden={loading || error}
        collapsed={tbCollapsed}
        layout={tbLayout}
        onGrab={onTbGrab}
        onZoomIn={zoomIn}
        onZoomOut={zoomOut}
        onFitView={() => fitView({ padding: 0.15 })}
        pendingAddType={pendingAddType}
        onAddNode={handleAddNode}
        disabled={disabled}
        onAutoArrange={handleAutoArrange}
        onUndo={handleUndoBot}
        undoDisabled={disabled || undoBotPending || !onRequestRefresh}
        undoTip={undoTip}
        onRedo={handleRedo}
        redoDisabled={disabled || redoPending || !onRequestRefresh}
        redoTip={redoTip}
        onReset={handleReset}
        resetDisabled={disabled || resetPending || !onRequestRefresh}
        onRenameMap={sessionId && onRequestRefresh ? () => setRenameTrigger((t) => t + 1) : undefined}
        onExportPng={handleExportPng}
        onExportBpmn={handleExportBpmn}
        onToggleLayout={handleToggleToolbarLayout}
      />

      {/* ── Right panel ── */}
      <aside ref={setPanelRef} className="process-canvas__panel" style={{ width: panelWidth, minWidth: panelWidth }}>
        <div className="process-canvas__panel-inner">
          {pendingAddType && (
            <div className="process-canvas__place-hint">Click to place · <strong>Esc</strong> to cancel</div>
          )}
          {!pendingAddType && subprocessStatus && (
            <div className="process-canvas__subprocess-status">{subprocessStatus}</div>
          )}

          <div ref={panelHeaderRef} className="process-canvas__panel-section process-canvas__panel-section--header">
            <ProcessNameHeader
              breadcrumb={breadcrumb}
              processDisplayName={processDisplayName}
              processId={processId}
              sessionId={sessionId}
              onDrillDown={onDrillDown}
              onRequestRefresh={onRequestRefresh}
              beginRenameTrigger={renameTrigger}
            />
          </div>

          <div
            ref={panelElementInfoRef}
            className={
              'process-canvas__panel-section ' +
              (selectedStep ? 'process-canvas__panel-section--detail' : 'process-canvas__panel-section--element-info')
            }
          >
            {selectedStep ? (
              <DetailPanel
                step={selectedStep}
                sessionId={sessionId}
                processId={processId}
                onClose={onCloseDetail}
                onUpdate={onStepUpdate}
              />
            ) : (
              <div className="process-canvas__element-info-placeholder">
                <p className="process-canvas__element-info-placeholder-text">Click on an element in the graph to see its details here.</p>
              </div>
            )}
          </div>

          {panelFooter && (
            <div ref={panelChatRef} className="process-canvas__panel-chat">
              {panelFooter}
            </div>
          )}
        </div>
      </aside>

      <div className="process-canvas__resize-handle" onMouseDown={() => setResizing(true)} title="Drag to resize panel" aria-label="Resize panel" />

      <DataViewState loading={loading} error={error} loadingText="Loading process\u2026" loadingClassName="process-canvas__loading" errorClassName="process-canvas__error" />

      <EdgeEditorModal
        edgeEditor={edgeEditor}
        edgeEditorSaving={edgeEditorSaving}
        onClose={handleEdgeEditorClose}
        onSave={handleEdgeEditorSave}
        onChangeLabel={handleEdgeEditorLabelChange}
      />

      <div className="process-canvas__graph">
        <div
          ref={setFlowRef}
          className={'process-canvas__flow' + (pendingAddType ? ' process-canvas__flow--placing' : '')}
          style={{ visibility: loading || error ? 'hidden' : 'visible' }}
          tabIndex={0}
          onMouseDown={() => flowWrapper.current?.focus()}
          onMouseMove={handleCanvasMouseMove}
          onMouseLeave={() => pendingAddType && setGhostPos(null)}
          onFocus={() => setFlowFocused(true)}
          onBlur={() => setFlowFocused(false)}
        >
          {pendingAddType && ghostPos && (
          <div
            className={`ghost-preview ghost-preview--${pendingAddType}`}
            style={{
              left: ghostPos.x,
              top: ghostPos.y,
              transform: `scale(${zoom ?? 1})`,
              transformOrigin: 'top left',
            }}
          >
            {pendingAddType === 'step' && (
              <div className="ghost-preview__step">
                <span className="ghost-preview__label">New Step</span>
              </div>
            )}
            {pendingAddType === 'decision' && (
              <div className="ghost-preview__decision">
                <div className="ghost-preview__decision-inner">
                  <span className="ghost-preview__label">New Decision</span>
                </div>
              </div>
            )}
            {pendingAddType === 'subprocess' && (
              <div className="ghost-preview__subprocess">
                <span className="ghost-preview__icon">▶▶</span>
                <span className="ghost-preview__label">New Subprocess</span>
              </div>
            )}
          </div>
        )}
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
          onPaneClick={handlePlaceNode}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.1}
          maxZoom={4}
          edgesReconnectable
          connectionLineType={ConnectionLineType.SmoothStep}
          defaultEdgeOptions={{
            type: 'smoothstep',
            markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: 'var(--edge-stroke, #c97d3a)' },
            labelStyle: { fill: 'var(--node-text, #4a3020)', fontWeight: 600, fontSize: 11 },
            labelBgStyle: { fill: 'var(--bg-secondary, #faf8f5)', stroke: 'var(--edge-stroke, #c97d3a)' },
            labelBgPadding: [6, 4],
            labelBgBorderRadius: 4,
          }}
          proOptions={{ hideAttribution: true }}
          deleteKeyCode={['Backspace', 'Delete']}
        >
          <LandscapeMinimap
            workspace={{ process_tree: { processes: workspaceProcesses } }}
            currentProcessId={processId}
            onProcessSelect={onDrillDown}
            minimapRef={minimapRefProp}
          />
          <Background variant="dots" color="var(--border, #ccc4b8)" gap={20} size={1.5} />
        </ReactFlow>
        </div>
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
