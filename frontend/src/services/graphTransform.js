/**
 * Transform JSON graph document -> React Flow nodes and edges.
 * Lanes are rendered as non-interactive background rectangles.
 */

import dagre from 'dagre'

const LANE_PADDING = 40
const LANE_MIN_HEIGHT = 160
const NODE_WIDTH = 260
const NODE_HEIGHT = 120
const EVENT_SIZE = 44
const GATEWAY_SIZE = 56

function getNodeDimensions(node) {
  const type = node.type || 'step'
  if (type === 'start' || type === 'end') return { width: EVENT_SIZE, height: EVENT_SIZE }
  if (type === 'decision') return { width: GATEWAY_SIZE, height: GATEWAY_SIZE }
  return { width: NODE_WIDTH, height: NODE_HEIGHT }
}

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
      connectable: true,
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

function runDagreLayout(stepNodes, edges, rankdir) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir, nodesep: 80, ranksep: 100 })

  const idSet = new Set(stepNodes.map((n) => n.id))
  for (const node of stepNodes) {
    const { width, height } = getNodeDimensions(node)
    g.setNode(node.id, { width, height })
  }
  for (const edge of edges) {
    if (!edge.source || !edge.target) continue
    if (idSet.has(edge.source) && idSet.has(edge.target)) {
      g.setEdge(edge.source, edge.target)
    }
  }

  dagre.layout(g)

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  const placed = stepNodes.map((node) => {
    const dn = g.node(node.id)
    if (!dn) return node
    const { width, height } = getNodeDimensions(node)
    const x = dn.x - width / 2
    const y = dn.y - height / 2
    minX = Math.min(minX, x)
    minY = Math.min(minY, y)
    maxX = Math.max(maxX, x + width)
    maxY = Math.max(maxY, y + height)
    return { ...node, position: { x, y } }
  })

  const bboxW = maxX - minX || 1
  const bboxH = maxY - minY || 1
  const aspectRatio = Math.max(bboxW, bboxH) / Math.min(bboxW, bboxH)

  return { placed, aspectRatio }
}

const GRID_GAP_X = 80
const GRID_GAP_Y = 100

/**
 * Folded grid: order nodes by graph flow (topological levels), then place in a grid
 * with multiple nodes per row and multiple rows for a balanced 2D layout.
 */
function runGridFoldedLayout(stepNodes, edges) {
  const idSet = new Set(stepNodes.map((n) => n.id))
  const idToNode = new Map(stepNodes.map((n) => [n.id, n]))

  const inDegree = new Map()
  const outEdges = new Map()
  for (const n of stepNodes) {
    inDegree.set(n.id, 0)
    outEdges.set(n.id, [])
  }
  for (const e of edges) {
    if (!idSet.has(e.source) || !idSet.has(e.target)) continue
    inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1)
    outEdges.get(e.source).push(e.target)
  }

  const levels = []
  const remaining = new Set(stepNodes.map((n) => n.id))
  while (remaining.size > 0) {
    const level = []
    for (const id of remaining) {
      if (inDegree.get(id) === 0) level.push(id)
    }
    if (level.length === 0) {
      levels.push(...remaining)
      break
    }
    for (const id of level) {
      remaining.delete(id)
      levels.push(id)
      for (const target of outEdges.get(id) || []) {
        if (remaining.has(target)) {
          inDegree.set(target, inDegree.get(target) - 1)
        }
      }
    }
  }
  const orderedIds = levels

  const n = orderedIds.length
  const maxPerRow = Math.max(2, Math.ceil(Math.sqrt(n)))
  const cellWidth = NODE_WIDTH + GRID_GAP_X
  const cellHeight = NODE_HEIGHT + GRID_GAP_Y
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  const placed = []

  for (let i = 0; i < orderedIds.length; i++) {
    const id = orderedIds[i]
    const node = idToNode.get(id)
    if (!node) continue
    const { width, height } = getNodeDimensions(node)
    const col = i % maxPerRow
    const row = Math.floor(i / maxPerRow)
    const x = col * cellWidth + (cellWidth - width) / 2
    const y = row * cellHeight + (cellHeight - height) / 2
    minX = Math.min(minX, x)
    minY = Math.min(minY, y)
    maxX = Math.max(maxX, x + width)
    maxY = Math.max(maxY, y + height)
    placed.push({ ...node, position: { x, y } })
  }

  const bboxW = maxX - minX || 1
  const bboxH = maxY - minY || 1
  const aspectRatio = Math.max(bboxW, bboxH) / Math.min(bboxW, bboxH)
  return { placed, aspectRatio }
}

/**
 * Compute a layout that minimises the longest dimension of the graph.
 * Tries three strategies: dagre LR, dagre TB, and a folded grid (multiple nodes per row, multiple rows).
 * Picks the result with the best (lowest) aspect ratio.
 * Lane nodes (id starting with lane_) are excluded from layout but kept in the result.
 */
export function autoArrangeNodes(nodes, edges) {
  const stepNodes = nodes.filter((n) => !n.id.startsWith('lane_'))
  const laneNodes = nodes.filter((n) => n.id.startsWith('lane_'))
  if (stepNodes.length === 0) return { nodes, positions: {} }

  const lr = runDagreLayout(stepNodes, edges, 'LR')
  const tb = runDagreLayout(stepNodes, edges, 'TB')
  const grid = runGridFoldedLayout(stepNodes, edges)

  const best = [lr, tb, grid].reduce((a, b) => (a.aspectRatio <= b.aspectRatio ? a : b))

  const positions = {}
  for (const node of best.placed) {
    positions[node.id] = { x: Math.round(node.position.x), y: Math.round(node.position.y) }
  }

  return {
    nodes: [...laneNodes, ...best.placed],
    positions,
  }
}
