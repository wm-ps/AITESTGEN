import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faWandMagicSparkles, faXmark } from '@fortawesome/free-solid-svg-icons'
import { explorerApi } from '../../explorer/explorerApi'
import { LoadingDots } from '../LoadingDots'
import { api } from '../../api'
import type { JourneyRead } from '../../api'

// The journey choice that means "create a new journey with this name".
const NEW_JOURNEY = '__new__'

const fieldStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  height: 36,
  padding: '0 11px',
  border: '1px solid var(--border-2)',
  borderRadius: 9,
  fontSize: 13,
  color: 'var(--fg-1)',
  background: 'var(--panel)',
  fontFamily: 'inherit',
  outline: 'none',
}

// "Author a test case": the user's request starts an authoring run on
// Explorer (its own path, explorer_worker.authoring). Explorer follows the
// request exactly, asks on its own screen what it needs, and adds the test
// cases here when done ("Author test cases" filter). The old live-exploration
// panel (LiveExplorationPanel) is kept but no longer shown.
export function AuthorPromptCard({
  applicationId,
  onClose,
  onStarted,
}: {
  applicationId: string
  onClose: () => void
  // The run is on: show it on the Explorer screen.
  onStarted: () => void
}) {
  const [prompt, setPrompt] = useState('')
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [journeys, setJourneys] = useState<JourneyRead[] | null>(null)
  // An existing journey's id, NEW_JOURNEY, or '' (nothing chosen yet).
  const [journeyChoice, setJourneyChoice] = useState('')
  const [newJourneyName, setNewJourneyName] = useState('')
  const isNewJourney = journeyChoice === NEW_JOURNEY
  const journeyReady = isNewJourney ? newJourneyName.trim() !== '' : journeyChoice !== ''
  const canStart = prompt.trim().length > 0 && journeyReady && !starting

  useEffect(() => {
    let cancelled = false
    api
      .listJourneys(applicationId)
      .then((rows) => {
        if (cancelled) return
        setJourneys(rows)
        // Nothing to pick from: creating a new journey is the only option.
        if (rows.length === 0) setJourneyChoice(NEW_JOURNEY)
      })
      .catch(() => {
        if (!cancelled) {
          setJourneys([])
          setJourneyChoice(NEW_JOURNEY)
        }
      })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  async function start(event: React.FormEvent) {
    event.preventDefault()
    if (!canStart) return
    setStarting(true)
    setError(null)
    try {
      await explorerApi.startAuthoring(
        applicationId,
        prompt.trim(),
        isNewJourney ? { journey_name: newJourneyName.trim() } : { journey_id: journeyChoice },
      )
      onStarted()
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Could not start. Please try again.')
      setStarting(false)
    }
  }

  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid rgba(30,150,138,0.26)',
        borderRadius: 14,
        boxShadow: 'var(--panel-shadow)',
        padding: '19px 20px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 13 }}>
        <div
          aria-hidden="true"
          style={{
            width: 32,
            height: 32,
            flexShrink: 0,
            borderRadius: 9,
            background: 'rgba(30,150,138,0.16)',
            border: '1px solid rgba(30,150,138,0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent-2)',
          }}
        >
          <FontAwesomeIcon icon={faWandMagicSparkles} style={{ fontSize: 13 }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.01em' }}>
            Author test cases
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 4 }}>
            Describe a flow, or list the exact scenarios you want. Explorer follows only what you write, asks if
            anything is unclear, and adds the test cases to the journey you choose.
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            border: '1px solid var(--border-2)',
            background: 'var(--panel-2)',
            color: 'var(--fg-4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
          }}
        >
          <FontAwesomeIcon icon={faXmark} style={{ fontSize: 11 }} />
        </button>
      </div>

      <form onSubmit={start} style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: '1 1 220px', minWidth: 0 }}>
            <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)' }}>
              Add the test cases to this journey
            </span>
            <select
              aria-label="Journey"
              value={journeyChoice}
              onChange={(event) => setJourneyChoice(event.target.value)}
              disabled={journeys === null}
              style={fieldStyle}
            >
              <option value="" disabled>
                {journeys === null ? 'Loading journeys' : 'Select a journey'}
              </option>
              {journeys?.map((journey) => (
                <option key={journey.id} value={journey.id}>
                  {journey.name}
                </option>
              ))}
              <option value={NEW_JOURNEY}>+ New journey</option>
            </select>
          </label>
          {isNewJourney && (
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: '1 1 220px', minWidth: 0 }}>
              <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)' }}>New journey name</span>
              <input
                aria-label="New journey name"
                value={newJourneyName}
                onChange={(event) => setNewJourneyName(event.target.value)}
                placeholder="Enter the new journey name"
                style={fieldStyle}
              />
            </label>
          )}
        </div>
        <textarea
          aria-label="What to test"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Describe the flow to test, or list the scenarios you want"
          rows={4}
          style={{
            width: '100%',
            boxSizing: 'border-box',
            padding: '11px 13px',
            border: '1px solid var(--border-2)',
            borderRadius: 9,
            fontSize: 13,
            color: 'var(--fg-1)',
            background: 'var(--panel)',
            fontFamily: 'inherit',
            resize: 'vertical',
            outline: 'none',
          }}
        />
        {error && <div style={{ color: 'var(--bad)', fontSize: 13, marginTop: 8 }}>{error}</div>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }}>
          <button
            type="submit"
            disabled={!canStart}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              height: 36,
              padding: '0 16px',
              borderRadius: 8,
              border: 'none',
              fontSize: 13.5,
              fontWeight: 600,
              color: '#fff',
              background: !canStart ? 'var(--fg-4)' : 'var(--accent)',
              boxShadow: !canStart ? 'none' : 'var(--accent-glow)',
              cursor: !canStart ? 'default' : 'pointer',
            }}
          >
            {starting ? <LoadingDots label="Starting" /> : 'Start authoring'}
          </button>
          <span style={{ fontSize: 10.5, color: 'var(--fg-4)' }}>Opens Explorer, where you can follow it live.</span>
        </div>
      </form>
    </div>
  )
}
