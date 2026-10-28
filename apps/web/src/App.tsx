import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCircleDot, faCompass, faListCheck, faRoute } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, hasDiscovery, type ActivityItemRead, type ApplicationRead, type UserRead } from './api'
import { AcceptInvite } from './components/AcceptInvite'
import { Activity } from './components/Activity'
import { ConnectAppForm } from './components/ConnectAppForm'
import { DiscoverJourneys } from './components/DiscoverJourneys'
import { ExplorerTab } from './explorer/ExplorerTab'
import { AppBootLoader, GlobalLoadingOverlay } from './components/GlobalLoadingOverlay'
import { Home } from './components/Home'
import { Overview } from './components/Overview'
import { RecordAndPlay } from './components/RecordAndPlay'
import { getRecordingPopupParamsFromUrl, RecordingSessionWindow } from './components/RecordingSessionWindow'
import { ResetPassword } from './components/ResetPassword'
import { OpenAllureReport } from './components/OpenAllureReport'
import { getAllureReportRouteFromUrl, getTestRunRouteFromUrl } from './allureReportRoute'
import { ReviewScenarios } from './components/ReviewScenarios'
import { Settings } from './components/Settings'
import { ServiceError } from './components/ServiceError'
import { SignIn } from './components/SignIn'
import { TeamMembers } from './components/TeamMembers'
import { TestSuiteResults } from './components/TestSuiteResults'
import { Toast } from './components/Toast'
import { Workspace, type WorkspaceTab, WORKSPACE_TABS } from './components/workspace/Workspace'
import { AppShell, type AppShellTab, type ShellRoute } from './components/shell/AppShell'
import { PermissionsProvider } from './PermissionsContext'

// Vantage V2 redesign: AppShell (left sidebar + topbar) wraps every
// signed-in view. Views that used to be separate Stepper-gated wizard
// screens (Discover Journeys, Review Scenarios, the post-generate results
// screen) plus Workspace's own internal tab rail are now one persistent
// per-application tab set living in AppShell's sidebar "Application"
// section — matching the prototype's Overview/Journeys/Scenarios/Test
// cases/Test runs/Record and play/Schedules tabs. Credentials stays
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
  activity: 'activity',
}
const SHELL_CRUMB_FOR_VIEW: Partial<Record<View, string>> = {
  overview: 'Overview',
  home: 'Applications',
  'connect-app': 'Add application',
  settings: 'Settings',
  team: 'Team members',
  activity: 'Activity',
}

function JourneysIcon() {
  return <FontAwesomeIcon icon={faRoute} style={{ fontSize: 15 }} />
}
function ScenariosIcon() {
  return <FontAwesomeIcon icon={faListCheck} style={{ fontSize: 15 }} />
}
function ExplorerIcon() {
  return <FontAwesomeIcon icon={faCompass} style={{ fontSize: 15 }} />
}
function RecordIcon() {
  return <FontAwesomeIcon icon={faCircleDot} style={{ fontSize: 15 }} />
}

// journeys/scenarios/record aren't part of Workspace's own tab set (they
// predate it, or have no backend yet) — merged with Workspace's static tab
// list below, then reordered to the prototype's sequence.
const JOURNEYS_TAB = { key: 'journeys', label: 'Journeys', heading: 'Explore Journeys', icon: JourneysIcon }
const SCENARIOS_TAB = { key: 'scenarios', label: 'Scenarios', heading: 'Review Scenarios', icon: ScenariosIcon }
const RECORD_TAB = { key: 'record', label: 'Record and play', heading: 'Record and play', icon: RecordIcon }
// Vantage Explorer (docs/vantage-explorer/PLAN.md) — the discovery module.
const EXPLORER_TAB = { key: 'explorer', label: 'Explorer', heading: 'Explorer', icon: ExplorerIcon }
const TAB_ORDER = ['overview', 'journeys', 'explorer', 'scenarios', 'suite', 'runs', 'record', 'schedules', 'export']

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

type AppTab = 'journeys' | 'explorer' | 'scenarios' | 'record' | WorkspaceTab

type View = 'overview' | 'home' | 'connect-app' | 'app' | 'settings' | 'team' | 'activity'

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
  // /recording-session?vnc=...&control=...&auth=...&app=... — opened in its
  // own tab by RecordAndPlay.tsx's "Record a flow" flow. Never requires a
  // signed-in session here either: the vnc/control URLs already carry the
  // recording token the service re-validates on every connect.
  const [recordingPopupParams] = useState(getRecordingPopupParamsFromUrl)
  // /applications/:appId/test-runs/:runId/report — the stable link to a run's
  // Allure report. Unlike the routes above it *does* need a session, so it's
  // deliberately absent from the me() effect's skip list: signed out it goes
  // through SignIn (which leaves the URL alone), then opens the report.
  const [allureReportRoute] = useState(getAllureReportRouteFromUrl)
  // /applications/:appId/test-runs/:runId — the run-completed email's "Open
  // in Vantage" link. Also needs a session; handled once signed in (below).
  const [testRunLink, setTestRunLink] = useState(getTestRunRouteFromUrl)
  // One-shot: the run the Runs tab opens on after following that link.
  const [openRunId, setOpenRunId] = useState<string | null>(null)
  // Covers logout and resume-application — both involve an API round trip
  // before the screen changes, and users were reading the pause as a hang.
  const [globalLoading, setGlobalLoading] = useState<string | null>(null)
  const [errorToast, setErrorToast] = useState<string | null>(null)
  const [successToast, setSuccessToast] = useState<string | null>(null)

  // Which per-application tab is active — freely clickable via AppShell's
  // sidebar, no more furthestCount/Stepper gating (the tabs each handle
  // their own "nothing here yet" state, same as Workspace's tabs already
  // did before this merge).
  const [appTab, setAppTab] = useState<AppTab>('journeys')
  // One-shot: the scenario a just-saved recording created — Test cases
  // (TestSuiteTab) brings its row into view and flashes it, then reports it
  // consumed. Cleared on any navigation away from 'suite' or to another
  // application, so a stale one never fires on a later visit.
  const [highlightScenarioId, setHighlightScenarioId] = useState<string | null>(null)
  useEffect(() => {
    if (appTab !== 'suite') setHighlightScenarioId(null)
  }, [appTab])
  useEffect(() => {
    setHighlightScenarioId(null)
  }, [application?.id])
  // An application added without discovery has no Journeys/Scenarios tabs —
  // any path that still points at one (stale tab state, a fallback) lands on
  // Test cases instead of a screen that no longer exists for it.
  useEffect(() => {
    if (application && !hasDiscovery(application) && (appTab === 'journeys' || appTab === 'scenarios')) {
      setAppTab('suite')
    }
  }, [application, appTab])
  // Same one-shot idea for Scenarios: journeys existing is not evidence
  // generation was triggered (Scenarios is a standing sidebar tab, reachable
  // without ever clicking Journeys' Continue) — only this deliberate
  // transition means generation actually started.
  const [justStartedScenarios, setJustStartedScenarios] = useState(false)
  // Set right after Generate: Test cases shows the generation-progress screen.
  const [justGeneratedSuite, setJustGeneratedSuite] = useState(false)
  const [autoTriggerRun, setAutoTriggerRun] = useState(false)
  useEffect(() => {
    if (!errorToast) return
    const timeout = setTimeout(() => setErrorToast(null), 3000)
    return () => clearTimeout(timeout)
  }, [errorToast])

  useEffect(() => {
    if (!successToast) return
    const timeout = setTimeout(() => setSuccessToast(null), 6000)
    return () => clearTimeout(timeout)
  }, [successToast])

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
    if (inviteToken || resetToken || recordingPopupParams) return
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
  }, [inviteToken, resetToken, recordingPopupParams])

  // Both lookups go through the normal org-scoped endpoints, so a link to
  // another organization's (or a deleted) run just 404s into a toast.
  useEffect(() => {
    if (!user || !testRunLink) return
    const { applicationId, testRunId } = testRunLink
    setTestRunLink(null)
    window.history.replaceState({}, '', '/')
    setGlobalLoading('Opening test run')
    Promise.all([api.getApplication(applicationId), api.getTestRun(applicationId, testRunId)])
      .then(([app]) => {
        setApplication(app)
        setJustGeneratedSuite(false)
        setAutoTriggerRun(false)
        setOpenRunId(testRunId)
        setAppTab('runs')
        setView('app')
      })
      .catch(() => setErrorToast("That test run couldn't be opened. It may have been deleted."))
      .finally(() => setGlobalLoading(null))
  }, [user, testRunLink])

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

  if (recordingPopupParams) {
    return <RecordingSessionWindow {...recordingPopupParams} />
  }

  if (serviceDown) {
    return <ServiceError code="API_UNAVAILABLE" onRetry={() => window.location.reload()} />
  }

  if (user === undefined) return <AppBootLoader />

  if (user === null) {
    return <SignIn onSignedIn={setUser} />
  }

  if (allureReportRoute) {
    return <OpenAllureReport {...allureReportRoute} />
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
    setAppTab('overview')
    setView('app')
    try {
      const [scenarios, suites] = await Promise.all([
        api.listScenarios(app.id),
        api.listTestSuites(app.id),
      ])
      // A TestSuite row exists as soon as generation starts (before its
      // TestAssets do) — resuming a first-time bulk generation lands on the
      // Test cases tab, which shows its own progress. Status-based, not
      // count-based: a skipped/failed Scenario never yields a TestAsset, so
      // counts never catch up. Only when no suite has finished yet — an
      // "Author a test case" request also flips one journey's suite to
      // 'generating' while the rest are complete; that resumes on Overview.
      const noSuiteHasFinishedYet = suites.length > 0 && !suites.some((s) => s.status === 'complete')
      const suiteGenerating =
        noSuiteHasFinishedYet && suites.some((s) => s.status === 'generating')
      // No Journeys/Scenarios tabs when discovery is off — an empty app
      // lands on Test cases, where its tests get added.
      setAppTab(
        suiteGenerating
          ? 'suite'
          : suites.length > 0
            ? 'overview'
            : !hasDiscovery(app)
              ? 'suite'
              : app.discovery_engine === 'explorer'
                ? 'explorer'
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

  // Activity row "Open": lands on the row's application tab, and on the run
  // itself for a test run — same steps as the run-completed email link above.
  async function openActivityItem(item: ActivityItemRead) {
    if (!item.application_id || !item.target_tab || globalLoading) return
    setGlobalLoading('Opening application')
    try {
      const app = await api.getApplication(item.application_id)
      setApplication(app)
      setJustGeneratedSuite(false)
      setAutoTriggerRun(false)
      setJustStartedScenarios(false)
      if (item.test_run_id) setOpenRunId(item.test_run_id)
      const tab = item.target_tab as AppTab
      setAppTab(!hasDiscovery(app) && (tab === 'journeys' || tab === 'scenarios') ? 'suite' : tab)
      setView('app')
    } catch {
      setErrorToast("That application couldn't be opened. It may have been deleted.")
    } finally {
      setGlobalLoading(null)
    }
  }

  // Turns the app's scenarios into test cases — from the Scenarios page, or
  // straight from Explorer's Scenarios tab for an Explorer app.
  async function generateTests() {
    if (!application || globalLoading) return
    setGlobalLoading('Generating test cases')
    try {
      await api.generateSuite(application.id)
      setJustGeneratedSuite(true)
      setAppTab('suite')
    } catch {
      setErrorToast('Failed to start test case generation. Please try again.')
    } finally {
      setGlobalLoading(null)
    }
  }

  function selectAppTab(tab: string) {
    // A deliberate sidebar click is never the one-shot "just started
    // scenarios" transition — only Journeys' Continue sets that flag.
    setJustStartedScenarios(false)
    setHighlightScenarioId(null)
    setAppTab(tab as AppTab)
  }
  // Journeys/Scenarios only exist for applications with discovery on.
  const discoveryTabsVisible = !application || hasDiscovery(application)

  const shellRoute = SHELL_ROUTE_FOR_VIEW[view]

  // Overview/Suite/Runs/Schedules must show from the very first render
  // inside an app — Workspace only mounts (and only then reports its tab
  // list) once the user actually visits one of its own tabs, so waiting on
  // `workspaceTabs` for these would leave the sidebar missing Overview the
  // whole time a user sits on Journeys/Scenarios.
  // A viewer has no Record and play (it creates test cases) and no Download
  // project (the API refuses them the export).
  const isViewer = user.role === 'viewer'
  // Explorer's output *is* the scenarios (its own Scenarios tab), so an
  // Explorer app has no separate Journeys / Scenarios pages. Their rows
  // still exist underneath: test generation reads them.
  const byExplorer = application?.discovery_engine === 'explorer'
  const mergedAppTabs: AppShellTab[] = application
    ? [
        ...WORKSPACE_TABS,
        // Explorer *is* discovery: an app added without discovery has neither.
        ...(discoveryTabsVisible
          ? [...(byExplorer ? [] : [JOURNEYS_TAB]), EXPLORER_TAB, ...(byExplorer ? [] : [SCENARIOS_TAB])]
          : []),
        RECORD_TAB,
      ].filter((t) => !isViewer || (t.key !== 'record' && t.key !== 'export'))
        .sort((a, b) => TAB_ORDER.indexOf(a.key) - TAB_ORDER.indexOf(b.key))
        .map((t) => ({ key: t.key, label: t.label, icon: t.icon, badge: (t as { badge?: string }).badge }))
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
            setAppTab(
              !hasDiscovery(connectedApplication)
                ? 'suite'
                : connectedApplication.discovery_engine === 'explorer'
                  ? 'explorer'
                  : 'journeys',
            )
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
            setJustStartedScenarios(application.discovery_engine !== 'explorer')
            setAppTab('scenarios')
          }}
          onOpenExplorer={application.discovery_engine === 'explorer' ? () => setAppTab('explorer') : undefined}
        />
      )}
      {view === 'app' && application && appTab === 'scenarios' && (
        <ReviewScenarios
          applicationId={application.id}
          applicationName={application.name}
          applicationUrl={application.url}
          generationJustStarted={justStartedScenarios}
          fromExplorer={application.discovery_engine === 'explorer'}
          onGoToJourneys={() => setAppTab('journeys')}
          onContinueToGenerate={generateTests}
        />
      )}
      {view === 'app' && application && appTab === 'explorer' && (
        <ExplorerTab applicationId={application.id} applicationName={application.name} applicationUrl={application.url} onGenerateTests={generateTests} />
      )}
      {view === 'app' && application && appTab === 'record' && (
        <RecordAndPlay
          applicationId={application.id}
          applicationName={application.name}
          applicationUrl={application.url}
          onSaved={(message, saved) => {
            setSuccessToast(message)
            setHighlightScenarioId(saved.scenarioExternalId)
            setAppTab('suite')
          }}
          onCancelled={setSuccessToast}
        />
      )}
      {view === 'app' && application && appTab !== 'journeys' && appTab !== 'explorer' && appTab !== 'scenarios' && appTab !== 'record' && (
        justGeneratedSuite && appTab === 'suite' ? (
          <TestSuiteResults
            applicationId={application.id}
            onComplete={() => setJustGeneratedSuite(false)}
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
            discoveryEnabled={hasDiscovery(application)}
            activeTab={appTab as WorkspaceTab}
            onActiveTabChange={(tab) => setAppTab(byExplorer && (tab === 'journeys' || tab === 'scenarios') ? 'explorer' : tab)}
            byExplorer={byExplorer}
            autoTriggerRun={autoTriggerRun}
            highlightScenarioId={highlightScenarioId}
            onHighlightConsumed={() => setHighlightScenarioId(null)}
            openRunId={openRunId}
            onOpenRunConsumed={() => setOpenRunId(null)}
          />
        )
      )}
      {view === 'settings' && user && <Settings user={user} onCancel={() => setView(previousView)} />}
      {view === 'team' && user && <TeamMembers user={user} />}
      {view === 'activity' && user && <Activity user={user} onOpen={openActivityItem} onBack={() => setView('overview')} />}
    </>
  )

  return (
    <PermissionsProvider value={user.role}>
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
        onGoActivity={() => setView('activity')}
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
      {successToast && (
        <Toast message={successToast} kind="success" onDismiss={() => setSuccessToast(null)} />
      )}

      {globalLoading && <GlobalLoadingOverlay message={globalLoading} />}
    </PermissionsProvider>
  )
}

export default App
