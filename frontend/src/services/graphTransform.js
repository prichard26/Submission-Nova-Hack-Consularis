/**
 * Graph document → React Flow nodes/edges.
 *
 * STRUCTURE:
 * - Public API: toReactFlowData(graph) — load graph, no layout; autoArrangeNodes(nodes, edges, opts) — run layout + handles.
 * - Layout pipeline (used only by autoArrangeNodes): buildDAG → assignRanks → groupByRank → orderNodesInRanks → assignCoordinates → centerParentsOverChildren.
 * - Handles: computeSmartHandles(nodes, edges, _, forceRecalc) — base handles + fan-out + fan-in.
 * - Lanes: computeLaneNodesFromPlaced(graph, placedNodes) for bounds from positions.
 *
 * Sugiyama: ranks = rows (DOWN) or columns (RIGHT); serial = one per rank; parallel = multiple per rank. No overlap by construction.
 */

const LANE_PADDING = 50
const LANE_MIN_HEIGHT = 150
const NODE_WIDTH = 250
const NODE_HEIGHT = 120
const EVENT_SIZE = 44
const GATEWAY_SIZE = 56
const DECISION_SIZE = 80

const V_SPACING = 75
const H_SPACING = 40

/** Extra gap between nodes when a rank has 2+ nodes (parallel branches) so they read as distinct columns. */
const PARALLEL_H_SPACING = 50
const STRAIGHT_ALIGN_TOLERANCE = 5

/** Width reserved for dummy nodes (long-edge virtualization) so the edge path gets horizontal space. */
const DUMMY_WIDTH = 300

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

  // Order for source handles so that "left" comes before "right", etc. (fixes swapped children on right branches)
  const SOURCE_HANDLE_ORDER = { 'left-source': 0, 'right-source': 1, 'top-source': 2, 'bottom-source': 3 }
  const bySourceThenHandle = [...edgesForRanking].sort((a, b) => {
    if (a.source !== b.source) return 0
    const ha = SOURCE_HANDLE_ORDER[a.sourceHandle] ?? 99
    const hb = SOURCE_HANDLE_ORDER[b.sourceHandle] ?? 99
    return ha - hb
  })

  const predForRanking = new Map()
  const succForRanking = new Map()
  for (const id of nodeIds) {
    predForRanking.set(id, [])
    succForRanking.set(id, [])
  }
  for (const e of bySourceThenHandle) {
    const succ = succForRanking.get(e.source)
    if (!succ.includes(e.target)) succ.push(e.target)
    const preds = predForRanking.get(e.target)
    if (!preds.includes(e.source)) preds.push(e.source)
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

  return { predForRanking, succForRanking, components }
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
  for (const r of rankIndices) order.set(r, [])
  const placed = new Set()
  function dfsOrder(id) {
    if (placed.has(id)) return
    placed.add(id)
    const r = nodeToRank.get(id)
    if (r !== undefined) order.get(r).push(id)
    for (const child of succForRanking.get(id) || []) dfsOrder(child)
  }
  const roots = [...(rankToNodes.get(rankIndices[0]) || [])]
  for (const root of roots) dfsOrder(root)
  for (const r of rankIndices) {
    for (const id of rankToNodes.get(r) || []) {
      if (!placed.has(id)) {
        placed.add(id)
        order.get(r).push(id)
      }
    }
  }

  function barycenterDown() {
    const next = new Map()
    for (const r of rankIndices) next.set(r, [])
    for (const r of rankIndices) {
      const nodes = order.get(r) || []
      const withBc = nodes.map((id) => {
        const preds = (predForRanking.get(id) || []).filter((p) => nodeToRank.get(p) === r - 1)
        const prevOrder = next.get(r - 1) || []
        const indices = preds.map((p) => prevOrder.indexOf(p)).filter((i) => i >= 0)
        const bc = indices.length === 0 ? 0 : indices.reduce((a, b) => a + b, 0) / indices.length
        return { id, bc }
      })
      withBc.sort((a, b) => a.bc - b.bc || 0)
      next.set(r, withBc.map((x) => x.id))
    }
    order = next
  }

  function barycenterUp() {
    const next = new Map()
    for (const r of rankIndices) next.set(r, [])
    for (const r of [...rankIndices].reverse()) {
      const nodes = order.get(r) || []
      const withBc = nodes.map((id) => {
        const succs = (succForRanking.get(id) || []).filter((s) => nodeToRank.get(s) === r + 1)
        const nextOrder = next.get(r + 1) || []
        const indices = succs.map((s) => nextOrder.indexOf(s)).filter((i) => i >= 0)
        const bc = indices.length === 0 ? 0 : indices.reduce((a, b) => a + b, 0) / indices.length
        return { id, bc }
      })
      withBc.sort((a, b) => a.bc - b.bc || 0)
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
  function dim(id) {
    const d = dimById.get(id)
    if (d) return d
    if (id.startsWith('__dummy__')) return { width: DUMMY_WIDTH, height: 0 }
    return { width: NODE_WIDTH, height: NODE_HEIGHT }
  }
  const rankIndices = [...rankToOrderedNodes.keys()].sort((a, b) => a - b)
  const positions = new Map()

  if (direction === 'RIGHT') {
    let currentX = 0
    for (const r of rankIndices) {
      const ids = rankToOrderedNodes.get(r) || []
      const maxWidth = ids.reduce((max, id) => Math.max(max, dim(id).width), 0)
      const isParallel = ids.length > 1
      const vGap = isParallel ? PARALLEL_H_SPACING : V_SPACING
      let columnHeight = 0
      const heights = ids.map((id) => {
        const h = dim(id).height
        columnHeight += h + (columnHeight > 0 ? vGap : 0)
        return h
      })
      const startY = -columnHeight / 2
      let y = startY
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i]
        const h = heights[i]
        const w = dim(id).width
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
    const maxHeight = ids.reduce((max, id) => Math.max(max, dim(id).height), 0)

    const isParallel = ids.length > 1
    const hGap = isParallel ? PARALLEL_H_SPACING : H_SPACING
    let rankWidth = 0
    const widths = ids.map((id) => {
      const w = dim(id).width
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

/**
 * Insert dummy nodes for edges that span more than one rank, so the layout reserves horizontal space
 * at each intermediate rank and long edges are not hidden behind centered nodes.
 * Mutates ranks and dag; returns the set of dummy node IDs (to strip from output later).
 * @param {Map<string, number>} ranks
 * @param {{ predForRanking: Map<string, string[]>, succForRanking: Map<string, string[]> }} dag
 * @param {Array<{ source: string, target: string }>} edges
 * @returns {Set<string>}
 */
function insertDummyNodes(ranks, dag, edges) {
  const dummyIds = new Set()
  for (const edge of edges) {
    const sRank = ranks.get(edge.source)
    const tRank = ranks.get(edge.target)
    if (sRank == null || tRank == null || tRank - sRank <= 1) continue

    let prev = edge.source
    for (let r = sRank + 1; r < tRank; r++) {
      const dId = `__dummy__${edge.source}__${edge.target}__${r}`
      dummyIds.add(dId)
      ranks.set(dId, r)
      if (!dag.succForRanking.has(dId)) dag.succForRanking.set(dId, [])
      dag.predForRanking.set(dId, [prev])
      dag.succForRanking.get(prev).push(dId)
      prev = dId
    }
    dag.succForRanking.get(prev).push(edge.target)
    const tgtPreds = dag.predForRanking.get(edge.target)
    if (tgtPreds) tgtPreds.push(prev)

    const srcSuccs = dag.succForRanking.get(edge.source)
    const idx1 = srcSuccs.indexOf(edge.target)
    if (idx1 >= 0) srcSuccs.splice(idx1, 1)
    const idx2 = tgtPreds ? tgtPreds.indexOf(edge.source) : -1
    if (idx2 >= 0) tgtPreds.splice(idx2, 1)
  }
  return dummyIds
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
 * Second pass: center each parent that has 2+ children over the horizontal (DOWN) or vertical (RIGHT) span of those children.
 * Process from bottom rank to top so children positions are final when we adjust the parent.
 * @param {Map<string, { x: number, y: number }>} positions mutated in place
 * @param {Map<number, string[]>} rankToNodes
 * @param {Map<string, string[]>} succForRanking
 * @param {'DOWN'|'RIGHT'} direction
 */
function centerParentsOverChildren(positions, rankToNodes, succForRanking, direction) {
  const rankIndices = [...rankToNodes.keys()].sort((a, b) => b - a)
  for (const r of rankIndices) {
    for (const id of rankToNodes.get(r) || []) {
      const succs = (succForRanking.get(id) || []).filter((s) => positions.has(s))
      if (succs.length < 2) continue
      const pos = positions.get(id)
      if (direction === 'RIGHT') {
        const avgY = succs.reduce((sum, s) => sum + positions.get(s).y, 0) / succs.length
        positions.set(id, { ...pos, y: avgY })
      } else {
        const avgX = succs.reduce((sum, s) => sum + positions.get(s).x, 0) / succs.length
        positions.set(id, { ...pos, x: avgX })
      }
    }
  }
}

/**
 * Align start and end nodes to the same horizontal (DOWN) or vertical (RIGHT) coordinate so they sit one above the other.
 * @param {Map<string, { x: number, y: number }>} positions mutated in place
 * @param {Array<{ id: string, type?: string }>} stepNodes
 * @param {'DOWN'|'RIGHT'} direction
 */
function alignStartAndEnd(positions, stepNodes, direction) {
  const startEndIds = stepNodes
    .filter((n) => (n.type === 'start' || n.type === 'end') && positions.has(n.id))
    .map((n) => n.id)
  if (startEndIds.length < 2) return
  const coords = startEndIds.map((id) => (direction === 'DOWN' ? positions.get(id).x : positions.get(id).y))
  const aligned = coords.reduce((a, b) => a + b, 0) / coords.length
  for (const id of startEndIds) {
    const pos = positions.get(id)
    if (direction === 'DOWN') positions.set(id, { ...pos, x: aligned })
    else positions.set(id, { ...pos, y: aligned })
  }
}

/**
 * Layout one connected component: ranks → order → coordinates → center parents. Returns id → position (center-of-top-edge).
 */
function layoutOneComponent(stepNodes, edges, direction) {
  const dag = buildDAG(stepNodes, edges)
  const ranks = assignRanks(dag)
  const dummyIds = insertDummyNodes(ranks, dag, edges)
  const rankToNodes = groupByRank(ranks)
  const ordered = orderNodesInRanks(rankToNodes, dag)
  const positions = assignCoordinates(ordered, stepNodes, direction)
  centerParentsOverChildren(positions, rankToNodes, dag.succForRanking, direction)
  alignStartAndEnd(positions, stepNodes, direction)
  for (const id of dummyIds) positions.delete(id)
  return { positions, ranks }
}

/**
 * Run full Sugiyama layout. One component: one pass. Multiple: layout each component and stack (DOWN = vertical, RIGHT = horizontal).
 */
function runSugiyamaLayout(stepNodes, edges, options = {}) {
  const direction = options.direction || 'DOWN'
  if (stepNodes.length === 0) return { placed: stepNodes, rankMap: new Map() }
  const idSet = new Set(stepNodes.map((n) => n.id))
  if (!edges.some((e) => idSet.has(e.source) && idSet.has(e.target))) return { placed: stepNodes, rankMap: new Map() }

  const dag = buildDAG(stepNodes, edges)
  const allPositions = new Map()
  const allRanks = new Map()

  if (dag.components.length === 1) {
    const { positions, ranks } = layoutOneComponent(stepNodes, edges, direction)
    for (const [id, pos] of positions) allPositions.set(id, pos)
    for (const [id, rank] of ranks) allRanks.set(id, rank)
  } else {
    const isRight = direction === 'RIGHT'
    let offsetY = 0
    let offsetX = 0
    for (const comp of dag.components) {
      const subNodes = stepNodes.filter((n) => comp.includes(n.id))
      const subEdges = edges.filter((e) => comp.includes(e.source) && comp.includes(e.target))
      const { positions, ranks } = layoutOneComponent(subNodes, subEdges, direction)
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
      for (const [id, rank] of ranks) allRanks.set(id, rank)
      if (isRight) offsetX += compMaxX + H_SPACING
      else offsetY += compMaxY + V_SPACING
    }
  }

  return {
    placed: stepNodes.map((n) => ({ ...n, position: allPositions.get(n.id) || n.position })),
    rankMap: allRanks,
  }
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

function classifyEdge(edge, rankMap, sourceInfo, targetInfo, direction) {
  if (edge.source === edge.target) return 'self-loop'
  if (rankMap && rankMap.has(edge.source) && rankMap.has(edge.target)) {
    const sRank = rankMap.get(edge.source)
    const tRank = rankMap.get(edge.target)
    if (sRank < tRank) return 'forward'
    if (sRank > tRank) return 'back'
    return 'same-rank'
  }

  if (direction === 'RIGHT') {
    if (sourceInfo.x < targetInfo.x) return 'forward'
    if (sourceInfo.x > targetInfo.x) return 'back'
    return 'same-rank'
  }
  if (sourceInfo.y < targetInfo.y) return 'forward'
  if (sourceInfo.y > targetInfo.y) return 'back'
  return 'same-rank'
}

function assignPrimaryHandles(edge, classification, direction, sourceInfo, targetInfo) {
  if (classification === 'self-loop') {
    return { sourceHandle: 'right-source', targetHandle: 'top-target' }
  }

  if (direction === 'RIGHT') {
    if (classification === 'forward') return { sourceHandle: 'right-source', targetHandle: 'left-target' }
    if (classification === 'back') return { sourceHandle: 'left-source', targetHandle: 'right-target' }
    const sourceIsAbove = sourceInfo.y <= targetInfo.y
    return sourceIsAbove
      ? { sourceHandle: 'bottom-source', targetHandle: 'top-target' }
      : { sourceHandle: 'top-source', targetHandle: 'bottom-target' }
  }

  if (classification === 'forward') return { sourceHandle: 'bottom-source', targetHandle: 'top-target' }
  if (classification === 'back') return { sourceHandle: 'top-source', targetHandle: 'bottom-target' }
  const sourceIsLeft = sourceInfo.x <= targetInfo.x
  return sourceIsLeft
    ? { sourceHandle: 'right-source', targetHandle: 'left-target' }
    : { sourceHandle: 'left-source', targetHandle: 'right-target' }
}

function getCrossAxisValue(node, handle, direction) {
  const side = (handle ? handle.split('-')[0] : '')
  const offset = HANDLE_OFFSETS[side]?.(node.w, node.h)
  if (!offset) return direction === 'RIGHT' ? node.y + node.h / 2 : node.x + node.w / 2
  if (direction === 'RIGHT') return node.y + offset.y
  return node.x + offset.x
}

function getPreferredSide(handle) {
  return handle ? handle.split('-')[0] : 'bottom'
}

function getSourceCandidatesBySide(side) {
  if (side === 'bottom') return ['left-source', 'bottom-source', 'right-source']
  if (side === 'top') return ['left-source', 'top-source', 'right-source']
  if (side === 'right') return ['top-source', 'right-source', 'bottom-source']
  return ['top-source', 'left-source', 'bottom-source']
}

function getTargetCandidatesBySide(side) {
  if (side === 'top') return ['left-target', 'top-target', 'right-target']
  if (side === 'bottom') return ['left-target', 'bottom-target', 'right-target']
  if (side === 'left') return ['top-target', 'left-target', 'bottom-target']
  return ['top-target', 'right-target', 'bottom-target']
}

function selectDistributedCandidate(candidates, index, total) {
  if (!candidates.length) return null
  if (total <= 1) return candidates[Math.floor(candidates.length / 2)]
  const ratio = index / (total - 1)
  const candidateIndex = Math.round(ratio * (candidates.length - 1))
  return candidates[candidateIndex]
}

function distributeBoundaryHandles(result, nodeInfo, direction) {
  const bySourceSide = new Map()
  const byTargetSide = new Map()

  for (let i = 0; i < result.length; i++) {
    const edge = result[i]
    const sourceNode = nodeInfo.get(edge.source)
    const targetNode = nodeInfo.get(edge.target)
    if (!sourceNode || !targetNode) continue
    const sourceSide = getPreferredSide(edge.sourceHandle)
    const targetSide = getPreferredSide(edge.targetHandle)
    const sourceKey = `${edge.source}::${sourceSide}`
    const targetKey = `${edge.target}::${targetSide}`
    if (!bySourceSide.has(sourceKey)) bySourceSide.set(sourceKey, [])
    if (!byTargetSide.has(targetKey)) byTargetSide.set(targetKey, [])
    bySourceSide.get(sourceKey).push(i)
    byTargetSide.get(targetKey).push(i)
  }

  for (const [key, indices] of bySourceSide) {
    if (indices.length < 2) continue
    const [, side] = key.split('::')
    const candidates = getSourceCandidatesBySide(side)
    const sorted = [...indices].sort((a, b) => {
      const ta = nodeInfo.get(result[a].target)
      const tb = nodeInfo.get(result[b].target)
      const av = direction === 'RIGHT' ? (ta?.y ?? 0) : (ta?.x ?? 0)
      const bv = direction === 'RIGHT' ? (tb?.y ?? 0) : (tb?.x ?? 0)
      return av - bv
    })
    for (let index = 0; index < sorted.length; index++) {
      const edgeIndex = sorted[index]
      const distributed = selectDistributedCandidate(candidates, index, sorted.length)
      if (distributed) result[edgeIndex].sourceHandle = distributed
    }
  }

  for (const [key, indices] of byTargetSide) {
    if (indices.length < 2) continue
    const [, side] = key.split('::')
    const candidates = getTargetCandidatesBySide(side)
    const sorted = [...indices].sort((a, b) => {
      const sa = nodeInfo.get(result[a].source)
      const sb = nodeInfo.get(result[b].source)
      const av = direction === 'RIGHT' ? (sa?.y ?? 0) : (sa?.x ?? 0)
      const bv = direction === 'RIGHT' ? (sb?.y ?? 0) : (sb?.x ?? 0)
      return av - bv
    })
    for (let index = 0; index < sorted.length; index++) {
      const edgeIndex = sorted[index]
      const distributed = selectDistributedCandidate(candidates, index, sorted.length)
      if (distributed) result[edgeIndex].targetHandle = distributed
    }
  }
}

function pairCrosses(edgeA, edgeB, nodeInfo, direction) {
  const sourceA = nodeInfo.get(edgeA.source)
  const sourceB = nodeInfo.get(edgeB.source)
  const targetA = nodeInfo.get(edgeA.target)
  const targetB = nodeInfo.get(edgeB.target)
  if (!sourceA || !sourceB || !targetA || !targetB) return false

  if (edgeA.source === edgeB.source) {
    const sourceAxisA = getCrossAxisValue(sourceA, edgeA.sourceHandle, direction)
    const sourceAxisB = getCrossAxisValue(sourceB, edgeB.sourceHandle, direction)
    const targetAxisA = getCrossAxisValue(targetA, edgeA.targetHandle, direction)
    const targetAxisB = getCrossAxisValue(targetB, edgeB.targetHandle, direction)
    return (sourceAxisA - sourceAxisB) * (targetAxisA - targetAxisB) < 0
  }

  if (edgeA.target === edgeB.target) {
    const sourceAxisA = getCrossAxisValue(sourceA, edgeA.sourceHandle, direction)
    const sourceAxisB = getCrossAxisValue(sourceB, edgeB.sourceHandle, direction)
    const targetAxisA = getCrossAxisValue(targetA, edgeA.targetHandle, direction)
    const targetAxisB = getCrossAxisValue(targetB, edgeB.targetHandle, direction)
    return (sourceAxisA - sourceAxisB) * (targetAxisA - targetAxisB) < 0
  }

  return false
}

function reduceCrossingsWithSwaps(result, nodeInfo, direction) {
  for (let i = 0; i < result.length; i++) {
    for (let j = i + 1; j < result.length; j++) {
      const a = result[i]
      const b = result[j]
      if (a.source !== b.source && a.target !== b.target) continue
      const crosses = pairCrosses(a, b, nodeInfo, direction)
      if (!crosses) continue

      if (a.source === b.source) {
        const oldA = a.sourceHandle
        const oldB = b.sourceHandle
        a.sourceHandle = oldB
        b.sourceHandle = oldA
        if (pairCrosses(a, b, nodeInfo, direction)) {
          a.sourceHandle = oldA
          b.sourceHandle = oldB
        }
      } else if (a.target === b.target) {
        const oldA = a.targetHandle
        const oldB = b.targetHandle
        a.targetHandle = oldB
        b.targetHandle = oldA
        if (pairCrosses(a, b, nodeInfo, direction)) {
          a.targetHandle = oldA
          b.targetHandle = oldB
        }
      }
    }
  }
}

function applyDoglegFallback(result, nodeInfo, direction) {
  for (let i = 0; i < result.length; i++) {
    for (let j = i + 1; j < result.length; j++) {
      const a = result[i]
      const b = result[j]
      if (!pairCrosses(a, b, nodeInfo, direction)) continue

      const sourceA = nodeInfo.get(a.source)
      const targetA = nodeInfo.get(a.target)
      if (!sourceA || !targetA) continue

      if (direction === 'RIGHT') {
        a.sourceHandle = (targetA.y >= sourceA.y) ? 'bottom-source' : 'top-source'
      } else {
        a.sourceHandle = (targetA.x >= sourceA.x) ? 'right-source' : 'left-source'
      }
      a.type = 'smoothstep'
    }
  }
}

function detectAndSwapCrossings(result, nodeInfo, direction) {
  reduceCrossingsWithSwaps(result, nodeInfo, direction)
  applyDoglegFallback(result, nodeInfo, direction)
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
export function computeSmartHandles(nodes, edges, direction = 'DOWN', forceRecalc = false, rankMap = null) {
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

  const nodeById = new Map(nodes.filter((n) => !n.id.startsWith('lane_')).map((n) => [n.id, n]))

  // First pass: classify and assign direction-aware primary handles.
  const result = edges.map((edge) => {
    const s = nodeInfo.get(edge.source)
    const t = nodeInfo.get(edge.target)
    if (!s || !t) return { ...edge, type: 'smoothstep' }
    const keepExisting = !forceRecalc && edge.sourceHandle && edge.targetHandle
    let sourceHandle, targetHandle
    if (keepExisting) {
      sourceHandle = edge.sourceHandle
      targetHandle = edge.targetHandle
    } else {
      const sourceNode = nodeById.get(edge.source)
      const targetNode = nodeById.get(edge.target)
      const isStartToEnd = sourceNode?.type === 'start' && targetNode?.type === 'end'
      if (isStartToEnd) {
        // Prefer side handles so the line is not forced vertical when start/end are aligned.
        if (direction === 'DOWN') {
          sourceHandle = 'right-source'
          targetHandle = 'left-target'
        } else {
          sourceHandle = 'bottom-source'
          targetHandle = 'top-target'
        }
      } else {
        const assigned = assignPrimaryHandles(edge, classifyEdge(edge, rankMap, s, t, direction), direction, s, t)
        sourceHandle = assigned.sourceHandle
        targetHandle = assigned.targetHandle
      }
    }
    const type = getEdgeTypeFromHandles(s, t, sourceHandle, targetHandle)
    return {
      ...edge,
      sourceHandle,
      targetHandle,
      type,
    }
  })

  // Second pass: boundary fan-out / fan-in distribution.
  distributeBoundaryHandles(result, nodeInfo, direction)

  // Third pass: crossing minimization and longer-path fallback.
  detectAndSwapCrossings(result, nodeInfo, direction)

  // Last pass: update edge type from finalized handles.
  for (let i = 0; i < result.length; i++) {
    const e = result[i]
    const s = nodeInfo.get(e.source)
    const t = nodeInfo.get(e.target)
    if (!s || !t) continue
    result[i].type = getEdgeTypeFromHandles(s, t, e.sourceHandle, e.targetHandle)
  }

  return result
}

/* =========================================================================
   Lane nodes
   ========================================================================= */

function computeLaneNodes(graph) {
  const nodes = []
  const stepsOrNodes = graph.nodes || graph.steps
  if (!graph.lanes || !stepsOrNodes) return nodes
  const stepById = new Map(stepsOrNodes.map((s) => [s.id, s]))

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
 * graph.lanes and graph.nodes (or graph.steps) define lane membership; positions come from placedNodes.
 */
export function computeLaneNodesFromPlaced(graph, placedNodes, options = {}) {
  const { processDisplayName } = options
  const nodes = []
  const stepsOrNodes = graph?.nodes || graph?.steps
  if (!graph?.lanes || !stepsOrNodes) return nodes
  const stepById = new Map(stepsOrNodes.map((s) => [s.id, s]))
  const positionById = new Map(placedNodes.map((n) => [n.id, n.position]))
  let isFirst = true

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

    const width = maxX - minX + LANE_PADDING * 2
    const height = Math.max(maxY - minY + LANE_PADDING * 2, LANE_MIN_HEIGHT)
    const useProcessName = isFirst && processDisplayName
    isFirst = false

    nodes.push({
      id: `lane_${lane.id}`,
      type: 'lane',
      position: { x: minX - LANE_PADDING, y: minY - LANE_PADDING },
      style: {
        width,
        height,
        zIndex: -1,
      },
      data: {
        label: lane.name,
        ...(useProcessName && { processName: processDisplayName }),
      },
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

export function toReactFlowData(graph, workspaceProcesses = {}, options = {}) {
  const { processDisplayName } = options
  const nodes = []
  const edges = []
  if (!graph) return { nodes: [], edges }

  const stepsOrNodes = graph.nodes || graph.steps || []
  const flowsOrEdges = graph.edges || graph.flows || []

  for (const step of stepsOrNodes) {
    const pageId = step.type === 'subprocess' ? step.id : step.called_element
    const processInfo = workspaceProcesses[pageId] || {}
    const storedPosition = step.position || { x: 0, y: 0 }
    const dims = getNodeDimensions(step)
    const attrs = step.attributes || {}
    nodes.push({
      id: step.id,
      type: step.type || 'step',
      position: centerToTopLeft(storedPosition, step),
      style: { width: dims.width, height: dims.height },
      data: {
        ...step,
        ...attrs,
        name: step.name ?? attrs.name,
        workspaceInfo: processInfo,
        called_element: pageId,
      },
      draggable: true,
      connectable: true,
    })
  }
  const stepNodes = nodes

  for (const flow of flowsOrEdges) {
    const fromId = flow.from ?? flow.source
    const toId = flow.to ?? flow.target
    edges.push({
      id: `${fromId}->${toId}`,
      source: fromId,
      target: toId,
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

  const laneNodesFromPositions = computeLaneNodesFromPlaced(graph, stepNodes, { processDisplayName })
  const direction = options.direction || 'DOWN'

  return {
    nodes: [...laneNodesFromPositions, ...stepNodes],
    edges: computeSmartHandles(stepNodes, edges, direction),
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

  const { processDisplayName } = options
  const { placed, rankMap } = runSugiyamaLayout(stepNodes, edges, { direction })
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
  // Force handle recalc so gates match new positions (do not keep pre-arrange sourceHandle/targetHandle).
  const smartEdges = computeSmartHandles(placedTopLeft, edges, direction, true, rankMap)
  const outLaneNodes = graph
    ? computeLaneNodesFromPlaced(graph, placedTopLeft, { processDisplayName })
    : laneNodes

  return {
    nodes: [...outLaneNodes, ...placedTopLeft],
    edges: smartEdges,
    positions,
  }
}
