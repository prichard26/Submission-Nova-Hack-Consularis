import { Handle, Position } from '@xyflow/react'
import './SubprocessNode.css'

const HANDLES = [
  { position: Position.Left, id: 'left' },
  { position: Position.Right, id: 'right' },
  { position: Position.Top, id: 'top' },
  { position: Position.Bottom, id: 'bottom' },
]
const TARGET_ORDER = ['left', 'right', 'top', 'bottom']
const SOURCE_ORDER = ['right', 'left', 'top', 'bottom']

export default function SubprocessNode({ data, selected }) {
  return (
    <div className={`subprocess-node ${selected ? 'subprocess-node--selected' : ''}`}>
      {TARGET_ORDER.map((id) => {
        const { position } = HANDLES.find((h) => h.id === id)
        return <Handle key={`${id}-target`} type="target" position={position} id={`${id}-target`} />
      })}
      {SOURCE_ORDER.map((id) => {
        const { position } = HANDLES.find((h) => h.id === id)
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
