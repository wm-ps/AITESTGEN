import { useEffect, useRef, useState } from 'react'
import { faPlus, faServer } from '@fortawesome/free-solid-svg-icons'
import {
  ApiError,
  DOMAIN_NOT_APPROVED_CODE,
  DOMAIN_NOT_APPROVED_MESSAGE,
  api,
  type EnvironmentRead,
} from '../../api'
import { PasswordInput } from '../PasswordInput'
import { EnvironmentModal, FieldError, ModalActions } from './EnvironmentModal'
import { useDomainBlocked, validateEnvironment, type UrlResult, type ValidationProgress } from './environmentValidation'
import { UrlReachability } from './UrlReachability'

export function FieldLabel({ children, required, optional }: { children: React.ReactNode; required?: boolean; optional?: boolean }) {
  return (
    <span
      className={required ? 'label-required' : undefined}
      style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)' }}
    >
      {children}
      {optional && <span style={{ fontWeight: 400, color: 'var(--fg-4)' }}> · optional</span>}
    </span>
  )
}

// Add new environment. Everything typed stays in this dialog's own state —
// Cancel (or Escape, or the close button) discards it, and nothing is saved
// or shown anywhere until **Add Environment** has passed every check: the URL's
// domain is approved, the application answers at the environment's own URL,
// and (for an app that signs in) a real login with the entered username and
// password works at the environment's own login URL.
//
// The login details mirror the default environment: when it signs in with a
// username and password, so must every environment, and a login URL is
// required exactly when the default has one.
export function AddEnvironmentDialog({
  applicationId,
  defaultEnvironment,
  onClose,
  onAdded,
}: {
  applicationId: string
  defaultEnvironment: EnvironmentRead
  onClose: () => void
  onAdded: (environment: EnvironmentRead) => void
}) {
  const needsLogin = defaultEnvironment.auth_method === 'standard_login'
  const loginUrlRequired = !!defaultEnvironment.login_url

  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [loginUrl, setLoginUrl] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState<ValidationProgress | 'Adding' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [urlResult, setUrlResult] = useState<UrlResult | null>(null)
  const domainBlocked = useDomainBlocked(url, true)
  // Set when the dialog closes: a check still running is abandoned and, above
  // all, nothing is saved after it.
  const closed = useRef(false)
  // Reset on mount: StrictMode's dev remount runs the cleanup once before the
  // dialog is really used, which would otherwise leave this stuck at true.
  useEffect(() => {
    closed.current = false
    return () => {
      closed.current = true
    }
  }, [])

  function firstMissing(): string | null {
    if (!name.trim()) return 'Enter the environment name'
    if (!url.trim()) return 'Enter the deployed URL'
    if (loginUrlRequired && !loginUrl.trim()) return 'Enter the login URL'
    if (needsLogin && !username.trim()) return 'Enter the username'
    if (needsLogin && !password.trim()) return 'Enter the password'
    return null
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (busy || domainBlocked) return
    const missing = firstMissing()
    if (missing) {
      setError(missing)
      return
    }
    setError(null)
    setUrlResult(null)
    setBusy('Checking URL')
    let urlFailed = false
    const entered = {
      name: name.trim(),
      url: url.trim(),
      login_url: loginUrl.trim() || undefined,
      username: needsLogin ? username.trim() : undefined,
      password: needsLogin ? password.trim() : undefined,
    }
    const problem = await validateEnvironment({
      url: entered.url,
      loginUrl: entered.login_url,
      username: entered.username ?? '',
      password: entered.password ?? '',
      checkUrl: true,
      checkLogin: needsLogin,
      onProgress: setBusy,
      onUrlResult: (result) => {
        urlFailed = !result.ok
        setUrlResult(result)
      },
      isCancelled: () => closed.current,
    })
    if (closed.current) return
    if (problem) {
      // A URL problem is already shown under the URL.
      setError(urlFailed ? null : problem)
      setBusy(null)
      return
    }
    setBusy('Adding')
    try {
      const created = await api.createEnvironment(applicationId, entered)
      if (closed.current) return
      onAdded(created)
    } catch (err) {
      if (closed.current) return
      setError(
        err instanceof ApiError && err.message === DOMAIN_NOT_APPROVED_CODE
          ? DOMAIN_NOT_APPROVED_MESSAGE
          : err instanceof ApiError && err.message === 'ENVIRONMENT_NAME_TAKEN'
            ? 'An environment with this name already exists.'
            : err instanceof ApiError
              ? err.message
              : 'Could not add this environment.',
      )
      setBusy(null)
    }
  }

  return (
    <EnvironmentModal
      title="Add new environment"
      subtitle="Run the same test cases for this application against another deployment."
      icon={faServer}
      onClose={onClose}
      onSubmit={handleSubmit}
      footer={
        <ModalActions
          onCancel={onClose}
          submitLabel="Add Environment"
          busyLabel={busy ?? 'Adding'}
          busy={busy !== null}
          disabled={domainBlocked}
          icon={faPlus}
        />
      }
    >
      <fieldset disabled={busy !== null} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
        <label className="field">
          <FieldLabel required>Environment name</FieldLabel>
          <input autoFocus placeholder="Enter the environment name" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <FieldLabel required>Deployed URL</FieldLabel>
          <input
            placeholder="Enter the deployed URL"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value)
              setUrlResult(null)
            }}
            style={{ fontFamily: 'var(--font-mono)' }}
          />
          {domainBlocked && (
            <span role="alert" style={{ color: 'var(--danger)', fontSize: 12 }}>
              {DOMAIN_NOT_APPROVED_MESSAGE}
            </span>
          )}
        </label>
        {!domainBlocked && <UrlReachability result={urlResult} />}
        <label className="field">
          <FieldLabel required={loginUrlRequired} optional={!loginUrlRequired}>
            Login URL
          </FieldLabel>
          <input
            placeholder="Enter the login URL"
            value={loginUrl}
            onChange={(e) => setLoginUrl(e.target.value)}
            style={{ fontFamily: 'var(--font-mono)' }}
          />
        </label>
        {needsLogin && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <label className="field">
              <FieldLabel required>Username</FieldLabel>
              <input
                placeholder="Enter the username"
                autoComplete="off"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <label className="field">
              <FieldLabel required>Password</FieldLabel>
              <PasswordInput
                placeholder="Enter the password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ border: '1px solid var(--border-2)', borderRadius: 'var(--radius)', padding: '9px var(--space-5)', background: 'var(--panel)', color: 'var(--fg)', fontFamily: 'inherit', fontSize: 'inherit' }}
              />
            </label>
          </div>
        )}
      </fieldset>
      {error && <FieldError>{error}</FieldError>}
    </EnvironmentModal>
  )
}
