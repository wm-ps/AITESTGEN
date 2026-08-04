import { useState } from 'react'
import { ApiError, api, type ApplicationCreate, type ApplicationRead } from '../api'
import { Stepper } from './Stepper'

// The dropdown's confirmed 3-option set (DESIGN.md "Connect App form"): Username & Password,
// API Key, OAuth Client Credentials. Only 'standard_login' is backend-supported today
// (packages/domain/src/domain/application.py AuthMethod) — API Key/OAuth are shown per the
// confirmed design but disabled until the backend accepts them.
type AuthMethod = ApplicationCreate['auth_method'] | 'api_key' | 'oauth_client_credentials'

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="label-required" style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
      {children}
    </span>
  )
}

export function ConnectAppForm({
  onConnected,
  onCancel,
}: {
  onConnected: (application: ApplicationRead) => void
  onCancel: () => void
}) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [loginUrl, setLoginUrl] = useState('')
  const [environment, setEnvironment] = useState('staging')
  const [authMethod, setAuthMethod] = useState<AuthMethod>('standard_login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const application = await api.createApplication({
        name,
        url,
        login_url: loginUrl || undefined,
        environment,
        auth_method: authMethod as ApplicationCreate['auth_method'],
        ...(authMethod === 'standard_login' ? { username, password } : {}),
      })
      onConnected(application)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Connecting the Application failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Stepper current="connect-app" />
      <main style={{ maxWidth: 'clamp(720px, 68vw, 1080px)', margin: '0 auto', padding: '32px 24px' }}>
        <h1 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 12px', textAlign: 'center' }}>
          Connect to your live application
        </h1>

        <form
          onSubmit={handleSubmit}
          className="card-panel"
          style={{
            padding: '14px 22px',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-3)',
            boxShadow: 'var(--shadow-dropdown-lg)',
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 'var(--space-7)' }}>
            <label className="field">
              <FieldLabel>Application name</FieldLabel>
              <input required value={name} onChange={(e) => setName(e.target.value)} />
            </label>

            <label className="field">
              <FieldLabel>Application URL</FieldLabel>
              <input
                type="url"
                required
                placeholder="https://staging.example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </label>
          </div>

          <label className="field">
            <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
              Login URL (optional)
            </span>
            <input
              type="url"
              placeholder="https://staging.example.com/login"
              value={loginUrl}
              onChange={(e) => setLoginUrl(e.target.value)}
            />
            <span className="caption" style={{ fontSize: 11.5 }}>
              Only needed if the login form isn't reachable from the Application URL.
            </span>
          </label>

          <div style={{ height: 1, background: 'var(--border-hairline)' }} />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-7)' }}>
            <label className="field">
              <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
                Environment
              </span>
              <select value={environment} onChange={(e) => setEnvironment(e.target.value)}>
                <option value="staging">Staging</option>
                <option value="qa">QA</option>
                <option value="production">Production</option>
              </select>
            </label>

            <label className="field">
              <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
                Authentication method
              </span>
              <select
                value={authMethod}
                onChange={(e) => setAuthMethod(e.target.value as AuthMethod)}
              >
                <option value="standard_login">Username &amp; Password</option>
                <option value="api_key" disabled>
                  API Key (coming soon)
                </option>
                <option value="oauth_client_credentials" disabled>
                  OAuth Client Credentials (coming soon)
                </option>
              </select>
            </label>
          </div>

          {authMethod === 'standard_login' ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-7)' }}>
              <label className="field">
                <FieldLabel>Username</FieldLabel>
                <input required autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} />
              </label>
              <label className="field">
                <FieldLabel>Password</FieldLabel>
                <input
                  type="password"
                  required
                  autoComplete="off"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
            </div>
          ) : authMethod === 'api_key' ? (
            <label className="field">
              <FieldLabel>API Key</FieldLabel>
              <input required autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
            </label>
          ) : null}

          <p
            className="caption"
            style={{
              background: 'var(--canvas-wash)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: 'var(--space-3)',
              margin: 0,
              fontSize: 12.5,
              lineHeight: 1.5,
            }}
          >
            Use a Dedicated Test Account for this Application, not a real end-user identity.
            Credentials are written directly to the secrets store and never stored in plaintext.
          </p>

          {error && (
            <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
              {error}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
            <button type="button" className="button-secondary" onClick={onCancel} style={{ padding: '9px 18px' }}>
              Cancel
            </button>
            <button type="submit" className="button-primary" disabled={submitting} style={{ padding: '9px 20px' }}>
              {submitting ? 'Connecting…' : 'Connect Application →'}
            </button>
          </div>
        </form>
      </main>
    </>
  )
}
