import { Handle, Position } from '@xyflow/react'
import './EventNode.css'

const HANDLES = [
  { position: Position.Left, id: 'left' },
  { position: Position.Right, id: 'right' },
  { position: Position.Top, id: 'top' },
  { position: Position.Bottom, id: 'bottom' },
]
const TARGET_ORDER = ['left', 'right', 'top', 'bottom']
const SOURCE_ORDER = ['right', 'left', 'top', 'bottom']

export default function EventNode({ data, selected }) {
  const isEnd = data.type === 'end'
  return (
    <div className={`event-node ${isEnd ? 'event-node--end' : 'event-node--start'} ${selected ? 'event-node--selected' : ''}`}>
      {TARGET_ORDER.map((id) => {
        const { position } = HANDLES.find((h) => h.id === id)
        return <Handle key={`${id}-target`} type="target" position={position} id={`${id}-target`} />
      })}
      {SOURCE_ORDER.map((id) => {
        const { position } = HANDLES.find((h) => h.id === id)
        return <Handle key={`${id}-source`} type="source" position={position} id={`${id}-source`} />
      })}
      <span className="event-node__label">{data.name || (isEnd ? 'End' : 'Start')}</span>
    </div>
  )
}
