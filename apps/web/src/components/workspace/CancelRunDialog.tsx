import { useState } from 'react'
import { createPortal } from 'react-dom'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faTriangleExclamation } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type TestRunRead } from '../../api'
import { LoadingDots } from '../LoadingDots'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'

type RunRef = { id: string; run_number: number }

// ~2s: well inside Workspace's 5s post-trigger window, and Prepare creates
// the run row within about a second of the workflow starting.
const FIND_RUN_ATTEMPTS = 3
const FIND_RUN_DELAY_MS = 1000

// Sits beside the toolbar's "Running…" button and is always clickable while
// a run is going. Which run to cancel is settled at click time: `run` (from
// Workspace's poll) is only a hint — when it's missing, the latest run is
// fetched right then, so the button never depends on the poll having
// delivered (observed: a browser whose poll never did left it disabled for a
// whole run). Clicked in the second or so before PrepareTestRunActivity
// creates the run row, it retries briefly.
export function CancelRunButton({
  applicationId,
  run: runHint,
  onCancelled,
  onAlreadyFinished,
}: {
  applicationId: string
  run: RunRef | null
  // The cancel endpoint answers with the run already cancelled (DB first,
  // workflow after) — applied straight away, no poll needed.
  onCancelled: (run: TestRunRead) => void
  // The run finished on its own before the cancel (no active run at click
  // time, or a 409 from the endpoint).
  onAlreadyFinished: () => void
}) {
  const [target, setTarget] = useState<RunRef | null>(null)
  const [finding, setFinding] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function findActiveRun(): Promise<RunRef | 'finished' | null> {
    for (let attempt = 0; attempt < FIND_RUN_ATTEMPTS; attempt++) {
      if (attempt > 0) await new Promise((resolve) => setTimeout(resolve, FIND_RUN_DELAY_MS))
      try {
        const latest = (await api.listTestRuns(applicationId, null, 1)).items[0]
        if (latest && (latest.status === 'pending' || latest.status === 'running')) {
          return { id: latest.id, run_number: latest.run_number }
        }
        // Only "finished" once the trigger has had time to create its row —
        // an early miss is the previous run still on top.
        if (latest && attempt === FIND_RUN_ATTEMPTS - 1) return 'finished'
      } catch {
        // transient — try again
      }
    }
    return null
  }

  async function openConfirm() {
    setNotice(null)
    setError(null)
    if (runHint) {
      setTarget(runHint)
      return
    }
    setFinding(true)
    try {
      const found = await findActiveRun()
      if (found === 'finished') onAlreadyFinished()
      else if (found) setTarget(found)
      else setNotice('The run is still starting — try again in a moment.')
    } finally {
      setFinding(false)
    }
  }

  async function confirmCancel() {
    const run = target
    if (!run) return
    setCancelling(true)
    setError(null)
    try {
      onCancelled(await api.cancelTestRun(applicationId, run.id))
      setTarget(null)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setTarget(null)
        onAlreadyFinished()
      } else {
        setError(err instanceof ApiError ? err.message : 'Could not cancel the run. Try again.')
      }
    } finally {
      setCancelling(false)
    }
  }

  return (
    <>
      <button
        type="button"
        aria-busy={finding}
        onClick={() => {
          if (!finding) openConfirm()
        }}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          height: 36,
          padding: '0 16px',
          borderRadius: 8,
          border: '1px solid color-mix(in srgb, var(--bad) 40%, transparent)',
          background: 'var(--panel)',
          color: 'var(--danger-strong)',
          fontSize: 13.5,
          fontWeight: 600,
          flex: 'none',
          whiteSpace: 'nowrap',
          cursor: finding ? 'default' : 'pointer',
        }}
      >
        {finding ? <LoadingDots label="Finding run" /> : 'Cancel run'}
      </button>
      {notice && (
        <span role="status" style={{ fontSize: 12.5, color: 'var(--fg-3)', whiteSpace: 'nowrap' }}>
          {notice}
        </span>
      )}
      {target && (
        <CancelRunDialog
          runNumber={target.run_number}
          cancelling={cancelling}
          error={error}
          onConfirm={confirmCancel}
          onClose={() => setTarget(null)}
        />
      )}
    </>
  )
}

function CancelRunDialog({
  runNumber,
  cancelling,
  error,
  onConfirm,
  onClose,
}: {
  runNumber: number
  cancelling: boolean
  error: string | null
  onConfirm: () => void
  onClose: () => void
}) {
  useEscapeToClose(() => {
    if (!cancelling) onClose()
  })
  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Cancel run"
      onClick={() => {
        if (!cancelling) onClose()
      }}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,23,42,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        zIndex: 100,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 420, width: '100%', padding: 24, background: 'var(--panel)', borderRadius: 14, boxShadow: 'var(--panel-shadow)' }}
      >
        <div style={{ display: 'flex', gap: 14, marginBottom: 18 }}>
          <span
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              width: 40,
              height: 40,
              borderRadius: 1000,
              background: 'color-mix(in srgb, var(--bad) 12%, transparent)',
              color: 'var(--bad)',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <FontAwesomeIcon icon={faTriangleExclamation} style={{ fontSize: 17 }} />
          </span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 4, color: 'var(--fg)' }}>
              Cancel run #{runNumber}?
            </div>
            <p style={{ margin: 0, lineHeight: 1.5, fontSize: 13, color: 'var(--fg-3)' }}>
              Tests still running are stopped and every test that hasn&apos;t finished is marked
              cancelled. Finished tests keep their results. No report or email is sent.
            </p>
            {error && (
              <p role="alert" style={{ margin: '8px 0 0', fontSize: 12.5, color: 'var(--danger-strong)' }}>
                {error}
              </p>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button
            type="button"
            disabled={cancelling}
            onClick={onClose}
            style={{ padding: '9px 16px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--fg-2)', fontWeight: 600, cursor: 'pointer' }}
          >
            Keep running
          </button>
          <button
            type="button"
            disabled={cancelling}
            onClick={onConfirm}
            style={{
              padding: '9px 16px',
              borderRadius: 8,
              border: 'none',
              background: 'var(--bad)',
              color: '#FFFFFF',
              fontWeight: 600,
              cursor: cancelling ? 'default' : 'pointer',
              opacity: cancelling ? 0.7 : 1,
            }}
          >
            {cancelling ? <LoadingDots label="Cancelling" /> : 'Cancel run'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
