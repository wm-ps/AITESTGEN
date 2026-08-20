import { Logo } from './Logo'

export function VantageWordmark({ fontSize = 27 }: { fontSize?: number }) {
  return (
    <span
      style={{
        fontSize,
        fontWeight: 700,
        letterSpacing: '-0.03em',
        backgroundImage: 'linear-gradient(135deg, var(--ink) 20%, var(--accent) 100%)',
        WebkitBackgroundClip: 'text',
        backgroundClip: 'text',
        color: 'transparent',
      }}
    >
      Vantage
    </span>
  )
}

export function VantageBrand({
  wordmarkSize = 27,
  markSize = 44,
}: {
  wordmarkSize?: number
  markSize?: number
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <Logo size={markSize} />
      <VantageWordmark fontSize={wordmarkSize} />
    </div>
  )
}
