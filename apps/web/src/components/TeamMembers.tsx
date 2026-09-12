import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEllipsis, faShieldHalved, faUserPlus } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type UserRead } from '../api'
import { InviteTeammateModal } from './InviteTeammateModal'
import { SkeletonRows } from './Skeleton'
import { Toast } from './Toast'

type TeamMember = {
  name: string
  email: string
  role: 'admin' | 'member'
  created_at: string
  last_active_at: string | null
}

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(diffMs / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

const rolePillStyle = (role: 'admin' | 'member'): React.CSSProperties => ({
  display: 'inline-block',
  padding: '3px 10px',
  borderRadius: 1000,
  fontSize: 11,
  fontWeight: 600,
  background: role === 'admin' ? 'rgba(30,150,138,0.14)' : 'var(--chip)',
  color: role === 'admin' ? 'var(--accent-2)' : 'var(--fg-3)',
  border: role === 'admin' ? '1px solid rgba(30,150,138,0.28)' : '1px solid var(--border-2)',
})

function MemberRow({ member, isSelf, onChanged, onError }: { member: TeamMember; isSelf: boolean; onChanged: () => void; onError: (message: string) => void }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [removing, setRemoving] = useState(false)

  async function remove() {
    setMenuOpen(false)
    setRemoving(true)
    try {
      await api.removeTeamMember(member.email)
      onChanged()
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Could not remove this member — try again.')
    } finally {
      setRemoving(false)
    }
  }

  return (
    <div
      style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.6fr) 130px 120px 40px', gap: 12, alignItems: 'center', padding: '14px 20px', borderBottom: '1px solid var(--row-line)', opacity: removing ? 0.5 : 1 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
        <div style={{ width: 34, height: 34, flex: 'none', borderRadius: 1000, background: 'var(--chip)', border: '1px solid var(--border-2)', color: 'var(--accent-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600 }}>
          {initials(member.name)}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {member.name}
            {isSelf && <span style={{ color: 'var(--fg-4)', fontWeight: 400 }}> (you)</span>}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--fg-4)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{member.email}</div>
        </div>
      </div>
      <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>
        {member.last_active_at ? relativeTime(member.last_active_at) : 'Never signed in'}
      </div>
      <div>
        <span style={rolePillStyle(member.role)}>{member.role === 'admin' ? 'Admin' : 'Member'}</span>
      </div>
      <div style={{ textAlign: 'right', position: 'relative' }}>
        {!isSelf && (
          <>
            <button
              type="button"
              title="More options"
              disabled={removing}
              onClick={() => setMenuOpen((v) => !v)}
              style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer', color: 'var(--fg-4)', display: 'inline-flex' }}
            >
              <FontAwesomeIcon icon={faEllipsis} style={{ fontSize: 15 }} />
            </button>
            {menuOpen && (
              <>
                <div onClick={() => setMenuOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 9 }} />
                <div style={{ position: 'absolute', top: '100%', right: 0, marginTop: 4, minWidth: 140, padding: 4, zIndex: 10, background: 'var(--panel)', border: '1px solid var(--border-2)', borderRadius: 10, boxShadow: 'var(--panel-shadow)' }}>
                  <button
                    type="button"
                    onClick={remove}
                    style={{ display: 'block', width: '100%', textAlign: 'left', padding: '9px 12px', fontSize: 13, border: 'none', background: 'none', color: 'var(--bad)', cursor: 'pointer', borderRadius: 6 }}
                  >
                    Remove
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export function TeamMembers({ user }: { user: UserRead }) {
  const [members, setMembers] = useState<TeamMember[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  function refresh() {
    api
      .listTeam()
      .then(setMembers)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Loading team members failed.'))
  }

  useEffect(refresh, [])

  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Team members</h1>
          <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 4 }}>Who can onboard applications, approve scenarios and trigger runs.</div>
        </div>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          onClick={() => setInviteOpen(true)}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, padding: '0 16px', borderRadius: 8, background: 'var(--accent)', color: '#fff', fontSize: 13.5, fontWeight: 600, cursor: 'pointer', boxShadow: 'var(--accent-glow)', border: 'none', whiteSpace: 'nowrap' }}
        >
          <FontAwesomeIcon icon={faUserPlus} style={{ fontSize: 13 }} />
          Invite member
        </button>
      </div>

      {error && (
        <div style={{ color: 'var(--bad)', fontSize: 13 }} role="alert">
          {error}
        </div>
      )}

      <div style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border-1)', borderRadius: 14, overflow: 'hidden', boxShadow: 'var(--panel-shadow)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.6fr) 130px 120px 40px', gap: 12, padding: '12px 20px', background: 'var(--panel-2)', borderBottom: '1px solid var(--border-2)' }}>
          <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Member</div>
          <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Last active</div>
          <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Role</div>
          <div />
        </div>
        {members === null ? (
          <div style={{ padding: 20 }}>
            <SkeletonRows count={4} height={42} gap={14} />
          </div>
        ) : (
          members.map((member) => (
            <MemberRow
              key={member.email}
              member={member}
              isSelf={member.email === user.email}
              onChanged={refresh}
              onError={setToast}
            />
          ))
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '13px 16px', border: '1px solid var(--border-2)', borderRadius: 10, background: 'var(--panel-2)' }}>
        <FontAwesomeIcon icon={faShieldHalved} style={{ fontSize: 13, color: "var(--ok)" }} />
        <div style={{ flex: 1, fontSize: 12.5, color: 'var(--fg-3)' }}>Only admins can view saved credentials or change discovery limits.</div>
      </div>

      {inviteOpen && <InviteTeammateModal onClose={() => setInviteOpen(false)} />}
      {toast && <Toast message={toast} kind="error" onDismiss={() => setToast(null)} />}
    </div>
  )
}
