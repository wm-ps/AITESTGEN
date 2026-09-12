import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
  faChevronDown,
  faCircleCheck,
  faClock,
  faCompass,
  faDiagramProject,
  faLayerGroup,
  faPlus,
  faTableList,
  faTriangleExclamation,
  faWandMagicSparkles,
} from '@fortawesome/free-solid-svg-icons'
import { api, type HomeApplicationRead, type OverviewStatsRead } from '../api'
import { EmptyState, RunsIllustration } from './EmptyState'
import { applicationStage, relativeTime } from './Home'
import { formatDuration } from './workspace/RunsTab'
import { Skeleton } from './Skeleton'

const POLL_INTERVAL_MS = 15000

// Matches the prototype's PIPE_STAGES — Discovery/Scenarios/Test cases are
// this app's own applicationStage() outcomes; Execution is the one active
// state that stage doesn't carry (a run can still be going after the suite
// is otherwise complete), so it's checked independently and wins ties.
const PIPE_STAGE_LABELS = ['Discovery', 'Scenarios', 'Test cases', 'Execution'] as const

function activePipelineIndex(app: HomeApplicationRead): number | null {
  const { isRunning, scenariosGenerating, suiteGenerating, testRunRunning } = applicationStage(app)
  if (testRunRunning) return 3
  if (suiteGenerating) return 2
  if (scenariosGenerating) return 1
  if (isRunning) return 0
  return null
}

export function Overview({
  onConnectApp,
  onGoApps,
  onOpenApplication,
}: {
  onConnectApp: () => void
  onGoApps: () => void
  onOpenApplication: (application: HomeApplicationRead) => void
}) {
  const [applications, setApplications] = useState<HomeApplicationRead[] | null>(null)
  const [stats, setStats] = useState<OverviewStatsRead | null>(null)
  const [pipeOpen, setPipeOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function refresh() {
      try {
        const rows = await api.getHome()
        if (!cancelled) setApplications(rows)
      } catch {
        // best-effort — a transient failure just skips this refresh
      }
      try {
        const body = await api.getOverviewStats()
        if (!cancelled) setStats(body)
      } catch {
        // best-effort — a transient failure just skips this refresh
      }
    }
    refresh()
    const interval = setInterval(refresh, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  const apps = applications ?? []
  const pipeRows = apps
    .map((app) => ({ app, stageIndex: activePipelineIndex(app) }))
    .filter((row): row is { app: HomeApplicationRead; stageIndex: number } => row.stageIndex !== null)
  const totalTestCases = apps.reduce((sum, a) => sum + a.test_case_count, 0)
  const totalRuns = apps.reduce((sum, a) => sum + a.test_run_count, 0)
  // Gated on status === 'completed', not just pass_rate != null — a run
  // still in progress already has a non-null rate (passed_count / total_count
  // with most of total_count not yet attempted), which would silently count
  // every not-yet-run test as a failure in every metric below. Same gate
  // Home.tsx's own `hasCompletedRun` uses per-app card.
  const ranApps = apps.filter((a) => a.last_test_run_status === 'completed' && a.last_test_run_pass_rate != null)
  // Real totals for the donut's legend — same last-run counts each app's
  // own Runs tab shows, just summed across the workspace.
  const totalPassed = ranApps.reduce((sum, a) => sum + (a.last_test_run_passed_count ?? 0), 0)
  const totalFailed = ranApps.reduce((sum, a) => sum + (a.last_test_run_failed_count ?? 0), 0)
  // "Latest run outcome" is the actual pass/fail split of every app's most
  // recent run, pooled — not avgPassRate below (that's each app's rate
  // averaged, which lets a 5-case app's percentage count the same as a
  // 500-case app's real result).
  const latestRunPassRate = totalPassed + totalFailed === 0 ? null : (totalPassed / (totalPassed + totalFailed)) * 100
  // Weighted by each app's test case count, not a flat average of each app's
  // pass-rate percentage — a flat average lets a 5-case app move the
  // headline number exactly as much as a 500-case app. HomeApplicationRead
  // has no true per-run total_count to pool against directly (only the
  // pre-divided pass_rate fraction plus passed/failed counts, which alone
  // undercount runs with timed-out/errored/blocked results), so
  // test_case_count — the app's current suite size — is the closest
  // existing-data proxy for how much each app's rate should count.
  const passRateWeight = ranApps.reduce((sum, a) => sum + a.test_case_count, 0)
  const avgPassRate =
    passRateWeight === 0
      ? null
      : (ranApps.reduce((sum, a) => sum + (a.last_test_run_pass_rate ?? 0) * a.test_case_count, 0) / passRateWeight) * 100
  // Scoped to ranApps, not all apps — `_health_tier(None)` (backend) reports
  // an application with zero runs as "needs_attention" (its headline says
  // "No tests have run yet", not "tests are failing"), so counting every
  // never-run app as needing attention here would overstate real failures.
  const needsAttentionCount = ranApps.filter((a) => a.last_test_run_health.tier !== 'healthy').length

  // Average of each app's own recent-pass-rate history, aligned from the
  // most-recent run backwards — the only cross-app time series the API
  // exposes (HomeApplicationRead.recent_pass_rates), so this is a real
  // trend, not invented data, even though it isn't calendar-week-aligned
  // like the prototype's illustrative axis labels.
  const maxHistory = Math.max(0, ...apps.map((a) => a.recent_pass_rates.length))
  const trend: number[] = []
  for (let i = 0; i < maxHistory; i++) {
    const valuesAtI = apps
      .map((a) => a.recent_pass_rates[a.recent_pass_rates.length - maxHistory + i])
      .filter((v): v is number => v != null)
    // Same 0-1-to-percentage scaling as avgPassRate above — recent_pass_rates
    // entries are fractions too.
    if (valuesAtI.length > 0) trend.push((valuesAtI.reduce((s, v) => s + v, 0) / valuesAtI.length) * 100)
  }

  const topByCases = [...apps].sort((a, b) => b.test_case_count - a.test_case_count).slice(0, 6)

  const ONE_WEEK_MS = 7 * 24 * 60 * 60 * 1000
  const onboardedThisWeek = apps.filter((a) => Date.now() - new Date(a.created_at).getTime() < ONE_WEEK_MS).length
  // How the average pass rate has moved across the same recent-run history
  // `trend` already aggregates — not calendar "vs last week" (the API has no
  // weekly rollup), just "since the start of the window we have."
  const passTrendDelta = trend.length >= 2 ? trend[trend.length - 1] - trend[0] : null

  const discoveryDates = apps
    .map((a) => a.last_discovery_started_at)
    .filter((d): d is string => d != null)
    .map((d) => new Date(d).getTime())
  const lastDiscoveryAt = discoveryDates.length === 0 ? null : new Date(Math.max(...discoveryDates)).toISOString()
  const appsDiscoveredUnderAWeek = apps.filter(
    (a) => a.last_discovery_started_at != null && Date.now() - new Date(a.last_discovery_started_at).getTime() < ONE_WEEK_MS,
  ).length

  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Overview</h1>
        <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 4 }}>
          Give Vantage a deployed URL. It discovers the app and writes the Playwright suite for it.
        </div>
      </div>

      {pipeRows.length > 0 && (
        <div
          style={{
            background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
            backdropFilter: 'blur(16px) saturate(1.25)',
            border: '1px solid var(--border-1)',
            borderRadius: 14,
            boxShadow: 'var(--panel-shadow)',
            overflow: 'hidden',
          }}
        >
          <div
            onClick={() => setPipeOpen((open) => !open)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '11px 16px',
              cursor: 'pointer',
              borderBottom: pipeOpen ? '1px solid var(--border-2)' : 'none',
            }}
          >
            <FontAwesomeIcon icon={faDiagramProject} style={{ fontSize: 11, color: 'var(--accent-2)' }} />
            <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg)', whiteSpace: 'nowrap' }}>Active pipelines</span>
            <span style={{ fontSize: 11, color: 'var(--fg-4)', whiteSpace: 'nowrap' }}>— {pipeRows.length} in progress</span>
            <span style={{ flex: 1 }} />
            <FontAwesomeIcon
              icon={faChevronDown}
              style={{ fontSize: 10, color: 'var(--fg-4)', transition: 'transform 160ms ease', transform: pipeOpen ? 'rotate(180deg)' : 'none' }}
            />
          </div>
          {pipeOpen &&
            pipeRows.map(({ app, stageIndex }) => {
              const coveragePct = app.journey_count > 0 ? (app.scenario_journeys_covered / app.journey_count) * 100 : 0
              const detail =
                stageIndex === 1
                  ? `${app.scenario_journeys_covered}/${app.journey_count} journeys`
                  : stageIndex === 0
                    ? 'Discovery in progress'
                    : stageIndex === 2
                      ? 'Generating suite…'
                      : 'Run in progress'
              return (
                <div
                  key={app.id}
                  onClick={() => onOpenApplication(app)}
                  className="v2-row-hover"
                  style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 16px', borderBottom: '1px solid var(--border-2)', cursor: 'pointer' }}
                >
                  <div style={{ width: 150, flex: 'none', minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--fg)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{app.name}</div>
                    <div style={{ fontSize: 10.5, color: 'var(--fg-4)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{app.url}</div>
                  </div>
                  <span
                    style={{
                      fontSize: 10.5,
                      fontWeight: 600,
                      padding: '3px 9px',
                      borderRadius: 6,
                      background: 'rgba(30,150,138,0.14)',
                      color: 'var(--accent-2)',
                      border: '1px solid rgba(30,150,138,0.28)',
                      flex: 'none',
                    }}
                  >
                    {PIPE_STAGE_LABELS[stageIndex]}
                  </span>
                  {stageIndex === 1 ? (
                    <div style={{ flex: 1, height: 4, borderRadius: 1000, background: 'var(--chip)', overflow: 'hidden', minWidth: 60 }}>
                      <div style={{ width: `${coveragePct}%`, height: '100%', background: 'var(--accent-2)' }} />
                    </div>
                  ) : (
                    <span style={{ display: 'inline-flex', flex: '1 1 auto', maxWidth: 14, justifyContent: 'center', fontSize: 11, color: 'var(--accent-2)', animation: 'aitg-spin 1s linear infinite' }}>
                      ⟳
                    </span>
                  )}
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', flex: 'none', whiteSpace: 'nowrap' }}>{detail}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500, color: 'var(--accent-2)', width: 32, textAlign: 'right', flex: 'none' }}>
                    {stageIndex === 1 ? `${Math.round(coveragePct)}%` : ''}
                  </span>
                </div>
              )
            })}
        </div>
      )}

      {applications === null ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,minmax(180px,1fr))', gap: 14 }}>
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border-1)', borderRadius: 14, padding: '18px 20px 17px', boxShadow: 'var(--panel-shadow)' }}>
              <Skeleton width={80} height={10} />
              <Skeleton width={70} height={28} style={{ marginTop: 16 }} />
              <Skeleton width={120} height={10} style={{ marginTop: 10 }} />
            </div>
          ))}
        </div>
      ) : apps.length === 0 ? (
        <div
          style={{
            background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
            backdropFilter: 'blur(16px) saturate(1.25)',
            border: '1px solid var(--border-1)',
            borderRadius: 14,
            boxShadow: 'var(--panel-shadow)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            textAlign: 'center',
            padding: '58px 32px 52px',
          }}
        >
          <div style={{ position: 'relative', width: 270, height: 158, marginBottom: 30 }}>
            <div style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', width: 300, height: 300, borderRadius: 1000, background: 'var(--glow)' }} />
            <div style={{ position: 'absolute', left: 0, top: 30, width: 120, height: 96, borderRadius: 12, background: 'var(--panel-2)', border: '1px solid var(--border-2)', boxShadow: '0 16px 34px rgba(0,0,0,0.16)', transform: 'rotate(-5deg)', display: 'flex', flexDirection: 'column', gap: 8, padding: 14 }}>
              <div style={{ width: 44, height: 6, borderRadius: 1000, background: 'var(--chip)' }} />
              <div style={{ flex: 1, borderRadius: 7, background: 'var(--chip)' }} />
            </div>
            <div style={{ position: 'absolute', right: 4, top: 18, width: 120, height: 96, borderRadius: 12, background: 'var(--panel-2)', border: '1px solid var(--border-2)', boxShadow: '0 16px 34px rgba(0,0,0,0.16)', transform: 'rotate(6deg)', display: 'flex', flexDirection: 'column', gap: 8, padding: 14 }}>
              <div style={{ width: 56, height: 6, borderRadius: 1000, background: 'var(--chip)' }} />
              <div style={{ width: 34, height: 6, borderRadius: 1000, background: 'var(--chip)' }} />
              <div style={{ flex: 1, borderRadius: 7, background: 'var(--chip)' }} />
            </div>
            <div style={{ position: 'absolute', left: '50%', bottom: 0, transform: 'translateX(-50%)', width: 74, height: 74, borderRadius: 1000, background: 'var(--panel-hi)', border: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 18px 36px rgba(0,0,0,0.22)' }}>
              <FontAwesomeIcon icon={faCompass} style={{ fontSize: 27, color: 'var(--accent-2)' }} />
            </div>
            <div style={{ position: 'absolute', left: 14, bottom: 16, width: 16, height: 16, borderRadius: 5, background: 'var(--chip)', border: '1px solid var(--border-2)', transform: 'rotate(20deg)' }} />
            <div style={{ position: 'absolute', right: 20, bottom: 24, width: 10, height: 10, borderRadius: 1000, background: 'var(--chip)', border: '1px solid var(--border-2)' }} />
          </div>
          <div style={{ fontSize: 19, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.015em' }}>No applications yet</div>
          <div style={{ fontSize: 13, color: 'var(--fg-3)', marginTop: 9, maxWidth: 470, lineHeight: '21px' }}>
            Once you onboard your first application, this page shows pass rate over time, latest run outcome and suite size for every app in the workspace.
          </div>
          <button
            type="button"
            onClick={onConnectApp}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 38, padding: '0 20px', borderRadius: 8, background: 'var(--accent)', color: '#fff', fontSize: 13.5, fontWeight: 600, cursor: 'pointer', boxShadow: 'var(--accent-glow)', marginTop: 24, border: 'none' }}
          >
            <FontAwesomeIcon icon={faPlus} style={{ fontSize: 11 }} />
            Add application
          </button>
        </div>
      ) : totalRuns === 0 ? (
        // No application has ever been run yet — the stat grid/trend/donut
        // below would all just be dashes and zeros, so show one
        // illustration instead of a wall of empty-looking cards.
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
            subtitle="Pass rate, trend and suite size show up here once any application finishes its first run."
          />
        </div>
      ) : apps.length > 0 ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,minmax(180px,1fr))', gap: 14 }}>
            {[
              {
                label: 'Applications tested',
                icon: faLayerGroup,
                value: String(apps.length),
                delta: onboardedThisWeek > 0 ? { text: `+${onboardedThisWeek}`, good: true } : null,
                sub: `${onboardedThisWeek} onboarded this week`,
              },
              {
                label: 'Test cases generated',
                icon: faTableList,
                value: totalTestCases.toLocaleString(),
                delta: null,
                sub: `${Math.round(totalTestCases / apps.length)} average per application`,
              },
              {
                label: 'Pass rate',
                icon: faCircleCheck,
                value: avgPassRate == null ? '—' : `${avgPassRate.toFixed(1)}%`,
                delta: passTrendDelta == null ? null : { text: `${passTrendDelta >= 0 ? '+' : ''}${passTrendDelta.toFixed(1)} pts`, good: passTrendDelta >= 0 },
                sub: ranApps.length === 0 ? 'No runs yet' : `Across ${ranApps.length} application${ranApps.length === 1 ? '' : 's'}`,
              },
              {
                label: 'Failure rate',
                icon: faTriangleExclamation,
                value: avgPassRate == null ? '—' : `${(100 - avgPassRate).toFixed(1)}%`,
                delta: passTrendDelta == null ? null : { text: `${-passTrendDelta >= 0 ? '+' : ''}${(-passTrendDelta).toFixed(1)} pts`, good: -passTrendDelta <= 0 },
                sub: `${needsAttentionCount} need attention`,
              },
            ].map((k) => (
              <div
                key={k.label}
                style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border-1)', borderRadius: 14, padding: '18px 20px 17px', boxShadow: 'var(--panel-shadow)' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ width: 30, height: 30, flex: 'none', borderRadius: 9, background: 'var(--chip)', border: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-2)' }}>
                    <FontAwesomeIcon icon={k.icon} style={{ fontSize: 12 }} />
                  </span>
                  <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>{k.label}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, marginTop: 16 }}>
                  <div style={{ fontSize: 33, lineHeight: '34px', color: 'var(--fg)', fontWeight: 600, letterSpacing: '-0.026em' }}>{k.value}</div>
                  {k.delta && (
                    <div style={{ fontSize: 11.5, fontWeight: 600, paddingBottom: 4, color: k.delta.good ? 'var(--ok)' : 'var(--bad)' }}>{k.delta.text}</div>
                  )}
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--fg-4)', marginTop: 7 }}>{k.sub}</div>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(330px,1fr))', gap: 14 }}>
            <div style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border-1)', borderRadius: 12, padding: '18px 20px', minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>Pass rate over time</div>
                  <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>Average across every application's recent runs</div>
                </div>
                {trend.length >= 2 && (
                  <div style={{ display: 'flex', gap: 14, fontSize: 11.5, color: 'var(--fg-3)' }}>
                    <span><span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: 2, background: 'var(--ok)', marginRight: 6 }} />Pass %</span>
                    <span><span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: 2, background: 'var(--bad)', marginRight: 6 }} />Failure %</span>
                  </div>
                )}
              </div>
              {trend.length < 2 ? (
                <div style={{ fontSize: 12.5, color: 'var(--fg-4)', padding: '40px 0', textAlign: 'center' }}>Not enough run history yet</div>
              ) : (
                <TrendSvg values={trend} />
              )}
            </div>

            <div style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border-1)', borderRadius: 12, padding: '18px 20px', display: 'flex', flexDirection: 'column' }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>Latest run outcome</div>
              <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>Pooled pass/fail from every application's last run</div>
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '14px 0' }}>
                <PassDonut passRate={latestRunPassRate} />
              </div>
              {latestRunPassRate != null && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 12.5 }}>
                    <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--ok)' }} />
                    <span style={{ flex: 1, color: 'var(--fg-3)' }}>Passed</span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-1)' }}>{totalPassed.toLocaleString()}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 12.5 }}>
                    <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--bad)' }} />
                    <span style={{ flex: 1, color: 'var(--fg-3)' }}>Failed</span>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-1)' }}>{totalFailed.toLocaleString()}</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {(() => {
            const testCasesCard = (
              <div style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border-1)', borderRadius: 12, padding: '18px 20px', minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>Test cases per application</div>
                    <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>Top {topByCases.length} by suite size · pass/fail split</div>
                  </div>
                  <span onClick={onGoApps} style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--accent-hi)', cursor: 'pointer' }}>
                    View all {apps.length}
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {topByCases.map((a) => {
                    // Already a 0-1 fraction (passed_count / total_count) — no /100 needed.
                    const passFrac = a.last_test_run_pass_rate
                    return (
                      <div
                        key={a.id}
                        onClick={() => onOpenApplication(a)}
                        className="v2-row-hover"
                        style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer', borderRadius: 8, margin: '0 -6px', padding: '2px 6px' }}
                      >
                        <div style={{ width: 158, flex: 'none', fontSize: 12.5, color: 'var(--fg-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</div>
                        <div style={{ flex: 1, height: 18, borderRadius: 5, background: 'var(--track)', display: 'flex', overflow: 'hidden' }}>
                          {passFrac != null && (
                            <>
                              <div style={{ width: `${passFrac * 100}%`, background: 'var(--ok)' }} />
                              <div style={{ width: `${(1 - passFrac) * 100}%`, background: 'var(--bad)' }} />
                            </>
                          )}
                        </div>
                        <div style={{ width: 42, flex: 'none', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)' }}>{a.test_case_count}</div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )

            const miniTiles = [
              {
                key: 'duration',
                icon: faClock,
                label: 'Avg run duration',
                value: stats == null ? '—' : formatDuration(stats.avg_run_duration_ms),
                sub: stats == null ? '—' : `Across ${stats.run_count} run${stats.run_count === 1 ? '' : 's'}`,
              },
              {
                key: 'healed',
                icon: faWandMagicSparkles,
                label: 'Self-healed locators',
                value: stats == null ? '—' : String(stats.self_healed_count),
                sub: 'In the last 7 days',
              },
              {
                key: 'discovery',
                icon: faCompass,
                label: 'Last discovery',
                value: lastDiscoveryAt == null ? '—' : relativeTime(lastDiscoveryAt),
                sub: `${appsDiscoveredUnderAWeek} of ${apps.length} apps under 7 days`,
              },
            ]

            function MiniTile({ icon, label, value, sub, flex }: { icon: typeof faCompass; label: string; value: string; sub: string; flex?: number }) {
              return (
                <div style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border-1)', borderRadius: 12, padding: '16px 18px', flex, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <FontAwesomeIcon icon={icon} style={{ fontSize: 12, color: 'var(--accent-hi)' }} />
                    <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>{label}</span>
                  </div>
                  <div style={{ fontSize: 22, lineHeight: '28px', color: 'var(--fg)', marginTop: 8, fontWeight: 600 }}>{value}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--fg-4)', marginTop: 2 }}>{sub}</div>
                </div>
              )
            }

            // Fewer than 3 applications means the "Test cases per application"
            // card is short (1-2 rows) — pairing it with a full 3-tile column
            // would leave that column mostly empty air. Pair it with just the
            // first mini tile instead, and let the other two form their own
            // row below. 3+ applications keeps the original two-column split,
            // with the mini tiles stretched (flex: 1 each) to fill the taller
            // card's full height instead of clustering at the top.
            return topByCases.length >= 3 ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(330px,1fr))', gap: 14 }}>
                {testCasesCard}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {miniTiles.map((t) => (
                    <MiniTile key={t.key} {...t} flex={1} />
                  ))}
                </div>
              </div>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(330px,1fr))', gap: 14 }}>
                  {testCasesCard}
                  <MiniTile {...miniTiles[0]} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(330px,1fr))', gap: 14 }}>
                  <MiniTile {...miniTiles[1]} />
                  <MiniTile {...miniTiles[2]} />
                </div>
              </>
            )
          })()}
        </>
      ) : null}
    </div>
  )
}

// Real aggregate line built from HomeApplicationRead.recent_pass_rates —
// deliberately simpler than the prototype's dual pass/fail polyline with a
// gradient fill (that illustrative version also plots a fail-rate line we
// have no equivalent series for); this one only draws what the API can
// actually back.
function TrendSvg({ values }: { values: number[] }) {
  const width = 620
  const height = 196
  const step = width / Math.max(1, values.length - 1)
  const y = (v: number) => height - (Math.max(0, Math.min(100, v)) / 100) * height
  const points = values.map((v, i) => `${i * step},${y(v)}`).join(' ')
  const areaPoints = `${0},${height} ${points} ${(values.length - 1) * step},${height}`
  // Failure % is the exact complement of the pass-rate series already being
  // plotted — no separate data needed, just 100 minus the same values.
  const failPoints = values.map((v, i) => `${i * step},${y(100 - v)}`).join(' ')
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  function handleMoveAt(clientX: number, rect: DOMRect) {
    const xFrac = (clientX - rect.left) / rect.width
    const idx = Math.round(xFrac * (values.length - 1))
    setHoverIndex(Math.max(0, Math.min(values.length - 1, idx)))
  }

  function handleMove(e: React.MouseEvent<SVGSVGElement>) {
    handleMoveAt(e.clientX, e.currentTarget.getBoundingClientRect())
  }

  // Touch has no hover — without this, the crosshair/tooltip built above
  // only ever worked with a mouse, so touching the chart on a phone/tablet
  // did nothing. A touch drag now scrubs the same crosshair a mouse move does.
  function handleTouch(e: React.TouchEvent<SVGSVGElement>) {
    const touch = e.touches[0]
    if (!touch) return
    handleMoveAt(touch.clientX, e.currentTarget.getBoundingClientRect())
  }

  const hoverPct = hoverIndex != null ? `${(hoverIndex / Math.max(1, values.length - 1)) * 100}%` : null

  return (
    <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-5)', textAlign: 'right', width: 26 }}>
        <span>100</span>
        <span>75</span>
        <span>50</span>
        <span>25</span>
        <span>0</span>
      </div>
      <div style={{ flex: 1, minWidth: 0, position: 'relative' }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          style={{ width: '100%', height, display: 'block', cursor: values.length > 1 ? 'crosshair' : 'default' }}
          onMouseMove={values.length > 1 ? handleMove : undefined}
          onMouseLeave={() => setHoverIndex(null)}
          onTouchStart={values.length > 1 ? handleTouch : undefined}
          onTouchMove={values.length > 1 ? handleTouch : undefined}
          onTouchEnd={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id="overview-trend-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--ok)" stopOpacity={0.28} />
              <stop offset="100%" stopColor="var(--ok)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <line x1={0} y1={2} x2={width} y2={2} stroke="var(--chip)" strokeWidth={1} />
          <line x1={0} y1={height / 2} x2={width} y2={height / 2} stroke="var(--chip)" strokeWidth={1} />
          <line x1={0} y1={height - 2} x2={width} y2={height - 2} stroke="var(--border-2)" strokeWidth={1} />
          <polygon points={areaPoints} fill="url(#overview-trend-fill)" />
          <polyline points={failPoints} fill="none" stroke="var(--bad)" strokeWidth={1.6} strokeLinejoin="round" strokeDasharray="3 4" opacity={0.85} />
          <polyline points={points} fill="none" stroke="var(--ok)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {hoverIndex != null && (
            <g pointerEvents="none">
              <line x1={hoverIndex * step} y1={0} x2={hoverIndex * step} y2={height} stroke="var(--fg-5)" strokeWidth={1} strokeDasharray="3 3" />
              <circle cx={hoverIndex * step} cy={y(values[hoverIndex])} r={4} fill="var(--ok)" stroke="#fff" strokeWidth={1.5} />
              <circle cx={hoverIndex * step} cy={y(100 - values[hoverIndex])} r={4} fill="var(--bad)" stroke="#fff" strokeWidth={1.5} />
            </g>
          )}
        </svg>
        {hoverIndex != null && hoverPct != null && (
          <div
            style={{
              position: 'absolute',
              top: 4,
              left: hoverPct,
              transform: `translateX(${hoverIndex === 0 ? '0%' : hoverIndex === values.length - 1 ? '-100%' : '-50%'})`,
              pointerEvents: 'none',
              background: 'var(--panel)',
              border: '1px solid var(--border-2)',
              borderRadius: 8,
              boxShadow: 'var(--panel-shadow)',
              padding: '6px 10px',
              fontSize: 11.5,
              whiteSpace: 'nowrap',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--ok)' }} />
              <span style={{ color: 'var(--fg-2)' }}>Pass {values[hoverIndex].toFixed(1)}%</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
              <span style={{ width: 6, height: 6, borderRadius: 2, background: 'var(--bad)' }} />
              <span style={{ color: 'var(--fg-2)' }}>Fail {(100 - values[hoverIndex]).toFixed(1)}%</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function PassDonut({ passRate }: { passRate: number | null }) {
  const pass = passRate ?? 0
  const fail = 100 - pass
  const circumference = 2 * Math.PI * 15.9
  return (
    <div style={{ position: 'relative', width: 168, height: 168 }}>
      <svg viewBox="0 0 42 42" style={{ width: 168, height: 168, transform: 'rotate(-90deg)' }}>
        <circle cx={21} cy={21} r={15.9} fill="none" stroke="var(--chip)" strokeWidth={4} />
        {passRate != null && (
          <>
            <circle
              cx={21}
              cy={21}
              r={15.9}
              fill="none"
              stroke="var(--ok)"
              strokeWidth={4}
              strokeDasharray={`${(pass / 100) * circumference} ${circumference}`}
              strokeLinecap="round"
            />
            <circle
              cx={21}
              cy={21}
              r={15.9}
              fill="none"
              stroke="var(--bad)"
              strokeWidth={4}
              strokeDasharray={`${(fail / 100) * circumference} ${circumference}`}
              strokeDashoffset={-(pass / 100) * circumference}
              strokeLinecap="round"
            />
          </>
        )}
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ fontSize: 30, color: 'var(--fg)', lineHeight: '32px', fontWeight: 600, letterSpacing: '-0.02em' }}>
          {passRate == null ? '—' : `${passRate.toFixed(1)}%`}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--fg-4)', marginTop: 2 }}>passed</div>
      </div>
    </div>
  )
}
