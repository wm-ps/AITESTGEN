import { useEffect, useState } from 'react'
import { api, type TestCaseRead, type TestSuiteRead } from '../api'
import { Stepper, type StepKey } from './Stepper'
import { LoadingDots } from './LoadingDots'

const POLL_INTERVAL_MS = 3000
const SECONDS_PER_TEST_CASE = 45

// Generated Test Assets are Playwright (TypeScript, @playwright/test) — group
// by that real generated file structure, matching the reference prototype's
// `.spec.ts` filenames directly.
function toTestFileName(journeyName: string): string {
  const slug = journeyName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `${slug || 'journey'}.spec.ts`
}

function ArrowRightIcon() {
  return (
    <svg width={26} height={26} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 13l4 4L19 7" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3v12" />
      <path d="M7 10l5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  )
}

function ClipboardCheckIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
      <rect x={9} y={3} width={6} height={4} rx={1} />
      <path d="M9 12l2 2 4-4" />
    </svg>
  )
}

function JourneysIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={5.5} r={2} />
      <circle cx={6} cy={17} r={2} />
      <circle cx={18} cy={17} r={2} />
      <path d="M12 7.5 6 15.3M12 7.5l6 7.8M7.8 17h8.4" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={12} r={9} />
      <path d="M12 7v5l3.5 3.5" />
    </svg>
  )
}

function ChevronIcon({ size, color, open }: { size: number; color: string; open: boolean }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s ease' }}
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

export function StatTile({ icon, value, label }: { icon: React.ReactNode; value: string | number; label: string }) {
  return (
    <div
      style={{
        background: 'var(--canvas)',
        border: '1px solid var(--border-hairline)',
        borderRadius: 'var(--radius-lg)',
        boxSizing: 'border-box',
        padding: '14px 16px',
        boxShadow: '0 4px 14px -3px rgba(15,23,42,0.12), 0 1px 3px rgba(15,23,42,0.07)',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
      }}
    >
      <div
        aria-hidden="true"
        style={{
          width: 28,
          height: 28,
          borderRadius: 9,
          background: 'var(--accent-wash)',
          color: 'var(--accent)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 19, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.1 }}>{value}</div>
        <div style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 3 }}>{label}</div>
      </div>
    </div>
  )
}

// Story 4.2 Task 4a (confirmed against the reference prototype, both by
// direct file inspection and a live click-through): submitting Generate
// Suite lands here; a "Test details" action reveals the per-TestSuite
// breakdown; each test case shows a type badge and a "Code" button opening
// one shared code-viewer modal — not a `<details>`-disclosure list.
const TYPE_BADGE: Record<string, { label: string; background: string; color: string }> = {
  happy: { label: 'Happy Path', background: 'var(--happy-wash)', color: 'var(--happy-strong)' },
  negative: { label: 'Negative Path', background: 'var(--danger-wash)', color: 'var(--danger-strong)' },
  edge: { label: 'Edge Case', background: 'var(--warn-wash)', color: 'var(--warn-strong)' },
}

// Loosened to `{ name, code }` rather than the full `TestCaseRead` so the
// Application Workspace's Test Suite tab (which only has a lazily-fetched
// code string, not a whole TestCaseRead) can reuse this modal too.
export function CodeModal({ testCase, onClose }: { testCase: { name: string; code: string }; onClose: () => void }) {
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
  onRunAllTests,
  furthestCount,
  onStepClick,
  onPrevious,
}: {
  applicationId: string
  onGoToDashboard: () => void
  onRunAllTests: () => void
  furthestCount: number
  onStepClick?: (key: StepKey) => void
  onPrevious?: () => void
}) {
  const [suites, setSuites] = useState<TestSuiteRead[]>([])
  const [expectedTestCaseCount, setExpectedTestCaseCount] = useState(0)
  const [testsExpanded, setTestsExpanded] = useState(false)
  const [expandedSuiteIds, setExpandedSuiteIds] = useState<Set<string>>(new Set())
  const [activeCode, setActiveCode] = useState<TestCaseRead | null>(null)
  const [downloading, setDownloading] = useState(false)

  async function handleDownload() {
    setDownloading(true)
    try {
      await api.downloadTestSuiteProject(applicationId)
    } catch {
      // best-effort — a failed download just leaves the button re-enabled
    } finally {
      setDownloading(false)
    }
  }

  function toggleSuite(suiteId: string) {
    setExpandedSuiteIds((prev) => {
      const next = new Set(prev)
      if (next.has(suiteId)) next.delete(suiteId)
      else next.add(suiteId)
      return next
    })
  }

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

  const testCaseCount = suites.reduce((sum, s) => sum + s.test_cases.length, 0)
  const isComplete = expectedTestCaseCount > 0 && testCaseCount >= expectedTestCaseCount

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
    if (isComplete) return
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId, isComplete])
  const estRuntimeMin = Math.max(1, Math.ceil((testCaseCount * SECONDS_PER_TEST_CASE) / 60))

  if (!isComplete) {
    return (
      <>
        <Stepper current="generate" furthestCount={furthestCount} onStepClick={onStepClick} onPrevious={onPrevious} />
        <main style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32, boxSizing: 'border-box' }}>
          <div role="status" style={{ textAlign: 'center' }}>
            <div
              aria-hidden="true"
              style={{
                width: 64,
                height: 64,
                borderRadius: 'var(--radius-full)',
                background: 'var(--accent-wash)',
                color: 'var(--accent)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 22px',
                boxSizing: 'border-box',
                animation: 'aitg-transition-icon 0.5s ease-out both, aitg-pulse 1.6s ease-in-out 0.5s infinite',
              }}
            >
              <ArrowRightIcon />
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 16 }}>
              Generating your test suite…
            </div>
            <div style={{ display: 'flex', gap: 6, justifyContent: 'center', marginBottom: 16 }}>
              <span style={{ width: 7, height: 7, borderRadius: 'var(--radius-full)', background: 'var(--accent)', animation: 'aitg-dot-bounce 1s ease-in-out infinite', animationDelay: '0s' }} />
              <span style={{ width: 7, height: 7, borderRadius: 'var(--radius-full)', background: 'var(--accent)', animation: 'aitg-dot-bounce 1s ease-in-out infinite', animationDelay: '0.15s' }} />
              <span style={{ width: 7, height: 7, borderRadius: 'var(--radius-full)', background: 'var(--accent)', animation: 'aitg-dot-bounce 1s ease-in-out infinite', animationDelay: '0.3s' }} />
            </div>
            <p className="caption" style={{ margin: 0, fontSize: 12.5 }}>
              {testCaseCount}/{expectedTestCaseCount || '…'} test cases so far
            </p>
            <p className="caption" style={{ margin: '6px 0 0', fontSize: 12, opacity: 0.7 }}>
              Stuck?{' '}
              <button
                type="button"
                onClick={() => onStepClick?.('generate')}
                style={{ font: 'inherit', color: 'var(--accent)', background: 'none', border: 0, padding: 0, cursor: 'pointer' }}
              >
                Resume generation
              </button>
            </p>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <Stepper current="generate" furthestCount={furthestCount} onStepClick={onStepClick} onPrevious={onPrevious} />
      <main style={{ display: 'flex', justifyContent: 'center', padding: '28px 24px' }}>
        <div style={{ maxWidth: 'clamp(760px, 68vw, 1080px)', width: '100%' }}>
          <div
            style={{
              position: 'relative',
              overflow: 'hidden',
              borderRadius: 'var(--radius-2xl)',
              background: 'linear-gradient(135deg, var(--accent) 0%, var(--accent) 55%, rgba(0,0,0,0.25) 100%)',
              padding: '20px 24px',
              textAlign: 'center',
              marginBottom: 16,
            }}
          >
            <span
              aria-hidden="true"
              style={{
                position: 'absolute',
                width: 200,
                height: 200,
                borderRadius: 'var(--radius-full)',
                background: 'rgba(255,255,255,0.08)',
                top: -60,
                right: -40,
                pointerEvents: 'none',
              }}
            />
            <span
              aria-hidden="true"
              style={{
                position: 'absolute',
                width: 160,
                height: 160,
                borderRadius: 'var(--radius-full)',
                background: 'rgba(255,255,255,0.06)',
                bottom: -70,
                left: -30,
                pointerEvents: 'none',
              }}
            />
            <div style={{ position: 'relative' }}>
              <div
                aria-hidden="true"
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 'var(--radius-full)',
                  background: 'rgba(255,255,255,0.16)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 10px',
                }}
              >
                <div style={{ width: 28, height: 28, borderRadius: 'var(--radius-full)', background: '#FFFFFF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <CheckIcon />
                </div>
              </div>
              <h1 style={{ fontSize: 19, fontWeight: 700, color: '#FFFFFF', margin: '0 0 5px' }}>
                Test Suites Generated
              </h1>
              <p style={{ margin: '0 0 14px', fontSize: 12.5, color: 'rgba(255,255,255,0.85)' }}>
                Generated {testCaseCount} test cases across {suites.length} journeys · Est. runtime{' '}
                {estRuntimeMin} min
              </p>
              <div style={{ display: 'flex', justifyContent: 'center', gap: 10 }}>
                <button
                  type="button"
                  disabled={downloading}
                  onClick={handleDownload}
                  style={{
                    padding: '9px 20px',
                    background: 'rgba(255,255,255,0.16)',
                    color: '#FFFFFF',
                    border: '1px solid rgba(255,255,255,0.5)',
                    borderRadius: 'var(--radius)',
                    fontSize: 13.5,
                    fontWeight: 700,
                    fontFamily: 'inherit',
                    cursor: downloading ? 'not-allowed' : 'pointer',
                    opacity: downloading ? 0.75 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 7,
                  }}
                >
                  <DownloadIcon />
                  {downloading ? <LoadingDots label="Downloading" /> : 'Download Test Suite'}
                </button>
                <button
                  type="button"
                  onClick={onRunAllTests}
                  style={{
                    padding: '9px 20px',
                    background: 'rgba(255,255,255,0.16)',
                    color: '#FFFFFF',
                    border: '1px solid rgba(255,255,255,0.5)',
                    borderRadius: 'var(--radius)',
                    fontSize: 13.5,
                    fontWeight: 700,
                    fontFamily: 'inherit',
                    cursor: 'pointer',
                  }}
                >
                  Run All Tests
                </button>
                <button
                  type="button"
                  onClick={onGoToDashboard}
                  style={{
                    padding: '9px 22px',
                    background: '#FFFFFF',
                    color: 'var(--accent)',
                    border: 'none',
                    borderRadius: 'var(--radius)',
                    fontSize: 13.5,
                    fontWeight: 700,
                    fontFamily: 'inherit',
                    cursor: 'pointer',
                    boxShadow: '0 8px 16px -6px rgba(0,0,0,0.2)',
                  }}
                >
                  Go to Dashboard →
                </button>
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 16 }}>
            <StatTile icon={<ClipboardCheckIcon />} value={testCaseCount} label="Test cases" />
            <StatTile icon={<JourneysIcon />} value={suites.length} label="Journeys covered" />
            <StatTile icon={<ClockIcon />} value={`${estRuntimeMin} min`} label="Est. runtime" />
          </div>

          <div
            style={{
              background: 'var(--canvas)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              boxSizing: 'border-box',
              overflow: 'hidden',
              boxShadow: '0 4px 14px -3px rgba(15,23,42,0.12), 0 1px 3px rgba(15,23,42,0.07)',
              marginBottom: 24,
            }}
          >
            <button
              type="button"
              onClick={() => setTestsExpanded((o) => !o)}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 12,
                width: '100%',
                padding: '16px 20px',
                background: 'none',
                border: 'none',
                borderBottom: testsExpanded ? '1px solid var(--border-hairline)' : 'none',
                textAlign: 'left',
                fontFamily: 'inherit',
                cursor: 'pointer',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>Generated Tests</div>
                <div style={{ fontSize: 12, color: 'var(--ink-muted)', marginTop: 2 }}>
                  {testCaseCount > 0
                    ? `${testCaseCount} test${testCaseCount === 1 ? '' : 's'} across ${suites.length} file${suites.length === 1 ? '' : 's'}`
                    : 'No tests generated'}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent)', whiteSpace: 'nowrap' }}>
                  {testsExpanded ? 'Hide Tests' : 'View Tests'}
                </span>
                <ChevronIcon size={15} color="var(--accent)" open={testsExpanded} />
              </div>
            </button>

            {testsExpanded &&
              suites.map((suite) => {
                const suiteOpen = expandedSuiteIds.has(suite.id)
                return (
                  <div key={suite.id} style={{ borderBottom: '1px solid var(--border-hairline)' }}>
                    <button
                      type="button"
                      onClick={() => toggleSuite(suite.id)}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: 12,
                        width: '100%',
                        padding: '14px 20px',
                        background: 'none',
                        border: 'none',
                        textAlign: 'left',
                        fontFamily: 'inherit',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                        <span
                          style={{
                            fontSize: 13,
                            fontWeight: 700,
                            color: 'var(--ink)',
                            fontFamily: 'var(--font-mono)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {toTestFileName(suite.journey_name)}
                        </span>
                        <span style={{ fontSize: 12, color: 'var(--ink-muted)', whiteSpace: 'nowrap', flexShrink: 0 }}>
                          {suite.test_cases.length} test{suite.test_cases.length === 1 ? '' : 's'}
                        </span>
                      </div>
                      <ChevronIcon size={14} color="var(--ink-faint)" open={suiteOpen} />
                    </button>

                    {suiteOpen && (
                      <div style={{ padding: '0 20px 14px', display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {suite.test_cases.map((testCase) => {
                          const badge = TYPE_BADGE[testCase.type] ?? TYPE_BADGE.happy
                          return (
                            <div
                              key={testCase.id}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: 12,
                                padding: '7px 10px',
                                borderRadius: 6,
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
                                    color: 'var(--ink-secondary)',
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
                                  background: 'var(--canvas)',
                                  border: '1px solid var(--border-strong)',
                                  boxShadow: '0 1px 2px rgba(15,23,42,0.06)',
                                  borderRadius: 6,
                                  fontSize: 12,
                                  fontWeight: 600,
                                  color: 'var(--accent)',
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
                    )}
                  </div>
                )
              })}
          </div>

          {activeCode && <CodeModal testCase={activeCode} onClose={() => setActiveCode(null)} />}
        </div>
      </main>
    </>
  )
}
