import { useEffect, useState } from 'react'
import { ApiError, api } from '../../api'
import type { LiveTestCaseRequestStatusRead, LiveTestCaseScenarioResultRead } from '../../api'
import { GenerationLoader } from '../GenerationLoader'

const POLL_INTERVAL_MS = 3000
const TERMINAL_STATUSES = new Set(['complete', 'failed', 'rejected'])

// Persisted so a page refresh, or closing and reopening this panel, can
// reconnect to an already-running request instead of losing it — the
// backend workflow keeps going regardless of whether anything is polling it.
function requestIdStorageKey(applicationId: string) {
  return `live-exploration-request:${applicationId}`
}

const IN_PROGRESS_COPY: Record<string, string> = {
  exploring: 'Exploring the live application…',
  generating: 'Generating the test case…',
  running: 'Running the test case…',
}

function ResultRow({ result }: { result: LiveTestCaseScenarioResultRead }) {
  const passed = result.test_result_status === 'passed'
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 0' }}>
      <span
        aria-hidden="true"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 20,
          height: 20,
          marginTop: 1,
          borderRadius: 'var(--radius-full)',
          background: passed ? 'var(--good-strong)' : 'var(--danger-strong)',
          color: 'white',
          fontSize: 12,
          fontWeight: 700,
          flexShrink: 0,
        }}
      >
        {passed ? '✓' : '!'}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={{
            fontSize: 12,
            color: passed ? 'var(--good-strong)' : 'var(--danger-strong)',
            fontWeight: 600,
            margin: 0,
          }}
        >
          {result.test_result_status ?? 'unknown'}
          {result.healed ? ' · healed via live re-exploration' : ''}
        </p>
        {result.error_message && (
          <p style={{ fontSize: 12.5, color: 'var(--ink-muted)', margin: '2px 0 0' }}>{result.error_message}</p>
        )}
      </div>
    </div>
  )
}

// The Natural Language tile's second entry point (AuthoringTab.tsx) — works
// even on a brand-new application with zero Discovery/TestSuite history: a
// live agent explores the real application itself (Playwright MCP + an LLM
// deciding each step) to accomplish the requirement, then generates and runs
// a test case grounded in exactly what it found. See
// `LiveExplorationTestWorkflow` (packages/workflows) for the full flow.
export function LiveExplorationPanel({
  applicationId,
  onClose,
}: {
  applicationId: string
  onClose: () => void
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
        if (!cancelled) setStatusRow(row)
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
  const results = statusRow?.results ?? []

  return (
    <div
      style={{
        background: 'var(--canvas)',
        borderRadius: 'var(--radius-xl)',
        boxShadow: 'var(--shadow-card)',
        padding: '28px 24px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: 'var(--ink)' }}>Explore live</h3>
        <button
          type="button"
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: 'var(--ink-muted)', cursor: 'pointer', fontSize: 13, padding: 0 }}
        >
          Close
        </button>
      </div>

      {!requestId && (
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span className="label">Test case</span>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder='Describe what to do in the real application, e.g. "Create a new MCP connection for a tenant and verify it appears in the list." No prior discovery data is needed — a live agent explores the application itself.'
              rows={6}
              style={{ resize: 'vertical' }}
            />
          </label>

          {error && <div style={{ color: 'var(--danger)', fontSize: 13, marginTop: 8 }}>{error}</div>}
          <button type="submit" className="button-primary" disabled={submitting || !prompt.trim()} style={{ marginTop: 14 }}>
            {submitting ? 'Submitting…' : 'Explore and generate'}
          </button>
        </form>
      )}

      {inProgress && status && <GenerationLoader title={IN_PROGRESS_COPY[status] ?? 'Working…'} />}

      {status === 'rejected' && (
        <div>
          <p style={{ color: 'var(--danger)', fontSize: 14 }}>
            {statusRow?.rejection_reason || "That doesn't look like a test case request for this application."}
          </p>
          <button type="button" className="button-secondary" onClick={reset}>
            Try again
          </button>
        </div>
      )}

      {status === 'complete' && (
        <div>
          {statusRow?.journey_name && (
            <p style={{ fontSize: 13, color: 'var(--ink-muted)', marginBottom: 10 }}>
              Journey: {statusRow.journey_name}
            </p>
          )}
          {results.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--ink-muted)' }}>
              No scenarios were executed.
            </p>
          ) : (
            results.map((result, i) => (
              <div key={result.scenario_id} style={{ borderTop: i > 0 ? '1px solid var(--border)' : undefined }}>
                <ResultRow result={result} />
              </div>
            ))
          )}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border)', marginTop: 16, paddingTop: 14 }}>
            <button
              type="button"
              onClick={reset}
              style={{ background: 'none', border: 'none', color: 'var(--accent)', fontWeight: 600, fontSize: 13, cursor: 'pointer', padding: 0 }}
            >
              + Explore another
            </button>
            <button type="button" className="button-secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      )}

      {status === 'failed' && (
        <div>
          <p style={{ color: 'var(--danger)', fontSize: 14 }}>Something went wrong during live exploration.</p>
          {statusRow?.error_message && (
            <p style={{ fontSize: 13, color: 'var(--ink-muted)' }}>{statusRow.error_message}</p>
          )}
          <button type="button" className="button-secondary" onClick={reset}>
            Try again
          </button>
        </div>
      )}
    </div>
  )
}
