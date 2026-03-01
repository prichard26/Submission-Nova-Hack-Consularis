export default function DataViewState({
  loading,
  error,
  loadingText = 'Loading…',
  loadingClassName,
  errorClassName,
}) {
  return (
    <>
      {loading && <div className={loadingClassName}>{loadingText}</div>}
      {error && (
        <div className={errorClassName} role="alert">
          {error}
        </div>
      )}
    </>
  )
}
