import { useEffect, useState } from 'react'
import { api, type JourneyRead, type ScenarioRead } from '../api'
import { Stepper } from './Stepper'

// Story 4.2 AC 2: no suite-name field — each TestSuite is auto-named from
// its own Journey (Task 1), there is nothing for the user to type here.
export function GenerateSuite({
  applicationId,
  onGenerated,
}: {
  applicationId: string
  onGenerated: () => void
}) {
  const [journeys, setJourneys] = useState<JourneyRead[]>([])
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([])
  const [generating, setGenerating] = useState(false)
  const [execution, setExecution] = useState<'run' | 'schedule' | 'save'>('run')

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
  const journeyIdsWithScenarios = new Set(scenarios.map((s) => s.journey_id))
  const suiteCount = journeys.filter((j) => journeyIdsWithScenarios.has(j.id)).length

  async function handleGenerate() {
    setGenerating(true)
    try {
      await api.generateSuite(applicationId)
      onGenerated()
    } finally {
      setGenerating(false)
    }
  }

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
        <h1 style={{ fontSize: 19, fontWeight: 650, margin: '0 0 8px' }}>Generate Suite</h1>
        <p className="caption" style={{ margin: '0 0 20px' }}>
          Each discovered Journey becomes its own named Test Suite, generated from its reviewed
          Scenarios.
        </p>

        <div className="card-panel" style={{ padding: 'var(--space-5)', marginBottom: 'var(--space-4)' }}>
          <div
            style={{
              display: 'flex',
              gap: 'var(--space-5)',
              marginBottom: 'var(--space-5)',
            }}
          >
            <div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{suiteCount}</div>
              <div className="caption" style={{ fontSize: 12 }}>
                Test Suite{suiteCount === 1 ? '' : 's'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{scenarios.length}</div>
              <div className="caption" style={{ fontSize: 12 }}>
                Test Case{scenarios.length === 1 ? '' : 's'}
              </div>
            </div>
          </div>

          <div style={{ marginBottom: 'var(--space-5)' }}>
            <label className="field">
              <span style={{ fontSize: 13, fontWeight: 600 }}>Target environment</span>
              <select defaultValue="test" aria-label="Target environment">
                <option value="test">Test</option>
                <option value="staging">Staging</option>
                <option value="production">Production</option>
              </select>
            </label>
          </div>

          <fieldset
            style={{ border: 'none', padding: 0, margin: '0 0 var(--space-5)' }}
            aria-label="Execution"
          >
            <legend style={{ fontSize: 13, fontWeight: 600, marginBottom: 'var(--space-2)' }}>
              Execution
            </legend>
            {(
              [
                ['run', 'Run immediately'],
                ['schedule', 'Schedule for later'],
                ['save', 'Save without running'],
              ] as const
            ).map(([value, label]) => (
              <label
                key={value}
                style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 6 }}
              >
                <input
                  type="radio"
                  name="execution"
                  value={value}
                  checked={execution === value}
                  onChange={() => setExecution(value)}
                />
                {label}
              </label>
            ))}
          </fieldset>

          <button
            type="button"
            onClick={handleGenerate}
            disabled={suiteCount === 0 || generating}
            style={{
              padding: '10px 20px',
              whiteSpace: 'nowrap',
              background: suiteCount > 0 && !generating ? 'var(--signal)' : 'var(--border)',
              color: suiteCount > 0 && !generating ? 'var(--signal-ink)' : 'var(--ink-faint)',
              border: 'none',
              borderRadius: 'var(--radius)',
              fontSize: 14,
              fontWeight: 600,
              fontFamily: 'inherit',
              cursor: suiteCount > 0 && !generating ? 'pointer' : 'not-allowed',
            }}
          >
            {generating ? 'Generating…' : 'Generate Test Suite'}
          </button>
        </div>
      </main>
    </>
  )
}
