import { useEscapeToClose } from '../hooks/useEscapeToClose'
import type { ApplicationRead } from '../api'

export function ConnectSuccessModal({
  application,
  onGoHome,
}: {
  application: ApplicationRead
  onGoHome: () => void
}) {
  useEscapeToClose(onGoHome)

  const rows: [string, string][] = [
    ['URL', application.url],
    ['Environment', application.environment],
    ['Authentication', application.auth_method === 'standard_login' ? 'Username & Password' : application.auth_method],
  ]

  return (
    <div
      onClick={onGoHome}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,23,42,0.35)',
        backdropFilter: 'blur(2px)',
        WebkitBackdropFilter: 'blur(2px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="card-panel"
        style={{
          width: '100%',
          maxWidth: 420,
          padding: '28px 28px 24px',
          boxSizing: 'border-box',
          boxShadow: 'var(--shadow-dropdown-lg)',
          borderTop: '3px solid var(--accent)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <span
            aria-hidden
            style={{
              flexShrink: 0,
              width: 30,
              height: 30,
              borderRadius: '50%',
              background: 'var(--accent-wash)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
              <path d="M3 8.5L6.2 12L13 4" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <div>
            <h2 style={{ fontSize: 16.5, fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
              {application.name} is connected
            </h2>
            <p style={{ fontSize: 13, color: 'var(--ink-muted)', lineHeight: 1.5, margin: '4px 0 0' }}>
              Next up: Discover Journeys, mapping out every path through the app. That can take a few minutes.
            </p>
          </div>
        </div>

        <div
          style={{
            marginTop: 16,
            padding: '10px 14px',
            background: 'var(--canvas-wash)',
            borderRadius: 'var(--radius)',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}
        >
          {rows.map(([label, value]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12.5 }}>
              <span style={{ color: 'var(--ink-secondary)', fontWeight: 600 }}>{label}</span>
              <span style={{ color: 'var(--ink)', textAlign: 'right', overflowWrap: 'anywhere' }}>{value}</span>
            </div>
          ))}
        </div>

        <p className="caption" style={{ fontSize: 12, margin: '14px 0 18px' }}>
          You may continue with other tasks. You will be notified once this is complete.
        </p>

        <button
          type="button"
          className="button-primary"
          onClick={onGoHome}
          style={{ width: '100%', padding: 11, fontSize: 14 }}
        >
          Go to Home screen
        </button>
      </div>
    </div>
  )
}
