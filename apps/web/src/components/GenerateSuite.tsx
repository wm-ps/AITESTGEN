import { useEffect, useState } from 'react'
import { api, type JourneyRead, type ScenarioRead } from '../api'
import { ServiceErrorNote } from './ServiceError'
import { Stepper, type StepKey } from './Stepper'
import { Pagination } from './Pagination'

const JOURNEYS_PER_PAGE = 5

const ENV_OPTIONS = [
  ['staging', 'Staging'],
  ['qa', 'QA'],
  ['production', 'Production'],
] as const

function PlayIcon() {
  return (
    <svg width={17} height={17} viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 4v16l14-8Z" />
    </svg>
  )
}

// Story 4.2 AC 2: no suite-name field — each TestSuite is auto-named from
// its own Journey (Task 1), there is nothing for the user to type here.
// (prototype-v3's "Suite name" input predates that decision and isn't
// reintroduced — DESIGN.md itself calls this panel a "visual restyle only";
// behavior, including this, stays as already confirmed/tested.)
export function GenerateSuite({
  applicationId,
  onGenerated,
  furthestCount,
  onStepClick,
  onPrevious,
  onNext,
}: {
  applicationId: string
  onGenerated: () => void
  furthestCount: number
  onStepClick?: (key: StepKey) => void
  onPrevious?: () => void
  onNext?: () => void
}) {
  const [journeys, setJourneys] = useState<JourneyRead[]>([])
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([])
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState(false)
  const [environment, setEnvironment] = useState<(typeof ENV_OPTIONS)[number][0]>('staging')
  const [journeysPage, setJourneysPage] = useState(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.listJourneys(applicationId), api.listScenarios(applicationId)]).then(
      ([journeyRows, scenarioRows]) => {
        if (cancelled) return
        setJourneys(journeyRows)
        setScenarios(scenarioRows)
      },
    )
    return () => {
      cancelled = true
    }
  }, [applicationId])

  // A Test Suite is only created for a Journey that actually has current
  // Scenarios (Task 3) — matches the summary the Generate Suite screen shows.
  const journeysWithScenarios = journeys
    .map((journey) => ({
      journey,
      scenarioCount: scenarios.filter((s) => s.journey_id === journey.id).length,
    }))
    .filter((row) => row.scenarioCount > 0)
  const suiteCount = journeysWithScenarios.length
  const journeysTotalPages = Math.max(1, Math.ceil(journeysWithScenarios.length / JOURNEYS_PER_PAGE))
  const pagedJourneysWithScenarios = journeysWithScenarios.slice(
    journeysPage * JOURNEYS_PER_PAGE,
    journeysPage * JOURNEYS_PER_PAGE + JOURNEYS_PER_PAGE,
  )
  const canGenerate = suiteCount > 0 && !generating
  const envLabel = ENV_OPTIONS.find(([value]) => value === environment)?.[1] ?? 'Staging'

  async function handleGenerate() {
    setGenerating(true)
    setGenerateError(false)
    try {
      await api.generateSuite(applicationId)
      onGenerated()
    } catch {
      setGenerateError(true)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <>
      <Stepper current="generate" furthestCount={furthestCount} onStepClick={onStepClick} onPrevious={onPrevious} onNext={onNext} />
      <main style={{ width: '100%', boxSizing: 'border-box', flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div
          style={{
            flex: 1,
            width: '100%',
            minWidth: 0,
            maxWidth: 'var(--content-max-wide)',
            margin: '0 auto',
            padding: `var(--content-top) var(--content-x)`,
            boxSizing: 'border-box',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
            <div
              aria-hidden="true"
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                background:
                  'linear-gradient(135deg, var(--accent) 0%, var(--accent) 65%, rgba(0,0,0,0.22) 100%)',
                boxShadow: '0 6px 14px -6px var(--accent-wash-soft), inset 0 1px 0 rgba(255,255,255,0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <PlayIcon />
            </div>
            <div>
              <h2 style={{ fontSize: 19, fontWeight: 700, margin: 0, color: 'var(--ink)' }}>Generate Test Suite</h2>
              <div style={{ fontSize: 13, color: 'var(--ink-muted)', marginTop: 2 }}>
                Configure this suite, then generate production-ready tests for every mapped journey.
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }}>
            <div
              style={{
                background: 'var(--canvas)',
                borderRadius: 'var(--radius-xl)',
                boxSizing: 'border-box',
                padding: '22px 24px',
                boxShadow: '0 4px 14px -3px rgba(15,23,42,0.12), 0 1px 3px rgba(15,23,42,0.07)',
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-secondary)', marginBottom: 6 }}>
                Target environment
              </div>
              <select
                value={environment}
                onChange={(e) => setEnvironment(e.target.value as typeof environment)}
                aria-label="Target environment"
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  padding: '10px 12px',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  color: 'var(--ink)',
                  background: 'var(--canvas)',
                }}
              >
                {ENV_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 20 }}>
                <div style={{ textAlign: 'center', padding: '12px 6px', background: 'var(--accent-wash-soft)', borderRadius: 10 }}>
                  <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>{suiteCount}</div>
                  <div style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 2 }}>
                    Test Suite{suiteCount === 1 ? '' : 's'}
                  </div>
                </div>
                <div style={{ textAlign: 'center', padding: '12px 6px', background: 'var(--accent-wash-soft)', borderRadius: 10 }}>
                  <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>{scenarios.length}</div>
                  <div style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 2 }}>
                    Test Case{scenarios.length === 1 ? '' : 's'}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={handleGenerate}
                disabled={!canGenerate}
                style={{
                  width: '100%',
                  marginTop: 16,
                  padding: 13,
                  background: canGenerate ? 'var(--accent)' : 'var(--border)',
                  color: canGenerate ? '#FFFFFF' : 'var(--ink-faint)',
                  border: 'none',
                  borderRadius: 9,
                  fontSize: 14.5,
                  fontWeight: 700,
                  fontFamily: 'inherit',
                  cursor: canGenerate ? 'pointer' : 'not-allowed',
                  boxShadow: canGenerate ? '0 8px 20px -6px var(--accent-wash)' : 'none',
                }}
              >
                {generating ? 'Generating…' : 'Generate Test Suite'}
              </button>
              {generateError && (
                <div style={{ marginTop: 10 }}>
                  <ServiceErrorNote code="GENERATION_UNAVAILABLE" />
                </div>
              )}
            </div>

            <div
              style={{
                background: 'var(--canvas)',
                borderRadius: 'var(--radius-xl)',
                boxSizing: 'border-box',
                padding: '22px 24px',
                boxShadow: '0 4px 14px -3px rgba(15,23,42,0.12), 0 1px 3px rgba(15,23,42,0.07)',
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  color: 'var(--ink-faint)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: 10,
                }}
              >
                Journeys included
              </div>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  borderRadius: 10,
                  overflow: 'hidden',
                  marginBottom: 20,
                }}
              >
                {journeysWithScenarios.length === 0 && (
                  <div className="caption" style={{ fontSize: 12.5, padding: 14 }}>
                    No journeys with reviewed scenarios yet.
                  </div>
                )}
                {pagedJourneysWithScenarios.map(({ journey, scenarioCount }) => (
                  <div
                    key={journey.id}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 8,
                      padding: '10px 14px',
                      background: 'var(--canvas)',
                    }}
                  >
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-secondary)' }}>
                      {journey.name}
                    </span>
                    <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                      {scenarioCount} scenario{scenarioCount === 1 ? '' : 's'} included
                    </span>
                  </div>
                ))}
                <Pagination
                  page={journeysPage}
                  totalPages={journeysTotalPages}
                  onPrev={() => setJourneysPage((p) => p - 1)}
                  onNext={() => setJourneysPage((p) => p + 1)}
                />
              </div>

              <div
                style={{
                  background: 'var(--canvas-wash)',
                  borderRadius: 10,
                  padding: '14px 16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 9,
                }}
              >
                {[
                  `All ${scenarios.length} scenario${scenarios.length === 1 ? '' : 's'} have test data ready`,
                  `Target environment: ${envLabel}`,
                ].map((label) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      aria-hidden="true"
                      style={{
                        width: 16,
                        height: 16,
                        borderRadius: 'var(--radius-full)',
                        background: '#DCFCE7',
                        color: 'var(--good)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 10,
                        fontWeight: 700,
                        flexShrink: 0,
                      }}
                    >
                      ✓
                    </span>
                    <span style={{ fontSize: 12.5, color: 'var(--ink-secondary)' }}>{label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  )
}
