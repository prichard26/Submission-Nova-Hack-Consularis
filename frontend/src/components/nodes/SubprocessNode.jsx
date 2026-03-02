import { Handle, Position } from '@xyflow/react'
import './SubprocessNode.css'

export default function SubprocessNode({ data }) {
  return (
    <div className="subprocess-node">
      <Handle type="target" position={Position.Left} />
      <div className="subprocess-node__icon">▶▶</div>
      <div className="subprocess-node__content">
        <span className="subprocess-node__name">{data.name}</span>
        {data.workspaceInfo?.summary && (
          <span className="subprocess-node__summary">
            {data.workspaceInfo.summary.step_count || 0} steps
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
