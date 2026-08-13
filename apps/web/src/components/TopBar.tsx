import { useState } from 'react'
import type { UserRead } from '../api'
import { Logo } from './Logo'

const ENV_LABELS: Record<string, string> = { staging: 'Staging', qa: 'QA', production: 'Production' }

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
}: {
  user: UserRead
  applicationBadge?: { name: string; environment: string }
  onLogout: () => void
  onGoHome?: () => void
  onInviteTeammate?: () => void
  onOpenSettings?: () => void
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
          <Logo size={32} />
          <span style={{ fontWeight: 700, fontSize: 16, color: 'var(--ink)' }}>AITestGen</span>
        </button>
        {applicationBadge && (
          <>
            <span style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} aria-hidden="true" />
            <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--ink)' }}>{applicationBadge.name}</span>
            <span
              style={{
                display: 'inline-block',
                fontSize: 11,
                fontWeight: 600,
                background: 'var(--accent-wash)',
                color: 'var(--accent)',
                borderRadius: 'var(--radius-full)',
                padding: '3px 9px',
                whiteSpace: 'nowrap',
              }}
            >
              {ENV_LABELS[applicationBadge.environment] || 'Staging'}
            </span>
          </>
        )}
      </div>

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
                  Invite teammate
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
    </header>
  )
}
