import { useMemo, useState, useCallback } from 'react'
import { layoutTree } from '../services/landscapeLayout'
import './LandscapeMinimap.css'

const PAD = 8
const WIDTH = 180
const HEIGHT = 120
const TOOLTIP_OFFSET = 12

/**
 * Minimap showing the process landscape (tree) with the current process highlighted.
 * Replaces the default React Flow minimap so users see where they are in the workspace.
 */
export default function LandscapeMinimap({ workspace, currentProcessId, onProcessSelect }) {
  const [hoveredNodeId, setHoveredNodeId] = useState(null)
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 })

  const handleNodeEnter = useCallback((nodeId, e) => {
    setHoveredNodeId(nodeId)
    setTooltipPosition({ x: e.clientX, y: e.clientY })
  }, [])

  const handleNodeMove = useCallback((e) => {
    if (hoveredNodeId) {
      setTooltipPosition({ x: e.clientX, y: e.clientY })
    }
  }, [hoveredNodeId])

  const handleNodeLeave = useCallback(() => {
    setHoveredNodeId(null)
  }, [])

  const { transform, nodes, edges } = useMemo(() => {
    const { nodes: layoutNodes, edges: layoutEdges } = layoutTree(workspace || {})
    if (layoutNodes.length === 0) {
      return { transform: '', nodes: [], edges: [] }
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
    const scaledW = contentW * scale
    const scaledH = contentH * scale
    const tx = (WIDTH - scaledW) / 2 - minX * scale
    const ty = (HEIGHT - scaledH) / 2 - minY * scale

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
      transform: `translate(${tx},${ty}) scale(${scale})`,
      nodes: layoutNodes,
      edges: edgesWithPoints,
    }
  }, [workspace])

  if (!workspace?.process_tree?.processes || Object.keys(workspace.process_tree.processes).length === 0) {
    return (
      <div
        className="landscape-minimap landscape-minimap--empty"
        title="Landscape (no processes)"
      >
        <span className="landscape-minimap__placeholder">No processes</span>
      </div>
    )
  }

  const processes = workspace?.process_tree?.processes || {}

  return (
    <div className="landscape-minimap">
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
              <g
                key={n.id}
                onMouseEnter={(e) => handleNodeEnter(n.id, e)}
                onMouseMove={handleNodeMove}
                onMouseLeave={handleNodeLeave}
              >
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
      {hoveredNodeId && (
        <div
          className="landscape-minimap__tooltip"
          style={{
            left: tooltipPosition.x + TOOLTIP_OFFSET,
            top: tooltipPosition.y + TOOLTIP_OFFSET,
          }}
        >
          {processes[hoveredNodeId]?.name || hoveredNodeId}
        </div>
      )}
    </div>
  )
}
