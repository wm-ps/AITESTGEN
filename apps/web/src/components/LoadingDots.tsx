const DELAYS = [0, 0.15, 0.3]

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
