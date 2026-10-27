import { useEffect, type CSSProperties, type ReactNode } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import { faXmark } from '@fortawesome/free-solid-svg-icons'
import { shotUrl } from './explorerApi'

// Same glass-card recipe as DiscoverJourneys' journey cards, so Explorer
// reads as part of Vantage rather than a bolted-on tool.
export const glassCard: CSSProperties = {
  background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
  backdropFilter: 'blur(16px) saturate(1.25)',
  border: '1px solid var(--border-1)',
  borderRadius: 14,
  boxShadow: 'var(--panel-shadow)',
}

export type Tone = 'accent' | 'ok' | 'warn' | 'bad' | 'neutral' | 'info'

const TONES: Record<Tone, { fg: string; bg: string; border: string }> = {
  accent: { fg: 'var(--accent-2)', bg: 'var(--accent-wash)', border: 'color-mix(in srgb, var(--accent-2) 22%, transparent)' },
  ok: { fg: 'var(--ok)', bg: 'color-mix(in srgb, var(--ok) 9%, white)', border: 'color-mix(in srgb, var(--ok) 25%, transparent)' },
  warn: { fg: 'var(--warn-2)', bg: 'color-mix(in srgb, var(--warn-2) 9%, white)', border: 'color-mix(in srgb, var(--warn-2) 25%, transparent)' },
  bad: { fg: 'var(--bad)', bg: 'color-mix(in srgb, var(--bad) 8%, white)', border: 'color-mix(in srgb, var(--bad) 25%, transparent)' },
  info: { fg: '#2F5FB3', bg: 'color-mix(in srgb, #2F5FB3 8%, white)', border: 'color-mix(in srgb, #2F5FB3 22%, transparent)' },
  neutral: { fg: 'var(--fg-3)', bg: 'var(--chip)', border: 'var(--line)' },
}

export function toneColor(tone: Tone) {
  return TONES[tone].fg
}

export function Pill({ tone = 'neutral', icon, children, title }: { tone?: Tone; icon?: IconDefinition; children: ReactNode; title?: string }) {
  const t = TONES[tone]
  return (
    <span
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '2px 9px',
        borderRadius: 1000,
        fontSize: 11.5,
        fontWeight: 600,
        lineHeight: '18px',
        color: t.fg,
        background: t.bg,
        border: `1px solid ${t.border}`,
        whiteSpace: 'nowrap',
      }}
    >
      {icon && <FontAwesomeIcon icon={icon} style={{ fontSize: 10 }} />}
      {children}
    </span>
  )
}

export function IconTile({ icon, tone = 'accent', size = 32 }: { icon: IconDefinition; tone?: Tone; size?: number }) {
  const t = TONES[tone]
  return (
    <span
      style={{
        width: size,
        height: size,
        flex: 'none',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: 9,
        color: t.fg,
        background: t.bg,
        border: `1px solid ${t.border}`,
      }}
    >
      <FontAwesomeIcon icon={icon} style={{ fontSize: size * 0.42 }} />
    </span>
  )
}

export function SectionTitle({ icon, children, aside }: { icon?: IconDefinition; children: ReactNode; aside?: ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
      {icon && <FontAwesomeIcon icon={icon} style={{ fontSize: 12.5, color: 'var(--fg-4)' }} />}
      <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: 'var(--fg-2)', letterSpacing: '0.01em', flex: 1 }}>{children}</h3>
      {aside}
    </div>
  )
}

export function HealthRing({ score, size = 56 }: { score: number | null; size?: number }) {
  const stroke = 6
  const r = (size - stroke) / 2
  const circumference = 2 * Math.PI * r
  const value = score ?? 0
  const tone: Tone = score === null ? 'neutral' : value >= 85 ? 'ok' : value >= 60 ? 'warn' : 'bad'
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={score === null ? 'Health not checked yet' : `Health ${value} of 100`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth={stroke} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={toneColor(tone)}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - value / 100)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 900ms ease' }}
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" style={{ fontSize: size * 0.3, fontWeight: 700, fill: 'var(--fg)', fontFamily: 'var(--font-ui)' }}>
        {score === null ? '–' : value}
      </text>
    </svg>
  )
}

export function healthTone(score: number | null): Tone {
  if (score === null) return 'neutral'
  return score >= 85 ? 'ok' : score >= 60 ? 'warn' : 'bad'
}

export function healthLabel(score: number | null): string {
  if (score === null) return 'Not checked yet'
  return score >= 85 ? 'Healthy' : score >= 60 ? 'Some problems' : 'Unhealthy'
}

export function Lightbox({ shotId, caption, onClose }: { shotId: string; caption?: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(15,23,42,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}
    >
      <figure onClick={(e) => e.stopPropagation()} style={{ margin: 0, maxWidth: 'min(1280px, 94vw)', display: 'flex', flexDirection: 'column', gap: 10, animation: 'aitg-materialize 220ms ease' }}>
        <img src={shotUrl(shotId)} alt={caption ?? 'Screenshot'} style={{ width: '100%', maxHeight: '82vh', objectFit: 'contain', borderRadius: 12, boxShadow: '0 24px 60px rgba(0,0,0,0.35)', background: 'white' }} />
        {caption && <figcaption style={{ color: 'white', fontSize: 13, textAlign: 'center' }}>{caption}</figcaption>}
      </figure>
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        style={{ position: 'absolute', top: 18, right: 22, width: 36, height: 36, borderRadius: 1000, border: 'none', background: 'rgba(255,255,255,0.15)', color: 'white', cursor: 'pointer' }}
      >
        <FontAwesomeIcon icon={faXmark} />
      </button>
    </div>
  )
}

export function timeAgo(iso: string, now: number): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
