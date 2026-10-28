// Busy state for a button (Run/Regenerate/Save/Sign in/...): the label
// followed by the same BouncingDots every running operation's status uses
// (StatusPill, Overview, Healing chip), so every "this is working" indicator
// in the app reads as one family.
export function LoadingDots({ label }: { label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      {label}
      <BouncingDots size={3.5} />
    </span>
  )
}

// Three bouncing dots for a running operation's status (Discovery,
// Scenario/Test Generation, Test Execution, Self-healing) and every busy
// button (via LoadingDots above).
export function BouncingDots({ size = 4 }: { size?: number }) {
  return (
    <span aria-hidden="true" style={{ display: 'inline-flex', alignItems: 'center', gap: size * 0.75, flexShrink: 0 }}>
      {[0, 0.16, 0.32].map((delay) => (
        <span
          key={delay}
          style={{
            width: size,
            height: size,
            borderRadius: 'var(--radius-full)',
            background: 'currentColor',
            animation: `aitg-dot-bounce 1.1s ease-in-out ${delay}s infinite`,
          }}
        />
      ))}
    </span>
  )
}
