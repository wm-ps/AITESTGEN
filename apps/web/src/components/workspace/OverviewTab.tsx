import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, type HealthTier, type OverviewRead } from '../../api'
import { EmptyState, RunsIllustration } from '../EmptyState'

const POLL_INTERVAL_MS = 5000

const HEALTH_COLORS: Record<HealthTier, { background: string; foreground: string }> = {
  healthy: { background: 'var(--good-wash)', foreground: 'var(--good-strong)' },
  needs_attention: { background: 'var(--warn-wash)', foreground: 'var(--warn-strong)' },
  critical: { background: 'var(--danger-wash)', foreground: 'var(--danger-strong)' },
}

// Same gradient-badge formula GenerateSuite/TestSuiteResults already use for
// their hero icon/banner (`135deg, <color> 0%, <color> 65%, rgba(0,0,0,0.22)
// 100%`), just keyed by health tier instead of always `--accent` — the
// health icon and the Pass rate tile are this tab's two "headline" moments,
// so they get the system's own strongest treatment instead of a flat tint.
const HEALTH_GRADIENT: Record<HealthTier, string> = {
  healthy: 'linear-gradient(135deg, var(--good-strong) 0%, var(--good-strong) 65%, rgba(0,0,0,0.22) 100%)',
  needs_attention: 'linear-gradient(135deg, var(--warn-strong) 0%, var(--warn-strong) 65%, rgba(0,0,0,0.22) 100%)',
  critical: 'linear-gradient(135deg, var(--danger-strong) 0%, var(--danger-strong) 65%, rgba(0,0,0,0.22) 100%)',
}

function LayersIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3 3 7.5 12 12l9-4.5z" />
      <path d="M3 12l9 4.5 9-4.5" />
      <path d="M3 16.5l9 4.5 9-4.5" />
    </svg>
  )
}

function CheckCircleIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={12} r={9} />
      <path d="M8.5 12.5l2.3 2.3L15.5 9.5" />
    </svg>
  )
}

function XCircleIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={12} r={9} />
      <path d="M9.5 9.5l5 5M14.5 9.5l-5 5" />
    </svg>
  )
}

function ClockPauseIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={12} r={9} />
      <path d="M12 7.5v5l3 1.7" />
    </svg>
  )
}

// `StatTile`'s `muted` tone fills with `--canvas-wash-alt`, a pale green
// (#eef5f3) — fine as a subtle accent elsewhere, but four of them in a row
// read as a wall of green tiles. This mirrors StatTile's own layout (icon
// chip + value/label) with strictly neutral gray instead, kept local to this
// tab rather than changing the shared tone (other screens still want it).
function NeutralStatTile({
  icon,
  value,
  label,
  delay = 0,
}: {
  icon: ReactNode
  value: string | number
  label: string
  delay?: number
}) {
  return (
    <div
      className="stat-tile-hover"
      style={{
        background: 'var(--canvas)',
        // `--border-hairline` (near-white) against this tile's own white
        // background and the white card-panel behind it left these
        // borderless-looking — bumped to `--border` (still subtle, matches
        // every other bordered panel in the app) so the tile reads as a
        // distinct card instead of blending into its container.
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        boxSizing: 'border-box',
        padding: '12px 15px',
        boxShadow: '0 1px 3px rgba(15,23,42,0.07)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        animation: `aitg-fade-up 0.35s ease-out ${delay}s both`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: 'var(--ink-muted)',
          }}
        >
          {label}
        </span>
        <span aria-hidden="true" style={{ color: 'var(--ink-muted)', display: 'flex' }}>
          {icon}
        </span>
      </div>
      <div style={{ fontSize: 23, fontWeight: 800, color: 'var(--ink)', lineHeight: 1 }}>{value}</div>
    </div>
  )
}

function AlertIcon() {
  return (
    <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 9v4M12 17h.01" />
      <path d="M10.3 3.6 2.5 17a1.8 1.8 0 0 0 1.5 2.7h16a1.8 1.8 0 0 0 1.5-2.7L13.7 3.6a1.8 1.8 0 0 0-3.4 0z" />
    </svg>
  )
}

function HeartPulseIcon() {
  return (
    <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 13l4 4L19 7" />
    </svg>
  )
}

function RunHistoryIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={12} r={9} />
      <path d="M12 7v5l3.5 3.5" />
    </svg>
  )
}

function DiscoveryIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={11} cy={11} r={6.5} />
      <path d="M20 20l-3.8-3.8" />
    </svg>
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

// DESIGN.md's label-section typography (11px/700, uppercase, tracked 0.05em,
// ink-faint permitted since it's a decorative eyebrow, not the information
// itself) — used as the section-header rhythm for this whole tab.
function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        fontSize: 11,
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--ink-faint)',
        marginBottom: 12,
      }}
    >
      {children}
    </div>
  )
}

// Reference bands, not per-point color: the previous version painted each
// dot by its own tier (good/warn/danger) while the line stayed accent —
// two color systems on one series read as "which color means what" instead
// of "is this going up." One accent hue for the whole series (identity);
// the healthy/attention/critical zones are shown as horizontal background
// bands instead, so "did this dip into the red" is a position judgment
// against a fixed backdrop, not a color-decoding exercise per dot.
const TREND_BANDS: { label: string; top: number; height: number; background: string }[] = [
  { label: '≥90%', top: 0, height: 10, background: 'var(--good-wash)' },
  { label: '70–89%', top: 10, height: 20, background: 'var(--warn-wash)' },
  { label: '<70%', top: 30, height: 70, background: 'var(--danger-wash)' },
]
const Y_GRIDLINES = [0, 25, 50, 75, 100]

// A bar per run answers "how many passed" but not "is this trending up or
// down" — a line is the chart people actually read as a trend. Built as a
// stretched SVG polyline/polygon (fine for lines) plus separately
// absolutely-positioned dot markers (so per-point radius/hit-target aren't
// distorted by the non-uniform x/y scaling `preserveAspectRatio="none"`
// produces on the SVG's own circles).
function TrendChart({ trend }: { trend: OverviewRead['trend'] }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  const n = trend.length
  const xPct = (i: number) => (n > 1 ? (i / (n - 1)) * 100 : 50)
  const yPct = (rate: number | null) => 100 - (rate != null ? rate * 100 : 0)

  // Never one label per point (crowds past ~6 runs) — first, last, and up
  // to two evenly-spaced points between them.
  const labeledIndices = useMemo(() => {
    if (n <= 1) return [0]
    if (n <= 4) return trend.map((_, i) => i)
    return Array.from(new Set([0, Math.round((n - 1) / 3), Math.round(((n - 1) * 2) / 3), n - 1]))
  }, [n, trend])

  if (trend.length === 0) {
    return (
      <p className="caption" style={{ fontSize: 12.5, margin: 0 }}>
        No runs yet — trend appears after your first "Run Suite".
      </p>
    )
  }

  const linePoints = trend.map((t, i) => `${xPct(i)},${yPct(t.pass_rate)}`).join(' ')
  const areaPoints = `0,100 ${linePoints} 100,100`

  const latest = trend[n - 1]
  const previous = n > 1 ? trend[n - 2] : null
  const latestPct = latest.pass_rate != null ? Math.round(latest.pass_rate * 100) : null
  const deltaPct =
    latestPct != null && previous?.pass_rate != null ? latestPct - Math.round(previous.pass_rate * 100) : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%' }}>
      {/* No repeat of the raw percentage here — the "Pass rate" stat tile
          above already headlines that number. This chart's own job is the
          trend itself, so only the run-over-run delta (info the tile
          doesn't carry) gets called out. */}
      {deltaPct != null && deltaPct !== 0 && (
        <div
          style={{
            fontSize: 12,
            fontWeight: 600,
            marginBottom: 10,
            color: deltaPct > 0 ? 'var(--good-strong)' : 'var(--danger-strong)',
          }}
        >
          {deltaPct > 0 ? '▲' : '▼'} {Math.abs(deltaPct)} pt{Math.abs(deltaPct) === 1 ? '' : 's'} vs previous run
        </div>
      )}

      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', gap: 8, flex: 1, minHeight: 0 }}>
          {/* Y-axis: an actual scale (0/25/50/75/100), not just the two
              endpoints — reading "where between 0 and 100 is this line"
              shouldn't require guessing the middle. */}
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '100%', flexShrink: 0 }}>
            {Y_GRIDLINES.slice()
              .reverse()
              .map((v, i) => (
                <span key={v} className="caption" style={{ fontSize: 10, lineHeight: 1, transform: 'translateY(-50%)' }}>
                  {i === 0 ? `${v}%` : v}
                </span>
              ))}
          </div>

          <div style={{ position: 'relative', flex: 1, height: '100%' }}>
            {/* Threshold bands — the fixed backdrop the line is read against. */}
            {TREND_BANDS.map((band) => (
              <div
                key={band.label}
                aria-hidden="true"
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  top: `${band.top}%`,
                  height: `${band.height}%`,
                  background: band.background,
                }}
              />
            ))}
            {Y_GRIDLINES.map((v) => (
              <div
                key={v}
                aria-hidden="true"
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  top: `${100 - v}%`,
                  borderTop: '1px dashed var(--border-hairline)',
                }}
              />
            ))}

            {n > 1 && (
              <svg
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                aria-hidden="true"
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
              >
                <polygon points={areaPoints} fill="var(--accent-wash-soft)" stroke="none" />
                <polyline
                  points={linePoints}
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
              </svg>
            )}

            {trend.map((t, i) => (
              <div
                key={t.run_id}
                onMouseEnter={() => setHoverIndex(i)}
                onMouseLeave={() => setHoverIndex((cur) => (cur === i ? null : cur))}
                style={{
                  position: 'absolute',
                  left: `${xPct(i)}%`,
                  top: 0,
                  bottom: 0,
                  // A hit target wider than the visible dot — a 7px circle is
                  // an unreliable mouse target; the invisible strip is what
                  // actually catches hover.
                  width: Math.max(16, 100 / Math.max(n - 1, 1)),
                  transform: 'translateX(-50%)',
                  cursor: 'pointer',
                }}
              >
                <span
                  style={{
                    position: 'absolute',
                    left: '50%',
                    top: `${yPct(t.pass_rate)}%`,
                    width: hoverIndex === i ? 9 : 6,
                    height: hoverIndex === i ? 9 : 6,
                    borderRadius: '50%',
                    background: 'var(--accent)',
                    border: '2px solid var(--canvas)',
                    transform: 'translate(-50%, -50%)',
                    boxShadow: '0 1px 2px rgba(15,23,42,0.25)',
                    transition: 'width 0.1s ease, height 0.1s ease',
                  }}
                />
                {hoverIndex === i && (
                  <div
                    role="tooltip"
                    style={{
                      position: 'absolute',
                      left: '50%',
                      top: `${yPct(t.pass_rate)}%`,
                      transform: 'translate(-50%, calc(-100% - 12px))',
                      background: 'var(--ink)',
                      color: '#FFFFFF',
                      borderRadius: 6,
                      padding: '5px 9px',
                      fontSize: 11,
                      whiteSpace: 'nowrap',
                      pointerEvents: 'none',
                      boxShadow: '0 4px 10px rgba(15,23,42,0.25)',
                      zIndex: 1,
                    }}
                  >
                    <div style={{ fontWeight: 700 }}>
                      {t.pass_rate != null ? `${Math.round(t.pass_rate * 100)}%` : 'No results'}
                    </div>
                    <div style={{ opacity: 0.8 }}>{formatDateTime(t.created_at)}</div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, marginLeft: 26, flexShrink: 0 }}>
          {trend.map((t, i) =>
            labeledIndices.includes(i) ? (
              <span key={t.run_id} className="caption" style={{ fontSize: 10.5 }}>
                {formatDateTime(t.created_at)}
              </span>
            ) : null,
          )}
        </div>
      </div>
    </div>
  )
}

function PlayIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M6 4.5v15l13-7.5z" />
    </svg>
  )
}

export function OverviewTab({
  applicationId,
  onRunSuite,
  running,
}: {
  applicationId: string
  onRunSuite: () => void
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
    return (
      <p className="caption" style={{ fontSize: 12.5 }}>
        Loading overview…
      </p>
    )
  }

  // No run has ever happened for this application — health/pass-rate/trend
  // are all meaningless zeros, so show one tab-level illustration instead of
  // three separate cards each explaining their own absence of data.
  if (!overview.latest_run) {
    return (
      <div className="card-panel" style={{ padding: 24 }}>
        <EmptyState
          illustration={<RunsIllustration />}
          title="No test runs yet"
          subtitle="Health, pass rate, and trend will show up here once your first run finishes."
          action={
            <button
              type="button"
              className="button-primary"
              disabled={running}
              onClick={onRunSuite}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
            >
              <PlayIcon />
              {running ? 'Running…' : 'Run Suite'}
            </button>
          }
        />
      </div>
    )
  }

  const healthColors = HEALTH_COLORS[overview.health.tier]

  return (
    <div className="card-panel" style={{ padding: 24 }}>
      <SectionLabel>Application health</SectionLabel>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 18,
          padding: '18px 20px',
          marginBottom: 24,
          borderRadius: 'var(--radius-lg)',
          background: healthColors.background,
          animation: 'aitg-fade-up 0.4s ease-out both',
        }}
      >
        <span
          aria-hidden="true"
          style={{
            display: 'inline-flex',
            width: 52,
            height: 52,
            borderRadius: 'var(--radius-full)',
            background: HEALTH_GRADIENT[overview.health.tier],
            color: '#FFFFFF',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            boxShadow: '0 8px 18px -6px rgba(15,23,42,0.35), inset 0 1px 0 rgba(255,255,255,0.35)',
          }}
        >
          {overview.health.tier === 'healthy' ? <HeartPulseIcon /> : <AlertIcon />}
        </span>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: healthColors.foreground, marginBottom: 3, letterSpacing: '-0.01em' }}>
            {overview.health.tier === 'healthy'
              ? 'Healthy'
              : overview.health.tier === 'needs_attention'
                ? 'Needs Attention'
                : 'Critical'}
          </div>
          <div style={{ fontSize: 14, color: 'var(--ink-secondary)' }}>{overview.health.headline}</div>
        </div>
      </div>

      {/* Test results leads — the numbers that matter most get top billing,
          ahead of Activity/trend context below. */}
      <SectionLabel>Test results</SectionLabel>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 12,
          marginBottom: 20,
        }}
      >
        <NeutralStatTile icon={<LayersIcon />} value={overview.total_tests} label="Total tests" delay={0.05} />
        <NeutralStatTile icon={<CheckCircleIcon />} value={overview.passed} label="Passed" delay={0.1} />
        <NeutralStatTile icon={<XCircleIcon />} value={overview.failed} label="Failed" delay={0.15} />
        <NeutralStatTile icon={<ClockPauseIcon />} value={overview.not_run} label="Not run" delay={0.2} />
      </div>

      {/* Activity and the trend chart side by side. Same border/shadow fix as
          NeutralStatTile above: --border-hairline with no background reads as
          invisible against this tab's white card-panel, so both panels get
          --border + a soft shadow to read as distinct cards. No `alignItems`
          override on the grid — default `stretch` gives both columns the
          row's full height, and each column's own panel fills it via
          `flex: 1`, so the shorter Activity panel matches the chart panel's
          height instead of sitting next to empty space. */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1.5fr',
          gap: 20,
          animation: 'aitg-fade-up 0.4s ease-out 0.1s both',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <SectionLabel>Activity</SectionLabel>
          <div
            style={{
              padding: '18px 20px',
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              gap: 16,
              borderRadius: 'var(--radius-lg)',
              background: 'var(--canvas)',
              border: '1px solid var(--border)',
              boxShadow: '0 1px 3px rgba(15,23,42,0.07)',
            }}
          >
            <div style={{ display: 'flex', gap: 12 }}>
              <span
                aria-hidden="true"
                style={{
                  display: 'inline-flex',
                  width: 32,
                  height: 32,
                  borderRadius: 9,
                  background: 'var(--border-hairline)',
                  color: 'var(--ink-secondary)',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <RunHistoryIcon />
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', marginBottom: 6 }}>Latest run</div>
                {overview.latest_run ? (
                  <>
                    <div className="caption" style={{ fontSize: 12, marginBottom: 4 }}>
                      {formatDateTime(overview.latest_run.created_at)}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--ink-secondary)' }}>
                      {overview.latest_run.passed_count} passed · {overview.latest_run.failed_count} failed
                      {overview.latest_run.blocked_count > 0 && ` · ${overview.latest_run.blocked_count} skipped`}
                      {overview.latest_run.duration_ms != null &&
                        ` · ${(overview.latest_run.duration_ms / 1000).toFixed(0)}s`}
                    </div>
                  </>
                ) : (
                  <p className="caption" style={{ fontSize: 12.5, margin: 0 }}>
                    No runs yet.
                  </p>
                )}
              </div>
            </div>

            <div style={{ borderTop: '1px solid var(--border-hairline)', paddingTop: 16, display: 'flex', gap: 12 }}>
              <span
                aria-hidden="true"
                style={{
                  display: 'inline-flex',
                  width: 32,
                  height: 32,
                  borderRadius: 9,
                  background: 'var(--border-hairline)',
                  color: 'var(--ink-secondary)',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <DiscoveryIcon />
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', marginBottom: 6 }}>Last discovery</div>
                <p className="caption" style={{ fontSize: 12.5, margin: 0 }}>
                  {overview.last_discovery_started_at ? formatDateTime(overview.last_discovery_started_at) : 'Never run'}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <SectionLabel>Pass rate trend</SectionLabel>
          <div
            style={{
              padding: '18px 20px',
              flex: 1,
              display: 'flex',
              borderRadius: 'var(--radius-lg)',
              background: 'var(--canvas)',
              border: '1px solid var(--border)',
              boxShadow: '0 1px 3px rgba(15,23,42,0.07)',
            }}
          >
            <TrendChart trend={overview.trend} />
          </div>
        </div>
      </div>
    </div>
  )
}
