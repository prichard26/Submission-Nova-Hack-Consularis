import { memo } from 'react'
import { Handle } from '@xyflow/react'
import { HANDLE_MAP } from './nodeTypes'
import './nodes-common.css'
import './SubprocessNode.css'
const TARGET_ORDER = ['left', 'right', 'top', 'bottom']
const SOURCE_ORDER = ['right', 'left', 'top', 'bottom']

function SubprocessNode({ data, selected }) {
  return (
    <div className={`subprocess-node node-shared-interactive node-shared-handles ${selected ? 'node-shared-selected' : ''}`}>
      {TARGET_ORDER.map((id) => {
        const { position } = HANDLE_MAP[id]
        return <Handle key={`${id}-target`} type="target" position={position} id={`${id}-target`} />
      })}
      {SOURCE_ORDER.map((id) => {
        const { position } = HANDLE_MAP[id]
        return <Handle key={`${id}-source`} type="source" position={position} id={`${id}-source`} />
      })}
      <div className="subprocess-node__icon">▶▶</div>
      <div className="subprocess-node__content">
        <span className="subprocess-node__name">{data.name}</span>
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
