/**
 * Dropdown to select the Bedrock model for chat (Nova Pro, Nova Lite, Claude, etc.). Used in AureliusChat.
 */
import './ModelPicker.css'

export default function ModelPicker({ models, value, onChange, disabled }) {
  if (!models || models.length === 0) return null

  return (
    <div className="model-picker">
      <select
        className="model-picker__select"
        value={value || ''}
        onChange={(e) => onChange?.(e.target.value)}
        disabled={disabled}
        title="Select reasoning model"
        aria-label="Select reasoning model"
      >
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}{m.tier === 'lite' ? ' (lite)' : ''}{m.is_default ? ' ★' : ''}
          </option>
        ))}
      </select>
    </div>
  )
}
