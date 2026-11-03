import { useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEye, faEyeSlash, faPencil, faPlus, faTrash } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type EnvironmentRead } from '../../api'
import { useCanEdit } from '../../PermissionsContext'
import { EditEnvironmentDialog } from '../environments/EditEnvironmentDialog'
import { useEnvironments } from '../environments/EnvironmentsContext'
import { RemoveEnvironmentDialog } from '../environments/RemoveEnvironmentDialog'
import { SkeletonRows } from '../Skeleton'

const GRID_TEMPLATE =
  'minmax(130px,1.1fr) minmax(170px,1.5fr) minmax(170px,1.5fr) minmax(150px,1.3fr) minmax(130px,1.1fr) 84px'
const REVEAL_FOR_MS = 15_000

const headerStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--fg-4)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
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

const keyOf = (environment: EnvironmentRead) => environment.id ?? 'default'

// Application settings: the application's own (default) environment and every
// extra one, with their URLs and sign-in details. Admins and members add, edit
// and remove (and can reveal a password); a viewer sees the table read-only.
export function AppSettingsTab({ applicationId }: { applicationId: string }) {
  const canEdit = useCanEdit()
  const context = useEnvironments()
  const [editing, setEditing] = useState<EnvironmentRead | null>(null)
  const [removing, setRemoving] = useState<EnvironmentRead | null>(null)
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
      {canEdit && canAdd && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
          <button
            type="button"
            onClick={() => requestAdd()}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              height: 38,
              padding: '0 18px',
              borderRadius: 8,
              border: 'none',
              fontSize: 13.5,
              fontWeight: 600,
              color: '#fff',
              background: 'var(--accent)',
              boxShadow: '0 4px 14px rgba(30,150,138,0.3)',
              cursor: 'pointer',
            }}
          >
            <FontAwesomeIcon icon={faPlus} style={{ fontSize: 11 }} />
            Add environment
          </button>
        </div>
      )}
      {revealError && (
        <p role="alert" style={{ color: 'var(--bad)', fontSize: 13, marginBottom: 14 }}>
          {revealError}
        </p>
      )}

      {environments.length === 0 ? (
        <SkeletonRows count={2} height={48} gap={10} />
      ) : (
        <div
          style={{
            background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
            backdropFilter: 'blur(16px) saturate(1.25)',
            border: '1px solid var(--border-1)',
            borderRadius: 14,
            boxShadow: 'var(--panel-shadow)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{ display: 'grid', gridTemplateColumns: GRID_TEMPLATE, alignItems: 'center', gap: 14, padding: '12px 20px', background: 'var(--panel-2)' }}
          >
            <div style={headerStyle}>Environment</div>
            <div style={headerStyle}>Deployed URL</div>
            <div style={headerStyle}>Login URL</div>
            <div style={headerStyle}>Username</div>
            <div style={headerStyle}>Password</div>
            <div style={{ ...headerStyle, textAlign: 'right' }}>Actions</div>
          </div>
          {environments.map((environment) => {
            const key = keyOf(environment)
            const signsIn = environment.auth_method === 'standard_login'
            const shown = revealed[key]
            return (
              <div
                key={key}
                data-testid={`environment-row-${environment.name}`}
                style={{
                  display: 'grid',
                  gridTemplateColumns: GRID_TEMPLATE,
                  alignItems: 'center',
                  gap: 14,
                  padding: '14px 20px',
                  borderBottom: '1px solid var(--row-line)',
                  borderLeft: environment.is_default ? '3px solid var(--accent)' : '3px solid transparent',
                  background: environment.is_default ? 'var(--accent-wash)' : undefined,
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ ...cellTextStyle, fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }} title={environment.name}>
                    {environment.name}
                  </div>
                  {environment.is_default && (
                    <span
                      style={{
                        display: 'inline-block',
                        marginTop: 5,
                        padding: '1px 9px',
                        borderRadius: 1000,
                        fontSize: 11,
                        fontWeight: 600,
                        color: 'var(--accent-2)',
                        background: 'var(--chip)',
                        border: '1px solid var(--accent-wash)',
                      }}
                    >
                      Default
                    </span>
                  )}
                </div>
                <div style={monoStyle} title={environment.url}>
                  {environment.url}
                </div>
                <div style={monoStyle} title={environment.login_url ?? undefined}>
                  {environment.login_url ?? '—'}
                </div>
                <div style={monoStyle}>{signsIn ? (environment.username ?? '—') : '—'}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  {signsIn ? (
                    <>
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
                    </>
                  ) : (
                    <span style={{ color: 'var(--fg-4)' }}>—</span>
                  )}
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 4 }}>
                  {canEdit && (signsIn || !environment.is_default) && (
                    <button
                      type="button"
                      aria-label={`Edit ${environment.name} environment`}
                      title="Edit"
                      onClick={() => setEditing(environment)}
                      style={{ ...iconButtonStyle, color: 'var(--fg-2)' }}
                    >
                      <FontAwesomeIcon icon={faPencil} style={{ fontSize: 13 }} />
                    </button>
                  )}
                  {canEdit && !environment.is_default && (
                    <button
                      type="button"
                      aria-label={`Remove ${environment.name} environment`}
                      title="Remove"
                      onClick={() => setRemoving(environment)}
                      style={{ ...iconButtonStyle, color: 'var(--bad)' }}
                    >
                      <FontAwesomeIcon icon={faTrash} style={{ fontSize: 13 }} />
                    </button>
                  )}
                </div>
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
