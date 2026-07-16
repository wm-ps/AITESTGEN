import { useRef, useState } from 'react'
import type { UserRead } from '../api'

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
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: `var(--space-3) var(--content-x)`,
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <span
          aria-hidden="true"
          style={{
            width: 26,
            height: 26,
            borderRadius: 7,
            background: 'var(--signal)',
            display: 'inline-block',
          }}
        />
        <span style={{ fontWeight: 650, fontSize: 15 }}>Application Intelligence Platform</span>
        {applicationBadge && (
          <>
            <span className="caption" aria-hidden="true">
              /
            </span>
            <span style={{ fontWeight: 650, fontSize: 13 }}>{applicationBadge.name}</span>
            <span
              className="caption"
              style={{
                textTransform: 'uppercase',
                fontSize: '10.5px',
                fontWeight: 650,
                letterSpacing: '0.04em',
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '2px 6px',
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
          style={{
            width: 28,
            height: 28,
            borderRadius: 'var(--radius-full)',
            background: 'var(--signal)',
            color: 'var(--signal-ink)',
            border: 'none',
            fontWeight: 650,
            fontSize: 12,
            cursor: 'pointer',
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
              top: '100%',
              marginTop: 'var(--space-2)',
              padding: 'var(--space-3)',
              minWidth: 200,
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-2)',
              zIndex: 10,
            }}
          >
            <div style={{ fontWeight: 650 }}>{user.name}</div>
            <div className="caption">{user.email}</div>
            <button
              type="button"
              role="menuitem"
              className="button-secondary"
              onClick={onLogout}
            >
              Log out
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
