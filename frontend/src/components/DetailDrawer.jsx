import './DetailDrawer.css'

export default function DetailDrawer({ step, onClose }) {
  if (!step) return null

  return (
    <div className="drawer">
      <div className="drawer__header">
        <div>
          <span className="drawer__id">{step.id}</span>
          <h2 className="drawer__title">{step.name}</h2>
          <span className="drawer__phase">{step.phaseName}</span>
        </div>
        <button className="drawer__close" onClick={onClose}>✕</button>
      </div>

      <div className="drawer__body">
        <p className="drawer__desc">{step.description}</p>

        <div className="drawer__row">
          <div className="drawer__pill drawer__pill--actor">
            👤 {step.actor}
          </div>
          <div className="drawer__pill drawer__pill--time">
            ⏱ {step.duration_min}
          </div>
        </div>

        {step.inputs?.length > 0 && (
          <div className="drawer__section">
            <h3 className="drawer__section-title">Inputs</h3>
            <ul className="drawer__list">
              {step.inputs.map((inp, i) => <li key={i}>{inp}</li>)}
            </ul>
          </div>
        )}

        {step.outputs?.length > 0 && (
          <div className="drawer__section">
            <h3 className="drawer__section-title">Outputs</h3>
            <ul className="drawer__list">
              {step.outputs.map((out, i) => <li key={i}>{out}</li>)}
            </ul>
          </div>
        )}

        {step.risks?.length > 0 && (
          <div className="drawer__section">
            <h3 className="drawer__section-title">⚠ Risks</h3>
            <ul className="drawer__list drawer__list--risk">
              {step.risks.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
