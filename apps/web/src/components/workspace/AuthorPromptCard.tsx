import { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faWandMagicSparkles, faXmark } from '@fortawesome/free-solid-svg-icons'
import { explorerApi } from '../../explorer/explorerApi'
import { LoadingDots } from '../LoadingDots'

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
  const canStart = prompt.trim().length > 0 && !starting

  async function start(event: React.FormEvent) {
    event.preventDefault()
    if (!canStart) return
    setStarting(true)
    setError(null)
    try {
      await explorerApi.startAuthoring(applicationId, prompt.trim())
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
            anything is unclear, and adds the test cases here.
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
