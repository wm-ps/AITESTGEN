import { useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEye, faEyeSlash, faLock, faShieldHalved } from '@fortawesome/free-solid-svg-icons'
import {
  ApiError,
  api,
  type HomeApplicationRead,
  type RetentionPeriod,
  type ScreenshotCapture,
  type SettingsRead,
  type UserRead,
} from '../api'
import { ApprovedDomainsPanel } from './ApprovedDomainsPanel'
import { LoadingDots } from './LoadingDots'
import { explorerApi, type ExplorerSettings } from '../explorer/explorerApi'
import { PasswordInput } from './PasswordInput'
import { SkeletonRows } from './Skeleton'
import { AccessDeniedIllustration } from './EmptyState'

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    // The hint is a hover tooltip only: no text under the field.
    <label title={hint} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)' }}>{label}</span>
      {children}
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
  background: 'var(--panel)',
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
  requires_login: boolean
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
  const [switching, setSwitching] = useState<Record<string, boolean>>({})
  const [switchError, setSwitchError] = useState<string | null>(null)

  async function toggleRequiresLogin(entry: CredentialEntry) {
    setSwitchError(null)
    setSwitching((prev) => ({ ...prev, [entry.application_id]: true }))
    try {
      await api.setRequiresLogin(entry.application_id, !entry.requires_login)
      await refreshCredentials()
    } catch (err) {
      setSwitchError(err instanceof ApiError ? err.message : 'Could not change sign-in for this application.')
    } finally {
      setSwitching((prev) => ({ ...prev, [entry.application_id]: false }))
    }
  }

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
            Stored encrypted at project level and reused for exploration, generation and every run. Turn Sign-in
            off for an app that has no login — exploration and tests then open it directly.
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

      {switchError && (
        <div style={{ color: 'var(--bad)', fontSize: 13 }} role="alert">
          {switchError}
        </div>
      )}

      {entries === null ? (
        !loadError && <SkeletonRows count={3} height={40} gap={10} />
      ) : entries.length === 0 ? (
        <div style={{ fontSize: 12.5, color: 'var(--fg-4)' }}>No applications with stored sign-in credentials yet.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr) minmax(0,1fr) 72px', gap: 12, padding: '0 4px 8px', borderBottom: '1px solid var(--line)' }}>
            <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-5)' }}>Application</div>
            <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-5)' }}>Username</div>
            <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-5)' }}>Secret</div>
            <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-5)' }}>Sign-in</div>
          </div>
          {entries.map((entry) => {
            return (
              <div
                key={entry.application_id}
                style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr) minmax(0,1fr) 72px', gap: 12, alignItems: 'center', padding: '12px 4px', borderBottom: '1px solid var(--row-line)' }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.application_name}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-4)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.environment}</div>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--fg-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.username || (entry.requires_login ? '' : 'No login')}</div>
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
                <button
                  type="button"
                  role="switch"
                  aria-checked={entry.requires_login}
                  aria-label={`${entry.application_name} requires sign-in`}
                  title={entry.requires_login ? 'Signs in with these credentials. Turn off if the app has no login.' : 'No login: opened directly. Turn on to sign in with these credentials.'}
                  disabled={switching[entry.application_id]}
                  onClick={() => toggleRequiresLogin(entry)}
                  style={{ width: 36, height: 20, borderRadius: 1000, padding: 2, display: 'flex', border: 'none', cursor: 'pointer', background: entry.requires_login ? 'var(--ok)' : 'var(--border-2)', transition: 'background 0.15s' }}
                >
                  <span style={{ width: 16, height: 16, borderRadius: 1000, background: entry.requires_login ? 'var(--on-ok)' : '#fff', transform: entry.requires_login ? 'translateX(16px)' : 'none', transition: 'transform 0.15s' }} />
                </button>
              </div>
            )
          })}
        </div>
      )}

      <form
        onSubmit={handleAddCredentials}
        style={{ border: '1px solid var(--border-2)', borderRadius: 10, background: 'var(--panel)', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}
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


// Settings → Explorer limits: what really bounds an Explorer (or authoring)
// run's time and AI cost. A run copies them when it starts; Resume picks up
// changes. "No limit" is null.
type LimitOption = { value: number | null; label: string }

function LimitSelect({
  value,
  options,
  onChange,
  label,
  disabled,
}: {
  value: number | null
  options: LimitOption[]
  onChange: (value: number | null) => void
  label: string
  disabled?: boolean
}) {
  return (
    <select
      aria-label={label}
      value={value == null ? 'none' : String(value)}
      onChange={(e) => onChange(e.target.value === 'none' ? null : Number(e.target.value))}
      disabled={disabled}
      style={fieldInputStyle}
    >
      {options.map((o) => (
        <option key={o.label} value={o.value == null ? 'none' : String(o.value)}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

const minutes = (ns: number[]): LimitOption[] => ns.map((n) => ({ value: n, label: n >= 60 && n % 60 === 0 ? `${n / 60} h` : `${n} min` }))
const counts = (ns: number[]): LimitOption[] => ns.map((n) => ({ value: n, label: String(n) }))
// Keeps a saved value selectable even when it isn't one of the presets.
const withValue = (options: LimitOption[], value: number | null): LimitOption[] =>
  options.some((o) => o.value === value) ? options : [...options, { value, label: value == null ? 'No limit' : String(value) }]

function LimitGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}>{title}</div>
      {/* auto-fill: a group with one field keeps one column's width, not the whole row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(210px,1fr))', gap: 16 }}>{children}</div>
    </div>
  )
}

function ExplorerLimitsSection({ limits, onChange }: { limits: ExplorerSettings; onChange: (limits: ExplorerSettings) => void }) {
  const set = <K extends keyof ExplorerSettings>(key: K, value: ExplorerSettings[K]) => onChange({ ...limits, [key]: value })
  const waitsForever = limits.question_wait_minutes == null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>Explorer limits</div>
        <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>
          Control how long Explorer and authoring runs take and how much AI they use. Each run uses the limits set when it starts.
        </div>
      </div>

      <LimitGroup title="Time">
        <Field label="Question wait" hint="How long a mission waits for your answer before carrying on without it.">
          <LimitSelect
            label="Question wait"
            value={limits.question_wait_minutes}
            options={withValue([...minutes([5, 10, 20, 30, 60, 120]), { value: null, label: 'Until you answer' }], limits.question_wait_minutes)}
            onChange={(v) => onChange({ ...limits, question_wait_minutes: v, ...(v == null ? { mission_time_limit_minutes: null } : {}) })}
          />
        </Field>
        <Field
          label="Mission time limit"
          hint={waitsForever ? 'No limit while missions wait until you answer.' : 'Longest one mission may take, waiting for your answers included.'}
        >
          <LimitSelect
            label="Mission time limit"
            value={limits.mission_time_limit_minutes}
            disabled={waitsForever}
            options={withValue([...minutes([30, 45, 60, 75, 90, 120, 180]), { value: null, label: 'No limit' }], limits.mission_time_limit_minutes)}
            onChange={(v) => set('mission_time_limit_minutes', v)}
          />
        </Field>
        <Field label="Run time limit" hint="Counted from when you confirm the App Summary. Reaching it pauses the run.">
          <LimitSelect
            label="Run time limit"
            value={limits.run_time_limit_minutes}
            options={withValue([{ value: null, label: 'No limit' }, ...minutes([60, 120, 240, 360, 480, 720, 1440])], limits.run_time_limit_minutes)}
            onChange={(v) => set('run_time_limit_minutes', v)}
          />
        </Field>
        <Field label="First look time limit" hint="How long Explorer looks around the app before writing the App Summary.">
          <LimitSelect
            label="First look time limit"
            value={limits.first_look_time_limit_minutes}
            options={withValue(minutes([30, 60, 90, 120, 180, 240]), limits.first_look_time_limit_minutes)}
            onChange={(v) => set('first_look_time_limit_minutes', v ?? 120)}
          />
        </Field>
        <Field label="Hidden screen search" hint="Time spent trying choices and empty or failing data to find screens that only appear sometimes.">
          <LimitSelect
            label="Hidden screen search"
            value={limits.hidden_screen_search_minutes}
            options={withValue([{ value: 0, label: 'Off' }, ...minutes([10, 25, 45, 60])], limits.hidden_screen_search_minutes)}
            onChange={(v) => set('hidden_screen_search_minutes', v ?? 0)}
          />
        </Field>
      </LimitGroup>

      <LimitGroup title="AI cost">
        <Field label="AI budget per run (USD)" hint="Reaching it pauses the run. You can then write scenarios from what was explored, or raise it and resume.">
          <input
            type="number"
            min={0.5}
            step={0.5}
            placeholder="No limit"
            aria-label="AI budget per run (USD)"
            value={limits.ai_budget_usd ?? ''}
            onChange={(e) => set('ai_budget_usd', e.target.value === '' ? null : Number(e.target.value))}
            style={fieldInputStyle}
          />
        </Field>
      </LimitGroup>

      <LimitGroup title="Coverage">
        <Field label="Screens in the first look" hint="Most screens Explorer visits before writing the App Summary.">
          <LimitSelect
            label="Screens in the first look"
            value={limits.first_look_max_screens}
            options={withValue(counts([25, 50, 100, 150, 250, 500]), limits.first_look_max_screens)}
            onChange={(v) => set('first_look_max_screens', v ?? 150)}
          />
        </Field>
        <Field label="Maximum missions" hint="Most missions (walk-throughs of a task) in one run, follow-ups included.">
          <LimitSelect
            label="Maximum missions"
            value={limits.max_missions}
            options={withValue(counts([5, 10, 15, 20, 30, 50]), limits.max_missions)}
            onChange={(v) => set('max_missions', v ?? 15)}
          />
        </Field>
        <Field label="Steps per mission" hint="Most clicks and entries one mission may take.">
          <LimitSelect
            label="Steps per mission"
            value={limits.steps_per_mission}
            options={withValue(counts([10, 20, 30, 40, 60]), limits.steps_per_mission)}
            onChange={(v) => set('steps_per_mission', v ?? 20)}
          />
        </Field>
        <Field label="Maximum scenarios" hint="Most scenarios Explorer tries to prove in one run.">
          <LimitSelect
            label="Maximum scenarios"
            value={limits.max_scenarios}
            options={withValue(counts([25, 50, 100, 150, 250, 500]), limits.max_scenarios)}
            onChange={(v) => set('max_scenarios', v ?? 150)}
          />
        </Field>
      </LimitGroup>

      <LimitGroup title="Accuracy">
        <Field label="Proof replays" hint="Clean replays each scenario must pass before it becomes a test case. More is surer but slower.">
          <LimitSelect
            label="Proof replays"
            value={limits.proof_replays}
            options={withValue([{ value: 0, label: 'None (fastest)' }, ...counts([1, 2, 3])], limits.proof_replays)}
            onChange={(v) => set('proof_replays', v ?? 1)}
          />
        </Field>
      </LimitGroup>
    </div>
  )
}

export function Settings({ user, onCancel }: { user: UserRead; onCancel: () => void }) {
  const [settings, setSettings] = useState<SettingsRead | null>(null)
  const [limits, setLimits] = useState<ExplorerSettings | null>(null)
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
    Promise.all([api.getSettings(), explorerApi.getSettings()])
      .then(([loaded, explorer]) => {
        setSettings(loaded)
        setLimits(explorer)
      })
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
            Exploration settings are limited to organization admins. Ask an admin on your team for access.
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
    if (!settings || !limits) return
    setError(null)
    setSubmitting(true)
    try {
      const [updated, explorer] = await Promise.all([api.updateSettings(settings), explorerApi.saveSettings(limits)])
      setSettings(updated)
      setLimits(explorer)
      onCancel()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Saving settings failed.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading || !settings || !limits) {
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
        <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 4 }}>Exploration limits, credentials and schedules.</div>
      </div>

      <form onSubmit={handleSubmit} style={panelStyle}>
        <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
          <ExplorerLimitsSection limits={limits} onChange={setLimits} />

          <div style={{ height: 1, background: 'var(--line)' }} />

          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>Test case generation</div>
            <div style={{ fontSize: 12, color: 'var(--fg-4)', marginTop: 2 }}>How many test cases are written and how failing ones are handled.</div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(190px,1fr))', gap: 16 }}>
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

            <Field label="Screenshot capture">
              <select
                value={settings.screenshot_capture}
                onChange={(e) => setSettings({ ...settings, screenshot_capture: e.target.value as ScreenshotCapture })}
                style={fieldInputStyle}
              >
                <option value="failed">Failed test cases</option>
                <option value="passed">Passed test cases</option>
                <option value="all">All</option>
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
                Deletes exploration data, generated test cases, screenshots and run history for a project once it is removed.
              </div>
            </div>
            <select
              value={settings.delete_project_after}
              onChange={(e) => setSettings({ ...settings, delete_project_after: e.target.value as RetentionPeriod })}
              style={{ height: 32, padding: '0 10px', border: '1px solid var(--border-2)', borderRadius: 8, fontSize: 12.5, color: 'var(--fg-1)', background: 'var(--panel)', flex: 'none' }}
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

      <ApprovedDomainsPanel />

      <CredentialsPanel />
    </div>
  )
}
