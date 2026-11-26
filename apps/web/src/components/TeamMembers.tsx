import { useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEllipsisVertical, faUserPlus } from '@fortawesome/free-solid-svg-icons'
import { ApiError, ROLE_LABEL, api, type RemovalImpactRead, type Role, type TeamMemberRead, type UserRead } from '../api'
import { InviteTeammateModal, ROLE_OPTIONS } from './InviteTeammateModal'
import { SkeletonRows } from './Skeleton'
import { Toast } from './Toast'
import { AnchoredMenu } from './AnchoredMenu'
import { EnvironmentModal, FieldError, ModalActions } from './environments/EnvironmentModal'

type TeamMember = TeamMemberRead

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

const rolePillStyle = (role: Role): React.CSSProperties => ({
  display: 'inline-block',
  padding: '3px 10px',
  borderRadius: 1000,
  fontSize: 11,
  fontWeight: 600,
  background: role === 'super_admin' ? 'rgba(30,150,138,0.14)' : 'var(--chip)',
  color: role === 'super_admin' ? 'var(--accent-2)' : 'var(--fg-3)',
  border: role === 'super_admin' ? '1px solid rgba(30,150,138,0.28)' : '1px solid var(--border-2)',
})

const menuItemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  width: '100%',
  textAlign: 'left',
  padding: '9px 12px',
  fontSize: 13,
  border: 'none',
  background: 'none',
  color: 'var(--fg-1)',
  cursor: 'pointer',
  borderRadius: 6,
  fontFamily: 'inherit',
}

const COLUMNS = 'minmax(240px,1.2fr) minmax(130px,0.6fr) minmax(200px,1.2fr) minmax(110px,0.5fr) 44px'

function teamsLabel(member: TeamMember): string {
  // A super admin can enter every team.
  if (member.role === 'super_admin') return 'All teams'
  return member.teams && member.teams.length > 0 ? member.teams.join(', ') : '—'
}

function MemberRow({
  member,
  members,
  isSelf,
  onChanged,
  onError,
}: {
  member: TeamMember
  members: TeamMember[]
  isSelf: boolean
  onChanged: (message?: string) => void
  onError: (message: string) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const [dialog, setDialog] = useState<'role' | 'remove' | 'stepdown' | null>(null)
  const canStepDown = isSelf && member.role === 'super_admin'

  return (
    <div style={{ display: 'grid', gridTemplateColumns: COLUMNS, gap: 12, alignItems: 'center', padding: '14px 20px', borderBottom: '1px solid var(--row-line)' }}>
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
      <div style={{ fontSize: 13, color: 'var(--fg-2)' }}>
        {member.last_active_at ? relativeTime(member.last_active_at) : 'Never signed in'}
      </div>
      <div style={{ fontSize: 13, color: 'var(--fg-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={teamsLabel(member)}>
        {teamsLabel(member)}
      </div>
      <div>
        <span style={rolePillStyle(member.role)}>{ROLE_LABEL[member.role]}</span>
      </div>
      <div style={{ textAlign: 'right', position: 'relative' }}>
        {(!isSelf || canStepDown) && (
          <>
            <button
              ref={menuButtonRef}
              type="button"
              title="More options"
              onClick={() => setMenuOpen((v) => !v)}
              style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer', color: 'var(--fg-4)', display: 'inline-flex' }}
            >
              <FontAwesomeIcon icon={faEllipsisVertical} style={{ fontSize: 15 }} />
            </button>
            <AnchoredMenu anchorRef={menuButtonRef} open={menuOpen} onClose={() => setMenuOpen(false)}>
              <div role="menu" style={{ minWidth: 184, padding: 4, background: 'var(--panel)', border: '1px solid var(--border-2)', borderRadius: 10, boxShadow: 'var(--panel-shadow)' }}>
                {isSelf ? (
                  <button type="button" role="menuitem" onClick={() => { setMenuOpen(false); setDialog('stepdown') }} style={menuItemStyle}>
                    Step down
                  </button>
                ) : (
                  <>
                    <button type="button" role="menuitem" onClick={() => { setMenuOpen(false); setDialog('role') }} style={menuItemStyle}>
                      Edit role
                    </button>
                    <button type="button" role="menuitem" onClick={() => { setMenuOpen(false); setDialog('remove') }} style={{ ...menuItemStyle, color: 'var(--bad)' }}>
                      Remove user
                    </button>
                  </>
                )}
              </div>
            </AnchoredMenu>
          </>
        )}
      </div>
      {dialog === 'role' && (
        <EditRoleDialog
          member={member}
          onClose={() => setDialog(null)}
          onDone={(message) => { setDialog(null); onChanged(message) }}
          onError={(message) => { setDialog(null); onError(message) }}
        />
      )}
      {dialog === 'remove' && (
        <RemoveUserDialog
          member={member}
          onClose={() => setDialog(null)}
          onDone={(message) => { setDialog(null); onChanged(message) }}
          onError={(message) => { setDialog(null); onError(message) }}
        />
      )}
      {dialog === 'stepdown' && (
        <StepDownDialog
          others={members.filter((m) => m.email !== member.email)}
          onClose={() => setDialog(null)}
          onDone={(message) => { setDialog(null); onChanged(message) }}
          onError={(message) => { setDialog(null); onError(message) }}
        />
      )}
    </div>
  )
}

const ROLE_DESCRIPTION: Record<Role, string> = {
  standard_user: "Joins the teams they're added to and gets a personal workspace.",
  super_admin: 'Full access to all teams, users and applications.',
}

// Super admin only on the server, which also refuses to leave the organization
// without a super admin (409) — that message is shown as-is.
function EditRoleDialog({
  member,
  onClose,
  onDone,
  onError,
}: {
  member: TeamMember
  onClose: () => void
  onDone: (message: string) => void
  onError: (message: string) => void
}) {
  const [role, setRole] = useState<Role>(member.role)
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  // Turning a Super Admin into a User takes team access away, so it is confirmed first.
  const demoting = member.role === 'super_admin' && role !== 'super_admin'

  async function change() {
    setBusy(true)
    try {
      await api.changeTeamMemberRole(member.email, role)
      onDone(`${member.name} is now ${ROLE_LABEL[role]}`)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Could not change this person’s role — try again.')
    } finally {
      setBusy(false)
    }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (demoting) setConfirming(true)
    else void change()
  }

  if (confirming) {
    return (
      <EnvironmentModal
        title={`Change ${member.name} to User?`}
        subtitle={member.email}
        onClose={onClose}
        maxWidth={480}
        footer={<ModalActions onCancel={onClose} submitLabel="Change to User" busyLabel="Changing" busy={busy} danger type="button" onSubmit={() => void change()} />}
      >
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--fg-2)', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <li>{member.name} will no longer be a Super Admin.</li>
          <li>They lose access to team applications they added or were shared on. Those stay with their team and its Team Admins.</li>
          <li>They keep their personal workspace and personal applications.</li>
        </ul>
      </EnvironmentModal>
    )
  }

  return (
    <EnvironmentModal
      title="Edit role"
      subtitle={member.name}
      onClose={onClose}
      onSubmit={submit}
      maxWidth={440}
      footer={<ModalActions onCancel={onClose} submitLabel="Update role" busyLabel="Updating" busy={busy} disabled={role === member.role} />}
    >
      <fieldset style={{ border: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {ROLE_OPTIONS.map((option) => (
          <label key={option.key} style={{ display: 'flex', gap: 10, padding: '10px 12px', borderRadius: 10, border: `1px solid ${role === option.key ? 'var(--accent)' : 'var(--border-2)'}`, cursor: 'pointer' }}>
            <input type="radio" name="org-role" checked={role === option.key} onChange={() => setRole(option.key)} />
            <span>
              <span style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>{option.label}</span>
              <span style={{ display: 'block', fontSize: 12, color: 'var(--fg-3)' }}>{ROLE_DESCRIPTION[option.key]}</span>
            </span>
          </label>
        ))}
      </fieldset>
    </EnvironmentModal>
  )
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

// Removing a person deletes them from Vantage for good, so it says what goes
// with them before it does it.
function RemoveUserDialog({
  member,
  onClose,
  onDone,
  onError,
}: {
  member: TeamMember
  onClose: () => void
  onDone: (message: string) => void
  onError: (message: string) => void
}) {
  const [impact, setImpact] = useState<RemovalImpactRead | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    api
      .getRemovalImpact(member.email)
      .then(setImpact)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : 'Could not check what removing them affects.'))
  }, [member.email])

  async function confirm() {
    setBusy(true)
    try {
      await api.removeTeamMember(member.email)
      onDone(`${member.name} was removed.`)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Could not remove this person — try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <EnvironmentModal
      title="Remove user"
      subtitle={`${member.name} · ${member.email}`}
      onClose={onClose}
      maxWidth={480}
      footer={<ModalActions onCancel={onClose} submitLabel="Remove user" busyLabel="Removing" busy={busy} disabled={!impact} danger type="button" onSubmit={confirm} />}
    >
      <p role="alert" style={{ margin: 0, fontSize: 13, fontWeight: 600, color: 'var(--danger)' }}>
        This permanently deletes their account and can't be undone.
      </p>
      {loadError && <FieldError>{loadError}</FieldError>}
      {impact && (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--fg-2)', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <li>
            {impact.personal_applications === 0
              ? 'They have no personal applications.'
              : `${plural(impact.personal_applications, 'personal application')} will be deleted${impact.people_losing_access > 0 ? `, and ${plural(impact.people_losing_access, 'person')} they shared ${impact.personal_applications === 1 ? 'it' : 'them'} with will lose access` : ''}.`}
          </li>
          <li>
            {impact.team_applications_added === 0
              ? 'They added no applications in a team.'
              : `${plural(impact.team_applications_added, 'application')} they added in teams stay with the team and go to its Team Admins.`}
          </li>
          <li>They leave {plural(impact.teams, 'team')} and lose access to every shared application.</li>
          {impact.schedules_without_recipient > 0 && (
            <li>{plural(impact.schedules_without_recipient, 'schedule')} they created keep running but have no one to email the report to.</li>
          )}
        </ul>
      )}
    </EnvironmentModal>
  )
}

// "Make Super Admin and step down" when you are the only one; otherwise just stepping down.
function StepDownDialog({
  others,
  onClose,
  onDone,
  onError,
}: {
  others: TeamMember[]
  onClose: () => void
  onDone: (message: string) => void
  onError: (message: string) => void
}) {
  const otherAdmins = others.filter((m) => m.role === 'super_admin')
  const [successor, setSuccessor] = useState(otherAdmins[0]?.email ?? '')
  const [busy, setBusy] = useState(false)
  const handingOver = otherAdmins.length === 0

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      await api.stepDown(successor)
      onDone('You stepped down. Teams and Users are for Super Admins only.')
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Could not step down — try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <EnvironmentModal
      title="Step down as Super Admin"
      subtitle={handingOver ? 'You are the only Super Admin — choose who takes over.' : 'You will become a User.'}
      onClose={onClose}
      onSubmit={submit}
      maxWidth={460}
      footer={
        <ModalActions
          onCancel={onClose}
          submitLabel={handingOver ? 'Make Super Admin and step down' : 'Step down to User'}
          busyLabel="Stepping down"
          busy={busy}
          disabled={!successor}
        />
      }
    >
      <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>
          {handingOver ? 'New Super Admin' : 'Hand over to'}
        </span>
        <select
          aria-label="New Super Admin"
          value={successor}
          onChange={(e) => setSuccessor(e.target.value)}
          style={{ height: 38, borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', padding: '0 10px', font: 'inherit', color: 'var(--fg)' }}
        >
          {(handingOver ? others : otherAdmins).map((m) => (
            <option key={m.email} value={m.email}>
              {m.name} ({m.email})
            </option>
          ))}
        </select>
      </label>
    </EnvironmentModal>
  )
}

export function TeamMembers({ user }: { user: UserRead }) {
  const [members, setMembers] = useState<TeamMember[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  function refresh() {
    api
      .listTeam()
      .then(setMembers)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load team members.'))
  }

  useEffect(refresh, [])

  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Users</h1>
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

      <div style={{ background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))', backdropFilter: 'blur(16px) saturate(1.25)', border: '1px solid var(--border)', borderRadius: 14, overflow: 'hidden', boxShadow: 'var(--panel-shadow)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: COLUMNS, gap: 12, padding: '12px 20px', background: 'var(--panel-2)', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Member</div>
          <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Last active</div>
          <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>Teams</div>
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
              members={members}
              isSelf={member.email === user.email}
              onChanged={(message) => {
                refresh()
                if (message) setNotice(message)
              }}
              onError={setToast}
            />
          ))
        )}
      </div>

      {inviteOpen && <InviteTeammateModal onClose={() => setInviteOpen(false)} />}
      {toast && <Toast message={toast} kind="error" onDismiss={() => setToast(null)} />}
      {notice && <Toast message={notice} kind="success" onDismiss={() => setNotice(null)} />}
    </div>
  )
}
