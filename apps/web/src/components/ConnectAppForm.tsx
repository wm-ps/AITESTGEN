import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faPlay, faPlugCircleCheck, faPlus } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, hasDiscovery, type ApplicationRead } from '../api'
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

// The login check runs in a real browser on the discovery worker and is
// polled, like Regenerate/Auto-fill. The cap sits just above the worker's
// own worst-case budget (credential_check.py) so a hung check ends as
// "couldn't confirm" instead of spinning forever.
const CREDENTIAL_POLL_MS = 1000
const CREDENTIAL_POLL_MAX_ATTEMPTS = 150
const INVALID_CREDENTIALS_MESSAGE =
  'The username or password is incorrect. Enter valid credentials and click Start discovery again.'
const UNCERTAIN_CREDENTIALS_MESSAGE =
  "We couldn't confirm these credentials. Click Start discovery to validate again."
const DISCOVERY_NOT_STARTED_MESSAGE =
  "Discovery couldn't start, so the application was not added. Click Start discovery to try again."

// Anything that isn't a proved `valid` / `invalid` (request error, worker
// unavailable, timeout) collapses to `uncertain` — discovery never starts on
// an unproven login, and the user is just asked to try again.
async function checkCredentials(payload: {
  url: string
  login_url?: string
  username: string
  password: string
}): Promise<'valid' | 'invalid' | 'uncertain'> {
  try {
    const { check_id } = await api.startCredentialCheck(payload)
    for (let attempt = 0; attempt < CREDENTIAL_POLL_MAX_ATTEMPTS; attempt++) {
      const result = await api.getCredentialCheck(check_id)
      if (result.status !== 'running') return result.status
      await new Promise((resolve) => setTimeout(resolve, CREDENTIAL_POLL_MS))
    }
  } catch {
    // fall through to uncertain
  }
  return 'uncertain'
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
  // Off = the application has no sign-in: the credentials section is hidden
  // and the application is created with auth_method 'none'.
  const [requiresSignIn, setRequiresSignIn] = useState(application ? application.auth_method !== 'none' : true)
  // Checked (today's behavior) starts a crawl on submit; unchecked only saves
  // the application — the submit button's label follows it so the user can
  // tell which one they're about to do.
  const [discoveryRequired, setDiscoveryRequired] = useState(application ? hasDiscovery(application) : true)
  const submitLabel = discoveryRequired ? 'Start discovery' : 'Add application'
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // Shown under the Username/Password fields — cleared on any edit to the
  // fields the check was run against.
  const [busyLabel, setBusyLabel] = useState('Connecting')
  const [credentialMessage, setCredentialMessage] = useState<string | null>(null)
  const [testingConnection, setTestingConnection] = useState(false)
  const [connectionResult, setConnectionResult] = useState<{ ok: boolean; detail: string | null } | null>(null)
  // `[FIXED]` Was previously shown as a dimmed/disabled-looking button plus
  // a bottom-right Toast on a blocked click — product decision changed this
  // to always look like a normal, enabled button, with a small popover
  // anchored right above it on a blocked click instead. The underlying gate
  // itself (`canStartDiscovery`, checked in `handleSubmit`) is unchanged —
  // editing the URL still resets `connectionResult` to null below, so this
  // can't go stale by pointing at a URL that was never (re-)verified.
  const [showConnectionPopover, setShowConnectionPopover] = useState(false)
  const canStartDiscovery = connectionResult?.ok === true

  useEffect(() => {
    if (!showConnectionPopover) return
    const timeout = setTimeout(() => setShowConnectionPopover(false), 3500)
    return () => clearTimeout(timeout)
  }, [showConnectionPopover])

  // Shared by the Test connection button (discovery off) and Start discovery's
  // first step (discovery on): same call, same result line under the URL.
  async function runConnectionTest(): Promise<boolean> {
    setConnectionResult(null)
    try {
      const result = await api.testConnection(url)
      setConnectionResult({ ok: result.reachable, detail: result.detail })
      return result.reachable
    } catch (err) {
      setConnectionResult({ ok: false, detail: err instanceof ApiError ? err.message : 'Could not reach the server to test this URL.' })
      return false
    }
  }

  async function handleTestConnection() {
    if (testingConnection || !url) return
    setTestingConnection(true)
    try {
      await runConnectionTest()
    } finally {
      setTestingConnection(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // With discovery on, Start discovery runs the URL check itself (below), so
    // the manual Test connection gate only applies when discovery is off.
    if (!discoveryRequired && !canStartDiscovery) {
      setShowConnectionPopover(true)
      return
    }
    setError(null)
    setCredentialMessage(null)
    setSubmitting(true)
    try {
      if (discoveryRequired) {
        setBusyLabel('Checking URL')
        if (!(await runConnectionTest())) return
      }
      // Only when discovery will actually run with a login — "Add
      // application" (no discovery) or a no-sign-in app skips the check.
      if (discoveryRequired && requiresSignIn) {
        setBusyLabel('Validating credentials')
        const verdict = await checkCredentials({
          url,
          login_url: loginUrl || undefined,
          username,
          password,
        })
        if (verdict !== 'valid') {
          setCredentialMessage(verdict === 'invalid' ? INVALID_CREDENTIALS_MESSAGE : UNCERTAIN_CREDENTIALS_MESSAGE)
          return
        }
      }
      setBusyLabel('Connecting')
      const application = await api.createApplication({
        name,
        url,
        environment: environment === 'other' ? customEnvironment : environment,
        discovery_required: discoveryRequired,
        ...(requiresSignIn
          ? { auth_method: 'standard_login' as const, login_url: loginUrl || undefined, username, password }
          : { auth_method: 'none' as const }),
      })
      onConnected(application)
    } catch (err) {
      setError(
        err instanceof ApiError && err.message === 'DISCOVERY_UNAVAILABLE'
          ? DISCOVERY_NOT_STARTED_MESSAGE
          : err instanceof ApiError
            ? err.message
            : 'Failed to connect the application.',
      )
    } finally {
      setBusyLabel('Connecting')
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
              : discoveryRequired
                ? 'Enter the deployed URL and sign-in credentials. Discovery starts immediately — journeys, scenarios and Playwright code follow automatically.'
                : 'Enter the deployed URL and sign-in credentials. No discovery runs — add test cases yourself by writing them or recording them.'}
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

            {/* `[FIXED label-association]` Not `Field` (a wrapping `<label>`) —
                the Test connection button and its result text used to live
                inside that same wrapping label, so a screen reader (and
                `getByLabelText`) read them as *part of* the "Deployed URL"
                label's own accessible name once a result appeared (e.g.
                "Deployed URLURL is reachable." — button text is excluded by
                the label-content algorithm, but plain text like this isn't).
                Explicit `htmlFor`/`id` labels only the input, regardless of
                what else renders alongside it. */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label htmlFor="connect-app-url" style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)' }}>
                Deployed URL
              </label>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <input
                  id="connect-app-url"
                  type="url"
                  required
                  readOnly={readOnly}
                  placeholder="https://"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value)
                    setConnectionResult(null)
                    setCredentialMessage(null)
                  }}
                  style={{ ...fieldInputStyle, fontFamily: 'var(--font-mono)', fontSize: 13 }}
                />
                {/* With discovery on, Start discovery checks the URL itself. */}
                {(!discoveryRequired || readOnly) && (
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
                )}
              </div>
              {connectionResult && (
                <div style={{ fontSize: 12, color: connectionResult.ok ? 'var(--ok)' : 'var(--bad)' }}>
                  {connectionResult.ok ? 'URL is reachable.' : connectionResult.detail ?? 'URL is not reachable.'}
                </div>
              )}
            </div>

            <div style={{ height: 1, background: 'var(--line)' }} />

            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <button
                type="button"
                role="switch"
                aria-checked={requiresSignIn}
                aria-labelledby="connect-app-signin-label"
                disabled={readOnly}
                onClick={() => setRequiresSignIn((v) => !v)}
                style={{
                  width: 36,
                  height: 20,
                  flex: 'none',
                  border: 'none',
                  borderRadius: 1000,
                  padding: 2,
                  display: 'flex',
                  background: requiresSignIn ? 'var(--ok)' : 'var(--border-2)',
                  cursor: readOnly ? 'default' : 'pointer',
                  transition: 'background 0.15s ease',
                }}
              >
                <span
                  style={{
                    width: 16,
                    height: 16,
                    borderRadius: 1000,
                    background: 'var(--on-ok)',
                    transform: requiresSignIn ? 'translateX(16px)' : 'none',
                    transition: 'transform 0.15s ease',
                  }}
                />
              </button>
              <div>
                <div id="connect-app-signin-label" style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-1)' }}>
                  This application requires sign-in
                </div>
                <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>
                  {!requiresSignIn
                    ? 'Turn on if the application asks for a username and password.'
                    : discoveryRequired
                      ? 'Credentials are stored encrypted and injected at discovery and run time only.'
                      : 'Credentials are stored encrypted and injected at run time only.'}
                </div>
              </div>
            </div>

            {requiresSignIn && (
              <div style={{ border: '1px solid var(--border-2)', borderRadius: 10, padding: 14, background: 'var(--panel)', display: 'flex', flexDirection: 'column', gap: 12 }}>
                <Field label="Login URL (optional)">
                  <input
                    type="url"
                    readOnly={readOnly}
                    placeholder="Enter the login page URL"
                    value={loginUrl}
                    onChange={(e) => {
                      setLoginUrl(e.target.value)
                      setCredentialMessage(null)
                    }}
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
                      onChange={(e) => {
                        setUsername(e.target.value)
                        setCredentialMessage(null)
                      }}
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
                      onChange={(e) => {
                        setPassword(e.target.value)
                        setCredentialMessage(null)
                      }}
                      style={{ ...fieldInputStyle, background: 'var(--panel)' }}
                    />
                  </Field>
                </div>
                {credentialMessage && (
                  <div style={{ color: 'var(--bad)', fontSize: 12.5 }} role="alert">
                    {credentialMessage}
                  </div>
                )}
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '13px 16px', border: '1px solid var(--border-2)', borderRadius: 10, background: 'var(--panel)' }}>
              <input
                id="connect-app-discovery"
                type="checkbox"
                checked={discoveryRequired}
                disabled={readOnly}
                onChange={(e) => {
                  setDiscoveryRequired(e.target.checked)
                  // A URL result from the other mode (Test connection vs.
                  // Start discovery's own check) must not carry over.
                  setConnectionResult(null)
                }}
                style={{ marginTop: 2, accentColor: 'var(--accent)', flexShrink: 0 }}
              />
              <div>
                <label htmlFor="connect-app-discovery" style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-1)' }}>
                  Autonomous discovery
                </label>
                <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>
                  Crawl the application to map journeys and scenarios automatically. Uncheck to only add the application
                  and create test cases yourself.
                </div>
              </div>
            </div>

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
                  {/* `[FIXED]` Start discovery always looks and behaves like a
                      normal, enabled button now — it's `canStartDiscovery`
                      that still gates whether `handleSubmit` actually
                      proceeds, unchanged. A blocked click shows the popover
                      below instead of dimming the button beforehand. */}
                  <div style={{ position: 'relative' }}>
                    {showConnectionPopover && (
                      <div
                        role="status"
                        style={{
                          position: 'absolute',
                          bottom: '100%',
                          right: 0,
                          marginBottom: 8,
                          padding: '9px 13px',
                          borderRadius: 8,
                          background: 'var(--fg)',
                          color: '#fff',
                          fontSize: 12.5,
                          fontWeight: 500,
                          whiteSpace: 'nowrap',
                          boxShadow: 'var(--shadow-dropdown)',
                          animation: 'aitg-fade-up 0.2s ease-out both',
                          zIndex: 10,
                        }}
                      >
                        Test the connection above to enable {submitLabel}.
                      </div>
                    )}
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
                        <LoadingDots label={busyLabel} />
                      ) : (
                        <>
                          <FontAwesomeIcon icon={discoveryRequired ? faPlay : faPlus} style={{ fontSize: 11 }} />
                          {submitLabel}
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </>
            )}
          </fieldset>
        </form>
      </div>
    </>
  )
}
