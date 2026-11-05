import { useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEllipsisVertical, faEye, faEyeSlash, faPlus, faStar } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type EnvironmentRead } from '../../api'
import { useCanEdit } from '../../PermissionsContext'
import { EditEnvironmentDialog } from '../environments/EditEnvironmentDialog'
import { useEnvironments } from '../environments/EnvironmentsContext'
import { RemoveEnvironmentDialog } from '../environments/RemoveEnvironmentDialog'
import { SkeletonRows } from '../Skeleton'
import { AnchoredMenu } from '../AnchoredMenu'

const REVEAL_FOR_MS = 15_000

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--fg-4)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  marginBottom: 2,
}

const cardStyle: React.CSSProperties = {
  background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
  backdropFilter: 'blur(16px) saturate(1.25)',
  border: '1px solid var(--border-1)',
  borderRadius: 14,
  boxShadow: 'var(--panel-shadow)',
  padding: 24,
}

const menuItemStyle: React.CSSProperties = {
  display: 'block',
  width: '100%',
  textAlign: 'left',
  padding: '8px 12px',
  border: 'none',
  background: 'none',
  borderRadius: 7,
  fontSize: 14,
  color: 'var(--fg-1)',
  cursor: 'pointer',
}

const cellTextStyle: React.CSSProperties = {
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const monoStyle: React.CSSProperties = { ...cellTextStyle, fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--fg-2)' }

const iconButtonStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 28,
  height: 28,
  borderRadius: 7,
  border: 'none',
  background: 'none',
  padding: 0,
  cursor: 'pointer',
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginTop: 10 }}>
      <div style={labelStyle}>{label}</div>
      <div style={{ ...monoStyle, fontSize: 13.5 }} title={value}>
        {value}
      </div>
    </div>
  )
}

const keyOf = (environment: EnvironmentRead) => environment.id ?? 'default'

function EnvironmentMenu({
  environment,
  open,
  onToggle,
  onClose,
  onEdit,
  onRemove,
}: {
  environment: EnvironmentRead
  open: boolean
  onToggle: () => void
  onClose: () => void
  onEdit?: () => void
  onRemove?: () => void
}) {
  const buttonRef = useRef<HTMLButtonElement>(null)
  return (
    <div style={{ position: 'relative' }}>
      <button
        ref={buttonRef}
        type="button"
        aria-label={`Actions for ${environment.name} environment`}
        aria-haspopup="menu"
        onClick={onToggle}
        style={{ ...iconButtonStyle, color: 'var(--fg-2)' }}
      >
        <FontAwesomeIcon icon={faEllipsisVertical} style={{ fontSize: 15 }} />
      </button>
      <AnchoredMenu anchorRef={buttonRef} open={open} onClose={onClose}>
        <div role="menu" style={{ width: 'max-content', padding: 4, background: 'var(--panel)', border: '1px solid var(--border-2)', borderRadius: 10, boxShadow: 'var(--panel-shadow)' }}>
          {onEdit && (
            <button
              type="button"
              role="menuitem"
              aria-label={`Edit ${environment.name} environment`}
              onClick={() => {
                onClose()
                onEdit()
              }}
              style={menuItemStyle}
            >
              Edit
            </button>
          )}
          {onRemove && (
            <button
              type="button"
              role="menuitem"
              aria-label={`Remove ${environment.name} environment`}
              onClick={() => {
                onClose()
                onRemove()
              }}
              style={{ ...menuItemStyle, color: 'var(--bad)' }}
            >
              Delete
            </button>
          )}
        </div>
      </AnchoredMenu>
    </div>
  )
}

// Application settings: the application's own (default) environment and every
// extra one, with their URLs and sign-in details. Admins and members add, edit
// and remove (and can reveal a password); a viewer sees the cards read-only.
export function AppSettingsTab({ applicationId }: { applicationId: string }) {
  const canEdit = useCanEdit()
  const context = useEnvironments()
  const [editing, setEditing] = useState<EnvironmentRead | null>(null)
  const [removing, setRemoving] = useState<EnvironmentRead | null>(null)
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [revealed, setRevealed] = useState<Record<string, string>>({})
  const [revealError, setRevealError] = useState<string | null>(null)
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  useEffect(() => {
    const pending = timers.current
    return () => Object.values(pending).forEach(clearTimeout)
  }, [])

  if (!context) return null
  const { environments, refresh, canAdd, requestAdd } = context
  const defaultEnvironment = environments.find((environment) => environment.is_default)

  function hide(key: string) {
    clearTimeout(timers.current[key])
    delete timers.current[key]
    setRevealed((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  async function toggleReveal(environment: EnvironmentRead) {
    const key = keyOf(environment)
    if (revealed[key] !== undefined) {
      hide(key)
      return
    }
    setRevealError(null)
    try {
      const { password } = await api.revealEnvironmentPassword(applicationId, environment.id)
      setRevealed((prev) => ({ ...prev, [key]: password }))
      timers.current[key] = setTimeout(() => hide(key), REVEAL_FOR_MS)
    } catch (err) {
      setRevealError(err instanceof ApiError ? err.message : 'Could not show this password.')
    }
  }

  return (
    <div>
      {revealError && (
        <p role="alert" style={{ color: 'var(--bad)', fontSize: 13, marginBottom: 14 }}>
          {revealError}
        </p>
      )}

      {environments.length === 0 ? (
        <SkeletonRows count={2} height={48} gap={10} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(360px,1fr))', gap: 20, gridAutoRows: '1fr' }}>
          {canEdit && canAdd && (
            <button
              type="button"
              aria-label="Add environment"
              onClick={() => requestAdd()}
              style={{ ...cardStyle, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, textAlign: 'center', cursor: 'pointer', borderColor: 'var(--accent)' }}
            >
              <span style={{ width: 50, height: 50, borderRadius: '50%', background: 'var(--panel-2)', color: 'var(--accent-2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                <FontAwesomeIcon icon={faPlus} style={{ fontSize: 16 }} />
              </span>
              <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--accent-2)' }}>Add environment</span>
              <span style={{ fontSize: 13, color: 'var(--fg-3)', maxWidth: 260 }}>
                Add another deployment URL to validate the same test cases against.
              </span>
            </button>
          )}
          {environments.map((environment) => {
            const key = keyOf(environment)
            const signsIn = environment.auth_method === 'standard_login'
            const shown = revealed[key]
            const canEditThis = canEdit && (signsIn || !environment.is_default)
            const canRemoveThis = canEdit && !environment.is_default
            return (
              <div
                key={key}
                data-testid={`environment-row-${environment.name}`}
                style={cardStyle}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                  {environment.is_default && <FontAwesomeIcon icon={faStar} style={{ fontSize: 14, color: 'var(--accent-2)' }} />}
                  <div style={{ ...cellTextStyle, flex: 1, fontSize: 16, fontWeight: 600, color: 'var(--fg)' }} title={environment.name}>
                    {environment.name}
                  </div>
                  {(canEditThis || canRemoveThis) && (
                    <EnvironmentMenu
                      environment={environment}
                      open={menuFor === key}
                      onToggle={() => setMenuFor((v) => (v === key ? null : key))}
                      onClose={() => setMenuFor(null)}
                      onEdit={canEditThis ? () => setEditing(environment) : undefined}
                      onRemove={canRemoveThis ? () => setRemoving(environment) : undefined}
                    />
                  )}
                </div>
                <Field label="Deployed URL" value={environment.url} />
                {environment.login_url && <Field label="Login URL" value={environment.login_url} />}
                {signsIn && <Field label="Username" value={environment.username ?? '—'} />}
                {signsIn && (
                  <div style={{ marginTop: 10 }}>
                    <div style={labelStyle}>Password</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                      <span style={{ ...monoStyle, letterSpacing: shown === undefined ? '0.1em' : undefined }}>
                        {shown ?? '••••••••••'}
                      </span>
                      {canEdit && (
                        <button
                          type="button"
                          aria-label={`${shown === undefined ? 'Show' : 'Hide'} password for ${environment.name}`}
                          aria-pressed={shown !== undefined}
                          onClick={() => toggleReveal(environment)}
                          style={{ ...iconButtonStyle, width: 24, height: 24, color: 'var(--fg-4)' }}
                        >
                          <FontAwesomeIcon icon={shown === undefined ? faEye : faEyeSlash} style={{ fontSize: 13 }} />
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {editing && defaultEnvironment && (
        <EditEnvironmentDialog
          applicationId={applicationId}
          environment={editing}
          defaultEnvironment={defaultEnvironment}
          onClose={() => setEditing(null)}
          onSaved={() => {
            hide(keyOf(editing))
            setEditing(null)
            refresh()
          }}
        />
      )}
      {removing && (
        <RemoveEnvironmentDialog
          applicationId={applicationId}
          environment={removing}
          onClose={() => setRemoving(null)}
          onRemoved={() => {
            setRemoving(null)
            refresh()
          }}
        />
      )}
    </div>
  )
}
