import { useEffect, useState } from 'react'
import { ApiError, api, type InteractionLevel, type RetentionPeriod, type SettingsRead, type UserRead } from '../api'
import { LoadingDots } from './LoadingDots'
import { AccessDeniedIllustration } from './EmptyState'

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
      {children}
    </span>
  )
}

export function Settings({ user, onCancel }: { user: UserRead; onCancel: () => void }) {
  const [settings, setSettings] = useState<SettingsRead | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const isAdmin = user.role === 'admin'

  useEffect(() => {
    // The account menu already hides Settings from non-admins — this guard
    // is only for a member landing here some other way (e.g. restored view
    // state). The API rejects non-admins anyway (CurrentAdminDep); skipping
    // the call here just avoids a guaranteed-403 request.
    if (!isAdmin) {
      setLoading(false)
      return
    }
    api
      .getSettings()
      .then(setSettings)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Loading settings failed.'))
      .finally(() => setLoading(false))
  }, [isAdmin])

  if (!isAdmin) {
    return (
      <main style={{ maxWidth: 'clamp(720px, 92vw, var(--content-max-wide))', margin: '0 auto', padding: '32px 24px' }}>
        <div className="card-panel" style={{ padding: '56px 32px', textAlign: 'center' }}>
          <div
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              width: 160,
              height: 160,
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '42% 58% 53% 47% / 45% 40% 60% 55%',
              background: 'linear-gradient(135deg, var(--canvas-wash-alt) 0%, var(--danger-wash) 100%)',
              marginBottom: 'var(--space-6)',
            }}
          >
            <AccessDeniedIllustration size={96} />
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>Access denied</div>
          <p className="caption" style={{ fontSize: 13.5, margin: '8px auto 0', maxWidth: 360, lineHeight: 1.5 }}>
            Discovery settings are limited to organization admins. Ask an admin on your team for access.
          </p>
          <button
            type="button"
            className="button-secondary"
            onClick={onCancel}
            style={{ marginTop: 'var(--space-7)', padding: '10px 20px' }}
          >
            Back
          </button>
        </div>
      </main>
    )
  }

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
      <main style={{ maxWidth: 'clamp(720px, 92vw, var(--content-max-wide))', margin: '0 auto', padding: '32px 24px' }} role="status">
        {error ?? <LoadingDots label="Loading settings" />}
      </main>
    )
  }

  return (
    <main style={{ maxWidth: 'clamp(720px, 92vw, var(--content-max-wide))', margin: '0 auto', padding: '32px 24px' }}>
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
              {[5, 10, 20, 50, 100, 250, 500, 1000].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <FieldLabel>Maximum discovery duration</FieldLabel>
            <select
              value={settings.max_discovery_duration_minutes ?? 'unlimited'}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  max_discovery_duration_minutes:
                    e.target.value === 'unlimited' ? null : Number(e.target.value),
                })
              }
            >
              {[2, 5, 10, 15, 30, 60].map((n) => (
                <option key={n} value={n}>
                  {n} min
                </option>
              ))}
              <option value="unlimited">Unlimited</option>
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

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-7)' }}>
          <label className="field">
            <FieldLabel>Delete project after</FieldLabel>
            <select
              value={settings.delete_project_after}
              onChange={(e) =>
                setSettings({ ...settings, delete_project_after: e.target.value as RetentionPeriod })
              }
            >
              <option value="1_day">1 day</option>
              <option value="1_week">1 week</option>
              <option value="1_month">1 month</option>
            </select>
          </label>

          <label className="field">
            <FieldLabel>Max self-heal attempts</FieldLabel>
            <select
              value={settings.max_heal_attempts}
              onChange={(e) =>
                setSettings({ ...settings, max_heal_attempts: Number(e.target.value) })
              }
            >
              {[0, 1, 2, 3, 5, 10].map((n) => (
                <option key={n} value={n}>
                  {n === 0 ? 'Disabled' : n}
                </option>
              ))}
            </select>
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
