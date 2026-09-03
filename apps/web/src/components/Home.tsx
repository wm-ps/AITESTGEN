import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { api, type ApplicationRead, type HomeApplicationRead, type UserRead } from '../api'
import { StatusPill } from './StatusPill'
import { Pagination } from './Pagination'
import { Toast } from './Toast'
import { useEscapeToClose } from '../hooks/useEscapeToClose'

const POLL_INTERVAL_MS = 15000
const APPS_PER_PAGE = 5
const VIEW_STORAGE_KEY = 'aitg-home-view'
// Mirrors MAX_ACTIVE_PROJECTS in apps/api/src/api/main.py — server enforces
// this for real, this just keeps the button from inviting a 409.
const MAX_ACTIVE_PROJECTS = 4

function FolderIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3.5 7.2A1.7 1.7 0 0 1 5.2 5.5h3.4l1.7 1.7h8a1.7 1.7 0 0 1 1.7 1.7v8.4a1.7 1.7 0 0 1-1.7 1.7H5.2a1.7 1.7 0 0 1-1.7-1.7V7.2Z" />
    </svg>
  )
}

function WarningIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3.5 21.5 20h-19L12 3.5Z" />
      <path d="M12 10v4" />
      <circle cx="12" cy="17.2" r="0.4" fill="currentColor" stroke="none" />
    </svg>
  )
}

function MoreIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="12" cy="5" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="12" cy="19" r="1.8" />
    </svg>
  )
}

function GridViewIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.3" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.3" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.3" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.3" />
    </svg>
  )
}

function ListViewIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3.5" y="4.5" width="17" height="4" rx="1" />
      <rect x="3.5" y="10" width="17" height="4" rx="1" />
      <rect x="3.5" y="15.5" width="17" height="4" rx="1" />
    </svg>
  )
}

function BranchIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="6" cy="5" r="2.2" />
      <circle cx="6" cy="19" r="2.2" />
      <circle cx="18" cy="12" r="2.2" />
      <path d="M6 7.2V16.8" />
      <path d="M6 9.5C6 12 8 12 10.5 12H15.8" />
    </svg>
  )
}

function DocumentIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6.5 3.5h8l3 3v13a1 1 0 0 1-1 1h-10a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1Z" />
      <path d="M14 3.5V7h3.5" />
      <path d="M8.5 12h7M8.5 15.3h7" />
    </svg>
  )
}

function RunsIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M10.3 8.7 15 12l-4.7 3.3V8.7Z" fill="currentColor" stroke="none" />
    </svg>
  )
}

// Stock-market-style trend vs the previous run — up green, down red, absent when flat or no prior run to compare.
function TrendArrow({ direction, size }: { direction: 'up' | 'down'; size: number }) {
  const color = direction === 'up' ? 'var(--good-strong)' : 'var(--danger-strong)'
  const points = direction === 'up' ? '23 6 13.5 15.5 8.5 10.5 1 18' : '23 18 13.5 8.5 8.5 13.5 1 6'
  const headPoints = direction === 'up' ? '17 6 23 6 23 12' : '17 18 23 18 23 12'
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flexShrink: 0 }}
    >
      <polyline points={points} />
      <polyline points={headPoints} />
    </svg>
  )
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  return parts
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(diffMs / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

// Same 90%/70% pass-rate cutoffs Workspace Overview's `_health_tier` uses
// (apps/api/src/api/main.py) — one health-tier vocabulary across the app.
function passRateColor(passRate: number): string {
  if (passRate >= 0.9) return 'var(--good-strong)'
  if (passRate >= 0.7) return 'var(--warn-strong)'
  return 'var(--danger-strong)'
}

function PassRateRing({ passRate }: { passRate: number | null }) {
  const size = 40
  const stroke = 4
  const r = (size - stroke) / 2
  const circumference = 2 * Math.PI * r
  const pct = passRate == null ? 0 : Math.min(1, Math.max(0, passRate))
  const color = passRate == null ? 'var(--border-strong)' : passRateColor(pct)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ position: 'relative', display: 'inline-flex', width: size, height: size, flexShrink: 0 }}>
        <svg width={size} height={size} overflow="visible" style={{ position: 'absolute', top: 0, left: 0, transform: 'rotate(-90deg)' }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border-strong)" strokeWidth={stroke} />
          {passRate != null && (
            <circle
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={color}
              strokeWidth={stroke}
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - pct)}
            />
          )}
        </svg>
        <span style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color }}>
          {passRate == null ? '—' : `${Math.round(pct * 100)}%`}
        </span>
      </span>
      <span className="caption" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
        {passRate == null ? 'No runs yet' : 'Pass rate'}
      </span>
    </div>
  )
}

// The SaaS-standard mini bar/column sparkline (Stripe/Vercel/GitHub-style
// run history): each bar is one run, bar height is that run's pass rate,
// bar color is its health tier — sequence AND magnitude read at a glance,
// no axis needed since heights compare directly against each other.
/* Trend column hidden for now — commented out with its call site in
 * ApplicationCard rather than deleted, since the column is coming back.
function MiniBarChart({ values }: { values: (number | null)[] }) {
  // A single bar has nothing to compare against — it's not a trend, just
  // one number redrawn as a shape (and a low pass rate renders as a bar
  // too short to see, which reads as blank/broken rather than "one run").
  if (values.length < 2) {
    return (
      <span className="caption" style={{ fontSize: 12 }}>
        {values.length === 0 ? 'No runs yet' : 'First run — no trend yet'}
      </span>
    )
  }
  // Combo chart: bars still give each run's own magnitude/tier, a
  // connecting line across their tops adds the rising/falling shape a
  // reader would otherwise have to infer bar-by-bar.
  const w = 100
  const h = 28
  const n = values.length
  const barWidth = (w / n) * 0.55
  const points = values.map((v, i) => {
    const val = v ?? 0
    const cx = (i + 0.5) * (w / n)
    const barHeight = Math.max(2, val * h)
    return { cx, y: h - val * h, barX: cx - barWidth / 2, barHeight, color: v != null ? passRateColor(v) : 'var(--border-strong)' }
  })
  return (
    <div>
      <svg width={110} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" overflow="visible">
        <title>Recent runs, oldest to newest — bars are each run, line is the trend</title>
        {points.map((p, i) => (
          <rect key={i} x={p.barX} y={h - p.barHeight} width={barWidth} height={p.barHeight} rx={1} fill={p.color} opacity={0.45} />
        ))}
        <polyline
          points={points.map((p) => `${p.cx},${p.y}`).join(' ')}
          fill="none"
          stroke="var(--ink-secondary)"
          strokeWidth={1.6}
          vectorEffect="non-scaling-stroke"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {points.map((p, i) => (
          <circle key={i} cx={p.cx} cy={p.y} r={2} fill={p.color} />
        ))}
      </svg>
      <div className="caption" style={{ fontSize: 12, marginTop: 4 }}>
        Recent runs
      </div>
    </div>
  )
}
*/

// Coverage % (scenario_journeys_covered / journey_count) is available on
// hover as a tooltip rather than a ring — a circular progress ring around a
// square-cornered badge read as visually broken, and this card's stat chips
// below already state the raw journey/scenario numbers directly.
function InitialsAvatar({ name, coveragePct, hasJourneys }: { name: string; coveragePct: number; hasJourneys: boolean }) {
  return (
    <span
      aria-hidden="true"
      title={hasJourneys ? `${Math.round(coveragePct * 100)}% of journeys covered by scenarios` : undefined}
      style={{
        display: 'inline-flex',
        alignSelf: 'stretch',
        width: '100%',
        height: '100%',
        borderRadius: 10,
        background: 'var(--accent-wash)',
        color: 'var(--accent)',
        alignItems: 'center',
        justifyContent: 'center',
        fontWeight: 700,
        fontSize: 15,
        flexShrink: 0,
      }}
    >
      {initials(name)}
    </span>
  )
}

// Value and label sit on one line, glued together as a single phrase ("12
// Journeys") — a stacked bold-number-over-label layout read as its own
// clickable badge, which it isn't.
function StatChip({
  value,
  label,
  valueColor,
  icon,
  layout = 'inline',
}: {
  value: ReactNode
  label: string
  valueColor?: string
  icon?: ReactNode
  layout?: 'inline' | 'stacked'
}) {
  if (layout === 'stacked') {
    return (
      <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 4, whiteSpace: 'nowrap' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          {icon && (
            <span aria-hidden="true" style={{ display: 'inline-flex', color: valueColor ?? 'var(--ink-muted)', flexShrink: 0 }}>
              {icon}
            </span>
          )}
          <span style={{ fontWeight: 700, fontSize: 16, color: valueColor }}>{value}</span>
        </span>
        <span className="caption" style={{ fontSize: 12 }}>
          {label}
        </span>
      </span>
    )
  }
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
      {icon && (
        <span aria-hidden="true" style={{ display: 'inline-flex', color: valueColor ?? 'var(--ink-muted)', flexShrink: 0 }}>
          {icon}
        </span>
      )}
      <span style={{ whiteSpace: 'nowrap' }}>
        <span style={{ fontWeight: 700, color: valueColor }}>{value}</span>{' '}
        <span className="caption" style={{ fontSize: 12 }}>
          {label}
        </span>
      </span>
    </span>
  )
}

function ApplicationCard({
  application,
  isAdmin,
  view,
  onResume,
  onBlocked,
  onChanged,
  onError,
}: {
  application: HomeApplicationRead
  isAdmin: boolean
  view: 'grid' | 'list'
  onResume: () => void
  onBlocked: () => void
  onChanged: () => void
  onError: (message: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [nameDraft, setNameDraft] = useState(application.name)
  const [menuOpen, setMenuOpen] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  useEscapeToClose(() => confirmingDelete && !deleting && setConfirmingDelete(false))
  const skipBlurRef = useRef(false)

  const discoveryStatus = application.discovery_status
  // `suite_count` alone can't tell "generation finished" from "generation
  // just started": EnsureTestSuiteActivity creates the TestSuite row before
  // its TestAssets exist. A count-based check here (test_case_count <
  // scenario_count) never recovers once a Scenario is permanently skipped
  // or fails all its wave retries — same gap TestSuiteResults.tsx's
  // isComplete had. `suites_generating_count` is the suite.status-based
  // signal that fix uses: whether any suite is still actually mid-run.
  const suiteGenerating = application.suite_count > 0 && application.suites_generating_count > 0
  const testCasesComplete = application.suite_count > 0 && !suiteGenerating
  // Same signal ReviewScenarios.tsx uses: `scenario_count` alone can't tell
  // "generation finished" from "still writing more Scenarios" once the
  // first one lands — `scenario_journeys_covered < journey_count` means
  // GenerationWorkflow is still running for at least one Journey.
  const scenariosGenerating =
    application.scenario_count > 0 && application.scenario_journeys_covered < application.journey_count
  const stage =
    discoveryStatus === 'failed' || discoveryStatus === 'paused'
      ? discoveryStatus
      : suiteGenerating
        ? 'generating_tests'
        : application.suite_count > 0
          ? 'suite_generated'
          : scenariosGenerating
            ? 'generating_scenarios'
            : application.scenario_count > 0
              ? 'scenarios_generated'
              : application.journey_count > 0
              ? 'journeys_generated'
              // `discovery_status` flips to "complete" as soon as the crawl
              // finishes — before the LLM inference call that produces
              // Journeys has run. `discovery_stage` reaching "analyzed" is
              // the real signal that analysis (and its journey count) is in,
              // so this card doesn't say "completed" while it's still
              // waiting on that call.
              : discoveryStatus === 'complete' && application.discovery_stage === 'analyzed'
                ? 'discovery_completed'
                : 'running'

  const isRunning = discoveryStatus === 'running'
  const hasJourneys = application.journey_count > 0
  const coveragePct = hasJourneys ? application.scenario_journeys_covered / application.journey_count : 0

  // A "Run All Tests" TestRun in progress outranks every discovery/
  // generation stage above — it's a different axis (execution, not
  // pipeline position) and the card must say so regardless of `stage`.
  const testRunRunning = application.last_test_run_status === 'running'
  const deleteBlocked = isRunning || scenariosGenerating || suiteGenerating || testRunRunning
  const deleteBlockedReason = isRunning
    ? 'Discovery is still running'
    : scenariosGenerating
      ? 'Scenario generation is still running'
      : suiteGenerating
        ? 'Test suite generation is still running'
        : testRunRunning
          ? 'A test run is still running'
          : undefined
  const passRate = application.last_test_run_pass_rate
  // Once a run has actually finished, the card should say how it went
  // (Healthy/Needs Attention/Critical) rather than sitting on "Ready to
  // run" forever — `ready_to_execute` only applies before the first run.
  const hasCompletedRun = application.last_test_run_status === 'completed' && passRate != null
  const readyToExecute = stage === 'suite_generated' && !testRunRunning && !hasCompletedRun
  const displayStatus = testRunRunning
    ? 'test_run_running'
    : hasCompletedRun
      ? application.last_test_run_health.tier
      : readyToExecute
        ? 'ready_to_execute'
        : stage
  // ponytail: no "last touched" column on Application, so once a TestRun
  // exists it's the freshest signal we show; before that we fall back to
  // the connect timestamp (`created_at`), which is honestly older than
  // "updated" implies. A real `updated_at` column (bumped on
  // discovery/generation activity) would fix this if it matters later.
  const activityLabel = application.last_test_run_created_at
    ? `Last run ${relativeTime(application.last_test_run_created_at)}`
    : `Updated ${relativeTime(application.created_at)}`

  const kebabButtonStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 24,
    height: 24,
    borderRadius: 6,
    border: 'none',
    background: 'none',
    color: 'var(--ink-muted)',
    padding: 0,
    flexShrink: 0,
  }

  const menuItemStyle: CSSProperties = {
    display: 'block',
    width: '100%',
    textAlign: 'left',
    padding: '9px 14px',
    fontSize: 13.5,
    fontWeight: 500,
    border: 'none',
    background: 'none',
    color: 'var(--ink)',
    cursor: 'pointer',
  }

  const renameActionButtonStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 24,
    height: 24,
    borderRadius: 6,
    border: 'none',
    background: 'none',
    padding: 0,
    fontSize: 14,
    lineHeight: 1,
    cursor: 'pointer',
    flexShrink: 0,
  }

  function cancelRename() {
    skipBlurRef.current = true
    setNameDraft(application.name)
    setEditing(false)
  }

  async function saveRename() {
    skipBlurRef.current = true
    const trimmed = nameDraft.trim()
    if (!trimmed || trimmed === application.name) {
      cancelRename()
      return
    }
    setEditing(false)
    try {
      await api.renameApplication(application.id, trimmed)
      onChanged()
    } catch {
      setNameDraft(application.name)
      onError('Could not rename application — try again.')
    }
  }

  async function confirmDelete() {
    setDeleting(true)
    try {
      await api.deleteApplication(application.id)
      onChanged()
    } catch {
      onError('Could not delete application — try again.')
    } finally {
      setDeleting(false)
      setConfirmingDelete(false)
    }
  }

  const identitySection = (
    <div style={{ minWidth: 0 }}>
        {editing ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
            <input
              autoFocus
              value={nameDraft}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setNameDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') saveRename()
                if (e.key === 'Escape') cancelRename()
              }}
              onBlur={() => {
                if (skipBlurRef.current) {
                  skipBlurRef.current = false
                  return
                }
                saveRename()
              }}
              style={{
                fontSize: 15,
                fontWeight: 700,
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '2px 6px',
                flex: 1,
                minWidth: 0,
                boxSizing: 'border-box',
                font: 'inherit',
              }}
            />
            <button
              type="button"
              title="Save"
              onClick={(e) => {
                e.stopPropagation()
                saveRename()
              }}
              style={{ ...renameActionButtonStyle, color: 'var(--accent)' }}
            >
              ✓
            </button>
            <button
              type="button"
              title="Cancel"
              onClick={(e) => {
                e.stopPropagation()
                cancelRename()
              }}
              style={{ ...renameActionButtonStyle, color: 'var(--ink-muted)' }}
            >
              ✕
            </button>
          </div>
        ) : (
          <div
            style={{
              fontSize: 15,
              fontWeight: 700,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              minWidth: 0,
            }}
          >
            {application.name}
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-6)', marginTop: 6, minWidth: 0 }}>
          <span style={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
            <StatusPill status={displayStatus} pulsing={testRunRunning || isRunning || scenariosGenerating || suiteGenerating} />
          </span>
          <span aria-hidden="true" style={{ width: 2, height: 16, background: 'var(--border-strong)', borderRadius: 1, flexShrink: 0 }} />
          <span
            className="caption"
            style={{ fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}
          >
            {activityLabel}
          </span>
        </div>
      </div>
  )

  const compact = view === 'grid'
  const iconSize = compact ? 22 : 19
  const chipLayout = compact ? 'stacked' : 'inline'
  const journeysChip = (
    <span style={{ opacity: hasJourneys ? 1 : 0.45 }}>
      <StatChip value={application.journey_count} label="Journeys" icon={<BranchIcon size={iconSize} />} layout={chipLayout} />
    </span>
  )
  const testCasesChip = (
    <span style={{ opacity: testCasesComplete ? 1 : 0.45 }}>
      <StatChip
        value={testCasesComplete ? application.test_case_count : '–'}
        label="Test Cases"
        icon={<DocumentIcon size={iconSize} />}
        layout={chipLayout}
      />
    </span>
  )
  // Grid tiles are too small for the ring's stroke + percentage text to stay
  // legible, so grid uses the same value-label shape as the other three
  // stats (no icon — the trend arrow and colored percentage carry that role)
  // — list keeps the ring, which has the room for it.
  const passRatePct = passRate == null ? null : Math.round(Math.min(1, Math.max(0, passRate)) * 100)
  // Trend vs the run before this one — only when there's a prior run to compare and it actually moved.
  const priorRates = application.recent_pass_rates.slice(0, -1)
  const priorRate = priorRates.length > 0 ? priorRates[priorRates.length - 1] : null
  const trend = passRate == null || priorRate == null || passRate === priorRate ? null : passRate > priorRate ? 'up' : 'down'
  const passRateChip = compact ? (
    <span style={{ opacity: passRate == null ? 0.45 : 1 }}>
      <StatChip
        value={passRatePct == null ? '—' : `${passRatePct}%`}
        label={passRate == null ? 'No runs yet' : 'Pass rate'}
        valueColor={passRate == null ? undefined : passRateColor(passRatePct! / 100)}
        icon={trend ? <TrendArrow direction={trend} size={iconSize} /> : undefined}
        layout="stacked"
      />
    </span>
  ) : (
    <span style={{ opacity: passRate == null ? 0.45 : 1 }}>
      <PassRateRing passRate={passRate} />
    </span>
  )
  const executionsChip = (
    <span style={{ opacity: testCasesComplete ? 1 : 0.45 }}>
      <StatChip value={application.test_run_count} label="Test Runs" icon={<RunsIcon size={iconSize} />} layout={chipLayout} />
    </span>
  )
  // Trend column hidden for now — <MiniBarChart values={application.recent_pass_rates} />
  const kebabMenu = isAdmin && !editing && (
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <button
            type="button"
            title="More options"
            onClick={(e) => {
              e.stopPropagation()
              setMenuOpen((v) => !v)
            }}
            style={kebabButtonStyle}
          >
            <MoreIcon size={19} />
          </button>
          {menuOpen && (
            <>
              <div
                onClick={(e) => {
                  e.stopPropagation()
                  setMenuOpen(false)
                }}
                style={{ position: 'fixed', inset: 0, zIndex: 9 }}
              />
              <div
                onClick={(e) => e.stopPropagation()}
                className="card-panel"
                style={{
                  position: 'absolute',
                  top: '100%',
                  right: 0,
                  marginTop: 4,
                  minWidth: 140,
                  padding: 4,
                  zIndex: 10,
                  boxShadow: 'var(--shadow-dropdown-lg)',
                }}
              >
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false)
                    setNameDraft(application.name)
                    setEditing(true)
                  }}
                  style={menuItemStyle}
                >
                  Rename
                </button>
                <button
                  type="button"
                  disabled={deleteBlocked}
                  title={deleteBlockedReason}
                  onClick={(e) => {
                    e.stopPropagation()
                    setMenuOpen(false)
                    if (deleteBlocked) return
                    setConfirmingDelete(true)
                  }}
                  style={{
                    ...menuItemStyle,
                    color: 'var(--danger)',
                    opacity: deleteBlocked ? 0.4 : 1,
                    cursor: deleteBlocked ? 'not-allowed' : 'pointer',
                  }}
                >
                  Delete
                </button>
              </div>
            </>
          )}
        </div>
  )

  const deleteDialog =
    confirmingDelete &&
    createPortal(
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Delete application"
          onClick={(e) => {
            e.stopPropagation()
            if (!deleting) setConfirmingDelete(false)
          }}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 'var(--space-9)',
            zIndex: 100,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="card-panel"
            style={{ maxWidth: 420, width: '100%', padding: 'var(--space-8)' }}
          >
            <div style={{ display: 'flex', gap: 'var(--space-6)', marginBottom: 'var(--space-7)' }}>
              <span
                aria-hidden="true"
                style={{
                  display: 'inline-flex',
                  width: 40,
                  height: 40,
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--danger-wash)',
                  color: 'var(--danger)',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <WarningIcon size={19} />
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 4 }}>
                  Delete &ldquo;{application.name}&rdquo;?
                </div>
                <p className="caption" style={{ margin: 0, lineHeight: 1.5 }}>
                  This removes the application from your workspace. This can&apos;t be undone from here.
                </p>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-4)' }}>
              <button
                type="button"
                className="button-secondary"
                disabled={deleting}
                onClick={(e) => {
                  e.stopPropagation()
                  setConfirmingDelete(false)
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={(e) => {
                  e.stopPropagation()
                  confirmDelete()
                }}
                style={{
                  padding: '9px 16px',
                  borderRadius: 'var(--radius)',
                  border: 'none',
                  background: 'var(--danger)',
                  color: '#FFFFFF',
                  fontWeight: 600,
                  cursor: deleting ? 'default' : 'pointer',
                  opacity: deleting ? 0.7 : 1,
                }}
              >
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>,
      document.body,
    )

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={isRunning ? onBlocked : onResume}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') (isRunning ? onBlocked : onResume)()
      }}
      className="card-panel home-app-card"
      style={
        view === 'list'
          ? {
              textAlign: 'left',
              padding: '16px 22px',
              cursor: 'pointer',
              display: 'grid',
              // Trend column commented out below (for now) — its 150px + gap
              // folds into the identity column instead of sitting empty.
              gridTemplateColumns: '52px minmax(220px, 500px) 120px 150px 160px 120px 24px',
              alignItems: 'center',
              columnGap: 'var(--space-6)',
              width: '100%',
              maxWidth: 1400,
            }
          : {
              textAlign: 'left',
              padding: '18px 20px',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-5)',
              width: '100%',
            }
      }
    >
      {view === 'list' ? (
        <>
          <InitialsAvatar name={application.name} coveragePct={coveragePct} hasJourneys={hasJourneys} />
          {identitySection}
          {journeysChip}
          {testCasesChip}
          {passRateChip}
          {executionsChip}
          {kebabMenu}
        </>
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-4)' }}>
            <div style={{ width: 48, height: 48, flexShrink: 0 }}>
              <InitialsAvatar name={application.name} coveragePct={coveragePct} hasJourneys={hasJourneys} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>{identitySection}</div>
            {kebabMenu}
          </div>
          <div aria-hidden="true" style={{ height: 1, background: 'var(--border-hairline)' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
            {journeysChip}
            {testCasesChip}
            {passRateChip}
            {executionsChip}
          </div>
        </>
      )}
      {deleteDialog}
    </div>
  )
}

export function Home({
  user,
  onConnectApp,
  onResumeApplication,
}: {
  user: UserRead
  onConnectApp: () => void
  onResumeApplication: (application: ApplicationRead) => void
}) {
  const firstName = user.name.trim().split(/\s+/)[0]
  const isAdmin = user.role === 'admin'
  const [showDemo, setShowDemo] = useState(false)
  useEscapeToClose(() => showDemo && setShowDemo(false))
  const [applications, setApplications] = useState<HomeApplicationRead[] | null>(null)
  const [snackbar, setSnackbar] = useState<{ message: string; kind: 'error' | 'info' } | null>(
    null,
  )
  const [page, setPage] = useState(0)
  const [view, setView] = useState<'grid' | 'list'>(() => {
    try {
      return localStorage.getItem(VIEW_STORAGE_KEY) === 'list' ? 'list' : 'grid'
    } catch {
      return 'grid'
    }
  })

  function changeView(next: 'grid' | 'list') {
    setView(next)
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, next)
    } catch {
      // best-effort — view choice just won't persist across reloads
    }
  }

  useEffect(() => {
    if (!snackbar) return
    const timeout = setTimeout(() => setSnackbar(null), 3000)
    return () => clearTimeout(timeout)
  }, [snackbar])

  async function refreshApplications() {
    try {
      setApplications(await api.getHome())
    } catch {
      // best-effort — a transient failure just skips this refresh
    }
  }

  useEffect(() => {
    refreshApplications()
    const interval = setInterval(refreshApplications, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [])

  // Newest activity first — a project just connected and one that just ran
  // tests both count as "recent," so sort by whichever timestamp is later.
  const applicationList = (Array.isArray(applications) ? applications : []).toSorted((a, b) => {
    const activityTime = (app: HomeApplicationRead) =>
      Math.max(new Date(app.created_at).getTime(), app.last_test_run_created_at ? new Date(app.last_test_run_created_at).getTime() : 0)
    return activityTime(b) - activityTime(a)
  })
  const totalPages = Math.max(1, Math.ceil(applicationList.length / APPS_PER_PAGE))
  const pageClamped = Math.min(page, totalPages - 1)
  const pagedApplications = applicationList.slice(
    pageClamped * APPS_PER_PAGE,
    pageClamped * APPS_PER_PAGE + APPS_PER_PAGE,
  )

  return (
    <main
      style={{
        width: '100%',
        boxSizing: 'border-box',
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        background:
          'radial-gradient(900px 500px at 85% -10%, var(--accent-wash-soft) 0%, transparent 55%), linear-gradient(180deg, #FBFCFE 0%, #F6F9FB 100%)',
      }}
    >
      <div
        style={{
          flex: 1,
          width: '100%',
          minWidth: 0,
          maxWidth: 'var(--content-max-wide)',
          margin: '0 auto',
          padding: '36px 44px',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-9)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 'var(--space-8)',
            flexShrink: 0,
            animation: 'aitg-fade-up 0.4s ease-out both',
          }}
        >
          <div>
            <div
              style={{
                fontSize: 15,
                fontWeight: 700,
                color: 'var(--accent)',
                marginBottom: 4,
                animation: 'aitg-welcome-reveal 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.1s both',
              }}
            >
              Welcome, {firstName}
            </div>
            <h1 style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.02em', margin: 0 }}>Applications</h1>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)', flexShrink: 0, alignItems: 'center' }}>
            <div
              role="group"
              aria-label="Choose application view"
              style={{
                display: 'flex',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                padding: 2,
                gap: 2,
              }}
            >
              <button
                type="button"
                title="Grid view"
                aria-label="Grid view"
                aria-pressed={view === 'grid'}
                onClick={() => changeView('grid')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 30,
                  height: 30,
                  border: 'none',
                  borderRadius: 'var(--radius-sm, 6px)',
                  cursor: 'pointer',
                  background: view === 'grid' ? 'var(--accent-wash)' : 'none',
                  color: view === 'grid' ? 'var(--accent)' : 'var(--ink-muted)',
                }}
              >
                <GridViewIcon size={16} />
              </button>
              <button
                type="button"
                title="List view"
                aria-label="List view"
                aria-pressed={view === 'list'}
                onClick={() => changeView('list')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 30,
                  height: 30,
                  border: 'none',
                  borderRadius: 'var(--radius-sm, 6px)',
                  cursor: 'pointer',
                  background: view === 'list' ? 'var(--accent-wash)' : 'none',
                  color: view === 'list' ? 'var(--accent)' : 'var(--ink-muted)',
                }}
              >
                <ListViewIcon size={16} />
              </button>
            </div>
            <button
              type="button"
              className="button-secondary"
              onClick={() => setShowDemo(true)}
              style={{ padding: '11px 18px' }}
            >
              Watch Demo
            </button>
            {applications && applications.length > 0 && (
              <button
                type="button"
                className="button-primary"
                disabled={applications.length >= MAX_ACTIVE_PROJECTS}
                title={
                  applications.length >= MAX_ACTIVE_PROJECTS
                    ? `Maximum of ${MAX_ACTIVE_PROJECTS} active applications reached — delete one before adding another.`
                    : undefined
                }
                onClick={onConnectApp}
                style={{
                  padding: '11px 18px',
                  opacity: applications.length >= MAX_ACTIVE_PROJECTS ? 0.5 : 1,
                  cursor: applications.length >= MAX_ACTIVE_PROJECTS ? 'not-allowed' : 'pointer',
                }}
              >
                + New Application
              </button>
            )}
          </div>
        </div>

        {applications === null ? null : applications.length > 0 ? (
          <>
            <div
              style={
                view === 'grid'
                  ? {
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))',
                      gap: 'var(--space-5)',
                      alignContent: 'start',
                      animation: 'aitg-fade-up 0.4s ease-out 0.1s both',
                    }
                  : {
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 'var(--space-5)',
                      animation: 'aitg-fade-up 0.4s ease-out 0.1s both',
                    }
              }
            >
              {pagedApplications.map((application) => (
                <ApplicationCard
                  key={application.id}
                  application={application}
                  isAdmin={isAdmin}
                  view={view}
                  onResume={() => onResumeApplication(application)}
                  onBlocked={() =>
                    setSnackbar({
                      message: 'Please wait while the discovery process completes.',
                      kind: 'info',
                    })
                  }
                  onChanged={refreshApplications}
                  onError={(message) => setSnackbar({ message, kind: 'error' })}
                />
              ))}
            </div>
            <Pagination
              page={pageClamped}
              totalPages={totalPages}
              totalItems={applicationList.length}
              pageSize={APPS_PER_PAGE}
              onPrev={() => setPage(pageClamped - 1)}
              onNext={() => setPage(pageClamped + 1)}
              onPage={setPage}
            />
          </>
        ) : (
          <div
            style={{
              border: '1px dashed var(--border)',
              borderRadius: 'var(--radius-xl)',
              boxSizing: 'border-box',
              padding: 'var(--space-10)',
              flex: 1,
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              animation: 'aitg-fade-up 0.4s ease-out 0.05s both',
            }}
          >
            <span
              aria-hidden="true"
              style={{
                display: 'inline-flex',
                width: 52,
                height: 52,
                borderRadius: 'var(--radius-full)',
                background: 'var(--accent-wash)',
                color: 'var(--accent)',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 'var(--space-8)',
                flexShrink: 0,
              }}
            >
              <FolderIcon size={24} />
            </span>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 'var(--space-3)' }}>No applications yet</div>
            <p className="caption" style={{ fontSize: 14, margin: '0 0 var(--space-8)', maxWidth: 420, lineHeight: 1.5 }}>
              Connect your first application to start discovering journeys and generating tests — no
              scripts required.
            </p>
            <button type="button" className="button-primary" onClick={onConnectApp} style={{ padding: '10px 20px' }}>
              + Create New Application
            </button>
          </div>
        )}
      </div>

      {showDemo && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Product demo"
          onClick={() => setShowDemo(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 'var(--space-9)',
            zIndex: 50,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="card-panel"
            style={{ maxWidth: 560, width: '100%', padding: 'var(--space-8)' }}
          >
            <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 4 }}>Product demo</div>
            <p className="caption" style={{ margin: '0 0 var(--space-7)' }}>
              Connect App, Discover Journeys, Review Scenarios, Generate Suite — in a few minutes.
            </p>
            <video
              controls
              autoPlay
              src="/demo/app-demo.mp4"
              style={{
                width: '100%',
                aspectRatio: '16 / 9',
                borderRadius: 'var(--radius-lg)',
                marginBottom: 'var(--space-7)',
                background: 'var(--ink)',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button type="button" className="button-secondary" onClick={() => setShowDemo(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {snackbar && (
        <Toast
          message={snackbar.message}
          kind={snackbar.kind}
          onDismiss={() => setSnackbar(null)}
        />
      )}
    </main>
  )
}
