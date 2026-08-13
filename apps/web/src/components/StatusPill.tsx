// `Complete` (green), `Failed` (red, Story 2.4), and `Paused` (amber, Story
// 2.17) have no documented pill variant in DESIGN.md — only `Running`
// (signal, pulsing) is named. Filled in here per DESIGN.md's own
// semantic-color rule (green = healthy/generated, red = failing, amber =
// attention/incomplete), not a literal citation.
//
// discovery_completed/journeys_generated/scenarios_generated share
// running's accent color (still "in motion"); suite_generated is the only
// non-running state that gets green (true finish line).
const COLORS: Record<string, { background: string; foreground: string }> = {
  running: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  discovery_completed: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  journeys_generated: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  scenarios_generated: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  suite_generated: { background: 'var(--good-wash)', foreground: 'var(--good-strong)' },
  complete: { background: 'var(--good-wash)', foreground: 'var(--good-strong)' },
  failed: { background: 'var(--danger-wash)', foreground: 'var(--danger-strong)' },
  paused: { background: 'var(--warn-wash)', foreground: 'var(--warn-strong)' },
  // Run All Tests feature — TestRun-level (pending/running reuse the
  // existing "still in motion" accent treatment above) and per-test-result
  // states below.
  completed: { background: 'var(--good-wash)', foreground: 'var(--good-strong)' },
  blocked: { background: 'var(--warn-wash)', foreground: 'var(--warn-strong)' },
  pending: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  passed: { background: 'var(--good-wash)', foreground: 'var(--good-strong)' },
  timed_out: { background: 'var(--danger-wash)', foreground: 'var(--danger-strong)' },
  errored: { background: 'var(--danger-wash)', foreground: 'var(--danger-strong)' },
  not_run: { background: 'var(--canvas-wash-alt)', foreground: 'var(--ink-muted)' },
}

const LABELS: Record<string, string> = {
  running: 'Discovery in Progress',
  discovery_completed: 'Discovery completed',
  journeys_generated: 'Journeys generated',
  scenarios_generated: 'Scenarios generated',
  suite_generated: 'Test suite generated',
  completed: 'Completed',
  // "Skipped", not "Blocked" — `blocked_count`/status="blocked" are vestigial
  // now that ExecutionPolicy gating was removed (see the `ponytail:` note in
  // `activities.py`); relabeled only, no new status/column.
  blocked: 'Skipped',
  pending: 'Pending',
  passed: 'Passed',
  failed: 'Failed',
  timed_out: 'Timed Out',
  errored: 'Errored',
  not_run: 'Not Run',
}

export function StatusPill({
  status,
  pulsing,
  label: labelOverride,
}: {
  status: string
  pulsing?: boolean
  // `LABELS` is shared across two different domains (Application discovery
  // stage vs. TestRun/TestResult status) that both happen to use the bare
  // string "running" for different things ("Discovery in Progress" is wrong
  // copy for a running TestRun) — callers outside the discovery domain pass
  // an explicit override rather than this component guessing from context.
  label?: string
}) {
  const label = labelOverride ?? LABELS[status] ?? status.charAt(0).toUpperCase() + status.slice(1)
  const colors = COLORS[status] ?? COLORS.running
  const showPulse = pulsing ?? status === 'running'
  return (
    <span
      className="status-pill"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        background: colors.background,
        color: colors.foreground,
      }}
    >
      {showPulse && (
        <span
          className="status-pill-pulse-dot"
          aria-hidden="true"
          style={{
            width: 6,
            height: 6,
            borderRadius: 'var(--radius-full)',
            background: colors.foreground,
          }}
        />
      )}
      {label}
    </span>
  )
}
