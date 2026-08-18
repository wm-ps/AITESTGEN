import { useEffect, useState } from 'react'
import { ApiError, api } from '../api'
import { WaveQaBrand } from './Brand'
import { LoadingDots } from './LoadingDots'
import { PasswordInput } from './PasswordInput'

export function ResetPassword({
  token,
  onDone,
}: {
  token: string
  onDone: () => void
}) {
  const [target, setTarget] = useState<{ name: string; email: string } | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    api
      .getResetPasswordTarget(token)
      .then(setTarget)
      .catch(() => setLoadError(true))
  }, [token])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await api.resetPassword({ token, password })
      setDone(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reset password.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main
      style={{
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxSizing: 'border-box',
        background: 'linear-gradient(165deg, #FFFFFF 0%, #F4F6FA 45%, #ECEFF5 100%)',
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="card-panel"
        style={{ width: '100%', maxWidth: 420, padding: '28px 34px', boxSizing: 'border-box' }}
      >
        <div style={{ marginBottom: 18 }}>
          <WaveQaBrand wordmarkSize={19} wmHeight={20} />
        </div>

        {loadError ? (
          <>
            <h2 style={{ fontSize: 19, fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
              This link is no longer valid
            </h2>
            <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '0 0 22px' }}>
              It may have expired or already been used. Request a new reset link from the sign-in
              screen.
            </p>
            <button type="button" className="button-primary" onClick={onDone} style={{ padding: 12, fontSize: 14.5 }}>
              Back to sign in
            </button>
          </>
        ) : done ? (
          <>
            <h2 style={{ fontSize: 19, fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
              Password updated
            </h2>
            <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '0 0 22px' }}>
              Sign in with your new password.
            </p>
            <button type="button" className="button-primary" onClick={onDone} style={{ padding: 12, fontSize: 14.5 }}>
              Go to sign in
            </button>
          </>
        ) : !target ? null : (
          <>
            <h2 style={{ fontSize: 19, fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
              Choose a new password
            </h2>
            <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '0 0 22px' }}>
              For {target.name}'s account.
            </p>

            <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <label className="field">
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Name</span>
                  <input type="text" readOnly value={target.name} style={{ padding: '11px 14px', fontSize: 14.5, background: 'var(--canvas-wash)' }} />
                </label>

                <label className="field">
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Email</span>
                  <input type="email" readOnly value={target.email} style={{ padding: '11px 14px', fontSize: 14.5, background: 'var(--canvas-wash)' }} />
                </label>

                <label className="field">
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
                    New password <span style={{ color: 'var(--danger)' }}>*</span>
                  </span>
                  <PasswordInput
                    required
                    minLength={8}
                    autoComplete="new-password"
                    placeholder="At least 8 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    style={{ padding: '11px 14px', fontSize: 14.5 }}
                  />
                </label>

                <label className="field">
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
                    Confirm password <span style={{ color: 'var(--danger)' }}>*</span>
                  </span>
                  <PasswordInput
                    required
                    minLength={8}
                    autoComplete="new-password"
                    placeholder="Re-enter password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    style={{ padding: '11px 14px', fontSize: 14.5 }}
                  />
                </label>

                {error && (
                  <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
                    {error}
                  </div>
                )}

                <button type="submit" className="button-primary" disabled={submitting} style={{ padding: 12, fontSize: 14.5 }}>
                  {submitting ? <LoadingDots label="Updating" /> : 'Reset password'}
                </button>
              </div>
            </fieldset>
          </>
        )}
      </form>
    </main>
  )
}
