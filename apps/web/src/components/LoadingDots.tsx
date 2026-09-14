// Ring spinner for a busy button (Run/Regenerate/Save/Sign in/...) — same
// currentColor + border-top-color trick and `aitg-spin` keyframe StatusPill's
// own in-motion dot already uses, so every "this is working" indicator in
// the app reads as one family.
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

// LoadingDots keeps its old name/label prop for every existing call site,
// but now renders the same Spinner as everything else instead of bouncing
// dots, so button loading states read as one consistent experience app-wide.
export function LoadingDots({ label }: { label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <Spinner size={12} />
      {label}
    </span>
  )
}
