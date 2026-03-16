/** React Flow custom node for type "start" / "end": circle with Start/End label. */
import { memo } from 'react'
import { NodeHandles } from './nodeTypes.jsx'
import './nodes-common.css'
import './EventNode.css'

function EventNode({ data, selected }) {
  const isEnd = data.type === 'end'
  return (
    <div
      className={`event-node node-shared-interactive node-shared-handles ${isEnd ? 'event-node--end' : 'event-node--start'} ${selected ? 'node-shared-selected' : ''} ${data.vizHighlighted ? 'node-shared-viz-highlight' : ''}`}
    >
      <NodeHandles />
      <span className="event-node__label">{data.name || (isEnd ? 'End' : 'Start')}</span>
    </div>
  )
}

export default memo(EventNode)
