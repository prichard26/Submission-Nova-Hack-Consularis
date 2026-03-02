import { useCallback, useEffect, useRef, useMemo, useState } from 'react'
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { toPng } from 'html-to-image'
import { useProcessGraph } from '../hooks/useProcessGraph'
import { toReactFlowData } from '../services/graphTransform'
import { nodeTypes } from './nodes/nodeTypes'
import { undoGraph, updatePositions, createNode, exportBpmnXml } from '../services/api'
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
  const flowWrapper = useRef(null)
  const posTimerRef = useRef(null)
  const pendingPositions = useRef({})

  const { initialNodes, initialEdges } = useMemo(() => {
    if (!graph) return { initialNodes: [], initialEdges: [] }
    const { nodes, edges } = toReactFlowData(graph, workspaceProcesses)
    return { initialNodes: nodes, initialEdges: edges }
  }, [graph, workspaceProcesses])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  // Sync when graph data changes
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

  return (
    <div className="process-canvas">
      <aside className="process-canvas__panel">
        <div className="process-canvas__panel-inner">
          <div className="process-canvas__toolbar" role="toolbar">
            <span className="process-canvas__toolbar-title">Process Canvas</span>
            <div className="process-canvas__toolbar-group">
              <span className="process-canvas__toolbar-label">Add</span>
              <div className="process-canvas__toolbar-actions">
                <button type="button" onClick={() => handleAddNode('step')} disabled={loading || !!error} title="Add Step">+ Step</button>
                <button type="button" onClick={() => handleAddNode('decision')} disabled={loading || !!error} title="Add Decision">+ Decision</button>
                <button type="button" onClick={() => handleAddNode('subprocess')} disabled={loading || !!error} title="Add Subprocess">+ Sub</button>
              </div>
            </div>
            <div className="process-canvas__toolbar-group">
              <span className="process-canvas__toolbar-label">Export</span>
              <div className="process-canvas__toolbar-actions">
                <button type="button" onClick={handleExportPng} disabled={loading || !!error} title="Export PNG">PNG</button>
                <button type="button" onClick={handleExportBpmn} disabled={loading || !!error} title="Export BPMN XML">BPMN</button>
              </div>
            </div>
            <div className="process-canvas__toolbar-group">
              <span className="process-canvas__toolbar-label">Actions</span>
              <div className="process-canvas__toolbar-actions">
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
          onNodeClick={handleNodeClick}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.1}
          maxZoom={4}
          defaultEdgeOptions={{ type: 'smoothstep' }}
          proOptions={{ hideAttribution: true }}
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
