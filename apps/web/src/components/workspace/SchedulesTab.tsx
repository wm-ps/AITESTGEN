import { useCallback, useEffect, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faEllipsisVertical } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, type ScheduleRead } from '../../api'
import { ScheduleDialog } from './ScheduleDialog'
import { SkeletonRows } from '../Skeleton'
import { EmptyState, SchedulesIllustration } from '../EmptyState'

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

const columnHeaderLabelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--fg-4)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}

const SCHEDULE_ROW_GRID_TEMPLATE = 'minmax(160px,2fr) minmax(120px,1.3fr) minmax(120px,1.2fr) 70px 32px'

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
        background: checked ? 'var(--accent)' : 'var(--track)',
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

// Vertical kebab (faEllipsisVertical) — same convention every other
// row-action menu in the app uses (Home.tsx, TeamMembers.tsx), not a
// hand-rolled horizontal-dots SVG.
function MoreIcon() {
  return <FontAwesomeIcon icon={faEllipsisVertical} style={{ fontSize: 15 }} />
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
  color: 'var(--fg-4)',
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
  color: 'var(--fg-1)',
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
                  color: item.danger ? 'var(--bad)' : menuItemStyle.color,
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
      <p role="alert" style={{ color: 'var(--bad)', fontSize: 13 }}>
        {loadError}
      </p>
    )
  }
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
        <button
          type="button"
          onClick={() => setDialog('create')}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            height: 36,
            padding: '0 18px',
            borderRadius: 8,
            border: 'none',
            fontSize: 13.5,
            fontWeight: 600,
            color: '#fff',
            background: 'var(--accent)',
            boxShadow: '0 4px 14px rgba(30,150,138,0.3)',
            cursor: 'pointer',
          }}
        >
          New schedule
        </button>
      </div>

      {actionError && (
        <p role="alert" style={{ color: 'var(--bad)', fontSize: 13, marginBottom: 14 }}>
          {actionError}
        </p>
      )}

      {schedules === null ? (
        <SkeletonRows count={3} height={48} gap={10} />
      ) : schedules.length === 0 ? (
        <EmptyState
          illustration={<SchedulesIllustration />}
          title="No schedules yet"
          subtitle="Create one to run this Application's tests automatically on a recurring cadence."
        />
      ) : (
        <div
          style={{
            background: 'linear-gradient(180deg,rgba(255,255,255,0.92),rgba(255,255,255,0.74))',
            backdropFilter: 'blur(16px) saturate(1.25)',
            border: '1px solid var(--border-1)',
            borderRadius: 14,
            boxShadow: 'var(--panel-shadow)',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: SCHEDULE_ROW_GRID_TEMPLATE,
              alignItems: 'center',
              gap: 14,
              padding: '11px 20px',
              background: 'var(--panel-2)',
            }}
          >
            <div style={columnHeaderLabelStyle}>Schedule</div>
            <div style={columnHeaderLabelStyle}>Cadence</div>
            <div style={columnHeaderLabelStyle}>Next run</div>
            <div style={columnHeaderLabelStyle}>Enabled</div>
            <div />
          </div>
          {schedules.map((schedule) => (
            <div
              key={schedule.id}
              style={{
                display: 'grid',
                gridTemplateColumns: SCHEDULE_ROW_GRID_TEMPLATE,
                alignItems: 'center',
                gap: 14,
                padding: '13px 20px',
                borderBottom: '1px solid var(--row-line)',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {schedule.name}
                </div>
                {schedule.created_by_name && (
                  <div className="caption" style={{ fontSize: 11.5, marginTop: 2 }}>
                    Created by {schedule.created_by_name}
                  </div>
                )}
              </div>
              <div style={{ fontSize: 12.5, color: 'var(--fg-3)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {schedule.cadence_label}
              </div>
              <div className="caption" style={{ fontSize: 12 }}>
                {schedule.next_run_at ? formatDateTime(schedule.next_run_at) : '—'}
              </div>
              <ToggleSwitch
                checked={schedule.enabled}
                disabled={pendingAction === schedule.id}
                onChange={() => handleToggle(schedule)}
              />
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
            </div>
          ))}
        </div>
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
