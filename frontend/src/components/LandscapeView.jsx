/**
 * Landscape view: process tree as a React Flow diagram (layoutTree). Each node is a card with process name and summary.
 * Clicking a node calls onProcessSelect so the dashboard can switch to that process's detail view.
 */
import { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Controls,
  Background,
  ReactFlowProvider,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { layoutTree } from '../services/landscapeLayout'
import './LandscapeView.css'

function buildFlowNodesAndEdges(workspace, currentProcessId) {
  const { nodes: layoutNodes, edges: layoutEdges } = layoutTree(workspace)
  const processes = workspace?.process_tree?.processes || {}

  const nodes = layoutNodes.map((n) => {
    const info = processes[n.id] || {}
    const isCurrent = n.id === currentProcessId
    return {
      id: n.id,
      type: 'default',
      position: { x: n.x, y: n.y },
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
        background: isCurrent ? 'var(--accent-soft, rgba(232, 93, 4, 0.25))' : 'var(--node-fill, #f5d4b8)',
        border: isCurrent ? '2px solid var(--accent, #e85d04)' : '2px solid var(--node-stroke, #c97d3a)',
        borderRadius: '10px',
        padding: 0,
        width: n.width,
      },
    }
  })

  const edges = layoutEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    style: { stroke: 'var(--edge-stroke, #c97d3a)' },
  }))

  return { nodes, edges }
}

function LandscapeCanvas({ workspace, currentProcessId, onProcessSelect, onSwitchView }) {
  const { nodes, edges } = useMemo(
    () => buildFlowNodesAndEdges(workspace, currentProcessId),
    [workspace, currentProcessId],
  )
  const handleNodeClick = useCallback(
    (_event, node) => onProcessSelect?.(node.id),
    [onProcessSelect],
  )

  if (!workspace) {
    return <div className="landscape-view__empty">Loading workspace...</div>
  }

  return (
    <div className="landscape-view">
      <button className="landscape-view__back" onClick={onSwitchView}>
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M10 3L5 8l5 5" /></svg>
        Process View
      </button>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
        fitView
        minZoom={0.3}
        maxZoom={2}
        nodesDraggable={false}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: 'smoothstep' }}
      >
        <Controls position="bottom-left" />
        <Background variant="dots" color="var(--border, #ccc4b8)" gap={20} size={1.5} />
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
