import { useEffect, useRef, useState } from 'react'
import { faCheck, faServer } from '@fortawesome/free-solid-svg-icons'
import {
  ApiError,
  DOMAIN_NOT_APPROVED_CODE,
  DOMAIN_NOT_APPROVED_MESSAGE,
  api,
  type EnvironmentRead,
  type EnvironmentUpdate,
} from '../../api'
import { PasswordInput } from '../PasswordInput'
import { FieldLabel } from './AddEnvironmentDialog'
import { EnvironmentModal, FieldError, ModalActions } from './EnvironmentModal'
import { useDomainBlocked, validateEnvironment, type UrlResult, type ValidationProgress } from './environmentValidation'
import { UrlReachability } from './UrlReachability'

// Same comparison whether or not the user keeps a trailing slash.
const same = (a: string, b: string) => a.trim().replace(/\/+$/, '') === b.trim().replace(/\/+$/, '')

// Edit an environment. An extra environment can change every field; the
// default one (the application's own) only its username and password — its
// URLs and name are the application's. A blank password means "keep the
// current one", so it must be typed again whenever the URL, login URL or
// username changes: that is what lets the new details be checked with a real
// login before anything is saved. As when adding, nothing is saved unless the
// checks for what changed pass, and Cancel discards the edit.
export function EditEnvironmentDialog({
  applicationId,
  environment,
  defaultEnvironment,
  onClose,
  onSaved,
}: {
  applicationId: string
  environment: EnvironmentRead
  defaultEnvironment: EnvironmentRead
  onClose: () => void
  onSaved: () => void
}) {
  const isDefault = environment.is_default
  const needsLogin = environment.auth_method === 'standard_login'
  const loginUrlRequired = !!defaultEnvironment.login_url

  const [name, setName] = useState(environment.name)
  const [url, setUrl] = useState(environment.url)
  const [loginUrl, setLoginUrl] = useState(environment.login_url ?? '')
  const [username, setUsername] = useState(environment.username ?? '')
  const [password, setPassword] = useState('')
  // The saved password, filled in from the vault on open so every field is
  // prefilled; only a difference from it counts as a change.
  const [savedPassword, setSavedPassword] = useState('')
  const [busy, setBusy] = useState<ValidationProgress | 'Saving' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [urlResult, setUrlResult] = useState<UrlResult | null>(null)

  const nameChanged = name.trim() !== environment.name
  const urlChanged = !same(url, environment.url)
  const loginUrlChanged = !same(loginUrl, environment.login_url ?? '')
  const usernameChanged = needsLogin && username.trim() !== (environment.username ?? '')
  const passwordEntered = needsLogin && password.trim() !== savedPassword
  const dirty = nameChanged || urlChanged || loginUrlChanged || usernameChanged || passwordEntered

  const domainBlocked = useDomainBlocked(url, urlChanged)
  const closed = useRef(false)
  // Reset on mount: StrictMode's dev remount runs the cleanup once before the
  // dialog is really used, which would otherwise leave this stuck at true.
  useEffect(() => {
    closed.current = false
    return () => {
      closed.current = true
    }
  }, [])

  // A failed reveal leaves the password blank, which still means "keep the
  // current one" for an extra environment.
  useEffect(() => {
    if (!needsLogin) return
    let stale = false
    api
      .revealEnvironmentPassword(applicationId, environment.id)
      .then(({ password: revealed }) => {
        const saved = revealed ?? ''
        if (stale) return
        setSavedPassword(saved)
        setPassword((typed) => typed || saved)
      })
      .catch(() => {})
    return () => {
      stale = true
    }
  }, [applicationId, environment.id, needsLogin])

  function firstProblem(): string | null {
    if (!name.trim()) return 'Enter the environment name'
    if (!url.trim()) return 'Enter the deployed URL'
    if (loginUrlRequired && !loginUrl.trim()) return 'Enter the login URL'
    if (needsLogin && !username.trim()) return 'Enter the username'
    if (needsLogin && !password.trim() && (isDefault || urlChanged || loginUrlChanged || usernameChanged)) {
      return isDefault ? 'Enter the password' : 'Enter the password to check the new details'
    }
    return null
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (busy || !dirty || domainBlocked) return
    const problem = firstProblem()
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    setUrlResult(null)
    setBusy('Checking URL')
    let urlFailed = false
    const checkLogin = needsLogin && (urlChanged || loginUrlChanged || usernameChanged || passwordEntered)
    const failure = await validateEnvironment({
      url: url.trim(),
      loginUrl: loginUrl.trim() || undefined,
      username: username.trim(),
      password: password.trim(),
      checkUrl: urlChanged,
      checkLogin,
      onProgress: setBusy,
      onUrlResult: (result) => {
        urlFailed = !result.ok
        setUrlResult(result)
      },
      isCancelled: () => closed.current,
    })
    if (closed.current) return
    if (failure) {
      // A URL problem is already shown under the URL.
      setError(urlFailed ? null : failure)
      setBusy(null)
      return
    }
    setBusy('Saving')
    try {
      if (isDefault) {
        await api.updateApplicationCredentials(applicationId, username.trim(), password.trim())
      } else {
        const payload: EnvironmentUpdate = {}
        if (nameChanged) payload.name = name.trim()
        if (urlChanged) payload.url = url.trim()
        if (loginUrlChanged) payload.login_url = loginUrl.trim()
        if (usernameChanged) payload.username = username.trim()
        if (passwordEntered) payload.password = password.trim()
        await api.updateEnvironment(applicationId, environment.id as string, payload)
      }
      if (closed.current) return
      onSaved()
    } catch (err) {
      if (closed.current) return
      setError(
        err instanceof ApiError && err.message === DOMAIN_NOT_APPROVED_CODE
          ? DOMAIN_NOT_APPROVED_MESSAGE
          : err instanceof ApiError && err.message === 'ENVIRONMENT_RUNNING'
            ? 'A test run is in progress on this environment. Try again when it finishes.'
            : err instanceof ApiError && err.message === 'ENVIRONMENT_NAME_TAKEN'
              ? 'An environment with this name already exists.'
              : err instanceof ApiError
                ? err.message
                : 'Could not save these changes.',
      )
      setBusy(null)
    }
  }

  return (
    <EnvironmentModal
      title="Edit environment"
      subtitle="Update the details for this environment."
      icon={faServer}
      onClose={onClose}
      onSubmit={handleSubmit}
      footer={
        <ModalActions
          onCancel={onClose}
          submitLabel="Save changes"
          busyLabel={busy ?? 'Saving'}
          busy={busy !== null}
          disabled={!dirty || domainBlocked}
          icon={faCheck}
        />
      }
    >
      <fieldset disabled={busy !== null} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
        <label className="field">
          <FieldLabel required>Environment name</FieldLabel>
          <input value={name} readOnly={isDefault} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <FieldLabel required>Deployed URL</FieldLabel>
          <input
            value={url}
            readOnly={isDefault}
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
            readOnly={isDefault}
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
              <FieldLabel required={isDefault}>Password</FieldLabel>
              <PasswordInput
                placeholder={isDefault ? 'Enter the password' : 'Leave blank to keep the current password'}
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
