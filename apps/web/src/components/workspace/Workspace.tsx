import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../../api'
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
      <path d="M6 3h9l4 4v14H6z" />
      <path d="M15 3v4h4" />
      <path d="M9 12h6M9 16h6" />
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

const TABS: { key: WorkspaceTab; label: string; icon: () => React.JSX.Element }[] = [
  { key: 'overview', label: 'Overview', icon: OverviewIcon },
  { key: 'suite', label: 'Test Suite', icon: SuiteIcon },
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
  const [running, setRunning] = useState(false)
  // Snapshotted at mount — App.tsx only ever mounts this component fresh
  // right after a "Run All Tests" click, so the effect below should fire
  // (or not) based on that one moment, not re-run if the prop identity
  // were ever to change later.
  const autoTriggerRunOnMountRef = useRef(autoTriggerRun)

  async function handleRunSuite() {
    setRunning(true)
    setTriggerError(null)
    try {
      await api.triggerTestRun(applicationId)
      setAutoSelectLatest(true)
      setActiveTab('runs')
    } catch (err) {
      setTriggerError(err instanceof ApiError ? err.message : 'Failed to start the test run')
    } finally {
      setRunning(false)
    }
  }

  useEffect(() => {
    if (!autoTriggerRunOnMountRef.current) return
    handleRunSuite()
    // handleRunSuite is stable enough for a mount-only effect — see the ref
    // comment above; re-running it on identity changes isn't the intent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <main style={{ display: 'flex', justifyContent: 'center', padding: '28px 24px' }}>
      <div style={{ maxWidth: 'clamp(760px, 68vw, 1080px)', width: '100%' }}>
        {triggerError && (
          <p role="alert" style={{ color: 'var(--danger-strong)', fontSize: 13, marginBottom: 16 }}>
            {triggerError}
          </p>
        )}

        {/* 3-column grid, not space-between: the tab bar stays visually
            centered on the page regardless of the button's width, instead of
            drifting off-center whenever the "Starting…" label changes it. */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto 1fr',
            alignItems: 'center',
            marginBottom: 20,
            gap: 12,
            borderBottom: '1px solid var(--border)',
          }}
        >
          <span aria-hidden="true" />
          {/* Underline variant, not a segmented pill: icon + label per tab,
              active tab gets an accent underline + accent text — reads as
              primary navigation instead of a filter control (which is what
              the pill style borrowed from ReviewScenarios' readiness filter
              actually reads as). */}
          <div role="tablist" style={{ display: 'inline-flex', gap: 4, justifySelf: 'center' }}>
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
                    alignItems: 'center',
                    gap: 7,
                    padding: '9px 16px 8px',
                    borderRadius: 0,
                    border: 'none',
                    borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
                    background: 'transparent',
                    color: active ? 'var(--accent)' : 'var(--ink-muted)',
                    fontSize: 13,
                    fontWeight: 600,
                    fontFamily: 'inherit',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <Icon />
                  {tab.label}
                </button>
              )
            })}
          </div>

          {/* Persistent regardless of tab — an enterprise dashboard's primary
              action shouldn't hide inside one specific tab. Play icon so the
              button reads as "go" at a glance, not just another labeled box. */}
          <button
            type="button"
            className="button-primary"
            disabled={running}
            onClick={handleRunSuite}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, justifySelf: 'end' }}
          >
            <PlayIcon />
            {running ? 'Starting…' : 'Run Suite'}
          </button>
        </div>

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
    </main>
  )
}
