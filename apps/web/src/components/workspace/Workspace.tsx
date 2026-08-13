import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../../api'
import { OverviewTab } from './OverviewTab'
import { TestSuiteTab } from './TestSuiteTab'
import { RunsTab } from './RunsTab'

type WorkspaceTab = 'overview' | 'suite' | 'runs'

const TABS: { key: WorkspaceTab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'suite', label: 'Test Suite' },
  { key: 'runs', label: 'Runs' },
]

export function Workspace({
  applicationId,
  applicationName,
  initialTab = 'overview',
  autoTriggerRun = false,
}: {
  applicationId: string
  applicationName: string
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
  // Snapshotted at mount — App.tsx only ever mounts this component fresh
  // right after a "Run All Tests" click, so the effect below should fire
  // (or not) based on that one moment, not re-run if the prop identity
  // were ever to change later.
  const autoTriggerRunOnMountRef = useRef(autoTriggerRun)

  useEffect(() => {
    if (!autoTriggerRunOnMountRef.current) return
    let cancelled = false
    api.triggerTestRun(applicationId).catch((err) => {
      if (!cancelled) {
        setTriggerError(err instanceof ApiError ? err.message : 'Failed to start the test run')
      }
    })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  function goToRunsWithNewRun() {
    setAutoSelectLatest(true)
    setActiveTab('runs')
  }

  return (
    <main style={{ display: 'flex', justifyContent: 'center', padding: '28px 24px' }}>
      <div style={{ maxWidth: 'clamp(760px, 68vw, 1080px)', width: '100%' }}>
        <h1 style={{ fontSize: 19, fontWeight: 700, color: 'var(--ink)', margin: '0 0 16px' }}>
          {applicationName}
        </h1>

        {triggerError && (
          <p role="alert" style={{ color: 'var(--danger-strong)', fontSize: 13, marginTop: -8, marginBottom: 16 }}>
            {triggerError}
          </p>
        )}

        <div
          role="tablist"
          style={{
            display: 'inline-flex',
            background: 'var(--canvas-wash)',
            borderRadius: 'var(--radius-full)',
            padding: 4,
            marginBottom: 20,
            gap: 2,
          }}
        >
          {TABS.map((tab) => {
            const active = activeTab === tab.key
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setActiveTab(tab.key)}
                style={{
                  padding: '8px 18px',
                  borderRadius: 'var(--radius-full)',
                  border: 'none',
                  background: active ? 'var(--canvas)' : 'none',
                  color: active ? 'var(--ink)' : 'var(--ink-muted)',
                  fontSize: 13,
                  fontWeight: 600,
                  fontFamily: 'inherit',
                  cursor: 'pointer',
                  boxShadow: active ? '0 1px 3px rgba(15,23,42,0.1)' : 'none',
                }}
              >
                {tab.label}
              </button>
            )
          })}
        </div>

        {activeTab === 'overview' && <OverviewTab applicationId={applicationId} />}
        {activeTab === 'suite' && (
          <TestSuiteTab applicationId={applicationId} onRunStarted={goToRunsWithNewRun} />
        )}
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
