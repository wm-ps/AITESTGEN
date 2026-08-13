import { useEffect, useState } from 'react'
import { ApiError, api, type ApplicationRead, type UserRead } from './api'
import { AcceptInvite } from './components/AcceptInvite'
import { ConnectAppForm } from './components/ConnectAppForm'
import { DiscoverJourneys } from './components/DiscoverJourneys'
import { GenerateSuite } from './components/GenerateSuite'
import { Home } from './components/Home'
import { InviteTeammateModal } from './components/InviteTeammateModal'
import { ReviewScenarios } from './components/ReviewScenarios'
import { Settings } from './components/Settings'
import { SignIn } from './components/SignIn'
import type { StepKey } from './components/Stepper'
import { TestSuiteResults } from './components/TestSuiteResults'
import { TopBar } from './components/TopBar'
import { Workspace } from './components/workspace/Workspace'

const VIEW_FOR_STEP: Record<StepKey, View> = {
  'connect-app': 'connect-app',
  discover: 'discover',
  review: 'review-scenarios',
  generate: 'generate-suite',
}

// Previous/Next walk this same order — 'test-suite-results' has no Stepper
// circle of its own (it renders the Stepper with furthestCount 4, all done),
// but it's still a stop along the Previous/Next line.
const VIEW_ORDER: View[] = [
  'connect-app',
  'discover',
  'review-scenarios',
  'generate-suite',
  'test-suite-results',
]

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
  | 'workspace'
  | 'settings'

function App() {
  const [user, setUser] = useState<UserRead | null | undefined>(undefined)
  const [view, setView] = useState<View>('home')
  const [previousView, setPreviousView] = useState<View>('home')
  const [application, setApplication] = useState<ApplicationRead | null>(null)
  // How many of the 4 wizard steps are actually finished — independent of
  // `view`, which is just whichever screen is on screen right now. Lets
  // Previous/Next and the Stepper's own step numbers revisit an earlier
  // completed step without losing its checkmark.
  const [furthestCount, setFurthestCount] = useState(0)
  const [inviteModalOpen, setInviteModalOpen] = useState(false)
  const [inviteToken, setInviteToken] = useState(getInviteTokenFromUrl)
  // Covers logout and resume-application — both involve an API round trip
  // before the screen changes, and users were reading the pause as a hang.
  const [globalLoading, setGlobalLoading] = useState<string | null>(null)
  const [errorToast, setErrorToast] = useState<string | null>(null)

  useEffect(() => {
    if (!errorToast) return
    const timeout = setTimeout(() => setErrorToast(null), 3000)
    return () => clearTimeout(timeout)
  }, [errorToast])

  // Read once by Workspace on mount (it fully remounts each time `view`
  // toggles away from 'workspace' and back) — lets "Run All Tests" land
  // straight on the Runs tab with the new run auto-selected, while a plain
  // dashboard resume lands on Overview as usual.
  const [workspaceEntry, setWorkspaceEntry] = useState<{
    initialTab: 'overview' | 'runs'
    autoTriggerRun: boolean
  }>({ initialTab: 'overview', autoTriggerRun: false })

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
    if (globalLoading) return
    setGlobalLoading('Logging out')
    try {
      await api.logout()
      setUser(null)
      setView('home')
      setApplication(null)
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
      setView(suiteComplete ? 'workspace' : suites.length > 0 ? 'test-suite-results' : 'discover')
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
          view === 'home' ? undefined : application ? { name: application.name, environment: application.environment } : undefined
        }
        onLogout={handleLogout}
        onGoHome={() => setView('home')}
        onInviteTeammate={() => setInviteModalOpen(true)}
        onOpenSettings={() => {
          setPreviousView(view)
          setView('settings')
        }}
      />
      {inviteModalOpen && <InviteTeammateModal onClose={() => setInviteModalOpen(false)} />}
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
          onConnected={() => setView('home')}
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
          onContinueToGenerate={() => {
            setFurthestCount((c) => Math.max(c, 3))
            setView('generate-suite')
          }}
          furthestCount={furthestCount}
          onStepClick={onStepClick}
          onPrevious={onPrevious}
          onNext={onNext}
        />
      )}
      {view === 'generate-suite' && application && (
        <GenerateSuite
          applicationId={application.id}
          onGenerated={() => {
            setFurthestCount(4)
            setView('test-suite-results')
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
          onGoToDashboard={() => {
            setWorkspaceEntry({ initialTab: 'overview', autoTriggerRun: false })
            setView('workspace')
          }}
          onRunAllTests={() => {
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
        />
      )}
      {view === 'settings' && <Settings onCancel={() => setView(previousView)} />}

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
        <div
          role="status"
          style={{
            position: 'fixed',
            right: 'var(--space-9)',
            bottom: 'var(--space-9)',
            background: 'var(--ink)',
            color: '#FFFFFF',
            padding: '12px 18px',
            borderRadius: 'var(--radius)',
            fontSize: 13.5,
            boxShadow: '0 12px 28px rgba(15,23,42,0.25)',
            zIndex: 100,
          }}
        >
          {errorToast}
        </div>
      )}
    </>
  )
}

export default App
