import { useEffect, useState } from 'react'
import { faCircleDot, faClock, faDownload, faFlaskVial, faListCheck, faRoute, faTableList } from '@fortawesome/free-solid-svg-icons'
import { api, type OverviewRead } from '../../api'
import { EmptyState, RunsIllustration } from '../EmptyState'
import { Skeleton } from '../Skeleton'
import { formatDuration, parseTrigger } from './RunsTab'
import { RunSuiteButton } from './RunSuiteButton'
import { faIcon } from '../../faIcon'

const POLL_INTERVAL_MS = 5000

// Same icons the sidebar nav uses for these same destinations (App.tsx's
// JourneysIcon/ScenariosIcon, Workspace.tsx's SuiteIcon/RunsIcon/SchedulesIcon)
// — these quick-action cards used to draw their own hand-rolled SVGs, a
// second, inconsistent glyph for the same concept.
const DiscoveryIcon = faIcon(faRoute)
const LayersIcon = faIcon(faListCheck)
const CheckCircleIcon = faIcon(faTableList)
const RunHistoryIcon = faIcon(faFlaskVial)
const ClockPauseIcon = faIcon(faClock)
const DownloadProjectIcon = faIcon(faDownload)
const RecordIcon = faIcon(faCircleDot)

// Prototype's appStats tile recipe (Vantage v2 mockup, isAppHome.appStats) —
// same label/value/sub tile used un-iconed on the Global overview page.
function StatTile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div
      style={{
        background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
        backdropFilter: 'blur(16px) saturate(1.25)',
        border: '1px solid var(--border-1)',
        borderRadius: 12,
        padding: '16px 18px',
      }}
    >
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>{label}</div>
      <div style={{ fontSize: 28, lineHeight: '32px', color: 'var(--fg)', fontWeight: 600, letterSpacing: '-0.02em', marginTop: 8 }}>{value}</div>
      {sub && <div style={{ fontSize: 11.5, color: 'var(--fg-4)', marginTop: 5 }}>{sub}</div>}
    </div>
  )
}

function LegendDot({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
      <span style={{ width: 7, height: 7, borderRadius: 'var(--radius-full)', flexShrink: 0, background: color }} />
      <span style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--fg-1)' }}>{value}</span>
    </div>
  )
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

// Prototype's lrTrend bar recipe: one bar per run, the most recent one
// highlighted in accent, height rescaled over 40–100% so a chart full of
// 90%+ runs doesn't look like a wall of near-identical full bars.
function PassRateByRunBars({ trend }: { trend: OverviewRead['trend'] }) {
  if (trend.length === 0) {
    return (
      <p className="caption" style={{ fontSize: 12.5, margin: 0 }}>
        No runs yet.
      </p>
    )
  }
  const lastIndex = trend.length - 1
  return (
    <div style={{ flex: 1, minHeight: 120, display: 'flex', alignItems: 'flex-end', gap: 14 }}>
      {trend.map((t, i) => {
        const pct = t.pass_rate != null ? Math.round(t.pass_rate * 100) : null
        const barHeight = pct == null ? 6 : Math.max(6, Math.round(((pct - 40) / 60) * 100))
        const isLast = i === lastIndex
        return (
          <div
            key={t.run_id}
            style={{ flex: 1, minWidth: 0, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', alignItems: 'center', gap: 6 }}
          >
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)' }}>{pct == null ? '—' : `${pct}%`}</div>
            <div
              style={{
                width: '100%',
                height: `${barHeight}%`,
                borderRadius: '5px 5px 0 0',
                background: isLast ? 'var(--accent)' : 'var(--chip)',
                border: `1px solid ${isLast ? 'var(--accent)' : 'var(--border-2)'}`,
                borderBottom: 'none',
              }}
            />
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: isLast ? 'var(--fg-2)' : 'var(--fg-5)' }}>
              #{t.run_number}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// Quick-action shortcut tiles' destinations — the same tab keys
// Workspace/AppShell already route on, kept as a local string union instead
// of importing WorkspaceTab from Workspace.tsx to avoid a circular import
// (Workspace.tsx already imports this file).
type QuickActionTarget = 'journeys' | 'scenarios' | 'record' | 'suite' | 'runs' | 'schedules' | 'export'

const QUICK_ACTIONS: { target: QuickActionTarget; label: string; hint: string; icon: () => React.JSX.Element }[] = [
  { target: 'journeys', label: 'View journeys', hint: 'See every discovered page flow.', icon: DiscoveryIcon },
  { target: 'scenarios', label: 'Review scenarios', hint: 'Approve or edit drafted test scenarios.', icon: LayersIcon },
  { target: 'record', label: 'Record and play', hint: 'Capture a flow by hand and replay it as a test.', icon: RecordIcon },
  { target: 'suite', label: 'View test cases', hint: "See this application's generated Playwright suite.", icon: CheckCircleIcon },
  { target: 'runs', label: 'View test runs', hint: 'Browse past executions and results.', icon: RunHistoryIcon },
  { target: 'schedules', label: 'Schedules and CI', hint: 'Automate discovery and suite runs on a cadence.', icon: ClockPauseIcon },
  { target: 'export', label: 'Download project', hint: 'Get the generated Playwright project as a .zip.', icon: DownloadProjectIcon },
]

// Same right-pointing chevron every "navigate to" row in this app uses
// (RunsTab's RightChevronIcon) — kept local since it's a one-line glyph, not
// worth importing across files for.
function ChevronRightIcon() {
  return (
    <svg width={10} height={10} viewBox="0 0 24 24" fill="none" stroke="var(--fg-5)" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 6l6 6-6 6" />
    </svg>
  )
}

// Fixed 3-per-row (not auto-fit) — a wide viewport would otherwise pack 4+
// of these ~240px-minimum cards onto one row; the prototype's grid is
// strictly 3 wide, wrapping to further rows instead of stretching wider.
function QuickActionsGrid({ onNavigate }: { onNavigate: (target: QuickActionTarget) => void }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,minmax(0,1fr))', gap: 14 }}>
      {QUICK_ACTIONS.map((action) => {
        const Icon = action.icon
        return (
          <div
            key={action.target}
            role="button"
            tabIndex={0}
            onClick={() => onNavigate(action.target)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') onNavigate(action.target)
            }}
            className="card-clickable"
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 13,
              background: 'var(--panel)',
              border: '1px solid var(--border-2)',
              borderRadius: 12,
              padding: '16px 18px',
              boxShadow: '0 1px 3px rgba(15,23,42,0.07)',
              cursor: 'pointer',
            }}
          >
            <span
              aria-hidden="true"
              style={{ width: 32, height: 32, flexShrink: 0, borderRadius: 8, background: 'var(--hover)', color: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <Icon />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>{action.label}</div>
              <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 3 }}>{action.hint}</div>
            </div>
            <span aria-hidden="true" style={{ marginTop: 4, flexShrink: 0 }}>
              <ChevronRightIcon />
            </span>
          </div>
        )
      })}
    </div>
  )
}

export function OverviewTab({
  applicationId,
  onRunSuite,
  onOpenJourneysDialog,
  onNavigateTab,
  running,
}: {
  applicationId: string
  onRunSuite: () => void
  onOpenJourneysDialog: () => void
  onNavigateTab: (target: QuickActionTarget) => void
  running: boolean
}) {
  const [overview, setOverview] = useState<OverviewRead | null>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const body = await api.getOverview(applicationId)
        if (!cancelled) setOverview(body)
      } catch {
        // best-effort poll — a transient failure just skips this tick
      }
    }

    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [applicationId])

  if (!overview) {
    // Skeleton, not a spinner — this tab is the landing spot right after
    // opening an application, before its first poll resolves.
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(210px,1fr))', gap: 14 }}>
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border-1)', borderRadius: 14, padding: '18px 20px 17px', boxShadow: 'var(--panel-shadow)' }}>
            <Skeleton width={80} height={10} />
            <Skeleton width={70} height={28} style={{ marginTop: 16 }} />
            <Skeleton width={120} height={10} style={{ marginTop: 10 }} />
          </div>
        ))}
      </div>
    )
  }

  // No run has ever happened for this application — health/pass-rate/trend
  // are all meaningless zeros, so show one tab-level illustration instead of
  // three separate cards each explaining their own absence of data.
  if (!overview.latest_run) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div
          style={{
            background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
            backdropFilter: 'blur(16px) saturate(1.25)',
            border: '1px solid var(--border-1)',
            borderRadius: 14,
            boxShadow: 'var(--panel-shadow)',
            padding: 24,
          }}
        >
          <EmptyState
            illustration={<RunsIllustration />}
            title="No test runs yet"
            subtitle="Health, pass rate, and trend will show up here once your first run finishes."
            action={
              <RunSuiteButton running={running} onFullSuite={onRunSuite} onOpenJourneysDialog={onOpenJourneysDialog} />
            }
          />
        </div>
        <QuickActionsGrid onNavigate={onNavigateTab} />
      </div>
    )
  }

  const { passed_count, failed_count, blocked_count } = overview.latest_run
  const total = passed_count + failed_count + blocked_count
  const segPct = (n: number) => (total > 0 ? (n / total) * 100 : 0)
  // Same denominator as the "Pass rate by run" bars below (this run's own
  // passed/total) — not `overview.pass_rate` (latest-known status per
  // scenario across all history, a different, wider-scoped number). Both
  // this stat tile and "Last run pass rate" are explicitly run-scoped, so
  // they must agree with the bars they sit next to instead of quietly
  // pulling from a different metric with a different denominator.
  const runPassRate = total > 0 ? passed_count / total : null
  const trend = overview.trend
  const deltaPts =
    trend.length >= 2 && trend[trend.length - 1].pass_rate != null && trend[trend.length - 2].pass_rate != null
      ? (trend[trend.length - 1].pass_rate! - trend[trend.length - 2].pass_rate!) * 100
      : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(210px,1fr))', gap: 14 }}>
        <StatTile
          label="Journeys mapped"
          value={overview.journey_count}
          sub={overview.last_discovery_started_at ? `Last discovery ${formatDateTime(overview.last_discovery_started_at)}` : 'No discovery yet'}
        />
        <StatTile label="Test cases" value={overview.total_tests} sub={`${overview.not_run} not yet run`} />
        <StatTile
          label="Pass rate"
          value={runPassRate == null ? '—' : `${(runPassRate * 100).toFixed(1)}%`}
          sub={`Latest run · ${formatDuration(overview.latest_run.duration_ms)}`}
        />
        <StatTile label="Open failures" value={overview.failed} sub={`${blocked_count} skipped`} />
      </div>

      <div
        style={{
          background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
          backdropFilter: 'blur(16px) saturate(1.25)',
          border: '1px solid var(--border-1)',
          borderRadius: 12,
          padding: '18px 20px',
          display: 'grid',
          gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.1fr)',
          gap: 24,
          alignItems: 'stretch',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>Last run pass rate</div>
              <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>
                {parseTrigger(overview.latest_run.trigger).by} · {formatDateTime(overview.latest_run.created_at)}
              </div>
            </div>
            <span
              onClick={() => onNavigateTab('runs')}
              style={{ fontSize: 11.5, fontWeight: 500, color: 'var(--accent-2)', cursor: 'pointer', flex: 'none', paddingTop: 3, whiteSpace: 'nowrap' }}
            >
              View run
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 40, lineHeight: '42px', fontWeight: 600, letterSpacing: '-0.03em', color: 'var(--fg)' }}>
              {runPassRate == null ? '—' : `${(runPassRate * 100).toFixed(1)}%`}
            </div>
            {deltaPts != null && (
              <div style={{ fontSize: 11.5, fontWeight: 500, color: deltaPts >= 0 ? 'var(--ok)' : 'var(--bad)' }}>
                {deltaPts >= 0 ? '+' : ''}
                {deltaPts.toFixed(1)} pts vs previous run
              </div>
            )}
          </div>
          <div style={{ height: 10, borderRadius: 'var(--radius-full)', overflow: 'hidden', background: 'var(--chip)', display: 'flex' }}>
            <div style={{ width: `${segPct(passed_count)}%`, background: 'var(--ok)' }} />
            <div style={{ width: `${segPct(failed_count)}%`, background: 'var(--bad)' }} />
            <div style={{ width: `${segPct(blocked_count)}%`, background: 'var(--border-2)' }} />
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 18px' }}>
            <LegendDot color="var(--ok)" label="Passed" value={passed_count} />
            <LegendDot color="var(--bad)" label="Failed" value={failed_count} />
            <LegendDot color="var(--border-2)" label="Not run" value={blocked_count} />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0, borderLeft: '1px solid var(--line)', paddingLeft: 24 }}>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)', letterSpacing: '0.02em' }}>Pass rate by run</div>
          <PassRateByRunBars trend={trend} />
        </div>
      </div>

      <QuickActionsGrid onNavigate={onNavigateTab} />
    </div>
  )
}
