import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError,
  api,
  type TestResultArtifactRead,
  type TestResultRead,
  type TestRunRead,
} from '../../api'
import { StatTile } from '../TestSuiteResults'
import { StatusPill } from '../StatusPill'
import { ServiceErrorNote } from '../ServiceError'
import { Pagination } from '../Pagination'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'

const POLL_INTERVAL_MS = 1500
const RUNS_PER_PAGE = 5
const RESULTS_PER_PAGE = 5

// Same arrow-left glyph as TopBar's own back button, not a text "←" glyph.
function BackIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </svg>
  )
}

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

function runSignalColor(run: TestRunRead): string {
  if (run.status === 'blocked') return 'var(--warn)'
  if (run.status === 'pending' || run.status === 'running') return 'var(--accent)'
  if (run.pass_rate == null) return 'var(--border-strong)'
  if (run.pass_rate >= 0.9) return 'var(--good)'
  if (run.pass_rate >= 0.7) return 'var(--warn)'
  return 'var(--danger)'
}

export function ArtifactsModal({ testResult, onClose }: { testResult: TestResultRead; onClose: () => void }) {
  useEscapeToClose(onClose)
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

const columnHeaderLabelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--ink-faint)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  whiteSpace: 'nowrap',
}

// Same CSS Grid technique as TestSuiteTab.tsx's `ASSET_GRID_TEMPLATE` for
// the same "Test Case / Duration / Status" shape — one shared template on
// both the header and every row, not flex + matched `minWidth`s (the
// previous approach here). That approach broke the moment a row's
// right-hand group had a different number of children than another row's:
// the "Artifacts" button only renders for non-passed rows, so a passed
// row's Duration/Status sat at a different position than a failed row's,
// which sat different again from the header. A dedicated Actions column
// (present, just empty, on every row) fixes Duration/Status in place
// regardless of whether Artifacts renders — and lines this list up with
// the Test Suite tab's, since it's the same shape.
const RESULT_GRID_TEMPLATE = '1fr 70px 130px 100px'
// Runs table columns (RunListHeader/RunListRow) use percentages, not px —
// `table-layout: fixed` + `width: 100%` on `.data-table` means these scale
// with the table instead of leaving it stuck at a fixed pixel sum. Date &
// Time gets the biggest share (30%); the rest split what's left, and Status
// stays unwidthed so it alone absorbs any remainder.
const DATE_COL_WIDTH = '30%'
const TRIGGERED_BY_COL_WIDTH = '16%'
const PASS_RATE_COL_WIDTH = '10%'
const PASSED_COL_WIDTH = '12%'
const FAILED_COL_WIDTH = '12%'
const RUN_DURATION_COL_WIDTH = '10%'

// Same "Test Case" / "Duration" / "Status" columns as the Test Suite tab's
// asset list (TestSuiteTab.tsx) — a failing test case reads the same way in
// both places, so correlating one against the other doesn't require
// re-learning the layout.
type ResultSortKey = 'name' | 'duration' | 'status'

function resultSortValue(result: TestResultRead, key: ResultSortKey): string | number {
  switch (key) {
    case 'name':
      return result.scenario_name.toLowerCase()
    case 'duration':
      return result.duration_ms ?? -1
    case 'status':
      return result.status
  }
}

function sortResults(results: TestResultRead[], key: ResultSortKey, dir: 'asc' | 'desc'): TestResultRead[] {
  const sorted = [...results].sort((a, b) => {
    const av = resultSortValue(a, key)
    const bv = resultSortValue(b, key)
    if (av < bv) return -1
    if (av > bv) return 1
    return 0
  })
  return dir === 'asc' ? sorted : sorted.reverse()
}

function SortableColumnLabel({
  label,
  sortKey,
  activeKey,
  dir,
  onSort,
  align,
}: {
  label: string
  sortKey: ResultSortKey
  activeKey: ResultSortKey | null
  dir: 'asc' | 'desc'
  onSort: (key: ResultSortKey) => void
  align?: 'right'
}) {
  const isActive = sortKey === activeKey
  return (
    <span
      onClick={() => onSort(sortKey)}
      style={{ ...columnHeaderLabelStyle, textAlign: align, cursor: 'pointer', userSelect: 'none' }}
    >
      {label}
      {isActive ? (dir === 'asc' ? ' ▲' : ' ▼') : ''}
    </span>
  )
}

function ResultListHeader({
  sortKey,
  sortDir,
  onSort,
}: {
  sortKey: ResultSortKey | null
  sortDir: 'asc' | 'desc'
  onSort: (key: ResultSortKey) => void
}) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: RESULT_GRID_TEMPLATE,
        alignItems: 'center',
        gap: 12,
        padding: '8px 16px',
        background: 'var(--canvas-wash-alt)',
        borderBottom: '1px solid var(--border-hairline)',
      }}
    >
      <SortableColumnLabel label="Test Case" sortKey="name" activeKey={sortKey} dir={sortDir} onSort={onSort} />
      <SortableColumnLabel
        label="Duration"
        sortKey="duration"
        activeKey={sortKey}
        dir={sortDir}
        onSort={onSort}
        align="right"
      />
      <SortableColumnLabel label="Status" sortKey="status" activeKey={sortKey} dir={sortDir} onSort={onSort} />
      <span aria-hidden="true" />
    </div>
  )
}

function TestResultRow({ result, isCurrentlyRunning }: { result: TestResultRead; isCurrentlyRunning?: boolean }) {
  const [artifactsFor, setArtifactsFor] = useState<TestResultRead | null>(null)
  const canShowArtifacts = NON_PASSED_STATUSES.has(result.status)

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: RESULT_GRID_TEMPLATE,
        alignItems: 'center',
        gap: 12,
        padding: '10px 16px',
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
      <span className="caption" style={{ fontSize: 11.5, whiteSpace: 'nowrap', textAlign: 'right' }}>
        {result.duration_ms != null ? `${(result.duration_ms / 1000).toFixed(1)}s` : ''}
      </span>
      {/* No distinct "running" status exists on a TestResult row (it only
          ever moves pending -> a terminal status) — the one test actually
          executing right now is inferred as the first still-pending row
          once finished ones are sorted to the top. */}
      <span>
        <StatusPill status={result.status} label={isCurrentlyRunning ? 'Running' : undefined} pulsing={isCurrentlyRunning} />
      </span>
      <span style={{ textAlign: 'right' }}>
        {canShowArtifacts && (
          <button type="button" className="button-secondary" onClick={() => setArtifactsFor(result)}>
            Artifacts
          </button>
        )}
      </span>
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

// Runs table's Date & Time column: one line, but with the timezone
// abbreviation appended — a bare "6:42 AM" is ambiguous once a run and
// its viewer aren't in the same zone.
function formatDateTimeWithZone(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  })
}

// `TestRunRead` has no `duration_ms` of its own (unlike a TestResult) —
// derived from `started_at`/`completed_at` instead, both already on the row.
function runDurationMs(run: TestRunRead): number | null {
  if (!run.started_at || !run.completed_at) return null
  return new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '—'
  const totalSeconds = Math.round(ms / 1000)
  if (totalSeconds < 60) return `${totalSeconds}s`
  return `${Math.floor(totalSeconds / 60)}m ${totalSeconds % 60}s`
}

function RunDetail({
  run,
  onBack,
  executionUnavailable,
}: {
  run: TestRunRead
  onBack: () => void
  executionUnavailable: boolean
}) {
  const isRunning = run.status === 'pending' || run.status === 'running'
  const [resultsPage, setResultsPage] = useState(0)
  const [resultSortKey, setResultSortKey] = useState<ResultSortKey | null>(null)
  const [resultSortDir, setResultSortDir] = useState<'asc' | 'desc'>('asc')
  const results = run.results ?? []
  const runningResultId = run.status === 'running' ? results.find((r) => r.status === 'pending')?.id : undefined
  // Finished (passed/failed/etc.) first, still-pending ones last — each
  // group keeps its original request order (stable sort on one boolean).
  // Only the default order, used until the viewer picks a column to sort by.
  const orderedResults = resultSortKey
    ? sortResults(results, resultSortKey, resultSortDir)
    : [...results].sort((a, b) => (a.status === 'pending' ? 1 : 0) - (b.status === 'pending' ? 1 : 0))
  const resultsTotalPages = Math.max(1, Math.ceil(orderedResults.length / RESULTS_PER_PAGE))
  const pagedResults = orderedResults.slice(
    resultsPage * RESULTS_PER_PAGE,
    resultsPage * RESULTS_PER_PAGE + RESULTS_PER_PAGE,
  )
  function handleResultSort(key: ResultSortKey) {
    if (key === resultSortKey) {
      setResultSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setResultSortKey(key)
      setResultSortDir('asc')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <button
            type="button"
            className="button-secondary"
            onClick={onBack}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 8 }}
          >
            <BackIcon />
            All Runs
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
        <div className="card-panel" style={{ padding: '16px 20px', marginBottom: 20, borderColor: 'var(--warn-wash-border)' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--warn-strong)', marginBottom: 4 }}>
            Execution blocked
          </div>
          <div style={{ fontSize: 13, color: 'var(--ink-secondary)' }}>{run.blocked_reason}</div>
        </div>
      )}

      {run.status !== 'blocked' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 20 }}>
          <StatTile icon={<ClipboardCheckIcon />} value={run.total_count} label="Total" tone="muted" />
          <StatTile icon={<CheckIcon />} value={run.passed_count} label="Passed" tone="good" />
          <StatTile icon={<XIcon />} value={run.failed_count} label="Failed" tone="danger" />
          <StatTile icon={<ClockIcon />} value={run.timed_out_count} label="Timed out" tone="warn" />
          <StatTile icon={<AlertIcon />} value={run.errored_count + run.blocked_count} label="Errored/Skipped" tone="warn" />
        </div>
      )}

      {isRunning && executionUnavailable && <ServiceErrorNote code="EXECUTION_UNAVAILABLE" />}

      {isRunning && !executionUnavailable && run.results == null && (
        <p className="caption" style={{ fontSize: 12.5 }}>
          Running tests — this list fills in as each test finishes.
        </p>
      )}

      {run.results && results.length > 0 && (
        <div className="card-panel" style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <ResultListHeader sortKey={resultSortKey} sortDir={resultSortDir} onSort={handleResultSort} />
          {pagedResults.map((result) => (
            <div key={result.id} style={{ borderBottom: '1px solid var(--border-hairline)' }}>
              <TestResultRow result={result} isCurrentlyRunning={result.id === runningResultId} />
            </div>
          ))}
          <Pagination
            page={resultsPage}
            totalPages={resultsTotalPages}
            totalItems={orderedResults.length}
            pageSize={RESULTS_PER_PAGE}
            onPrev={() => setResultsPage((p) => p - 1)}
            onNext={() => setResultsPage((p) => p + 1)}
            onPage={setResultsPage}
          />
        </div>
      )}
    </div>
  )
}

// Backend only ever produces "Manual run" / "Manual run by {name}" (see
// `_to_test_run_read` in api/main.py).
function parseTrigger(trigger: string): { by: string } {
  const match = trigger.match(/^Manual run by (.+)$/)
  return { by: match ? match[1] : '—' }
}

type SortKey = 'date' | 'triggeredBy' | 'passRate' | 'passed' | 'failed' | 'duration' | 'status'

function sortValue(run: TestRunRead, key: SortKey): string | number {
  switch (key) {
    case 'date':
      return run.created_at
    case 'triggeredBy':
      return parseTrigger(run.trigger).by.toLowerCase()
    case 'passRate':
      return run.pass_rate ?? -1
    case 'passed':
      return run.passed_count
    case 'failed':
      return run.failed_count
    case 'duration':
      return runDurationMs(run) ?? -1
    case 'status':
      return run.status
  }
}

// Sorts only the currently-loaded page — the list API has no `sort` param,
// and re-sorting across pages would mean fetching every page up front.
function sortRuns(runs: TestRunRead[], key: SortKey, dir: 'asc' | 'desc'): TestRunRead[] {
  const sorted = [...runs].sort((a, b) => {
    const av = sortValue(a, key)
    const bv = sortValue(b, key)
    if (av < bv) return -1
    if (av > bv) return 1
    return 0
  })
  return dir === 'asc' ? sorted : sorted.reverse()
}

function SortableTh({
  label,
  sortKey,
  activeKey,
  dir,
  onSort,
  width,
  align,
}: {
  label: string
  sortKey: SortKey
  activeKey: SortKey
  dir: 'asc' | 'desc'
  onSort: (key: SortKey) => void
  // Omitted only for the last column — under `table-layout: fixed`, every
  // other column holds exactly the width it's given (px or %), and the one
  // column left without a width absorbs whatever space remains instead of
  // the browser stretching all of them proportionally to fill the row.
  width?: number | string
  align?: 'left' | 'right'
}) {
  const isActive = sortKey === activeKey
  return (
    <th
      className="sortable"
      onClick={() => onSort(sortKey)}
      style={{ ...columnHeaderLabelStyle, width, textAlign: align ?? 'left' }}
    >
      {label}
      {isActive ? (dir === 'asc' ? ' ▲' : ' ▼') : ''}
    </th>
  )
}

function RunListHeader({
  sortKey,
  sortDir,
  onSort,
}: {
  sortKey: SortKey
  sortDir: 'asc' | 'desc'
  onSort: (key: SortKey) => void
}) {
  return (
    <thead>
      <tr>
        <SortableTh label="Date & Time" sortKey="date" activeKey={sortKey} dir={sortDir} onSort={onSort} width={DATE_COL_WIDTH} />
        <SortableTh
          label="Triggered By"
          sortKey="triggeredBy"
          activeKey={sortKey}
          dir={sortDir}
          onSort={onSort}
          width={TRIGGERED_BY_COL_WIDTH}
        />
        <SortableTh
          label="Pass Rate"
          sortKey="passRate"
          activeKey={sortKey}
          dir={sortDir}
          onSort={onSort}
          width={PASS_RATE_COL_WIDTH}
          align="right"
        />
        <SortableTh
          label="Passed"
          sortKey="passed"
          activeKey={sortKey}
          dir={sortDir}
          onSort={onSort}
          width={PASSED_COL_WIDTH}
          align="right"
        />
        <SortableTh
          label="Failed"
          sortKey="failed"
          activeKey={sortKey}
          dir={sortDir}
          onSort={onSort}
          width={FAILED_COL_WIDTH}
          align="right"
        />
        <SortableTh
          label="Duration"
          sortKey="duration"
          activeKey={sortKey}
          dir={sortDir}
          onSort={onSort}
          width={RUN_DURATION_COL_WIDTH}
          align="right"
        />
        <SortableTh label="Status" sortKey="status" activeKey={sortKey} dir={sortDir} onSort={onSort} />
      </tr>
    </thead>
  )
}

function RunListRow({ run, onOpen }: { run: TestRunRead; onOpen: () => void }) {
  const { by } = parseTrigger(run.trigger)
  return (
    <tr
      role="button"
      tabIndex={0}
      className="clickable"
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onOpen()
      }}
    >
      <td style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', borderLeft: `3px solid ${runSignalColor(run)}` }}>
        {formatDateTimeWithZone(run.created_at)}
      </td>
      <td style={{ fontSize: 12.5, color: 'var(--ink-secondary)' }}>{by}</td>
      <td className="caption" style={{ fontSize: 12, textAlign: 'right' }}>
        {run.pass_rate != null ? `${Math.round(run.pass_rate * 100)}%` : '—'}
      </td>
      <td style={{ fontSize: 12, textAlign: 'right', color: 'var(--good)' }}>{run.passed_count} passed</td>
      <td style={{ fontSize: 12, textAlign: 'right', color: 'var(--danger)' }}>{run.failed_count} failed</td>
      <td className="caption" style={{ fontSize: 12, textAlign: 'right' }}>
        {formatDuration(runDurationMs(run))}
      </td>
      <td>
        <StatusPill status={run.status} label={testRunStatusLabel(run.status)} />
      </td>
    </tr>
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
  const [executionUnavailable, setExecutionUnavailable] = useState(false)
  const [runs, setRuns] = useState<TestRunRead[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [sortKey, setSortKey] = useState<SortKey>('date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const sortedRuns = useMemo(() => sortRuns(runs, sortKey, sortDir), [runs, sortKey, sortDir])
  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }
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
    // `POST .../test-runs` returns before its TestRun row even exists
    // (`PrepareTestRunActivity` creates it asynchronously), so the very
    // first fetch below can still show the *previous* (often already
    // finished) run on top. Whatever id shows up on that first fetch
    // becomes the baseline; auto-select then waits for a *different* id
    // instead of jumping straight to that stale leftover.
    let baselineId: string | undefined
    let baselineCaptured = false

    async function load() {
      try {
        const body = await api.listTestRuns(applicationId, page + 1, RUNS_PER_PAGE)
        if (cancelled) return
        setRuns(body.items)
        setTotal(body.total)
        if (!baselineCaptured) {
          baselineCaptured = true
          baselineId = body.items[0]?.id
        } else if (
          autoSelectPendingRef.current &&
          page === 0 &&
          body.items.length > 0 &&
          body.items[0].id !== baselineId
        ) {
          autoSelectPendingRef.current = false
          setSelectedRunId(body.items[0].id)
          onAutoSelectConsumedRef.current?.()
        }
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
    }

    load()
    // Always-on, not conditional on there being an active run — simplest
    // way to guarantee the table reflects a run started/finished by
    // anything (this tab, another tab, a reload) without extra bookkeeping.
    const interval = setInterval(load, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId, page, selectedRunId])

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null)
      setExecutionUnavailable(false)
      return
    }
    let cancelled = false
    let interval: ReturnType<typeof setInterval> | undefined

    async function poll() {
      let status: string | undefined
      try {
        const detail = await api.getTestRun(applicationId, selectedRunId!)
        if (cancelled) return
        setSelectedRun(detail)
        status = detail.status
        if ((detail.status === 'completed' || detail.status === 'blocked') && interval) {
          clearInterval(interval)
        }
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
      // `trigger_test_run` only checks for a live worker before starting —
      // a worker that crashes right after leaves the run sitting at
      // "running" with nothing to explain why (same gap generation-status/
      // discovery-status close for their own workers). Only worth asking
      // while the run could still be in flight.
      if (status === 'pending' || status === 'running') {
        try {
          const { available } = await api.getExecutionStatus(applicationId)
          if (!cancelled) setExecutionUnavailable(!available)
        } catch {
          // best-effort poll — a transient failure just skips this tick
        }
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
      <RunDetail
        run={selectedRun}
        onBack={() => setSelectedRunId(null)}
        executionUnavailable={executionUnavailable}
      />
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
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <RunListHeader sortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
              <tbody>
                {sortedRuns.map((run) => (
                  <RunListRow key={run.id} run={run} onOpen={() => setSelectedRunId(run.id)} />
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            totalItems={total}
            pageSize={RUNS_PER_PAGE}
            onPrev={() => setPage((p) => p - 1)}
            onNext={() => setPage((p) => p + 1)}
            onPage={setPage}
          />
        </div>
      )}
    </div>
  )
}
