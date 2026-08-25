import { useState } from 'react'
import { ApiError, api, type ApplicationCreate, type ApplicationRead } from '../api'
import { Stepper, type StepKey } from './Stepper'
import { PasswordInput } from './PasswordInput'
import { LoadingDots } from './LoadingDots'

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

function ConnectedAppSummary({ application }: { application: ApplicationRead }) {
  const rows: [string, string][] = [
    ['Application name', application.name],
    ['Application URL', application.url],
    ...(application.login_url ? ([['Login URL', application.login_url]] as [string, string][]) : []),
    ['Environment', application.environment],
    ['Authentication method', application.auth_method === 'standard_login' ? 'Username & Password' : application.auth_method],
  ]
  return (
    <main style={{ maxWidth: 'clamp(720px, 92vw, var(--content-max-wide))', margin: '0 auto', padding: '32px 24px' }}>
      <h1 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 12px', textAlign: 'center' }}>
        Connected application
      </h1>
      <div
        className="card-panel"
        style={{ padding: '14px 22px', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', boxShadow: 'var(--shadow-dropdown-lg)' }}
      >
        {rows.map(([label, value]) => (
          <div key={label} className="field">
            <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>{label}</span>
            <span style={{ fontSize: 14 }}>{value}</span>
          </div>
        ))}
        <p className="caption" style={{ margin: 0, fontSize: 12 }}>
          Credentials are stored in the secrets vault and aren't shown here.
        </p>
      </div>
    </main>
  )
}

export function ConnectAppForm({
  application,
  onConnected,
  onCancel,
  furthestCount,
  onStepClick,
  onPrevious,
  onNext,
}: {
  application?: ApplicationRead | null
  onConnected: (application: ApplicationRead) => void
  onCancel: () => void
  furthestCount: number
  onStepClick?: (key: StepKey) => void
  onPrevious?: () => void
  onNext?: () => void
}) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [loginUrl, setLoginUrl] = useState('')
  const [environment, setEnvironment] = useState('staging')
  const [customEnvironment, setCustomEnvironment] = useState('')
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
        environment: environment === 'other' ? customEnvironment : environment,
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

  if (application) {
    return (
      <>
        <Stepper
          current="connect-app"
          furthestCount={furthestCount}
          onStepClick={onStepClick}
          onPrevious={onPrevious}
          onNext={onNext}
        />
        <ConnectedAppSummary application={application} />
      </>
    )
  }

  return (
    <>
      <Stepper current="connect-app" furthestCount={furthestCount} onStepClick={onStepClick} onPrevious={onPrevious} onNext={onNext} />
      <main style={{ maxWidth: 'clamp(720px, 92vw, var(--content-max-wide))', margin: '0 auto', padding: '32px 24px' }}>
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
          <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 'var(--space-7)' }}>
            <label className="field">
              <FieldLabel>Application name</FieldLabel>
              <input required placeholder="e.g. Staging Checkout" value={name} onChange={(e) => setName(e.target.value)} />
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
                <option value="other">Other</option>
              </select>
              {environment === 'other' && (
                <input
                  type="text"
                  placeholder="e.g. sandbox, uat"
                  value={customEnvironment}
                  onChange={(e) => setCustomEnvironment(e.target.value)}
                  required
                  style={{ marginTop: 6 }}
                />
              )}
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
                <input
                  required
                  autoComplete="off"
                  placeholder="Login username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </label>
              <label className="field">
                <FieldLabel>Password</FieldLabel>
                <PasswordInput
                  required
                  autoComplete="off"
                  placeholder="Login password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
            </div>
          ) : authMethod === 'api_key' ? (
            <label className="field">
              <FieldLabel>API Key</FieldLabel>
              <input
                required
                autoComplete="off"
                placeholder="Paste API key"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </label>
          ) : null}

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
            Use a Dedicated Test Account for this Application, not a real end-user identity, on a lower environment.
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
              {submitting ? <LoadingDots label="Connecting" /> : 'Connect Application →'}
            </button>
          </div>
          </fieldset>
        </form>
      </main>
    </>
  )
}
