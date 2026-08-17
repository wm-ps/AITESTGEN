const DOT_DELAYS = [0, 0.15, 0.3]

function ArrowRightIcon() {
  return (
    <svg width={26} height={26} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  )
}

// Shared "generation in progress" animation — one pulsing icon + bouncing
// dots, first established for Generate Test Suite (TestSuiteResults.tsx) and
// reused everywhere else something is generating in the background
// (scenarios, discovery) so all of these flows read as the same kind of wait
// instead of some showing a percent-fill progress bar and others not.
export function GenerationLoader({
  title,
  caption,
  footer,
}: {
  title: string
  caption?: React.ReactNode
  footer?: React.ReactNode
}) {
  return (
    <div role="status" style={{ textAlign: 'center' }}>
      <div
        aria-hidden="true"
        style={{
          width: 64,
          height: 64,
          borderRadius: 'var(--radius-full)',
          background: 'var(--accent-wash)',
          color: 'var(--accent)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          margin: '0 auto 22px',
          boxSizing: 'border-box',
          animation: 'aitg-transition-icon 0.5s ease-out both, aitg-pulse 1.6s ease-in-out 0.5s infinite',
        }}
      >
        <ArrowRightIcon />
      </div>
      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--ink)', marginBottom: 16 }}>{title}</div>
      <div style={{ display: 'flex', gap: 6, justifyContent: 'center', marginBottom: 16 }}>
        {DOT_DELAYS.map((delay) => (
          <span
            key={delay}
            style={{
              width: 7,
              height: 7,
              borderRadius: 'var(--radius-full)',
              background: 'var(--accent)',
              animation: 'aitg-dot-bounce 1s ease-in-out infinite',
              animationDelay: `${delay}s`,
            }}
          />
        ))}
      </div>
      {caption}
      {footer}
    </div>
  )
}
