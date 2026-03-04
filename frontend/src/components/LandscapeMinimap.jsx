import { useMemo } from 'react'
import { layoutTree } from '../services/landscapeLayout'
import './LandscapeMinimap.css'

const PAD = 8
const WIDTH = 180
const HEIGHT = 120

/**
 * Minimap showing the process landscape (tree) with the current process highlighted.
 * Replaces the default React Flow minimap so users see where they are in the workspace.
 */
export default function LandscapeMinimap({ workspace, currentProcessId, onProcessSelect }) {
  const { viewBox, transform, nodes, edges } = useMemo(() => {
    const { nodes: layoutNodes, edges: layoutEdges } = layoutTree(workspace || {})
    if (layoutNodes.length === 0) {
      return {
        viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
        transform: '',
        nodes: [],
        edges: [],
      }
    }

    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const n of layoutNodes) {
      minX = Math.min(minX, n.x)
      minY = Math.min(minY, n.y)
      maxX = Math.max(maxX, n.x + n.width)
      maxY = Math.max(maxY, n.y + n.height)
    }
    const contentW = maxX - minX
    const contentH = maxY - minY
    const scale = Math.min(
      (WIDTH - 2 * PAD) / contentW,
      (HEIGHT - 2 * PAD) / contentH,
    )
    const tx = PAD - minX * scale
    const ty = PAD - minY * scale

    const nodeMap = new Map(layoutNodes.map((n) => [n.id, n]))
    const edgesWithPoints = layoutEdges.map((e) => {
      const a = nodeMap.get(e.source)
      const b = nodeMap.get(e.target)
      if (!a || !b) return null
      return {
        id: e.id,
        x1: a.x + a.width / 2,
        y1: a.y + a.height / 2,
        x2: b.x + b.width / 2,
        y2: b.y + b.height / 2,
      }
    }).filter(Boolean)

    return {
      viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
      transform: `translate(${tx},${ty}) scale(${scale})`,
      nodes: layoutNodes,
      edges: edgesWithPoints,
    }
  }, [workspace, currentProcessId])

  if (!workspace?.process_tree?.processes || Object.keys(workspace.process_tree.processes).length === 0) {
    return (
      <div
        className="landscape-minimap landscape-minimap--empty"
        style={{ width: WIDTH, height: HEIGHT }}
        title="Landscape (no processes)"
      >
        <span className="landscape-minimap__placeholder">No processes</span>
      </div>
    )
  }

  return (
    <div
      className="landscape-minimap"
      style={{ width: WIDTH, height: HEIGHT }}
      title="Landscape — current process highlighted"
    >
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="landscape-minimap__svg"
        preserveAspectRatio="xMidYMid meet"
      >
        <g transform={transform}>
          {/* Edges */}
          {edges.map((e) => (
            <line
              key={e.id}
              x1={e.x1}
              y1={e.y1}
              x2={e.x2}
              y2={e.y2}
              className="landscape-minimap__edge"
            />
          ))}
          {/* Nodes */}
          {nodes.map((n) => {
            const isCurrent = n.id === currentProcessId
            return (
              <g key={n.id}>
                <rect
                  x={n.x}
                  y={n.y}
                  width={n.width}
                  height={n.height}
                  rx={4}
                  className={
                    isCurrent
                      ? 'landscape-minimap__node landscape-minimap__node--current'
                      : 'landscape-minimap__node'
                  }
                  onClick={() => onProcessSelect?.(n.id)}
                />
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
}
