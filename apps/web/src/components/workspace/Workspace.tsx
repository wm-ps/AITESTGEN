import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../../api'
import { ServiceErrorNote } from '../ServiceError'
import { Toast } from '../Toast'
import { AuthoringTab } from './AuthoringTab'
import { CredentialsTab } from './CredentialsTab'
import { OverviewTab } from './OverviewTab'
import { SchedulesTab } from './SchedulesTab'
import { TestSuiteTab } from './TestSuiteTab'
import { RunsTab } from './RunsTab'

type WorkspaceTab = 'overview' | 'suite' | 'runs' | 'schedules' | 'author' | 'credentials'

function OverviewIcon() {
  return (
    <svg width={19} height={19} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x={3.5} y={3.5} width={7} height={7} rx={1.5} />
      <rect x={13.5} y={3.5} width={7} height={7} rx={1.5} />
      <rect x={3.5} y={13.5} width={7} height={7} rx={1.5} />
      <rect x={13.5} y={13.5} width={7} height={7} rx={1.5} />
    </svg>
  )
}

// Same icon Home's "Test cases" stat chip uses — not a new shape.
function SuiteIcon() {
  return (
    <svg width={19} height={19} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6.5 3.5h8l3 3v13a1 1 0 0 1-1 1h-10a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1Z" />
      <path d="M14 3.5V7h3.5" />
      <path d="M8.5 12h7M8.5 15.3h7" />
    </svg>
  )
}

// Same icon Home's "Executions" stat chip uses — not a new shape.
function RunsIcon() {
  return (
    <svg width={19} height={19} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M10.3 8.7 15 12l-4.7 3.3V8.7Z" fill="currentColor" stroke="none" />
    </svg>
  )
}

// Clock face + a small recurrence arrow — reads as "recurring schedule",
// distinct from RunsIcon's single play-triangle-in-a-circle.
function SchedulesIcon() {
  return (
    <svg width={19} height={19} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12.5" r="7.5" />
      <path d="M12 8.5v4.2l3 1.8" />
      <path d="M4.5 5.2A9 9 0 0 1 8 3.2" />
    </svg>
  )
}

function PlayIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M6 4.5v15l13-7.5z" />
    </svg>
  )
}

// Pen (authoring) + spark (assisted/automatic) — distinct from either tile's
// own icon since this one has to represent both at once.
function AuthorIcon() {
  return (
    <svg width={19} height={19} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M13.5 5.5 4.5 14.5 3.5 18.5 7.5 17.5 16.5 8.5Z" />
      <path d="M12 7 15 10" />
      <path d="M18.5 3.5 19.2 5.1 20.8 5.8 19.2 6.5 18.5 8.1 17.8 6.5 16.2 5.8 17.8 5.1Z" fill="currentColor" stroke="none" />
    </svg>
  )
}

function CredentialsIcon() {
  return (
    <svg width={19} height={19} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="8" cy="15" r="4.5" />
      <path d="M11.2 11.8 19.5 3.5M16.5 6.5l2.5 2.5M13.5 9.5l2 2" />
    </svg>
  )
}

const RUN_IS_ACTIVE = (status: string) => status === 'pending' || status === 'running'
const RUN_POLL_MS = 2000

// `label` is the nav rail's word — kept short, the rail has no room for
// more. `heading` is the fuller name shown as the content pane's page title.
const TABS: { key: WorkspaceTab; label: string; heading: string; icon: () => React.JSX.Element }[] = [
  { key: 'overview', label: 'Overview', heading: 'Test Overview', icon: OverviewIcon },
  { key: 'suite', label: 'Suite', heading: 'Test Suite', icon: SuiteIcon },
  { key: 'runs', label: 'Runs', heading: 'Test Runs', icon: RunsIcon },
  { key: 'schedules', label: 'Schedules', heading: 'Schedules', icon: SchedulesIcon },
  { key: 'author', label: 'Author', heading: 'Add Test Cases', icon: AuthorIcon },
  { key: 'credentials', label: 'Credentials', heading: 'Application Credentials', icon: CredentialsIcon },
]

export function Workspace({
  applicationId,
  initialTab = 'overview',
  autoTriggerRun = false,
  isAdmin = false,
}: {
  applicationId: string
  initialTab?: WorkspaceTab
  // Set by App.tsx's "Run All Tests" wiring (TestSuiteResults's celebratory
  // banner) — Workspace owns the actual trigger call so the resulting error
  // (if any) has somewhere to surface, mirroring what the old standalone
  // TestExecutionResults.tsx screen used to show.
  autoTriggerRun?: boolean
  isAdmin?: boolean
}) {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(initialTab)
  // Set once, the moment "Run Suite"/"Run All Tests" switches to the Runs
  // tab — consumed by RunsTab's own auto-select-newest-run poll, then never
  // re-armed just by switching tabs again.
  const [autoSelectLatest, setAutoSelectLatest] = useState(initialTab === 'runs')
  const [triggerError, setTriggerError] = useState<string | null>(null)
  const [triggerErrorUnavailable, setTriggerErrorUnavailable] = useState(false)
  const [running, setRunning] = useState(false)
  const [runToast, setRunToast] = useState<string | null>(null)
  // Set by RunsTab while a single run's detail is open, so the back button
  // can sit next to this page's own "Test Runs" title instead of RunsTab
  // rendering a second, duplicate heading of its own.
  const [runsBack, setRunsBack] = useState<(() => void) | null>(null)
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

  async function handleRunSuite() {
    setRunning(true)
    setTriggerError(null)
    setTriggerErrorUnavailable(false)
    setRunToast('Run will initiate in a few seconds, please wait…')
    try {
      await api.triggerTestRun(applicationId)
      suppressReenableUntilRef.current = Date.now() + 5000
      setAutoSelectLatest(true)
      setActiveTab('runs')
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

  return (
    <main style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      {/* Full-height rail flush against the viewport edge, not a floating
          icon row inline with the content column — icon + label stacked
          per item reads as the dashboard's fixed navigation spine. */}
      <nav
        aria-label="Workspace sections"
        style={{
          width: 92,
          flexShrink: 0,
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 6,
          padding: '20px 8px',
          background: 'var(--canvas)',
          borderRight: '1px solid var(--border)',
          // Page scrolls at the body level (no height cap up the tree), not
          // inside the content pane — sticky keeps the rail pinned to the
          // viewport through that scroll instead of riding away with it.
          position: 'sticky',
          top: 0,
          alignSelf: 'flex-start',
        }}
      >
        {TABS.filter((tab) => tab.key !== 'credentials' || isAdmin).map((tab) => {
          const active = activeTab === tab.key
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setActiveTab(tab.key)}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 4,
                width: 76,
                padding: '10px 4px',
                whiteSpace: 'nowrap',
                borderRadius: 'var(--radius)',
                border: 'none',
                background: active ? 'var(--accent-wash)' : 'transparent',
                color: active ? 'var(--accent)' : 'var(--ink-muted)',
                fontSize: 13,
                fontWeight: 600,
                fontFamily: 'inherit',
                cursor: 'pointer',
              }}
            >
              <Icon />
              {tab.label}
            </button>
          )
        })}
      </nav>

      <div
        style={{
          flex: 1,
          minWidth: 0,
          overflowY: 'auto',
          boxSizing: 'border-box',
          padding: '28px 32px',
          background:
            'radial-gradient(900px 500px at 85% -10%, var(--accent-wash-soft) 0%, transparent 55%), linear-gradient(180deg, #FBFCFE 0%, #F6F9FB 100%)',
        }}
      >
        <div style={{ maxWidth: 'var(--content-max-wide)', margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {/* Hidden while a run is expanded — RunDetail renders its own
                  back button next to "Run #<n>" instead, so the run's
                  identity replaces this generic tab title rather than
                  sitting above a second, redundant one. */}
              {!(activeTab === 'runs' && runsBack) && (
                <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, color: 'var(--ink)' }}>
                  {TABS.find((tab) => tab.key === activeTab)?.heading}
                </h1>
              )}
            </div>
            {activeTab === 'runs' && (
              <button
                type="button"
                className="button-primary"
                disabled={running}
                onClick={handleRunSuite}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
              >
                <PlayIcon />
                {running ? 'Running…' : 'Run Suite'}
              </button>
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
            <OverviewTab applicationId={applicationId} onRunSuite={handleRunSuite} running={running} />
          )}
          {activeTab === 'suite' && <TestSuiteTab applicationId={applicationId} />}
          {activeTab === 'schedules' && <SchedulesTab applicationId={applicationId} />}
          {activeTab === 'author' && <AuthoringTab />}
          {activeTab === 'credentials' && isAdmin && <CredentialsTab applicationId={applicationId} />}
          {activeTab === 'runs' && (
            <RunsTab
              applicationId={applicationId}
              autoSelectLatest={autoSelectLatest}
              onAutoSelectConsumed={() => setAutoSelectLatest(false)}
              onDetailChange={(onBack) => setRunsBack(() => onBack)}
            />
          )}
        </div>
      </div>

      {runToast && <Toast message={runToast} kind="info" onDismiss={() => setRunToast(null)} />}
    </main>
  )
}
