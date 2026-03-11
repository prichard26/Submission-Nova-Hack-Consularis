import { useNavigate } from 'react-router-dom'
import '../pages/Dashboard.css'

/**
 * Shared top bar: logo left; Chat, Analyze, I buttons right.
 * activeMode: 'chat' | 'analyze' | 'info' — which button is shown in orange.
 */
export default function DashboardTopBar({
  activeMode = 'chat',
  panelChatRef,
  onShowTutorial,
  topbarRef,
}) {
  const navigate = useNavigate()

  return (
    <header ref={topbarRef} className="dashboard__topbar">
      <span className="dashboard__logo">
        <img className="dashboard__logo-icon" src="/logo.png" alt="Consularis" width="24" height="24" />
        Consularis.ai
      </span>
      <div className="dashboard__topbar-actions">
        <button
          type="button"
          className={`dashboard__topbar-btn${activeMode === 'chat' ? ' dashboard__topbar-btn--active' : ''}`}
          onClick={() => {
            if (panelChatRef?.current) {
              panelChatRef.current.scrollIntoView({ behavior: 'smooth' })
            } else {
              navigate('/dashboard')
            }
          }}
          title="Focus chat"
          aria-label="Focus chat"
          aria-current={activeMode === 'chat' ? 'true' : undefined}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H5l-2 2V4z" /></svg>
          Chat
        </button>
        <button
          type="button"
          className={`dashboard__topbar-btn${activeMode === 'analyze' ? ' dashboard__topbar-btn--active' : ''}`}
          onClick={() => navigate('/dashboard/analyze')}
          title="Automation analysis"
          aria-label="Open automation analysis"
          aria-current={activeMode === 'analyze' ? 'true' : undefined}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="6.5" cy="6.5" r="4.25" />
            <path d="M9.15 9.15l3.6 3.6" />
            <path d="M4.25 7.5l1.5-1.2 1.5 1.5 1.25-2" strokeWidth="1.1" />
            <circle cx="4.25" cy="7.5" r="0.55" fill="currentColor" stroke="none" />
            <circle cx="5.75" cy="6.3" r="0.55" fill="currentColor" stroke="none" />
            <circle cx="7.25" cy="7.8" r="0.55" fill="currentColor" stroke="none" />
          </svg>
          Analyze
        </button>
        <button
          type="button"
          className={`dashboard__topbar-btn dashboard__topbar-btn--icon${activeMode === 'info' ? ' dashboard__topbar-btn--active' : ''}`}
          onClick={() => onShowTutorial?.()}
          title="Show tour"
          aria-label="Show tour"
          aria-current={activeMode === 'info' ? 'true' : undefined}
        >
          <span className="dashboard__topbar-icon-i">i</span>
        </button>
      </div>
    </header>
  )
}
