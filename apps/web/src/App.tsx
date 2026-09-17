import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCircleDot, faListCheck, faRoute } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type ApplicationRead, type UserRead } from './api'
import { AcceptInvite } from './components/AcceptInvite'
import { ConnectAppForm } from './components/ConnectAppForm'
import { DiscoverJourneys } from './components/DiscoverJourneys'
import { AppBootLoader, GlobalLoadingOverlay } from './components/GlobalLoadingOverlay'
import { Home } from './components/Home'
import { Overview } from './components/Overview'
import { RecordAndPlay } from './components/RecordAndPlay'
import { ResetPassword } from './components/ResetPassword'
import { ReviewScenarios } from './components/ReviewScenarios'
import { Settings } from './components/Settings'
import { ServiceError } from './components/ServiceError'
import { SignIn } from './components/SignIn'
import { TeamMembers } from './components/TeamMembers'
import { TestSuiteResults } from './components/TestSuiteResults'
import { Toast } from './components/Toast'
import { Workspace, type WorkspaceTab, WORKSPACE_TABS } from './components/workspace/Workspace'
import { AppShell, type AppShellTab, type ShellRoute } from './components/shell/AppShell'

// Vantage V2 redesign: AppShell (left sidebar + topbar) wraps every
// signed-in view. Views that used to be separate Stepper-gated wizard
// screens (Discover Journeys, Review Scenarios, the post-generate results
// screen) plus Workspace's own internal tab rail are now one persistent
// per-application tab set living in AppShell's sidebar "Application"
// section — matching the prototype's Overview/Journeys/Scenarios/Test
// cases/Test runs/Record and play/Schedules and CI tabs. Credentials stays
// as an extra tab beyond the prototype's 8 (no prototype-tab home for
// existing per-app credential rotation) and Download project stays folded
// into Test cases (TestSuiteTab already combines suite view + export).
const SHELL_ROUTE_FOR_VIEW: Partial<Record<View, ShellRoute>> = {
  overview: 'overview',
  home: 'apps',
  'connect-app': 'wizard',
  app: 'app',
  settings: 'settings',
  team: 'team',
}
const SHELL_CRUMB_FOR_VIEW: Partial<Record<View, string>> = {
  overview: 'Overview',
  home: 'Applications',
  'connect-app': 'Add application',
  settings: 'Settings',
  team: 'Team members',
}

function JourneysIcon() {
  return <FontAwesomeIcon icon={faRoute} style={{ fontSize: 15 }} />
}
function ScenariosIcon() {
  return <FontAwesomeIcon icon={faListCheck} style={{ fontSize: 15 }} />
}
function RecordIcon() {
  return <FontAwesomeIcon icon={faCircleDot} style={{ fontSize: 15 }} />
}

// journeys/scenarios/record aren't part of Workspace's own tab set (they
// predate it, or have no backend yet) — merged with Workspace's static tab
// list below, then reordered to the prototype's sequence.
const JOURNEYS_TAB = { key: 'journeys', label: 'Journeys', heading: 'Discover Journeys', icon: JourneysIcon }
const SCENARIOS_TAB = { key: 'scenarios', label: 'Scenarios', heading: 'Review Scenarios', icon: ScenariosIcon }
const RECORD_TAB = { key: 'record', label: 'Record and play', heading: 'Record and play', icon: RecordIcon }
const TAB_ORDER = ['overview', 'journeys', 'scenarios', 'suite', 'runs', 'record', 'schedules', 'export']

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

type AppTab = 'journeys' | 'scenarios' | 'record' | WorkspaceTab

type View = 'overview' | 'home' | 'connect-app' | 'app' | 'settings' | 'team'

function App() {
  const [user, setUser] = useState<UserRead | null | undefined>(undefined)
  // A network-level failure (fetch never got a response — backend/pods down)
  // isn't an ApiError, so it can't mean "not signed in". Route it to the
  // generic error screen instead of silently bouncing to SignIn.
  const [serviceDown, setServiceDown] = useState(false)
  const [view, setView] = useState<View>('overview')
  const [previousView, setPreviousView] = useState<View>('overview')
  const [application, setApplication] = useState<ApplicationRead | null>(null)
  const [inviteToken, setInviteToken] = useState(getInviteTokenFromUrl)
  const [resetToken, setResetToken] = useState(getResetTokenFromUrl)
  // Covers logout and resume-application — both involve an API round trip
  // before the screen changes, and users were reading the pause as a hang.
  const [globalLoading, setGlobalLoading] = useState<string | null>(null)
  const [errorToast, setErrorToast] = useState<string | null>(null)

  // Which per-application tab is active — freely clickable via AppShell's
  // sidebar, no more furthestCount/Stepper gating (the tabs each handle
  // their own "nothing here yet" state, same as Workspace's tabs already
  // did before this merge).
  const [appTab, setAppTab] = useState<AppTab>('journeys')
  // One-shot: set when "Generate Test Suite" (Scenarios tab) or "Run Tests"
  // (the post-generate results screen) fires, so the Test cases / Test runs
  // tab shows that transitional screen once, then reverts to the steady-
  // state tab content on any other navigation — same one-time-screen
  // behavior the old 'test-suite-results' view had.
  const [justGeneratedSuite, setJustGeneratedSuite] = useState(false)
  const [autoTriggerRun, setAutoTriggerRun] = useState(false)
  // Same one-shot idea for Scenarios: journeys existing is not evidence
  // generation was triggered (Scenarios is a standing sidebar tab, reachable
  // without ever clicking Journeys' Continue) — only this deliberate
  // transition means generation actually started.
  const [justStartedScenarios, setJustStartedScenarios] = useState(false)
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

  if (user === undefined) return <AppBootLoader />

  if (user === null) {
    return <SignIn onSignedIn={setUser} />
  }

  async function handleLogout() {
    if (globalLoading) return
    setGlobalLoading('Logging out')
    try {
      await api.logout()
      setUser(null)
      setView('overview')
      setApplication(null)
    } catch {
      setErrorToast('Failed to log out. Please try again.')
    } finally {
      setGlobalLoading(null)
    }
  }

  // Switches immediately instead of blocking behind a full-screen spinner
  // overlay — Workspace's own tabs (Overview/Journeys/Scenarios/Test cases)
  // already show their own skeleton/loading state while this data resolves,
  // so a second, separate "Loading project" spinner on top of that is
  // redundant. Lands on Overview optimistically; corrected below once the
  // real generation state is known.
  async function handleResumeApplication(app: ApplicationRead) {
    if (globalLoading) return
    setApplication(app)
    setJustGeneratedSuite(false)
    setAutoTriggerRun(false)
    setAppTab('overview')
    setView('app')
    try {
      const [scenarios, suites] = await Promise.all([
        api.listScenarios(app.id),
        api.listTestSuites(app.id),
      ])
      // A TestSuite row exists as soon as generation starts (before its
      // TestAssets do) — resuming mid-generation must land back on the
      // Test cases tab's generating state, not stay on Overview with a
      // partial suite.
      // `[FIXED]` `testCaseCount >= scenarios.length` looked like the right
      // "is generation done" gate but a Scenario that's permanently skipped
      // (over the max_test_cases_per_application cap) or failed all its wave
      // retries never contributes a TestAsset — the count then never
      // catches up even though generation genuinely finished, so every
      // fresh resume of that application landed back on this fake
      // "generating" state forever (until any manual sidebar tab click,
      // which unconditionally clears this flag in `selectAppTab` below —
      // that's why switching tabs and back always looked like it "fixed"
      // it). `suites_generating_count`'s own status-based signal
      // (Home.tsx's `suiteGenerating`) doesn't have this problem — mirror
      // that here instead of re-deriving completion from counts.
      //
      // `[FIXED]` regression: that alone still isn't the right gate for
      // this specific full-screen takeover — it's meant for "you just
      // asked to bulk-generate the whole suite from scratch and nothing
      // exists yet" (TestSuiteResults' own aggregate %/count reads as one
      // suite-wide run). A live-exploration ("Author a test case") request
      // also flips one Journey's TestSuite to 'generating' for its ~1-3
      // scenarios while every other journey's suite is already 'complete'
      // — that must land on the normal Test cases tab (which already shows
      // the existing list plus its own inline progress via TestSuiteTab's
      // own poll), not hijack the whole screen with an aggregate view that
      // has nothing to do with what's actually generating.
      const noSuiteHasFinishedYet = suites.length > 0 && !suites.some((s) => s.status === 'complete')
      const suiteGenerating =
        noSuiteHasFinishedYet && suites.some((s) => s.status === 'generating')
      setJustGeneratedSuite(suiteGenerating)
      setAppTab(
        suiteGenerating
          ? 'suite'
          : suites.length > 0
            ? 'overview'
            : scenarios.length > 0
              ? 'scenarios'
              : 'journeys',
      )
    } catch {
      setApplication(null)
      setView('home')
      setErrorToast('Failed to load project. Please try again.')
    }
  }

  // Shared by AppShell's sidebar/topbar "Add application" and Home's own
  // connect-app card, so both entry points reset the same state.
  function goAddApplication() {
    setApplication(null)
    setView('connect-app')
  }

  function selectAppTab(tab: string) {
    // A deliberate sidebar click is never the one-shot "just generated /
    // just triggered a run" transition — only the programmatic transitions
    // below (Journeys' Continue, Scenarios' Generate, the results screen's
    // Run Tests) set those flags.
    setJustGeneratedSuite(false)
    setAutoTriggerRun(false)
    setJustStartedScenarios(false)
    setAppTab(tab as AppTab)
  }

  const shellRoute = SHELL_ROUTE_FOR_VIEW[view]

  // Overview/Suite/Runs/Schedules must show from the very first render
  // inside an app — Workspace only mounts (and only then reports its tab
  // list) once the user actually visits one of its own tabs, so waiting on
  // `workspaceTabs` for these would leave the sidebar missing Overview the
  // whole time a user sits on Journeys/Scenarios.
  const mergedAppTabs: AppShellTab[] = application
    ? [...WORKSPACE_TABS, JOURNEYS_TAB, SCENARIOS_TAB, RECORD_TAB]
        .sort((a, b) => TAB_ORDER.indexOf(a.key) - TAB_ORDER.indexOf(b.key))
        .map((t) => ({ key: t.key, label: t.label, icon: t.icon }))
    : []

  const mainContent = (
    <>
      {view === 'overview' && (
        <Overview onConnectApp={goAddApplication} onGoApps={() => setView('home')} onOpenApplication={handleResumeApplication} />
      )}
      {view === 'home' && <Home user={user} onConnectApp={goAddApplication} onResumeApplication={handleResumeApplication} />}
      {view === 'connect-app' && (
        <ConnectAppForm
          application={application}
          onConnected={(connectedApplication) => {
            setApplication(connectedApplication)
            setAppTab('journeys')
            setView('app')
          }}
          onCancel={() => setView('home')}
        />
      )}
      {view === 'app' && application && appTab === 'journeys' && (
        <DiscoverJourneys
          applicationId={application.id}
          applicationName={application.name}
          applicationUrl={application.url}
          discoveryStatus={application.discovery_status}
          discoveryStage={application.discovery_stage ?? null}
          discoveryFailureReason={application.discovery_failure_reason ?? null}
          onContinueToScenarios={() => {
            setJustStartedScenarios(true)
            setAppTab('scenarios')
          }}
        />
      )}
      {view === 'app' && application && appTab === 'scenarios' && (
        <ReviewScenarios
          applicationId={application.id}
          applicationName={application.name}
          applicationUrl={application.url}
          generationJustStarted={justStartedScenarios}
          onGoToJourneys={() => setAppTab('journeys')}
          onContinueToGenerate={async () => {
            if (globalLoading) return
            setGlobalLoading('Generating test suite')
            try {
              await api.generateSuite(application.id)
              setJustGeneratedSuite(true)
              setAppTab('suite')
            } catch {
              setErrorToast('Failed to start test suite generation. Please try again.')
            } finally {
              setGlobalLoading(null)
            }
          }}
        />
      )}
      {view === 'app' && application && appTab === 'record' && (
        <RecordAndPlay applicationName={application.name} applicationUrl={application.url} />
      )}
      {view === 'app' && application && appTab !== 'journeys' && appTab !== 'scenarios' && appTab !== 'record' && (
        justGeneratedSuite && appTab === 'suite' ? (
          <TestSuiteResults
            applicationId={application.id}
            onRunTests={() => {
              setJustGeneratedSuite(false)
              setAutoTriggerRun(true)
              setAppTab('runs')
            }}
          />
        ) : (
          <Workspace
            applicationId={application.id}
            applicationName={application.name}
            applicationUrl={application.url}
            activeTab={appTab as WorkspaceTab}
            onActiveTabChange={(tab) => setAppTab(tab)}
            autoTriggerRun={autoTriggerRun}
          />
        )
      )}
      {view === 'settings' && user && <Settings user={user} onCancel={() => setView(previousView)} />}
      {view === 'team' && user && <TeamMembers user={user} />}
    </>
  )

  return (
    <>
      <AppShell
        user={user}
        route={shellRoute ?? 'apps'}
        crumb={
          view === 'app'
            ? (mergedAppTabs.find((t) => t.key === appTab)?.label ?? '')
            : (SHELL_CRUMB_FOR_VIEW[view] ?? '')
        }
        onGoOverview={() => setView('overview')}
        onGoApps={() => setView('home')}
        onAddApplication={goAddApplication}
        onOpenSettings={() => {
          setPreviousView(view)
          setView('settings')
        }}
        onGoTeam={() => setView('team')}
        onLogout={handleLogout}
        app={
          application && view === 'app'
            ? {
                name: application.name,
                tabs: mergedAppTabs,
                activeTab: appTab,
                onSelectTab: selectAppTab,
                onExit: () => setView('home'),
              }
            : undefined
        }
      >
        {mainContent}
      </AppShell>

      {errorToast && (
        <Toast message={errorToast} kind="error" onDismiss={() => setErrorToast(null)} />
      )}

      {globalLoading && <GlobalLoadingOverlay message={globalLoading} />}
    </>
  )
}

export default App
