import { useState } from 'react'
import { faXmark } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type ScheduleCadenceType, type ScheduleCreate, type ScheduleRead } from '../../api'
import { modalButton, modalCloseButton, modalFooter, modalHeader, modalOverlay, modalPanel, modalTitle } from '../modalStyles'
import { LoadingDots } from '../LoadingDots'
import { EnvironmentSelect } from '../environments/EnvironmentSelect'
import { SuiteSelect } from './suites/SuiteSelect'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'
import { faIcon } from '../../faIcon'

const Xmark = faIcon(faXmark)

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="label-required"
      style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--fg-4)' }}
    >
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

type FormState = {
  name: string
  cadenceType: ScheduleCadenceType
  hour: number
  minute: number
  daysOfWeek: Set<number>
  dayOfMonth: number
  cronExpression: string
  // null = the application's own (default) environment.
  environmentId: string | null
  // null = every test case.
  testCollectionId: string | null
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
    environmentId: null,
    testCollectionId: null,
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
    environmentId: schedule.environment_id ?? null,
    testCollectionId: schedule.test_collection_id ?? null,
  }
}

function toPayload(form: FormState): ScheduleCreate {
  // No time_zone — the server stamps every new schedule with its own
  // configured default (SCHEDULE_DEFAULT_TIME_ZONE); there's nothing for
  // this dialog to send.
  const base = { name: form.name.trim(), cadence_type: form.cadenceType }
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
      // Only sent when it differs from what the schedule already has, so an
      // edit that doesn't touch it leaves it alone — and null moves a schedule
      // back to the default environment.
      if (form.environmentId !== (initial?.environment_id ?? null)) {
        payload.environment_id = form.environmentId
      }
      // Same rule for the suite: an edit that doesn't touch it leaves it alone,
      // and null moves the schedule back to every test case.
      if (form.testCollectionId !== (initial?.test_collection_id ?? null)) {
        payload.test_collection_id = form.testCollectionId
      }
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
    <div onClick={onClose} style={{ ...modalOverlay, zIndex: 90 }}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        style={{ ...modalPanel, maxWidth: 440 }}
      >
        <div style={modalHeader}>
          <div>
            <h2 style={modalTitle}>{initial ? 'Edit schedule' : 'New schedule'}</h2>
            <p className="caption" style={{ margin: '4px 0 0', fontSize: 13 }}>
              Run all test cases or one test suite automatically on a cadence.
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} style={modalCloseButton}>
            <Xmark size={13} />
          </button>
        </div>

        <fieldset disabled={submitting} style={{ border: 0, margin: 0, padding: 0, display: 'contents' }}>
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16, padding: '4px 28px 22px' }}>
            <label className="field">
              <FieldLabel>Name</FieldLabel>
              <input
                required
                autoFocus
                placeholder="Enter a name for this schedule"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>

            <SuiteSelect
              applicationId={applicationId}
              value={form.testCollectionId}
              onChange={(testCollectionId) => setForm({ ...form, testCollectionId })}
            />

            <EnvironmentSelect
              label="Environment"
              value={form.environmentId}
              onChange={(environmentId) => setForm({ ...form, environmentId })}
            />

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
                <legend style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--fg-2)', padding: 0 }}>
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
                  Five fields: minute hour day-of-month month day-of-week. Interpreted in this
                  server's configured time zone.
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

            <p
              className="caption"
              style={{
                background: 'var(--bg-2)',
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
          </div>

          <div style={modalFooter}>
            <button type="button" className="button-secondary" onClick={onClose} style={modalButton}>
              Cancel
            </button>
            <button
              type="submit"
              className="button-primary"
              disabled={submitting}
              style={{ ...modalButton, cursor: submitting ? 'not-allowed' : 'pointer' }}
            >
              {submitting ? <LoadingDots label="Saving" /> : initial ? 'Save changes' : 'Create schedule'}
            </button>
          </div>
        </fieldset>
      </form>
    </div>
  )
}
