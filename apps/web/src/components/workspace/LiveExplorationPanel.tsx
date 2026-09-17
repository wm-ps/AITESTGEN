import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faWandMagicSparkles, faXmark } from '@fortawesome/free-solid-svg-icons'
import { faIcon } from '../../faIcon'

const Sparkles = faIcon(faWandMagicSparkles)
import { ApiError, api } from '../../api'
import type { LiveTestCaseRequestStatusRead } from '../../api'
import { GenerationLoader } from '../GenerationLoader'

const POLL_INTERVAL_MS = 3000
export const TERMINAL_STATUSES = new Set(['complete', 'failed', 'rejected'])

// Persisted so a page refresh, or closing and reopening this panel, can
// reconnect to an already-running request instead of losing it — the
// backend workflow keeps going regardless of whether anything is polling it.
export function requestIdStorageKey(applicationId: string) {
  return `live-exploration-request:${applicationId}`
}

const secondaryButtonStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  height: 34,
  padding: '0 14px',
  borderRadius: 8,
  border: '1px solid var(--border-2)',
  background: 'var(--panel-2)',
  color: 'var(--fg-2)',
  fontSize: 12.5,
  fontWeight: 500,
  cursor: 'pointer',
}

const IN_PROGRESS_COPY: Record<string, string> = {
  exploring: 'Exploring the live application…',
  // Covers code generation AND the internal verify/self-heal pass that
  // follows it — that pass exists only to catch a broken locator before the
  // test case ships; it's never a real, user-visible run, so it gets no
  // status/copy of its own (see LiveExplorationTestWorkflow's docstring).
  generating: 'Generating the test case…',
}

// Opened via "Author a test case" on the Scenario page (ReviewScenarios.tsx)
// — works even on a brand-new application with zero Discovery/TestSuite
// history: a
// live agent explores the real application itself (Playwright MCP + an LLM
// deciding each step) to accomplish the requirement, then generates and runs
// a test case grounded in exactly what it found. See
// `LiveExplorationTestWorkflow` (packages/workflows) for the full flow.
export function LiveExplorationPanel({
  applicationId,
  onClose,
  onComplete,
}: {
  applicationId: string
  onClose: () => void
  // Fired once, the moment a request reaches 'complete' — TestSuiteTab's
  // own test case list is fetched once on mount and otherwise never polled
  // again once it already has rows, so without this its new test cases
  // stayed invisible until something else (a tab switch, a refresh)
  // happened to remount it.
  onComplete?: () => void
}) {
  const [prompt, setPrompt] = useState('')
  const [requestId, setRequestId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(requestIdStorageKey(applicationId))
    } catch {
      return null
    }
  })
  const [statusRow, setStatusRow] = useState<LiveTestCaseRequestStatusRead | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!requestId) return
    let cancelled = false

    async function poll() {
      try {
        const row = await api.getLiveTestCaseRequest(applicationId, requestId as string)
        if (cancelled) return
        // `statusRow` here is still the value from before this fetch (a
        // status change re-runs this whole effect with a fresh closure) —
        // exactly the "first time we've seen it turn complete" signal, so
        // this fires once per request, not once per remaining poll tick.
        if (row.status === 'complete' && statusRow?.status !== 'complete') {
          onComplete?.()
        }
        setStatusRow(row)
        // Clear the persisted id as soon as the request reaches a terminal
        // status, not only on a 404 — otherwise it sits in storage
        // indefinitely (nothing else ever clears it short of "Try again"/
        // "+Explore another"), and TestSuiteTab's own "reopen if a request
        // is in flight" check (which only looks at whether *a* id is
        // stored, not its status) then reopens this panel to the old
        // complete/failed screen on every future visit to the tab — even
        // long after this run actually finished.
        if (TERMINAL_STATUSES.has(row.status)) {
          try {
            localStorage.removeItem(requestIdStorageKey(applicationId))
          } catch {
            // best-effort — worst case TestSuiteTab reopens this panel once
            // more next visit, which clears it again right here
          }
        }
      } catch (err) {
        // A stale persisted request id (expired workflow retention, or from
        // a different environment) 404s forever otherwise, leaving the panel
        // blank with no way back to the submit form.
        if (err instanceof ApiError && err.status === 404 && !cancelled) {
          try {
            localStorage.removeItem(requestIdStorageKey(applicationId))
          } catch {
            // ignore — clearing state below still recovers this session
          }
          setRequestId(null)
          setStatusRow(null)
          return
        }
        // otherwise best-effort poll — a transient failure just skips this tick
      }
    }

    poll()
    if (statusRow && TERMINAL_STATUSES.has(statusRow.status)) return
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId, requestId, statusRow?.status])

  function reset() {
    try {
      localStorage.removeItem(requestIdStorageKey(applicationId))
    } catch {
      // best-effort — worst case a stale id is retried and 404s harmlessly
    }
    setRequestId(null)
    setStatusRow(null)
    setPrompt('')
    setError(null)
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!prompt.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const { request_id } = await api.createLiveTestCase(applicationId, prompt.trim())
      try {
        localStorage.setItem(requestIdStorageKey(applicationId), request_id)
      } catch {
        // best-effort — polling still works this session even if it can't persist
      }
      setStatusRow(null)
      setRequestId(request_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to submit the request.')
    } finally {
      setSubmitting(false)
    }
  }

  const status = statusRow?.status
  const inProgress = status != null && !TERMINAL_STATUSES.has(status)
  const testCaseCount = statusRow?.generated_tests.length ?? 0

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
            Author a test case in plain language
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 4 }}>
            Describe what should be tested. Vantage explores the live application, writes the test case and
            adds it to this suite.
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          style={{
            width: 28,
            height: 28,
            flexShrink: 0,
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

      {!requestId && (
        <form onSubmit={handleSubmit} style={{ marginTop: 16 }}>
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Describe what should happen in the application — the steps to take and what to check."
            rows={4}
            style={{
              width: '100%',
              boxSizing: 'border-box',
              padding: '11px 13px',
              border: '1px solid var(--border-2)',
              borderRadius: 9,
              fontSize: 13,
              color: 'var(--fg-1)',
              background: 'var(--panel-2)',
              fontFamily: 'inherit',
              resize: 'vertical',
              outline: 'none',
            }}
          />

          {error && <div style={{ color: 'var(--bad)', fontSize: 13, marginTop: 8 }}>{error}</div>}

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }}>
            <button
              type="submit"
              disabled={submitting || !prompt.trim()}
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
                background: submitting || !prompt.trim() ? 'var(--fg-4)' : 'var(--accent)',
                boxShadow: submitting || !prompt.trim() ? 'none' : 'var(--accent-glow)',
                cursor: submitting || !prompt.trim() ? 'default' : 'pointer',
              }}
            >
              <FontAwesomeIcon icon={faWandMagicSparkles} style={{ fontSize: 11 }} />
              {submitting ? 'Submitting…' : 'Explore and generate'}
            </button>
            <span style={{ fontSize: 10.5, color: 'var(--fg-4)' }}>
              No prior discovery is needed — a live agent explores the application itself.
            </span>
          </div>
        </form>
      )}

      {inProgress && status && <GenerationLoader icon={Sparkles} title={IN_PROGRESS_COPY[status] ?? 'Working…'} />}

      {status === 'rejected' && (
        <div style={{ marginTop: 16 }}>
          <p style={{ color: 'var(--bad)', fontSize: 13.5, margin: '0 0 12px' }}>
            {statusRow?.rejection_reason || "That doesn't look like a test case request for this application."}
          </p>
          <button type="button" onClick={reset} style={secondaryButtonStyle}>
            Try again
          </button>
        </div>
      )}

      {status === 'complete' && (
        <div style={{ marginTop: 16 }}>
          {statusRow?.journey_name && (
            <p style={{ fontSize: 13, color: 'var(--fg-4)', margin: '0 0 10px' }}>
              Journey: {statusRow.journey_name}
            </p>
          )}
          <p style={{ fontSize: 13.5, color: 'var(--fg)', margin: 0 }}>
            {testCaseCount > 0
              ? `${testCaseCount} test case${testCaseCount === 1 ? '' : 's'} added to the suite.`
              : 'Test case added to the suite.'}{' '}
            Run them from the Test Suite tab to see results.
          </p>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-2)', marginTop: 16, paddingTop: 14 }}>
            <button
              type="button"
              onClick={reset}
              style={{ background: 'none', border: 'none', color: 'var(--accent)', fontWeight: 600, fontSize: 13, cursor: 'pointer', padding: 0 }}
            >
              + Explore another
            </button>
            <button type="button" onClick={onClose} style={secondaryButtonStyle}>
              Close
            </button>
          </div>
        </div>
      )}

      {status === 'failed' && (
        <div style={{ marginTop: 16 }}>
          <p style={{ color: 'var(--bad)', fontSize: 13.5, margin: '0 0 8px' }}>Something went wrong during live exploration.</p>
          {statusRow?.error_message && (
            <p style={{ fontSize: 13, color: 'var(--fg-4)', margin: '0 0 12px' }}>{statusRow.error_message}</p>
          )}
          <button type="button" onClick={reset} style={secondaryButtonStyle}>
            Try again
          </button>
        </div>
      )}
    </div>
  )
}
