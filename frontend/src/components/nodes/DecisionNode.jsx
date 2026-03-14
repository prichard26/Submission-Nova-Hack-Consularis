import { memo } from 'react'
import { NodeHandles } from './nodeTypes.jsx'
import './nodes-common.css'
import './DecisionNode.css'

function DecisionNode({ data, selected }) {
  return (
    <div className="decision-node node-shared-handles">
      <NodeHandles />
      <div className={`decision-node__diamond node-shared-interactive ${selected ? 'node-shared-selected' : ''} ${data.vizHighlighted ? 'node-shared-viz-highlight' : ''}`}>
        <span className="decision-node__label">{data.name || '?'}</span>
      </div>
    </div>
  )
}

export default memo(DecisionNode)
