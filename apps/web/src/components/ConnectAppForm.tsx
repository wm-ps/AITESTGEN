import { useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faBolt, faPlay, faPlugCircleCheck } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type ApplicationCreate, type ApplicationRead } from '../api'
import { LoadingDots } from './LoadingDots'

const KNOWN_ENVIRONMENTS = ['staging', 'production', 'qa']

// A real <label> wrapping its control (not a sibling span) — keeps
// getByLabelText/screen-reader association working, same as the field
// pattern this replaces.
function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)' }}>{label}</span>
      {children}
      {hint && <span style={{ fontSize: 11.5, color: 'var(--fg-4)' }}>{hint}</span>}
    </label>
  )
}

const fieldInputStyle: React.CSSProperties = {
  height: 38,
  padding: '0 12px',
  border: '1px solid var(--border-2)',
  borderRadius: 8,
  fontSize: 13.5,
  color: 'var(--fg-1)',
  background: 'var(--panel)',
  outline: 'none',
  width: '100%',
  boxSizing: 'border-box',
  fontFamily: 'inherit',
}

export function ConnectAppForm({
  application,
  onConnected,
  onCancel,
}: {
  application?: ApplicationRead | null
  onConnected: (application: ApplicationRead) => void
  onCancel: () => void
}) {
  // Once an application is connected, this screen is a read-only receipt of
  // what was submitted — not editable, and never swaps to a different layout.
  const readOnly = !!application

  const [name, setName] = useState(application?.name ?? '')
  const [url, setUrl] = useState(application?.url ?? '')
  const [loginUrl, setLoginUrl] = useState(application?.login_url ?? '')
  const [environment, setEnvironment] = useState(
    application && !KNOWN_ENVIRONMENTS.includes(application.environment) ? 'other' : application?.environment ?? 'staging',
  )
  const [customEnvironment, setCustomEnvironment] = useState(
    application && !KNOWN_ENVIRONMENTS.includes(application.environment) ? application.environment : '',
  )
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [testingConnection, setTestingConnection] = useState(false)
  const [connectionResult, setConnectionResult] = useState<{ ok: boolean; detail: string | null } | null>(null)

  async function handleTestConnection() {
    if (testingConnection || !url) return
    setTestingConnection(true)
    setConnectionResult(null)
    try {
      const result = await api.testConnection(url)
      setConnectionResult({ ok: result.reachable, detail: result.detail })
    } catch (err) {
      setConnectionResult({ ok: false, detail: err instanceof ApiError ? err.message : 'Could not reach the server to test this URL.' })
    } finally {
      setTestingConnection(false)
    }
  }

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
        auth_method: 'standard_login' as ApplicationCreate['auth_method'],
        username,
        password,
      })
      onConnected(application)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to connect the application.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>
            {readOnly ? 'Connected application' : 'Add application'}
          </h1>
          <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 4 }}>
            {readOnly
              ? 'What was submitted when this application connected.'
              : 'Enter the deployed URL and sign-in credentials. Discovery starts immediately — journeys, scenarios and Playwright code follow automatically.'}
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          style={{
            background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
            backdropFilter: 'blur(16px) saturate(1.25)',
            border: '1px solid var(--border-1)',
            borderRadius: 14,
            padding: 18,
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
            boxShadow: 'var(--panel-shadow)',
          }}
        >
          <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <Field label="Application name">
                <input
                  required
                  readOnly={readOnly}
                  placeholder="Enter the application name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={fieldInputStyle}
                />
              </Field>
              <Field label="Environment">
                <select
                  value={environment}
                  disabled={readOnly}
                  onChange={(e) => setEnvironment(e.target.value)}
                  style={{ ...fieldInputStyle, opacity: 1, WebkitTextFillColor: 'var(--fg-1)', cursor: readOnly ? 'default' : 'pointer' }}
                >
                  <option value="staging">Staging</option>
                  <option value="production">Production</option>
                  <option value="qa">QA</option>
                  <option value="other">Other</option>
                </select>
                {environment === 'other' && (
                  <input
                    type="text"
                    aria-label="Custom environment"
                    readOnly={readOnly}
                    placeholder="Enter the environment name"
                    value={customEnvironment}
                    onChange={(e) => setCustomEnvironment(e.target.value)}
                    required
                    style={{ ...fieldInputStyle, marginTop: 4 }}
                  />
                )}
              </Field>
            </div>

            <Field label="Deployed URL">
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <input
                  type="url"
                  required
                  readOnly={readOnly}
                  placeholder="https://"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value)
                    setConnectionResult(null)
                  }}
                  style={{ ...fieldInputStyle, fontFamily: 'var(--font-mono)', fontSize: 13 }}
                />
                <button
                  type="button"
                  disabled={!url || testingConnection || readOnly}
                  onClick={handleTestConnection}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 8,
                    height: 30,
                    padding: '0 12px',
                    borderRadius: 8,
                    border: '1px solid rgba(30,150,138,0.35)',
                    background: 'rgba(30,150,138,0.1)',
                    color: 'var(--accent-2)',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: !url || testingConnection || readOnly ? 'not-allowed' : 'pointer',
                    opacity: !url || readOnly ? 0.5 : 1,
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  {testingConnection ? (
                    <LoadingDots label="Testing" />
                  ) : (
                    <>
                      <FontAwesomeIcon icon={faPlugCircleCheck} style={{ fontSize: 11 }} />
                      Test connection
                    </>
                  )}
                </button>
              </div>
              {connectionResult && (
                <div style={{ fontSize: 12, color: connectionResult.ok ? 'var(--ok)' : 'var(--bad)' }}>
                  {connectionResult.ok ? 'URL is reachable.' : connectionResult.detail ?? 'URL is not reachable.'}
                </div>
              )}
            </Field>

            <div style={{ height: 1, background: 'var(--line)' }} />

            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <div
                title="Sign-in is required for every application"
                style={{ width: 36, height: 20, flex: 'none', borderRadius: 1000, padding: 2, display: 'flex', background: 'var(--ok)' }}
              >
                <div style={{ width: 16, height: 16, borderRadius: 1000, background: 'var(--on-ok)', transform: 'translateX(16px)' }} />
              </div>
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-1)' }}>This application requires sign-in</div>
                <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>
                  Credentials are stored encrypted and injected at discovery and run time only.
                </div>
              </div>
            </div>

            <div style={{ border: '1px solid var(--border-2)', borderRadius: 10, padding: 14, background: 'var(--panel-2)', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <Field label="Login URL (optional)">
                <input
                  type="url"
                  readOnly={readOnly}
                  placeholder="Enter the login page URL"
                  value={loginUrl}
                  onChange={(e) => setLoginUrl(e.target.value)}
                  style={{ ...fieldInputStyle, background: 'var(--panel)', fontFamily: 'var(--font-mono)', fontSize: 13 }}
                />
              </Field>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <Field label="Username">
                  <input
                    required={!readOnly}
                    readOnly={readOnly}
                    autoComplete="off"
                    placeholder={readOnly ? 'Stored securely — not shown' : 'Service account email'}
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    style={{ ...fieldInputStyle, background: 'var(--panel)' }}
                  />
                </Field>
                <Field label="Password">
                  <input
                    type="password"
                    readOnly={readOnly}
                    required={!readOnly}
                    autoComplete="off"
                    placeholder={readOnly ? 'Stored securely — not shown' : 'Password or token'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    style={{ ...fieldInputStyle, background: 'var(--panel)' }}
                  />
                </Field>
              </div>
            </div>

            {!readOnly && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '13px 16px', border: '1px solid var(--border-2)', borderRadius: 10, background: 'var(--panel-2)' }}>
                <FontAwesomeIcon icon={faBolt} style={{ fontSize: 13, color: 'var(--fg-3)', flexShrink: 0 }} />
                <div style={{ flex: 1, fontSize: 12.5, color: 'var(--fg-3)' }}>
                  Discovery uses the workspace defaults for runtime, page count and journey limits. Change them in Configuration → Settings.
                </div>
              </div>
            )}

            {error && (
              <div style={{ color: 'var(--bad)', fontSize: 13 }} role="alert">
                {error}
              </div>
            )}

            {!readOnly && (
              <>
                <div style={{ height: 1, background: 'var(--line)' }} />
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={onCancel}
                    style={{ height: 38, padding: '0 18px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', fontSize: 13.5, fontWeight: 500, color: 'var(--fg-2)', cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submitting}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 8,
                      height: 38,
                      padding: '0 20px',
                      borderRadius: 8,
                      background: 'var(--accent)',
                      color: '#fff',
                      fontSize: 13.5,
                      fontWeight: 600,
                      cursor: submitting ? 'default' : 'pointer',
                      boxShadow: 'var(--accent-glow)',
                      border: 'none',
                      opacity: submitting ? 0.75 : 1,
                    }}
                  >
                    {submitting ? (
                      <LoadingDots label="Connecting" />
                    ) : (
                      <>
                        <FontAwesomeIcon icon={faPlay} style={{ fontSize: 11 }} />
                        Start discovery
                      </>
                    )}
                  </button>
                </div>
              </>
            )}
          </fieldset>
        </form>
      </div>
    </>
  )
}
