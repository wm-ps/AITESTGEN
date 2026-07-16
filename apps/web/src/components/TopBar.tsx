import { useRef, useState } from 'react'
import type { UserRead } from '../api'
import { Logo } from './Logo'

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
}: {
  user: UserRead
  applicationBadge?: { name: string; environment: string }
  onLogout: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  return (
    <header
      style={{
        height: 64,
        boxSizing: 'border-box',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 32px',
        background: 'var(--paper)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <Logo size={32} />
        <span style={{ fontWeight: 700, fontSize: 16 }}>AITestGen</span>
        {applicationBadge && (
          <>
            <span style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} aria-hidden="true" />
            <span style={{ fontWeight: 650, fontSize: 15 }}>{applicationBadge.name}</span>
            <span
              style={{
                display: 'inline-block',
                textTransform: 'uppercase',
                fontSize: 11,
                fontWeight: 650,
                letterSpacing: '0.04em',
                background: 'var(--signal-wash)',
                color: 'var(--signal)',
                borderRadius: 'var(--radius-full)',
                padding: '3px 9px',
                whiteSpace: 'nowrap',
              }}
            >
              {applicationBadge.environment}
            </span>
          </>
        )}
      </div>

      <div ref={menuRef} style={{ position: 'relative' }}>
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
            background: 'var(--surface-hover)',
            border: '1px solid var(--border)',
            color: 'var(--ink-muted)',
            fontWeight: 600,
            fontSize: 13,
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          {initials(user.name)}
        </button>
        {menuOpen && (
          <div
            role="menu"
            className="card-panel"
            style={{
              position: 'absolute',
              right: 0,
              top: 40,
              minWidth: 180,
              boxShadow: '0 12px 28px rgba(15,23,42,0.14)',
              overflow: 'hidden',
              zIndex: 10,
            }}
          >
            <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--surface-hover)' }}>
              <div style={{ fontSize: 13, fontWeight: 650 }}>{user.name}</div>
              <div className="caption" style={{ fontSize: 12, marginTop: 1 }}>
                {user.email}
              </div>
            </div>
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
        )}
      </div>
    </header>
  )
}
