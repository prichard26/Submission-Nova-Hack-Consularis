/**
 * Shared layout for process tree (landscape).
 * Used by LandscapeView and LandscapeMinimap.
 */

import dagre from 'dagre'

const NODE_WIDTH = 220
const NODE_HEIGHT = 100

/**
 * @param {{ process_tree?: { processes?: Record<string, { name?: string, children?: string[], summary?: object, category?: string }> } }} workspace
 * @returns {{ nodes: Array<{ id: string, x: number, y: number, width: number, height: number }>, edges: Array<{ id: string, source: string, target: string }> }}
 */
export function layoutTree(workspace) {
  const nodes = []
  const edges = []
  if (!workspace?.process_tree?.processes) return { nodes, edges }

  const processes = workspace.process_tree.processes
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 80, ranksep: 100 })

  for (const pid of Object.keys(processes)) {
    g.setNode(pid, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const [pid, info] of Object.entries(processes)) {
    for (const child of info.children || []) {
      if (processes[child]) {
        g.setEdge(pid, child)
      }
    }
  }

  dagre.layout(g)

  for (const [pid] of Object.entries(processes)) {
    const pos = g.node(pid)
    if (!pos) continue
    nodes.push({
      id: pid,
      x: pos.x - NODE_WIDTH / 2,
      y: pos.y - NODE_HEIGHT / 2,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    })
  }

  for (const e of g.edges()) {
    edges.push({
      id: `${e.v}->${e.w}`,
      source: e.v,
      target: e.w,
    })
  }

  return { nodes, edges }
}

