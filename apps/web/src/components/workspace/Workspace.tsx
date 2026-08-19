import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../../api'
import { ServiceErrorNote } from '../ServiceError'
import { Toast } from '../Toast'
import { OverviewTab } from './OverviewTab'
import { TestSuiteTab } from './TestSuiteTab'
import { RunsTab } from './RunsTab'

type WorkspaceTab = 'overview' | 'suite' | 'runs'

function OverviewIcon() {
  return (
    <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x={3.5} y={3.5} width={7} height={7} rx={1.5} />
      <rect x={13.5} y={3.5} width={7} height={7} rx={1.5} />
      <rect x={3.5} y={13.5} width={7} height={7} rx={1.5} />
      <rect x={13.5} y={13.5} width={7} height={7} rx={1.5} />
    </svg>
  )
}

function SuiteIcon() {
  return (
    <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3 3 7.5 12 12l9-4.5z" />
      <path d="M3 12l9 4.5 9-4.5" />
      <path d="M3 16.5l9 4.5 9-4.5" />
    </svg>
  )
}

function RunsIcon() {
  return (
    <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={12} r={8.5} />
      <path d="M12 7.5v5l3.2 3.2" />
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

const RUN_IS_ACTIVE = (status: string) => status === 'pending' || status === 'running'
const RUN_POLL_MS = 2000

const TABS: { key: WorkspaceTab; label: string; icon: () => React.JSX.Element }[] = [
  { key: 'overview', label: 'Overview', icon: OverviewIcon },
  { key: 'suite', label: 'Suite', icon: SuiteIcon },
  { key: 'runs', label: 'Runs', icon: RunsIcon },
]

export function Workspace({
  applicationId,
  initialTab = 'overview',
  autoTriggerRun = false,
}: {
  applicationId: string
  initialTab?: WorkspaceTab
  // Set by App.tsx's "Run All Tests" wiring (TestSuiteResults's celebratory
  // banner) — Workspace owns the actual trigger call so the resulting error
  // (if any) has somewhere to surface, mirroring what the old standalone
  // TestExecutionResults.tsx screen used to show.
  autoTriggerRun?: boolean
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
        const page = await api.listTestRuns(applicationId, 1, 1)
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
    <main style={{ display: 'flex', height: 'calc(100vh - 64px)' }}>
      {/* Full-height rail flush against the viewport edge, not a floating
          icon row inline with the content column — icon + label stacked
          per item reads as the dashboard's fixed navigation spine. */}
      <nav
        aria-label="Workspace sections"
        style={{
          width: 76,
          flexShrink: 0,
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 6,
          padding: '20px 8px',
          background: 'var(--canvas)',
          borderRight: '1px solid var(--border)',
        }}
      >
        {TABS.map((tab) => {
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
                width: 60,
                padding: '10px 4px',
                borderRadius: 'var(--radius)',
                border: 'none',
                background: active ? 'var(--accent-wash)' : 'transparent',
                color: active ? 'var(--accent)' : 'var(--ink-muted)',
                fontSize: 11,
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

        {activeTab === 'runs' && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginBottom: 20 }}>
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
          </div>
        )}

        {activeTab === 'overview' && <OverviewTab applicationId={applicationId} />}
        {activeTab === 'suite' && <TestSuiteTab applicationId={applicationId} />}
        {activeTab === 'runs' && (
          <RunsTab
            applicationId={applicationId}
            autoSelectLatest={autoSelectLatest}
            onAutoSelectConsumed={() => setAutoSelectLatest(false)}
          />
        )}
      </div>

      {runToast && <Toast message={runToast} kind="info" onDismiss={() => setRunToast(null)} />}
    </main>
  )
}
