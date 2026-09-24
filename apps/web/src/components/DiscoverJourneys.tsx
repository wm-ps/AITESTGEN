import { useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowRight, faEllipsisVertical } from '@fortawesome/free-solid-svg-icons'
import { faImage } from '@fortawesome/free-regular-svg-icons'
import { api, type JourneyRead, type JourneyStepRead } from '../api'
import { useDiscoveryProgress } from '../hooks/useDiscoveryProgress'
import { useEscapeToClose } from '../hooks/useEscapeToClose'
import { AppIdentityLine } from './AppIdentityLine'
import { ServiceErrorNote } from './ServiceError'
import { ImportProgress } from './ImportProgress'
import { Pagination } from './Pagination'
import { EmptyState, JourneysIllustration } from './EmptyState'

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
          color: 'var(--fg-4)',
          cursor: 'pointer',
          fontSize: 16,
          lineHeight: 1,
        }}
      >
        <FontAwesomeIcon icon={faEllipsisVertical} />
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
  applicationUrl,
  discoveryStatus,
  discoveryStage,
  discoveryFailureReason,
  onContinueToScenarios,
}: {
  applicationId: string
  applicationName: string
  applicationUrl: string
  discoveryStatus: string
  discoveryStage: string | null
  discoveryFailureReason: string | null
  onContinueToScenarios: () => void
}) {
  const [journeys, setJourneys] = useState<JourneyRead[]>([])
  // Vantage V2: every journey on the current page shows its own nav timeline
  // + screenshot inline (stacked cards), not a click-to-select master/detail
  // split — so steps are fetched per visible journey, not for one selection.
  const [stepsByJourney, setStepsByJourney] = useState<Record<string, JourneyStepRead[]>>({})
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [continuing, setContinuing] = useState(false)
  const [continueError, setContinueError] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)
  useEscapeToClose(() => setLightboxUrl(null), lightboxUrl != null)
  // Per-card screenshot fade-in — each journey's image loads independently
  // now that every card on the page renders its own (no more single
  // selected-journey detail pane to fade in and out of).
  const [loadedImgIds, setLoadedImgIds] = useState<Set<string>>(new Set())
  // `[FIXED]` A screenshot's presigned URL can fail to load (expired,
  // network blip, the underlying object missing) — with no `onError`
  // handling, that image tag just sat there broken (browser's native
  // broken-image icon) with its skeleton never clearing either, since
  // `onLoad` never fires for a failed request. Falls back to the same "no
  // screenshot yet" placeholder a genuinely-absent screenshot already
  // gets, instead of ever showing broken/blank image content. Keyed by
  // URL (like the `<img key={screenshotUrl}>` below), not journey id — a
  // later poll's fresh presigned URL for the same journey is untried and
  // gets a real retry, rather than staying stuck failed forever.
  const [failedImgUrls, setFailedImgUrls] = useState<Set<string>>(new Set())
  // Story 2.17: pause/resume already round-trips through the API — this
  // just reflects the response immediately rather than waiting for
  // useDiscoveryProgress's next poll tick.
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
  } = useDiscoveryProgress(applicationId, discoveryStatus, discoveryStage, discoveryFailureReason)

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

  const searchLower = search.trim().toLowerCase()
  const matchingJourneys = journeys.filter((j) => (j.name ?? '').toLowerCase().includes(searchLower))
  const totalPages = Math.max(1, Math.ceil(matchingJourneys.length / JOURNEYS_PER_PAGE))
  const pageClamped = Math.min(page, totalPages - 1)
  const pagedJourneys = matchingJourneys.slice(
    pageClamped * JOURNEYS_PER_PAGE,
    pageClamped * JOURNEYS_PER_PAGE + JOURNEYS_PER_PAGE,
  )
  const showPagination = matchingJourneys.length > JOURNEYS_PER_PAGE

  // Fetches steps for whichever journeys are visible on the current page —
  // only the ones not already cached, and never re-fetches ones we have
  // (a journey's steps don't change once discovery has written them).
  useEffect(() => {
    let cancelled = false
    const toFetch = pagedJourneys.filter((j) => !(j.id in stepsByJourney))
    if (toFetch.length === 0) return
    Promise.all(toFetch.map((j) => api.listJourneySteps(j.id).then((rows) => [j.id, rows] as const))).then(
      (entries) => {
        if (cancelled) return
        setStepsByJourney((prev) => {
          const next = { ...prev }
          for (const [id, rows] of entries) next[id] = rows
          return next
        })
      },
    )
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagedJourneys.map((j) => j.id).join(',')])

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
  }

  const canContinue = journeys.length > 0 && !continuing

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
            <h2 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Journeys</h2>
            <AppIdentityLine name={applicationName} url={applicationUrl} />
            <div className="caption" style={{ fontSize: 13, marginTop: 3 }}>
              {journeys.length} journey{journeys.length === 1 ? '' : 's'} discovered
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
                border: '1px solid var(--border-2)',
                borderRadius: 'var(--radius)',
                fontSize: 13,
                fontFamily: 'inherit',
                color: 'var(--fg)',
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
            {journeys.length > 0 && (
              <button
                type="button"
                onClick={handleContinueToScenarios}
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
                Review scenarios
                <FontAwesomeIcon icon={faArrowRight} style={{ fontSize: 14 }} />
              </button>
            )}
          </div>
        </div>

        {sessionExpired ? (
          <p className="caption" role="alert" style={{ color: 'var(--danger)' }}>
            Session expired mid-discovery. Re-authenticate to continue discovery.
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {pagedJourneys.map((journey, cardIndex) => {
              const steps = stepsByJourney[journey.id] ?? []
              const stages = stageFlow(steps)
              const rawScreenshotUrl = steps.at(-1)?.screenshot_url ?? null
              const screenshotUrl = rawScreenshotUrl && !failedImgUrls.has(rawScreenshotUrl) ? rawScreenshotUrl : null
              const loaded = loadedImgIds.has(journey.id)
              return (
                <div
                  key={journey.id}
                  style={{
                    background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
                    backdropFilter: 'blur(16px) saturate(1.25)',
                    border: '1px solid var(--border-1)',
                    borderRadius: 14,
                    padding: '18px 20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 16,
                    boxShadow: 'var(--panel-shadow)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', minWidth: 0 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--fg-5)', flex: 'none' }}>
                      {String(pageClamped * JOURNEYS_PER_PAGE + cardIndex + 1).padStart(2, '0')}
                    </span>
                    {renamingId === journey.id ? (
                      <JourneyRenameInput
                        initialName={journey.name}
                        onSave={(name) => handleRename(journey.id, name)}
                        onCancel={() => setRenamingId(null)}
                      />
                    ) : (
                      <span style={{ fontSize: 16, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.014em' }}>{journey.name}</span>
                    )}
                    <span style={{ flex: 1 }} />
                    <JourneyRowMenu onRename={() => setRenamingId(journey.id)} onDelete={() => handleDelete(journey.id)} />
                  </div>
                  {journey.description && (
                    <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: -8 }}>{journey.description}</div>
                  )}

                  <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                    <div style={{ flex: '0 1 230px', minWidth: 190, display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {screenshotUrl ? (
                        <>
                          <div
                            style={{
                              position: 'relative',
                              aspectRatio: '16/10',
                              borderRadius: 10,
                              border: '1px solid var(--border-2)',
                              overflow: 'hidden',
                              background: 'var(--panel-2)',
                            }}
                          >
                            {!loaded && (
                              <div
                                className="aitg-skeleton"
                                style={{
                                  position: 'absolute',
                                  inset: 0,
                                  display: 'flex',
                                  flexDirection: 'column',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  gap: 6,
                                  background:
                                    'linear-gradient(90deg, var(--chip) 30%, color-mix(in srgb, var(--border-2) 60%, var(--chip)) 50%, var(--chip) 70%)',
                                  backgroundSize: '200% 100%',
                                }}
                              >
                                <FontAwesomeIcon icon={faImage} style={{ fontSize: 18, color: 'var(--fg-5)' }} />
                                <span style={{ fontSize: 10.5, color: 'var(--fg-4)' }}>Preparing preview…</span>
                              </div>
                            )}
                            <img
                              key={screenshotUrl}
                              src={screenshotUrl}
                              alt={`${journey.name}'s final step screenshot`}
                              decoding="async"
                              onClick={() => setLightboxUrl(screenshotUrl)}
                              onLoad={() => setLoadedImgIds((prev) => new Set(prev).add(journey.id))}
                              onError={() => setFailedImgUrls((prev) => new Set(prev).add(screenshotUrl))}
                              style={{
                                display: 'block',
                                width: '100%',
                                height: '100%',
                                objectFit: 'cover',
                                cursor: 'zoom-in',
                                opacity: loaded ? 1 : 0,
                                transition: 'opacity 250ms ease',
                              }}
                            />
                          </div>
                        </>
                      ) : (
                        <div
                          style={{
                            position: 'relative',
                            aspectRatio: '16/10',
                            borderRadius: 10,
                            border: '1px dashed var(--border-2)',
                            background:
                              'repeating-linear-gradient(135deg,var(--panel-2),var(--panel-2) 8px,var(--chip) 8px,var(--chip) 16px)',
                            overflow: 'hidden',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                        >
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7 }}>
                            <FontAwesomeIcon icon={faImage} style={{ fontSize: 20, color: "var(--fg-5)" }} />
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-4)', background: 'var(--panel)', border: '1px solid var(--border-2)', borderRadius: 4, padding: '2px 7px', whiteSpace: 'nowrap' }}>
                              no screenshot yet
                            </span>
                          </div>
                        </div>
                      )}
                    </div>

                    <div style={{ flex: '1 1 340px', minWidth: 280 }}>
                      <div style={{ border: '1px solid var(--border-2)', borderRadius: 10, background: 'var(--panel-2)', overflow: 'hidden' }}>
                        <div style={{ padding: '9px 14px', borderBottom: '1px solid var(--border-2)', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>
                          Page navigation
                        </div>
                        <div data-testid="journey-flow" style={{ display: 'flex', flexDirection: 'column' }}>
                          {stages.length === 0 && (
                            <div style={{ padding: '12px 14px', fontSize: 12, color: 'var(--fg-4)' }}>Loading steps…</div>
                          )}
                          {stages.map((stage, index) => (
                            <div
                              key={`${stage}-${index}`}
                              style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 14px', minWidth: 0, borderTop: index ? '1px solid var(--row-line)' : 'none' }}
                            >
                              <span style={{ flex: 'none', width: 18, height: 18, borderRadius: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-mono)', fontSize: 9.5, fontWeight: 600, background: 'var(--chip)', border: '1px solid var(--border-2)', color: 'var(--fg-3)' }}>
                                {index + 1}
                              </span>
                              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg-1)' }}>{stage}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
            {pagedJourneys.length === 0 && (
              <EmptyState
                illustration={<JourneysIllustration />}
                title="No journeys found"
                subtitle="No journeys match your search."
              />
            )}
            {showPagination && (
              <Pagination
                page={pageClamped}
                totalPages={totalPages}
                totalItems={matchingJourneys.length}
                pageSize={JOURNEYS_PER_PAGE}
                onPrev={() => setPage(pageClamped - 1)}
                onNext={() => setPage(pageClamped + 1)}
                onPage={setPage}
              />
            )}
          </div>
        )}

        {journeys.length === 0 && status !== 'failed' && (
          hadJourneysRef.current ? (
            <EmptyState
              illustration={<JourneysIllustration />}
              title="No journeys"
              subtitle="All journeys have been removed."
            />
          ) : (
            <ImportProgress applicationName={applicationName} />
          )
        )}
      </div>
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
