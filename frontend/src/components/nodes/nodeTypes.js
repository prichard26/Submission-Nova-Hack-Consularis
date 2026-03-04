import StepNode from './StepNode'
import DecisionNode from './DecisionNode'
import SubprocessNode from './SubprocessNode'
import EventNode from './EventNode'
import { Position } from '@xyflow/react'

export const HANDLES = [
  { position: Position.Left, id: 'left' },
  { position: Position.Right, id: 'right' },
  { position: Position.Top, id: 'top' },
  { position: Position.Bottom, id: 'bottom' },
]

export const HANDLE_MAP = Object.fromEntries(HANDLES.map((handle) => [handle.id, handle]))

export const nodeTypes = {
  step: StepNode,
  decision: DecisionNode,
  subprocess: SubprocessNode,
  start: EventNode,
  end: EventNode,
}
