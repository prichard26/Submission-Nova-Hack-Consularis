/**
 * Draggable toolbar overlay on the process canvas: zoom, fit view, add node, auto-arrange, undo/redo, reset, export PNG/BPMN, layout toggle.
 */
export default function FloatingToolbar({
  toolbarRef,
  className,
  position,
  hidden,
  collapsed,
  layout,
  onGrab,
  onZoomIn,
  onZoomOut,
  onFitView,
  pendingAddType,
  onAddNode,
  disabled,
  editDisabled = false,
  onAutoArrange,
  onUndo,
  undoDisabled,
  undoTip,
  onRedo,
  redoDisabled,
  redoTip,
  onReset,
  resetDisabled,
  onExportPng,
  onExportBpmn,
  onVisualize,
  vizActive,
  onToggleLayout,
}) {
  return (
    <div ref={toolbarRef} className={className} style={{ left: position.x, top: position.y, visibility: hidden ? 'hidden' : 'visible' }}>
      {collapsed ? (
        <div className="ftb__toggle" onMouseDown={onGrab} data-tip="Expand toolbar">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg>
        </div>
      ) : (
        <>
          <div className="ftb__toggle" onMouseDown={onGrab} data-tip="Drag to move · Click to collapse">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M3 4h10M3 8h10M3 12h10" /></svg>
          </div>
          <span className="ftb__sep" />
          <button type="button" className="ftb__btn" onClick={onZoomIn} data-tip="Zoom in">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg>
          </button>
          <button type="button" className="ftb__btn" onClick={onZoomOut} data-tip="Zoom out">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true"><path d="M3 8h10" /></svg>
          </button>
          <button type="button" className="ftb__btn" onClick={onFitView} data-tip="Fit to view">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2 6V3.5A1.5 1.5 0 0 1 3.5 2H6M10 2h2.5A1.5 1.5 0 0 1 14 3.5V6M14 10v2.5a1.5 1.5 0 0 1-1.5 1.5H10M6 14H3.5A1.5 1.5 0 0 1 2 12.5V10" /></svg>
          </button>
          <span className="ftb__sep" />
          <button type="button" className={'ftb__btn' + (pendingAddType === 'step' ? ' ftb__btn--active' : '')} onClick={() => onAddNode('step')} disabled={disabled || editDisabled} data-tip="Add Step · S">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="2" y="3" width="12" height="10" rx="2" /><path d="M8 6v4M6 8h4" strokeLinecap="round" /></svg>
          </button>
          <button type="button" className={'ftb__btn' + (pendingAddType === 'decision' ? ' ftb__btn--active' : '')} onClick={() => onAddNode('decision')} disabled={disabled || editDisabled} data-tip="Add Decision · D">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M8 2L14 8L8 14L2 8Z" strokeLinejoin="round" /><path d="M8 6v4M6 8h4" strokeLinecap="round" /></svg>
          </button>
          <button type="button" className={'ftb__btn' + (pendingAddType === 'subprocess' ? ' ftb__btn--active' : '')} onClick={() => onAddNode('subprocess')} disabled={disabled || editDisabled} data-tip="Add Subprocess · P">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="1.5" y="2.5" width="9" height="7" rx="1.5" /><rect x="5.5" y="6.5" width="9" height="7" rx="1.5" /></svg>
          </button>
          <span className="ftb__sep" />
          <button type="button" className="ftb__btn" onClick={onAutoArrange} disabled={disabled || editDisabled} data-tip="Auto-arrange · A">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="2" y="2" width="4" height="4" rx="1" /><rect x="10" y="2" width="4" height="4" rx="1" /><rect x="2" y="10" width="4" height="4" rx="1" /><rect x="10" y="10" width="4" height="4" rx="1" /></svg>
          </button>
          <button type="button" className="ftb__btn" onClick={onUndo} disabled={undoDisabled} data-tip={undoTip}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 6h7a3 3 0 0 1 0 6H8" /><path d="M6 3L3 6l3 3" /></svg>
          </button>
          <button type="button" className="ftb__btn" onClick={onRedo} disabled={redoDisabled} data-tip={redoTip}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M13 6H6a3 3 0 0 0 0 6h2" /><path d="M10 3l3 3-3 3" /></svg>
          </button>
          <button type="button" className="ftb__btn" onClick={onReset} disabled={resetDisabled} data-tip="Reset to baseline">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2.5 8a5.5 5.5 0 0 1 9.3-4" /><path d="M13.5 8a5.5 5.5 0 0 1-9.3 4" /><path d="M11.5 2l.3 2.2-2.2.3" /><path d="M4.5 14l-.3-2.2 2.2-.3" /></svg>
          </button>
          <span className="ftb__sep" />
          <button type="button" className="ftb__btn" onClick={onExportPng} disabled={disabled || editDisabled} data-tip="Export PNG">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="2" y="2" width="12" height="12" rx="2" /><circle cx="6" cy="6" r="1.5" fill="currentColor" stroke="none" /><path d="M2 11l3.5-4 2.5 3 2-2 4 3" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
          <button type="button" className="ftb__btn" onClick={onExportBpmn} disabled={disabled || editDisabled} data-tip="Export BPMN">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" aria-hidden="true"><path d="M4 2h5.5L13 5.5V14H4V2Z" /><path d="M9.5 2v3.5H13" /><path d="M6.5 9.5L8 11l1.5-1.5" strokeLinecap="round" /></svg>
          </button>
          <span className="ftb__sep" />
          <button type="button" className={'ftb__btn' + (vizActive ? ' ftb__btn--active' : '')} onClick={onVisualize} disabled={disabled} data-tip="Visualization mode">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M1 8s2.5-4.5 7-4.5S15 8 15 8s-2.5 4.5-7 4.5S1 8 1 8z" /><circle cx="8" cy="8" r="2.5" /></svg>
          </button>
          <button type="button" className="ftb__btn ftb__btn--meta" onClick={onToggleLayout} data-tip={layout === 'vertical' ? 'Horizontal layout' : 'Vertical layout'}>
            {layout === 'vertical' ? (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2 8h12M10 5l3 3-3 3M6 11l-3-3 3-3" /></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 2v12M5 10l3 3 3-3M11 6l-3-3-3 3" /></svg>
            )}
          </button>
        </>
      )}
    </div>
  )
}
