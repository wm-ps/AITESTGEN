import { useEffect, useState } from 'react'
import { api, type TestCaseRead, type TestSuiteRead } from '../api'

const POLL_INTERVAL_MS = 1500

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

export function TestSuiteResults({ applicationId }: { applicationId: string }) {
  const [suites, setSuites] = useState<TestSuiteRead[]>([])
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [activeCode, setActiveCode] = useState<TestCaseRead | null>(null)

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

  return (
    <main
      style={{
        maxWidth: 'var(--content-max)',
        margin: '0 auto',
        padding: `var(--content-top) var(--content-x)`,
      }}
    >
      <h1 style={{ fontSize: 19, fontWeight: 650, margin: '0 0 8px' }}>Test Suites</h1>

      <div
        className="card-panel"
        style={{ padding: 'var(--space-5)', marginBottom: 'var(--space-4)' }}
      >
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

        {suites.length === 0 ? (
          <p className="caption" style={{ margin: 0 }}>
            Generating — Test Suites will appear here as each Journey's Playwright tests finish.
          </p>
        ) : (
          <button
            type="button"
            onClick={() => setDetailsOpen((o) => !o)}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--signal)',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              padding: 0,
              fontFamily: 'inherit',
            }}
          >
            {detailsOpen ? 'Hide test details' : 'Test details →'}
          </button>
        )}
      </div>

      {detailsOpen &&
        suites.map((suite) => (
          <div
            key={suite.id}
            className="card-panel"
            style={{ padding: 0, marginBottom: 'var(--space-3)', overflow: 'hidden' }}
          >
            <div
              style={{
                padding: 'var(--space-3) var(--space-4)',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span style={{ fontSize: 13.5, fontWeight: 700 }}>{suite.name}</span>
              <span className="caption" style={{ fontSize: 12 }}>
                {suite.test_cases.length} test case{suite.test_cases.length === 1 ? '' : 's'}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
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
                      padding: '10px 16px',
                      borderBottom: '1px solid var(--border)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '2px 8px',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: 10.5,
                          fontWeight: 650,
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
                        background: '#FFFFFF',
                        color: 'var(--signal)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: 12,
                        fontWeight: 600,
                        fontFamily: 'inherit',
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                        flexShrink: 0,
                      }}
                    >
                      Code
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        ))}

      {activeCode && <CodeModal testCase={activeCode} onClose={() => setActiveCode(null)} />}
    </main>
  )
}
