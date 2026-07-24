import { useEffect, useState } from 'react'
import { ApiError, api, type ApplicationRead, type UserRead } from './api'
import { ConnectAppForm } from './components/ConnectAppForm'
import { DiscoverJourneys } from './components/DiscoverJourneys'
import { GenerateSuite } from './components/GenerateSuite'
import { Home } from './components/Home'
import { ReviewScenarios } from './components/ReviewScenarios'
import { SignIn } from './components/SignIn'
import { TestSuiteResults } from './components/TestSuiteResults'
import { TopBar } from './components/TopBar'

type View =
  | 'home'
  | 'connect-app'
  | 'discover'
  | 'review-scenarios'
  | 'generate-suite'
  | 'test-suite-results'

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
        <DiscoverJourneys
          applicationId={application.id}
          applicationName={application.name}
          discoveryStatus={application.discovery_status}
          discoveryStage={application.discovery_stage ?? null}
          discoveryFailureReason={application.discovery_failure_reason ?? null}
          onContinueToScenarios={() => setView('review-scenarios')}
        />
      )}
      {view === 'review-scenarios' && application && (
        <ReviewScenarios
          applicationId={application.id}
          onContinueToGenerate={() => setView('generate-suite')}
        />
      )}
      {view === 'generate-suite' && application && (
        <GenerateSuite
          applicationId={application.id}
          onGenerated={() => setView('test-suite-results')}
        />
      )}
      {view === 'test-suite-results' && application && (
        <TestSuiteResults
          applicationId={application.id}
          onGoToDashboard={() => setView('home')}
        />
      )}
    </>
  )
}

export default App
