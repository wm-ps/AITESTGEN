import { useEffect, useState } from 'react'
import { ApiError, api, type ApplicationRead, type UserRead } from './api'
import { AcceptInvite } from './components/AcceptInvite'
import { ConnectAppForm } from './components/ConnectAppForm'
import { DiscoverJourneys } from './components/DiscoverJourneys'
import { GenerateSuite } from './components/GenerateSuite'
import { Home } from './components/Home'
import { InviteTeammateModal } from './components/InviteTeammateModal'
import { ReviewScenarios } from './components/ReviewScenarios'
import { SignIn } from './components/SignIn'
import { TestSuiteResults } from './components/TestSuiteResults'
import { TopBar } from './components/TopBar'

// Invite links point at /accept-invite?token=... — handled before the
// signed-in check below since accepting an invite never requires an
// existing session.
function getInviteTokenFromUrl(): string | null {
  return window.location.pathname === '/accept-invite'
    ? new URLSearchParams(window.location.search).get('token')
    : null
}

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
  const [inviteModalOpen, setInviteModalOpen] = useState(false)
  const [inviteToken, setInviteToken] = useState(getInviteTokenFromUrl)

  useEffect(() => {
    if (inviteToken) return
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
  }, [inviteToken])

  function handleSignedIn(signedInUser: UserRead) {
    window.history.replaceState({}, '', '/')
    setUser(signedInUser)
    setInviteToken(null)
  }

  if (inviteToken) {
    return <AcceptInvite token={inviteToken} onSignedIn={handleSignedIn} />
  }

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
        onGoHome={() => setView('home')}
        onInviteTeammate={() => setInviteModalOpen(true)}
      />
      {inviteModalOpen && <InviteTeammateModal onClose={() => setInviteModalOpen(false)} />}
      {view === 'home' && (
        <Home
          user={user}
          onConnectApp={() => setView('connect-app')}
          onResumeApplication={(app) => {
            setApplication(app)
            setView('discover')
          }}
        />
      )}
      {view === 'connect-app' && (
        <ConnectAppForm
          onConnected={() => setView('home')}
          onCancel={() => setView('home')}
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
