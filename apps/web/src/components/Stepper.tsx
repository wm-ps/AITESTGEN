const STEPS = [
  { key: 'connect-app', label: 'Connect App' },
  { key: 'discover', label: 'Discover Journeys' },
  { key: 'review', label: 'Review Scenarios' },
  { key: 'generate', label: 'Generate Suite' },
] as const

export type StepKey = (typeof STEPS)[number]['key']

function NavButton({
  label,
  onClick,
  children,
}: {
  label: string
  onClick?: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      className="button-secondary"
      aria-label={label}
      disabled={!onClick}
      onClick={onClick}
      style={{ padding: '6px 14px', opacity: onClick ? 1 : 0.4, cursor: onClick ? 'pointer' : 'default' }}
    >
      {children}
    </button>
  )
}

// `furthestCount` is how many steps (0-4) are fully completed — independent
// of `current`, which is just whichever screen is being viewed right now.
// They diverge once Previous/Next or a Stepper click lets you revisit an
// earlier completed step without losing its checkmark (Story: wizard
// back-navigation).
export function Stepper({
  current,
  furthestCount,
  onStepClick,
  onPrevious,
  onNext,
}: {
  current: StepKey
  furthestCount: number
  onStepClick?: (key: StepKey) => void
  onPrevious?: () => void
  onNext?: () => void
}) {
  const currentIndex = STEPS.findIndex((step) => step.key === current)

  return (
    <div style={{ margin: '22px 32px 6px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20 }}>
      <NavButton label="Previous step" onClick={onPrevious}>
        ← Previous
      </NavButton>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {STEPS.map((step, index) => {
          const done = index < furthestCount
          const active = !done && index === currentIndex
          const clickable = index <= furthestCount && !!onStepClick
          return (
            <div key={step.key} style={{ display: 'flex', alignItems: 'center' }}>
              <div
                role={clickable ? 'button' : undefined}
                tabIndex={clickable ? 0 : undefined}
                onClick={clickable ? () => onStepClick(step.key) : undefined}
                onKeyDown={
                  clickable
                    ? (e) => {
                        if (e.key === 'Enter' || e.key === ' ') onStepClick(step.key)
                      }
                    : undefined
                }
                style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: clickable ? 'pointer' : 'default' }}
              >
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
                    background: index < furthestCount ? 'var(--accent)' : 'var(--accent-wash-strong)',
                    margin: '0 14px',
                  }}
                />
              )}
            </div>
          )
        })}
      </div>
      <NavButton label="Next step" onClick={onNext}>
        Next →
      </NavButton>
    </div>
  )
}
