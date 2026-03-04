import { memo } from 'react'
import { Handle } from '@xyflow/react'
import { HANDLE_MAP } from './nodeTypes'
import './nodes-common.css'
import './DecisionNode.css'
const TARGET_ORDER = ['left', 'right', 'top', 'bottom']
const SOURCE_ORDER = ['right', 'left', 'top', 'bottom']

function DecisionNode({ data, selected }) {
  return (
    <div className="decision-node node-shared-handles">
      {TARGET_ORDER.map((id) => {
        const { position } = HANDLE_MAP[id]
        return <Handle key={`${id}-target`} type="target" position={position} id={`${id}-target`} />
      })}
      {SOURCE_ORDER.map((id) => {
        const { position } = HANDLE_MAP[id]
        return <Handle key={`${id}-source`} type="source" position={position} id={`${id}-source`} />
      })}
      <div className={`decision-node__diamond node-shared-interactive ${selected ? 'node-shared-selected' : ''}`}>
        <span className="decision-node__label">{data.name || '?'}</span>
      </div>
    </div>
  )
}

export default memo(DecisionNode)
