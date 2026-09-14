import vantageLogo from '../assets/vantage-logo-v2.png'
import omnewaveLogo from '../assets/omnewave-logo.svg'

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

// Fetched from omnewave.com's own header (wp-content/uploads/2026/03/Group-1948760417.svg,
// icon + "Omnewave" wordmark baked into one flat-color SVG). Rendered whole (not cropped to
// just the icon) at a size tall enough for the wordmark to actually read, and in its own
// brand red (not mask-recolored like VantageBrand) — it's a third-party mark, not our theme.
export function OmnewaveBrand({ markSize = 22 }: { markSize?: number }) {
  return <img src={omnewaveLogo} alt="Omnewave" style={{ display: 'inline-block', height: markSize, width: 'auto', verticalAlign: 'middle' }} />
}
