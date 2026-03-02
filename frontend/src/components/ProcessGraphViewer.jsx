import { memo, useMemo } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  MarkerType,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useGraphJson } from '../hooks/useGraphJson'
import './ProcessGraphViewer.css'
import DataViewState from './DataViewState'

const ProcessTaskNode = memo(function ProcessTaskNode({ data }) {
  return (
    <div className="process-graph-viewer__task-node">
      <Handle type="target" position={Position.Left} className="process-graph-viewer__handle" />
      <Handle type="source" position={Position.Right} className="process-graph-viewer__handle" />
      <div className="process-graph-viewer__task-title">{data.label}</div>
      <div className="process-graph-viewer__task-meta">
        <span>{data.actor || 'Unknown role'}</span>
        <span>{data.duration_min || '—'}</span>
      </div>
    </div>
  )
})

const nodeTypes = {
  processTask: ProcessTaskNode,
}

/**
 * Viewer contract:
 * - Accepts { sessionId, refreshTrigger } like BpmnViewer.
 * - Refreshes on either prop change so chat edits appear immediately.
 */
export default function ProcessGraphViewer({ sessionId, processId = 'Process_Global', refreshTrigger = 0 }) {
  const { graph, loading, error } = useGraphJson(sessionId, processId, refreshTrigger)

  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] }

    const lanes = Array.isArray(graph.lanes) ? graph.lanes : []
    const graphNodes = Array.isArray(graph.nodes) ? graph.nodes : []
    const graphEdges = Array.isArray(graph.edges) ? graph.edges : []
    const laneHeight = Number(graph?.layout?.lane_height) || 130
    const taskWidth = Number(graph?.layout?.task_width) || 200
    const gapX = Number(graph?.layout?.gap_x) || 56
    const maxLaneSteps = Number(graph?.layout?.max_lane_steps) || 1
    const laneWidth = Math.max(1100, maxLaneSteps * (taskWidth + gapX) + 480)
    const laneLabelWidth = 200

    const laneNodes = lanes.map((lane, laneIndex) => {
      const y = typeof lane.y === 'number' ? lane.y : laneIndex * laneHeight
      const sectionLabel = `${lane.id} — ${(lane.name || '').trim() || 'Phase'}`
      return {
        id: `lane:${lane.id}`,
        type: 'default',
        position: { x: -laneLabelWidth - 24, y },
        draggable: false,
        selectable: false,
        connectable: false,
        focusable: false,
        data: {
          label: sectionLabel,
          laneId: lane.id,
          laneIndex,
        },
        style: {
          width: laneWidth + laneLabelWidth + 24,
          height: Math.max(100, laneHeight - 18),
        },
        className: `process-graph-viewer__lane-node process-graph-viewer__lane-node--${laneIndex % 2 === 0 ? 'even' : 'odd'}`,
      }
    })

    const taskNodes = graphNodes.map((node) => ({
      id: node.id,
      type: 'processTask',
      draggable: false,
      data: {
        label: node.label || node.id,
        actor: node.actor || '',
        duration_min: node.duration_min || '—',
      },
      position: {
        x: Number(node?.position?.x) || 0,
        y: Number(node?.position?.y) || 0,
      },
    }))

    const rfEdges = graphEdges.map((edge) => ({
      id: edge.id || `edge:${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      label: edge.condition || edge.label || '',
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      className: 'process-graph-viewer__edge',
      style: { strokeWidth: 1.8 },
      labelStyle: { fill: '#e0d4c4', fontSize: 12, fontFamily: 'DM Sans, sans-serif' },
      labelBgStyle: { fill: '#1a1510' },
      labelBgPadding: [4, 2],
      labelBgBorderRadius: 4,
    }))

    return { nodes: [...laneNodes, ...taskNodes], edges: rfEdges }
  }, [graph])

  return (
    <div className="process-graph-viewer">
      <DataViewState
        loading={loading}
        error={error}
        loadingText="Loading process map…"
        loadingClassName="process-graph-viewer__loading"
        errorClassName="process-graph-viewer__error"
      />
      <div
        className="process-graph-viewer__canvas"
        style={{ visibility: loading || error ? 'hidden' : 'visible' }}
      >
        <ReactFlow
          fitView
          fitViewOptions={{ padding: 0.18, duration: 300 }}
          minZoom={0.35}
          maxZoom={1.8}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          panOnDrag
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} size={1} />
          <MiniMap pannable zoomable />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  )
}
