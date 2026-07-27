// `Complete` (green) and `Failed` (red, Story 2.4) have no documented pill
// variant in DESIGN.md — only `Running` (signal, pulsing) is named. Filled
// in here per DESIGN.md's own semantic-color rule (green = healthy/generated,
// red = failing), not a literal citation.
const COLORS: Record<string, { background: string; foreground: string }> = {
  running: { background: 'var(--accent-wash)', foreground: 'var(--accent)' },
  complete: { background: 'var(--good-wash)', foreground: 'var(--good-strong)' },
  failed: { background: 'var(--danger-wash)', foreground: 'var(--danger-strong)' },
}

export function StatusPill({ status }: { status: string }) {
  const label = status.charAt(0).toUpperCase() + status.slice(1)
  const colors = COLORS[status] ?? COLORS.running
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
      {status === 'running' && (
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
