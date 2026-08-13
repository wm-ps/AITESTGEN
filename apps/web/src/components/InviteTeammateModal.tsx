import { useState } from 'react'
import { ApiError, api } from '../api'
import { LoadingDots } from './LoadingDots'

export function InviteTeammateModal({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'admin' | 'member'>('member')
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.sendInvite({ email, role })
      setSent(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send invite.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,23,42,0.35)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
      }}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="card-panel"
        style={{ width: '100%', maxWidth: 380, padding: '24px 28px', boxSizing: 'border-box' }}
      >
        <h2 style={{ fontSize: 17, fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
          Invite a teammate
        </h2>

        {sent ? (
          <>
            <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '10px 0 20px' }}>
              Invite sent to {email}.
            </p>
            <button type="button" className="button-primary" onClick={onClose} style={{ padding: 11, fontSize: 14 }}>
              Done
            </button>
          </>
        ) : (
          <>
            <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '0 0 18px' }}>
              They'll get an email with a link to set up their account.
            </p>
            <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <label className="field">
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Email</span>
                  <input
                    type="email"
                    required
                    autoFocus
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    style={{ padding: '10px 12px', fontSize: 14 }}
                  />
                </label>
                <label className="field">
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>Role</span>
                  <select
                    value={role}
                    onChange={(e) => setRole(e.target.value as 'admin' | 'member')}
                    style={{ padding: '10px 12px', fontSize: 14 }}
                  >
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
                {error && (
                  <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
                    {error}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
                  <button type="button" className="button-secondary" onClick={onClose} style={{ flex: 1, padding: 11, fontSize: 14 }}>
                    Cancel
                  </button>
                  <button type="submit" className="button-primary" disabled={submitting} style={{ flex: 1, padding: 11, fontSize: 14 }}>
                    {submitting ? <LoadingDots label="Sending" /> : 'Send invite'}
                  </button>
                </div>
              </div>
            </fieldset>
          </>
        )}
      </form>
    </div>
  )
}
