const DELAYS = [0, 0.15, 0.3]

// Small ring spinner for a busy *button* (Run/Regenerate/Save) — same
// currentColor + border-top-color trick and `aitg-spin` keyframe StatusPill's
// own in-motion dot already uses, so every "this is working" indicator in
// the app reads as one family. LoadingDots (bouncing dots) stays for
// full-width submit buttons (forms/dialogs) where it already reads fine;
// this is for compact inline buttons where three dots read as fussier than
// a single spinner.
export function Spinner({ size = 12 }: { size?: number }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: 'var(--radius-full)',
        border: '1.5px solid color-mix(in srgb, currentColor 25%, transparent)',
        borderTopColor: 'currentColor',
        animation: 'aitg-spin 0.7s linear infinite',
        flexShrink: 0,
      }}
    />
  )
}

export function LoadingDots({ label }: { label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      {label}
      <span style={{ display: 'inline-flex', gap: 3, marginLeft: 2 }} aria-hidden="true">
        {DELAYS.map((delay) => (
          <span
            key={delay}
            style={{
              width: 4,
              height: 4,
              borderRadius: 'var(--radius-full)',
              background: 'currentColor',
              animation: 'aitg-dot-bounce 1s ease-in-out infinite',
              animationDelay: `${delay}s`,
            }}
          />
        ))}
      </span>
    </span>
  )
}
