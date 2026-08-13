import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  api,
  type TestResultArtifactRead,
  type TestResultRead,
  type TestRunRead,
} from '../../api'
import { StatTile } from '../TestSuiteResults'
import { StatusPill } from '../StatusPill'

const POLL_INTERVAL_MS = 1500
const RUNS_PER_PAGE = 10

function ClipboardCheckIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
      <rect x={9} y={3} width={6} height={4} rx={1} />
      <path d="M9 12l2 2 4-4" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 13l4 4L19 7" />
    </svg>
  )
}

function XIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={12} r={9} />
      <path d="M12 7v5l3.5 3.5" />
    </svg>
  )
}

function AlertIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 9v4M12 17h.01" />
      <path d="M10.3 3.6 2.5 17a1.8 1.8 0 0 0 1.5 2.7h16a1.8 1.8 0 0 0 1.5-2.7L13.7 3.6a1.8 1.8 0 0 0-3.4 0z" />
    </svg>
  )
}

const NON_PASSED_STATUSES = new Set(['failed', 'timed_out', 'errored'])

export function ArtifactsModal({ testResult, onClose }: { testResult: TestResultRead; onClose: () => void }) {
  const [artifacts, setArtifacts] = useState<TestResultArtifactRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .listTestResultArtifacts(testResult.id)
      .then((rows) => {
        if (!cancelled) setArtifacts(rows)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : 'Failed to load artifacts')
      })
    return () => {
      cancelled = true
    }
  }, [testResult.id])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${testResult.scenario_name} artifacts`}
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,23,42,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--canvas)',
          borderRadius: 'var(--radius)',
          width: 'min(560px, 92vw)',
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '12px 16px',
            borderBottom: '1px solid var(--border-hairline)',
          }}
        >
          <span style={{ color: 'var(--ink)', fontSize: 13, fontWeight: 600 }}>
            {testResult.scenario_name} — failure artifacts
          </span>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--ink-muted)',
              cursor: 'pointer',
              fontSize: 16,
              lineHeight: 1,
              padding: 4,
            }}
          >
            ✕
          </button>
        </div>
        <div style={{ padding: 20, overflow: 'auto' }}>
          {testResult.error_message && (
            <pre
              style={{
                margin: '0 0 16px',
                padding: 12,
                background: 'var(--canvas-wash)',
                border: '1px solid var(--border-hairline)',
                borderRadius: 'var(--radius)',
                fontSize: 12,
                lineHeight: 1.6,
                color: 'var(--danger-strong)',
                fontFamily: "'SFMono-Regular',Consolas,monospace",
                whiteSpace: 'pre-wrap',
                overflow: 'auto',
                maxHeight: 200,
              }}
            >
              {testResult.error_message}
            </pre>
          )}
          {loadError && <p style={{ color: 'var(--danger-strong)', fontSize: 13 }}>{loadError}</p>}
          {artifacts === null && !loadError && <p className="caption">Loading artifacts…</p>}
          {artifacts !== null && artifacts.length === 0 && (
            <p className="caption">No screenshot or trace was captured for this failure.</p>
          )}
          {artifacts !== null && artifacts.length > 0 && (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {artifacts.map((artifact) => (
                <li key={artifact.id}>
                  <a
                    href={artifact.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: 13, color: 'var(--accent)', fontWeight: 600 }}
                  >
                    {artifact.artifact_type === 'trace' ? 'Playwright trace' : 'Screenshot'} (
                    {Math.max(1, Math.round(artifact.size_bytes / 1024))} KB)
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

function TestResultRow({ result }: { result: TestResultRead }) {
  const [artifactsFor, setArtifactsFor] = useState<TestResultRead | null>(null)
  const canShowArtifacts = NON_PASSED_STATUSES.has(result.status)

  return (
    <div
      className="list-row"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        padding: '10px 14px',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {result.scenario_name}
        </div>
        {result.status === 'blocked' && result.blocked_reason && (
          <div className="caption" style={{ fontSize: 11.5, marginTop: 2 }}>
            {result.blocked_reason}
          </div>
        )}
        {canShowArtifacts && result.error_message && (
          <div style={{ fontSize: 11.5, color: 'var(--danger-strong)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {result.error_message}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
        {result.duration_ms != null && (
          <span className="caption" style={{ fontSize: 11.5, whiteSpace: 'nowrap' }}>
            {(result.duration_ms / 1000).toFixed(1)}s
          </span>
        )}
        <StatusPill status={result.status} />
        {canShowArtifacts && (
          <button type="button" className="button-secondary" onClick={() => setArtifactsFor(result)}>
            Artifacts
          </button>
        )}
      </div>
      {artifactsFor && <ArtifactsModal testResult={artifactsFor} onClose={() => setArtifactsFor(null)} />}
    </div>
  )
}

// `StatusPill`'s shared LABELS map says "Discovery in Progress" for the
// bare string "running" — correct for Application discovery, wrong for a
// running TestRun. Only `running` needs the override; pending/completed/
// blocked are already worded correctly for both domains.
function testRunStatusLabel(status: string): string | undefined {
  return status === 'running' ? 'Running' : undefined
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function RunDetail({ run, onBack }: { run: TestRunRead; onBack: () => void }) {
  const isRunning = run.status === 'pending' || run.status === 'running'

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <button
            type="button"
            onClick={onBack}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--accent)',
              fontSize: 12.5,
              fontWeight: 600,
              cursor: 'pointer',
              padding: 0,
              marginBottom: 8,
            }}
          >
            ← All Runs
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <StatusPill status={run.status} label={testRunStatusLabel(run.status)} />
            <span className="caption" style={{ fontSize: 12.5 }}>
              {run.trigger} · {formatDateTime(run.created_at)}
            </span>
          </div>
        </div>
      </div>

      {run.status === 'blocked' && (
        <div className="card-panel" style={{ padding: '16px 20px', marginBottom: 20, borderColor: 'var(--warn-strong)' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--warn-strong)', marginBottom: 4 }}>
            Execution blocked
          </div>
          <div style={{ fontSize: 13, color: 'var(--ink-secondary)' }}>{run.blocked_reason}</div>
        </div>
      )}

      {run.status !== 'blocked' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 20 }}>
          <StatTile icon={<ClipboardCheckIcon />} value={run.total_count} label="Total" />
          <StatTile icon={<CheckIcon />} value={run.passed_count} label="Passed" />
          <StatTile icon={<XIcon />} value={run.failed_count} label="Failed" />
          <StatTile icon={<ClockIcon />} value={run.timed_out_count} label="Timed out" />
          <StatTile icon={<AlertIcon />} value={run.errored_count + run.blocked_count} label="Errored/Skipped" />
        </div>
      )}

      {isRunning && run.results == null && (
        <p className="caption" style={{ fontSize: 12.5 }}>
          Running tests — this list fills in as each test finishes.
        </p>
      )}

      {run.results && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {run.results.map((result) => (
            <TestResultRow key={result.id} result={result} />
          ))}
        </div>
      )}
    </div>
  )
}

function RunListRow({ run, onOpen }: { run: TestRunRead; onOpen: () => void }) {
  return (
    <div
      role="button"
      tabIndex={0}
      className="list-row"
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onOpen()
      }}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        padding: '12px 16px',
        cursor: 'pointer',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>{formatDateTime(run.created_at)}</div>
        <div className="caption" style={{ fontSize: 11.5, marginTop: 2 }}>
          {run.trigger}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 }}>
        <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
          {run.pass_rate != null ? `${Math.round(run.pass_rate * 100)}% pass` : '—'}
        </span>
        <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
          {run.passed_count}/{run.total_count} results
        </span>
        <StatusPill status={run.status} label={testRunStatusLabel(run.status)} />
      </div>
    </div>
  )
}

export function RunsTab({
  applicationId,
  autoSelectLatest,
  onAutoSelectConsumed,
}: {
  applicationId: string
  // `triggerTestRun` starts a Temporal workflow fire-and-forget and only
  // returns `{started: boolean}` — no run id — so "land on the run that
  // was just started" means polling the newest-first list until it shows
  // up, not selecting a known id directly.
  autoSelectLatest?: boolean
  // Called once the newest run has been auto-selected, so the parent can
  // clear its own flag — otherwise remounting this tab later (navigating
  // away and back with no fresh run triggered) would re-arm auto-select
  // and hijack a deliberate return to the run list.
  onAutoSelectConsumed?: () => void
}) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [selectedRun, setSelectedRun] = useState<TestRunRead | null>(null)
  const [runs, setRuns] = useState<TestRunRead[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const autoSelectPendingRef = useRef(!!autoSelectLatest)
  const totalPages = Math.max(1, Math.ceil(total / RUNS_PER_PAGE))
  // "Latest ref" pattern — `onAutoSelectConsumed` is a fresh arrow function
  // from Workspace on every render, so calling it via a ref rather than
  // depending on it directly keeps the polling effect below from tearing
  // down and restarting on every unrelated Workspace re-render.
  const onAutoSelectConsumedRef = useRef(onAutoSelectConsumed)
  onAutoSelectConsumedRef.current = onAutoSelectConsumed

  useEffect(() => {
    if (selectedRunId) return
    let cancelled = false
    let interval: ReturnType<typeof setInterval> | undefined

    async function load() {
      try {
        const body = await api.listTestRuns(applicationId, page + 1, RUNS_PER_PAGE)
        if (cancelled) return
        setRuns(body.items)
        setTotal(body.total)
        if (autoSelectPendingRef.current && page === 0 && body.items.length > 0) {
          autoSelectPendingRef.current = false
          setSelectedRunId(body.items[0].id)
          onAutoSelectConsumedRef.current?.()
        }
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
    }

    load()
    if (autoSelectPendingRef.current) {
      interval = setInterval(load, POLL_INTERVAL_MS)
    }
    return () => {
      cancelled = true
      if (interval) clearInterval(interval)
    }
  }, [applicationId, page, selectedRunId])

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null)
      return
    }
    let cancelled = false
    let interval: ReturnType<typeof setInterval> | undefined

    async function poll() {
      try {
        const detail = await api.getTestRun(applicationId, selectedRunId!)
        if (cancelled) return
        setSelectedRun(detail)
        if ((detail.status === 'completed' || detail.status === 'blocked') && interval) {
          clearInterval(interval)
        }
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
    }

    poll()
    interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      if (interval) clearInterval(interval)
    }
  }, [applicationId, selectedRunId])

  if (selectedRunId) {
    return selectedRun ? (
      <RunDetail run={selectedRun} onBack={() => setSelectedRunId(null)} />
    ) : (
      <p className="caption" style={{ fontSize: 12.5 }}>
        Loading run…
      </p>
    )
  }

  return (
    <div>
      {runs.length === 0 ? (
        <p className="caption" style={{ fontSize: 13 }}>
          No test runs yet — use "Run Suite" from the Test Suite tab to start one.
        </p>
      ) : (
        <div
          className="card-panel"
          style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
        >
          {runs.map((run) => (
            <div key={run.id} style={{ borderBottom: '1px solid var(--border-hairline)' }}>
              <RunListRow run={run} onOpen={() => setSelectedRunId(run.id)} />
            </div>
          ))}
          {totalPages > 1 && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 'var(--space-3)',
                padding: 'var(--space-4) var(--space-5)',
              }}
            >
              <button
                type="button"
                className="button-secondary"
                disabled={page <= 0}
                onClick={() => setPage((p) => p - 1)}
              >
                Prev
              </button>
              <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                Page {page + 1} of {totalPages}
              </span>
              <button
                type="button"
                className="button-secondary"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
