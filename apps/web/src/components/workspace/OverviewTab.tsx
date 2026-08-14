import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, type HealthTier, type OverviewRead } from '../../api'
import { StatTile } from '../TestSuiteResults'

const POLL_INTERVAL_MS = 5000

const HEALTH_COLORS: Record<HealthTier, { background: string; foreground: string }> = {
  healthy: { background: 'var(--good-wash)', foreground: 'var(--good-strong)' },
  needs_attention: { background: 'var(--warn-wash)', foreground: 'var(--warn-strong)' },
  critical: { background: 'var(--danger-wash)', foreground: 'var(--danger-strong)' },
}

function tierForPassRate(passRate: number | null): HealthTier {
  if (passRate == null) return 'needs_attention'
  if (passRate >= 0.9) return 'healthy'
  if (passRate >= 0.7) return 'needs_attention'
  return 'critical'
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

function DashIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={12} r={9} />
      <path d="M9 12h6" />
    </svg>
  )
}

function PercentIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 5 5 19" />
      <circle cx={7} cy={7} r={2} />
      <circle cx={17} cy={17} r={2} />
    </svg>
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
        No runs yet — trend appears after the first "Run Suite".
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
  const latestColors = HEALTH_COLORS[tierForPassRate(latest.pass_rate)]

  return (
    <div style={{ display: 'flex', gap: 24, alignItems: 'stretch', height: '100%', width: '100%' }}>
      <div style={{ flexShrink: 0, minWidth: 90, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <div style={{ fontSize: 30, fontWeight: 700, color: latestColors.foreground, lineHeight: 1 }}>
          {latestPct != null ? `${latestPct}%` : '—'}
        </div>
        <div className="caption" style={{ fontSize: 11.5, marginTop: 4 }}>
          latest pass rate
        </div>
        {deltaPct != null && deltaPct !== 0 && (
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              marginTop: 6,
              color: deltaPct > 0 ? 'var(--good-strong)' : 'var(--danger-strong)',
            }}
          >
            {deltaPct > 0 ? '▲' : '▼'} {Math.abs(deltaPct)} pt{Math.abs(deltaPct) === 1 ? '' : 's'} vs previous run
          </div>
        )}
      </div>

      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', gap: 8, flex: 1, minHeight: 0 }}>
          {/* Y-axis: an actual scale (0/25/50/75/100), not just the two
              endpoints — reading "where between 0 and 100 is this line"
              shouldn't require guessing the middle. */}
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '100%', flexShrink: 0 }}>
            {Y_GRIDLINES.slice()
              .reverse()
              .map((v) => (
                <span key={v} className="caption" style={{ fontSize: 10, lineHeight: 1, transform: 'translateY(-50%)' }}>
                  {v}%
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

export function OverviewTab({ applicationId }: { applicationId: string }) {
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

  const healthColors = HEALTH_COLORS[overview.health.tier]

  return (
    <div>
      <SectionLabel>Application health</SectionLabel>
      <div
        className="card-panel"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          padding: '18px 20px',
          marginBottom: 20,
          background: healthColors.background,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            display: 'inline-flex',
            width: 44,
            height: 44,
            borderRadius: 'var(--radius-full)',
            background: 'var(--canvas)',
            color: healthColors.foreground,
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            boxShadow: '0 2px 6px rgba(15,23,42,0.1)',
          }}
        >
          {overview.health.tier === 'healthy' ? <HeartPulseIcon /> : <AlertIcon />}
        </span>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: healthColors.foreground, marginBottom: 2 }}>
            {overview.health.tier === 'healthy'
              ? 'Healthy'
              : overview.health.tier === 'needs_attention'
                ? 'Needs Attention'
                : 'Critical'}
          </div>
          <div style={{ fontSize: 13, color: 'var(--ink-secondary)' }}>{overview.health.headline}</div>
        </div>
      </div>

      {/* Test results leads — the numbers that matter most get top billing,
          ahead of Activity/trend context below. */}
      <SectionLabel>Test results</SectionLabel>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 20 }}>
        <StatTile icon={<ClipboardCheckIcon />} value={overview.total_tests} label="Total tests" tone="muted" />
        <StatTile icon={<CheckIcon />} value={overview.passed} label="Passed" tone="good" />
        <StatTile icon={<XIcon />} value={overview.failed} label="Failed" tone="danger" />
        <StatTile icon={<DashIcon />} value={overview.not_run} label="Not run" tone="muted" />
        <StatTile
          icon={<PercentIcon />}
          value={overview.pass_rate != null ? `${Math.round(overview.pass_rate * 100)}%` : '—'}
          label="Pass rate"
          tone={tierForPassRate(overview.pass_rate) === 'healthy' ? 'good' : tierForPassRate(overview.pass_rate) === 'critical' ? 'danger' : 'warn'}
        />
      </div>

      {/* Activity (one card, not two) and the trend chart side by side. No
          `alignItems` override on the grid — default `stretch` gives both
          columns the row's full height, and each column's own card-panel
          fills it via `flex: 1`, so the shorter Activity card matches the
          chart card's height instead of sitting next to empty space. */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: 20 }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <SectionLabel>Activity</SectionLabel>
          <div
            className="card-panel"
            style={{
              padding: '16px 20px',
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              gap: 16,
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
                  background: 'var(--accent-wash-soft)',
                  color: 'var(--accent)',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <RunHistoryIcon />
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)', marginBottom: 6 }}>Latest run</div>
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
                  background: 'var(--accent-wash-soft)',
                  color: 'var(--accent)',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <DiscoveryIcon />
              </span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)', marginBottom: 6 }}>Last discovery</div>
                <p className="caption" style={{ fontSize: 12.5, margin: 0 }}>
                  {overview.last_discovery_started_at ? formatDateTime(overview.last_discovery_started_at) : 'Never run'}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <SectionLabel>Pass rate trend</SectionLabel>
          <div className="card-panel" style={{ padding: '18px 20px', flex: 1, display: 'flex' }}>
            <TrendChart trend={overview.trend} />
          </div>
        </div>
      </div>
    </div>
  )
}
