import { useState } from 'react'
import { ApiError, api, type UserRead } from '../api'
import { WaveQaBrand } from './Brand'
import { LoadingDots } from './LoadingDots'
import { PasswordInput } from './PasswordInput'

export function AcceptInvite({
  token,
  onSignedIn,
}: {
  token: string
  onSignedIn: (user: UserRead) => void
}) {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const user = await api.acceptInvite({ token, name, password })
      onSignedIn(user)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not accept this invite.')
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
        <h2 style={{ fontSize: 19, fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
          Set up your account
        </h2>
        <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '0 0 22px' }}>
          You've been invited to join a workspace on waveQA.
        </p>

        <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <label className="field">
              <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
                Full name <span style={{ color: 'var(--danger)' }}>*</span>
              </span>
              <input
                type="text"
                required
                autoComplete="name"
                placeholder="Full name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={{ padding: '11px 14px', fontSize: 14.5 }}
              />
            </label>

            <label className="field">
              <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
                Password <span style={{ color: 'var(--danger)' }}>*</span>
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

            {error && (
              <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
                {error}
              </div>
            )}

            <button type="submit" className="button-primary" disabled={submitting} style={{ padding: 12, fontSize: 14.5 }}>
              {submitting ? <LoadingDots label="Setting up" /> : 'Create account'}
            </button>
          </div>
        </fieldset>
      </form>
    </main>
  )
}
