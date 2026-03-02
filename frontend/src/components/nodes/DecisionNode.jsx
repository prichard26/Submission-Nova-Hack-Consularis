import { Handle, Position } from '@xyflow/react'
import './DecisionNode.css'

const HANDLES = [
  { position: Position.Left, id: 'left' },
  { position: Position.Right, id: 'right' },
  { position: Position.Top, id: 'top' },
  { position: Position.Bottom, id: 'bottom' },
]
const TARGET_ORDER = ['left', 'right', 'top', 'bottom']
const SOURCE_ORDER = ['right', 'left', 'top', 'bottom']

export default function DecisionNode({ data, selected }) {
  return (
    <div className="decision-node">
      {TARGET_ORDER.map((id) => {
        const { position } = HANDLES.find((h) => h.id === id)
        return <Handle key={`${id}-target`} type="target" position={position} id={`${id}-target`} />
      })}
      {SOURCE_ORDER.map((id) => {
        const { position } = HANDLES.find((h) => h.id === id)
        return <Handle key={`${id}-source`} type="source" position={position} id={`${id}-source`} />
      })}
      <div className={`decision-node__diamond ${selected ? 'decision-node__diamond--selected' : ''}`}>
        <span className="decision-node__label">{data.name || '?'}</span>
      </div>
    </div>
  )
}
