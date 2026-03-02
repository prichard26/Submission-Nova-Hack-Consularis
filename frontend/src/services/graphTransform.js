/**
 * Transform JSON graph document -> React Flow nodes and edges.
 * Lanes are rendered as non-interactive background rectangles.
 */

const LANE_PADDING = 40
const LANE_MIN_HEIGHT = 160
const NODE_WIDTH = 260
const NODE_HEIGHT = 120

function computeLaneNodes(graph) {
  const nodes = []
  if (!graph.lanes || !graph.steps) return nodes

  for (const lane of graph.lanes) {
    const refs = new Set(lane.node_refs || [])
    const laneSteps = graph.steps.filter((s) => refs.has(s.id))
    if (laneSteps.length === 0) continue

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const s of laneSteps) {
      const pos = s.position || { x: 0, y: 0 }
      minX = Math.min(minX, pos.x)
      minY = Math.min(minY, pos.y)
      maxX = Math.max(maxX, pos.x + NODE_WIDTH)
      maxY = Math.max(maxY, pos.y + NODE_HEIGHT)
    }

    const width = maxX - minX + LANE_PADDING * 2 + 100
    const height = Math.max(maxY - minY + LANE_PADDING * 2, LANE_MIN_HEIGHT)

    nodes.push({
      id: `lane_${lane.id}`,
      type: 'group',
      position: { x: minX - LANE_PADDING - 80, y: minY - LANE_PADDING },
      style: {
        width,
        height,
        background: 'var(--lane-bg, rgba(245, 212, 184, 0.04))',
        border: '1px solid var(--lane-border, rgba(201, 125, 58, 0.15))',
        borderRadius: '8px',
        zIndex: -1,
      },
      data: { label: lane.name },
      selectable: false,
      draggable: false,
      connectable: false,
    })
  }
  return nodes
}

export function toReactFlowData(graph, workspaceProcesses = {}) {
  const nodes = []
  const edges = []

  if (!graph) return { nodes, edges }

  const laneNodes = computeLaneNodes(graph)
  nodes.push(...laneNodes)

  for (const step of graph.steps || []) {
    const processInfo = workspaceProcesses[step.called_element] || {}
    nodes.push({
      id: step.id,
      type: step.type || 'step',
      position: step.position || { x: 0, y: 0 },
      data: { ...step, workspaceInfo: processInfo },
      draggable: step.type !== 'start' && step.type !== 'end',
    })
  }

  for (const flow of graph.flows || []) {
    edges.push({
      id: `${flow.from}->${flow.to}`,
      source: flow.from,
      target: flow.to,
      label: flow.label || '',
      animated: false,
      style: { stroke: 'var(--edge-stroke, #c97d3a)' },
      labelStyle: { fill: 'var(--node-text, #4a3020)', fontWeight: 600, fontSize: 11 },
    })
  }

  return { nodes, edges }
}
