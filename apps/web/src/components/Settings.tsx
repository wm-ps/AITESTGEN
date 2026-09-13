import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEye, faEyeSlash, faLock, faShieldHalved } from '@fortawesome/free-solid-svg-icons'
import {
  ApiError,
  api,
  type HomeApplicationRead,
  type InteractionLevel,
  type RetentionPeriod,
  type SettingsRead,
  type UserRead,
} from '../api'
import { LoadingDots } from './LoadingDots'
import { PasswordInput } from './PasswordInput'
import { SkeletonRows } from './Skeleton'
import { AccessDeniedIllustration } from './EmptyState'

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)' }}>{label}</span>
      {children}
      {hint && <span style={{ fontSize: 10.5, color: 'var(--fg-4)' }}>{hint}</span>}
    </label>
  )
}

const fieldInputStyle: React.CSSProperties = {
  height: 38,
  padding: '0 12px',
  border: '1px solid var(--border-2)',
  borderRadius: 8,
  fontSize: 13.5,
  color: 'var(--fg-1)',
  background: 'var(--panel-2)',
  outline: 'none',
  width: '100%',
  boxSizing: 'border-box',
  fontFamily: 'inherit',
}

const panelStyle: React.CSSProperties = {
  background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
  backdropFilter: 'blur(16px) saturate(1.25)',
  border: '1px solid var(--border-1)',
  borderRadius: 14,
  padding: 20,
  display: 'flex',
  flexDirection: 'column',
  gap: 18,
  boxShadow: 'var(--panel-shadow)',
}

type CredentialEntry = {
  application_id: string
  application_name: string
  environment: string
  username: string
  has_password: boolean
}

function CredentialsPanel() {
  const [entries, setEntries] = useState<CredentialEntry[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [revealed, setRevealed] = useState<Record<string, string>>({})
  const [revealing, setRevealing] = useState<Record<string, boolean>>({})

  const [apps, setApps] = useState<HomeApplicationRead[] | null>(null)
  const [selectedAppId, setSelectedAppId] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  function refreshCredentials() {
    return api
      .listCredentials()
      .then(setEntries)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : 'Loading saved credentials failed.'))
  }

  useEffect(() => {
    refreshCredentials()
    api.getHome().then(setApps).catch(() => {
      // best-effort — the "Add credentials" app picker just stays empty
    })
  }, [])

  async function handleAddCredentials(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedAppId) return
    setSaveError(null)
    setSaveSuccess(false)
    setSaving(true)
    try {
      await api.updateApplicationCredentials(selectedAppId, newUsername, newPassword)
      setNewUsername('')
      setNewPassword('')
      setSaveSuccess(true)
      await refreshCredentials()
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Could not save credentials.')
    } finally {
      setSaving(false)
    }
  }

  async function toggleReveal(applicationId: string) {
    if (revealed[applicationId] !== undefined) {
      setRevealed((prev) => {
        const next = { ...prev }
        delete next[applicationId]
        return next
      })
      return
    }
    setRevealing((prev) => ({ ...prev, [applicationId]: true }))
    try {
      const { password } = await api.revealCredential(applicationId)
      setRevealed((prev) => ({ ...prev, [applicationId]: password }))
    } catch {
      // best-effort — row just stays masked
    } finally {
      setRevealing((prev) => ({ ...prev, [applicationId]: false }))
    }
  }

  // Nothing to store or reuse credentials for yet — the panel (and its
  // "add credentials" form) has no application to point at, so skip it
  // entirely rather than show an empty shell.
  if (apps !== null && apps.length === 0) return null

  return (
    <div style={panelStyle}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>Saved credentials</div>
          <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>
            Stored encrypted at project level and reused for discovery, generation and every run.
          </div>
        </div>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 30, padding: '0 12px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel-2)', fontSize: 12, fontWeight: 500, color: 'var(--fg-2)', flex: 'none' }}>
          <FontAwesomeIcon icon={faShieldHalved} style={{ fontSize: 11, color: "var(--ok)" }} />
          Encrypted at rest
        </div>
      </div>

      {loadError && (
        <div style={{ color: 'var(--bad)', fontSize: 13 }} role="alert">
          {loadError}
        </div>
      )}

      {entries === null ? (
        !loadError && <SkeletonRows count={3} height={40} gap={10} />
      ) : entries.length === 0 ? (
        <div style={{ fontSize: 12.5, color: 'var(--fg-4)' }}>No applications with stored sign-in credentials yet.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr) minmax(0,1fr)', gap: 12, padding: '0 4px 8px', borderBottom: '1px solid var(--line)' }}>
            <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-5)' }}>Application</div>
            <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-5)' }}>Username</div>
            <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-5)' }}>Secret</div>
          </div>
          {entries.map((entry) => {
            return (
              <div
                key={entry.application_id}
                style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr) minmax(0,1fr)', gap: 12, alignItems: 'center', padding: '12px 4px', borderBottom: '1px solid var(--row-line)' }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.application_name}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-4)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.environment}</div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--fg-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.username}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {revealed[entry.application_id] ?? '••••••••'}
                  </span>
                  <button
                    type="button"
                    title={revealed[entry.application_id] !== undefined ? 'Hide' : 'Reveal'}
                    disabled={revealing[entry.application_id]}
                    onClick={() => toggleReveal(entry.application_id)}
                    style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer', color: 'var(--fg-4)', flex: 'none', display: 'flex' }}
                  >
                    {revealed[entry.application_id] !== undefined ? <FontAwesomeIcon icon={faEyeSlash} style={{ fontSize: 12 }} /> : <FontAwesomeIcon icon={faEye} style={{ fontSize: 12 }} />}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <form
        onSubmit={handleAddCredentials}
        style={{ border: '1px solid var(--border-2)', borderRadius: 10, background: 'var(--panel-2)', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}
      >
        <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--fg-1)' }}>Add credentials</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: 14 }}>
          <Field label="Application">
            <select
              required
              value={selectedAppId}
              onChange={(e) => setSelectedAppId(e.target.value)}
              style={{ ...fieldInputStyle, background: 'var(--panel)' }}
            >
              <option value="" disabled>
                Select an application
              </option>
              {(apps ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Environment">
            <input
              readOnly
              value={apps?.find((a) => a.id === selectedAppId)?.environment ?? ''}
              placeholder="Select an application first"
              style={{ ...fieldInputStyle, background: 'var(--panel)' }}
            />
          </Field>
          <Field label="Username">
            <input
              required
              autoComplete="off"
              placeholder="Enter the username"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              style={{ ...fieldInputStyle, background: 'var(--panel)', fontFamily: 'var(--font-mono)' }}
            />
          </Field>
          <Field label="Password or token">
            <PasswordInput
              required
              autoComplete="off"
              placeholder="Enter the password or token"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              style={{ ...fieldInputStyle, background: 'var(--panel)', fontFamily: 'var(--font-mono)' }}
            />
          </Field>
        </div>
        {saveError && (
          <div style={{ color: 'var(--bad)', fontSize: 12.5 }} role="alert">
            {saveError}
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            type="submit"
            disabled={saving || !selectedAppId}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 34, padding: '0 16px', borderRadius: 8, background: 'var(--accent)', color: '#fff', fontSize: 13, fontWeight: 600, cursor: saving || !selectedAppId ? 'default' : 'pointer', opacity: saving || !selectedAppId ? 0.6 : 1, border: 'none' }}
          >
            <FontAwesomeIcon icon={faLock} style={{ fontSize: 11 }} />
            {saving ? 'Saving…' : 'Save credentials'}
          </button>
          {saveSuccess && (
            <span style={{ fontSize: 12, color: 'var(--ok)' }}>Credentials saved.</span>
          )}
        </div>
      </form>
    </div>
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
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load settings.'))
      .finally(() => setLoading(false))
  }, [isAdmin])

  if (!isAdmin) {
    return (
      <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%' }}>
        <div style={{ ...panelStyle, padding: '56px 32px', textAlign: 'center', alignItems: 'center' }}>
          <div
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              width: 160,
              height: 160,
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '42% 58% 53% 47% / 45% 40% 60% 55%',
              background: 'linear-gradient(135deg, var(--panel-2) 0%, color-mix(in srgb, var(--bad) 10%, transparent) 100%)',
            }}
          >
            <AccessDeniedIllustration size={96} />
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--fg)' }}>Access denied</div>
          <p style={{ fontSize: 13.5, margin: '8px auto 0', maxWidth: 360, lineHeight: 1.5, color: 'var(--fg-3)' }}>
            Discovery settings are limited to organization admins. Ask an admin on your team for access.
          </p>
          <button
            type="button"
            onClick={onCancel}
            style={{ marginTop: 20, padding: '10px 20px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', color: 'var(--fg-2)', fontWeight: 600, cursor: 'pointer' }}
          >
            Back
          </button>
        </div>
      </div>
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
      <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%' }} role="status">
        {error ?? <SkeletonRows count={5} height={38} gap={14} />}
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Settings</h1>
        <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 4 }}>Discovery limits, credentials and schedules.</div>
      </div>

      <form onSubmit={handleSubmit} style={panelStyle}>
        <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>Discovery limits</div>
            <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>Applied to every new application unless overridden per run.</div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(190px,1fr))', gap: 16 }}>
            <Field label="Maximum discovery time" hint="Discovery stops and keeps what it found">
              <select
                value={settings.max_discovery_duration_minutes ?? 'unlimited'}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    max_discovery_duration_minutes: e.target.value === 'unlimited' ? null : Number(e.target.value),
                  })
                }
                style={fieldInputStyle}
              >
                {[2, 5, 10, 15, 30, 60].map((n) => (
                  <option key={n} value={n}>
                    {n} min
                  </option>
                ))}
                <option value="unlimited">Unlimited</option>
              </select>
            </Field>

            <Field label="Maximum pages" hint="Per application, per discovery run">
              <select value={settings.max_pages} onChange={(e) => setSettings({ ...settings, max_pages: Number(e.target.value) })} style={fieldInputStyle}>
                {[5, 10, 20, 50, 100, 250, 500, 1000].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Maximum journeys" hint="Highest-value journeys are kept first">
              <input
                type="number"
                min={1}
                placeholder="Unlimited"
                value={settings.max_journeys ?? ''}
                onChange={(e) => setSettings({ ...settings, max_journeys: e.target.value === '' ? null : Number(e.target.value) })}
                style={fieldInputStyle}
              />
            </Field>

            <Field label="Navigation timeout">
              <select
                value={settings.navigation_timeout_seconds}
                onChange={(e) => setSettings({ ...settings, navigation_timeout_seconds: Number(e.target.value) })}
                style={fieldInputStyle}
              >
                {[10, 15, 30, 60].map((n) => (
                  <option key={n} value={n}>
                    {n} sec
                  </option>
                ))}
                {[120, 180, 240, 300].map((n) => (
                  <option key={n} value={n}>
                    {n / 60} min
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Interaction level">
              <select
                value={settings.interaction_level}
                onChange={(e) => setSettings({ ...settings, interaction_level: e.target.value as InteractionLevel })}
                style={fieldInputStyle}
              >
                <option value="passive">Passive</option>
                <option value="normal">Normal</option>
                <option value="aggressive">Aggressive</option>
              </select>
            </Field>

            <Field label="Maximum scenarios / journey">
              <input
                type="number"
                min={1}
                placeholder="Unlimited"
                value={settings.max_scenarios_per_journey ?? ''}
                onChange={(e) =>
                  setSettings({ ...settings, max_scenarios_per_journey: e.target.value === '' ? null : Number(e.target.value) })
                }
                style={fieldInputStyle}
              />
            </Field>

            <Field label="Maximum test cases / application">
              <input
                type="number"
                min={1}
                placeholder="Unlimited"
                value={settings.max_test_cases_per_application ?? ''}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    max_test_cases_per_application: e.target.value === '' ? null : Number(e.target.value),
                  })
                }
                style={fieldInputStyle}
              />
            </Field>

            <Field label="Maximum self-heal attempts">
              <select
                value={settings.max_heal_attempts}
                onChange={(e) => setSettings({ ...settings, max_heal_attempts: Number(e.target.value) })}
                style={fieldInputStyle}
              >
                {[0, 1, 2, 3, 5, 10].map((n) => (
                  <option key={n} value={n}>
                    {n === 0 ? 'Disabled' : n}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <div style={{ height: 1, background: 'var(--line)' }} />

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <div title="Every removed project is cleaned up automatically" style={{ width: 36, height: 20, flex: 'none', borderRadius: 1000, padding: 2, display: 'flex', background: 'var(--ok)' }}>
              <div style={{ width: 16, height: 16, borderRadius: 1000, background: 'var(--on-ok)', transform: 'translateX(16px)' }} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg-1)' }}>Auto-clean up removed projects</div>
              <div style={{ fontSize: 11.5, color: 'var(--fg-4)', marginTop: 2 }}>
                Deletes discovery data, generated suites, screenshots and run history for a project once it is removed.
              </div>
            </div>
            <select
              value={settings.delete_project_after}
              onChange={(e) => setSettings({ ...settings, delete_project_after: e.target.value as RetentionPeriod })}
              style={{ height: 32, padding: '0 10px', border: '1px solid var(--border-2)', borderRadius: 8, fontSize: 12.5, color: 'var(--fg-1)', background: 'var(--panel-2)', flex: 'none' }}
            >
              <option value="1_day">After 1 day</option>
              <option value="1_week">After 1 week</option>
              <option value="1_month">After 1 month</option>
            </select>
          </div>

          {error && (
            <div style={{ color: 'var(--bad)', fontSize: 13 }} role="alert">
              {error}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button
              type="button"
              onClick={onCancel}
              style={{ height: 38, padding: '0 18px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', fontSize: 13.5, fontWeight: 500, color: 'var(--fg-2)', cursor: 'pointer' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              style={{
                height: 38,
                padding: '0 20px',
                borderRadius: 8,
                background: 'var(--accent)',
                color: '#fff',
                fontSize: 13.5,
                fontWeight: 600,
                cursor: submitting ? 'default' : 'pointer',
                boxShadow: 'var(--accent-glow)',
                border: 'none',
                opacity: submitting ? 0.75 : 1,
              }}
            >
              {submitting ? <LoadingDots label="Saving" /> : 'Save settings'}
            </button>
          </div>
        </fieldset>
      </form>

      <CredentialsPanel />
    </div>
  )
}
