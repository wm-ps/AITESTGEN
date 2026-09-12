import { useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faBrain, faChevronDown, faChevronRight, faRoute, faWandMagicSparkles } from '@fortawesome/free-solid-svg-icons'
import { api, formatTestCaseNumber, type JourneyRead, type ScenarioRead } from '../api'
import { AppIdentityLine } from './AppIdentityLine'
import { GenerationLoader } from './GenerationLoader'
import { ServiceErrorNote } from './ServiceError'
import { EmptyState, ScenariosIllustration } from './EmptyState'
import { faIcon } from '../faIcon'

const Route = faIcon(faRoute)
const WandSparkles = faIcon(faWandMagicSparkles)
const Brain = faIcon(faBrain)

// Matches the prototype's disclosure pattern exactly — a closed group/scenario
// shows fa-chevron-right, an open one shows fa-chevron-down (two different
// glyphs, not one rotated).
function ChevronIcon({ open, small }: { open: boolean; small?: boolean }) {
  return (
    <FontAwesomeIcon
      icon={open ? faChevronDown : faChevronRight}
      style={{ fontSize: small ? 10 : 11, color: 'var(--fg-4)', flex: 'none' }}
    />
  )
}

const POLL_INTERVAL_MS = 3000

function ScenarioRenameInput({
  initialName,
  onSave,
  onCancel,
}: {
  initialName: string
  onSave: (name: string) => void
  onCancel: () => void
}) {
  const [value, setValue] = useState(initialName)
  const cancelledRef = useRef(false)

  return (
    <input
      autoFocus
      value={value}
      aria-label="Scenario name"
      onChange={(e) => setValue(e.target.value)}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur()
        if (e.key === 'Escape') {
          cancelledRef.current = true
          onCancel()
        }
      }}
      onBlur={() => {
        if (cancelledRef.current) return
        const trimmed = value.trim()
        if (trimmed) onSave(trimmed)
        else onCancel()
      }}
      style={{
        border: '1px solid var(--border-3)',
        borderRadius: 'var(--radius)',
        padding: '4px 8px',
        fontSize: 14,
        flex: 1,
        marginRight: 'var(--space-3)',
      }}
    />
  )
}

function ScenarioRowMenu({ onRename, onDelete }: { onRename: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false)

  return (
    <div style={{ position: 'relative' }} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Scenario actions"
        onClick={() => setOpen((o) => !o)}
        style={{
          width: 26,
          height: 26,
          borderRadius: 'var(--radius)',
          background: 'transparent',
          border: 'none',
          color: 'var(--fg-4)',
          cursor: 'pointer',
          fontSize: 16,
          lineHeight: 1,
        }}
      >
        ⋯
      </button>
      {open && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 9 }} onClick={() => setOpen(false)} />
          <div
            role="menu"
            className="card-panel"
            style={{
              position: 'absolute',
              right: 0,
              top: 30,
              minWidth: 140,
              boxShadow: '0 12px 28px rgba(15,23,42,0.14)',
              overflow: 'hidden',
              zIndex: 10,
            }}
          >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onRename()
            }}
            style={{
              display: 'block',
              width: '100%',
              textAlign: 'left',
              padding: '9px 12px',
              background: 'none',
              border: 'none',
              fontSize: 13,
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            Rename
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onDelete()
            }}
            className="menu-item-danger"
            style={{
              display: 'block',
              width: '100%',
              textAlign: 'left',
              padding: '9px 12px',
              background: 'none',
              border: 'none',
              fontSize: 13,
              color: 'var(--danger)',
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            Delete
          </button>
          </div>
        </>
      )}
    </div>
  )
}

export function ReviewScenarios({
  applicationId,
  applicationName,
  applicationUrl,
  onContinueToGenerate,
  onGoToJourneys,
}: {
  applicationId: string
  applicationName: string
  applicationUrl: string
  onContinueToGenerate: () => void
  onGoToJourneys: () => void
}) {
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([])
  const [journeys, setJourneys] = useState<JourneyRead[]>([])
  // Vantage V2: accordion by journey, then by scenario — journey groups open
  // by default, scenario detail (steps + test data) closed by default,
  // matching the prototype's own open/closed defaults. No more pagination;
  // an accordion's own collapse already manages density.
  const [closedGroupIds, setClosedGroupIds] = useState<Set<string>>(new Set())
  const [openScenarioIds, setOpenScenarioIds] = useState<Set<string>>(new Set())
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [autofillingId, setAutofillingId] = useState<string | null>(null)
  const [autofillError, setAutofillError] = useState<string | null>(null)
  // Same distinction DiscoverJourneys draws for Journeys: "generation still
  // running" and "every Scenario was removed" both look like an empty list.
  const hadScenariosRef = useRef(false)
  if (scenarios.length > 0) hadScenariosRef.current = true
  const [generationUnavailable, setGenerationUnavailable] = useState(false)

  // GenerationWorkflow runs one per Journey but each writes a variable
  // number of Scenarios (happy/negative/edge) — so a raw scenario count
  // can't signal "done" the way TestSuiteResults' test-case count does.
  // Distinct Journeys covered vs total candidate Journeys is the signal
  // that's actually stable: every Journey gets exactly one generation run.
  useEffect(() => {
    let cancelled = false
    api.listJourneys(applicationId).then((rows) => {
      if (!cancelled) setJourneys(rows)
    })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  const journeysCovered = new Set(scenarios.map((s) => s.journey_id)).size
  const isComplete = journeys.length > 0 && journeysCovered >= journeys.length

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const rows = await api.listScenarios(applicationId)
        if (!cancelled) setScenarios(rows)
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
      // Scenario generation and Suite generation share one worker/task queue
      // (GENERATION_TASK_QUEUE) — this is the same dead-worker check
      // TestSuiteResults uses, catching a worker that crashes mid-run rather
      // than being down at submit time (already guarded separately).
      try {
        const { available } = await api.getGenerationStatus(applicationId)
        if (!cancelled) setGenerationUnavailable(!available)
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

  async function handleRename(id: string, name: string) {
    setRenamingId(null)
    const updated = await api.renameScenario(id, name)
    setScenarios((rows) => rows.map((s) => (s.id === id ? updated : s)))
  }

  async function handleDelete(id: string) {
    if (!window.confirm('Delete this scenario?')) return
    await api.deleteScenario(id)
    setScenarios((rows) => rows.filter((s) => s.id !== id))
  }

  async function handleTestDataChange(scenarioId: string, name: string, value: string) {
    const updated = await api.updateScenarioTestData(scenarioId, name, value)
    setScenarios((rows) => rows.map((s) => (s.id === scenarioId ? updated : s)))
  }

  // "Clear" — resets every field on this Scenario to blank, reusing the same
  // per-field endpoint the manual edit fields already call (no new backend
  // needed for this half of the feature).
  async function handleClearTestData(scenario: ScenarioRead) {
    for (const field of scenario.test_data) {
      await handleTestDataChange(scenario.id, field.name, '')
    }
  }

  // "Auto-generate" — the same deterministic, non-AI default fill Suite
  // Generation already applies to any still-blank field, triggerable early.
  async function handleAutofillTestData(scenarioId: string) {
    if (autofillingId) return
    setAutofillingId(scenarioId)
    setAutofillError(null)
    try {
      await api.autofillScenarioTestData(scenarioId)
      let result = await api.getAutofillScenarioTestDataStatus(scenarioId)
      while (result.status === 'running') {
        await new Promise((resolve) => setTimeout(resolve, 500))
        result = await api.getAutofillScenarioTestDataStatus(scenarioId)
      }
      if (result.status === 'complete' && result.scenario) {
        setScenarios((rows) => rows.map((s) => (s.id === scenarioId ? result.scenario! : s)))
      } else {
        setAutofillError(result.error_message ?? 'Could not auto-fill test data — try again.')
      }
    } catch {
      setAutofillError('Could not auto-fill test data — try again.')
    } finally {
      setAutofillingId(null)
    }
  }

  // `[UPDATED]` No longer gated on test_data completeness — any blank field
  // (missed by the reviewer, or never filled in at all) gets a sensible
  // default at generation time (PlaywrightGenerationActivity, Story 4.2).
  // Enabled as soon as there's at least one Scenario to generate from.
  const canContinue = scenarios.length > 0
  // Matches the prototype's scenarioSubhead: "{N} scenarios across {M}
  // journeys · each with its own test steps and test data".
  const headerSub =
    scenarios.length === 0
      ? ''
      : `${scenarios.length} scenario${scenarios.length === 1 ? '' : 's'} across ${journeys.length} journey${journeys.length === 1 ? '' : 's'} · each with its own test steps and test data`

  // Group by journey, in the same order Journeys were discovered — a
  // journey_id with no match in `journeys` (its Journey was deleted) still
  // gets its own group, keyed by that scenario's own journey_name.
  const groupedScenarios: { journeyId: string; journeyName: string; scenarios: ScenarioRead[] }[] = []
  for (const journey of journeys) {
    const inGroup = scenarios.filter((s) => s.journey_id === journey.id)
    if (inGroup.length > 0) groupedScenarios.push({ journeyId: journey.id, journeyName: journey.name, scenarios: inGroup })
  }
  for (const scenario of scenarios) {
    if (!journeys.some((j) => j.id === scenario.journey_id) && !groupedScenarios.some((g) => g.journeyId === scenario.journey_id)) {
      groupedScenarios.push({
        journeyId: scenario.journey_id,
        journeyName: scenario.journey_name,
        scenarios: scenarios.filter((s) => s.journey_id === scenario.journey_id),
      })
    }
  }

  return (
    <>
      <main style={{ width: '100%', boxSizing: 'border-box', flex: 1, display: 'flex', flexDirection: 'column' }}>
      <div
        style={{
          flex: 1,
          width: '100%',
          minWidth: 0,
          maxWidth: 1560,
          margin: '0 auto',
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'space-between',
            gap: 'var(--space-8)',
            marginBottom: 'var(--space-7)',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <h2 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Scenarios</h2>
            <AppIdentityLine name={applicationName} url={applicationUrl} />
            {headerSub && (
              <div className="caption" style={{ fontSize: 13, marginTop: 3, maxWidth: 520 }}>
                {headerSub}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-5)', flexShrink: 0 }}>
              <button
                type="button"
                onClick={onContinueToGenerate}
                disabled={!canContinue}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '10px 20px',
                  whiteSpace: 'nowrap',
                  background: canContinue ? 'var(--accent)' : 'var(--border-2)',
                  color: canContinue ? 'var(--accent-ink)' : 'var(--fg-5)',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  fontSize: 14,
                  fontWeight: 600,
                  fontFamily: 'inherit',
                  cursor: canContinue ? 'pointer' : 'not-allowed',
                  boxShadow: canContinue ? 'var(--shadow-button-primary)' : 'none',
                }}
              >
                <WandSparkles size={14} />
                Generate test cases
              </button>
          </div>
        </div>

        {scenarios.length === 0 && isComplete ? (
          <EmptyState
            illustration={<ScenariosIllustration />}
            title={hadScenariosRef.current ? 'No scenarios remain' : 'No scenarios yet'}
            subtitle={
              hadScenariosRef.current
                ? 'Add journeys back to generate new scenarios.'
                : 'Scenarios appear here once discovered journeys are turned into drafted test scenarios.'
            }
          />
        ) : !isComplete && generationUnavailable ? (
          <div
            style={{
              background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
              backdropFilter: 'blur(16px) saturate(1.25)',
              border: '1px solid var(--border-1)',
              borderRadius: 14,
              boxShadow: 'var(--panel-shadow)',
              padding: 'var(--space-10) var(--space-5)',
              marginTop: 'var(--space-5)',
              textAlign: 'center',
            }}
          >
            <ServiceErrorNote code="GENERATION_UNAVAILABLE" />
            <p className="caption" style={{ margin: '10px 0 0', fontSize: 12 }}>
              <button
                type="button"
                onClick={onGoToJourneys}
                style={{ font: 'inherit', color: 'var(--accent)', background: 'none', border: 0, padding: 0, cursor: 'pointer' }}
              >
                Go back and retry
              </button>
            </p>
          </div>
        ) : !isComplete ? (
          // Gated on `isComplete` (every Journey covered), not `scenarios.length
          // > 0` — otherwise this flips to the interactive list the instant the
          // first Scenario lands, showing a partial set while generation is
          // still running in the background. TestSuiteResults gates its results
          // screen the same way, so both "something is generating" flows read
          // consistently: stay on the loader until the whole batch is done.
          <div
            style={{
              background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
              backdropFilter: 'blur(16px) saturate(1.25)',
              border: '1px solid var(--border-1)',
              borderRadius: 14,
              boxShadow: 'var(--panel-shadow)',
              marginTop: 'var(--space-5)',
            }}
          >
            <GenerationLoader
              icon={Brain}
              title="Modelling scenarios…"
              body="Each settled journey is broken into scenarios with their own steps and test data. They appear here as discovery completes."
              bullets={['Reading journeys', 'Drafting scenarios', 'Deriving test data']}
              percent={journeys.length > 0 ? (journeysCovered / journeys.length) * 100 : undefined}
              caption={
                <p className="caption" style={{ margin: '2px 0 0', fontSize: 12.5 }}>
                  {journeysCovered}/{journeys.length || '…'} journeys covered
                </p>
              }
              footer={
                <p className="caption" style={{ margin: '10px 0 0', fontSize: 12, opacity: 0.7 }}>
                  Generation runs in the background — this list updates automatically.
                </p>
              }
            />
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {groupedScenarios.map((group) => {
              const groupOpen = !closedGroupIds.has(group.journeyId)
              return (
                <div
                  key={group.journeyId}
                  style={{
                    background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
                    backdropFilter: 'blur(16px) saturate(1.25)',
                    border: '1px solid var(--border-1)',
                    borderRadius: 14,
                    overflow: 'hidden',
                    boxShadow: 'var(--panel-shadow)',
                  }}
                >
                  <div
                    onClick={() =>
                      setClosedGroupIds((prev) => {
                        const next = new Set(prev)
                        if (next.has(group.journeyId)) next.delete(group.journeyId)
                        else next.add(group.journeyId)
                        return next
                      })
                    }
                    style={{ display: 'flex', alignItems: 'center', gap: 13, padding: '15px 18px', cursor: 'pointer', background: 'var(--panel)' }}
                  >
                    <ChevronIcon open={groupOpen} />
                    <div
                      style={{
                        width: 30,
                        height: 30,
                        flex: 'none',
                        borderRadius: 9,
                        background: 'var(--chip)',
                        border: '1px solid var(--border-2)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: 'var(--accent-2)',
                      }}
                    >
                      <Route size={14} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.01em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {group.journeyName}
                      </div>
                      <div style={{ fontSize: 11.5, color: 'var(--fg-4)', marginTop: 3 }}>
                        {group.scenarios.length} scenario{group.scenarios.length === 1 ? '' : 's'}
                      </div>
                    </div>
                  </div>

                  {groupOpen && (
                    <div style={{ borderTop: '1px solid var(--border-2)' }}>
                      {group.scenarios.map((scenario, index) => {
                        const isOpen = openScenarioIds.has(scenario.id)
                        return (
                          <div key={scenario.id} style={index ? { borderTop: '1px solid var(--row-line)' } : undefined}>
                            <div
                              onClick={() =>
                                setOpenScenarioIds((prev) => {
                                  const next = new Set(prev)
                                  if (next.has(scenario.id)) next.delete(scenario.id)
                                  else next.add(scenario.id)
                                  return next
                                })
                              }
                              style={{ display: 'flex', alignItems: 'flex-start', gap: 13, padding: '15px 18px 15px 20px', cursor: 'pointer' }}
                            >
                              <span style={{ marginTop: 5 }}>
                                <ChevronIcon open={isOpen} small />
                              </span>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                {renamingId === scenario.id ? (
                                  <div onClick={(e) => e.stopPropagation()}>
                                    <ScenarioRenameInput
                                      initialName={scenario.name}
                                      onSave={(name) => handleRename(scenario.id, name)}
                                      onCancel={() => setRenamingId(null)}
                                    />
                                  </div>
                                ) : (
                                  <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg-1)' }}>
                                    <span className="caption" style={{ fontWeight: 700, marginRight: 6 }}>
                                      {formatTestCaseNumber(scenario.test_case_number)}
                                    </span>
                                    {scenario.name}
                                  </div>
                                )}
                              </div>
                              <div style={{ flex: 'none', display: 'flex', alignItems: 'center', gap: 14 }}>
                                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--fg-4)', whiteSpace: 'nowrap' }}>
                                  {scenario.steps.length} steps
                                </span>
                                <div onClick={(e) => e.stopPropagation()}>
                                  <ScenarioRowMenu onRename={() => setRenamingId(scenario.id)} onDelete={() => handleDelete(scenario.id)} />
                                </div>
                              </div>
                            </div>

                            {isOpen && (
                              <div style={{ padding: '2px 18px 18px 43px', display: 'flex', flexDirection: 'column', gap: 13 }}>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: 13 }}>
                                  <div style={{ border: '1px solid var(--border-2)', borderRadius: 10, background: 'var(--panel-2)', padding: 14 }}>
                                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 10 }}>Test steps</div>
                                    <ol style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 6 }}>
                                      {scenario.steps.map((step, stepIndex) => (
                                        <li key={stepIndex} style={{ fontSize: 12.5, color: 'var(--fg-1)' }}>
                                          {step}
                                        </li>
                                      ))}
                                    </ol>
                                  </div>

                                  {scenario.test_data.length > 0 && (
                                  <div style={{ border: '1px solid var(--border-2)', borderRadius: 10, background: 'var(--panel-2)', padding: 14, minWidth: 0 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 13, flexWrap: 'wrap' }}>
                                      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', flex: 1 }}>Test data</span>
                                    </div>
                                    <>
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 13 }}>
                                          {scenario.test_data.map((field) => {
                                            const missing = field.mandatory && !field.value
                                            return (
                                              <div key={field.name} style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
                                                <label style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)' }}>
                                                  {field.name}
                                                  {field.mandatory && <span style={{ color: 'var(--bad)' }}> *</span>}
                                                </label>
                                                <input
                                                  defaultValue={field.value ?? ''}
                                                  placeholder={`Enter ${field.name}`}
                                                  onBlur={(e) => handleTestDataChange(scenario.id, field.name, e.target.value)}
                                                  style={{ height: 34, padding: '0 10px', border: `1px solid ${missing ? 'var(--warn-2)' : 'var(--border-2)'}`, borderRadius: 8, fontSize: 12.5, color: 'var(--fg-1)', background: 'var(--panel)', outline: 'none' }}
                                                />
                                                <div style={{ fontSize: 10.5, color: 'var(--fg-4)' }}>
                                                  {field.mandatory ? 'Required for this scenario' : 'Optional — auto-filled if left blank'}
                                                </div>
                                                {missing && <div style={{ fontSize: 10.5, color: 'var(--warn-2)' }}>Required to generate this test</div>}
                                              </div>
                                            )
                                          })}
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
                                          <button
                                            type="button"
                                            disabled={autofillingId === scenario.id}
                                            onClick={() => handleAutofillTestData(scenario.id)}
                                            style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 30, padding: '0 12px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', fontSize: 12, fontWeight: 500, color: 'var(--fg-2)', cursor: autofillingId === scenario.id ? 'default' : 'pointer' }}
                                          >
                                            {autofillingId === scenario.id ? 'Generating…' : 'Auto-generate'}
                                          </button>
                                          <button
                                            type="button"
                                            onClick={() => handleClearTestData(scenario)}
                                            style={{ display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 12px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', fontSize: 12, fontWeight: 500, color: 'var(--fg-3)', cursor: 'pointer' }}
                                          >
                                            Clear
                                          </button>
                                          <span style={{ flex: 1 }} />
                                          <span style={{ fontSize: 11, color: 'var(--fg-4)' }}>Blank fields are generated from the discovered form constraints</span>
                                        </div>
                                        {autofillError && autofillingId === null && (
                                          <div style={{ fontSize: 11.5, color: 'var(--bad)', marginTop: 8 }}>{autofillError}</div>
                                        )}
                                      </>
                                  </div>
                                  )}
                                </div>

                                <div>
                                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 6 }}>Expected result</div>
                                  <div style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>{scenario.expected_result}</div>
                                </div>
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
      </main>
    </>
  )
}
