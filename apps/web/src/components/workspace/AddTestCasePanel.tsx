import { useEffect, useState } from 'react'
import { ApiError, api } from '../../api'
import type { TestCaseGenerationResultRead, TestCaseRequestStatusRead } from '../../api'
import { GenerationLoader } from '../GenerationLoader'

const POLL_INTERVAL_MS = 3000
// Terminal — polling stops once the request reaches one of these.
const TERMINAL_STATUSES = new Set(['complete', 'failed', 'rejected'])

// A single prompt can decompose into several test cases (e.g. "test that
// login and logout both work") — `scenario_count` (known once analysis
// finishes) makes that visible instead of a multi-scenario request looking
// identical to a single one while it runs.
function inProgressCopy(status: string, scenarioCount: number): string {
  if (status === 'analyzing') return 'Understanding your request…'
  if (scenarioCount > 1) return `Building and running ${scenarioCount} test cases…`
  return 'Building and running the test case…'
}

// Results view (below) is a presentational pass modeled on a provided design
// reference (tabbed Needs attention/Added/All), refined per explicit product
// feedback: `status` alone answers "was a Scenario + linked test case
// actually created and added to its Suite" — the ONLY question "Needs
// attention" means. A `status="complete"` result is reported as simply
// "Added to Test Suite" regardless of whether its run passed or failed —
// pass/fail-of-run belongs to the Suite/Runs tabs, not this summary. No new
// data and no new actions (no retry/view-log/discard/rerun-discovery — those
// would be new backend functionality, out of scope here) — every field read
// below already existed on `TestCaseGenerationResultRead` (bar `stage`,
// which the workflow now sets alongside `error_message` for exactly this
// display, same non-functional addition as `is_new_journey`).
function resultNeedsAttention(result: TestCaseGenerationResultRead): boolean {
  return result.status !== 'complete'
}

// NLM Matching and Creation Rules — headline + detail lines, checked in this
// exact priority order (an already-existing result can't also be "new", and
// a new-Journey result implies a new Scenario too, so only the first
// matching case applies):
//   1. already_existed   → the exact Test Case was already in the Suite
//   2. is_new_journey    → brand-new Journey (+ Scenario) created for it
//   3. is_new_scenario   → brand-new Scenario under an existing Journey
//   4. (none of the above) → an existing Scenario was matched/reused and
//      this was its first Test Case generated
function addedDisplay(result: TestCaseGenerationResultRead): { headline: string; details: string[] } {
  if (result.already_existed) {
    return {
      headline: 'Test case already exists in Test Suite',
      details: result.journey_name ? [`Journey: ${result.journey_name}`] : [],
    }
  }
  if (result.is_new_journey) {
    return {
      headline: 'Test case created',
      details: [
        result.journey_name
          ? `Created under new Journey: ${result.journey_name}`
          : 'Created under a new Journey',
      ],
    }
  }
  if (result.is_new_scenario) {
    return {
      headline: 'Test case created',
      details: [
        result.journey_name
          ? `New Scenario created under Journey: ${result.journey_name}`
          : 'New Scenario created',
      ],
    }
  }
  return {
    headline: 'Test case created',
    details: [
      ...(result.scenario_name ? [`Matched Scenario: ${result.scenario_name}`] : []),
      ...(result.journey_name ? [`Journey: ${result.journey_name}`] : []),
    ],
  }
}

function AddedRow({ result }: { result: TestCaseGenerationResultRead }) {
  const { headline, details } = addedDisplay(result)
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
          background: 'var(--good-strong)',
          color: 'white',
          fontSize: 12,
          fontWeight: 700,
          flexShrink: 0,
        }}
      >
        ✓
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: 12, color: 'var(--good-strong)', fontWeight: 600, margin: 0 }}>{headline}</p>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', marginTop: 2 }}>
          {result.scenario_name ?? 'Untitled test case'}
        </div>
        {details.map((line) => (
          <p key={line} style={{ fontSize: 12.5, color: 'var(--ink-muted)', margin: '2px 0 0' }}>
            {line}
          </p>
        ))}
      </div>
      {result.already_existed && (
        <span
          style={{
            fontSize: 11.5,
            fontWeight: 600,
            color: 'var(--ink-muted)',
            background: 'var(--canvas-wash-alt)',
            borderRadius: 'var(--radius-full)',
            padding: '2px 8px',
            flexShrink: 0,
          }}
        >
          In suite
        </span>
      )}
    </div>
  )
}

function AttentionRow({ result }: { result: TestCaseGenerationResultRead }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10,
        padding: '10px 0',
        flexWrap: 'wrap',
      }}
    >
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
          background: 'var(--danger-strong)',
          color: 'white',
          fontSize: 12,
          fontWeight: 700,
          flexShrink: 0,
        }}
      >
        !
      </span>
      <div style={{ flex: 1, minWidth: 160 }}>
        <p style={{ fontSize: 12, color: 'var(--danger-strong)', fontWeight: 600, margin: 0 }}>
          Could not create test case
        </p>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', marginTop: 2 }}>
          {result.scenario_name ?? 'Untitled test case'}
        </div>
        <p style={{ fontSize: 12.5, color: 'var(--ink-muted)', margin: '2px 0 0' }}>
          {result.error_message ?? 'This test case could not be created.'}
        </p>
      </div>
      {result.stage && (
        <span
          style={{
            fontSize: 11.5,
            fontWeight: 600,
            color: 'var(--danger-strong)',
            background: 'var(--danger-wash)',
            borderRadius: 'var(--radius-full)',
            padding: '2px 10px',
            flexShrink: 0,
            alignSelf: 'center',
          }}
        >
          {result.stage}
        </span>
      )}
    </div>
  )
}

// The Natural Language tile's real flow (AuthoringTab.tsx) — describe a test
// case in plain English, then generate and run it via the same pipeline
// Generate Suite already uses. Everything is prompt-based: there is no
// separate test-data form — mention a concrete value directly in the prompt
// (e.g. "using promo code EXPIRED10") and it's used verbatim; anything not
// mentioned is resolved from the existing Test Data Pool or synthesized
// automatically by the same generator that already fills in test data for
// every normal-flow Scenario — no pause, no follow-up prompt. One
// `request_id` (minted by the create call, not a DB id — see
// `AddTestCaseWorkflow`'s own docstring) is polled until it reaches a
// terminal status; the final result is a LIST (Multiple Test Cases) — one
// entry per Scenario the prompt decomposed into, each independently
// PASS/FAIL.
export function AddTestCasePanel({
  applicationId,
  onClose,
}: {
  applicationId: string
  onClose: () => void
}) {
  const [prompt, setPrompt] = useState('')
  const [requestId, setRequestId] = useState<string | null>(null)
  const [statusRow, setStatusRow] = useState<TestCaseRequestStatusRead | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Tabbed results view (reference design) — which tab is active, and when
  // the request finished (client-side timestamp; nothing server-side tracks
  // this, so it's stamped the moment a terminal status is first observed).
  const [activeTab, setActiveTab] = useState<'attention' | 'added' | 'all'>('attention')
  const [completedAt, setCompletedAt] = useState<Date | null>(null)

  useEffect(() => {
    if (!requestId) return
    let cancelled = false

    async function poll() {
      try {
        const row = await api.getTestCaseRequest(applicationId, requestId as string)
        if (!cancelled) setStatusRow(row)
      } catch {
        // best-effort poll — a transient failure just skips this tick
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
    setRequestId(null)
    setStatusRow(null)
    setPrompt('')
    setError(null)
    setActiveTab('attention')
    setCompletedAt(null)
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!prompt.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const { request_id } = await api.createTestCase(applicationId, prompt.trim())
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
  const needsAttention = results.filter(resultNeedsAttention)
  const added = results.filter((r) => !resultNeedsAttention(r))

  useEffect(() => {
    if (status === 'complete') {
      setCompletedAt((prev) => prev ?? new Date())
      setActiveTab(needsAttention.length > 0 ? 'attention' : 'added')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  const activeResults =
    activeTab === 'attention' ? needsAttention : activeTab === 'added' ? added : results
  // Title mirrors the reference design's static "Add Test Cases" heading
  // once the request lands — every other state keeps the original label.
  const heading = status === 'complete' ? 'Add Test Cases' : 'Add a test case'

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
        <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: 'var(--ink)' }}>{heading}</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {completedAt && (
            <span style={{ fontSize: 12.5, color: 'var(--ink-muted)' }}>
              Generation finished ·{' '}
              {completedAt.toLocaleString(undefined, {
                day: 'numeric',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          )}
          <button
            type="button"
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--ink-muted)', cursor: 'pointer', fontSize: 13, padding: 0 }}
          >
            Close
          </button>
        </div>
      </div>

      {!requestId && (
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span className="label">Test case</span>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder='Describe the test case in plain English, e.g. "Verify that applying the promo code EXPIRED10 at checkout shows an error and does not change the total." — mention any specific data you want used directly in the sentence; anything not mentioned is filled in automatically.'
              rows={6}
              style={{ resize: 'vertical' }}
            />
          </label>

          {error && <div style={{ color: 'var(--danger)', fontSize: 13, marginTop: 8 }}>{error}</div>}
          <button type="submit" className="button-primary" disabled={submitting || !prompt.trim()} style={{ marginTop: 14 }}>
            {submitting ? 'Submitting…' : 'Generate test case'}
          </button>
        </form>
      )}

      {inProgress && status && (
        <GenerationLoader
          title={inProgressCopy(status, statusRow?.scenario_count ?? 0)}
          caption={
            statusRow?.functionality_summary ? (
              <p style={{ fontSize: 13, color: 'var(--ink-muted)', marginTop: 4 }}>{statusRow.functionality_summary}</p>
            ) : undefined
          }
        />
      )}

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
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>
              {results.length} generated
            </span>
            {added.length > 0 && (
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--good-strong)',
                  background: 'var(--good-wash)',
                  borderRadius: 'var(--radius-full)',
                  padding: '3px 10px',
                }}
              >
                {added.length} added
              </span>
            )}
            {needsAttention.length > 0 && (
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--danger-strong)',
                  background: 'var(--danger-wash)',
                  borderRadius: 'var(--radius-full)',
                  padding: '3px 10px',
                }}
              >
                {needsAttention.length} needs attention
              </span>
            )}
          </div>

          {/* Tabs — same flat result list as before, just switched between
              instead of always shown stacked. */}
          <div style={{ display: 'flex', gap: 20, borderBottom: '1px solid var(--border)', marginBottom: 4 }}>
            {(
              [
                ['attention', `Needs attention (${needsAttention.length})`],
                ['added', `Added (${added.length})`],
                ['all', `All (${results.length})`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setActiveTab(key)}
                style={{
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === key ? '2px solid var(--accent)' : '2px solid transparent',
                  color: activeTab === key ? 'var(--accent)' : 'var(--ink-muted)',
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: 'pointer',
                  padding: '0 0 10px',
                }}
              >
                {label}
              </button>
            ))}
          </div>

          {activeResults.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--ink-muted)', padding: '14px 0' }}>Nothing here.</p>
          ) : (
            activeResults.map((result, i) => (
              <div key={i} style={{ borderTop: i > 0 ? '1px solid var(--border)' : undefined }}>
                {resultNeedsAttention(result) ? (
                  <AttentionRow result={result} />
                ) : (
                  <AddedRow result={result} />
                )}
              </div>
            ))
          )}

          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              borderTop: '1px solid var(--border)',
              marginTop: 16,
              paddingTop: 14,
            }}
          >
            <button
              type="button"
              onClick={reset}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--accent)',
                fontWeight: 600,
                fontSize: 13,
                cursor: 'pointer',
                padding: 0,
              }}
            >
              + Add another test case
            </button>
            <button type="button" className="button-secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      )}

      {status === 'failed' && (
        <div>
          <p style={{ color: 'var(--danger)', fontSize: 14 }}>
            Something went wrong while generating this test case.
          </p>
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
