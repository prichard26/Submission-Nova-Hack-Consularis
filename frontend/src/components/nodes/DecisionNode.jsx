import { Handle, Position } from '@xyflow/react'
import './DecisionNode.css'

export default function DecisionNode({ data }) {
  return (
    <div className="decision-node">
      <Handle type="target" position={Position.Left} />
      <div className="decision-node__diamond">
        <span className="decision-node__label">{data.name || '?'}</span>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
