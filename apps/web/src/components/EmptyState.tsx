import type { ReactNode } from 'react'

// One illustration style system reused everywhere ("nothing here yet" for
// Runs, Trend, Journeys, Scenarios, ...) so every empty state reads as the
// same family — same line weight, same soft backdrop, same teal accent — but
// each scene draws the specific thing that's missing rather than a generic
// empty box, so the picture itself explains what will show up here.

export function RunsIllustration() {
  return (
    <svg width={64} height={64} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <rect x="6" y="10" width="42" height="30" rx="4" stroke="var(--ink-faint)" strokeWidth={1.6} />
      <line x1="6" y1="17.5" x2="48" y2="17.5" stroke="var(--ink-faint)" strokeWidth={1.6} />
      <rect x="12" y="23" width="5" height="5" rx="1.2" stroke="var(--ink-faint)" strokeWidth={1.4} />
      <line x1="21" y1="25.5" x2="40" y2="25.5" stroke="var(--ink-faint)" strokeWidth={1.4} strokeLinecap="round" />
      <rect x="12" y="31" width="5" height="5" rx="1.2" stroke="var(--ink-faint)" strokeWidth={1.4} />
      <line x1="21" y1="33.5" x2="36" y2="33.5" stroke="var(--ink-faint)" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="46" cy="42" r="14" fill="var(--accent)" />
      <path d="M42 36.5 52.5 42 42 47.5Z" fill="var(--accent-ink)" />
    </svg>
  )
}

export function TrendIllustration() {
  return (
    <svg width={64} height={64} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <path d="M10 8v42h44" stroke="var(--ink-faint)" strokeWidth={1.4} strokeLinecap="round" />
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
      <path d="M18 30 Q30 18 38 27 T55 15" stroke="var(--ink-faint)" strokeWidth={1.6} strokeLinecap="round" strokeDasharray="1 5.5" fill="none" />
      <circle cx="38" cy="27" r="3.2" fill="none" stroke="var(--ink-faint)" strokeWidth={1.4} strokeDasharray="2 2.5" />
      <circle cx="55" cy="15" r="3.2" fill="none" stroke="var(--ink-faint)" strokeWidth={1.4} strokeDasharray="2 2.5" />
    </svg>
  )
}

export function ScenariosIllustration() {
  return (
    <svg width={64} height={64} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <rect x="9" y="8" width="30" height="40" rx="4" stroke="var(--ink-faint)" strokeWidth={1.6} />
      <line x1="16" y1="19" x2="32" y2="19" stroke="var(--ink-faint)" strokeWidth={1.4} strokeLinecap="round" />
      <line x1="16" y1="27" x2="32" y2="27" stroke="var(--ink-faint)" strokeWidth={1.4} strokeLinecap="round" />
      <line x1="16" y1="35" x2="26" y2="35" stroke="var(--ink-faint)" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="45" cy="41" r="12" fill="var(--accent)" />
      <path d="M39.5 41 43.5 45 50.5 36.5" stroke="var(--accent-ink)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" fill="none" />
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
        background: 'linear-gradient(135deg, var(--canvas-wash-alt) 0%, var(--accent-wash-soft) 100%)',
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
      <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>{title}</div>
      <div className="caption" style={{ fontSize: 12, marginTop: 4 }}>
        {subtitle}
      </div>
      {action && <div style={{ marginTop: 'var(--space-4)' }}>{action}</div>}
    </div>
  )
}
