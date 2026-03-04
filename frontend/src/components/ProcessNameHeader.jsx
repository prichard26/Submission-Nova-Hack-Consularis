export default function ProcessNameHeader({
  breadcrumb,
  processDisplayName,
  onDrillDown,
  stats,
}) {
  return (
    <section className="panel-info">
      <nav className="panel-info__path" aria-label="Process path">
        {breadcrumb.slice(0, -1).map((part) => (
          <span key={part.id} className="panel-info__path-item">
            <button className="panel-info__path-link" onClick={() => onDrillDown?.(part.id)}>{part.name}</button>
            <span className="panel-info__path-sep">›</span>
          </span>
        ))}
        <span className="panel-info__current">
          <span className="panel-info__name-display" title={processDisplayName}>{processDisplayName}</span>
        </span>
      </nav>
      <div className="panel-info__stats">
        <div className="panel-info__stat"><span className="panel-info__stat-value">{stats.steps}</span><span className="panel-info__stat-label">Steps</span></div>
        <div className="panel-info__stat"><span className="panel-info__stat-value">{stats.decisions}</span><span className="panel-info__stat-label">Decisions</span></div>
        <div className="panel-info__stat"><span className="panel-info__stat-value">{stats.subprocesses}</span><span className="panel-info__stat-label">Subs</span></div>
        <div className="panel-info__stat"><span className="panel-info__stat-value">{stats.connections}</span><span className="panel-info__stat-label">Edges</span></div>
        <div className="panel-info__stat"><span className="panel-info__stat-value">{stats.lanes}</span><span className="panel-info__stat-label">Lanes</span></div>
      </div>
    </section>
  )
}
