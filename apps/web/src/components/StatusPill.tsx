// `Complete` (green) and `Failed` (red, Story 2.4) have no documented pill
// variant in DESIGN.md — only `Running` (signal, pulsing) is named. Filled
// in here per DESIGN.md's own semantic-color rule (green = healthy/generated,
// red = failing), not a literal citation.
const COLORS: Record<string, { background: string; foreground: string }> = {
  running: { background: 'var(--signal-wash)', foreground: 'var(--signal)' },
  complete: { background: 'var(--good-wash)', foreground: 'var(--good)' },
  failed: { background: 'var(--danger-wash)', foreground: 'var(--danger)' },
}

export function StatusPill({ status }: { status: string }) {
  const label = status.charAt(0).toUpperCase() + status.slice(1)
  const colors = COLORS[status] ?? COLORS.running
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        background: colors.background,
        color: colors.foreground,
        borderRadius: 'var(--radius-full)',
        fontSize: 11.5,
        fontWeight: 650,
        padding: '4px 10px',
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
