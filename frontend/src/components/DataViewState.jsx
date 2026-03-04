import { memo } from 'react'

function DataViewState({
  loading,
  error,
  loadingText = 'Loading…',
  loadingClassName,
  errorClassName,
}) {
  const errorText = error?.message ?? (error ? String(error) : '')

  return (
    <>
      {loading && <div className={loadingClassName}>{loadingText}</div>}
      {errorText && (
        <div className={errorClassName} role="alert">
          {errorText}
        </div>
      )}
    </>
  )
}

export default memo(DataViewState)
