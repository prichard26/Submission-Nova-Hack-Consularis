import { useCallback, useEffect, useRef, useMemo, useState } from 'react'
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { toPng } from 'html-to-image'
import { useProcessGraph } from '../hooks/useProcessGraph'
import { toReactFlowData, autoArrangeNodes } from '../services/graphTransform'
import { nodeTypes } from './nodes/nodeTypes'
import { undoGraph, updatePositions, createNode, createEdge, deleteEdge, exportBpmnXml } from '../services/api'
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
  const { graph, loading, error } = useProcessGraph(sessionId, processId, refreshTrigger)
  const [undoBotPending, setUndoBotPending] = useState(false)
  const [panelWidth, setPanelWidth] = useState(380)
  const [resizing, setResizing] = useState(false)
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
      setPanelWidth((w) => Math.min(720, Math.max(280, newWidth)))
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
      if (node.type === 'subprocess' && onDrillDown && node.data?.called_element) {
        onDrillDown(node.data.called_element)
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

  const handleAddNode = useCallback(
    async (type) => {
      if (!graph?.lanes?.length) return
      const laneId = graph.lanes[0].id
      const name = type === 'step' ? 'New Step' : type === 'decision' ? 'New Decision' : 'New Subprocess'
      try {
        await createNode(sessionId, processId, laneId, name, type)
        onRequestRefresh?.()
      } catch (err) {
        console.warn('Create node failed', err)
      }
    },
    [graph, sessionId, processId, onRequestRefresh],
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
    async (connection) => {
      if (!connection?.source || !connection?.target) return
      try {
        await createEdge(sessionId, processId, connection.source, connection.target, '')
        onRequestRefresh?.()
      } catch (err) {
        console.warn('Create edge failed', err)
      }
    },
    [sessionId, processId, onRequestRefresh],
  )

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

  const handleReconnect = useCallback(
    async (oldEdge, newConnection) => {
      if (!newConnection?.source || !newConnection?.target) return
      try {
        await deleteEdge(sessionId, processId, oldEdge.source, oldEdge.target)
        await createEdge(sessionId, processId, newConnection.source, newConnection.target, '')
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
            <button type="button" onClick={() => handleAddNode('step')} disabled={disabled} title="Add Step">+ Step</button>
            <button type="button" onClick={() => handleAddNode('decision')} disabled={disabled} title="Add Decision">+ Decision</button>
            <button type="button" onClick={() => handleAddNode('subprocess')} disabled={disabled} title="Add Subprocess">+ Sub</button>
            <span className="process-canvas__toolbar-sep" />
            <button type="button" onClick={handleAutoArrange} disabled={disabled || !onRequestRefresh} title="Auto-arrange nodes">Arrange</button>
            <button type="button" onClick={handleUndoBot} disabled={disabled || undoBotPending || !onRequestRefresh} title="Undo last bot change">Undo</button>
            <span className="process-canvas__toolbar-sep" />
            <button type="button" onClick={handleExportPng} disabled={disabled} title="Export as PNG">PNG</button>
            <button type="button" onClick={handleExportBpmn} disabled={disabled} title="Export as BPMN XML">BPMN</button>
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
      <div
        ref={flowWrapper}
        className="process-canvas__flow"
        style={{ visibility: loading || error ? 'hidden' : 'visible' }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={handleConnect}
          onEdgesDelete={handleEdgesDelete}
          onReconnect={handleReconnect}
          onNodeClick={handleNodeClick}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.1}
          maxZoom={4}
          edgesReconnectable
          defaultEdgeOptions={{
            type: 'smoothstep',
            markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--edge-stroke, #c97d3a)' },
          }}
          proOptions={{ hideAttribution: true }}
          deleteKeyCode={['Backspace', 'Delete']}
        >
          <Controls position="bottom-left" />
          <MiniMap
            nodeStrokeColor="var(--node-stroke, #c97d3a)"
            nodeColor="var(--node-fill, #f5d4b8)"
            maskColor="rgba(255, 255, 255, 0.7)"
            style={{ background: 'var(--bg-secondary, #1a1510)' }}
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
