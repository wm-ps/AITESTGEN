import { useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faPeopleGroup } from '@fortawesome/free-solid-svg-icons'
import { PERSONAL_WORKSPACE, type UserRead, type WorkspaceRead } from '../api'
import { useWorkspace } from '../WorkspaceContext'

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

const itemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  width: '100%',
  padding: '9px 16px',
  border: 'none',
  background: 'transparent',
  cursor: 'pointer',
  textAlign: 'left',
  font: 'inherit',
  fontSize: 13,
  color: 'var(--fg-2)',
}

// Top-bar account menu: who you are, the workspace you are working in, "Your
// Teams" (your personal workspace and every team — picking one switches to it)
// and Log out. (Managing teams is the Teams page in the sidebar.) Works without a WorkspaceProvider too (no team list).
export function AccountMenu({
  user,
  onLogout,
}: {
  user: UserRead
  onLogout: () => void
}) {
  const workspace = useWorkspace()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    function onDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [open])

  const active = workspace?.active
  const inPersonal = active?.id === PERSONAL_WORKSPACE
  // The button shows who you are in your personal workspace, the team's name in a team.
  const buttonName = !active ? null : inPersonal ? user.name : active.name
  // In a team the button already names it; only the personal workspace needs saying.
  const subtitle = inPersonal ? '(Personal)' : null
  const label = (item: WorkspaceRead) => (item.kind === 'personal' ? `${user.name} (Personal)` : item.name)

  // "Your Teams" holds the other workspaces to switch to — the one you are in is already on show.
  const others = workspace ? [workspace.data.personal, ...workspace.data.teams].filter((item) => item.id !== active?.id) : []

  const row = (item: WorkspaceRead) => {
    return (
      <button
        key={item.id}
        type="button"
        role="menuitem"
        onClick={() => {
          setOpen(false)
          workspace?.switchTo(item.id)
        }}
        style={itemStyle}
      >
        <FontAwesomeIcon icon={faPeopleGroup} style={{ fontSize: 14, color: 'var(--fg-4)', width: 18 }} />
        <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label(item)}</span>
              </button>
    )
  }

  return (
    <div ref={ref} style={{ position: 'relative', flex: 'none' }}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={initials(user.name)}
        onClick={() => setOpen((v) => !v)}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, padding: '0 4px 0 14px', borderRadius: 1000, border: '1px solid var(--border-2)', background: 'var(--chip)', cursor: 'pointer', font: 'inherit', maxWidth: 260 }}
      >
        {buttonName && (
          <span aria-hidden="true" style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 170 }}>
            {buttonName}
          </span>
        )}
        <span aria-hidden="true" style={{ width: 26, height: 26, flex: 'none', borderRadius: 1000, background: 'var(--accent)', color: '#fff', fontSize: 11, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
          {initials(user.name)}
        </span>
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Account"
          style={{ position: 'absolute', top: 42, right: 0, width: 300, zIndex: 60, borderRadius: 12, background: 'var(--panel)', border: '1px solid var(--border-2)', boxShadow: '0 20px 50px rgba(10,12,16,0.2)', overflow: 'hidden' }}
        >
          <div style={{ padding: '18px 16px 14px', textAlign: 'center' }}>
            <span aria-hidden="true" style={{ width: 52, height: 52, borderRadius: 1000, background: 'var(--accent)', color: '#fff', fontSize: 18, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
              {initials(user.name)}
            </span>
            <div style={{ marginTop: 8, fontSize: 14, fontWeight: 700, color: 'var(--fg)' }}>{user.name}</div>
            {subtitle && <div style={{ marginTop: 2, fontSize: 12.5, color: 'var(--fg-3)' }}>{subtitle}</div>}
            <div style={{ marginTop: 2, fontSize: 12, color: 'var(--fg-4)' }}>{user.email}</div>
          </div>
          {others.length > 0 && (
            <div role="group" aria-label="Your Teams" style={{ padding: '4px 0 8px' }}>
              <div style={{ padding: '4px 16px 6px', fontSize: 12.5, fontWeight: 600, color: 'var(--fg-3)' }}>Your Teams</div>
              {others.map(row)}
            </div>
          )}
          <div style={{ borderTop: '1px solid var(--line)', padding: '6px 0' }}>
            <button type="button" role="menuitem" onClick={onLogout} style={{ ...itemStyle, color: 'var(--bad)' }}>
              Log out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
