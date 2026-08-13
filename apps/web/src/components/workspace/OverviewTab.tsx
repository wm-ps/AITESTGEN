import { useEffect, useState } from 'react'
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

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function TrendChart({ trend }: { trend: OverviewRead['trend'] }) {
  if (trend.length === 0) {
    return (
      <p className="caption" style={{ fontSize: 12.5 }}>
        No runs yet — trend appears after the first "Run Suite".
      </p>
    )
  }
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 72 }}>
      {trend.map((point) => {
        const tier = tierForPassRate(point.pass_rate)
        const colors = HEALTH_COLORS[tier]
        const heightPct = point.pass_rate != null ? Math.max(6, Math.round(point.pass_rate * 100)) : 6
        return (
          <div
            key={point.run_id}
            title={`${formatDateTime(point.created_at)} — ${point.pass_rate != null ? `${Math.round(point.pass_rate * 100)}%` : 'no results'}`}
            style={{
              flex: 1,
              height: `${heightPct}%`,
              minHeight: 4,
              borderRadius: 3,
              background: colors.foreground,
              opacity: 0.85,
            }}
          />
        )
      })}
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
      <div
        className="card-panel"
        style={{
          padding: '16px 20px',
          marginBottom: 20,
          background: healthColors.background,
          borderColor: healthColors.foreground,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 700, color: healthColors.foreground, marginBottom: 2 }}>
          {overview.health.tier === 'healthy'
            ? 'Healthy'
            : overview.health.tier === 'needs_attention'
              ? 'Needs Attention'
              : 'Critical'}
        </div>
        <div style={{ fontSize: 13, color: 'var(--ink-secondary)' }}>{overview.health.headline}</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 20 }}>
        <StatTile icon={<ClipboardCheckIcon />} value={overview.total_tests} label="Total tests" />
        <StatTile icon={<CheckIcon />} value={overview.passed} label="Passed" />
        <StatTile icon={<XIcon />} value={overview.failed} label="Failed" />
        <StatTile icon={<DashIcon />} value={overview.not_run} label="Not run" />
        <StatTile
          icon={<PercentIcon />}
          value={overview.pass_rate != null ? `${Math.round(overview.pass_rate * 100)}%` : '—'}
          label="Pass rate"
        />
      </div>

      <div className="card-panel" style={{ padding: '16px 20px', marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)', marginBottom: 12 }}>Pass rate trend</div>
        <TrendChart trend={overview.trend} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div className="card-panel" style={{ padding: '16px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)', marginBottom: 8 }}>Latest run</div>
          {overview.latest_run ? (
            <>
              <div className="caption" style={{ fontSize: 12, marginBottom: 6 }}>
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
        <div className="card-panel" style={{ padding: '16px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)', marginBottom: 8 }}>Last discovery</div>
          <p className="caption" style={{ fontSize: 12.5, margin: 0 }}>
            {overview.last_discovery_started_at ? formatDateTime(overview.last_discovery_started_at) : 'Never run'}
          </p>
        </div>
      </div>
    </div>
  )
}
