import { useState } from 'react'
import { AddTestCasePanel } from './AddTestCasePanel'

function ChatIcon() {
  return (
    <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 5.5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-4.5 3.5V17.5H4a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1Z" />
      <path d="M7.5 10h9M7.5 13.5h6" />
    </svg>
  )
}

function RecordIcon() {
  return (
    <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={12} cy={12} r={8.5} />
      <circle cx={12} cy={12} r={3} fill="currentColor" stroke="none" />
    </svg>
  )
}

// Corner ribbon, diagonal across the tile's top-right corner — clipped by
// the tile's own `overflow: hidden`, the classic enterprise "coming soon"
// corner flag rather than a floating pill.
function ComingSoonBadge() {
  return (
    <div
      aria-hidden="true"
      className="ribbon-shimmer"
      style={{
        position: 'absolute',
        top: 18,
        right: -34,
        width: 140,
        transform: 'rotate(45deg)',
        color: '#fff',
        fontSize: 10.5,
        fontWeight: 700,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        textAlign: 'center',
        padding: '4px 0',
        boxShadow: '0 2px 6px var(--accent-wash-soft)',
      }}
    >
      Coming soon
    </div>
  )
}

function AuthoringTile({
  icon,
  title,
  description,
  onClick,
}: {
  icon: React.JSX.Element
  title: string
  description: string
  // Present only for a tile that's actually wired up — "Record & Play"
  // still has none, so it stays a preview-only "coming soon" card.
  onClick?: () => void
}) {
  const clickable = onClick != null
  return (
    <div
      onClick={onClick}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={
        clickable
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') onClick?.()
            }
          : undefined
      }
      className={clickable ? 'card-clickable' : undefined}
      style={{
        position: 'relative',
        overflow: 'hidden',
        background: 'var(--canvas)',
        borderRadius: 'var(--radius-xl)',
        boxShadow: 'var(--shadow-card)',
        padding: '28px 24px',
        cursor: clickable ? 'pointer' : undefined,
      }}
    >
      {!clickable && <ComingSoonBadge />}
      <div
        aria-hidden="true"
        style={{
          width: 44,
          height: 44,
          borderRadius: 12,
          background: 'var(--accent-wash)',
          color: 'var(--accent)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 16,
        }}
      >
        {icon}
      </div>
      <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: 'var(--ink)' }}>{title}</h3>
      <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', marginTop: 8, lineHeight: 1.5 }}>{description}</p>
    </div>
  )
}

export function AuthoringTab({ applicationId }: { applicationId: string }) {
  const [nlmOpen, setNlmOpen] = useState(false)

  if (nlmOpen) {
    return <AddTestCasePanel applicationId={applicationId} onClose={() => setNlmOpen(false)} />
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, paddingTop: 8 }}>
      <AuthoringTile
        icon={<ChatIcon />}
        title="Natural Language"
        description="Describe a test case in plain English and have it turned into a ready-to-run scenario — no steps to script by hand."
        onClick={() => setNlmOpen(true)}
      />
      <AuthoringTile
        icon={<RecordIcon />}
        title="Record & Play"
        description="Walk through the flow once in your browser and capture it as a repeatable test — no manual authoring at all."
      />
    </div>
  )
}
