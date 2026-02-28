import './DomainCard.css'

const icons = {
  pharmacy: (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="20" y="8" width="24" height="48" rx="4" stroke="currentColor" strokeWidth="2.5"/>
      <rect x="26" y="24" width="12" height="4" rx="1" fill="currentColor"/>
      <rect x="30" y="20" width="4" height="12" rx="1" fill="currentColor"/>
      <path d="M20 16h24" stroke="currentColor" strokeWidth="2"/>
      <circle cx="32" cy="46" r="3" fill="currentColor" opacity="0.5"/>
    </svg>
  ),
  logistics: (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="20" width="36" height="24" rx="3" stroke="currentColor" strokeWidth="2.5"/>
      <path d="M40 28h12l8 10v6h-20V28z" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round"/>
      <circle cx="16" cy="48" r="5" stroke="currentColor" strokeWidth="2.5"/>
      <circle cx="48" cy="48" r="5" stroke="currentColor" strokeWidth="2.5"/>
      <rect x="10" y="26" width="16" height="3" rx="1" fill="currentColor" opacity="0.4"/>
      <rect x="10" y="32" width="12" height="3" rx="1" fill="currentColor" opacity="0.3"/>
    </svg>
  ),
  other: (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="8" y="12" width="48" height="40" rx="4" stroke="currentColor" strokeWidth="2.5"/>
      <circle cx="24" cy="32" r="6" stroke="currentColor" strokeWidth="2" opacity="0.6"/>
      <circle cx="40" cy="28" r="4" stroke="currentColor" strokeWidth="2" opacity="0.4"/>
      <path d="M16 44c4-4 8-6 16-6s12 2 16 6" stroke="currentColor" strokeWidth="2" opacity="0.5"/>
      <rect x="28" y="8" width="8" height="8" rx="2" fill="currentColor" opacity="0.3"/>
    </svg>
  ),
}

export default function DomainCard({ domain, label, description, selected, onClick }) {
  return (
    <button
      className={`domain-card ${selected ? 'domain-card--selected' : ''}`}
      onClick={onClick}
    >
      <div className="domain-card__icon">
        {icons[domain]}
      </div>
      <h3 className="domain-card__label">{label}</h3>
      <p className="domain-card__desc">{description}</p>
      {selected && <div className="domain-card__check">&#10003;</div>}
    </button>
  )
}
