import { useMemo, useCallback, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import AnalyzePage from './pages/AnalyzePage'

export default function App() {
  const [session, setSession] = useState(() => {
    try {
      const saved = sessionStorage.getItem('consularis_session')
      return saved ? JSON.parse(saved) : null
    } catch (err) {
      void err
      return null
    }
  })

  const safeSession = useMemo(() => {
    if (!session?.companyName) return null
    return {
      companyName: session.companyName,
      sector: session.sector || 'pharmacy',
      fromBlank: session.fromBlank ?? false,
    }
  }, [session])

  const updateSession = useCallback((nextSession) => {
    const normalized = {
      companyName: nextSession.companyName,
      sector: nextSession.sector || 'pharmacy',
      fromBlank: nextSession.fromBlank ?? false,
    }
    setSession(normalized)
    sessionStorage.setItem('consularis_session', JSON.stringify(normalized))
  }, [])

  return (
    <Routes>
      <Route
        path="/"
        element={
          safeSession ? (
            <Navigate to="/dashboard" replace />
          ) : (
            <Landing onSubmit={updateSession} />
          )
        }
      />
      <Route
        path="/dashboard"
        element={
          safeSession ? (
            <Dashboard companyName={safeSession.companyName} />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/dashboard/analyze"
        element={
          safeSession ? (
            <AnalyzePage sessionId={safeSession.companyName} />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
