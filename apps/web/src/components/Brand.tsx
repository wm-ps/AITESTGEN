import wmLogo from '../assets/wm-logo.svg'

export function WaveQaMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: 0 }}>
      <circle cx="10" cy="10" r="7.5" fill="none" stroke="currentColor" strokeWidth="2.6" />
      <line x1="15.3" y1="15.3" x2="21.5" y2="21.5" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" />
      <path d="M6.8 10.2L9 12.4L13.2 7.6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function WaveQaWordmark({ fontSize = 27 }: { fontSize?: number }) {
  return (
    <span style={{ fontSize, letterSpacing: '-0.03em', display: 'inline-flex', alignItems: 'center' }}>
      <span style={{ fontWeight: 400, color: 'var(--ink-secondary)' }}>wave</span>
      <span style={{ color: 'var(--accent)', margin: '0 -1px 0 2px', display: 'inline-flex' }}>
        <WaveQaMark size={Math.round(fontSize * 0.95)} />
      </span>
      <span style={{ fontWeight: 500, color: 'var(--accent)' }}>A</span>
    </span>
  )
}

export function WaveQaBrand({
  wordmarkSize = 27,
  wmHeight = 28,
  tagline = false,
}: {
  wordmarkSize?: number
  wmHeight?: number
  tagline?: boolean
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <img src={wmLogo} alt="WaveMaker" height={wmHeight} style={{ display: 'block' }} />
      <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1 }}>
        <WaveQaWordmark fontSize={wordmarkSize} />
        {tagline && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
            <span style={{ flex: 1, height: 1, background: 'var(--border-strong)', opacity: 0.5 }} />
            <span
              style={{
                fontSize: 7,
                fontWeight: 700,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: 'var(--ink-faint)',
                whiteSpace: 'nowrap',
              }}
            >
              For Web Apps
            </span>
          </span>
        )}
      </div>
    </div>
  )
}
