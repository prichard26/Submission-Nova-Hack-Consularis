import { memo } from 'react'
import { Handle } from '@xyflow/react'
import { HANDLE_MAP } from './nodeTypes'
import './nodes-common.css'
import './StepNode.css'
const TARGET_ORDER = ['left', 'right', 'top', 'bottom']
const SOURCE_ORDER = ['right', 'left', 'top', 'bottom']

function StepNode({ data, selected }) {
  const errRate = parseFloat(data.error_rate_percent)
  const hasHighError = !isNaN(errRate) && errRate > 5
  const autoPotential = (data.automation_potential || '').toLowerCase()

  return (
    <div
      className={`step-node node-shared-interactive node-shared-handles ${hasHighError ? 'step-node--high-error' : ''} ${selected ? 'node-shared-selected' : ''}`}
    >
      {TARGET_ORDER.map((id) => {
        const { position } = HANDLE_MAP[id]
        return <Handle key={`${id}-target`} type="target" position={position} id={`${id}-target`} />
      })}
      {SOURCE_ORDER.map((id) => {
        const { position } = HANDLE_MAP[id]
        return <Handle key={`${id}-source`} type="source" position={position} id={`${id}-source`} />
      })}
      <div className="step-node__header">
        <span className="step-node__name">{data.name}</span>
        {data.actor && <span className="step-node__actor">{data.actor}</span>}
      </div>
      <div className="step-node__metrics">
        {data.duration_min && (
          <span className="step-node__badge step-node__badge--duration">{data.duration_min}</span>
        )}
        {data.cost_per_execution && (
          <span className="step-node__badge step-node__badge--cost">{data.cost_per_execution}</span>
        )}
        {data.error_rate_percent && (
          <span className={`step-node__badge ${hasHighError ? 'step-node__badge--error-high' : 'step-node__badge--error'}`}>
            {data.error_rate_percent}% err
          </span>
        )}
      </div>
      {autoPotential && (
        <div className="step-node__automation">
          <div className={`step-node__auto-bar step-node__auto-bar--${autoPotential}`} />
          <span className="step-node__auto-label">{autoPotential} automation</span>
        </div>
      )}
      {data.risks && data.risks.length > 0 && (
        <div className="step-node__risk-indicator" title={data.risks.join(', ')}>⚠</div>
      )}
    </div>
  )
}

export default memo(StepNode)
