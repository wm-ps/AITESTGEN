import { useEffect, useRef, useState } from 'react'
import { api, type JourneyRead, type ScenarioRead } from '../api'
import { Stepper, type StepKey } from './Stepper'
import { GenerationLoader } from './GenerationLoader'

const POLL_INTERVAL_MS = 3000
const SCENARIOS_PER_PAGE = 6

const TYPE_BADGE: Record<string, { label: string; background: string; color: string }> = {
  happy: { label: 'Happy Path', background: 'var(--happy-wash)', color: 'var(--happy-strong)' },
  negative: { label: 'Negative Path', background: 'var(--danger-wash)', color: 'var(--danger-strong)' },
  edge: { label: 'Edge Case', background: 'var(--warn-wash)', color: 'var(--warn-strong)' },
}

const READINESS_FILTERS = ['All', 'Ready', 'Needs data'] as const
type ReadinessFilter = (typeof READINESS_FILTERS)[number]

function ReadinessPill({ ready }: { ready: boolean }) {
  return (
    <span
      className="status-pill"
      style={{
        background: ready ? 'var(--good-wash)' : 'var(--warn-wash)',
        color: ready ? 'var(--good-strong)' : 'var(--warn-strong)',
      }}
    >
      {ready ? 'Ready' : 'Test Data Required'}
    </span>
  )
}

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
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius)',
        padding: '4px 8px',
        fontSize: 14,
        flex: 1,
        marginRight: 'var(--space-3)',
      }}
    />
  )
}

function JourneyFilterDropdown({
  journeys,
  selected,
  onChange,
}: {
  journeys: JourneyRead[]
  selected: Set<string>
  onChange: (next: Set<string>) => void
}) {
  const [open, setOpen] = useState(false)
  const label = selected.size === 0 ? 'All journeys' : `${selected.size} journey${selected.size === 1 ? '' : 's'}`

  function toggle(id: string) {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange(next)
  }

  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="button-secondary"
        style={{ fontSize: 12, whiteSpace: 'nowrap' }}
      >
        {label} ▾
      </button>
      {open && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 9 }} onClick={() => setOpen(false)} />
          <div
            role="menu"
            aria-label="Filter by journey"
            className="card-panel"
            style={{
              position: 'absolute',
              right: 0,
              top: 34,
              minWidth: 220,
              maxHeight: 280,
              overflowY: 'auto',
              boxShadow: '0 12px 28px rgba(15,23,42,0.14)',
              zIndex: 10,
              padding: 'var(--space-2) 0',
            }}
          >
            {selected.size > 0 && (
              <button
                type="button"
                onClick={() => onChange(new Set())}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '8px 12px',
                  background: 'none',
                  border: 'none',
                  borderBottom: '1px solid var(--border-hairline)',
                  fontSize: 12.5,
                  fontWeight: 600,
                  color: 'var(--accent)',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >
                Clear filter
              </button>
            )}
            {journeys.map((journey) => (
              <label
                key={journey.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 12px',
                  fontSize: 12.5,
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  checked={selected.has(journey.id)}
                  onChange={() => toggle(journey.id)}
                />
                {journey.name}
              </label>
            ))}
            {journeys.length === 0 && (
              <div className="caption" style={{ padding: '8px 12px', fontSize: 12 }}>
                No journeys yet.
              </div>
            )}
          </div>
        </>
      )}
    </div>
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
          color: 'var(--ink-muted)',
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
  onContinueToGenerate,
  furthestCount,
  onStepClick,
  onPrevious,
  onNext,
}: {
  applicationId: string
  onContinueToGenerate: () => void
  furthestCount: number
  onStepClick?: (key: StepKey) => void
  onPrevious?: () => void
  onNext?: () => void
}) {
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([])
  const [journeys, setJourneys] = useState<JourneyRead[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [readinessFilter, setReadinessFilter] = useState<ReadinessFilter>('All')
  const [journeyFilter, setJourneyFilter] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  // Same distinction DiscoverJourneys draws for Journeys: "generation still
  // running" and "every Scenario was removed" both look like an empty list.
  const hadScenariosRef = useRef(false)
  if (scenarios.length > 0) hadScenariosRef.current = true

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
    }

    poll()
    if (isComplete) return
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId, isComplete])

  // Land on the first Scenario selected by default, not an empty canvas —
  // also re-picks the first one if the selected Scenario was deleted.
  useEffect(() => {
    if (selectedId && scenarios.some((s) => s.id === selectedId)) return
    setSelectedId(scenarios[0]?.id ?? null)
  }, [scenarios, selectedId])

  async function handleRename(id: string, name: string) {
    setRenamingId(null)
    const updated = await api.renameScenario(id, name)
    setScenarios((rows) => rows.map((s) => (s.id === id ? updated : s)))
  }

  async function handleDelete(id: string) {
    if (!window.confirm('Remove this Scenario?')) return
    await api.deleteScenario(id)
    setScenarios((rows) => rows.filter((s) => s.id !== id))
    setSelectedId((current) => (current === id ? null : current))
  }

  async function handleTestDataChange(scenarioId: string, name: string, value: string) {
    const updated = await api.updateScenarioTestData(scenarioId, name, value)
    setScenarios((rows) => rows.map((s) => (s.id === scenarioId ? updated : s)))
  }

  const selectedScenario = scenarios.find((s) => s.id === selectedId) ?? null
  // `[UPDATED]` No longer gated on test_data completeness — any blank field
  // (missed by the reviewer, or never filled in at all) gets a sensible
  // default at generation time (PlaywrightGenerationActivity, Story 4.2).
  // Enabled as soon as there's at least one Scenario to generate from.
  const canContinue = scenarios.length > 0
  const searchLower = search.trim().toLowerCase()
  const visibleScenarios = scenarios.filter((s) => {
    if (!(s.name ?? '').toLowerCase().includes(searchLower)) return false
    if (journeyFilter.size > 0 && !journeyFilter.has(s.journey_id)) return false
    if (readinessFilter === 'Ready') return s.test_data_complete
    if (readinessFilter === 'Needs data') return !s.test_data_complete
    return true
  })
  const needsDataCount = scenarios.filter((s) => !s.test_data_complete).length
  const headerSub =
    scenarios.length === 0
      ? ''
      : needsDataCount > 0
        ? `${needsDataCount} scenario${needsDataCount === 1 ? '' : 's'} require${needsDataCount === 1 ? 's' : ''} test data before the suite can be generated.`
        : 'All scenarios are Ready — you can generate the test suite.'
  const totalPages = Math.max(1, Math.ceil(visibleScenarios.length / SCENARIOS_PER_PAGE))
  const pageClamped = Math.min(page, totalPages - 1)
  const pagedScenarios = visibleScenarios.slice(
    pageClamped * SCENARIOS_PER_PAGE,
    pageClamped * SCENARIOS_PER_PAGE + SCENARIOS_PER_PAGE,
  )
  const showPagination = visibleScenarios.length > SCENARIOS_PER_PAGE

  return (
    <>
      <Stepper current="review" furthestCount={furthestCount} onStepClick={onStepClick} onPrevious={onPrevious} onNext={onNext} />
      <main
        style={{
          maxWidth: 'var(--content-max)',
          margin: '0 auto',
          padding: `var(--content-top) var(--content-x)`,
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
          <div>
            <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0, color: 'var(--ink)' }}>
              Review Scenarios
            </h1>
            {headerSub && (
              <div className="caption" style={{ fontSize: 13, marginTop: 3, maxWidth: 520 }}>
                {headerSub}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-5)', flexShrink: 0 }}>
              <div
                role="group"
                aria-label="Filter by readiness"
                style={{
                  display: 'inline-flex',
                  background: 'var(--canvas-wash-alt)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  padding: 3,
                  gap: 3,
                }}
              >
                {READINESS_FILTERS.map((filterOption) => (
                  <button
                    key={filterOption}
                    type="button"
                    aria-pressed={readinessFilter === filterOption}
                    onClick={() => {
                      setReadinessFilter(filterOption)
                      setPage(0)
                    }}
                    style={{
                      padding: '6px 11px',
                      border: 'none',
                      borderRadius: 'var(--radius-xs)',
                      fontSize: 12,
                      fontWeight: 600,
                      fontFamily: 'inherit',
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      background: readinessFilter === filterOption ? 'var(--canvas)' : 'transparent',
                      color: readinessFilter === filterOption ? 'var(--ink)' : 'var(--ink-muted)',
                    }}
                  >
                    {filterOption}
                  </button>
                ))}
              </div>
              <JourneyFilterDropdown
                journeys={journeys}
                selected={journeyFilter}
                onChange={(next) => {
                  setJourneyFilter(next)
                  setPage(0)
                }}
              />
              <input
                type="text"
                placeholder="Search scenarios"
                aria-label="Search scenarios"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(0)
                }}
                style={{
                  width: 200,
                  boxSizing: 'border-box',
                  padding: '8px 12px',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  fontSize: 13,
                  fontFamily: 'inherit',
                  color: 'var(--ink)',
                }}
              />
              <button
                type="button"
                onClick={onContinueToGenerate}
                disabled={!canContinue}
                style={{
                  padding: '10px 20px',
                  whiteSpace: 'nowrap',
                  background: canContinue ? 'var(--accent)' : 'var(--border)',
                  color: canContinue ? 'var(--accent-ink)' : 'var(--ink-faint)',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  fontSize: 14,
                  fontWeight: 600,
                  fontFamily: 'inherit',
                  cursor: canContinue ? 'pointer' : 'not-allowed',
                  boxShadow: canContinue ? 'var(--shadow-button-primary)' : 'none',
                }}
              >
                Generate Test Suite →
              </button>
          </div>
        </div>

        {scenarios.length === 0 && hadScenariosRef.current ? (
          <p style={{ textAlign: 'center', padding: '80px 24px', color: 'var(--ink-muted)', fontSize: 14 }}>
            No scenarios remain — add journeys back to generate scenarios.
          </p>
        ) : !isComplete ? (
          // Gated on `isComplete` (every Journey covered), not `scenarios.length
          // > 0` — otherwise this flips to the interactive list the instant the
          // first Scenario lands, showing a partial set while generation is
          // still running in the background. TestSuiteResults gates its results
          // screen the same way, so both "something is generating" flows read
          // consistently: stay on the loader until the whole batch is done.
          <div
            className="card-panel"
            style={{
              padding: 'var(--space-10) var(--space-5)',
              marginTop: 'var(--space-5)',
            }}
          >
            <GenerationLoader
              title="Generating scenarios"
              caption={
                <p className="caption" style={{ margin: 0, fontSize: 12.5 }}>
                  {journeysCovered}/{journeys.length || '…'} journeys covered
                </p>
              }
              footer={
                <p className="caption" style={{ margin: '6px 0 0', fontSize: 12, opacity: 0.7 }}>
                  Generation runs in the background — this list updates automatically.
                </p>
              }
            />
          </div>
        ) : (
          <div className="card-panel" style={{ display: 'flex', overflow: 'hidden' }}>
            <div
              style={{
                width: 280,
                flexShrink: 0,
                display: 'flex',
                flexDirection: 'column',
                background: 'var(--canvas-wash-alt)',
                borderRight: '1px solid var(--border)',
              }}
            >
              <ul
                style={{
                  listStyle: 'none',
                  margin: 0,
                  padding: 'var(--space-6) var(--space-5) var(--space-3)',
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-2)',
                }}
              >
                {pagedScenarios.map((scenario) => {
                  const badge = TYPE_BADGE[scenario.type] ?? TYPE_BADGE.happy
                  return (
                    <li
                      key={scenario.id}
                      className={`list-row card-clickable${selectedId === scenario.id ? ' list-row-selected' : ''}`}
                      onClick={() => setSelectedId(scenario.id)}
                      style={{
                        padding: 'var(--space-3) var(--space-4)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        cursor: 'pointer',
                      }}
                    >
                      {renamingId === scenario.id ? (
                        <ScenarioRenameInput
                          initialName={scenario.name}
                          onSave={(name) => handleRename(scenario.id, name)}
                          onCancel={() => setRenamingId(null)}
                        />
                      ) : (
                        <div style={{ minWidth: 0 }}>
                          <div
                            style={{
                              fontSize: 13.5,
                              fontWeight: 600,
                              color: selectedId === scenario.id ? 'var(--accent)' : 'var(--ink)',
                            }}
                          >
                            {scenario.name}
                          </div>
                          <div className="caption" style={{ fontSize: 12, marginBottom: 4 }}>
                            from {scenario.journey_name}
                          </div>
                          <span className="badge" style={{ background: badge.background, color: badge.color }}>
                            {badge.label}
                          </span>{' '}
                          <ReadinessPill ready={scenario.test_data_complete} />
                        </div>
                      )}
                      <ScenarioRowMenu
                        onRename={() => setRenamingId(scenario.id)}
                        onDelete={() => handleDelete(scenario.id)}
                      />
                    </li>
                  )
                })}
                {pagedScenarios.length === 0 && (
                  <p className="caption" style={{ textAlign: 'center', padding: '40px 14px', fontSize: 12.5 }}>
                    No matches.
                  </p>
                )}
              </ul>
              {showPagination && (
                <div
                  style={{
                    flexShrink: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 'var(--space-3)',
                    padding: 'var(--space-4) var(--space-5) var(--space-6)',
                    borderTop: '1px solid var(--border-hairline)',
                  }}
                >
                  <button
                    type="button"
                    className="button-secondary"
                    disabled={pageClamped <= 0}
                    onClick={() => setPage(pageClamped - 1)}
                  >
                    Prev
                  </button>
                  <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                    Page {pageClamped + 1} of {totalPages}
                  </span>
                  <button
                    type="button"
                    className="button-secondary"
                    disabled={pageClamped >= totalPages - 1}
                    onClick={() => setPage(pageClamped + 1)}
                  >
                    Next
                  </button>
                </div>
              )}
            </div>

            <div
              style={{
                flex: 1,
                minWidth: 0,
                padding: 'var(--space-9) var(--content-x)',
              }}
            >
              {selectedScenario ? (
                <div style={{ maxWidth: 680 }}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--space-3)',
                      marginBottom: 'var(--space-1)',
                    }}
                  >
                    <div style={{ fontSize: 16, fontWeight: 700 }}>{selectedScenario.name}</div>
                    {(() => {
                      const badge = TYPE_BADGE[selectedScenario.type] ?? TYPE_BADGE.happy
                      return (
                        <span className="badge" style={{ background: badge.background, color: badge.color }}>
                          {badge.label}
                        </span>
                      )
                    })()}
                    <ReadinessPill ready={selectedScenario.test_data_complete} />
                  </div>
                  <div className="caption" style={{ fontSize: 12, marginBottom: 'var(--space-4)' }}>
                    from {selectedScenario.journey_name}
                  </div>

                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 'var(--space-2)' }}>
                    Test steps
                  </div>
                  <ol style={{ margin: '0 0 var(--space-4)', paddingLeft: 20 }}>
                    {selectedScenario.steps.map((step, index) => (
                      <li key={index} style={{ fontSize: 13, marginBottom: 6 }}>
                        {step}
                      </li>
                    ))}
                  </ol>

                  <div
                    style={{
                      background: 'var(--accent-wash-soft)',
                      border: '1px solid var(--accent-wash)',
                      borderRadius: 'var(--radius-lg)',
                      padding: 'var(--space-4)',
                      marginBottom: 'var(--space-4)',
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 'var(--space-3)' }}>
                      Test data
                    </div>
                    {!selectedScenario.test_data_complete && (
                      <p
                        role="alert"
                        style={{
                          background: 'var(--warn-wash)',
                          border: '1px solid var(--warn-wash-border)',
                          color: '#92400E',
                          borderRadius: 'var(--radius)',
                          padding: 'var(--space-3)',
                          fontSize: 12.5,
                          margin: '0 0 var(--space-3)',
                        }}
                      >
                        Test data required — fill in the highlighted fields below to mark this
                        scenario Ready.
                      </p>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                      {selectedScenario.test_data.map((field) => {
                        const missing = field.mandatory && !field.value
                        return (
                          <label key={field.name} className="field">
                            <span style={{ fontSize: 12 }}>
                              {field.name}
                              {field.mandatory && (
                                <span style={{ color: 'var(--danger)' }} aria-label="required">
                                  {' '}
                                  *
                                </span>
                              )}
                            </span>
                            <input
                              defaultValue={field.value ?? ''}
                              onBlur={(e) =>
                                handleTestDataChange(selectedScenario.id, field.name, e.target.value)
                              }
                            />
                            {missing && (
                              <span style={{ fontSize: 11, color: 'var(--warn-strong)' }}>
                                Required to generate this test
                              </span>
                            )}
                          </label>
                        )
                      })}
                    </div>
                  </div>

                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 'var(--space-2)' }}>
                    Expected result
                  </div>
                  <div
                    style={{
                      borderLeft: '3px solid var(--good)',
                      color: 'var(--ink-secondary)',
                      padding: 'var(--space-3)',
                      fontSize: 13,
                    }}
                  >
                    {selectedScenario.expected_result}
                  </div>
                </div>
              ) : (
                <p className="caption" style={{ margin: 0 }}>
                  Select a Scenario to see its Test steps, Test data, and Expected result.
                </p>
              )}
            </div>
          </div>
        )}
      </main>
    </>
  )
}
