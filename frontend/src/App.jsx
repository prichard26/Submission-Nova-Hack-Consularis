import { useState } from 'react'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'

export default function App() {
  const [session, setSession] = useState(null) // { sector, companyName }

  if (!session) {
    return <Landing onSubmit={setSession} />
  }

  return <Dashboard companyName={session.companyName} sector={session.sector} />
}
