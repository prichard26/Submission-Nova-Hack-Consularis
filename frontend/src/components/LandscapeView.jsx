import { useMemo } from 'react'
import {
  ReactFlow,
  Controls,
  Background,
  ReactFlowProvider,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from 'dagre'
import './LandscapeView.css'

function layoutTree(workspace) {
  const nodes = []
  const edges = []
  if (!workspace?.process_tree?.processes) return { nodes, edges }

  const processes = workspace.process_tree.processes
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 100 })

  for (const [pid, info] of Object.entries(processes)) {
    g.setNode(pid, { width: 220, height: 100 })
    for (const child of info.children || []) {
      if (processes[child]) {
        g.setEdge(pid, child)
      }
    }
  }

  dagre.layout(g)

  for (const [pid, info] of Object.entries(processes)) {
    const pos = g.node(pid)
    nodes.push({
      id: pid,
      type: 'default',
      position: { x: pos.x - 110, y: pos.y - 50 },
      data: {
        label: (
          <div className="landscape-card">
            <div className="landscape-card__name">{info.name}</div>
            <div className="landscape-card__stats">
              {info.summary?.step_count != null && (
                <span>{info.summary.step_count} steps</span>
              )}
              {info.summary?.subprocess_count > 0 && (
                <span>{info.summary.subprocess_count} sub</span>
              )}
              {info.summary?.automation_coverage && (
                <span>{info.summary.automation_coverage} auto</span>
              )}
            </div>
            {info.category && (
              <span className="landscape-card__category">{info.category}</span>
            )}
          </div>
        ),
      },
      style: {
        background: 'var(--node-fill, #f5d4b8)',
        border: '2px solid var(--node-stroke, #c97d3a)',
        borderRadius: '10px',
        padding: 0,
        width: 220,
      },
    })
  }

  for (const e of g.edges()) {
    edges.push({
      id: `${e.v}->${e.w}`,
      source: e.v,
      target: e.w,
      style: { stroke: 'var(--edge-stroke, #c97d3a)' },
    })
  }

  return { nodes, edges }
}

function LandscapeCanvas({ workspace, onProcessSelect }) {
  const { nodes, edges } = useMemo(() => layoutTree(workspace), [workspace])

  if (!workspace) {
    return <div className="landscape-view__empty">Loading workspace...</div>
  }

  return (
    <div className="landscape-view">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={(_e, node) => onProcessSelect?.(node.id)}
        fitView
        minZoom={0.3}
        maxZoom={2}
        nodesDraggable={false}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: 'smoothstep' }}
      >
        <Controls position="bottom-left" />
        <Background variant="dots" color="#ccc4b8" gap={20} size={1.5} />
      </ReactFlow>
    </div>
  )
}

export default function LandscapeView(props) {
  return (
    <ReactFlowProvider>
      <LandscapeCanvas {...props} />
    </ReactFlowProvider>
  )
}
