import type { ComponentProps } from 'react'
import { cn } from '../../lib/utils'

// shadcn/ui's canonical Skeleton primitive (https://ui.shadcn.com/docs/components/skeleton),
// adapted to this app's Tailwind-without-preflight setup (see index.css) —
// `animate-pulse` swapped for the app's existing shimmer keyframe
// (aitg-skeleton-shimmer, defined in index.css) so it keeps the slower,
// premium sweep instead of a flat opacity pulse.
function Skeleton({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        'rounded-md bg-[linear-gradient(90deg,var(--chip)_35%,color-mix(in_srgb,var(--border-2)_55%,var(--chip))_50%,var(--chip)_65%)] bg-[length:200%_100%] animate-[aitg-skeleton-shimmer_1.9s_ease-in-out_infinite]',
        className,
      )}
      {...props}
    />
  )
}

export { Skeleton }
