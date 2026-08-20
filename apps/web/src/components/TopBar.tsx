import { useState } from 'react'
import type { UserRead } from '../api'
import { VantageBrand } from './Brand'

const ENV_LABELS: Record<string, string> = { staging: 'Staging', qa: 'QA', production: 'Production' }
// Distinct dot color per environment — production reads as the "real"
// deliberate one (good/green), not an alarm color; staging/qa share accent.
const ENV_DOT_COLOR: Record<string, string> = {
  staging: 'var(--accent)',
  qa: 'var(--warn-strong)',
  production: 'var(--good-strong)',
}

function WorkspaceIcon() {
  return (
    <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x={3} y={4} width={18} height={16} rx={2} />
      <path d="M3 9h18M9 9v11" />
    </svg>
  )
}

function DiscoveryIcon() {
  return (
    <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx={11} cy={11} r={6.5} />
      <path d="M20 20l-3.8-3.8" />
    </svg>
  )
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  return parts
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

export function TopBar({
  user,
  applicationBadge,
  onLogout,
  onGoHome,
  onInviteTeammate,
  onOpenSettings,
  onOpenWorkspace,
  onViewDiscovery,
}: {
  user: UserRead
  applicationBadge?: { name: string; environment: string }
  onLogout: () => void
  onGoHome?: () => void
  onInviteTeammate?: () => void
  onOpenSettings?: () => void
  onOpenWorkspace?: () => void
  onViewDiscovery?: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header
      style={{
        height: 64,
        boxSizing: 'border-box',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 32px',
        background: 'var(--canvas)',
        borderBottom: '1px solid var(--border)',
        boxShadow: 'var(--shadow-topbar)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-5)' }}>
        <button
          type="button"
          onClick={onGoHome}
          aria-label="Go to Home"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-5)',
            background: 'none',
            border: 'none',
            padding: 0,
            cursor: onGoHome ? 'pointer' : 'default',
            font: 'inherit',
            color: 'inherit',
          }}
        >
          <VantageBrand wordmarkSize={22} markSize={22} />
        </button>
        {applicationBadge && (
          <>
            <span style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} aria-hidden="true" />
            <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--ink)' }}>{applicationBadge.name}</span>
            {/* A small outlined tag, not a filled pill — the app name is the
                thing that matters here, the environment is context, so it
                reads quieter and smaller than a status pill would. */}
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                fontSize: 9.5,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                color: 'var(--ink-muted)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-xs)',
                padding: '2px 6px',
                whiteSpace: 'nowrap',
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: 'var(--radius-full)',
                  background: ENV_DOT_COLOR[applicationBadge.environment] ?? 'var(--accent)',
                  flexShrink: 0,
                }}
              />
              {ENV_LABELS[applicationBadge.environment] || 'Staging'}
            </span>
          </>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-5)' }}>
        {onViewDiscovery && (
          <button
            type="button"
            className="button-secondary"
            onClick={onViewDiscovery}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <DiscoveryIcon />
            View Discovery
          </button>
        )}
        {onOpenWorkspace && (
          <button
            type="button"
            className="button-secondary"
            onClick={onOpenWorkspace}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <WorkspaceIcon />
            Workspace
          </button>
        )}
        <div style={{ position: 'relative' }}>
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
          className="avatar-button"
          style={{
            width: 32,
            height: 32,
            borderRadius: 'var(--radius-full)',
            background: 'var(--canvas-wash-alt)',
            border: '1px solid var(--border)',
            color: 'var(--ink-secondary)',
            fontWeight: 600,
            fontSize: 13,
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          {initials(user.name)}
        </button>
        {menuOpen && (
          <>
            <div
              onClick={() => setMenuOpen(false)}
              style={{ position: 'fixed', inset: 0, zIndex: 40 }}
              aria-hidden="true"
            />
            <div
              role="menu"
              className="card-panel"
              style={{
                position: 'absolute',
                right: 0,
                top: 40,
                minWidth: 180,
                borderRadius: 10,
                boxShadow: 'var(--shadow-dropdown-lg)',
                overflow: 'hidden',
                zIndex: 41,
              }}
            >
              <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--canvas-wash-alt)' }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{user.name}</div>
                <div style={{ fontSize: 12, marginTop: 1, color: 'var(--ink-faint)' }}>{user.email}</div>
              </div>
              {user.role === 'admin' && onInviteTeammate && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false)
                    onInviteTeammate()
                  }}
                  className="menu-item"
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    padding: '10px 14px',
                    background: 'none',
                    border: 'none',
                    borderBottom: '1px solid var(--canvas-wash-alt)',
                    fontSize: 13,
                    color: 'var(--ink)',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                  }}
                >
                  Invite
                </button>
              )}
              {user.role === 'admin' && onOpenSettings && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false)
                    onOpenSettings()
                  }}
                  className="menu-item"
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    padding: '10px 14px',
                    background: 'none',
                    border: 'none',
                    borderBottom: '1px solid var(--canvas-wash-alt)',
                    fontSize: 13,
                    color: 'var(--ink)',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                  }}
                >
                  Settings
                </button>
              )}
              <button
                type="button"
                role="menuitem"
                onClick={onLogout}
                className="menu-item-danger"
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '10px 14px',
                  background: 'none',
                  border: 'none',
                  fontSize: 13,
                  color: 'var(--danger)',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >
                Log out
              </button>
            </div>
          </>
        )}
        </div>
      </div>
    </header>
  )
}
