/**
 * React Flow node type registry and shared handle config: StepNode, DecisionNode, SubprocessNode, EventNode, LaneNode.
 */
import { Handle, Position } from '@xyflow/react'
import StepNode from './StepNode'
import DecisionNode from './DecisionNode'
import SubprocessNode from './SubprocessNode'
import EventNode from './EventNode'
import LaneNode from './LaneNode'

const HANDLES = [
  { position: Position.Left, id: 'left' },
  { position: Position.Right, id: 'right' },
  { position: Position.Top, id: 'top' },
  { position: Position.Bottom, id: 'bottom' },
]

const HANDLE_MAP = Object.fromEntries(HANDLES.map((handle) => [handle.id, handle]))

const TARGET_ORDER = ['left', 'right', 'top', 'bottom']
const SOURCE_ORDER = ['right', 'left', 'top', 'bottom']

export function NodeHandles() {
  return (
    <>
      {TARGET_ORDER.map((id) => {
        const { position } = HANDLE_MAP[id]
        return <Handle key={`${id}-target`} type="target" position={position} id={`${id}-target`} />
      })}
      {SOURCE_ORDER.map((id) => {
        const { position } = HANDLE_MAP[id]
        return <Handle key={`${id}-source`} type="source" position={position} id={`${id}-source`} />
      })}
    </>
  )
}

export const nodeTypes = {
  step: StepNode,
  decision: DecisionNode,
  subprocess: SubprocessNode,
  start: EventNode,
  end: EventNode,
  lane: LaneNode,
}
