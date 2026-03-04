/**
 * Graph document → React Flow nodes/edges.
 *
 * Goals:
 * - Well-designed graph: easy to read edges and elements by position.
 * - Best port: edges start/end at the handle pair that keeps them short.
 * - Straight edges when the segment is axis-aligned (no diagonal).
 * - Series (linear chain): center nodes on one vertical axis so edges are vertical.
 * - Parallel (branches): do not force one column; keep ELK’s horizontal spread.
 */

import ELK from 'elkjs/lib/elk.bundled.js'

const elk = new ELK()

const LANE_PADDING = 40
const LANE_MIN_HEIGHT = 160
const NODE_WIDTH = 260
const NODE_HEIGHT = 120
const EVENT_SIZE = 44
const GATEWAY_SIZE = 56

/* Layout spacing — used by ELK options; reserves space for edge labels (≈ label height + padding). */
const EDGE_LABEL_CLEARANCE = 24
const NODE_NODE_SPACING = 80
const LAYER_SPACING = 160
const EDGE_NODE_SPACING = 60
const EDGE_EDGE_SPACING = 24

export function getNodeDimensions(node) {
  const type = node.type || 'step'
  if (type === 'start' || type === 'end') return { width: EVENT_SIZE, height: EVENT_SIZE }
  if (type === 'decision') return { width: GATEWAY_SIZE, height: GATEWAY_SIZE }
  return { width: NODE_WIDTH, height: NODE_HEIGHT }
}

/* =========================================================================
   Smart handle assignment — best port so edges stay short
   =========================================================================
   Edges exit bottom or right, enter top or left. We pick the handle pair that
   minimizes distance and avoids collisions/crossings. For vertical flow, prefer
   bottom→top when the path is clear so joining points line up.
   ========================================================================= */

const HANDLE_OFFSETS = {
  right:  (w, h) => ({ x: w, y: h / 2 }),
  left:   (_w, h) => ({ x: 0, y: h / 2 }),
  bottom: (w, h) => ({ x: w / 2, y: h }),
  top:    (w) => ({ x: w / 2, y: 0 }),
}

/* Exit from bottom or right only; enter from top or left only. */
const ALLOWED_PAIRS = [
  ['right-source', 'left-target'],
  ['right-source', 'top-target'],
  ['bottom-source', 'top-target'],
  ['bottom-source', 'left-target'],
]

function handleSide(handleId) {
  return handleId.split('-')[0]
}

/* Cross product: (a - o) × (b - o). */
function cross(o, a, b) {
  return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)
}

function segmentsIntersect(a, b, c, d) {
  const d1 = cross(a, b, c)
  const d2 = cross(a, b, d)
  const d3 = cross(c, d, a)
  const d4 = cross(c, d, b)
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
      ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return true
  return false
}

/** True if segment (p1, p2) intersects axis-aligned rect { x, y, width, height }. */
function segmentIntersectsRect(p1, p2, rect) {
  const { x: rx, y: ry, width: rw, height: rh } = rect
  const corners = [
    { x: rx, y: ry },
    { x: rx + rw, y: ry },
    { x: rx + rw, y: ry + rh },
    { x: rx, y: ry + rh },
  ]
  for (let i = 0; i < 4; i++) {
    const c1 = corners[i]
    const c2 = corners[(i + 1) % 4]
    if (segmentsIntersect(p1, p2, c1, c2)) return true
  }
  /* Also check if segment is fully inside rect. */
  const minX = Math.min(p1.x, p2.x)
  const maxX = Math.max(p1.x, p2.x)
  const minY = Math.min(p1.y, p2.y)
  const maxY = Math.max(p1.y, p2.y)
  if (minX >= rx && maxX <= rx + rw && minY >= ry && maxY <= ry + rh) return true
  return false
}

const K_CROSSING = 200
const K_NODE_COLLISION = 300
const STRAIGHT_ALIGN_TOLERANCE = 2

/**
 * Use straight edge only when the segment is axis-aligned (vertical or horizontal)
 * and has no collisions/crossings; otherwise smoothstep.
 */
function getEdgeType(edge, allEdges, nodeInfo, getHandlePosition) {
  if (!edge.sourceHandle || !edge.targetHandle) return 'smoothstep'
  const s = nodeInfo.get(edge.source)
  const t = nodeInfo.get(edge.target)
  if (!s || !t) return 'smoothstep'
  const p1 = getHandlePosition(s, edge.sourceHandle)
  const p2 = getHandlePosition(t, edge.targetHandle)

  for (const [nid, info] of nodeInfo) {
    if (nid === edge.source || nid === edge.target) continue
    const rect = { x: info.x, y: info.y, width: info.w, height: info.h }
    if (segmentIntersectsRect(p1, p2, rect)) return 'smoothstep'
  }

  for (const other of allEdges) {
    if (other.id === edge.id || !other.sourceHandle || !other.targetHandle) continue
    const os = nodeInfo.get(other.source)
    const ot = nodeInfo.get(other.target)
    if (!os || !ot) continue
    const pa = getHandlePosition(os, other.sourceHandle)
    const pb = getHandlePosition(ot, other.targetHandle)
    if (segmentsIntersect(p1, p2, pa, pb)) return 'smoothstep'
  }

  const dx = Math.abs(p1.x - p2.x)
  const dy = Math.abs(p1.y - p2.y)
  const isVertical = dx <= STRAIGHT_ALIGN_TOLERANCE
  const isHorizontal = dy <= STRAIGHT_ALIGN_TOLERANCE
  if (!isVertical && !isHorizontal) return 'smoothstep'
  return 'straight'
}

export function computeSmartHandles(nodes, edges, direction = null) {
  const nodeInfo = new Map()
  for (const n of nodes) {
    if (n.id.startsWith('lane_')) continue
    const dim = getNodeDimensions(n)
    nodeInfo.set(n.id, { x: n.position.x, y: n.position.y, w: dim.width, h: dim.height, type: n.type || 'step' })
  }

  function getHandlePosition(info, handleId) {
    const side = handleSide(handleId)
    const off = HANDLE_OFFSETS[side](info.w, info.h)
    return { x: info.x + off.x, y: info.y + off.y }
  }

  const sourceHandleCount = new Map()
  const assigned = []

  for (const edge of edges) {
    const s = nodeInfo.get(edge.source)
    const t = nodeInfo.get(edge.target)
    if (!s || !t) {
      assigned.push(edge)
      continue
    }
    if (edge.sourceHandle && edge.targetHandle) {
      assigned.push(edge)
      const key = `${edge.source}::${edge.sourceHandle}`
      sourceHandleCount.set(key, (sourceHandleCount.get(key) || 0) + 1)
      continue
    }

    let bestScore = Infinity
    let bestSH = 'right-source'
    let bestTH = 'left-target'

    for (const [sh, th] of ALLOWED_PAIRS) {
      const p1 = getHandlePosition(s, sh)
      const p2 = getHandlePosition(t, th)
      const dist = Math.abs(p1.x - p2.x) + Math.abs(p1.y - p2.y)

      let nodeCollisions = 0
      for (const [nid, info] of nodeInfo) {
        if (nid === edge.source || nid === edge.target) continue
        const rect = { x: info.x, y: info.y, width: info.w, height: info.h }
        if (segmentIntersectsRect(p1, p2, rect)) nodeCollisions++
      }

      let crossings = 0
      for (const prev of assigned) {
        const ps = nodeInfo.get(prev.source)
        const pt = nodeInfo.get(prev.target)
        if (!ps || !pt || !prev.sourceHandle || !prev.targetHandle) continue
        const pa = getHandlePosition(ps, prev.sourceHandle)
        const pb = getHandlePosition(pt, prev.targetHandle)
        if (segmentsIntersect(p1, p2, pa, pb)) crossings++
      }

      let score = dist + K_NODE_COLLISION * nodeCollisions + K_CROSSING * crossings

      /* Prefer vertical: when DOWN and path is clear, use bottom→top so joining points superpose. */
      if (
        direction === 'DOWN' &&
        sh === 'bottom-source' &&
        th === 'top-target' &&
        nodeCollisions === 0 &&
        crossings === 0
      ) {
        score = -1
      }

      if (score < bestScore) {
        bestScore = score
        bestSH = sh
        bestTH = th
      }
    }

    const key = `${edge.source}::${bestSH}`
    sourceHandleCount.set(key, (sourceHandleCount.get(key) || 0) + 1)
    assigned.push({ ...edge, sourceHandle: bestSH, targetHandle: bestTH })
  }

  const seen = new Map()
  const afterDecision = assigned.map((edge) => {
    const info = nodeInfo.get(edge.source)
    if (!info || info.type !== 'decision') return edge

    const key = `${edge.source}::${edge.sourceHandle}`
    const total = sourceHandleCount.get(key) || 1
    if (total <= 1) return edge

    const idx = seen.get(key) || 0
    seen.set(key, idx + 1)
    if (idx === 0) return edge

    const alt = adjacentHandlePair(edge.sourceHandle)
    if (!alt) return edge
    return { ...edge, sourceHandle: alt.sourceHandle, targetHandle: alt.targetHandle }
  })

  return afterDecision.map((edge) => ({
    ...edge,
    type: getEdgeType(edge, afterDecision, nodeInfo, getHandlePosition),
  }))
}

function adjacentHandlePair(sourceHandle) {
  /* Decision-node fan-out: alternate only between right-source and bottom-source. */
  const map = {
    'right-source': { sourceHandle: 'bottom-source', targetHandle: 'top-target' },
    'bottom-source': { sourceHandle: 'right-source', targetHandle: 'left-target' },
  }
  return map[sourceHandle] || null
}

/* =========================================================================
   Lane nodes
   ========================================================================= */

function computeLaneNodes(graph) {
  const nodes = []
  if (!graph.lanes || !graph.steps) return nodes
  const stepById = new Map((graph.steps || []).map((step) => [step.id, step]))

  for (const lane of graph.lanes) {
    const laneSteps = (lane.node_refs || [])
      .map((id) => stepById.get(id))
      .filter(Boolean)
    if (laneSteps.length === 0) continue

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const step of laneSteps) {
      const pos = step.position || { x: 0, y: 0 }
      const { width, height } = getNodeDimensions(step)
      minX = Math.min(minX, pos.x)
      minY = Math.min(minY, pos.y)
      maxX = Math.max(maxX, pos.x + width)
      maxY = Math.max(maxY, pos.y + height)
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
        pointerEvents: 'none',
      },
      data: { label: lane.name },
      selectable: false,
      draggable: false,
      connectable: false,
    })
  }
  return nodes
}

/**
 * Recompute lane nodes from placed step positions (e.g. after auto-layout).
 * graph.lanes and graph.steps define lane membership; positions come from placedNodes.
 */
export function computeLaneNodesFromPlaced(graph, placedNodes) {
  const nodes = []
  if (!graph?.lanes || !graph?.steps) return nodes
  const stepById = new Map((graph.steps || []).map((step) => [step.id, step]))
  const positionById = new Map(placedNodes.map((n) => [n.id, n.position]))

  for (const lane of graph.lanes) {
    const laneStepIds = (lane.node_refs || []).filter((id) => stepById.has(id))
    if (laneStepIds.length === 0) continue

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const stepId of laneStepIds) {
      const step = stepById.get(stepId)
      const pos = positionById.get(stepId) || step?.position || { x: 0, y: 0 }
      const { width, height } = getNodeDimensions(step || { type: 'step' })
      minX = Math.min(minX, pos.x)
      minY = Math.min(minY, pos.y)
      maxX = Math.max(maxX, pos.x + width)
      maxY = Math.max(maxY, pos.y + height)
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
        pointerEvents: 'none',
      },
      data: { label: lane.name },
      selectable: false,
      draggable: false,
      connectable: false,
    })
  }
  return nodes
}

/* =========================================================================
   toReactFlowData — graph JSON → {nodes, edges}
   ========================================================================= */

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
      draggable: true,
      connectable: true,
    })
  }

  for (const flow of graph.flows || []) {
    edges.push({
      id: `${flow.from}->${flow.to}`,
      source: flow.from,
      target: flow.to,
      sourceHandle: flow.source_handle || flow.sourceHandle || undefined,
      targetHandle: flow.target_handle || flow.targetHandle || undefined,
      label: flow.label || '',
      animated: false,
      style: { stroke: 'var(--edge-stroke, #c97d3a)' },
      labelStyle: { fill: 'var(--node-text, #4a3020)', fontWeight: 600, fontSize: 11 },
      labelBgStyle: { fill: 'var(--bg-secondary, #faf8f5)', stroke: 'var(--edge-stroke, #c97d3a)' },
      labelBgPadding: [6, 4],
      labelBgBorderRadius: 4,
    })
  }

  const stepNodes = nodes.filter((n) => !n.id.startsWith('lane_'))
  const hasPositions = stepNodes.some((n) => n.position.x !== 0 || n.position.y !== 0)

  let stepNodesForOutput = stepNodes
  if (hasPositions) {
    const dimById = new Map(stepNodes.map((n) => [n.id, getNodeDimensions(n)]))
    const filteredEdges = edges.filter((e) => {
      const idSet = new Set(stepNodes.map((n) => n.id))
      return idSet.has(e.source) && idSet.has(e.target)
    })
    stepNodesForOutput = alignPlacedNodes(stepNodes, filteredEdges, dimById, 'DOWN')
  }

  return {
    nodes: [...laneNodes, ...stepNodesForOutput],
    edges: computeSmartHandles(stepNodesForOutput, edges, 'DOWN'),
  }
}

/* =========================================================================
   ELK layout (async) — Mennens-style: DOWN, process-friendly spacing
   Spacing uses constants above to keep edge labels clear of nodes/layers.
   ========================================================================= */

const MENNENS_ELK_OPTIONS = {
  'elk.direction': 'DOWN',
  'elk.spacing.nodeNode': String(NODE_NODE_SPACING),
  'elk.layered.spacing.nodeNodeBetweenLayers': String(LAYER_SPACING),
  'elk.layered.spacing.edgeNodeBetweenLayers': String(EDGE_LABEL_CLEARANCE),
  'elk.spacing.edgeNode': String(EDGE_NODE_SPACING),
  'elk.spacing.edgeEdge': String(EDGE_EDGE_SPACING),
}

async function runElkLayout(stepNodes, edges, direction, layoutOptionsOverride = {}) {
  const dimById = new Map(stepNodes.map((n) => [n.id, getNodeDimensions(n)]))
  const idSet = new Set(stepNodes.map((n) => n.id))

  const defaultOptions = {
    'elk.algorithm': 'layered',
    'elk.direction': direction,
    'elk.edgeRouting': 'ORTHOGONAL',
    'elk.spacing.nodeNode': '60',
    'elk.layered.spacing.nodeNodeBetweenLayers': '100',
    'elk.layered.spacing.edgeNodeBetweenLayers': '30',
    'elk.spacing.edgeNode': '30',
    'elk.spacing.edgeEdge': '15',
    'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
    'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
  }
  const layoutOptions = { ...defaultOptions, ...layoutOptionsOverride }

  const elkGraph = {
    id: 'root',
    layoutOptions,
    children: stepNodes.map((n) => {
      const { width, height } = dimById.get(n.id)
      return { id: n.id, width, height }
    }),
    edges: edges
      .filter((e) => idSet.has(e.source) && idSet.has(e.target))
      .map((e) => ({
        id: e.id,
        sources: [e.source],
        targets: [e.target],
      })),
  }

  const result = await elk.layout(elkGraph)
  const childMap = new Map((result.children || []).map((c) => [c.id, c]))

  let placed = stepNodes.map((node) => {
    const elkNode = childMap.get(node.id)
    if (!elkNode) return node
    return { ...node, position: { x: elkNode.x, y: elkNode.y } }
  })

  placed = alignPlacedNodes(placed, edges.filter((e) => idSet.has(e.source) && idSet.has(e.target)), dimById, direction)

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const node of placed) {
    const { width, height } = dimById.get(node.id)
    minX = Math.min(minX, node.position.x)
    minY = Math.min(minY, node.position.y)
    maxX = Math.max(maxX, node.position.x + width)
    maxY = Math.max(maxY, node.position.y + height)
  }

  const bboxW = maxX - minX || 1
  const bboxH = maxY - minY || 1
  const aspectRatio = Math.max(bboxW, bboxH) / Math.min(bboxW, bboxH)

  return { placed, aspectRatio, direction }
}

/* =========================================================================
   Post-layout alignment.
   - Series (linear chain): center nodes on one vertical axis → straight vertical edges.
   - Parallel (branches): only snap to grid; keep ELK’s horizontal spread.
   ========================================================================= */

const ALIGN_GRID_SIZE = 20

function isLinearChain(placed, edges, idSet) {
  const inDeg = new Map()
  const outDeg = new Map()
  for (const id of idSet) {
    inDeg.set(id, 0)
    outDeg.set(id, 0)
  }
  for (const e of edges) {
    if (!idSet.has(e.source) || !idSet.has(e.target)) continue
    outDeg.set(e.source, (outDeg.get(e.source) || 0) + 1)
    inDeg.set(e.target, (inDeg.get(e.target) || 0) + 1)
  }
  let starts = 0, ends = 0
  for (const id of idSet) {
    if (inDeg.get(id) === 0) starts++
    if (outDeg.get(id) === 0) ends++
    if (inDeg.get(id) > 1 || outDeg.get(id) > 1) return false
  }
  return starts === 1 && ends === 1
}

function alignPlacedNodes(placed, edges, dimById, direction = null) {
  if (placed.length === 0) return placed

  const idSet = new Set(placed.map((n) => n.id))
  const filteredEdges = edges.filter((e) => idSet.has(e.source) && idSet.has(e.target))
  const series = direction === 'DOWN' && isLinearChain(placed, filteredEdges, idSet)

  if (series) {
    const centers = placed.map((n) => {
      const { width } = dimById.get(n.id) || getNodeDimensions(n)
      return n.position.x + width / 2
    })
    centers.sort((a, b) => a - b)
    const medianCenterX = centers[Math.floor(centers.length / 2)]
    placed = placed.map((node) => {
      const { width, height } = dimById.get(node.id) || getNodeDimensions(node)
      return {
        ...node,
        position: { x: medianCenterX - width / 2, y: node.position.y },
      }
    })
  }

  const g = ALIGN_GRID_SIZE
  return placed.map((node) => {
    const { width, height } = dimById.get(node.id) || getNodeDimensions(node)
    const cx = node.position.x + width / 2
    const cy = node.position.y + height / 2
    const newCx = Math.round(cx / g) * g
    const newCy = Math.round(cy / g) * g
    return {
      ...node,
      position: { x: newCx - width / 2, y: newCy - height / 2 },
    }
  })
}

export { alignPlacedNodes }

/* =========================================================================
   autoArrangeNodes (async) — Mennens layout only
   Options: { graph, viewportAspect } (viewportAspect unused; single algorithm).
   Returns { nodes, edges (with smart handles), positions }.
   ========================================================================= */

export async function autoArrangeNodes(nodes, edges, options = {}) {
  const { graph = null } = options

  const stepNodes = nodes.filter((n) => !n.id.startsWith('lane_'))
  const laneNodes = nodes.filter((n) => n.id.startsWith('lane_'))
  if (stepNodes.length === 0) return { nodes, edges, positions: {} }

  const hasEdges = edges.some((e) => {
    const ids = new Set(stepNodes.map((n) => n.id))
    return ids.has(e.source) && ids.has(e.target)
  })

  let placed = stepNodes
  const direction = 'DOWN'

  if (hasEdges) {
    try {
      const result = await runElkLayout(stepNodes, edges, 'DOWN', MENNENS_ELK_OPTIONS)
      placed = result.placed
    } catch (err) {
      console.warn('Auto-arrange (ELK) failed, keeping current positions', err)
    }
  }

  const smartEdges = computeSmartHandles(placed, edges, direction)
  const positions = {}
  for (const node of placed) {
    positions[node.id] = { x: Math.round(node.position.x), y: Math.round(node.position.y) }
  }

  const outLaneNodes = graph ? computeLaneNodesFromPlaced(graph, placed) : laneNodes

  return {
    nodes: [...outLaneNodes, ...placed],
    edges: smartEdges,
    positions,
  }
}
