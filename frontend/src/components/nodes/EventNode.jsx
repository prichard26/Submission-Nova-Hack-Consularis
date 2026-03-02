import { Handle, Position } from '@xyflow/react'
import './EventNode.css'

export default function EventNode({ data }) {
  const isEnd = data.type === 'end'
  return (
    <div className={`event-node ${isEnd ? 'event-node--end' : 'event-node--start'}`}>
      {!isEnd && <Handle type="source" position={Position.Right} />}
      {isEnd && <Handle type="target" position={Position.Left} />}
      {!isEnd && <Handle type="target" position={Position.Left} />}
      {isEnd && <Handle type="source" position={Position.Right} />}
      <span className="event-node__label">{data.name || (isEnd ? 'End' : 'Start')}</span>
    </div>
  )
}
