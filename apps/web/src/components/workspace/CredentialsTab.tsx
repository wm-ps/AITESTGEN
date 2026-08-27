import { useEffect, useState } from 'react'
import { ApiError, api, type ApplicationRead } from '../../api'
import { PasswordInput } from '../PasswordInput'

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="label-required" style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
      {children}
    </span>
  )
}

const AUTH_METHOD_LABEL: Record<string, string> = {
  standard_login: 'Username & Password',
  sso_session_reuse: 'SSO / Session Reuse',
}

// Admin-only rotation for a standard_login Application's stored username/
// password. Laid out like ConnectAppForm's read-only receipt (same field
// grid, same card width) so this reads as "the connection", not a bare
// two-input form — the read-only fields here are never editable, only the
// credential fields at the bottom submit anywhere. No support for
// sso_session_reuse apps (a session_state blob isn't what this form
// collects) — matches the confirmed V1 scope.
export function CredentialsTab({ applicationId }: { applicationId: string }) {
  const [application, setApplication] = useState<ApplicationRead | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .getApplication(applicationId)
      .then((app) => !cancelled && setApplication(app))
      .catch(() => !cancelled && setLoadError(true))
    return () => {
      cancelled = true
    }
  }, [applicationId])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSuccess(false)
    setSubmitting(true)
    try {
      await api.updateApplicationCredentials(applicationId, username, password)
      setSuccess(true)
      setUsername('')
      setPassword('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Updating credentials failed.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loadError) {
    return (
      <p role="alert" style={{ color: 'var(--danger)', fontSize: 13 }}>
        Couldn't load this Application's connection details.
      </p>
    )
  }
  if (!application) {
    return (
      <p className="caption" style={{ fontSize: 12.5 }}>
        Loading…
      </p>
    )
  }

  const notStandardLogin = application.auth_method !== 'standard_login'

  return (
    <form
      onSubmit={handleSubmit}
      className="card-panel"
      style={{
        padding: '20px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)',
        boxShadow: 'var(--shadow-dropdown-lg)',
      }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 'var(--space-7)' }}>
        <label className="field">
          <FieldLabel>Application name</FieldLabel>
          <input disabled value={application.name} />
        </label>
        <label className="field">
          <FieldLabel>Application URL</FieldLabel>
          <input disabled value={application.url} />
        </label>
      </div>

      {application.login_url && (
        <label className="field">
          <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Login URL</span>
          <input disabled value={application.login_url} />
        </label>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-7)' }}>
        <label className="field">
          <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Environment</span>
          <input disabled value={application.environment} />
        </label>
        <label className="field">
          <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Authentication method</span>
          <input disabled value={AUTH_METHOD_LABEL[application.auth_method] ?? application.auth_method} />
        </label>
      </div>

      <div style={{ height: 1, background: 'var(--border-hairline)' }} />

      {notStandardLogin ? (
        <p className="caption" style={{ fontSize: 12.5, margin: 0 }}>
          Credential rotation isn't supported for this Application's authentication method yet.
        </p>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-7)' }}>
            <label className="field">
              <FieldLabel>New username</FieldLabel>
              <input required autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="field">
              <FieldLabel>New password</FieldLabel>
              <PasswordInput required autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
          </div>

          <p
            className="caption"
            style={{
              background: 'var(--canvas-wash)',
              borderRadius: 'var(--radius)',
              padding: 'var(--space-3)',
              margin: 0,
              fontSize: 12.5,
              lineHeight: 1.5,
            }}
          >
            The new credential is written directly to the secrets store, replacing the old one, and
            takes effect on the next discovery run or test run. A discovery run already in progress
            keeps using the old credential until it finishes.
          </p>

          {error && (
            <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
              {error}
            </div>
          )}
          {success && (
            <div style={{ color: 'var(--good-strong)', fontSize: 13 }} role="status">
              Credentials updated.
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--space-4)' }}>
            <button type="submit" className="button-primary" disabled={submitting} style={{ padding: '9px 20px' }}>
              {submitting ? 'Saving…' : 'Save credentials'}
            </button>
          </div>
        </>
      )}
    </form>
  )
}
