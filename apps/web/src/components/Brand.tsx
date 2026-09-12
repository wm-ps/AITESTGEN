import vantageLogo from '../assets/vantage-logo-v2.png'

// Original mark restored (double-chevron + wordmark), but recolored via CSS
// mask instead of baked-in PNG color — so it always tracks var(--accent)
// (theme color) without needing a re-export every time the palette changes.
export function VantageBrand({ markSize = 44 }: { markSize?: number }) {
  return (
    <span
      role="img"
      aria-label="Vantage"
      style={{
        display: 'inline-block',
        height: markSize,
        width: markSize * (315 / 61),
        backgroundColor: 'var(--accent)',
        WebkitMaskImage: `url(${vantageLogo})`,
        maskImage: `url(${vantageLogo})`,
        WebkitMaskRepeat: 'no-repeat',
        maskRepeat: 'no-repeat',
        WebkitMaskSize: 'contain',
        maskSize: 'contain',
        WebkitMaskPosition: 'left center',
        maskPosition: 'left center',
      }}
    />
  )
}
