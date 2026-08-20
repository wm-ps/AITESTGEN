import { useState } from 'react'
import { ApiError, api } from '../api'
import { VantageBrand } from './Brand'
import { LoadingDots } from './LoadingDots'

export function ForgotPassword({ onBackToSignIn }: { onBackToSignIn: () => void }) {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.forgotPassword({ email })
      setSent(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send reset link.')
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
          <VantageBrand wordmarkSize={19} markSize={18} />
        </div>

        {sent ? (
          <>
            <h2 style={{ fontSize: 19, fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
              Check your email
            </h2>
            <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '0 0 22px' }}>
              If an account exists for {email}, a reset link is on its way. The link expires in 1
              hour.
            </p>
            <button type="button" className="button-primary" onClick={onBackToSignIn} style={{ padding: 12, fontSize: 14.5 }}>
              Back to sign in
            </button>
          </>
        ) : (
          <>
            <h2 style={{ fontSize: 19, fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
              Reset your password
            </h2>
            <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '0 0 22px' }}>
              Enter your work email and we'll send you a link to reset it.
            </p>

            <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <label className="field">
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
                    Work email <span style={{ color: 'var(--danger)' }}>*</span>
                  </span>
                  <input
                    type="email"
                    required
                    autoFocus
                    autoComplete="username"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    style={{ padding: '11px 14px', fontSize: 14.5 }}
                  />
                </label>

                {error && (
                  <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
                    {error}
                  </div>
                )}

                <button type="submit" className="button-primary" disabled={submitting} style={{ padding: 12, fontSize: 14.5 }}>
                  {submitting ? <LoadingDots label="Sending" /> : 'Send reset link'}
                </button>
                <button type="button" className="button-secondary" onClick={onBackToSignIn} style={{ padding: 11, fontSize: 14 }}>
                  Back to sign in
                </button>
              </div>
            </fieldset>
          </>
        )}
      </form>
    </main>
  )
}
