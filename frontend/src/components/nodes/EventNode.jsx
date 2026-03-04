import { memo } from 'react'
import { Handle } from '@xyflow/react'
import { HANDLE_MAP } from './nodeTypes'
import './nodes-common.css'
import './EventNode.css'
const TARGET_ORDER = ['left', 'right', 'top', 'bottom']
const SOURCE_ORDER = ['right', 'left', 'top', 'bottom']

function EventNode({ data, selected }) {
  const isEnd = data.type === 'end'
  return (
    <div
      className={`event-node node-shared-interactive node-shared-handles ${isEnd ? 'event-node--end' : 'event-node--start'} ${selected ? 'node-shared-selected' : ''}`}
    >
      {TARGET_ORDER.map((id) => {
        const { position } = HANDLE_MAP[id]
        return <Handle key={`${id}-target`} type="target" position={position} id={`${id}-target`} />
      })}
      {SOURCE_ORDER.map((id) => {
        const { position } = HANDLE_MAP[id]
        return <Handle key={`${id}-source`} type="source" position={position} id={`${id}-source`} />
      })}
      <span className="event-node__label">{data.name || (isEnd ? 'End' : 'Start')}</span>
    </div>
  )
}

export default memo(EventNode)
