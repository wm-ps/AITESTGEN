import { useEffect, useMemo, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowLeft, faEllipsisVertical, faEye, faMagnifyingGlass, faPlus, faTrashCan, faUserPlus, faXmark } from '@fortawesome/free-solid-svg-icons'
import {
  ApiError,
  PERSONAL_WORKSPACE,
  TEAM_ROLE_LABEL,
  api,
  type TeamApplicationRead,
  type TeamMemberRead,
  type TeamPersonRead,
  type TeamRead,
  type TeamRole,
} from '../api'
import { useWorkspace } from '../WorkspaceContext'
import { AnchoredMenu } from './AnchoredMenu'
import { EnvironmentModal, FieldError, ModalActions } from './environments/EnvironmentModal'
import { Avatar, PersonPicker, type Person } from './PersonPicker'
import { SkeletonRows } from './Skeleton'
import { Toast } from './Toast'

// Role pill: teal for Team Admin / Application Admin, grey for the rest.
const pillStyle = (admin: boolean): React.CSSProperties => ({
  display: 'inline-flex',
  alignItems: 'center',
  height: 24,
  padding: '0 11px',
  borderRadius: 1000,
  fontSize: 12,
  fontWeight: 600,
  whiteSpace: 'nowrap',
  background: admin ? 'rgba(30,150,138,0.12)' : 'var(--chip)',
  color: admin ? 'var(--accent-2)' : 'var(--fg-2)',
})

// The frosted table card every list on these screens sits in.
const cardStyle: React.CSSProperties = {
  background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
  backdropFilter: 'blur(16px) saturate(1.25)',
  border: '1px solid var(--border)',
  borderRadius: 12,
  overflow: 'hidden',
}

const headRow: React.CSSProperties = { display: 'grid', gap: 12, alignItems: 'center', padding: '11px 20px', background: 'var(--panel-2)', borderBottom: '1px solid var(--border)' }

const monoNumber: React.CSSProperties = { fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, color: 'var(--fg-2)' }

const primaryButton: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, padding: '0 14px', whiteSpace: 'nowrap' }

const labelStyle: React.CSSProperties = {
  fontSize: 10.5,
  fontWeight: 600,
  letterSpacing: '0.07em',
  textTransform: 'uppercase',
  color: 'var(--fg-4)',
}

// Form labels in the dialogs.
const fieldLabel: React.CSSProperties = { fontSize: 12.5, fontWeight: 600, color: 'var(--fg-1)' }

const menuItemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  width: '100%',
  padding: '8px 12px',
  border: 'none',
  background: 'transparent',
  textAlign: 'left',
  font: 'inherit',
  fontSize: 13,
  color: 'var(--fg-2)',
  cursor: 'pointer',
}

const TeamMark = ({ name, size = 26 }: { name: string; size?: number }) => (
  <span
    aria-hidden="true"
    style={{ width: size, height: size, flex: 'none', borderRadius: size > 32 ? 12 : 7, background: 'var(--accent)', color: '#fff', fontSize: size > 32 ? 20 : 12, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
  >
    {name.trim()[0]?.toUpperCase()}
  </span>
)

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

// --- Teams (super admin) ---------------------------------------------------------

export function Teams() {
  const workspace = useWorkspace()
  const [teams, setTeams] = useState<TeamRead[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<TeamRead | null>(null)

  function refresh() {
    api
      .listTeams()
      .then((rows) => {
        setTeams(rows)
        setError(null)
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load teams.'))
    workspace?.refresh()
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(refresh, [])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (teams ?? []).filter((t) => !q || t.name.toLowerCase().includes(q) || t.team_admins.some((a) => a.toLowerCase().includes(q)))
  }, [teams, query])

  const open = teams?.find((t) => t.id === openId)
  if (open) {
    return <TeamDetail team={open} canManage onBack={() => setOpenId(null)} onChanged={refresh} />
  }

  const cols = 'minmax(0,1.6fr) minmax(0,1.4fr) 120px 130px 36px'
  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Teams</h1>
        </div>
        <div style={{ flex: 1 }} />
        <button type="button" className="button-primary" onClick={() => setCreating(true)} style={primaryButton}>
          <FontAwesomeIcon icon={faPlus} style={{ fontSize: 11 }} />
          Create team
        </button>
      </div>

      <div className="field-shell" style={{ height: 40, maxWidth: 420, width: '100%', borderRadius: 10, padding: '0 12px', gap: 10 }}>
        <FontAwesomeIcon icon={faMagnifyingGlass} style={{ color: 'var(--fg-4)', fontSize: 12 }} />
        <input data-bare aria-label="Search teams" placeholder="Search teams or Team Admin" value={query} onChange={(e) => setQuery(e.target.value)} style={{ fontSize: 13.5 }} />
      </div>

      {error && <FieldError>{error}</FieldError>}
      <div style={cardStyle}>
        <div style={{ ...headRow, gridTemplateColumns: cols }}>
          <div style={labelStyle}>Team</div>
          <div style={labelStyle}>Team Admin</div>
          <div style={{ ...labelStyle, textAlign: 'center' }}>Members</div>
          <div style={{ ...labelStyle, textAlign: 'center' }}>Applications</div>
          <div />
        </div>
        {teams === null ? (
          <div style={{ padding: 20 }}>
            <SkeletonRows count={3} height={42} gap={14} />
          </div>
        ) : shown.length === 0 ? (
          <p style={{ padding: '40px 20px', margin: 0, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>No teams match your search.</p>
        ) : (
          shown.map((team) => (
            <div
              key={team.id}
              role="button"
              tabIndex={0}
              className="table-row-hover"
              onClick={() => setOpenId(team.id)}
              onKeyDown={(e) => {
                if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  setOpenId(team.id)
                }
              }}
              style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, alignItems: 'center', width: '100%', padding: '13px 20px', borderBottom: '1px solid var(--row-line)', cursor: 'pointer', textAlign: 'left', boxSizing: 'border-box' }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                <TeamMark name={team.name} />
                <span style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{team.name}</span>
              </span>
              <span style={{ fontSize: 12.5, color: 'var(--fg-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{team.team_admins.join(', ') || '—'}</span>
              <span style={{ ...monoNumber, textAlign: 'center' }}>{team.member_count}</span>
              <span style={{ ...monoNumber, textAlign: 'center' }}>{team.application_count}</span>
              <TeamRowMenu team={team} onView={() => setOpenId(team.id)} onDelete={() => setDeleting(team)} />
            </div>
          ))
        )}
      </div>

      {creating && (
        <CreateTeamDialog
          onClose={() => setCreating(false)}
          onCreated={(team) => {
            setCreating(false)
            setToast(`Team ${team.name} created`)
            setTeams((prev) => [...(prev ?? []), team].sort((a, b) => a.name.localeCompare(b.name)))
            setOpenId(team.id)
            workspace?.refresh()
          }}
        />
      )}
      {deleting && (
        <DeleteTeamDialog
          team={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            const gone = deleting
            setDeleting(null)
            setToast(`Team ${gone.name} deleted`)
            setTeams((prev) => (prev ?? []).filter((t) => t.id !== gone.id))
            if (workspace?.active.id === gone.id) workspace.switchTo(PERSONAL_WORKSPACE)
            workspace?.refresh()
          }}
        />
      )}
      {toast && <Toast message={toast} kind="success" onDismiss={() => setToast(null)} />}
    </div>
  )
}

// Own component so each row's menu has its own anchor ref. View team opens the
// team; Delete team asks first.
function TeamRowMenu({ team, onView, onDelete }: { team: TeamRead; onView: () => void; onDelete: () => void }) {
  const anchor = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  return (
    <span style={{ display: 'flex', justifyContent: 'flex-end' }} onClick={(e) => e.stopPropagation()}>
      <button
        ref={anchor}
        type="button"
        title="More options"
        aria-label={`Actions for ${team.name}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="icon-button-hover"
        style={{ width: 30, height: 30, border: 'none', borderRadius: 8, background: 'transparent', cursor: 'pointer', color: 'var(--fg-3)' }}
      >
        <FontAwesomeIcon icon={faEllipsisVertical} />
      </button>
      <AnchoredMenu anchorRef={anchor} open={open} onClose={() => setOpen(false)}>
        <div role="menu" style={{ minWidth: 184, padding: '4px 0', borderRadius: 10, background: 'var(--panel)', border: '1px solid var(--border-2)', boxShadow: '0 18px 44px rgba(10,12,16,0.24)' }}>
          <button type="button" role="menuitem" style={menuItemStyle} onClick={() => { setOpen(false); onView() }}>
            <FontAwesomeIcon icon={faEye} style={{ fontSize: 12, width: 14 }} />
            View team
          </button>
          <button type="button" role="menuitem" style={{ ...menuItemStyle, color: 'var(--bad)' }} onClick={() => { setOpen(false); onDelete() }}>
            <FontAwesomeIcon icon={faTrashCan} style={{ fontSize: 12, width: 14 }} />
            Delete team
          </button>
        </div>
      </AnchoredMenu>
    </span>
  )
}

// A team with applications can't be deleted: the dialog says so and what to do.
// An empty one asks for confirmation. The API refuses too (409) if an
// application turned up in the meantime.
function DeleteTeamDialog({ team, onClose, onDeleted }: { team: TeamRead; onClose: () => void; onDeleted: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const blocked = team.application_count > 0

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      await api.deleteTeam(team.id)
      onDeleted()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete this team — try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <EnvironmentModal
      title="Delete team"
      subtitle={team.name}
      onClose={onClose}
      maxWidth={480}
      footer={
        blocked ? (
          <button type="button" className="button-primary" onClick={onClose} style={{ height: 36, padding: '0 16px' }}>
            Close
          </button>
        ) : (
          <ModalActions onCancel={onClose} submitLabel="Delete team" busyLabel="Deleting" busy={busy} danger type="button" onSubmit={confirm} />
        )
      }
    >
      {blocked ? (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--fg-2)' }}>
          This team still has {plural(team.application_count, 'application')}, added by its members or shared at team level. Delete them first, then come back to delete the team.
        </p>
      ) : (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--fg-2)' }}>
          Delete {team.name}? Its {plural(team.member_count, 'member')} will lose access to this workspace. This can't be undone.
        </p>
      )}
      {error && <FieldError>{error}</FieldError>}
    </EnvironmentModal>
  )
}

// --- My team (a team admin's read-only page for the active team) --------------------

export function MyTeam() {
  const workspace = useWorkspace()
  const [team, setTeam] = useState<TeamRead | null>(null)
  const [error, setError] = useState<string | null>(null)
  const id = workspace && workspace.active.kind === 'team' ? workspace.active.id : null

  useEffect(() => {
    if (!id) return
    api
      .getTeam(id)
      .then(setTeam)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load the team.'))
  }, [id])

  if (!id) return <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>Switch to a team to see it here.</div>
  if (error) return <FieldError>{error}</FieldError>
  if (!team) return <SkeletonRows count={3} height={42} gap={14} />
  return <TeamDetail team={team} canManage={false} />
}

// --- one team: members and applications -------------------------------------------

function TeamDetail({
  team,
  canManage,
  onBack,
  onChanged,
}: {
  team: TeamRead
  canManage: boolean
  onBack?: () => void
  onChanged?: () => void
}) {
  const [tab, setTab] = useState<'members' | 'applications'>('members')
  const [members, setMembers] = useState<TeamPersonRead[] | null>(null)
  const [applications, setApplications] = useState<TeamApplicationRead[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [toast, setToast] = useState<{ message: string; kind: 'success' | 'error' } | null>(null)

  function loadMembers() {
    api
      .listTeamPeople(team.id)
      .then(setMembers)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load the members.'))
  }
  useEffect(() => {
    loadMembers()
    api
      .listTeamApplications(team.id)
      .then(setApplications)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load the applications.'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [team.id])

  function changed(message?: string) {
    loadMembers()
    onChanged?.()
    if (message) setToast({ message, kind: 'success' })
  }

  const admins = members?.filter((m) => m.role === 'team_admin').map((m) => m.name) ?? team.team_admins
  const tabButton = (key: 'members' | 'applications', label: string, count: number) => (
    <button
      type="button"
      role="tab"
      aria-selected={tab === key}
      onClick={() => setTab(key)}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '11px 14px', border: 'none', borderBottom: tab === key ? '2px solid var(--accent)' : '2px solid transparent', marginBottom: -1, background: 'transparent', cursor: 'pointer', font: 'inherit', fontSize: 13, fontWeight: 600, color: tab === key ? 'var(--fg)' : 'var(--fg-3)' }}
    >
      {label}
      <span style={{ ...monoNumber, fontSize: 11, padding: '1px 7px', borderRadius: 1000, background: 'var(--chip)', color: 'var(--fg-3)' }}>{count}</span>
    </button>
  )

  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {onBack && (
        <button type="button" className="link-back" onClick={onBack} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, border: 'none', background: 'none', cursor: 'pointer', font: 'inherit', fontSize: 12.5, fontWeight: 500, padding: 0, width: 'fit-content' }}>
          <FontAwesomeIcon icon={faArrowLeft} style={{ fontSize: 11 }} />
          All teams
        </button>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <TeamMark name={team.name} size={44} />
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h1 style={{ fontSize: 22, lineHeight: '28px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>{team.name}</h1>
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--fg-3)', margin: '3px 0 0' }}>
            Team Admin: {admins.join(', ') || '—'}
          </p>
        </div>
      </div>

      <div role="tablist" style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)' }}>
        {tabButton('members', 'Members', members?.length ?? team.member_count)}
        {tabButton('applications', 'Applications', applications?.length ?? team.application_count)}
      </div>
      {error && <FieldError>{error}</FieldError>}

      {tab === 'members' ? (
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '14px 20px', background: 'var(--panel-2)', borderBottom: '1px solid var(--border)' }}>
            <div style={{ flex: 1 }} />
            {canManage && (
              <button type="button" className="button-primary" onClick={() => setAdding(true)} style={primaryButton}>
                <FontAwesomeIcon icon={faUserPlus} style={{ fontSize: 11 }} />
                Add users
              </button>
            )}
          </div>
          {members === null ? (
            <div style={{ padding: 20 }}><SkeletonRows count={3} height={42} gap={14} /></div>
          ) : (
            members.map((member) => (
              <MemberRow
                key={member.email}
                member={member}
                team={team}
                canManage={canManage}
                onChanged={changed}
                onError={(message) => setToast({ message, kind: 'error' })}
              />
            ))
          )}
        </div>
      ) : (
        <ApplicationsTable applications={applications} />
      )}

      {adding && (
        <AddMemberDialog
          team={team}
          existing={(members ?? []).map((m) => m.email)}
          onClose={() => setAdding(false)}
          onAdded={(person) => {
            setAdding(false)
            changed(`${person.name} added to ${team.name}`)
          }}
        />
      )}
      {toast && <Toast message={toast.message} kind={toast.kind} onDismiss={() => setToast(null)} />}
    </div>
  )
}

function ApplicationsTable({ applications }: { applications: TeamApplicationRead[] | null }) {
  const cols = 'minmax(0,1.6fr) minmax(0,1fr) minmax(0,1.3fr)'
  return (
    <div style={cardStyle}>
      <div style={{ ...headRow, gridTemplateColumns: cols }}>
        <div style={labelStyle}>Application</div>
        <div style={labelStyle}>Added by</div>
        <div style={labelStyle}>Working on it</div>
      </div>
      {applications === null ? (
        <div style={{ padding: 20 }}><SkeletonRows count={3} height={42} gap={14} /></div>
      ) : applications.length === 0 ? (
        <p style={{ padding: '40px 20px', margin: 0, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>No applications added to this team yet.</p>
      ) : (
        applications.map((a) => (
          <div key={a.id} style={{ display: 'grid', gridTemplateColumns: cols, gap: 12, alignItems: 'center', padding: '13px 20px', borderBottom: '1px solid var(--row-line)' }}>
            <span style={{ minWidth: 0 }}>
              <span style={{ display: 'block', fontSize: 13.5, fontWeight: 500, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
              <span style={{ display: 'block', fontFamily: "'IBM Plex Mono', monospace", fontSize: 11.5, color: 'var(--fg-4)', marginTop: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.url}</span>
            </span>
            <span style={{ fontSize: 12.5, color: 'var(--fg-2)' }}>{a.added_by_name ?? '—'}</span>
            <span style={{ display: 'flex', alignItems: 'center' }}>
              {a.people.slice(0, 3).map((name) => (
                <span key={name} title={name} style={{ marginRight: -6, borderRadius: 1000, border: '2px solid var(--panel)', display: 'inline-flex' }}>
                  <Avatar name={name} size={26} />
                </span>
              ))}
              <span style={{ marginLeft: 14, fontSize: 11.5, color: 'var(--fg-4)' }}>{a.people_count > 3 ? `+${a.people_count - 3} more` : plural(a.people_count, 'person').replace('persons', 'people')}</span>
            </span>
          </div>
        ))
      )}
    </div>
  )
}

function MemberRow({
  member,
  team,
  canManage,
  onChanged,
  onError,
}: {
  member: TeamPersonRead
  team: TeamRead
  canManage: boolean
  onChanged: (message?: string) => void
  onError: (message: string) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [editing, setEditing] = useState(false)
  const anchor = useRef<HTMLButtonElement>(null)

  return (
    <div className="table-row-hover" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 200px 60px', gap: 12, alignItems: 'center', padding: '11px 20px', borderBottom: '1px solid var(--row-line)' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
        <span style={{ borderRadius: 1000, border: '1px solid var(--border-2)', display: 'inline-flex' }}>
          <Avatar name={member.name} size={26} />
        </span>
        <span title={member.email} style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{member.name}</span>
      </span>
      <span><span style={pillStyle(member.role === 'team_admin')}>{TEAM_ROLE_LABEL[member.role]}</span></span>
      <span style={{ textAlign: 'right' }}>
        {canManage && (
          <>
            <button
              ref={anchor}
              type="button"
              title="More options"
              aria-label={`Actions for ${member.name}`}
              onClick={() => setMenuOpen((v) => !v)}
              className="icon-button-hover"
              style={{ width: 30, height: 30, border: 'none', borderRadius: 8, background: 'transparent', cursor: 'pointer', color: 'var(--fg-3)' }}
            >
              <FontAwesomeIcon icon={faEllipsisVertical} />
            </button>
            <AnchoredMenu anchorRef={anchor} open={menuOpen} onClose={() => setMenuOpen(false)}>
              <div role="menu" style={{ minWidth: 184, padding: '4px 0', borderRadius: 10, background: 'var(--panel)', border: '1px solid var(--border-2)', boxShadow: '0 18px 44px rgba(10,12,16,0.24)' }}>
                <button type="button" role="menuitem" style={menuItemStyle} onClick={() => { setMenuOpen(false); setEditing(true) }}>
                  Edit role
                </button>
                <button type="button" role="menuitem" style={{ ...menuItemStyle, color: 'var(--bad)' }} onClick={() => { setMenuOpen(false); setConfirming(true) }}>
                  Remove from team
                </button>
              </div>
            </AnchoredMenu>
          </>
        )}
      </span>
      {editing && (
        <EditTeamRoleDialog
          member={member}
          team={team}
          onClose={() => setEditing(false)}
          onDone={(message) => { setEditing(false); onChanged(message) }}
          onError={onError}
        />
      )}
      {confirming && (
        <RemoveFromTeamDialog
          member={member}
          team={team}
          onClose={() => setConfirming(false)}
          onDone={(message) => { setConfirming(false); onChanged(message) }}
          onError={(message) => { setConfirming(false); onError(message) }}
        />
      )}
    </div>
  )
}

function EditTeamRoleDialog({
  member,
  team,
  onClose,
  onDone,
  onError,
}: {
  member: TeamPersonRead
  team: TeamRead
  onClose: () => void
  onDone: (message: string) => void
  onError: (message: string) => void
}) {
  const [role, setRole] = useState<TeamRole>(member.role)
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      await api.changeTeamPersonRole(team.id, member.email, role)
      onDone(`${member.name} is now ${TEAM_ROLE_LABEL[role]} of ${team.name}`)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Could not change the role — try again.')
      onClose()
    } finally {
      setBusy(false)
    }
  }

  return (
    <EnvironmentModal
      title="Edit role"
      subtitle={`${member.name} in ${team.name}`}
      onClose={onClose}
      onSubmit={submit}
      maxWidth={440}
      footer={<ModalActions onCancel={onClose} submitLabel="Update role" busyLabel="Updating" busy={busy} disabled={role === member.role} />}
    >
      <fieldset style={{ border: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {(['team_member', 'team_admin'] as TeamRole[]).map((value) => (
          <label key={value} style={{ display: 'flex', gap: 10, padding: '10px 12px', borderRadius: 10, border: `1px solid ${role === value ? 'var(--accent)' : 'var(--border-2)'}`, cursor: 'pointer' }}>
            <input type="radio" name="team-role" checked={role === value} onChange={() => setRole(value)} />
            <span>
              <span style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>{TEAM_ROLE_LABEL[value]}</span>
              <span style={{ display: 'block', fontSize: 12, color: 'var(--fg-3)' }}>
                {value === 'team_admin'
                  ? 'Sees every application in the team and decides who can use each one.'
                  : 'Sees the applications they added or that were shared with them.'}
              </span>
            </span>
          </label>
        ))}
      </fieldset>
    </EnvironmentModal>
  )
}

function RemoveFromTeamDialog({
  member,
  team,
  onClose,
  onDone,
  onError,
}: {
  member: TeamPersonRead
  team: TeamRead
  onClose: () => void
  onDone: (message: string) => void
  onError: (message: string) => void
}) {
  const [busy, setBusy] = useState(false)

  async function confirm() {
    setBusy(true)
    try {
      await api.removeTeamPerson(team.id, member.email)
      onDone(`${member.name} was removed from ${team.name}`)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Could not remove this person — try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <EnvironmentModal
      title="Remove from team"
      subtitle={`${member.name} · ${team.name}`}
      onClose={onClose}
      maxWidth={460}
      footer={<ModalActions onCancel={onClose} submitLabel="Remove" busyLabel="Removing" busy={busy} danger type="button" onSubmit={confirm} />}
    >
      <p style={{ margin: 0, fontSize: 13, color: 'var(--fg-2)' }}>
        They lose access to this team's workspace and to every application shared with them in it. Applications they added stay with the team and go to the Team Admins.
      </p>
    </EnvironmentModal>
  )
}

// People of the organisation, for the pickers (a super admin lists them all).
function usePeople(): TeamMemberRead[] | null {
  const [people, setPeople] = useState<TeamMemberRead[] | null>(null)
  useEffect(() => {
    api.listTeam().then(setPeople).catch(() => setPeople([]))
  }, [])
  return people
}

const matches = (person: Person, query: string) => {
  const q = query.trim().toLowerCase()
  return !!q && (person.name.toLowerCase().includes(q) || person.email.toLowerCase().includes(q))
}

function AddMemberDialog({
  team,
  existing,
  onClose,
  onAdded,
}: {
  team: TeamRead
  existing: string[]
  onClose: () => void
  onAdded: (person: Person) => void
}) {
  const people = usePeople()
  const [query, setQuery] = useState('')
  const [picked, setPicked] = useState<Person | null>(null)
  const [role, setRole] = useState<TeamRole>('team_member')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const options = (people ?? []).filter((p) => !existing.includes(p.email) && matches(p, query)).slice(0, 8)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!picked) return
    setBusy(true)
    setError(null)
    try {
      await api.addTeamPerson(team.id, picked.email, role)
      onAdded(picked)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not add this person — try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <EnvironmentModal
      title="Add team member"
      subtitle={team.name}
      onClose={onClose}
      onSubmit={submit}
      maxWidth={480}
      footer={<ModalActions onCancel={onClose} submitLabel="Add member" busyLabel="Adding" busy={busy} disabled={!picked} />}
    >
      <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={fieldLabel}>Email address</span>
        <PersonPicker
          label="Email address"
          query={picked ? picked.email : query}
          onQuery={(value) => {
            setPicked(null)
            setQuery(value)
          }}
          options={options}
          onPick={(person) => {
            setPicked(person)
            setQuery(person.email)
          }}
          placeholder="Type email address"
          height={40}
        />
      </label>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={fieldLabel}>Role</span>
        <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value as TeamRole)} style={{ height: 40, borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', padding: '0 10px', font: 'inherit', fontSize: 14, color: 'var(--fg)' }}>
          <option value="team_member">{TEAM_ROLE_LABEL.team_member}</option>
          <option value="team_admin">{TEAM_ROLE_LABEL.team_admin}</option>
        </select>
      </label>
      {error && <FieldError>{error}</FieldError>}
    </EnvironmentModal>
  )
}

function CreateTeamDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (team: TeamRead) => void }) {
  const people = usePeople()
  const [name, setName] = useState('')
  const [query, setQuery] = useState('')
  const [admins, setAdmins] = useState<Person[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const options = (people ?? []).filter((p) => !admins.some((a) => a.email === p.email) && matches(p, query)).slice(0, 8)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onCreated(await api.createTeam(name, admins.map((a) => a.email)))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create the team — try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <EnvironmentModal
      title="Create team"
      onClose={onClose}
      onSubmit={submit}
      maxWidth={500}
      footer={<ModalActions onCancel={onClose} submitLabel="Create team" busyLabel="Creating" busy={busy} disabled={!name.trim() || admins.length === 0} />}
    >
      <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={fieldLabel}>Team name</span>
        <div className="field-shell" style={{ height: 38 }}>
          <input data-bare aria-label="Team name" value={name} placeholder="Enter the team name" onChange={(e) => setName(e.target.value)} />
        </div>
      </label>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={fieldLabel}>Team Admins <span style={{ fontWeight: 400, color: 'var(--fg-4)' }}>· at least one</span></span>
        {admins.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {admins.map((admin) => (
              <span key={admin.email} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 6px 3px 10px', borderRadius: 1000, background: 'rgba(30,150,138,0.12)', color: 'var(--accent-2)', fontSize: 12, fontWeight: 600 }}>
                {admin.name}
                <button type="button" aria-label={`Remove ${admin.name}`} onClick={() => setAdmins((prev) => prev.filter((a) => a.email !== admin.email))} style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'inherit', padding: 0 }}>
                  <FontAwesomeIcon icon={faXmark} style={{ fontSize: 11 }} />
                </button>
              </span>
            ))}
          </div>
        )}
        <PersonPicker label="Team Admins" query={query} onQuery={setQuery} options={options} placeholder="Type name or email address" height={38} onPick={(person) => { setAdmins((prev) => [...prev, person]); setQuery('') }} />
      </div>
      {error && <FieldError>{error}</FieldError>}
    </EnvironmentModal>
  )
}
