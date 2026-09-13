import type { ComponentType, ReactNode } from 'react'
import { faClock, faFileCode, faFileZipper, faFlaskVial, faListCheck } from '@fortawesome/free-solid-svg-icons'
import { faIcon } from '../faIcon'

const ListCheck = faIcon(faListCheck)
const FileCode = faIcon(faFileCode)
const FlaskVial = faIcon(faFlaskVial)
const FileZipper = faIcon(faFileZipper)
const Clock = faIcon(faClock)

// One illustration style system reused everywhere ("nothing here yet" for
// Runs, Trend, Journeys, Scenarios, ...) so every empty state reads as the
// same family — same line weight, same soft backdrop, same teal accent — but
// each scene draws the specific thing that's missing rather than a generic
// empty box, so the picture itself explains what will show up here.

// Static twin of GenerationLoader's browser-window mockup (prototype's
// "No scenarios/cases/runs yet" scenes) — same 196x130 stage, panel and
// badge geometry, just without the pulse/scan/ring animation since nothing
// is in progress here.
function BrowserCardIllustration({ icon: Icon }: { icon: ComponentType<{ size?: number }> }) {
  return (
    <div aria-hidden="true" style={{ position: 'relative', width: 196, height: 130 }}>
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: '50%',
          transform: 'translate(-50%,-50%)',
          width: 230,
          height: 230,
          borderRadius: 1000,
          background: 'var(--glow)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: 22,
          top: 34,
          width: 112,
          height: 82,
          borderRadius: 12,
          background: 'var(--panel-2)',
          border: '1px solid var(--border-2)',
          boxShadow: '0 16px 34px rgba(18,22,54,0.14)',
        }}
      >
        <div style={{ height: 22, borderBottom: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', gap: 4, paddingLeft: 9 }}>
          <span style={{ width: 5, height: 5, borderRadius: 1000, background: 'var(--border-3)' }} />
          <span style={{ width: 5, height: 5, borderRadius: 1000, background: 'var(--border-3)' }} />
          <span style={{ width: 5, height: 5, borderRadius: 1000, background: 'var(--border-3)' }} />
        </div>
      </div>
      <div style={{ position: 'absolute', left: 33, top: 68, width: 56, height: 6, borderRadius: 1000, background: 'var(--chip)' }} />
      <div style={{ position: 'absolute', left: 33, top: 82, width: 80, height: 6, borderRadius: 1000, background: 'var(--chip)' }} />
      <div style={{ position: 'absolute', left: 33, top: 96, width: 40, height: 6, borderRadius: 1000, background: 'var(--chip)' }} />
      <div
        style={{
          position: 'absolute',
          right: 14,
          top: 8,
          width: 60,
          height: 60,
          borderRadius: 1000,
          background: 'var(--panel-hi)',
          border: '1px solid var(--border-2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 14px 30px rgba(18,22,54,0.16)',
          color: 'var(--accent-2)',
        }}
      >
        <Icon size={22} />
      </div>
      <div style={{ position: 'absolute', left: 2, bottom: 16, width: 14, height: 14, borderRadius: 1000, border: '1px solid var(--border-3)' }} />
    </div>
  )
}

// Static twin of the "package ready to download" folder scene (prototype's
// "Nothing to export yet") — a tabbed folder shape instead of the browser
// card, same 196x130 stage and badge geometry as BrowserCardIllustration.
function FolderIllustration({ icon: Icon }: { icon: ComponentType<{ size?: number }> }) {
  return (
    <div aria-hidden="true" style={{ position: 'relative', width: 196, height: 130 }}>
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: '50%',
          transform: 'translate(-50%,-50%)',
          width: 230,
          height: 230,
          borderRadius: 1000,
          background: 'var(--glow)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: 44,
          top: 36,
          width: 90,
          height: 68,
          borderRadius: '0 10px 10px 10px',
          background: 'var(--panel-2)',
          border: '1px solid var(--border-2)',
          boxShadow: '0 16px 34px rgba(18,22,54,0.14)',
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: -13,
            width: 40,
            height: 13,
            borderRadius: '6px 6px 0 0',
            background: 'var(--panel-2)',
            border: '1px solid var(--border-2)',
            borderBottom: 'none',
          }}
        />
      </div>
      <div style={{ position: 'absolute', left: 58, top: 56, width: 52, height: 6, borderRadius: 1000, background: 'var(--chip)' }} />
      <div style={{ position: 'absolute', left: 58, top: 70, width: 36, height: 6, borderRadius: 1000, background: 'var(--chip)' }} />
      <div
        style={{
          position: 'absolute',
          right: 6,
          top: 4,
          width: 58,
          height: 58,
          borderRadius: 1000,
          background: 'var(--panel-hi)',
          border: '1px solid var(--border-2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 14px 30px rgba(18,22,54,0.16)',
          color: 'var(--accent-2)',
        }}
      >
        <Icon size={21} />
      </div>
      <div style={{ position: 'absolute', right: 0, bottom: 2, width: 20, height: 20, borderRadius: 7, background: 'var(--chip)', border: '1px solid var(--border-2)', transform: 'rotate(18deg)' }} />
    </div>
  )
}

export function RunsIllustration() {
  return <BrowserCardIllustration icon={FlaskVial} />
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
  return <BrowserCardIllustration icon={ListCheck} />
}

export function TestCasesIllustration() {
  return <BrowserCardIllustration icon={FileCode} />
}

export function DownloadIllustration() {
  return <FolderIllustration icon={FileZipper} />
}

export function SchedulesIllustration() {
  return <BrowserCardIllustration icon={Clock} />
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
  variant = 'icon',
}: {
  illustration: ReactNode
  title: string
  subtitle: string
  action?: ReactNode
  /** 'scene' is the prototype's full glass-panel card (BrowserCardIllustration/
   * FolderIllustration, which already draw their own glow) — 'icon' is the
   * older small-icon-in-a-squircle treatment everything else here still uses. */
  variant?: 'icon' | 'scene'
}) {
  if (variant === 'scene') {
    return (
      <div
        style={{
          background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
          backdropFilter: 'blur(16px) saturate(1.25)',
          border: '1px solid var(--border)',
          borderRadius: 14,
          boxShadow: 'var(--panel-shadow)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '62px 24px 66px',
          textAlign: 'center',
        }}
      >
        <div style={{ marginBottom: 28 }}>{illustration}</div>
        <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.01em' }}>{title}</div>
        <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 7, maxWidth: 380, lineHeight: '20px' }}>{subtitle}</div>
        {action && <div style={{ marginTop: 22 }}>{action}</div>}
      </div>
    )
  }
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
