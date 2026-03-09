import { memo } from 'react'
import './LaneNode.css'

function LaneNode({ data, style = {} }) {
  const title = data.processName ?? data.label ?? ''
  const { width, height, ...rest } = style

  return (
    <div className="lane-node" style={{ width, height, ...rest }}>
      {title && (
        <div className="lane-node__title">{title}</div>
      )}
    </div>
  )
}

export default memo(LaneNode)
