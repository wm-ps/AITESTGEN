const STEPS = [
  { key: 'connect-app', label: 'Connect App' },
  { key: 'discover', label: 'Discover Journeys' },
  { key: 'review', label: 'Review Scenarios' },
  { key: 'generate', label: 'Generate Suite' },
] as const

export function Stepper({
  current,
  allComplete = false,
}: {
  current: 'connect-app' | 'discover' | 'review' | 'generate'
  allComplete?: boolean
}) {
  const currentIndex = STEPS.findIndex((step) => step.key === current)

  return (
    <div style={{ margin: '22px 32px 6px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      {STEPS.map((step, index) => {
        const done = allComplete || index < currentIndex
        const active = !allComplete && index === currentIndex
        return (
          <div key={step.key} style={{ display: 'flex', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span
                style={{
                  width: 23,
                  height: 23,
                  borderRadius: 'var(--radius-full)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: 11,
                  flexShrink: 0,
                  background: done ? 'var(--accent)' : active ? 'var(--canvas)' : 'var(--accent-wash-soft)',
                  color: done ? 'var(--accent-ink)' : active ? 'var(--accent)' : 'var(--ink-muted)',
                  border: `1.5px solid ${done || active ? 'var(--accent)' : 'var(--accent-wash-strong)'}`,
                  boxShadow: active ? '0 0 0 4px var(--accent-wash)' : 'none',
                }}
              >
                {done ? '✓' : index + 1}
              </span>
              <span
                style={{
                  fontSize: 12.5,
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  color: active || done ? 'var(--ink)' : 'var(--ink-secondary)',
                }}
              >
                {step.label}
              </span>
            </div>
            {index < STEPS.length - 1 && (
              <span
                style={{
                  width: 34,
                  height: 1.5,
                  borderRadius: 1,
                  background: index < currentIndex || allComplete ? 'var(--accent)' : 'var(--accent-wash-strong)',
                  margin: '0 14px',
                }}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
