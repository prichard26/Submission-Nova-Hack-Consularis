/**
 * Transform JSON graph document -> React Flow nodes and edges.
 * Lanes are rendered as non-interactive background rectangles.
 *
 * Layout: ELK (primary) with dagre fallback.
 * Edges: smart handle assignment based on relative node positions.
 */

import dagre from 'dagre'
import ELK from 'elkjs/lib/elk.bundled.js'

const elk = new ELK()

const LANE_PADDING = 40
const LANE_MIN_HEIGHT = 160
const NODE_WIDTH = 260
const NODE_HEIGHT = 120
const EVENT_SIZE = 44
const GATEWAY_SIZE = 56
const GRID_GAP_X = 80
const GRID_GAP_Y = 100

function getNodeDimensions(node) {
  const type = node.type || 'step'
  if (type === 'start' || type === 'end') return { width: EVENT_SIZE, height: EVENT_SIZE }
  if (type === 'decision') return { width: GATEWAY_SIZE, height: GATEWAY_SIZE }
  return { width: NODE_WIDTH, height: NODE_HEIGHT }
}

/* =========================================================================
   Smart handle assignment
   =========================================================================
   For each edge, compute the actual position of every source-handle and
   every target-handle on the two nodes, then pick the pair whose Manhattan
   distance is shortest (avoiding same-direction pairs that create U-bends).
   Decision nodes with multiple edges sharing a source handle get the extras
   re-routed to an adjacent handle.
   ========================================================================= */

const HANDLE_OFFSETS = {
  right:  (w, h) => ({ x: w, y: h / 2 }),
  left:   (_w, h) => ({ x: 0, y: h / 2 }),
  bottom: (w, h) => ({ x: w / 2, y: h }),
  top:    (w) => ({ x: w / 2, y: 0 }),
}

const VALID_PAIRS = [
  ['right-source', 'left-target'],
  ['right-source', 'top-target'],
  ['right-source', 'bottom-target'],
  ['left-source', 'right-target'],
  ['left-source', 'top-target'],
  ['left-source', 'bottom-target'],
  ['bottom-source', 'top-target'],
  ['bottom-source', 'left-target'],
  ['bottom-source', 'right-target'],
  ['top-source', 'bottom-target'],
  ['top-source', 'left-target'],
  ['top-source', 'right-target'],
]

function handleSide(handleId) {
  return handleId.split('-')[0]
}

function computeSmartHandles(nodes, edges) {
  const nodeInfo = new Map()
  for (const n of nodes) {
    if (n.id.startsWith('lane_')) continue
    const dim = getNodeDimensions(n)
    nodeInfo.set(n.id, { x: n.position.x, y: n.position.y, w: dim.width, h: dim.height, type: n.type || 'step' })
  }

  const sourceHandleCount = new Map()

  const assigned = edges.map((edge) => {
    const s = nodeInfo.get(edge.source)
    const t = nodeInfo.get(edge.target)
    if (!s || !t) return edge
    if (edge.sourceHandle && edge.targetHandle) return edge

    let bestDist = Infinity
    let bestSH = 'right-source'
    let bestTH = 'left-target'

    for (const [sh, th] of VALID_PAIRS) {
      const sOff = HANDLE_OFFSETS[handleSide(sh)](s.w, s.h)
      const tOff = HANDLE_OFFSETS[handleSide(th)](t.w, t.h)
      const dist = Math.abs((s.x + sOff.x) - (t.x + tOff.x))
               + Math.abs((s.y + sOff.y) - (t.y + tOff.y))
      if (dist < bestDist) {
        bestDist = dist
        bestSH = sh
        bestTH = th
      }
    }

    const key = `${edge.source}::${bestSH}`
    sourceHandleCount.set(key, (sourceHandleCount.get(key) || 0) + 1)

    return { ...edge, sourceHandle: bestSH, targetHandle: bestTH }
  })

  const seen = new Map()
  return assigned.map((edge) => {
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
}

function adjacentHandlePair(sourceHandle) {
  const map = {
    'right-source': { sourceHandle: 'bottom-source', targetHandle: 'top-target' },
    'left-source': { sourceHandle: 'top-source', targetHandle: 'bottom-target' },
    'bottom-source': { sourceHandle: 'right-source', targetHandle: 'left-target' },
    'top-source': { sourceHandle: 'left-source', targetHandle: 'right-target' },
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
    })
  }

  const stepNodes = nodes.filter((n) => !n.id.startsWith('lane_'))
  const hasPositions = stepNodes.some((n) => n.position.x !== 0 || n.position.y !== 0)
  if (hasPositions) {
    return { nodes, edges: computeSmartHandles(stepNodes, edges) }
  }

  return { nodes, edges }
}

/* =========================================================================
   ELK layout (async) — layered algorithm with crossing minimisation
   ========================================================================= */

async function runElkLayout(stepNodes, edges, direction) {
  const dimById = new Map(stepNodes.map((n) => [n.id, getNodeDimensions(n)]))
  const idSet = new Set(stepNodes.map((n) => n.id))

  const elkGraph = {
    id: 'root',
    layoutOptions: {
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
    },
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

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  const placed = stepNodes.map((node) => {
    const elkNode = childMap.get(node.id)
    if (!elkNode) return node
    const { width, height } = dimById.get(node.id)
    minX = Math.min(minX, elkNode.x)
    minY = Math.min(minY, elkNode.y)
    maxX = Math.max(maxX, elkNode.x + width)
    maxY = Math.max(maxY, elkNode.y + height)
    return { ...node, position: { x: elkNode.x, y: elkNode.y } }
  })

  const bboxW = maxX - minX || 1
  const bboxH = maxY - minY || 1
  const aspectRatio = Math.max(bboxW, bboxH) / Math.min(bboxW, bboxH)

  return { placed, aspectRatio }
}

/* =========================================================================
   Dagre layout (fallback) — improved spacing
   ========================================================================= */

function runDagreLayout(stepNodes, edges, rankdir) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({
    rankdir,
    nodesep: 60,
    ranksep: 120,
    edgesep: 25,
    marginx: 20,
    marginy: 20,
  })

  const dimensionsByNodeId = new Map(stepNodes.map((node) => [node.id, getNodeDimensions(node)]))
  const idSet = new Set(stepNodes.map((n) => n.id))
  for (const node of stepNodes) {
    const { width, height } = dimensionsByNodeId.get(node.id)
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
    const { width, height } = dimensionsByNodeId.get(node.id)
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

/* =========================================================================
   Grid layout (last resort for disconnected / edgeless graphs)
   ========================================================================= */

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

  const sortedOrder = []
  const remaining = new Set(stepNodes.map((n) => n.id))
  while (remaining.size > 0) {
    const level = []
    for (const id of remaining) {
      if (inDegree.get(id) === 0) level.push(id)
    }
    if (level.length === 0) {
      sortedOrder.push(...remaining)
      break
    }
    level.sort()
    for (const id of level) {
      remaining.delete(id)
      sortedOrder.push(id)
      for (const target of outEdges.get(id) || []) {
        if (remaining.has(target)) {
          inDegree.set(target, inDegree.get(target) - 1)
        }
      }
    }
  }
  const orderedIds = sortedOrder
  const maxPerRow = Math.max(2, Math.ceil(Math.sqrt(orderedIds.length)))
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

/* =========================================================================
   Edge crossing counter — used to break aspect-ratio ties
   ========================================================================= */

function countCrossings(placed, edges) {
  const center = new Map()
  for (const n of placed) {
    const d = getNodeDimensions(n)
    center.set(n.id, { x: n.position.x + d.width / 2, y: n.position.y + d.height / 2 })
  }

  const segs = edges
    .filter((e) => center.has(e.source) && center.has(e.target))
    .map((e) => ({ a: center.get(e.source), b: center.get(e.target) }))

  let count = 0
  for (let i = 0; i < segs.length; i++) {
    for (let j = i + 1; j < segs.length; j++) {
      if (segmentsIntersect(segs[i], segs[j])) count++
    }
  }
  return count
}

function cross(o, a, b) {
  return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)
}

function segmentsIntersect(s1, s2) {
  const d1 = cross(s2.a, s2.b, s1.a)
  const d2 = cross(s2.a, s2.b, s1.b)
  const d3 = cross(s1.a, s1.b, s2.a)
  const d4 = cross(s1.a, s1.b, s2.b)
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
      ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return true
  return false
}

function layoutScore(placed, edges) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const n of placed) {
    const d = getNodeDimensions(n)
    minX = Math.min(minX, n.position.x)
    minY = Math.min(minY, n.position.y)
    maxX = Math.max(maxX, n.position.x + d.width)
    maxY = Math.max(maxY, n.position.y + d.height)
  }
  const bboxW = maxX - minX || 1
  const bboxH = maxY - minY || 1

  const ratio = bboxW / bboxH
  const IDEAL = 1.8
  const ratioDeviation = Math.abs(Math.log2(ratio / IDEAL))

  const crossings = countCrossings(placed, edges)
  return crossings * 10 + ratioDeviation * 4
}

/* =========================================================================
   autoArrangeNodes (async)
   Tries ELK RIGHT + DOWN, falls back to improved dagre LR + TB.
   Returns { nodes, edges (with smart handles), positions }.
   ========================================================================= */

export async function autoArrangeNodes(nodes, edges) {
  const stepNodes = nodes.filter((n) => !n.id.startsWith('lane_'))
  const laneNodes = nodes.filter((n) => n.id.startsWith('lane_'))
  if (stepNodes.length === 0) return { nodes, edges, positions: {} }

  const hasEdges = edges.some((e) => {
    const ids = new Set(stepNodes.map((n) => n.id))
    return ids.has(e.source) && ids.has(e.target)
  })

  let candidates = []

  if (hasEdges) {
    try {
      const [elkR, elkD] = await Promise.all([
        runElkLayout(stepNodes, edges, 'RIGHT'),
        runElkLayout(stepNodes, edges, 'DOWN'),
      ])
      candidates.push(elkR, elkD)
    } catch (_) {
      /* ELK unavailable — fall through to dagre */
    }
  }

  if (candidates.length === 0) {
    const lr = runDagreLayout(stepNodes, edges, 'LR')
    const tb = runDagreLayout(stepNodes, edges, 'TB')
    candidates.push(lr, tb)

    if (!hasEdges) {
      candidates.push(runGridFoldedLayout(stepNodes, edges))
    }
  }

  const best = candidates.reduce((a, b) =>
    layoutScore(a.placed, edges) <= layoutScore(b.placed, edges) ? a : b,
  )

  const positions = {}
  for (const node of best.placed) {
    positions[node.id] = { x: Math.round(node.position.x), y: Math.round(node.position.y) }
  }

  const smartEdges = computeSmartHandles(best.placed, edges)

  return {
    nodes: [...laneNodes, ...best.placed],
    edges: smartEdges,
    positions,
  }
}
