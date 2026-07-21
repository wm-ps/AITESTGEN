import { useEffect, useRef, useState } from 'react'
import { api, type JourneyRead, type JourneyStepRead } from '../api'
import { useDiscoveryProgress } from '../hooks/useDiscoveryProgress'
import { ImportProgress } from './ImportProgress'
import { Stepper } from './Stepper'
import { StatusPill } from './StatusPill'

const POLL_INTERVAL_MS = 1500

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
}: {
  applicationId: string
  applicationName: string
  discoveryStatus: string
  discoveryStage: string | null
  discoveryFailureReason: string | null
}) {
  const [journeys, setJourneys] = useState<JourneyRead[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [steps, setSteps] = useState<JourneyStepRead[]>([])
  const [renamingId, setRenamingId] = useState<string | null>(null)

  const {
    status: liveStatus,
    stage: liveStage,
    failureReason: liveFailureReason,
  } = useDiscoveryProgress(
    applicationId,
    discoveryStatus,
    discoveryStage,
    discoveryFailureReason,
    journeys.length > 0,
  )

  const sessionExpired = liveStatus === 'failed' && liveFailureReason === 'session_expired'

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const rows = await api.listJourneys(applicationId)
        if (!cancelled) setJourneys(rows)
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
    }

    poll()
    // `status` flips to "complete" as soon as the crawl finishes, well
    // before Inference ever writes a Journey — gating on `status !== 'running'`
    // alone would stop this poll before Journeys ever appear.
    if (journeys.length > 0 || liveStatus === 'failed') return
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId, liveStatus, journeys.length])

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

  return (
    <>
      <Stepper current="discover" />
      <main
        style={{
          maxWidth: 'var(--content-max)',
          margin: '0 auto',
          padding: `var(--content-top) var(--content-x)`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', margin: '0 0 8px' }}>
          <h1 style={{ fontSize: 19, fontWeight: 650, margin: 0 }}>Discover Journeys</h1>
          <StatusPill status={liveStatus} />
        </div>

        {sessionExpired ? (
          <p className="caption" role="alert" style={{ color: 'var(--danger)' }}>
            Session expired mid-crawl. Re-authenticate to continue discovery.
          </p>
        ) : (
          liveStatus === 'failed' && (
            <p className="caption" role="alert" style={{ color: 'var(--danger)' }}>
              Discovery Run failed.
            </p>
          )
        )}

        {journeys.length > 0 && (
          <div
            style={{
              display: 'flex',
              gap: 'var(--space-5)',
              alignItems: 'flex-start',
              marginTop: 'var(--space-4)',
            }}
          >
            <ul
              style={{
                listStyle: 'none',
                margin: 0,
                padding: 0,
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-2)',
              }}
            >
              {journeys.map((journey) => (
                <li
                  key={journey.id}
                  className="card-panel card-clickable"
                  onClick={() => setSelectedId(journey.id)}
                  style={{
                    padding: 'var(--space-3) var(--space-4)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    cursor: 'pointer',
                    borderColor: selectedId === journey.id ? 'var(--signal)' : undefined,
                  }}
                >
                  {renamingId === journey.id ? (
                    <JourneyRenameInput
                      initialName={journey.name}
                      onSave={(name) => handleRename(journey.id, name)}
                      onCancel={() => setRenamingId(null)}
                    />
                  ) : (
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600 }}>{journey.name}</div>
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
            </ul>

            <div
              className="card-panel"
              style={{
                width: 340,
                flexShrink: 0,
                padding: 'var(--space-4)',
                position: 'sticky',
                top: 'var(--space-4)',
              }}
            >
              {selectedJourney ? (
                <>
                  <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 'var(--space-1)' }}>
                    {selectedJourney.name}
                  </div>
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
                              background: 'var(--signal-wash)',
                              color: 'var(--signal)',
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
                </>
              ) : (
                <p className="caption" style={{ margin: 0 }}>
                  Select a Journey to see its discovered steps.
                </p>
              )}
            </div>
          </div>
        )}

        {journeys.length === 0 && liveStatus !== 'failed' && (
          <ImportProgress stage={liveStage} applicationName={applicationName} />
        )}
      </main>
    </>
  )
}
