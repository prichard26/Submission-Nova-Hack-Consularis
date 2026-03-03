import { useCallback, useEffect, useRef, useMemo, useState } from 'react'
import {
  ReactFlow,
  MiniMap,
  Controls,
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

function Canvas({
  sessionId,
  processId = 'Process_Global',
  refreshTrigger = 0,
  onStepSelect,
  onDrillDown,
  onRequestRefresh,
  panelFooter,
  workspaceProcesses = {},
}) {
  const { screenToFlowPosition } = useReactFlow()
  const { graph, loading, error } = useProcessGraph(sessionId, processId, refreshTrigger)
  const [undoBotPending, setUndoBotPending] = useState(false)
  const [redoPending, setRedoPending] = useState(false)
  const [resetPending, setResetPending] = useState(false)
  const [panelWidth, setPanelWidth] = useState(380)
  const [resizing, setResizing] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [flowFocused, setFlowFocused] = useState(false)
  const [pendingAddType, setPendingAddType] = useState(null)
  const [subprocessStatus, setSubprocessStatus] = useState('')
  const [edgeEditor, setEdgeEditor] = useState(null)
  const [edgeEditorSaving, setEdgeEditorSaving] = useState(false)
  const flowWrapper = useRef(null)
  const panelRef = useRef(null)
  const posTimerRef = useRef(null)
  const pendingPositions = useRef({})

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
    function onUp() {
      setResizing(false)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [resizing])

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
        // New subprocess nodes may not yet be linked to a target process.
        // Fall back to opening details so the node remains actionable on click.
        if (onStepSelect) {
          onStepSelect(node.data)
        }
        return
      }
      if (node.type === 'step' && onStepSelect) {
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
        if (e.shiftKey) {
          handleRedo()
        } else {
          handleUndoBot()
        }
        return
      }

      if (key === 's') {
        e.preventDefault()
        handleAddNode('step')
      } else if (key === 'd') {
        e.preventDefault()
        handleAddNode('decision')
      } else if (key === 'p') {
        e.preventDefault()
        handleAddNode('subprocess')
      } else if (key === 'a') {
        e.preventDefault()
        handleAutoArrange()
      } else if (key === 'escape') {
        setPendingAddType(null)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [flowFocused, loading, error, handleAddNode, handleAutoArrange, handleUndoBot, handleRedo])

  const disabled = loading || !!error

  return (
    <div className="process-canvas">
      <div
        className="process-canvas__resize-handle"
        onMouseDown={() => setResizing(true)}
        title="Drag to resize panel"
        aria-label="Resize panel"
      />
      <aside
        ref={panelRef}
        className="process-canvas__panel"
        style={{ width: panelWidth, minWidth: panelWidth }}
      >
        <div className="process-canvas__panel-inner">
          <div className="process-canvas__toolbar" role="toolbar">
            <span className="process-canvas__toolbar-title">Canvas</span>
            <button
              type="button"
              onClick={() => handleAddNode('step')}
              disabled={disabled}
              className={pendingAddType === 'step' ? 'process-canvas__toolbar-button--active' : ''}
              title="Add Step (S)"
            >
              + Step
            </button>
            <button
              type="button"
              onClick={() => handleAddNode('decision')}
              disabled={disabled}
              className={pendingAddType === 'decision' ? 'process-canvas__toolbar-button--active' : ''}
              title="Add Decision (D)"
            >
              + Decision
            </button>
            <button
              type="button"
              onClick={() => handleAddNode('subprocess')}
              disabled={disabled}
              className={pendingAddType === 'subprocess' ? 'process-canvas__toolbar-button--active' : ''}
              title="Add Subprocess (P)"
            >
              + Sub
            </button>
            <span className="process-canvas__toolbar-sep" />
            <button type="button" onClick={handleAutoArrange} disabled={disabled || !onRequestRefresh} title="Auto-arrange nodes (A)">Arrange</button>
            <button type="button" onClick={handleUndoBot} disabled={disabled || undoBotPending || !onRequestRefresh} title="Undo last change (Ctrl/Cmd+Z)">Undo</button>
            <button type="button" onClick={handleRedo} disabled={disabled || redoPending || !onRequestRefresh} title="Redo last undo (Ctrl/Cmd+Shift+Z)">Redo</button>
            <button type="button" onClick={handleReset} disabled={disabled || resetPending || !onRequestRefresh} title="Reset to baseline">Reset</button>
            <span className="process-canvas__toolbar-sep" />
            <button type="button" onClick={handleExportPng} disabled={disabled} title="Export as PNG">PNG</button>
            <button type="button" onClick={handleExportBpmn} disabled={disabled} title="Export as BPMN XML">BPMN</button>
          </div>
          {pendingAddType && (
            <div className="process-canvas__place-hint">
              Click on canvas to place the new {pendingAddType}. It starts unconnected.
            </div>
          )}
          {!pendingAddType && subprocessStatus && (
            <div className="process-canvas__subprocess-status">{subprocessStatus}</div>
          )}
          <div className="process-canvas__shortcuts" aria-label="Keyboard shortcuts">
            <div className="process-canvas__shortcuts-title">Keyboard shortcuts</div>
            <div className="process-canvas__shortcuts-grid">
              <span><kbd>S</kbd> Add Step</span>
              <span><kbd>D</kbd> Add Decision</span>
              <span><kbd>P</kbd> Add Subprocess</span>
              <span><kbd>A</kbd> Auto-arrange</span>
              <span><kbd>Ctrl/Cmd + Z</kbd> Undo</span>
              <span><kbd>Ctrl/Cmd + Shift + Z</kbd> Redo</span>
            </div>
            <div className="process-canvas__shortcuts-note">Click the canvas first to enable shortcuts.</div>
          </div>
          {panelFooter && <div className="process-canvas__panel-footer">{panelFooter}</div>}
        </div>
      </aside>
      <DataViewState
        loading={loading}
        error={error}
        loadingText="Loading process…"
        loadingClassName="process-canvas__loading"
        errorClassName="process-canvas__error"
      />
      {edgeEditor && (
        <div className="process-canvas__edge-editor-backdrop" onClick={handleEdgeEditorClose}>
          <div className="process-canvas__edge-editor" onClick={(e) => e.stopPropagation()}>
            <div className="process-canvas__edge-editor-title">
              {edgeEditor.mode === 'create' ? 'New connection label' : 'Edit connection label'}
            </div>
            <input
              className="process-canvas__edge-editor-input"
              autoFocus
              placeholder="Enter edge text (optional)"
              value={edgeEditor.label}
              onChange={(e) => setEdgeEditor((prev) => (prev ? { ...prev, label: e.target.value } : prev))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  handleEdgeEditorSave()
                } else if (e.key === 'Escape') {
                  e.preventDefault()
                  handleEdgeEditorClose()
                }
              }}
            />
            <div className="process-canvas__edge-editor-actions">
              <button type="button" onClick={handleEdgeEditorClose} disabled={edgeEditorSaving}>Cancel</button>
              <button type="button" onClick={handleEdgeEditorSave} disabled={edgeEditorSaving}>
                {edgeEditorSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
      <div
        ref={flowWrapper}
        className={`process-canvas__flow ${pendingAddType ? 'process-canvas__flow--placing' : ''}`}
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
          defaultEdgeOptions={{
            type: 'smoothstep',
            markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--edge-stroke, #c97d3a)' },
          }}
          proOptions={{ hideAttribution: true }}
          deleteKeyCode={['Backspace', 'Delete']}
        >
          <Controls position="top-left" />
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
