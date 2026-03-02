import { useMemo, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'

function SessionRoutes({ session }) {
  if (!session) {
    return <Navigate to="/" replace />
  }

  return (
    <Dashboard companyName={session.companyName} sector={session.sector} />
  )
}

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
    }
  }, [session])

  function updateSession(nextSession) {
    const normalized = {
      companyName: nextSession.companyName,
      sector: nextSession.sector || 'pharmacy',
    }
    setSession(normalized)
    sessionStorage.setItem('consularis_session', JSON.stringify(normalized))
  }

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
      <Route path="/dashboard" element={<SessionRoutes session={safeSession} />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
