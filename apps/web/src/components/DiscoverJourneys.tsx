import { useEffect, useRef, useState } from 'react'
import { api, type JourneyRead, type JourneyStepRead } from '../api'
import { useDiscoveryProgress } from '../hooks/useDiscoveryProgress'
import { ServiceErrorNote } from './ServiceError'
import { ImportProgress } from './ImportProgress'
import { Stepper, type StepKey } from './Stepper'
import { StatusPill } from './StatusPill'

const POLL_INTERVAL_MS = 3000
const JOURNEYS_PER_PAGE = 5

// Collapses consecutive steps sharing a stage (e.g. a page visit + its form
// submit both labeled "Checkout") into one flow node — the reviewer wants
// the business flow (Login → Cart → Checkout), not one row per captured step.
function stageFlow(steps: JourneyStepRead[]): string[] {
  const stages: string[] = []
  for (const step of steps) {
    if (stages[stages.length - 1] !== step.stage_label) stages.push(step.stage_label)
  }
  return stages
}

function JourneyRenameInput({
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
      aria-label="Journey name"
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

function JourneyRowMenu({ onRename, onDelete }: { onRename: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false)

  return (
    <div style={{ position: 'relative' }} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Journey actions"
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

export function DiscoverJourneys({
  applicationId,
  applicationName,
  discoveryStatus,
  discoveryStage,
  discoveryFailureReason,
  onContinueToScenarios,
  furthestCount,
  onStepClick,
  onPrevious,
  onNext,
}: {
  applicationId: string
  applicationName: string
  discoveryStatus: string
  discoveryStage: string | null
  discoveryFailureReason: string | null
  onContinueToScenarios: () => void
  furthestCount: number
  onStepClick?: (key: StepKey) => void
  onPrevious?: () => void
  onNext?: () => void
}) {
  const [journeys, setJourneys] = useState<JourneyRead[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [steps, setSteps] = useState<JourneyStepRead[]>([])
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [continuing, setContinuing] = useState(false)
  const [continueError, setContinueError] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)
  // Story 2.17: pause/resume already round-trips through the API — this
  // just reflects the response immediately rather than waiting for
  // useDiscoveryProgress's next poll tick (which stops polling entirely
  // once Journeys exist, so it may never pick the change up on its own).
  const [statusOverride, setStatusOverride] = useState<string | null>(null)
  const [pauseResumeBusy, setPauseResumeBusy] = useState(false)
  const [pauseResumeError, setPauseResumeError] = useState<string | null>(null)
  // Distinguishes "discovery hasn't produced any Journeys yet" (show
  // Discovery Progress) from "every Journey was deleted" (show the bare
  // "All journeys have been removed." empty state, EXPERIENCE.md State
  // Patterns) — both look identical as `journeys.length === 0`, so this
  // remembers whether the list was ever non-empty in this session.
  const hadJourneysRef = useRef(false)
  if (journeys.length > 0) hadJourneysRef.current = true

  const {
    status: liveStatus,
    stage: liveStage,
    failureReason: liveFailureReason,
    workerAvailable,
    retryCount,
  } = useDiscoveryProgress(
    applicationId,
    discoveryStatus,
    discoveryStage,
    discoveryFailureReason,
    journeys.length > 0,
  )

  useEffect(() => setStatusOverride(null), [liveStatus])
  const status = statusOverride ?? liveStatus

  const sessionExpired = status === 'failed' && liveFailureReason === 'session_expired'
  const discoveryWorkerDown =
    (status === 'failed' && liveFailureReason === 'worker_unavailable') ||
    (status === 'running' && !workerAvailable)

  async function handlePause() {
    setPauseResumeError(null)
    setPauseResumeBusy(true)
    try {
      const application = await api.pauseDiscovery(applicationId)
      setStatusOverride(application.discovery_status)
    } catch {
      setPauseResumeError('Could not pause discovery. Try again.')
    } finally {
      setPauseResumeBusy(false)
    }
  }

  async function handleResume() {
    setPauseResumeError(null)
    setPauseResumeBusy(true)
    try {
      const application = await api.resumeDiscovery(applicationId)
      setStatusOverride(application.discovery_status)
    } catch {
      setPauseResumeError('Could not resume discovery. Try again.')
    } finally {
      setPauseResumeBusy(false)
    }
  }

  // Read via refs inside the poll tick rather than depending on `liveStatus`/
  // `liveStage` directly — those flip through several transient values
  // (initializing/authenticating/discovering/analyzing) during one run, and
  // making the effect depend on them would tear down and recreate the
  // interval (with an extra immediate `poll()`) on every one of those, not
  // just the two terminal ones this actually needs to stop on.
  const liveStatusRef = useRef(liveStatus)
  liveStatusRef.current = liveStatus
  const liveStageRef = useRef(liveStage)
  liveStageRef.current = liveStage

  useEffect(() => {
    let cancelled = false
    let interval: ReturnType<typeof setInterval> | undefined

    async function poll() {
      try {
        const rows = await api.listJourneys(applicationId)
        if (!cancelled) setJourneys(rows)
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
      // `[FIXED 2026-07-22]` Inference writes Journeys one at a time (its own
      // commit per candidate, Story 2.6) — stopping as soon as
      // `journeys.length > 0` (the old condition) stopped polling the
      // instant the *first* Journey landed, silently missing every one
      // written after it (a real run producing 11 Journeys only ever showed
      // 1). `discovery_stage` reaching "analyzed" (backend's terminal
      // marker, written once InferenceActivity finishes creating all
      // Journeys) is the real "analysis fully finished" signal; a failed
      // run is the other stop case.
      if (!cancelled && (liveStatusRef.current === 'failed' || liveStageRef.current === 'analyzed')) {
        clearInterval(interval)
      }
    }

    poll()
    interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId])

  // Land on the first Journey selected by default, not an empty canvas —
  // also re-picks the first one if the selected Journey was deleted.
  useEffect(() => {
    if (selectedId && journeys.some((j) => j.id === selectedId)) return
    setSelectedId(journeys[0]?.id ?? null)
  }, [journeys, selectedId])

  useEffect(() => {
    if (!selectedId) {
      setSteps([])
      return
    }
    let cancelled = false
    api.listJourneySteps(selectedId).then((rows) => {
      if (!cancelled) setSteps(rows)
    })
    return () => {
      cancelled = true
    }
  }, [selectedId])

  async function handleRename(id: string, name: string) {
    setRenamingId(null)
    const updated = await api.renameJourney(id, name)
    setJourneys((rows) => rows.map((j) => (j.id === id ? updated : j)))
  }

  async function handleDelete(id: string) {
    if (!window.confirm('Delete this Journey? It will be excluded from the Trusted Knowledge Model.')) {
      return
    }
    await api.deleteJourney(id)
    setJourneys((rows) => rows.filter((j) => j.id !== id))
    setSelectedId((current) => (current === id ? null : current))
  }

  const selectedJourney = journeys.find((j) => j.id === selectedId) ?? null
  const stages = stageFlow(steps)
  const canContinue = journeys.length > 0 && !continuing

  const searchLower = search.trim().toLowerCase()
  const matchingJourneys = journeys.filter((j) => (j.name ?? '').toLowerCase().includes(searchLower))
  const totalPages = Math.max(1, Math.ceil(matchingJourneys.length / JOURNEYS_PER_PAGE))
  const pageClamped = Math.min(page, totalPages - 1)
  const pagedJourneys = matchingJourneys.slice(
    pageClamped * JOURNEYS_PER_PAGE,
    pageClamped * JOURNEYS_PER_PAGE + JOURNEYS_PER_PAGE,
  )
  const showPagination = matchingJourneys.length > JOURNEYS_PER_PAGE

  async function handleContinueToScenarios() {
    setContinuing(true)
    setContinueError(false)
    try {
      await api.generateScenarios(applicationId)
      onContinueToScenarios()
    } catch {
      setContinueError(true)
    } finally {
      setContinuing(false)
    }
  }

  return (
    <>
      <Stepper current="discover" furthestCount={furthestCount} onStepClick={onStepClick} onPrevious={onPrevious} onNext={onNext} />
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
              <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0, color: 'var(--ink)' }}>
                Discover Journeys
              </h1>
              <StatusPill status={status} />
            </div>
            <div className="caption" style={{ fontSize: 13, marginTop: 3 }}>
              {journeys.length} Journey{journeys.length === 1 ? '' : 's'} Discovered
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-5)', flexShrink: 0 }}>
            <input
              type="text"
              placeholder="Search journeys"
              aria-label="Search journeys"
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
            {(status === 'running' || status === 'paused') && (
              <button
                type="button"
                className="button-secondary"
                onClick={status === 'running' ? handlePause : handleResume}
                disabled={pauseResumeBusy}
              >
                {status === 'running' ? 'Pause Discovery' : 'Resume Discovery'}
              </button>
            )}
            <button
              type="button"
              onClick={handleContinueToScenarios}
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
              Continue to Scenarios →
            </button>
          </div>
        </div>

        {sessionExpired ? (
          <p className="caption" role="alert" style={{ color: 'var(--danger)' }}>
            Session expired mid-crawl. Re-authenticate to continue discovery.
          </p>
        ) : discoveryWorkerDown ? (
          <ServiceErrorNote code="DISCOVERY_UNAVAILABLE" />
        ) : (
          status === 'failed' && (
            <p className="caption" role="alert" style={{ color: 'var(--danger)' }}>
              Discovery Run failed.
            </p>
          )
        )}

        {status === 'running' && retryCount > 0 && (
          <p className="caption" style={{ color: 'var(--warn-strong)' }}>
            Recovered from a worker restart — resuming from where it left off.
          </p>
        )}

        {continueError && <ServiceErrorNote code="GENERATION_UNAVAILABLE" />}

        {status === 'paused' && (
          <p className="caption" style={{ color: 'var(--warn-strong)' }}>
            Discovery paused. Resume to continue exploring from where it left off.
          </p>
        )}

        {pauseResumeError && (
          <p className="caption" role="alert" style={{ color: 'var(--danger)' }}>
            {pauseResumeError}
          </p>
        )}

        {journeys.length > 0 && (
          <div
            className="card-panel"
            style={{ display: 'flex', overflow: 'hidden' }}
          >
            <div
              style={{
                width: 260,
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
                {pagedJourneys.map((journey) => (
                  <li
                    key={journey.id}
                    className={`list-row card-clickable${selectedId === journey.id ? ' list-row-selected' : ''}`}
                    onClick={() => setSelectedId(journey.id)}
                    style={{
                      padding: 'var(--space-3) var(--space-4)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                    }}
                  >
                    {renamingId === journey.id ? (
                      <JourneyRenameInput
                        initialName={journey.name}
                        onSave={(name) => handleRename(journey.id, name)}
                        onCancel={() => setRenamingId(null)}
                      />
                    ) : (
                      <div style={{ minWidth: 0 }}>
                        <div
                          style={{
                            fontSize: 13.5,
                            fontWeight: 600,
                            color: selectedId === journey.id ? 'var(--accent)' : 'var(--ink)',
                          }}
                        >
                          {journey.name}
                        </div>
                        <div className="caption" style={{ fontSize: 12 }}>
                          {journey.step_count} step{journey.step_count === 1 ? '' : 's'}
                        </div>
                      </div>
                    )}
                    <JourneyRowMenu
                      onRename={() => setRenamingId(journey.id)}
                      onDelete={() => handleDelete(journey.id)}
                    />
                  </li>
                ))}
                {pagedJourneys.length === 0 && (
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
                display: 'flex',
                gap: 'var(--space-9)',
              }}
            >
              {selectedJourney ? (
                <>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 'var(--space-1)' }}>
                      {selectedJourney.name}
                    </div>
                    {selectedJourney.description && (
                      <div className="caption" style={{ fontSize: 13, marginBottom: 'var(--space-2)' }}>
                        {selectedJourney.description}
                      </div>
                    )}
                    <div className="caption" style={{ fontSize: 13, fontWeight: 600, marginBottom: 'var(--space-4)' }}>
                      Discovered flow · {selectedJourney.step_count} step
                      {selectedJourney.step_count === 1 ? '' : 's'}
                    </div>
                    <div data-testid="journey-flow">
                      {stages.map((stage, index) => (
                        <div key={`${stage}-${index}`} style={{ display: 'flex', gap: 'var(--space-3)' }}>
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                            <div
                              style={{
                                width: 26,
                                height: 26,
                                flexShrink: 0,
                                borderRadius: 'var(--radius-full)',
                                background: 'var(--accent-wash)',
                                color: 'var(--accent)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: 12,
                                fontWeight: 700,
                              }}
                            >
                              {index + 1}
                            </div>
                            {index < stages.length - 1 && (
                              <div aria-hidden="true" style={{ width: 2, flex: 1, background: 'var(--border)' }} />
                            )}
                          </div>
                          <div style={{ paddingBottom: index < stages.length - 1 ? 'var(--space-5)' : 0 }}>
                            <div style={{ fontSize: 14, fontWeight: 600 }}>{stage}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div
                    style={{
                      width: 480,
                      flexShrink: 0,
                      alignSelf: 'flex-start',
                      position: 'sticky',
                      top: 'var(--space-4)',
                    }}
                  >
                    <div
                      className="caption"
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        marginBottom: 'var(--space-2)',
                      }}
                    >
                      Reference screenshot
                    </div>
                    {steps.at(-1)?.screenshot_url ? (
                      <img
                        src={steps.at(-1)?.screenshot_url ?? undefined}
                        alt="Journey's final step screenshot"
                        onClick={() => setLightboxUrl(steps.at(-1)?.screenshot_url ?? null)}
                        style={{
                          width: '100%',
                          height: 'auto',
                          objectFit: 'contain',
                          cursor: 'zoom-in',
                          border: '1px solid var(--border)',
                        }}
                      />
                    ) : (
                      <div
                        style={{
                          height: 420,
                          borderRadius: 'var(--radius-xl)',
                          border: '1px solid var(--border)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          background:
                            'repeating-linear-gradient(135deg, var(--canvas-wash-alt), var(--canvas-wash-alt) 10px, var(--canvas-wash) 10px, var(--canvas-wash) 20px)',
                        }}
                      >
                        <span
                          className="caption"
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: 11.5,
                            background: 'var(--canvas)',
                            border: '1px solid var(--border)',
                            borderRadius: 'var(--radius-xs)',
                            padding: '4px 10px',
                          }}
                        >
                          no screenshot available
                        </span>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <p className="caption" style={{ margin: 0 }}>
                  Select a Journey to see its discovered steps.
                </p>
              )}
            </div>
          </div>
        )}

        {journeys.length === 0 && status !== 'failed' && (
          hadJourneysRef.current ? (
            <p style={{ textAlign: 'center', padding: '80px 24px', color: 'var(--ink-muted)', fontSize: 14 }}>
              All journeys have been removed.
            </p>
          ) : (
            <ImportProgress applicationName={applicationName} />
          )
        )}
      </main>
      {lightboxUrl && (
        <div
          onClick={() => setLightboxUrl(null)}
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.85)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
        >
          <button
            type="button"
            aria-label="Close"
            onClick={() => setLightboxUrl(null)}
            style={{
              position: 'fixed',
              top: 'var(--space-5)',
              right: 'var(--space-5)',
              width: 40,
              height: 40,
              borderRadius: 'var(--radius-full)',
              border: '1px solid rgba(255,255,255,0.3)',
              background: 'rgba(255,255,255,0.1)',
              color: '#fff',
              fontSize: 20,
              lineHeight: 1,
              cursor: 'pointer',
            }}
          >
            ×
          </button>
          <img
            src={lightboxUrl}
            alt="Journey's final step screenshot, enlarged"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: '90vw', maxHeight: '90vh', objectFit: 'contain' }}
          />
        </div>
      )}
    </>
  )
}
