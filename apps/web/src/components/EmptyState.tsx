import type { ReactNode } from 'react'

// One illustration style system reused everywhere ("nothing here yet" for
// Runs, Trend, Journeys, Scenarios, ...) so every empty state reads as the
// same family — same line weight, same soft backdrop, same teal accent — but
// each scene draws the specific thing that's missing rather than a generic
// empty box, so the picture itself explains what will show up here.

export function RunsIllustration() {
  // A browser chrome (traffic-light dots + address bar), not a generic
  // list-in-a-box — reads unambiguously as "a test run driving a real
  // browser," matching Journeys'/Scenarios' subject-specific scenes instead
  // of the same rect+lines glyph every other illustration here also used.
  return (
    <svg width={64} height={64} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <rect x="6" y="10" width="42" height="30" rx="4" stroke="var(--fg-5)" strokeWidth={1.6} />
      <line x1="6" y1="17.5" x2="48" y2="17.5" stroke="var(--fg-5)" strokeWidth={1.6} />
      <circle cx="11" cy="13.75" r="1.3" fill="var(--fg-5)" />
      <circle cx="15.5" cy="13.75" r="1.3" fill="var(--fg-5)" />
      <circle cx="20" cy="13.75" r="1.3" fill="var(--fg-5)" />
      <rect x="25" y="12.3" width="19" height="2.9" rx="1.45" stroke="var(--fg-5)" strokeWidth={1.1} />
      <line x1="12" y1="24" x2="34" y2="24" stroke="var(--fg-5)" strokeWidth={1.4} strokeLinecap="round" />
      <line x1="12" y1="30" x2="40" y2="30" stroke="var(--fg-5)" strokeWidth={1.4} strokeLinecap="round" />
      <line x1="12" y1="36" x2="28" y2="36" stroke="var(--fg-5)" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="46" cy="42" r="14" fill="var(--accent)" />
      <path d="M42 36.5 52.5 42 42 47.5Z" fill="var(--accent-ink)" />
    </svg>
  )
}

export function TrendIllustration() {
  return (
    <svg width={64} height={64} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <path d="M10 8v42h44" stroke="var(--fg-5)" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="20" cy="38" r="3.4" fill="var(--accent)" />
      <path d="M20 38 Q34 34 46 19" stroke="var(--accent)" strokeWidth={1.6} strokeLinecap="round" strokeDasharray="1 5" fill="none" />
      <circle cx="46" cy="19" r="3" fill="none" stroke="var(--accent)" strokeWidth={1.4} strokeDasharray="2 2.5" />
    </svg>
  )
}

export function JourneysIllustration() {
  return (
    <svg width={64} height={64} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      {/* A map pin (the journey's start) with the mapped route beyond it
          gone — dashed, not drawn — and its waypoints left hollow: this is
          "removed", not "not discovered yet". */}
      <path
        d="M12 26c-4.5 0-8 3.4-8 7.8 0 5.6 8 14.2 8 14.2s8-8.6 8-14.2c0-4.4-3.5-7.8-8-7.8Z"
        fill="var(--accent)"
      />
      <circle cx="12" cy="33.5" r="2.6" fill="var(--accent-ink)" />
      <path d="M18 30 Q30 18 38 27 T55 15" stroke="var(--fg-5)" strokeWidth={1.6} strokeLinecap="round" strokeDasharray="1 5.5" fill="none" />
      <circle cx="38" cy="27" r="3.2" fill="none" stroke="var(--fg-5)" strokeWidth={1.4} strokeDasharray="2 2.5" />
      <circle cx="55" cy="15" r="3.2" fill="none" stroke="var(--fg-5)" strokeWidth={1.4} strokeDasharray="2 2.5" />
    </svg>
  )
}

export function AccessDeniedIllustration({ size = 64 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <path
        d="M32 8 58 52H6Z"
        fill="var(--danger-wash)"
        stroke="var(--danger)"
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
      <line x1="32" y1="24" x2="32" y2="37" stroke="var(--danger-strong)" strokeWidth={2.6} strokeLinecap="round" />
      <circle cx="32" cy="44.5" r="1.8" fill="var(--danger-strong)" />
    </svg>
  )
}

export function ScenariosIllustration() {
  return (
    <svg width={64} height={64} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <rect x="9" y="8" width="30" height="40" rx="4" stroke="var(--fg-5)" strokeWidth={1.6} />
      <line x1="16" y1="19" x2="32" y2="19" stroke="var(--fg-5)" strokeWidth={1.4} strokeLinecap="round" />
      <line x1="16" y1="27" x2="32" y2="27" stroke="var(--fg-5)" strokeWidth={1.4} strokeLinecap="round" />
      <line x1="16" y1="35" x2="26" y2="35" stroke="var(--fg-5)" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="45" cy="41" r="12" fill="var(--accent)" />
      <path d="M39.5 41 43.5 45 50.5 36.5" stroke="var(--accent-ink)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

export function TestCasesIllustration() {
  // A checklist (checkbox + label per row, one already ticked) — reads as
  // "test cases," not a generic spreadsheet grid, matching Journeys'/
  // Scenarios' subject-specific scenes instead of a plain table glyph.
  return (
    <svg width={64} height={64} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <rect x="8" y="8" width="34" height="40" rx="4" stroke="var(--fg-5)" strokeWidth={1.6} />
      <rect x="13" y="16" width="6" height="6" rx="1.6" fill="var(--accent)" />
      <path d="M14.6 19 16.4 20.8 19.4 17" stroke="var(--accent-ink)" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <line x1="23" y1="19" x2="37" y2="19" stroke="var(--fg-5)" strokeWidth={1.4} strokeLinecap="round" />
      <rect x="13" y="27" width="6" height="6" rx="1.6" stroke="var(--fg-5)" strokeWidth={1.4} />
      <line x1="23" y1="30" x2="37" y2="30" stroke="var(--fg-5)" strokeWidth={1.4} strokeLinecap="round" />
      <rect x="13" y="38" width="6" height="6" rx="1.6" stroke="var(--fg-5)" strokeWidth={1.4} />
      <line x1="23" y1="41" x2="33" y2="41" stroke="var(--fg-5)" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="46" cy="42" r="14" fill="var(--accent)" />
      <path d="M40.5 42h11M40.5 37.5h11M40.5 46.5h7" stroke="var(--accent-ink)" strokeWidth={2} strokeLinecap="round" />
    </svg>
  )
}

export function DownloadIllustration() {
  // A zip archive (folded corner + dashed seam down the middle), not a
  // plain generic folder — reads as "downloadable project package" on its
  // own, matching Journeys'/Scenarios' subject-specific scenes.
  return (
    <svg width={64} height={64} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <path d="M10 10a3 3 0 0 1 3-3h13l6 6v33a3 3 0 0 1-3 3H13a3 3 0 0 1-3-3Z" stroke="var(--fg-5)" strokeWidth={1.6} strokeLinejoin="round" />
      <path d="M26 7v6h6" stroke="var(--fg-5)" strokeWidth={1.6} strokeLinejoin="round" />
      <line x1="19" y1="15" x2="19" y2="45" stroke="var(--fg-5)" strokeWidth={1.4} strokeDasharray="3 3" />
      <rect x="16" y="15" width="6" height="4" fill="var(--fg-5)" />
      <rect x="16" y="23" width="6" height="4" fill="var(--fg-5)" />
      <rect x="16" y="31" width="6" height="4" fill="var(--fg-5)" />
      <circle cx="46" cy="42" r="14" fill="var(--accent)" />
      <path d="M46 35.5v11M40.5 42 46 47.5 51.5 42" stroke="var(--accent-ink)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

export function SchedulesIllustration() {
  return (
    <svg width={64} height={64} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <rect x="8" y="12" width="34" height="34" rx="4" stroke="var(--fg-5)" strokeWidth={1.6} />
      <line x1="8" y1="21" x2="42" y2="21" stroke="var(--fg-5)" strokeWidth={1.6} />
      <line x1="16" y1="8" x2="16" y2="16" stroke="var(--fg-5)" strokeWidth={1.6} strokeLinecap="round" />
      <line x1="34" y1="8" x2="34" y2="16" stroke="var(--fg-5)" strokeWidth={1.6} strokeLinecap="round" />
      <rect x="15" y="27" width="5" height="5" rx="1.2" stroke="var(--fg-5)" strokeWidth={1.4} />
      <rect x="24" y="27" width="5" height="5" rx="1.2" stroke="var(--fg-5)" strokeWidth={1.4} />
      <rect x="15" y="36" width="5" height="5" rx="1.2" stroke="var(--fg-5)" strokeWidth={1.4} />
      <circle cx="46" cy="42" r="14" fill="var(--accent)" />
      <path d="M46 34.5v7.5l5.5 3.5" stroke="var(--accent-ink)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

// Soft, slightly irregular backdrop (not a plain circle) — a squircle blob
// reads as illustration staging, a perfect circle reads as an icon badge.
function IllustrationBackdrop({ children }: { children: ReactNode }) {
  return (
    <div
      aria-hidden="true"
      style={{
        display: 'inline-flex',
        width: 96,
        height: 96,
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: '42% 58% 53% 47% / 45% 40% 60% 55%',
        background: 'linear-gradient(135deg, var(--hover) 0%, var(--accent-wash-soft) 100%)',
        marginBottom: 'var(--space-4)',
      }}
    >
      {children}
    </div>
  )
}

export function EmptyState({
  illustration,
  title,
  subtitle,
  action,
}: {
  illustration: ReactNode
  title: string
  subtitle: string
  action?: ReactNode
}) {
  return (
    <div style={{ textAlign: 'center', padding: '48px 20px' }}>
      <IllustrationBackdrop>{illustration}</IllustrationBackdrop>
      <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg-2)' }}>{title}</div>
      <div className="caption" style={{ fontSize: 12, marginTop: 4 }}>
        {subtitle}
      </div>
      {action && <div style={{ marginTop: 'var(--space-4)' }}>{action}</div>}
    </div>
  )
}
