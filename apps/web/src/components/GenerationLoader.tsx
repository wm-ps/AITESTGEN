import type { ComponentType } from 'react'

// Shared "generation in progress" animation — a pulsing browser-window
// mockup with a scan-line sweep, an icon badge with two expanding rings,
// three staggered status bullets, and an optional progress bar. One shared
// recipe (prototype's Journeys/Scenarios/Test-cases loaders are the same
// animation with a different icon + copy) reused across discovery, scenario
// generation and suite generation so all three read as the same kind of
// wait instead of three different-looking spinners.
export function GenerationLoader({
  icon: Icon,
  title,
  body,
  bullets,
  percent,
  caption,
  footer,
}: {
  icon: ComponentType<{ size?: number }>
  title: string
  body?: string
  bullets?: string[]
  /** 0-100 — omit when there's no reliable per-stage total to divide by (see ImportProgress's own note: a fabricated percent reads as more precise than it is). */
  percent?: number
  caption?: React.ReactNode
  footer?: React.ReactNode
}) {
  return (
    <div
      role="status"
      style={{
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '58px 24px 60px',
      }}
    >
      <div aria-hidden="true" style={{ position: 'relative', width: 196, height: 130, marginBottom: 28 }}>
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
            overflow: 'hidden',
          }}
        >
          <div style={{ height: 22, borderBottom: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', gap: 4, paddingLeft: 9 }}>
            <span style={{ width: 5, height: 5, borderRadius: 1000, background: 'var(--border-3)' }} />
            <span style={{ width: 5, height: 5, borderRadius: 1000, background: 'var(--border-3)' }} />
            <span style={{ width: 5, height: 5, borderRadius: 1000, background: 'var(--border-3)' }} />
          </div>
          <div style={{ padding: '12px 11px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ width: 56, height: 6, borderRadius: 1000, background: 'var(--chip)', animation: 'v2-pulse 1.5s ease-in-out infinite' }} />
            <div style={{ width: 80, height: 6, borderRadius: 1000, background: 'var(--chip)', animation: 'v2-pulse 1.5s ease-in-out .25s infinite' }} />
            <div style={{ width: 40, height: 6, borderRadius: 1000, background: 'var(--chip)', animation: 'v2-pulse 1.5s ease-in-out .5s infinite' }} />
          </div>
          <div
            style={{
              position: 'absolute',
              left: 0,
              top: 22,
              width: '100%',
              height: 2,
              background: 'linear-gradient(90deg,rgba(30,150,138,0),var(--accent-2),rgba(30,150,138,0))',
              animation: 'v2-scan 2.1s ease-in-out infinite',
            }}
          />
        </div>
        <div style={{ position: 'absolute', right: 14, top: 8, width: 60, height: 60, borderRadius: 1000, border: '1px solid var(--accent-2)', animation: 'v2-ring 2.4s ease-out infinite' }} />
        <div style={{ position: 'absolute', right: 14, top: 8, width: 60, height: 60, borderRadius: 1000, border: '1px solid var(--accent-2)', animation: 'v2-ring 2.4s ease-out 1.2s infinite' }} />
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
        <div style={{ position: 'absolute', right: 6, bottom: 6, width: 22, height: 22, borderRadius: 7, background: 'var(--chip)', border: '1px solid var(--border-2)', animation: 'v2-float 3.2s ease-in-out infinite' }} />
        <div style={{ position: 'absolute', left: 2, bottom: 16, width: 14, height: 14, borderRadius: 1000, border: '1px solid var(--border-3)', animation: 'v2-pulse 2.2s ease-in-out infinite' }} />
      </div>

      <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.01em' }}>{title}</div>
      {body && (
        <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 7, maxWidth: 400, lineHeight: '20px', textWrap: 'pretty' as React.CSSProperties['textWrap'] }}>
          {body}
        </div>
      )}
      {caption}

      {percent != null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 22, width: 300, maxWidth: '100%' }}>
          <div style={{ flex: 1, height: 5, borderRadius: 1000, background: 'var(--chip)', overflow: 'hidden' }}>
            <div style={{ width: `${Math.max(0, Math.min(100, percent))}%`, height: '100%', background: 'linear-gradient(90deg,var(--accent),var(--accent-2))' }} />
          </div>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 500, color: 'var(--accent-2)', width: 38, textAlign: 'right', flex: 'none' }}>
            {Math.round(percent)}%
          </span>
        </div>
      )}

      {bullets && bullets.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, flexWrap: 'wrap', justifyContent: 'center' }}>
          {bullets.map((label, i) => (
            <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
              {i > 0 && <span style={{ width: 3, height: 3, borderRadius: 1000, background: 'var(--fg-6)' }} />}
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: 'var(--fg-4)' }}>
                <span style={{ width: 5, height: 5, borderRadius: 1000, background: 'var(--accent-2)', animation: `v2-pulse 1.4s ease-in-out ${i * 0.3}s infinite` }} />
                {label}
              </span>
            </span>
          ))}
        </div>
      )}

      {footer}
    </div>
  )
}
