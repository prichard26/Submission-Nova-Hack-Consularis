import './Colonnade.css'

export default function Colonnade({ children }) {
  return (
    <div className="colonnade">
      <div className="colonnade__side colonnade__side--left" aria-hidden>
        <div className="colonnade__column" />
        <div className="colonnade__column" />
        <div className="colonnade__column" />
      </div>
      <div className="colonnade__content">
        <div className="colonnade__frieze colonnade__frieze--top" />
        {children}
        <div className="colonnade__frieze colonnade__frieze--bottom" />
      </div>
      <div className="colonnade__side colonnade__side--right" aria-hidden>
        <div className="colonnade__column" />
        <div className="colonnade__column" />
        <div className="colonnade__column" />
      </div>
    </div>
  )
}
