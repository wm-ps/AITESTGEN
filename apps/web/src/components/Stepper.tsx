const STEPS = [
  { key: 'connect-app', label: 'Connect App' },
  { key: 'discover', label: 'Discover Journeys' },
  { key: 'review', label: 'Review Scenarios' },
  { key: 'generate', label: 'Generate Suite' },
] as const

export function Stepper({ current }: { current: 'connect-app' | 'discover' | 'review' }) {
  const currentIndex = STEPS.findIndex((step) => step.key === current)

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        padding: `var(--space-3) var(--content-x)`,
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      {STEPS.map((step, index) => {
        const done = index < currentIndex
        const active = index === currentIndex
        return (
          <div key={step.key} style={{ display: 'flex', alignItems: 'center' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                padding: '5px 10px 5px 5px',
                borderRadius: 'var(--radius-full)',
                background: active ? 'var(--signal-wash)' : 'transparent',
              }}
            >
              <span
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 'var(--radius-full)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: 11,
                  flexShrink: 0,
                  background: done ? 'var(--signal)' : 'var(--paper)',
                  color: done ? 'var(--signal-ink)' : active ? 'var(--signal)' : 'var(--ink-faint)',
                  border: `2px solid ${done || active ? 'var(--signal)' : 'var(--border-strong)'}`,
                }}
              >
                {done ? '✓' : index + 1}
              </span>
              <span
                style={{
                  fontSize: 12.5,
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  color: active || done ? 'var(--ink)' : 'var(--ink-faint)',
                }}
              >
                {step.label}
              </span>
            </div>
            {index < STEPS.length - 1 && (
              <span style={{ width: 28, height: 1, background: 'var(--border)', margin: '0 4px' }} />
            )}
          </div>
        )
      })}
    </div>
  )
}
