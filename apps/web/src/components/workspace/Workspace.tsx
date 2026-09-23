import { useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faClock, faDownload, faFlaskVial, faGauge, faPen, faTableList } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api } from '../../api'
import { AppIdentityLine } from '../AppIdentityLine'
import { ServiceErrorNote } from '../ServiceError'
import { Toast } from '../Toast'
import { DownloadTab } from './DownloadTab'
import { NotesTab } from './NotesTab'
import { OverviewTab } from './OverviewTab'
import { RunJourneysDialog } from './RunJourneysDialog'
import { RunSuiteButton } from './RunSuiteButton'
import { SchedulesTab } from './SchedulesTab'
import { TestSuiteTab } from './TestSuiteTab'
import { RunsTab } from './RunsTab'

export type WorkspaceTab = 'overview' | 'suite' | 'runs' | 'schedules' | 'export' | 'notes'

// Matches the prototype's per-application nav (fa-gauge/fa-table-list/
// fa-flask-vial/fa-clock/fa-download), replacing the previous hand-drawn SVGs.
function OverviewIcon() {
  return <FontAwesomeIcon icon={faGauge} style={{ fontSize: 15 }} />
}

function SuiteIcon() {
  return <FontAwesomeIcon icon={faTableList} style={{ fontSize: 15 }} />
}

function RunsIcon() {
  return <FontAwesomeIcon icon={faFlaskVial} style={{ fontSize: 15 }} />
}

function SchedulesIcon() {
  return <FontAwesomeIcon icon={faClock} style={{ fontSize: 15 }} />
}

function DownloadIcon() {
  return <FontAwesomeIcon icon={faDownload} style={{ fontSize: 15 }} />
}

function NotesIcon() {
  return <FontAwesomeIcon icon={faPen} style={{ fontSize: 15 }} />
}

const RUN_IS_ACTIVE = (status: string) => status === 'pending' || status === 'running'
const RUN_POLL_MS = 2000

// `label` is the nav rail's word — kept short, the rail has no room for
// more. `heading` is the fuller name shown as the content pane's page title.
export const WORKSPACE_TABS: { key: WorkspaceTab; label: string; heading: string; icon: () => React.JSX.Element }[] = [
  { key: 'overview', label: 'Overview', heading: 'Overview', icon: OverviewIcon },
  { key: 'suite', label: 'Test cases', heading: 'Test cases', icon: SuiteIcon },
  { key: 'runs', label: 'Test runs', heading: 'Test runs', icon: RunsIcon },
  { key: 'schedules', label: 'Schedules and CI', heading: 'Schedules and CI', icon: SchedulesIcon },
  { key: 'export', label: 'Download project', heading: 'Download project', icon: DownloadIcon },
  { key: 'notes', label: 'Notes', heading: 'Notes', icon: NotesIcon },
]

export function Workspace({
  applicationId,
  applicationName,
  applicationUrl,
  activeTab,
  onActiveTabChange,
  onTabsChange,
  autoTriggerRun = false,
}: {
  applicationId: string
  applicationName: string
  applicationUrl: string
  activeTab: WorkspaceTab
  // Widened beyond WorkspaceTab — OverviewTab's quick-action shortcuts can
  // also jump to 'journeys'/'scenarios'/'record', which live in App.tsx's
  // `appTab` state, not this component's own `activeTab`. The caller
  // (App.tsx) already handles every value in that broader union.
  onActiveTabChange: (tab: WorkspaceTab | 'journeys' | 'scenarios' | 'record') => void
  // Reports the currently-visible tab list up to the caller (AppShell's
  // sidebar renders it) whenever it changes.
  onTabsChange?: (tabs: typeof WORKSPACE_TABS) => void
  // Set by App.tsx's "Run All Tests" wiring (TestSuiteResults's celebratory
  // banner) — Workspace owns the actual trigger call so the resulting error
  // (if any) has somewhere to surface, mirroring what the old standalone
  // TestExecutionResults.tsx screen used to show.
  autoTriggerRun?: boolean
}) {
  // Set once, the moment "Run Suite"/"Run All Tests" switches to the Runs
  // tab — consumed by RunsTab's own auto-select-newest-run poll, then never
  // re-armed just by switching tabs again. Workspace remounts fresh whenever
  // the user leaves and returns to any of its tabs (App.tsx swaps it out for
  // Journeys/Scenarios in between), so reading `activeTab` once at mount —
  // not in an effect — still captures "did we land here already on Runs".
  const [autoSelectLatest, setAutoSelectLatest] = useState(activeTab === 'runs')
  // Overview has nothing to show before a run exists (health/pass-rate/
  // trend are all meaningless) — kept out of the nav rail entirely until
  // then, rather than showing it just to land on its own empty state.
  const [hasRunEver, setHasRunEver] = useState(false)
  // Nothing to download and nothing worth running before the suite has
  // written at least one test case — kept out of the nav rail (Download
  // project) and off the toolbar (Run Suite) until then, same reasoning as
  // hasRunEver above.
  const [hasTestsGenerated, setHasTestsGenerated] = useState(false)
  const [triggerError, setTriggerError] = useState<string | null>(null)
  const [triggerErrorUnavailable, setTriggerErrorUnavailable] = useState(false)
  const [running, setRunning] = useState(false)
  const [runToast, setRunToast] = useState<string | null>(null)
  // Set by RunsTab while a single run's detail is open, so the back button
  // can sit next to this page's own "Test Runs" title instead of RunsTab
  // rendering a second, duplicate heading of its own.
  const [runsBack, setRunsBack] = useState<(() => void) | null>(null)
  // Run Suite Flow: "Run Journey(s)…" wizard, opened from this page's
  // toolbar RunSuiteButton.
  const [journeysDialogOpen, setJourneysDialogOpen] = useState(false)
  // Snapshotted at mount — App.tsx only ever mounts this component fresh
  // right after a "Run All Tests" click, so the effect below should fire
  // (or not) based on that one moment, not re-run if the prop identity
  // were ever to change later.
  const autoTriggerRunOnMountRef = useRef(autoTriggerRun)
  // `POST .../test-runs` returns before `PrepareTestRunActivity` has even
  // created the TestRun row (see the API's own comment on that endpoint), so
  // the poll below can briefly see no active run right after triggering.
  // This holds the button disabled through that gap; the poll itself is the
  // only thing that ever turns it back off.
  const suppressReenableUntilRef = useRef(0)

  useEffect(() => {
    if (!runToast) return
    const timeout = setTimeout(() => setRunToast(null), 4000)
    return () => clearTimeout(timeout)
  }, [runToast])

  // Single source of truth for "is any run active right now" — runs
  // continuously while this Application's workspace is open, so the button
  // reflects reality regardless of who/what started the run (this click, a
  // reload mid-run, another tab), not just runs this instance itself fired.
  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const page = await api.listTestRuns(applicationId, null, 1)
        if (cancelled) return
        const latest = page.items[0]
        const active = !!latest && RUN_IS_ACTIVE(latest.status)
        setRunning(active || Date.now() < suppressReenableUntilRef.current)
        // Only a finished run (completed or blocked) unlocks the Overview
        // tab — a run still pending/running has nothing for it to show yet.
        if (latest && !active) setHasRunEver(true)
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
      try {
        const suiteStatus = await api.getTestSuiteStatus(applicationId, 1, 1, '')
        if (!cancelled && suiteStatus.total > 0) setHasTestsGenerated(true)
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
    }
    poll()
    const interval = setInterval(poll, RUN_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId])

  async function handleRunSuite(journeyRun?: { suiteName: string; testCaseIds: string[] }) {
    setRunning(true)
    setTriggerError(null)
    setTriggerErrorUnavailable(false)
    setRunToast('Run started…')
    try {
      await api.triggerTestRun(
        applicationId,
        journeyRun
          ? { suite_name: journeyRun.suiteName, test_case_ids: journeyRun.testCaseIds }
          : undefined,
      )
      suppressReenableUntilRef.current = Date.now() + 5000
      setAutoSelectLatest(true)
      onActiveTabChange('runs')
    } catch (err) {
      if (err instanceof ApiError && err.message !== 'EXECUTION_UNAVAILABLE') {
        setTriggerError(err.message)
      } else {
        setTriggerErrorUnavailable(true)
      }
      setRunning(false)
    }
  }

  useEffect(() => {
    if (!autoTriggerRunOnMountRef.current) return
    // Cleared before firing, not after — StrictMode dev double-invokes this
    // effect (mount, cleanup, mount again) to catch exactly this kind of
    // non-idempotent effect; `handleRunSuite` has no dedupe of its own
    // (triggerTestRun always starts a genuinely new run), so without this
    // the second pass fired a real duplicate run.
    autoTriggerRunOnMountRef.current = false
    handleRunSuite()
    // handleRunSuite is stable enough for a mount-only effect — see the ref
    // comment above; re-running it on identity changes isn't the intent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Reported to the caller (AppShell's sidebar renders these) — re-fires
  // once `hasRunEver` flips true so Overview appears without needing a
  // remount.
  useEffect(() => {
    onTabsChange?.(
      WORKSPACE_TABS.filter(
        (tab) => (tab.key !== 'overview' || hasRunEver) && (tab.key !== 'export' || hasTestsGenerated),
      ),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasRunEver, hasTestsGenerated])

  return (
    <main style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
            {/* Hidden while a run is expanded — RunDetail renders its own
                back button next to "Run #<n>" instead, so the run's
                identity replaces this generic tab title rather than
                sitting above a second, redundant one. */}
            {!(activeTab === 'runs' && runsBack) && (
              <>
                <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>
                  {WORKSPACE_TABS.find((tab) => tab.key === activeTab)?.heading}
                </h1>
                {activeTab === 'notes' ? (
                  <div style={{ fontSize: 13.5, color: 'var(--fg-3)' }}>
                    Application context Vantage reads whenever it generates scenarios and test cases for{' '}
                    {applicationName}.
                  </div>
                ) : (
                  <AppIdentityLine name={applicationName} url={applicationUrl} />
                )}
              </>
            )}
          </div>
          {activeTab === 'runs' && hasTestsGenerated && (
            <RunSuiteButton
              running={running}
              onFullSuite={() => handleRunSuite()}
              onOpenJourneysDialog={() => setJourneysDialogOpen(true)}
            />
          )}
        </div>
        {triggerError && (
          <p role="alert" style={{ color: 'var(--danger-strong)', fontSize: 13, marginBottom: 16 }}>
            {triggerError}
          </p>
        )}
        {triggerErrorUnavailable && (
          <div style={{ marginBottom: 16 }}>
            <ServiceErrorNote code="EXECUTION_UNAVAILABLE" />
          </div>
        )}

        {activeTab === 'overview' && (
          <OverviewTab applicationId={applicationId} onNavigateTab={onActiveTabChange} />
        )}
        {activeTab === 'suite' && <TestSuiteTab applicationId={applicationId} />}
        {activeTab === 'schedules' && <SchedulesTab applicationId={applicationId} />}
        {activeTab === 'notes' && <NotesTab applicationId={applicationId} />}
        {activeTab === 'export' && <DownloadTab applicationId={applicationId} applicationName={applicationName} />}
        {activeTab === 'runs' && (
          <RunsTab
            applicationId={applicationId}
            autoSelectLatest={autoSelectLatest}
            onAutoSelectConsumed={() => setAutoSelectLatest(false)}
            onDetailChange={(onBack) => setRunsBack(() => onBack)}
          />
        )}
      </div>

      {runToast && <Toast message={runToast} kind="info" onDismiss={() => setRunToast(null)} />}

      {journeysDialogOpen && (
        <RunJourneysDialog
          applicationId={applicationId}
          onClose={() => setJourneysDialogOpen(false)}
          onExecute={(suiteName, testCaseIds) => {
            setJourneysDialogOpen(false)
            handleRunSuite({ suiteName, testCaseIds })
          }}
        />
      )}
    </main>
  )
}
