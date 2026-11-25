import { createPortal } from 'react-dom'
import { useCallback, useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCheck, faLock, faUserGroup, faUserMinus, faUserPen, faXmark } from '@fortawesome/free-solid-svg-icons'
import { APP_ROLE_LABEL, ApiError, api, type AccessEntryRead, type AppRole, type CandidateRead } from '../api'
import { useEscapeToClose } from '../hooks/useEscapeToClose'
import { FieldError } from './environments/EnvironmentModal'
import { LoadingDots } from './LoadingDots'
import { modalCloseButton, modalOverlay, modalPanel } from './modalStyles'
import { Avatar, PersonPicker } from './PersonPicker'
import { Toast } from './Toast'

const ROLES: AppRole[] = ['app_admin', 'contributor', 'viewer']

const pillStyle = (role: AppRole): React.CSSProperties => ({
  display: 'inline-flex',
  alignItems: 'center',
  height: 26,
  padding: '0 11px',
  borderRadius: 1000,
  fontSize: 12,
  fontWeight: 600,
  whiteSpace: 'nowrap',
  background: role === 'app_admin' ? 'rgba(30,150,138,0.12)' : 'var(--chip)',
  color: role === 'app_admin' ? 'var(--accent-2)' : role === 'viewer' ? 'var(--fg-3)' : 'var(--fg-2)',
})

const selectStyle: React.CSSProperties = {
  height: 38,
  minWidth: 150,
  borderRadius: 8,
  border: '1px solid var(--border-2)',
  background: 'var(--panel)',
  padding: '0 10px',
  font: 'inherit',
  fontSize: 13,
  color: 'var(--fg)',
}

const iconButton: React.CSSProperties = {
  width: 28,
  height: 28,
  border: 'none',
  borderRadius: 8,
  background: 'transparent',
  cursor: 'pointer',
  color: 'var(--fg-4)',
  fontSize: 12,
}

// Who can see this application and with which role. Application admins (the
// adder, team admins, super admins on a team's applications) open it from the
// Applications list or the application header. The adder and the team admins
// are locked rows: full access, not editable. A team's application can only be
// shared with members of that team; a personal one with anyone.
export function ManageAccessDialog({
  applicationId,
  applicationName,
  onClose,
  onChanged,
}: {
  applicationId: string
  applicationName: string
  onClose: () => void
  /** Called after any change, so the list behind can refresh its counts. */
  onChanged?: () => void
}) {
  const [entries, setEntries] = useState<AccessEntryRead[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<{ message: string; kind: 'success' | 'error' } | null>(null)

  const [query, setQuery] = useState('')
  const [options, setOptions] = useState<CandidateRead[]>([])
  const [searching, setSearching] = useState(false)
  const [picked, setPicked] = useState<CandidateRead | null>(null)
  const [role, setRole] = useState<AppRole>('viewer')
  const [sharing, setSharing] = useState(false)

  const [editing, setEditing] = useState<{ email: string; role: AppRole } | null>(null)
  const [saving, setSaving] = useState(false)
  const editingRef = useRef(editing)
  editingRef.current = editing

  const load = useCallback(() => {
    api
      .listAccess(applicationId)
      .then((rows) => {
        setEntries(rows)
        setError(null)
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load who has access.'))
  }, [applicationId])
  useEffect(load, [load])

  // Escape cancels a role edit first, then closes the dialog. Closing from the
  // X, Escape or the footer only — never a click outside, which would throw away
  // what was typed.
  useEscapeToClose(
    useCallback(() => {
      if (editingRef.current) setEditing(null)
      else onClose()
    }, [onClose]),
  )

  // Server-side type-ahead: team members (or, for a personal application, anyone)
  // who don't have access yet.
  useEffect(() => {
    const q = query.trim()
    if (!q || picked) {
      setOptions([])
      return
    }
    setSearching(true)
    let cancelled = false
    const timer = setTimeout(() => {
      api
        .accessCandidates(applicationId, q)
        .then((rows) => !cancelled && setOptions(rows))
        .catch(() => !cancelled && setOptions([]))
        .finally(() => !cancelled && setSearching(false))
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [applicationId, query, picked])

  async function share() {
    if (!picked) return
    setSharing(true)
    try {
      await api.shareApplication(applicationId, picked.email, role)
      setToast({ message: `${picked.name} added`, kind: 'success' })
      setPicked(null)
      setQuery('')
      setRole('viewer')
      load()
      onChanged?.()
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not share — try again.', kind: 'error' })
    } finally {
      setSharing(false)
    }
  }

  async function saveRole(entry: AccessEntryRead) {
    if (!editing) return
    setSaving(true)
    try {
      await api.changeAccessRole(applicationId, entry.email, editing.role)
      setToast({ message: `${entry.name} is now ${APP_ROLE_LABEL[editing.role]}`, kind: 'success' })
      setEditing(null)
      load()
      onChanged?.()
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not change the role — try again.', kind: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function remove(entry: AccessEntryRead) {
    try {
      await api.removeAccess(applicationId, entry.email)
      setToast({ message: `${entry.name} removed`, kind: 'success' })
      load()
      onChanged?.()
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not remove access — try again.', kind: 'error' })
    }
  }

  const cols = 'minmax(0,1fr) 158px 66px'
  // Portaled to <body>: a card with `backdrop-filter` becomes the containing
  // block of `position: fixed`, which would trap the overlay inside it.
  return createPortal(
    <div style={{ ...modalOverlay, zIndex: 90, background: 'rgba(10,12,16,0.46)', backdropFilter: 'blur(3px)', padding: 24 }}>
      <div role="dialog" aria-modal="true" aria-label="Manage access" style={{ ...modalPanel, maxWidth: 560, border: '1px solid var(--border)', boxShadow: '0 30px 80px rgba(10,12,16,0.3)', maxHeight: 'calc(100vh - 48px)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '20px 22px 14px' }}>
          <span aria-hidden="true" style={{ width: 40, height: 40, flex: 'none', borderRadius: 11, background: 'rgba(30,150,138,0.12)', color: 'var(--accent-2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <FontAwesomeIcon icon={faUserGroup} />
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.015em' }}>Manage access</h2>
            <p style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--fg-3)', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 500, color: 'var(--fg-2)', whiteSpace: 'nowrap' }}>{applicationName}</span>
              {entries && <span style={{ fontSize: 12, color: 'var(--fg-4)' }}>{entries.length === 1 ? '1 person has access' : `${entries.length} people have access`}</span>}
            </p>
          </div>
          <button type="button" aria-label="Close" className="icon-button-hover" onClick={onClose} style={{ ...modalCloseButton, width: 28, height: 28, padding: 0, borderRadius: 8, color: 'var(--fg-4)' }}>
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>

        <div style={{ padding: '0 22px 16px', display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <PersonPicker
            label="Person to share with"
            query={picked ? picked.email : query}
            onQuery={(value) => {
              setPicked(null)
              setQuery(value)
            }}
            options={options}
            loading={searching}
            onPick={(person) => {
              setPicked(person)
              setQuery(person.email)
            }}
            placeholder="Type name or email address"
          />
          <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value as AppRole)} style={selectStyle}>
            {ROLES.map((value) => (
              <option key={value} value={value}>{APP_ROLE_LABEL[value]}</option>
            ))}
          </select>
          <button type="button" className="button-primary" disabled={!picked || sharing} onClick={share} style={{ height: 38, padding: '0 16px', whiteSpace: 'nowrap', cursor: !picked || sharing ? 'not-allowed' : 'pointer', opacity: !picked ? 0.6 : 1 }}>
            {sharing ? <LoadingDots label="Sharing" /> : 'Share'}
          </button>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', borderTop: '1px solid var(--border)' }}>
          {error && <div style={{ padding: '12px 22px' }}><FieldError>{error}</FieldError></div>}
          {entries?.map((entry) => {
            const isEditing = editing !== null && editing.email === entry.email
            return (
              <div key={entry.email} data-testid={`access-row-${entry.email}`} style={{ display: 'grid', gridTemplateColumns: cols, gap: 10, alignItems: 'center', padding: '10px 22px', borderBottom: '1px solid var(--row-line)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                  <span style={{ borderRadius: 1000, border: '1px solid var(--border-2)', display: 'inline-flex' }}>
                    <Avatar name={entry.name} />
                  </span>
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--fg-1)' }}>
                      {entry.name}
                      {entry.reason && <span style={{ marginLeft: 6, fontSize: 11, fontWeight: 500, color: 'var(--fg-4)' }}>{entry.reason}</span>}
                    </span>
                    <span style={{ display: 'block', fontSize: 11.5, color: 'var(--fg-4)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {entry.email}
                    </span>
                  </span>
                </span>
                <span>
                  {isEditing ? (
                    <select aria-label={`Role for ${entry.name}`} value={editing.role} onChange={(e) => setEditing({ email: entry.email, role: e.target.value as AppRole })} style={{ ...selectStyle, height: 30, minWidth: 0, width: '100%', borderRadius: 7, fontSize: 12.5, borderColor: 'var(--accent)' }}>
                      {ROLES.map((value) => (
                        <option key={value} value={value}>{APP_ROLE_LABEL[value]}</option>
                      ))}
                    </select>
                  ) : (
                    <span style={pillStyle(entry.role)}>{APP_ROLE_LABEL[entry.role]}</span>
                  )}
                </span>
                <span style={{ display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
                  {entry.locked ? (
                    <span title="Always has access. Can't be changed or removed." aria-label="Locked" style={{ width: 28, height: 28, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-5)' }}>
                      <FontAwesomeIcon icon={faLock} style={{ fontSize: 11 }} />
                    </span>
                  ) : isEditing ? (
                    <>
                      <button type="button" aria-label={`Save role for ${entry.name}`} disabled={saving} onClick={() => saveRole(entry)} style={{ ...iconButton, background: 'var(--accent)', color: '#fff' }}>
                        <FontAwesomeIcon icon={faCheck} />
                      </button>
                      <button type="button" aria-label="Cancel" className="icon-button-hover" onClick={() => setEditing(null)} style={{ ...iconButton, color: 'var(--fg-3)' }}>
                        <FontAwesomeIcon icon={faXmark} />
                      </button>
                    </>
                  ) : (
                    <>
                      <button type="button" title="Edit role" aria-label={`Change role for ${entry.name}`} onClick={() => setEditing({ email: entry.email, role: entry.role })} className="icon-button-hover" style={iconButton}>
                        <FontAwesomeIcon icon={faUserPen} />
                      </button>
                      <button type="button" title="Remove access" aria-label={`Remove access for ${entry.name}`} onClick={() => remove(entry)} className="icon-button-danger" style={iconButton}>
                        <FontAwesomeIcon icon={faUserMinus} />
                      </button>
                    </>
                  )}
                </span>
              </div>
            )
          })}
          {entries === null && !error && <p style={{ padding: '14px 22px', margin: 0, fontSize: 13, color: 'var(--fg-3)' }}><LoadingDots label="Loading" /></p>}
        </div>
      </div>
      {toast && <Toast message={toast.message} kind={toast.kind} onDismiss={() => setToast(null)} />}
    </div>,
    document.body,
  )
}
