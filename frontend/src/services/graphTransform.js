/**
 * Graph document → React Flow nodes/edges.
 *
 * Custom Sugiyama-style layered layout:
 * - No node overlap, minimal edge crossings.
 * - Serial (one node per rank): DOWN = one above the other; RIGHT = one beside the other.
 * - Parallel (multiple nodes per rank): DOWN = 2+ columns side-by-side; RIGHT = 2+ rows stacked.
 * - direction 'DOWN' (default): ranks = rows, same rank = horizontal spread.
 * - direction 'RIGHT': ranks = columns, same rank = vertical stack. Use autoArrangeNodes(..., { direction: 'RIGHT' }).
 */

const LANE_PADDING = 40
const LANE_MIN_HEIGHT = 160
const NODE_WIDTH = 260
const NODE_HEIGHT = 120
const EVENT_SIZE = 44
const GATEWAY_SIZE = 56
const DECISION_SIZE = 80

const V_SPACING = 100
const H_SPACING = 80
/** Extra gap between nodes when a rank has 2+ nodes (parallel branches) so they read as distinct columns. */
const PARALLEL_H_SPACING = 120
const STRAIGHT_ALIGN_TOLERANCE = 2

export function getNodeDimensions(node) {
  const type = node.type || 'step'
  if (type === 'start' || type === 'end') return { width: EVENT_SIZE, height: EVENT_SIZE }
  if (type === 'decision') return { width: DECISION_SIZE, height: DECISION_SIZE }
  return { width: NODE_WIDTH, height: NODE_HEIGHT }
}

/**
 * Stored/API position = center of top edge (top handle). React Flow uses top-left.
 * Convert center-of-top-edge -> top-left for rendering.
 */
export function centerToTopLeft(position, node) {
  if (!position) return { x: 0, y: 0 }
  const { width } = getNodeDimensions(node || { type: 'step' })
  return { x: position.x - width / 2, y: position.y }
}

/**
 * Convert React Flow top-left position -> center-of-top-edge for storing/API.
 */
export function topLeftToCenter(position, node) {
  if (!position) return { x: 0, y: 0 }
  const { width } = getNodeDimensions(node || { type: 'step' })
  return { x: position.x + width / 2, y: position.y }
}

/* =========================================================================
   Phase 1: Build DAG — adjacency lists, detect start/end, break cycles
   ========================================================================= */

/**
 * @param {Array<{ id: string }>} stepNodes
 * @param {Array<{ source: string, target: string }>} edges
 * @returns {{ nodeIds: string[], successors: Map<string, string[]>, predecessors: Map<string, string[]>, edgesForRanking: Array<{ source: string, target: string }>, components: string[][] }}
 */
function buildDAG(stepNodes, edges) {
  const nodeIds = stepNodes.map((n) => n.id)
  const idSet = new Set(nodeIds)
  const filteredEdges = edges.filter((e) => idSet.has(e.source) && idSet.has(e.target))

  const successors = new Map()
  const predecessors = new Map()
  for (const id of nodeIds) {
    successors.set(id, [])
    predecessors.set(id, [])
  }
  for (const e of filteredEdges) {
    if (!successors.get(e.source).includes(e.target)) {
      successors.get(e.source).push(e.target)
      predecessors.get(e.target).push(e.source)
    }
  }

  const visiting = new Set()
  const done = new Set()
  const backEdges = new Set()

  function dfs(u) {
    visiting.add(u)
    for (const v of successors.get(u) || []) {
      if (visiting.has(v)) backEdges.add(`${u}->${v}`)
      else if (!done.has(v)) dfs(v)
    }
    visiting.delete(u)
    done.add(u)
  }
  for (const id of nodeIds) {
    if (!done.has(id)) dfs(id)
  }

  const edgesForRanking = filteredEdges.filter((e) => !backEdges.has(`${e.source}->${e.target}`))

  const predForRanking = new Map()
  const succForRanking = new Map()
  for (const id of nodeIds) {
    predForRanking.set(id, [])
    succForRanking.set(id, [])
  }
  for (const e of edgesForRanking) {
    succForRanking.get(e.source).push(e.target)
    predForRanking.get(e.target).push(e.source)
  }

  const componentVisited = new Set()
  const components = []

  function componentDfs(id, comp) {
    componentVisited.add(id)
    comp.push(id)
    for (const next of succForRanking.get(id) || []) {
      if (!componentVisited.has(next)) componentDfs(next, comp)
    }
    for (const prev of predForRanking.get(id) || []) {
      if (!componentVisited.has(prev)) componentDfs(prev, comp)
    }
  }
  for (const id of nodeIds) {
    if (!componentVisited.has(id)) {
      const comp = []
      componentDfs(id, comp)
      components.push(comp)
    }
  }

  return {
    nodeIds,
    successors,
    predecessors,
    edgesForRanking,
    predForRanking,
    succForRanking,
    components,
  }
}

/* =========================================================================
   Phase 2: Assign ranks (longest path from start)
   ========================================================================= */

/**
 * @param {{ predForRanking: Map<string, string[]>, succForRanking: Map<string, string[]>, components: string[][] }} dag
 * @returns {Map<string, number>} nodeId -> rank
 */
function assignRanks(dag) {
  const ranks = new Map()
  const { predForRanking, succForRanking, components } = dag

  for (const comp of components) {
    const compSet = new Set(comp)
    const topoOrder = []
    const inDeg = new Map()
    for (const id of comp) inDeg.set(id, 0)
    for (const id of comp) {
      for (const p of predForRanking.get(id) || []) {
        if (compSet.has(p)) inDeg.set(id, (inDeg.get(id) || 0) + 1)
      }
    }
    const queue = comp.filter((id) => inDeg.get(id) === 0)
    while (queue.length > 0) {
      const u = queue.shift()
      topoOrder.push(u)
      for (const v of succForRanking.get(u) || []) {
        if (!compSet.has(v)) continue
        inDeg.set(v, (inDeg.get(v) || 0) - 1)
        if (inDeg.get(v) === 0) queue.push(v)
      }
    }

    for (const id of topoOrder) {
      const preds = (predForRanking.get(id) || []).filter((p) => compSet.has(p))
      const predRanks = preds.map((p) => ranks.get(p) ?? -1)
      const maxPred = predRanks.length === 0 ? -1 : Math.max(...predRanks)
      ranks.set(id, maxPred + 1)
    }
  }

  return ranks
}

/* =========================================================================
   Phase 3: Order nodes within ranks (barycenter heuristic, 4 sweeps)
   ========================================================================= */

/**
 * @param {Map<number, string[]>} rankToNodes rank -> [nodeId]
 * @param {{ predForRanking: Map<string, string[]>, succForRanking: Map<string, string[]> }} dag
 * @returns {Map<number, string[]>} rank -> ordered [nodeId]
 */
function orderNodesInRanks(rankToNodes, dag) {
  const { predForRanking, succForRanking } = dag
  const rankIndices = [...rankToNodes.keys()].sort((a, b) => a - b)
  const nodeToRank = new Map()
  for (const [r, ids] of rankToNodes) {
    for (const id of ids) nodeToRank.set(id, r)
  }

  let order = new Map()
  for (const r of rankIndices) {
    order.set(r, [...(rankToNodes.get(r) || [])])
  }

  function barycenterDown() {
    const next = new Map()
    for (const r of rankIndices) next.set(r, [])
    for (const r of rankIndices) {
      const nodes = order.get(r) || []
      const withBc = nodes.map((id) => {
        const preds = (predForRanking.get(id) || []).filter((p) => nodeToRank.get(p) === r - 1)
        const prevOrder = order.get(r - 1) || []
        const indices = preds.map((p) => prevOrder.indexOf(p)).filter((i) => i >= 0)
        const bc = indices.length === 0 ? 0 : indices.reduce((a, b) => a + b, 0) / indices.length
        return { id, bc }
      })
      withBc.sort((a, b) => a.bc - b.bc || (a.id < b.id ? -1 : 1))
      next.set(r, withBc.map((x) => x.id))
    }
    order = next
  }

  function barycenterUp() {
    const next = new Map()
    for (const r of rankIndices) next.set(r, [])
    for (const r of rankIndices) {
      const nodes = order.get(r) || []
      const withBc = nodes.map((id) => {
        const succs = (succForRanking.get(id) || []).filter((s) => nodeToRank.get(s) === r + 1)
        const nextOrder = order.get(r + 1) || []
        const indices = succs.map((s) => nextOrder.indexOf(s)).filter((i) => i >= 0)
        const bc = indices.length === 0 ? 0 : indices.reduce((a, b) => a + b, 0) / indices.length
        return { id, bc }
      })
      withBc.sort((a, b) => a.bc - b.bc || (a.id < b.id ? -1 : 1))
      next.set(r, withBc.map((x) => x.id))
    }
    order = next
  }

  barycenterDown()
  barycenterUp()
  barycenterDown()
  barycenterUp()

  return order
}

/* =========================================================================
   Phase 4: Assign coordinates (no overlap by construction)
   ========================================================================= */

/**
 * @param {Map<number, string[]>} rankToOrderedNodes
 * @param {Array<{ id: string, type?: string }>} stepNodes
 * @param {'DOWN'|'RIGHT'} [direction] DOWN = serial vertical, parallel horizontal. RIGHT = serial horizontal, parallel vertical.
 * @returns {Map<string, { x: number, y: number }>}
 */
function assignCoordinates(rankToOrderedNodes, stepNodes, direction = 'DOWN') {
  const dimById = new Map(stepNodes.map((n) => [n.id, getNodeDimensions(n)]))
  const rankIndices = [...rankToOrderedNodes.keys()].sort((a, b) => a - b)
  const positions = new Map()

  if (direction === 'RIGHT') {
    let currentX = 0
    for (const r of rankIndices) {
      const ids = rankToOrderedNodes.get(r) || []
      const maxWidth = ids.reduce((max, id) => {
        const d = dimById.get(id)
        return d ? Math.max(max, d.width) : max
      }, 0)
      const isParallel = ids.length > 1
      const vGap = isParallel ? PARALLEL_H_SPACING : V_SPACING
      let columnHeight = 0
      const heights = ids.map((id) => {
        const d = dimById.get(id)
        const h = d ? d.height : NODE_HEIGHT
        columnHeight += h + (columnHeight > 0 ? vGap : 0)
        return h
      })
      const startY = -columnHeight / 2
      let y = startY
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i]
        const h = heights[i]
        const d = dimById.get(id)
        const w = d ? d.width : NODE_WIDTH
        positions.set(id, { x: currentX + w / 2, y })
        y += h + vGap
      }
      currentX += maxWidth + H_SPACING
    }
    return positions
  }

  let currentY = 0
  for (const r of rankIndices) {
    const ids = rankToOrderedNodes.get(r) || []
    const maxHeight = ids.reduce((max, id) => {
      const d = dimById.get(id)
      return d ? Math.max(max, d.height) : max
    }, 0)

    const isParallel = ids.length > 1
    const hGap = isParallel ? PARALLEL_H_SPACING : H_SPACING
    let rankWidth = 0
    const widths = ids.map((id) => {
      const d = dimById.get(id)
      const w = d ? d.width : NODE_WIDTH
      rankWidth += w + (rankWidth > 0 ? hGap : 0)
      return w
    })
    const startX = -rankWidth / 2
    let x = startX
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i]
      const w = widths[i]
      positions.set(id, { x: x + w / 2, y: currentY })
      x += w + hGap
    }
    currentY += maxHeight + V_SPACING
  }

  return positions
}

/** @param {Map<string, number>} ranks @returns {Map<number, string[]>} */
function groupByRank(ranks) {
  const rankToNodes = new Map()
  for (const [id, r] of ranks) {
    if (!rankToNodes.has(r)) rankToNodes.set(r, [])
    rankToNodes.get(r).push(id)
  }
  return rankToNodes
}

/**
 * Run full Sugiyama layout. Single component: one pass. Multiple components: layout each and stack (vertically for DOWN, horizontally for RIGHT).
 * @param {Array<{ id: string, type?: string, position: { x: number, y: number }, [key: string]: unknown }>} stepNodes
 * @param {Array<{ source: string, target: string }>} edges
 * @param {{ direction?: 'DOWN'|'RIGHT' }} [options]
 * @returns {{ placed: typeof stepNodes }}
 */
function runSugiyamaLayout(stepNodes, edges, options = {}) {
  const direction = options.direction || 'DOWN'
  if (stepNodes.length === 0) return { placed: stepNodes }
  const idSet = new Set(stepNodes.map((n) => n.id))
  const hasEdges = edges.some((e) => idSet.has(e.source) && idSet.has(e.target))
  if (!hasEdges) return { placed: stepNodes }

  const dag = buildDAG(stepNodes, edges)
  const allPositions = new Map()

  if (dag.components.length === 1) {
    const ranks = assignRanks(dag)
    const rankToNodes = groupByRank(ranks)
    const ordered = orderNodesInRanks(rankToNodes, dag)
    const positions = assignCoordinates(ordered, stepNodes, direction)
    for (const [id, pos] of positions) allPositions.set(id, pos)
  } else {
    const isRight = direction === 'RIGHT'
    let offsetY = 0
    let offsetX = 0
    for (const comp of dag.components) {
      const subNodes = stepNodes.filter((n) => comp.includes(n.id))
      const subEdges = edges.filter((e) => comp.includes(e.source) && comp.includes(e.target))
      const subDag = buildDAG(subNodes, subEdges)
      const ranks = assignRanks(subDag)
      const rankToNodes = groupByRank(ranks)
      const ordered = orderNodesInRanks(rankToNodes, subDag)
      const positions = assignCoordinates(ordered, subNodes, direction)
      let compMaxY = 0
      let compMaxX = 0
      for (const [id, pos] of positions) {
        const node = subNodes.find((n) => n.id === id)
        const dim = getNodeDimensions(node || { type: 'step' })
        compMaxY = Math.max(compMaxY, pos.y + dim.height)
        compMaxX = Math.max(compMaxX, pos.x + dim.width / 2)
        allPositions.set(id, {
          x: pos.x + (isRight ? offsetX : 0),
          y: pos.y + (isRight ? 0 : offsetY),
        })
      }
      if (isRight) offsetX += compMaxX + H_SPACING
      else offsetY += compMaxY + V_SPACING
    }
  }

  const placed = stepNodes.map((n) => ({
    ...n,
    position: allPositions.get(n.id) || n.position,
  }))
  return { placed }
}

/* =========================================================================
   Phase 5: Position-based handle assignment and edge type
   ========================================================================= */

const HANDLE_OFFSETS = {
  right: (w, h) => ({ x: w, y: h / 2 }),
  left: (_w, h) => ({ x: 0, y: h / 2 }),
  bottom: (w, h) => ({ x: w / 2, y: h }),
  top: (w) => ({ x: w / 2, y: 0 }),
}

function getHandlesForEdge(sourceInfo, targetInfo) {
  const sx = sourceInfo.x + sourceInfo.w / 2
  const sy = sourceInfo.y + sourceInfo.h / 2
  const tx = targetInfo.x + targetInfo.w / 2
  const ty = targetInfo.y + targetInfo.h / 2
  const dy = ty - sy
  const dx = tx - sx
  if (dy > 0 && Math.abs(dx) <= Math.abs(dy)) return { sourceHandle: 'bottom-source', targetHandle: 'top-target' }
  if (dy < 0 && Math.abs(dx) <= Math.abs(dy)) return { sourceHandle: 'top-source', targetHandle: 'bottom-target' }
  if (dx > 0) return { sourceHandle: 'right-source', targetHandle: 'left-target' }
  return { sourceHandle: 'left-source', targetHandle: 'right-target' }
}

function getEdgeTypeFromHandles(sourceInfo, targetInfo, sourceHandle, targetHandle) {
  const side = (h) => (h ? h.split('-')[0] : '')
  const so = HANDLE_OFFSETS[side(sourceHandle)]?.(sourceInfo.w, sourceInfo.h)
  const to = HANDLE_OFFSETS[side(targetHandle)]?.(targetInfo.w, targetInfo.h)
  if (!so || !to) return 'smoothstep'
  const p1 = { x: sourceInfo.x + so.x, y: sourceInfo.y + so.y }
  const p2 = { x: targetInfo.x + to.x, y: targetInfo.y + to.y }
  const dx = Math.abs(p1.x - p2.x)
  const dy = Math.abs(p1.y - p2.y)
  if (dx <= STRAIGHT_ALIGN_TOLERANCE || dy <= STRAIGHT_ALIGN_TOLERANCE) return 'straight'
  return 'smoothstep'
}

/**
 * @param {Array<{ id: string, position: { x: number, y: number }, type?: string }>} nodes
 * @param {Array<{ id: string, source: string, target: string, [key: string]: unknown }>} edges
 * @returns {Array<{ id: string, source: string, target: string, sourceHandle: string, targetHandle: string, type: string, [key: string]: unknown }>}
 */
export function computeSmartHandles(nodes, edges, _direction = null) {
  const nodeInfo = new Map()
  for (const n of nodes) {
    if (n.id.startsWith('lane_')) continue
    const dim = getNodeDimensions(n)
    nodeInfo.set(n.id, {
      x: n.position.x,
      y: n.position.y,
      w: dim.width,
      h: dim.height,
    })
  }

  return edges.map((edge) => {
    const s = nodeInfo.get(edge.source)
    const t = nodeInfo.get(edge.target)
    if (!s || !t) return { ...edge, type: 'smoothstep' }
    const { sourceHandle, targetHandle } = edge.sourceHandle && edge.targetHandle
      ? { sourceHandle: edge.sourceHandle, targetHandle: edge.targetHandle }
      : getHandlesForEdge(s, t)
    const type = getEdgeTypeFromHandles(s, t, sourceHandle, targetHandle)
    return {
      ...edge,
      sourceHandle,
      targetHandle,
      type,
    }
  })
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
  if (!graph) return { nodes: [], edges }

  for (const step of graph.steps || []) {
    const processInfo = workspaceProcesses[step.called_element] || {}
    const storedPosition = step.position || { x: 0, y: 0 }
    const dims = getNodeDimensions(step)
    nodes.push({
      id: step.id,
      type: step.type || 'step',
      position: centerToTopLeft(storedPosition, step),
      style: { width: dims.width, height: dims.height },
      data: { ...step, workspaceInfo: processInfo },
      draggable: true,
      connectable: true,
    })
  }
  const stepNodes = nodes

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

  const laneNodesFromPositions = computeLaneNodesFromPlaced(graph, stepNodes)

  return {
    nodes: [...laneNodesFromPositions, ...stepNodes],
    edges: computeSmartHandles(stepNodes, edges, 'DOWN'),
  }
}


/* =========================================================================
   autoArrangeNodes — Sugiyama layout + position-based handles.
   Options: { graph }. Returns { nodes, edges (with handles), positions }.
   ========================================================================= */

export function autoArrangeNodes(nodes, edges, options = {}) {
  const { graph = null, direction = 'DOWN' } = options

  const stepNodes = nodes.filter((n) => !n.id.startsWith('lane_'))
  const laneNodes = nodes.filter((n) => n.id.startsWith('lane_'))
  if (stepNodes.length === 0) return { nodes, edges, positions: {} }

  const { placed } = runSugiyamaLayout(stepNodes, edges, { direction })
  const positions = {}
  const placedTopLeft = placed.map((node) => {
    const centerPos = node.position
    positions[node.id] = { x: Math.round(centerPos.x), y: Math.round(centerPos.y) }
    const dims = getNodeDimensions(node)
    return {
      ...node,
      position: centerToTopLeft(centerPos, node),
      style: { width: dims.width, height: dims.height },
    }
  })
  const smartEdges = computeSmartHandles(placedTopLeft, edges, 'DOWN')
  const outLaneNodes = graph ? computeLaneNodesFromPlaced(graph, placedTopLeft) : laneNodes

  return {
    nodes: [...outLaneNodes, ...placedTopLeft],
    edges: smartEdges,
    positions,
  }
}
