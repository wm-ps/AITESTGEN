import { Skeleton as ShadcnSkeleton } from './ui/skeleton'

// Shared shimmering placeholder for any "data not loaded yet" spot — used
// instead of a spinner/LoadingDots wherever the real content has a known
// shape (a table row, a card, a stat tile), so the loading state previews
// that shape rather than just signaling "something is happening." Thin
// wrapper around shadcn/ui's Skeleton primitive (components/ui/skeleton.tsx)
// — keeps this file's width/height/radius prop API so none of this app's
// existing call sites need to change.
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
    <ShadcnSkeleton
      aria-hidden="true"
      style={{
        width,
        height,
        borderRadius: radius,
        ...style,
      }}
    />
  )
}

// Every row is full width — these stand in for table/card rows (their real
// content always spans the row), not paragraph text, so a shortened row
// would just look like it failed to load rather than like a placeholder.
export function SkeletonRows({ count, height = 14, gap = 8 }: { count: number; height?: number; gap?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap }}>
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} height={height} width="100%" />
      ))}
    </div>
  )
}
