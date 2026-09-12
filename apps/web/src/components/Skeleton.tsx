// Shared shimmering placeholder for any "data not loaded yet" spot — used
// instead of a spinner/LoadingDots wherever the real content has a known
// shape (a table row, a card, a stat tile), so the loading state previews
// that shape rather than just signaling "something is happening."
export function Skeleton({
  width = '100%',
  height = 14,
  radius = 6,
  style,
}: {
  width?: number | string
  height?: number | string
  radius?: number
  style?: React.CSSProperties
}) {
  return (
    <div
      aria-hidden="true"
      className="aitg-skeleton"
      style={{
        width,
        height,
        borderRadius: radius,
        background: 'linear-gradient(90deg, var(--chip) 25%, var(--border-2) 50%, var(--chip) 75%)',
        backgroundSize: '200% 100%',
        ...style,
      }}
    />
  )
}

export function SkeletonRows({ count, height = 14, gap = 8 }: { count: number; height?: number; gap?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap }}>
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} height={height} width={i % 3 === 2 ? '60%' : '100%'} />
      ))}
    </div>
  )
}
