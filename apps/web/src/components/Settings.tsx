import { useEffect, useState } from 'react'
import { ApiError, api, type InteractionLevel, type SettingsRead } from '../api'
import { LoadingDots } from './LoadingDots'

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
      {children}
    </span>
  )
}

export function Settings({ onCancel }: { onCancel: () => void }) {
  const [settings, setSettings] = useState<SettingsRead | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api
      .getSettings()
      .then(setSettings)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Loading settings failed.'))
      .finally(() => setLoading(false))
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!settings) return
    setError(null)
    setSubmitting(true)
    try {
      const updated = await api.updateSettings(settings)
      setSettings(updated)
      onCancel()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Saving settings failed.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading || !settings) {
    return (
      <main style={{ maxWidth: 'clamp(720px, 68vw, 1080px)', margin: '0 auto', padding: '32px 24px' }} role="status">
        {error ?? <LoadingDots label="Loading settings" />}
      </main>
    )
  }

  return (
    <main style={{ maxWidth: 'clamp(720px, 68vw, 1080px)', margin: '0 auto', padding: '32px 24px' }}>
      <h1 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 12px', textAlign: 'center' }}>
        Discovery settings
      </h1>

      <form
        onSubmit={handleSubmit}
        className="card-panel"
        style={{
          padding: '14px 22px',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-3)',
          boxShadow: 'var(--shadow-dropdown-lg)',
        }}
      >
        <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-7)' }}>
          <label className="field">
            <FieldLabel>Maximum pages</FieldLabel>
            <select
              value={settings.max_pages}
              onChange={(e) => setSettings({ ...settings, max_pages: Number(e.target.value) })}
            >
              {[50, 100, 250, 500, 1000].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <FieldLabel>Maximum discovery duration</FieldLabel>
            <select
              value={settings.max_discovery_duration_minutes}
              onChange={(e) =>
                setSettings({ ...settings, max_discovery_duration_minutes: Number(e.target.value) })
              }
            >
              {[5, 10, 15, 30, 60].map((n) => (
                <option key={n} value={n}>
                  {n} min
                </option>
              ))}
            </select>
          </label>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-7)' }}>
          <label className="field">
            <FieldLabel>Navigation timeout</FieldLabel>
            <select
              value={settings.navigation_timeout_seconds}
              onChange={(e) =>
                setSettings({ ...settings, navigation_timeout_seconds: Number(e.target.value) })
              }
            >
              {[10, 15, 30, 60].map((n) => (
                <option key={n} value={n}>
                  {n} sec
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <FieldLabel>Interaction level</FieldLabel>
            <select
              value={settings.interaction_level}
              onChange={(e) =>
                setSettings({ ...settings, interaction_level: e.target.value as InteractionLevel })
              }
            >
              <option value="passive">Passive</option>
              <option value="normal">Normal</option>
              <option value="aggressive">Aggressive</option>
            </select>
          </label>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--space-7)' }}>
          <label className="field">
            <FieldLabel>Max journeys</FieldLabel>
            <input
              type="number"
              min={1}
              placeholder="Unlimited"
              value={settings.max_journeys ?? ''}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  max_journeys: e.target.value === '' ? null : Number(e.target.value),
                })
              }
            />
          </label>

          <label className="field">
            <FieldLabel>Max scenarios / journey</FieldLabel>
            <input
              type="number"
              min={1}
              placeholder="Unlimited"
              value={settings.max_scenarios_per_journey ?? ''}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  max_scenarios_per_journey: e.target.value === '' ? null : Number(e.target.value),
                })
              }
            />
          </label>

          <label className="field">
            <FieldLabel>Max test cases / application</FieldLabel>
            <input
              type="number"
              min={1}
              placeholder="Unlimited"
              value={settings.max_test_cases_per_application ?? ''}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  max_test_cases_per_application:
                    e.target.value === '' ? null : Number(e.target.value),
                })
              }
            />
          </label>
        </div>

        {error && (
          <div style={{ color: 'var(--danger)', fontSize: 13 }} role="alert">
            {error}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-4)', marginTop: 'var(--space-4)' }}>
          <button type="button" className="button-secondary" onClick={onCancel} style={{ padding: '9px 18px' }}>
            Cancel
          </button>
          <button type="submit" className="button-primary" disabled={submitting} style={{ padding: '9px 20px' }}>
            {submitting ? <LoadingDots label="Saving" /> : 'Save settings'}
          </button>
        </div>
        </fieldset>
      </form>
    </main>
  )
}
