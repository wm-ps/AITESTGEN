import { useState } from 'react'
import { ApiError, api, type ApplicationRead } from '../api'

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
    <main
      style={{
        maxWidth: 560,
        margin: '0 auto',
        padding: `var(--content-top) var(--content-x)`,
      }}
    >
      <h1 style={{ fontSize: 19, fontWeight: 650, margin: '0 0 20px' }}>Connect Application</h1>

      <form
        onSubmit={handleSubmit}
        className="card-panel"
        style={{
          padding: 'var(--space-6)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-4)',
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

        <fieldset
          style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 'var(--space-4)' }}
        >
          <legend className="label">Credentials</legend>
          <p className="caption" style={{ margin: '0 0 12px' }}>
            Use a Dedicated Test Account for this Application, not a real end-user identity.
            Credentials are written directly to the secrets store and never stored in plaintext.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <label className="field">
              <span className="label">Username</span>
              <input
                required
                autoComplete="off"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
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
        </fieldset>

        {error && (
          <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
            {error}
          </div>
        )}

        <button type="submit" className="button-primary" disabled={submitting}>
          {submitting ? 'Connecting…' : 'Connect Application'}
        </button>
      </form>
    </main>
  )
}
