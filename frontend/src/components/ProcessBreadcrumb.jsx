import './ProcessBreadcrumb.css'

export default function ProcessBreadcrumb({ workspaceProcesses, activeProcessId, onNavigate }) {
  if (!workspaceProcesses || !activeProcessId) return null

  const parts = []
  let current = activeProcessId

  while (current) {
    const info = workspaceProcesses[current]
    if (!info) break
    parts.unshift({ id: current, name: info.name })
    const path = info.path || ''
    const segments = path.split('/').filter(Boolean)
    if (segments.length >= 2) {
      current = segments[segments.length - 2]
    } else {
      break
    }
    if (current === parts[0]?.id) break
  }

  if (parts.length <= 1) return null

  return (
    <nav className="process-breadcrumb" aria-label="Process navigation">
      {parts.map((p, i) => (
        <span key={p.id} className="process-breadcrumb__segment">
          {i > 0 && <span className="process-breadcrumb__separator">›</span>}
          {i < parts.length - 1 ? (
            <button
              className="process-breadcrumb__link"
              onClick={() => onNavigate?.(p.id)}
            >
              {p.name}
            </button>
          ) : (
            <span className="process-breadcrumb__current">{p.name}</span>
          )}
        </span>
      ))}
    </nav>
  )
}
