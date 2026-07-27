import { useEffect, useState } from 'react'
import { api, type TestCaseRead, type TestSuiteRead } from '../api'
import { Stepper } from './Stepper'

const POLL_INTERVAL_MS = 1500
const SECONDS_PER_TEST_CASE = 45

function toSpecFileName(journeyName: string): string {
  const slug = journeyName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `${slug || 'journey'}.spec.ts`
}

function Spinner() {
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-block',
        width: 14,
        height: 14,
        borderRadius: '50%',
        border: '2px solid var(--border)',
        borderTopColor: 'var(--signal)',
        animation: 'aitg-spin 0.7s linear infinite',
      }}
    />
  )
}

function StatCard({ icon, value, label }: { icon: string; value: string | number; label: string }) {
  return (
    <div className="card-panel" style={{ padding: 'var(--space-5)', textAlign: 'center' }}>
      <span
        aria-hidden="true"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 32,
          height: 32,
          borderRadius: 'var(--radius-full)',
          background: 'var(--signal-wash)',
          color: 'var(--signal)',
          marginBottom: 'var(--space-3)',
        }}
      >
        {icon}
      </span>
      <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
      <div className="caption">{label}</div>
    </div>
  )
}

// Story 4.2 Task 4a (confirmed against the reference prototype, both by
// direct file inspection and a live click-through): submitting Generate
// Suite lands here; a "Test details" action reveals the per-TestSuite
// breakdown; each test case shows a type badge and a "Code" button opening
// one shared code-viewer modal — not a `<details>`-disclosure list.
const TYPE_BADGE: Record<string, { label: string; background: string; color: string }> = {
  happy: { label: 'Happy Path', background: 'var(--good-wash)', color: 'var(--good)' },
  negative: { label: 'Negative Path', background: 'var(--danger-wash)', color: 'var(--danger)' },
  edge: { label: 'Edge Case', background: 'var(--warn-wash)', color: 'var(--warn)' },
}

function CodeModal({ testCase, onClose }: { testCase: TestCaseRead; onClose: () => void }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${testCase.name} code`}
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,23,42,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#0F172A',
          borderRadius: 'var(--radius)',
          width: 'min(720px, 92vw)',
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '12px 16px',
            borderBottom: '1px solid rgba(255,255,255,0.1)',
          }}
        >
          <span style={{ color: '#E2E8F0', fontSize: 13, fontWeight: 600 }}>{testCase.name}</span>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: '#94A3B8',
              cursor: 'pointer',
              fontSize: 16,
              lineHeight: 1,
              padding: 4,
            }}
          >
            ✕
          </button>
        </div>
        <pre
          style={{
            margin: 0,
            padding: 20,
            overflow: 'auto',
            fontSize: 12.5,
            lineHeight: 1.6,
            color: '#D1D5DB',
            fontFamily: "'SFMono-Regular',Consolas,monospace",
            whiteSpace: 'pre',
          }}
        >
          {testCase.code}
        </pre>
      </div>
    </div>
  )
}

export function TestSuiteResults({
  applicationId,
  onGoToDashboard,
}: {
  applicationId: string
  onGoToDashboard: () => void
}) {
  const [suites, setSuites] = useState<TestSuiteRead[]>([])
  const [expectedTestCaseCount, setExpectedTestCaseCount] = useState(0)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [activeCode, setActiveCode] = useState<TestCaseRead | null>(null)

  useEffect(() => {
    let cancelled = false
    api.listScenarios(applicationId).then((scenarios) => {
      if (cancelled) return
      setExpectedTestCaseCount(scenarios.length)
    })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const rows = await api.listTestSuites(applicationId)
        if (!cancelled) setSuites(rows)
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
    }

    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId])

  const testCaseCount = suites.reduce((sum, s) => sum + s.test_cases.length, 0)
  const isComplete = expectedTestCaseCount > 0 && testCaseCount >= expectedTestCaseCount
  const estRuntimeMin = Math.max(1, Math.ceil((testCaseCount * SECONDS_PER_TEST_CASE) / 60))

  if (!isComplete) {
    return (
      <>
        <Stepper current="generate" />
        <main
          style={{
            maxWidth: 'var(--content-max)',
            margin: '0 auto',
            padding: `var(--content-top) var(--content-x)`,
          }}
        >
          <h1 style={{ fontSize: 19, fontWeight: 650, margin: '0 0 8px' }}>Test Suites</h1>
          <div className="card-panel" style={{ padding: 'var(--space-5)' }}>
            <div style={{ display: 'flex', gap: 'var(--space-5)', marginBottom: 'var(--space-4)' }}>
              <div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{suites.length}</div>
                <div className="caption" style={{ fontSize: 12 }}>
                  Test Suite{suites.length === 1 ? '' : 's'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{testCaseCount}</div>
                <div className="caption" style={{ fontSize: 12 }}>
                  Test case{testCaseCount === 1 ? '' : 's'}
                </div>
              </div>
            </div>
            <p
              className="caption"
              role="status"
              style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}
            >
              <Spinner />
              Generating — {testCaseCount}/{expectedTestCaseCount || '…'} test cases so far…
            </p>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <Stepper current="generate" allComplete />
      <main
        style={{
          maxWidth: 'var(--content-max)',
          margin: '0 auto',
          padding: `var(--content-top) var(--content-x)`,
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 'var(--space-6)' }}>
          <span
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 48,
              height: 48,
              borderRadius: 'var(--radius-full)',
              background: 'var(--good-wash)',
              color: 'var(--good)',
              fontSize: 20,
              marginBottom: 'var(--space-4)',
            }}
          >
            ✓
          </span>
          <h1 style={{ fontSize: 21, fontWeight: 700, margin: '0 0 6px' }}>Test Suites Generated</h1>
          <p className="caption" style={{ margin: '0 0 var(--space-5)' }}>
            Generated {testCaseCount} test cases across {suites.length} journeys · Est. runtime{' '}
            {estRuntimeMin} min
          </p>
          <button
            type="button"
            onClick={onGoToDashboard}
            style={{
              padding: '10px 20px',
              background: 'var(--signal)',
              color: 'var(--signal-ink)',
              border: 'none',
              borderRadius: 'var(--radius)',
              fontSize: 14,
              fontWeight: 600,
              fontFamily: 'inherit',
              cursor: 'pointer',
            }}
          >
            Go to Dashboard →
          </button>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 'var(--space-4)',
            marginBottom: 'var(--space-6)',
          }}
        >
          <StatCard icon="✓" value={testCaseCount} label="Test cases" />
          <StatCard icon="◈" value={suites.length} label="Journeys covered" />
          <StatCard icon="◷" value={`${estRuntimeMin} min`} label="Est. runtime" />
        </div>

        <div className="card-panel" style={{ padding: 0 }}>
          <button
            type="button"
            onClick={() => setDetailsOpen((o) => !o)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: 'var(--space-4)',
              background: 'none',
              border: 'none',
              borderBottom: detailsOpen ? '1px solid var(--border)' : 'none',
              width: '100%',
              textAlign: 'left',
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--signal)',
              fontFamily: 'inherit',
              cursor: 'pointer',
            }}
          >
            {detailsOpen ? 'Hide test details' : 'Show test details'}
            <span aria-hidden="true">{detailsOpen ? '⌃' : '⌄'}</span>
          </button>

          {detailsOpen &&
            suites.map((suite) => (
              <div
                key={suite.id}
                style={{ padding: 'var(--space-4)', borderBottom: '1px solid var(--border)' }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 'var(--space-2)',
                  }}
                >
                  <div
                    style={{ fontSize: 13, fontWeight: 700, fontFamily: 'var(--font-mono, monospace)' }}
                  >
                    {toSpecFileName(suite.journey_name)}
                  </div>
                  <div className="caption" style={{ fontSize: 12 }}>
                    {suite.test_cases.length} test{suite.test_cases.length === 1 ? '' : 's'}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {suite.test_cases.map((testCase) => {
                    const badge = TYPE_BADGE[testCase.type] ?? TYPE_BADGE.happy
                    return (
                      <div
                        key={testCase.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 'var(--space-3)',
                          padding: '8px 4px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                          <span
                            style={{
                              display: 'inline-block',
                              padding: '2px 7px',
                              borderRadius: 6,
                              fontSize: 10.5,
                              fontWeight: 600,
                              background: badge.background,
                              color: badge.color,
                              flexShrink: 0,
                            }}
                          >
                            {badge.label}
                          </span>
                          <span
                            style={{
                              fontSize: 13,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {testCase.name}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setActiveCode(testCase)}
                          style={{
                            padding: '5px 12px',
                            background: 'var(--paper)',
                            border: '1px solid var(--border)',
                            borderRadius: 6,
                            fontSize: 12,
                            fontWeight: 600,
                            fontFamily: 'inherit',
                            cursor: 'pointer',
                            whiteSpace: 'nowrap',
                            flexShrink: 0,
                          }}
                        >
                          View Code
                        </button>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
        </div>

        {activeCode && <CodeModal testCase={activeCode} onClose={() => setActiveCode(null)} />}
      </main>
    </>
  )
}
