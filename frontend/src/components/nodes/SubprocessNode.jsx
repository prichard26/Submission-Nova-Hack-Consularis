/** React Flow custom node for type "subprocess": name and step count from workspaceInfo. */
import { memo } from 'react'
import { NodeHandles } from './nodeTypes.jsx'
import './nodes-common.css'
import './SubprocessNode.css'

function SubprocessNode({ data, selected }) {
  return (
    <div className={`subprocess-node node-shared-interactive node-shared-handles ${selected ? 'node-shared-selected' : ''} ${data.vizHighlighted ? 'node-shared-viz-highlight' : ''}`}>
      <NodeHandles />
      <div className="subprocess-node__icon">▶▶</div>
      <div className="subprocess-node__content">
        <span className="subprocess-node__name">{data.workspaceInfo?.name || data.name}</span>
        {data.workspaceInfo?.summary && (
          <span className="subprocess-node__summary">
            {data.workspaceInfo.summary.step_count || 0} steps
          </span>
        )}
      </div>
    </div>
  )
}

export default memo(SubprocessNode)
