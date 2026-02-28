import { Handle, Position } from '@xyflow/react'
import './StepNode.css'

const ACTOR_ICONS = {
  'Physician': '👨‍⚕️',
  'Pharmacist': '💊',
  'Pharmacy Technician': '🔧',
  'Nurse': '👩‍⚕️',
  'Procurement / Pharmacist': '📦',
  'Procurement': '📦',
  'QA': '✅',
  'Pharmacist / QA': '✅',
  'Porter / Transport': '🚚',
  'Porter/AGV': '🚚',
  'Nurse/Physician': '👨‍⚕️',
  'System': '🖥️',
  'Pharmacy Technician / System': '🖥️',
  'Pharmacist / Pharmacy Technician': '💊',
}

export default function StepNode({ data, selected }) {
  const icon = ACTOR_ICONS[data.actor] || '👤'
  const colors = data.colors || {}

  return (
    <div
      className={`step-node ${selected ? 'step-node--selected' : ''}`}
      style={{
        background: colors.bg,
        borderColor: selected ? '#e85d04' : colors.border,
        '--phase-color': colors.border,
        '--phase-text': colors.text,
      }}
    >
      <Handle type="target" position={Position.Top} className="step-node__handle" />

      <div className="step-node__header">
        <span className="step-node__id">{data.id}</span>
        <span className="step-node__phase-dot" style={{ background: colors.border }} />
      </div>

      <div className="step-node__name">{data.name}</div>

      <div className="step-node__meta">
        <span className="step-node__actor">{icon} {data.actor}</span>
        <span className="step-node__duration">⏱ {data.duration_min}</span>
      </div>

      <Handle type="source" position={Position.Bottom} className="step-node__handle" />
    </div>
  )
}
