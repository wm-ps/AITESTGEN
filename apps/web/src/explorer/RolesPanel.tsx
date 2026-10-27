import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faPlus, faTrashCan, faUsers } from '@fortawesome/free-solid-svg-icons'
import { LoadingDots } from '../components/LoadingDots'
import { explorerApi, type ExplorerRole } from './explorerApi'
import { Pill } from './ui'

export function RolesPanel({ applicationId }: { applicationId: string }) {
  const [roles, setRoles] = useState<ExplorerRole[]>([])
  const [name, setName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = () => explorerApi.roles(applicationId).then(setRoles).catch(() => {})
  useEffect(() => {
    void load()
  }, [applicationId]) // eslint-disable-line react-hooks/exhaustive-deps
  const input = { fontFamily: 'inherit', fontSize: 13, padding: '8px 10px', minWidth: 0 } as const
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--fg-2)' }}>Other kinds of users <span style={{ fontWeight: 400, color: 'var(--fg-5)' }}>(optional)</span></div>
      {roles.map((r) => (
        <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}>
          <Pill icon={faUsers}>{r.name}</Pill>
          <span style={{ color: 'var(--fg-5)' }}>login saved securely</span>
          <button
            type="button"
            aria-label={`Remove ${r.name}`}
            onClick={async () => {
              await explorerApi.deleteRole(r.id)
              await load()
            }}
            style={{ border: 'none', background: 'transparent', color: 'var(--fg-5)', cursor: 'pointer' }}
          >
            <FontAwesomeIcon icon={faTrashCan} style={{ fontSize: 11 }} />
          </button>
        </div>
      ))}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 8 }}>
        <input className="field" aria-label="User type" placeholder="Enter the user type, like Viewer" value={name} onChange={(e) => setName(e.target.value)} style={input} />
        <input className="field" aria-label="Username" placeholder="Enter its username" value={username} onChange={(e) => setUsername(e.target.value)} style={input} autoComplete="off" />
        <input className="field" aria-label="Password" placeholder="Enter its password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={input} autoComplete="new-password" />
        <button
          type="button"
          className="button-secondary"
          disabled={busy || !name.trim() || !username.trim() || !password}
          onClick={async () => {
            setBusy(true)
            setError(null)
            try {
              await explorerApi.addRole(applicationId, name.trim(), username.trim(), password)
              setName('')
              setUsername('')
              setPassword('')
              await load()
            } catch (e) {
              setError(e instanceof Error ? e.message : 'Could not save the login')
            } finally {
              setBusy(false)
            }
          }}
        >
          {busy ? <LoadingDots label="Saving" /> : <FontAwesomeIcon icon={faPlus} />}
        </button>
      </div>
      {error && <div style={{ fontSize: 12, color: 'var(--danger)' }}>{error}</div>}
    </div>
  )
}
