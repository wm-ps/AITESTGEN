import { useState } from 'react'
import { ApiError, api, type ApplicationRead } from '../api'
import { Stepper } from './Stepper'

export function ConnectAppForm({ onConnected }: { onConnected: (application: ApplicationRead) => void }) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [environment, setEnvironment] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const application = await api.createApplication({ name, url, environment, username, password })
      onConnected(application)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Connecting the Application failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Stepper current="connect-app" />
      <main style={{ maxWidth: 720, margin: '0 auto', padding: '48px var(--content-x)' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: '0 0 6px' }}>Connect to your live application</h1>
        <p className="caption" style={{ maxWidth: 560, fontSize: 14, margin: '0 0 14px' }}>
          AITestGen connects to your deployed application over the network — not your source code —
          then turns its critical workflows into a structured library of test scenarios, ready to
          review in minutes.
        </p>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            fontSize: 12.5,
            color: 'var(--ink-faint)',
            margin: '0 0 32px',
          }}
        >
          <span>Read-only connection</span>
          <span>→</span>
          <span>Workflows mapped</span>
          <span>→</span>
          <span>Scenarios ready to review</span>
        </div>

        <form
          onSubmit={handleSubmit}
          className="card-panel"
          style={{
            padding: 'var(--space-8)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-5)',
          }}
        >
          <label className="field">
            <span className="label">Application name</span>
            <input required value={name} onChange={(e) => setName(e.target.value)} />
          </label>

          <label className="field">
            <span className="label">Base URL</span>
            <input
              type="url"
              required
              placeholder="https://staging.example.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>

          <label className="field">
            <span className="label">Environment</span>
            <input
              required
              placeholder="staging, UAT, ..."
              value={environment}
              onChange={(e) => setEnvironment(e.target.value)}
            />
          </label>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-5)' }}>
            <label className="field">
              <span className="label">Username</span>
              <input required autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="field">
              <span className="label">Password</span>
              <input
                type="password"
                required
                autoComplete="off"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
          </div>

          <p
            className="caption"
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: 'var(--space-3)',
              margin: 0,
              lineHeight: 1.5,
            }}
          >
            Use a Dedicated Test Account for this Application, not a real end-user identity.
            Credentials are written directly to the secrets store and never stored in plaintext.
          </p>

          {error && (
            <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
              {error}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button type="submit" className="button-primary" disabled={submitting} style={{ padding: '11px 22px' }}>
              {submitting ? 'Connecting…' : 'Connect Application →'}
            </button>
          </div>
        </form>
      </main>
    </>
  )
}
