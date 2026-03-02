import StepNode from './StepNode'
import DecisionNode from './DecisionNode'
import SubprocessNode from './SubprocessNode'
import EventNode from './EventNode'

export const nodeTypes = {
  step: StepNode,
  decision: DecisionNode,
  subprocess: SubprocessNode,
  start: EventNode,
  end: EventNode,
}
