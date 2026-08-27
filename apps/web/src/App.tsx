import { useEffect, useState } from 'react'
import { ApiError, api, type ApplicationRead, type UserRead } from './api'
import { AcceptInvite } from './components/AcceptInvite'
import { ConnectAppForm } from './components/ConnectAppForm'
import { ConnectSuccessModal } from './components/ConnectSuccessModal'
import { DiscoverJourneys } from './components/DiscoverJourneys'
import { Footer } from './components/Footer'
import { Home } from './components/Home'
import { InviteTeammateModal } from './components/InviteTeammateModal'
import { ResetPassword } from './components/ResetPassword'
import { ReviewScenarios } from './components/ReviewScenarios'
import { Settings } from './components/Settings'
import { ServiceError } from './components/ServiceError'
import { SignIn } from './components/SignIn'
import type { StepKey } from './components/Stepper'
import { TestSuiteResults } from './components/TestSuiteResults'
import { Toast } from './components/Toast'
import { TopBar } from './components/TopBar'
import { Workspace } from './components/workspace/Workspace'

const VIEW_FOR_STEP: Record<StepKey, View> = {
  'connect-app': 'connect-app',
  discover: 'discover',
  review: 'review-scenarios',
  // No 'generate-suite' config screen anymore — the "Generate Test Suite"
  // click on Review Scenarios kicks off generation directly, so this step
  // goes straight to its results.
  generate: 'test-suite-results',
}

// Previous/Next walk this same order — 'test-suite-results' has no Stepper
// circle of its own (it renders the Stepper with furthestCount 4, all done),
// but it's still a stop along the Previous/Next line.
const VIEW_ORDER: View[] = ['connect-app', 'discover', 'review-scenarios', 'test-suite-results']

// Invite links point at /accept-invite?token=... — handled before the
// signed-in check below since accepting an invite never requires an
// existing session.
function getInviteTokenFromUrl(): string | null {
  return window.location.pathname === '/accept-invite'
    ? new URLSearchParams(window.location.search).get('token')
    : null
}

// Reset-password links point at /reset-password?token=... — same
// before-the-signed-in-check handling as accept-invite above.
function getResetTokenFromUrl(): string | null {
  return window.location.pathname === '/reset-password'
    ? new URLSearchParams(window.location.search).get('token')
    : null
}

type View =
  | 'home'
  | 'connect-app'
  | 'discover'
  | 'review-scenarios'
  | 'test-suite-results'
  | 'workspace'
  | 'settings'

function App() {
  const [user, setUser] = useState<UserRead | null | undefined>(undefined)
  // A network-level failure (fetch never got a response — backend/pods down)
  // isn't an ApiError, so it can't mean "not signed in". Route it to the
  // generic error screen instead of silently bouncing to SignIn.
  const [serviceDown, setServiceDown] = useState(false)
  const [view, setView] = useState<View>('home')
  const [previousView, setPreviousView] = useState<View>('home')
  const [application, setApplication] = useState<ApplicationRead | null>(null)
  // Set right after Connect Application succeeds, cleared once the user
  // dismisses ConnectSuccessModal — separate from `application` itself so
  // resuming an already-connected app (handleResumeApplication) never
  // re-triggers this one-time modal.
  const [justConnected, setJustConnected] = useState<ApplicationRead | null>(null)
  // How many of the 4 wizard steps are actually finished — independent of
  // `view`, which is just whichever screen is on screen right now. Lets
  // Previous/Next and the Stepper's own step numbers revisit an earlier
  // completed step without losing its checkmark.
  const [furthestCount, setFurthestCount] = useState(0)
  const [inviteModalOpen, setInviteModalOpen] = useState(false)
  const [inviteToken, setInviteToken] = useState(getInviteTokenFromUrl)
  const [resetToken, setResetToken] = useState(getResetTokenFromUrl)
  // Covers logout and resume-application — both involve an API round trip
  // before the screen changes, and users were reading the pause as a hang.
  const [globalLoading, setGlobalLoading] = useState<string | null>(null)
  const [errorToast, setErrorToast] = useState<string | null>(null)

  useEffect(() => {
    if (!errorToast) return
    const timeout = setTimeout(() => setErrorToast(null), 3000)
    return () => clearTimeout(timeout)
  }, [errorToast])

  // Fired by api.ts's request() on any 401 that isn't a login attempt —
  // catches an idle-timeout logout (COOKIE_MAX_AGE, apps/api/src/api/auth.py)
  // hit mid-session by a background poll, not just the mount-time check
  // below, so a stale tab bounces to Sign In instead of erroring silently.
  useEffect(() => {
    function handleExpired() {
      setUser(null)
      setErrorToast('Your session expired from inactivity. Please sign in again.')
    }
    window.addEventListener('auth:expired', handleExpired)
    return () => window.removeEventListener('auth:expired', handleExpired)
  }, [])

  // Read once by Workspace on mount (it fully remounts each time `view`
  // toggles away from 'workspace' and back) — lets "Run All Tests" land
  // straight on the Runs tab with the new run auto-selected, while a plain
  // dashboard resume lands on Overview as usual.
  const [workspaceEntry, setWorkspaceEntry] = useState<{
    initialTab: 'overview' | 'runs'
    autoTriggerRun: boolean
  }>({ initialTab: 'overview', autoTriggerRun: false })

  useEffect(() => {
    if (inviteToken || resetToken) return
    api
      .me()
      .then(setUser)
      .catch((err) => {
        if (err instanceof ApiError) {
          setUser(null)
        } else {
          setServiceDown(true)
        }
      })
  }, [inviteToken, resetToken])

  function handleSignedIn(signedInUser: UserRead) {
    window.history.replaceState({}, '', '/')
    setUser(signedInUser)
    setInviteToken(null)
  }

  // Unlike accept-invite, resetting a password never signs the user in —
  // they land back on the sign-in screen to enter their new credentials.
  function handleResetDone() {
    window.history.replaceState({}, '', '/')
    setResetToken(null)
    setUser(null)
  }

  if (inviteToken) {
    return <AcceptInvite token={inviteToken} onSignedIn={handleSignedIn} />
  }

  if (resetToken) {
    return <ResetPassword token={resetToken} onDone={handleResetDone} />
  }

  if (serviceDown) {
    return <ServiceError code="API_UNAVAILABLE" onRetry={() => window.location.reload()} />
  }

  if (user === undefined) return null

  if (user === null) {
    return <SignIn onSignedIn={setUser} />
  }

  async function handleLogout() {
    if (globalLoading) return
    setGlobalLoading('Logging out')
    try {
      await api.logout()
      setUser(null)
      setView('home')
      setApplication(null)
      setJustConnected(null)
    } catch {
      setErrorToast('Failed to log out. Please try again.')
    } finally {
      setGlobalLoading(null)
    }
  }

  // A test suite already generated means every wizard step is done —
  // land straight on the results screen instead of Discover Journeys.
  // Otherwise unchanged: always resume on Discover Journeys (existing
  // behavior), just with an accurate furthestCount for Previous/Next/Stepper
  // navigation once the user starts moving around.
  async function handleResumeApplication(app: ApplicationRead) {
    if (globalLoading) return
    setGlobalLoading('Loading project')
    try {
      setApplication(app)
      const [scenarios, suites] = await Promise.all([
        api.listScenarios(app.id),
        api.listTestSuites(app.id),
      ])
      // A TestSuite row exists as soon as generation starts (before its
      // TestAssets do) — resuming mid-generation must land back on the
      // Generate Suite results screen (it already polls and shows its own
      // "generating" state), not jump into Workspace with a partial suite.
      const testCaseCount = suites.reduce((sum, s) => sum + s.test_cases.length, 0)
      const suiteComplete = suites.length > 0 && testCaseCount >= scenarios.length
      setFurthestCount(suites.length > 0 ? 4 : scenarios.length > 0 ? 2 : 1)
      setWorkspaceEntry({ initialTab: 'overview', autoTriggerRun: false })
      setView(
        suiteComplete
          ? 'workspace'
          : suites.length > 0
            ? 'test-suite-results'
            : scenarios.length > 0
              ? 'review-scenarios'
              : 'discover',
      )
    } catch {
      setApplication(null)
      setErrorToast('Failed to load project. Please try again.')
    } finally {
      setGlobalLoading(null)
    }
  }

  const viewingIndex = VIEW_ORDER.indexOf(view)
  const onPrevious = viewingIndex > 0 ? () => setView(VIEW_ORDER[viewingIndex - 1]) : undefined
  const onNext =
    viewingIndex >= 0 && viewingIndex < VIEW_ORDER.length - 1 && viewingIndex + 1 <= furthestCount
      ? () => setView(VIEW_ORDER[viewingIndex + 1])
      : undefined
  // Stepper only calls this for a step index <= furthestCount in the first
  // place (its own clickable check) — no need to re-guard here.
  const onStepClick = (key: StepKey) => setView(VIEW_FOR_STEP[key])

  return (
    <>
      <TopBar
        user={user}
        applicationBadge={
          view === 'home' || view === 'settings'
            ? undefined
            : application
              ? { name: application.name, environment: application.environment }
              : undefined
        }
        onLogout={handleLogout}
        onGoHome={() => setView('home')}
        onInviteTeammate={() => setInviteModalOpen(true)}
        onOpenSettings={() => {
          setPreviousView(view)
          setView('settings')
        }}
        onOpenWorkspace={
          application && view !== 'home' && furthestCount >= 4 && view !== 'workspace'
            ? () => {
                setWorkspaceEntry({ initialTab: 'overview', autoTriggerRun: false })
                setView('workspace')
              }
            : undefined
        }
        onViewDiscovery={application && view === 'workspace' ? () => setView('discover') : undefined}
      />
      {inviteModalOpen && <InviteTeammateModal onClose={() => setInviteModalOpen(false)} />}
      {justConnected && (
        <ConnectSuccessModal
          application={justConnected}
          onGoHome={() => {
            setJustConnected(null)
            setView('home')
          }}
        />
      )}
      <main style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        {view === 'home' && (
          <Home
            user={user}
            onConnectApp={() => {
              setApplication(null)
              setFurthestCount(0)
              setView('connect-app')
            }}
            onResumeApplication={handleResumeApplication}
          />
        )}
        {view === 'connect-app' && (
          <ConnectAppForm
            application={application}
            onConnected={(connectedApplication) => {
              setApplication(connectedApplication)
              setFurthestCount((c) => Math.max(c, 1))
              setJustConnected(connectedApplication)
            }}
            onCancel={() => setView('home')}
            furthestCount={furthestCount}
            onStepClick={onStepClick}
            onPrevious={onPrevious}
            onNext={onNext}
          />
        )}
        {view === 'discover' && application && (
          <DiscoverJourneys
            applicationId={application.id}
            applicationName={application.name}
            discoveryStatus={application.discovery_status}
            discoveryStage={application.discovery_stage ?? null}
            discoveryFailureReason={application.discovery_failure_reason ?? null}
            onContinueToScenarios={() => {
              setFurthestCount((c) => Math.max(c, 2))
              setView('review-scenarios')
            }}
            furthestCount={furthestCount}
            onStepClick={onStepClick}
            onPrevious={onPrevious}
            onNext={onNext}
          />
        )}
        {view === 'review-scenarios' && application && (
          <ReviewScenarios
            applicationId={application.id}
            onContinueToGenerate={async () => {
              if (globalLoading) return
              setGlobalLoading('Generating test suite')
              try {
                await api.generateSuite(application.id)
                setFurthestCount(4)
                setView('test-suite-results')
              } catch {
                setErrorToast('Failed to start test suite generation. Please try again.')
              } finally {
                setGlobalLoading(null)
              }
            }}
            furthestCount={furthestCount}
            onStepClick={onStepClick}
            onPrevious={onPrevious}
            onNext={onNext}
          />
        )}
        {view === 'test-suite-results' && application && (
          <TestSuiteResults
            applicationId={application.id}
            onRunTests={() => {
              setWorkspaceEntry({ initialTab: 'runs', autoTriggerRun: true })
              setView('workspace')
            }}
            furthestCount={furthestCount}
            onStepClick={onStepClick}
            onPrevious={onPrevious}
          />
        )}
        {view === 'workspace' && application && (
          <Workspace
            applicationId={application.id}
            initialTab={workspaceEntry.initialTab}
            autoTriggerRun={workspaceEntry.autoTriggerRun}
            isAdmin={user?.role === 'admin'}
          />
        )}
        {view === 'settings' && user && <Settings user={user} onCancel={() => setView(previousView)} />}
      </main>

      <Footer />

      {globalLoading && (
        <div
          role="status"
          aria-label={globalLoading}
          style={{
            position: 'fixed',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            pointerEvents: 'none',
          }}
        >
          <span style={{ display: 'flex', gap: 6 }} aria-hidden="true">
            {[0, 0.15, 0.3].map((delay) => (
              <span
                key={delay}
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--accent)',
                  animation: 'aitg-dot-bounce 1s ease-in-out infinite',
                  animationDelay: `${delay}s`,
                }}
              />
            ))}
          </span>
        </div>
      )}

      {errorToast && (
        <Toast message={errorToast} kind="error" onDismiss={() => setErrorToast(null)} />
      )}
    </>
  )
}

export default App
