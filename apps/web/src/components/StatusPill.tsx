// `Complete` (green), `Failed` (red, Story 2.4), and `Paused` (amber, Story
// 2.17) have no documented pill variant in DESIGN.md — only `Running`
// (signal, pulsing) is named. Filled in here per DESIGN.md's own
// semantic-color rule (green = healthy/generated, red = failing, amber =
// attention/incomplete), not a literal citation.
//
// discovery_completed/journeys_generated/scenarios_generated share
// running's accent color (still "in motion"); suite_generated is the only
// non-running state that gets green (true finish line).
const STATUS_COLORS: Record<string, { background: string; foreground: string }> = {
  running: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  discovery_completed: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  journeys_generated: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  scenarios_generated: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  generating_scenarios: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  generating_tests: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  suite_generated: { background: 'var(--good-wash)', foreground: 'var(--good-strong)' },
  // Home card overrides (Story: Home card redesign) — `suite_generated`
  // once Workspace is actually enterable, and an in-progress "Run All
  // Tests" TestRun, which is a different axis from discovery/generation
  // and must not be confused with `running` (discovery) above.
  ready_to_execute: { background: 'var(--good-wash)', foreground: 'var(--good-strong)' },
  test_run_running: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
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
  // Post-execution pass-rate badge (Home card, Runs tab, Overview tab) —
  // shares `_health_tier`'s tier names (apps/api/src/api/main.py) so the
  // wording/color is one vocabulary everywhere it appears.
  healthy: { background: 'var(--good-wash)', foreground: 'var(--good-strong)' },
  needs_attention: { background: 'var(--warn-wash)', foreground: 'var(--warn-strong)' },
  critical: { background: 'var(--danger-wash)', foreground: 'var(--danger-strong)' },
}

const LABELS: Record<string, string> = {
  running: 'Discovery in Progress',
  discovery_completed: 'Discovery completed',
  journeys_generated: 'Journeys generated',
  scenarios_generated: 'Scenarios generated',
  generating_scenarios: 'Generating scenarios',
  generating_tests: 'Generating test cases',
  suite_generated: 'Test suite generated',
  ready_to_execute: 'Ready to run',
  test_run_running: 'Running',
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
  healthy: 'Healthy',
  needs_attention: 'Needs Attention',
  critical: 'Critical',
}

export function StatusPill({
  status,
  pulsing,
  label: labelOverride,
  variant = 'pill',
}: {
  status: string
  pulsing?: boolean
  // `LABELS` is shared across two different domains (Application discovery
  // stage vs. TestRun/TestResult status) that both happen to use the bare
  // string "running" for different things ("Discovery in Progress" is wrong
  // copy for a running TestRun) — callers outside the discovery domain pass
  // an explicit override rather than this component guessing from context.
  label?: string
  // 'inline' drops the tinted pill chrome for a dashboard-list-row look
  // (colored dot + plain text, e.g. Vercel/Linear deployment status) —
  // same color data, no background/padding/shadow.
  variant?: 'pill' | 'inline'
}) {
  const label = labelOverride ?? LABELS[status] ?? status.charAt(0).toUpperCase() + status.slice(1)
  const colors = STATUS_COLORS[status] ?? STATUS_COLORS.running
  const showPulse = pulsing ?? status === 'running'
  const inline = variant === 'inline'
  return (
    <span
      className={inline ? undefined : 'status-pill'}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        background: inline ? 'none' : colors.background,
        color: inline ? 'var(--ink-secondary)' : colors.foreground,
        fontSize: inline ? 12.5 : undefined,
        fontWeight: inline ? 600 : undefined,
      }}
    >
      {/* A leading dot always shows, not only while pulsing — reads as a
          proper status indicator (like a build/CI chip) instead of plain
          tinted text. While in motion it becomes a spinning ring instead of
          a solid dot — reads as "actively working" rather than a blink. */}
      {showPulse ? (
        <span
          aria-hidden="true"
          style={{
            width: 9,
            height: 9,
            borderRadius: 'var(--radius-full)',
            border: '1.5px solid color-mix(in srgb, currentColor 25%, transparent)',
            borderTopColor: 'currentColor',
            color: colors.foreground,
            flexShrink: 0,
            animation: 'aitg-spin 0.7s linear infinite',
          }}
        />
      ) : (
        <span
          aria-hidden="true"
          style={{
            width: 6,
            height: 6,
            borderRadius: 'var(--radius-full)',
            background: colors.foreground,
            flexShrink: 0,
          }}
        />
      )}
      {label}
    </span>
  )
}
