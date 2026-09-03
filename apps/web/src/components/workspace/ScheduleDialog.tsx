import { useState } from 'react'
import { ApiError, api, type ScheduleCadenceType, type ScheduleCreate, type ScheduleRead } from '../../api'
import { LoadingDots } from '../LoadingDots'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="label-required" style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)' }}>
      {children}
    </span>
  )
}

const CADENCE_OPTIONS: { value: ScheduleCadenceType; label: string }[] = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'custom_cron', label: 'Custom (cron)' },
]

// 0 = Sunday .. 6 = Saturday — the server stores exactly this numbering
// (ScheduleCalendarSpec.day_of_week's own), so there is no conversion here.
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

const HOURS = Array.from({ length: 24 }, (_, h) => h)
// 15-minute granularity: two plain <select>s instead of `type="time"` (no
// precedent anywhere in this app, and its rendering/parsing is
// locale-dependent) — matches the app's existing plain-<select>-for-enums
// convention and needs no free-text parsing. Finer granularity is
// deliberately a Custom-cron job, not a fourth widget.
const MINUTES = [0, 15, 30, 45]
// 1-28 only, mirroring the server's cap: every Gregorian month has at
// least 28 days, so this always exists; 29-31 would silently skip short
// months.
const DAYS_OF_MONTH = Array.from({ length: 28 }, (_, i) => i + 1)

// Intl.supportedValuesOf is available in every browser this app targets;
// the short fallback list exists only so jsdom (vitest) renders something.
const TIME_ZONES: string[] =
  (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.(
    'timeZone',
  ) ?? ['UTC', 'Asia/Kolkata', 'America/New_York', 'Europe/London']
const BROWSER_TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone

type FormState = {
  name: string
  cadenceType: ScheduleCadenceType
  hour: number
  minute: number
  daysOfWeek: Set<number>
  dayOfMonth: number
  cronExpression: string
  timeZone: string
}

function blankForm(): FormState {
  return {
    name: '',
    cadenceType: 'daily',
    hour: 2,
    minute: 0, // 02:00 — a nightly-regression default
    daysOfWeek: new Set([1]), // Monday
    dayOfMonth: 1,
    cronExpression: '',
    timeZone: TIME_ZONES.includes(BROWSER_TIME_ZONE) ? BROWSER_TIME_ZONE : 'UTC',
  }
}

function formFromSchedule(schedule: ScheduleRead): FormState {
  return {
    name: schedule.name,
    cadenceType: schedule.cadence_type,
    hour: schedule.hour ?? 2,
    minute: schedule.minute ?? 0,
    daysOfWeek: new Set(schedule.days_of_week),
    dayOfMonth: schedule.day_of_month ?? 1,
    cronExpression: schedule.cron_expression ?? '',
    timeZone: schedule.time_zone,
  }
}

function toPayload(form: FormState): ScheduleCreate {
  const base = { name: form.name.trim(), cadence_type: form.cadenceType, time_zone: form.timeZone }
  if (form.cadenceType === 'custom_cron') {
    return { ...base, cron_expression: form.cronExpression.trim() }
  }
  return {
    ...base,
    hour: form.hour,
    minute: form.minute,
    days_of_week: form.cadenceType === 'weekly' ? [...form.daysOfWeek].sort((a, b) => a - b) : [],
    day_of_month: form.cadenceType === 'monthly' ? form.dayOfMonth : null,
  }
}

// Same limitation as item 4's design note, stated in-product: a worker
// outage caps the schedule at one eventual late run for the whole outage
// window (overlap=SKIP drops everything scheduled in between), it does not
// queue or backfill missed occurrences.
const WORKER_DOWN_CAPTION =
  "Scheduled runs need the execution worker online at fire time. If it's offline, only the " +
  'first missed run eventually starts once the worker returns — any other runs that would ' +
  'have fired during the outage are skipped, not queued or backfilled.'

export function ScheduleDialog({
  applicationId,
  initial,
  onClose,
  onSaved,
}: {
  applicationId: string
  initial: ScheduleRead | null
  onClose: () => void
  onSaved: () => void
}) {
  useEscapeToClose(onClose)
  const [form, setForm] = useState<FormState>(initial ? formFromSchedule(initial) : blankForm())
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const payload = toPayload(form)
      if (initial) {
        await api.updateSchedule(initial.id, payload)
      } else {
        await api.createSchedule(applicationId, payload)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save this schedule.')
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
        style={{ width: '100%', maxWidth: 480, padding: '24px 28px', boxSizing: 'border-box' }}
      >
        <h2 style={{ fontSize: 17, fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px' }}>
          {initial ? 'Edit schedule' : 'New schedule'}
        </h2>
        <p style={{ fontSize: 13.5, color: 'var(--ink-muted)', margin: '10px 0 18px' }}>
          Automatically runs "Run All Tests" for this Application on the cadence below.
        </p>

        <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <label className="field">
              <FieldLabel>Name</FieldLabel>
              <input
                required
                autoFocus
                placeholder="Nightly Regression"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>

            <label className="field">
              <FieldLabel>Cadence</FieldLabel>
              <select
                value={form.cadenceType}
                onChange={(e) => setForm({ ...form, cadenceType: e.target.value as ScheduleCadenceType })}
              >
                {CADENCE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>

            {form.cadenceType === 'weekly' && (
              <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
                <legend style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-secondary)', padding: 0 }}>
                  Days
                </legend>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 6 }}>
                  {DAYS.map((label, day) => (
                    <label
                      key={label}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}
                    >
                      <input
                        type="checkbox"
                        checked={form.daysOfWeek.has(day)}
                        onChange={() => {
                          const next = new Set(form.daysOfWeek)
                          if (next.has(day)) next.delete(day)
                          else next.add(day)
                          setForm({ ...form, daysOfWeek: next })
                        }}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}

            {form.cadenceType === 'monthly' && (
              <label className="field">
                <FieldLabel>Day of month</FieldLabel>
                <select
                  value={form.dayOfMonth}
                  onChange={(e) => setForm({ ...form, dayOfMonth: Number(e.target.value) })}
                >
                  {DAYS_OF_MONTH.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
                <span className="caption" style={{ fontSize: 12 }}>
                  Days 29-31 aren't offered — they'd skip short months. Use a custom cron expression
                  instead.
                </span>
              </label>
            )}

            {form.cadenceType === 'custom_cron' ? (
              <label className="field">
                <FieldLabel>Cron expression</FieldLabel>
                <input
                  required
                  placeholder="0 2 * * 1-5"
                  value={form.cronExpression}
                  onChange={(e) => setForm({ ...form, cronExpression: e.target.value })}
                />
                <span className="caption" style={{ fontSize: 12 }}>
                  Five fields: minute hour day-of-month month day-of-week. Interpreted in the time
                  zone below.
                </span>
              </label>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-7)' }}>
                <label className="field">
                  <FieldLabel>Hour</FieldLabel>
                  <select value={form.hour} onChange={(e) => setForm({ ...form, hour: Number(e.target.value) })}>
                    {HOURS.map((h) => (
                      <option key={h} value={h}>
                        {String(h).padStart(2, '0')}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <FieldLabel>Minute</FieldLabel>
                  <select value={form.minute} onChange={(e) => setForm({ ...form, minute: Number(e.target.value) })}>
                    {MINUTES.map((m) => (
                      <option key={m} value={m}>
                        {String(m).padStart(2, '0')}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}

            <label className="field">
              <FieldLabel>Time zone</FieldLabel>
              {/* Explicit IANA zone, never a UTC offset — mirrors this
                  feature's backend Schedule.time_zone, which avoids DST
                  bugs by construction. */}
              <select value={form.timeZone} onChange={(e) => setForm({ ...form, timeZone: e.target.value })}>
                {TIME_ZONES.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </label>

            <p
              className="caption"
              style={{
                background: 'var(--canvas-wash)',
                borderRadius: 'var(--radius)',
                padding: 'var(--space-3)',
                margin: 0,
                fontSize: 12,
                lineHeight: 1.5,
              }}
            >
              {WORKER_DOWN_CAPTION}
            </p>

            {error && (
              <div role="alert" style={{ color: 'var(--danger)', fontSize: 13 }}>
                {error}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
              <button
                type="button"
                className="button-secondary"
                onClick={onClose}
                style={{ flex: 1, padding: 11, fontSize: 14 }}
              >
                Cancel
              </button>
              <button type="submit" className="button-primary" disabled={submitting} style={{ flex: 1, padding: 11, fontSize: 14 }}>
                {submitting ? <LoadingDots label="Saving" /> : initial ? 'Save changes' : 'Create schedule'}
              </button>
            </div>
          </div>
        </fieldset>
      </form>
    </div>
  )
}
