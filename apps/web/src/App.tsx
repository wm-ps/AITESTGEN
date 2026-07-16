import { useEffect, useState } from 'react'
import { ApiError, api, type ApplicationRead, type UserRead } from './api'
import { ConnectAppForm } from './components/ConnectAppForm'
import { DiscoverJourneysPlaceholder } from './components/DiscoverJourneysPlaceholder'
import { Home } from './components/Home'
import { SignIn } from './components/SignIn'
import { TopBar } from './components/TopBar'

type View = 'home' | 'connect-app' | 'discover'

function App() {
  const [user, setUser] = useState<UserRead | null | undefined>(undefined)
  const [view, setView] = useState<View>('home')
  const [application, setApplication] = useState<ApplicationRead | null>(null)

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          setUser(null)
        } else {
          setUser(null)
        }
      })
  }, [])

  if (user === undefined) return null

  if (user === null) {
    return <SignIn onSignedIn={setUser} />
  }

  async function handleLogout() {
    await api.logout()
    setUser(null)
    setView('home')
    setApplication(null)
  }

  return (
    <>
      <TopBar
        user={user}
        applicationBadge={
          view === 'home' ? undefined : application ? { name: application.name, environment: application.environment } : undefined
        }
        onLogout={handleLogout}
      />
      {view === 'home' && <Home user={user} onConnectApp={() => setView('connect-app')} />}
      {view === 'connect-app' && (
        <ConnectAppForm
          onConnected={(app) => {
            setApplication(app)
            setView('discover')
          }}
        />
      )}
      {view === 'discover' && application && (
        <DiscoverJourneysPlaceholder discoveryStatus={application.discovery_status} />
      )}
    </>
  )
}

export default App
