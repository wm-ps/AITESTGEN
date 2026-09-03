import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, type ScheduleRead } from '../../api'
import { ScheduleDialog } from './ScheduleDialog'

// Same "Date & Time" formatting convention as RunsTab's own
// formatDateTimeWithZone — a bare "6:42 AM" is ambiguous once the viewer
// isn't in the same zone as the schedule.
function formatDateTimeWithZone(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  })
}

const columnHeaderLabelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--ink-faint)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}

// Self-contained on/off control — doubles as the status indicator (no
// separate "Enabled"/"Disabled" pill needed alongside it, the switch's own
// position already says that) and the control that flips it.
function ToggleSwitch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onChange}
      style={{
        position: 'relative',
        width: 36,
        height: 20,
        borderRadius: 'var(--radius-full)',
        border: 'none',
        padding: 0,
        flexShrink: 0,
        background: checked ? 'var(--accent)' : 'var(--border-strong)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
        transition: 'background 0.15s ease',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: 2,
          left: checked ? 18 : 2,
          width: 16,
          height: 16,
          borderRadius: 'var(--radius-full)',
          background: '#fff',
          boxShadow: '0 1px 2px rgba(15,23,42,0.35)',
          transition: 'left 0.15s ease',
        }}
      />
    </button>
  )
}

// Same three-dot glyph as Home.tsx's own kebab menu — not a new shape.
function MoreIcon() {
  return (
    <svg width={19} height={19} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="12" cy="5" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="12" cy="19" r="1.8" />
    </svg>
  )
}

const kebabButtonStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 24,
  height: 24,
  borderRadius: 6,
  border: 'none',
  background: 'none',
  color: 'var(--ink-muted)',
  padding: 0,
  cursor: 'pointer',
}

const menuItemStyle: React.CSSProperties = {
  display: 'block',
  width: '100%',
  textAlign: 'left',
  padding: '9px 14px',
  fontSize: 13.5,
  fontWeight: 500,
  border: 'none',
  background: 'none',
  color: 'var(--ink)',
  cursor: 'pointer',
}

// Same overlay-backdrop-to-close + absolutely-positioned card-panel pattern
// as Home.tsx's own per-row kebab menu — one row's menu open at a time,
// tracked by the parent (`openMenuId`) rather than per-row local state, so
// opening a second row's menu always closes the first.
function RowMenu({
  open,
  onOpenChange,
  items,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  items: { label: string; onClick: () => void; disabled?: boolean; danger?: boolean }[]
}) {
  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        title="More actions"
        aria-label="More actions"
        onClick={() => onOpenChange(!open)}
        style={kebabButtonStyle}
      >
        <MoreIcon />
      </button>
      {open && (
        <>
          <div
            data-testid="row-menu-backdrop"
            onClick={() => onOpenChange(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 9 }}
          />
          <div
            className="card-panel"
            style={{
              position: 'absolute',
              top: '100%',
              right: 0,
              marginTop: 4,
              minWidth: 140,
              padding: 4,
              zIndex: 10,
              boxShadow: 'var(--shadow-dropdown-lg)',
            }}
          >
            {items.map((item) => (
              <button
                key={item.label}
                type="button"
                disabled={item.disabled}
                onClick={() => {
                  onOpenChange(false)
                  item.onClick()
                }}
                style={{
                  ...menuItemStyle,
                  color: item.danger ? 'var(--danger)' : menuItemStyle.color,
                  opacity: item.disabled ? 0.6 : 1,
                  cursor: item.disabled ? 'not-allowed' : 'pointer',
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// One piece of state for "which dialog, if any, is open" rather than a
// separate boolean + a separate editing-id — those two could otherwise
// drift out of sync with each other.
type DialogState = 'create' | { edit: ScheduleRead } | null

export function SchedulesTab({ applicationId }: { applicationId: string }) {
  const [schedules, setSchedules] = useState<ScheduleRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [dialog, setDialog] = useState<DialogState>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)

  const reload = useCallback(
    async (signal?: { cancelled: boolean }) => {
      try {
        const body = await api.listSchedules(applicationId)
        if (signal?.cancelled) return
        setSchedules(body)
        setLoadError(null)
      } catch (err) {
        if (signal?.cancelled) return
        setLoadError(err instanceof ApiError ? err.message : "Couldn't load schedules.")
      }
    },
    [applicationId],
  )

  useEffect(() => {
    const signal = { cancelled: false }
    reload(signal)
    // next_run_at moves once per occurrence, not once a second — no poll
    // interval here (unlike RunsTab); a manual refresh after every mutation
    // below is enough.
    return () => {
      signal.cancelled = true
    }
  }, [reload])

  async function handleToggle(schedule: ScheduleRead) {
    setActionError(null)
    setPendingAction(schedule.id)
    try {
      if (schedule.enabled) await api.disableSchedule(schedule.id)
      else await api.enableSchedule(schedule.id)
      await reload()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Could not update this schedule.')
    } finally {
      setPendingAction(null)
    }
  }

  async function handleDelete(schedule: ScheduleRead) {
    setActionError(null)
    setPendingAction(schedule.id)
    try {
      await api.deleteSchedule(schedule.id)
      await reload()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Could not delete this schedule.')
    } finally {
      setPendingAction(null)
    }
  }

  async function handleRunNow(schedule: ScheduleRead) {
    setActionError(null)
    setPendingAction(schedule.id)
    try {
      await api.runScheduleNow(schedule.id)
    } catch (err) {
      if (err instanceof ApiError && err.message === 'EXECUTION_IN_PROGRESS') {
        setActionError('A test run for this application is already in progress — try again once it finishes.')
      } else if (err instanceof ApiError && err.message === 'EXECUTION_UNAVAILABLE') {
        setActionError('The test execution service is not responding right now. Please try again in a moment.')
      } else {
        setActionError(err instanceof ApiError ? err.message : 'Could not trigger this schedule.')
      }
    } finally {
      setPendingAction(null)
    }
  }

  if (loadError) {
    return (
      <p role="alert" style={{ color: 'var(--danger)', fontSize: 13 }}>
        {loadError}
      </p>
    )
  }
  if (!schedules) {
    return (
      <p className="caption" style={{ fontSize: 12.5 }}>
        Loading…
      </p>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
        <button type="button" className="button-primary" onClick={() => setDialog('create')}>
          New schedule
        </button>
      </div>

      {actionError && (
        <p role="alert" style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 14 }}>
          {actionError}
        </p>
      )}

      {schedules.length === 0 ? (
        <p className="caption" style={{ fontSize: 13 }}>
          No schedules yet. Create one to run this Application's tests automatically on a
          recurring cadence.
        </p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ ...columnHeaderLabelStyle, width: '20%' }}>Name</th>
              <th style={{ ...columnHeaderLabelStyle, width: '32%' }}>Cadence</th>
              <th style={{ ...columnHeaderLabelStyle, width: '20%' }}>Next run</th>
              <th style={{ ...columnHeaderLabelStyle, width: '10%' }}>Enabled</th>
              <th style={{ ...columnHeaderLabelStyle, width: '8%' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {schedules.map((schedule) => (
              <tr key={schedule.id}>
                <td style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>{schedule.name}</td>
                <td style={{ fontSize: 12.5, color: 'var(--ink-secondary)' }}>{schedule.cadence_label}</td>
                <td className="caption" style={{ fontSize: 12 }}>
                  {schedule.next_run_at ? formatDateTimeWithZone(schedule.next_run_at) : '—'}
                </td>
                <td>
                  <ToggleSwitch
                    checked={schedule.enabled}
                    disabled={pendingAction === schedule.id}
                    onChange={() => handleToggle(schedule)}
                  />
                </td>
                <td>
                  <RowMenu
                    open={openMenuId === schedule.id}
                    onOpenChange={(open) => setOpenMenuId(open ? schedule.id : null)}
                    items={[
                      {
                        label: 'Run now',
                        disabled: pendingAction === schedule.id,
                        onClick: () => handleRunNow(schedule),
                      },
                      {
                        label: 'Edit',
                        disabled: pendingAction === schedule.id,
                        onClick: () => setDialog({ edit: schedule }),
                      },
                      {
                        label: 'Delete',
                        danger: true,
                        disabled: pendingAction === schedule.id,
                        onClick: () => handleDelete(schedule),
                      },
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {dialog && (
        <ScheduleDialog
          applicationId={applicationId}
          initial={dialog === 'create' ? null : dialog.edit}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null)
            reload()
          }}
        />
      )}
    </div>
  )
}
