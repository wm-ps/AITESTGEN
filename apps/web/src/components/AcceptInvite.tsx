import { useState } from 'react'
import { ApiError, api, type UserRead } from '../api'
import { Logo } from './Logo'

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
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
          <Logo size={28} />
          <span style={{ fontWeight: 800, fontSize: 19, color: 'var(--ink)' }}>AITestGen</span>
        </div>
        <h2 style={{ fontSize: 19, fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
          Set up your account
        </h2>
        <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '0 0 22px' }}>
          You've been invited to join a workspace on AITestGen.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <label className="field">
            <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
              Full name <span style={{ color: 'var(--danger)' }}>*</span>
            </span>
            <input
              type="text"
              required
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{ padding: '11px 14px', fontSize: 14.5 }}
            />
          </label>

          <label className="field">
            <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
              Password <span style={{ color: 'var(--danger)' }}>*</span>
            </span>
            <input
              type="password"
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
            {submitting ? 'Setting up…' : 'Create account'}
          </button>
        </div>
      </form>
    </main>
  )
}
