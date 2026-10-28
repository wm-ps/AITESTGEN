import { useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faArrowRight, faChevronDown, faImage, faLock, faMagnifyingGlass, faXmark } from '@fortawesome/free-solid-svg-icons'
import {
  ApiError,
  api,
  type ActivityCategory,
  type ActivityItemRead,
  type ActivityOutcome,
  type ActivityPageRead,
  type HomeApplicationRead,
  type TestResultArtifactRead,
  type TestResultRead,
  type TestRunRead,
  type UserRead,
} from '../api'
import { Pagination } from './Pagination'
import { SkeletonRows } from './Skeleton'

// Admin-only cross-application timeline (`GET /activity`, apps/api/src/api/activity.py),
// laid out per the Vantage v2 prototype's Activity screen: a filter bar of
// dropdowns with counts, a Time / Event / By / Result list grouped by day,
// and a side panel carrying the exact error.

const REFRESH_MS = 30_000
const MONO = 'var(--font-mono)'

const RESULT: Record<ActivityOutcome, { label: string; color: string; tint: string }> = {
  running: { label: 'Running', color: 'var(--accent-hi)', tint: 'rgba(15,118,110,0.10)' },
  done: { label: 'Done', color: 'var(--ok)', tint: 'rgba(13,138,100,0.10)' },
  failed: { label: 'Failed', color: 'var(--bad)', tint: 'rgba(201,48,73,0.08)' },
  changed: { label: 'Changed', color: 'var(--fg-3)', tint: 'var(--chip)' },
  stopped: { label: 'Stopped', color: 'var(--warn)', tint: 'rgba(217,119,6,0.10)' },
}

const CATEGORY_LABEL: Record<ActivityCategory, string> = {
  discovery: 'Exploration',
  scenarios: 'Scenarios',
  test_cases: 'Test cases',
  test_runs: 'Test runs',
  settings: 'Settings & team',
}

const TIME_OPTIONS = [
  { value: '24', label: 'Last 24 hours' },
  { value: String(24 * 7), label: 'Last 7 days' },
  { value: String(24 * 30), label: 'Last 30 days' },
  { value: String(24 * 90), label: 'Last 90 days' },
]

const FAILED_RESULT_STATUSES = new Set(['failed', 'timed_out', 'errored'])

type Filters = { since_hours: string; category: string; application_id: string; outcome: string; q: string }
const DEFAULT_FILTERS: Filters = { since_hours: String(24 * 7), category: '', application_id: '', outcome: '', q: '' }

const sectionLabelStyle: React.CSSProperties = {
  fontSize: 10.5,
  fontWeight: 600,
  letterSpacing: '0.07em',
  textTransform: 'uppercase',
  color: 'var(--fg-4)',
}

const secondaryButtonStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  height: 32,
  padding: '0 14px',
  borderRadius: 8,
  border: '1px solid var(--border-2)',
  background: 'var(--panel)',
  color: 'var(--fg-2)',
  fontSize: 12.5,
  fontWeight: 500,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  fontFamily: 'inherit',
}

const cardStyle: React.CSSProperties = {
  border: '1px solid var(--border)',
  borderRadius: 12,
  background: 'var(--panel)',
  boxShadow: 'var(--panel-shadow)',
}

const ROW_GRID = '64px minmax(240px,1fr) minmax(130px,180px) 96px'

function dayLabel(iso: string): string {
  const date = new Date(iso)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  if (date.toDateString() === today.toDateString()) return 'Today'
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return date.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' })
}

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })
}

function durationLabel(start: string | null, end: string | null): string | null {
  if (!start || !end) return null
  const seconds = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000)
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

// The API sends one display string; scheduled runs are prefixed "Schedule: ".
function actorParts(actor: string): { name: string; kind: string } {
  if (actor === 'System') return { name: 'Vantage', kind: 'System' }
  if (actor.startsWith('Schedule: ')) return { name: actor.slice('Schedule: '.length), kind: 'Schedule' }
  return { name: actor, kind: 'Person' }
}

function appLabel(item: ActivityItemRead): string {
  if (!item.application_name) return 'Workspace'
  return item.application_deleted ? `${item.application_name} (deleted)` : item.application_name
}

// One plain next step for the most common failures — never a guess at the
// cause, just where to look.
function suggestedNextStep(item: ActivityItemRead): string | null {
  if (item.outcome !== 'failed') return null
  const reason = `${item.reason ?? ''} ${item.details.failure_reason ?? ''}`.toLowerCase()
  if (/login|session|credential|unauthori[sz]ed|401/.test(reason)) {
    return "Check the application's saved login credentials, then try again."
  }
  if (item.kind === 'test_run') return 'Open the run to see each failure, or retry the failed tests with self-healing.'
  if (item.kind === 'discovery') return 'Confirm the application is reachable, then resume exploration.'
  if (item.category === 'scenarios') return 'Generate scenarios again from the Scenarios tab.'
  if (item.category === 'test_cases') return 'Generate test cases again from the Test cases tab.'
  return null
}

function ResultLabel({ outcome }: { outcome: ActivityOutcome }) {
  const r = RESULT[outcome]
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 20 }}>
      <span style={{ width: 7, height: 7, flex: 'none', borderRadius: 1000, background: r.color }} />
      <span style={{ fontSize: 12.5, fontWeight: 600, color: r.color }}>{r.label}</span>
    </span>
  )
}

export function Activity({
  user,
  onOpen,
  onBack,
}: {
  user: UserRead
  onOpen: (item: ActivityItemRead) => void
  onBack: () => void
}) {
  if (user.role !== 'admin') {
    return (
      <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%' }}>
        <div style={{ ...cardStyle, borderRadius: 14, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '64px 32px 56px' }}>
          <div style={{ width: 60, height: 60, borderRadius: 1000, background: 'var(--chip)', border: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 22 }}>
            <FontAwesomeIcon icon={faLock} style={{ fontSize: 20, color: 'var(--fg-3)' }} />
          </div>
          <div style={{ fontSize: 19, fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.015em' }}>No access</div>
          <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 9, maxWidth: 460, lineHeight: '21px' }}>
            Activity is only available to workspace admins. You're signed in as a {user.role}. Ask an admin if you need to see this page.
          </div>
          <button
            type="button"
            onClick={onBack}
            style={{ marginTop: 24, display: 'inline-flex', alignItems: 'center', height: 38, padding: '0 20px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: '#fff', fontSize: 13.5, fontWeight: 600, cursor: 'pointer', boxShadow: 'var(--accent-glow)', fontFamily: 'inherit' }}
          >
            Back to Overview
          </button>
          <div style={{ marginTop: 26, fontFamily: MONO, fontSize: 11, color: 'var(--fg-4)', padding: '4px 10px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--panel-2)' }}>
            403 Forbidden · GET /activity
          </div>
        </div>
      </div>
    )
  }
  return <ActivityFeed onOpen={onOpen} />
}

type FilterOption = { value: string; label: string; count?: number }

function FilterDropdown({
  label,
  value,
  options,
  defaultValue,
  open,
  onToggle,
  onPick,
}: {
  label: string
  value: string
  defaultValue: string
  options: FilterOption[]
  open: boolean
  onToggle: () => void
  onPick: (value: string) => void
}) {
  const current = options.find((o) => o.value === value) ?? options[0]
  const active = value !== defaultValue
  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${label}: ${current.label}`}
        onClick={onToggle}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          height: 32,
          padding: '0 11px',
          borderRadius: 8,
          border: `1px solid ${active ? 'var(--accent)' : 'var(--border-2)'}`,
          background: active ? 'rgba(15,118,110,0.06)' : 'var(--panel)',
          fontSize: 12.5,
          cursor: 'pointer',
          whiteSpace: 'nowrap',
          fontFamily: 'inherit',
        }}
      >
        <span style={{ color: 'var(--fg-4)' }}>{label}</span>
        <span style={{ fontWeight: 600, color: 'var(--fg-1)' }}>{current.label}</span>
        <FontAwesomeIcon icon={faChevronDown} style={{ fontSize: 8.5, color: 'var(--fg-4)', marginLeft: 2 }} />
      </button>
      {open && (
        <>
          <div onClick={onToggle} aria-hidden="true" style={{ position: 'fixed', inset: 0, zIndex: 30 }} />
          <div
            role="listbox"
            aria-label={label}
            style={{ position: 'absolute', top: 38, left: 0, zIndex: 31, minWidth: 230, maxHeight: 340, overflow: 'auto', padding: 5, borderRadius: 10, border: '1px solid var(--border-2)', background: 'var(--panel)', boxShadow: '0 14px 34px rgba(18,22,34,0.16)' }}
          >
            {options.map((o) => {
              const selected = o.value === value
              return (
                <button
                  key={o.value}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className="menu-item"
                  onClick={() => onPick(o.value)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 7,
                    border: 'none',
                    background: selected ? 'var(--hover)' : 'none',
                    fontSize: 13,
                    fontWeight: selected ? 600 : 400,
                    color: 'var(--fg-1)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontFamily: 'inherit',
                  }}
                >
                  <span style={{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{o.label}</span>
                  {o.count !== undefined && <span style={{ fontFamily: MONO, fontSize: 11, color: 'var(--fg-4)' }}>{o.count}</span>}
                </button>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function ActivityFeed({ onOpen }: { onOpen: (item: ActivityItemRead) => void }) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [searchDraft, setSearchDraft] = useState('')
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const [oldestFirst, setOldestFirst] = useState(false)
  // Cursor stack: cursors[i] is the cursor for page i (null = first page).
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [page, setPage] = useState(0)
  const [data, setData] = useState<ActivityPageRead | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [applications, setApplications] = useState<HomeApplicationRead[]>([])
  const [selected, setSelected] = useState<ActivityItemRead | null>(null)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    api.getHome().then(setApplications).catch(() => {
      // best-effort — the Application filter just lists none
    })
  }, [])

  useEffect(() => {
    const timeout = setTimeout(() => updateFilters({ q: searchDraft.trim() }), 300)
    return () => clearTimeout(timeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft])

  function resetPaging() {
    setCursors([null])
    setPage(0)
  }

  function updateFilters(patch: Partial<Filters>) {
    setFilters((current) => {
      const next = { ...current, ...patch }
      return JSON.stringify(next) === JSON.stringify(current) ? current : next
    })
    resetPaging()
  }

  const cursor = cursors[page] ?? null
  useEffect(() => {
    let cancelled = false
    function load() {
      setRefreshing(true)
      api
        .listActivity({
          application_id: filters.application_id || undefined,
          category: (filters.category || undefined) as ActivityCategory | undefined,
          outcome: (filters.outcome || undefined) as ActivityOutcome | undefined,
          q: filters.q || undefined,
          since_hours: Number(filters.since_hours),
          cursor: cursor ?? undefined,
          sort: oldestFirst ? 'oldest' : 'newest',
        })
        .then((result) => {
          if (cancelled) return
          setData(result)
          setError(null)
          setUpdatedAt(new Date())
          // Keep an open detail panel in step with the refreshed row.
          setSelected((current) => (current ? (result.items.find((i) => i.id === current.id) ?? current) : null))
        })
        .catch((err) => {
          if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load activity.')
        })
        .finally(() => {
          if (!cancelled) setRefreshing(false)
        })
    }
    setData(null)
    load()
    // Only the first page refreshes itself — later pages don't change.
    const interval = page === 0 ? setInterval(load, REFRESH_MS) : undefined
    return () => {
      cancelled = true
      if (interval) clearInterval(interval)
    }
  }, [filters, page, cursor, oldestFirst, reloadKey])

  function goNext() {
    if (!data?.next_cursor) return
    setCursors((c) => [...c.slice(0, page + 1), data.next_cursor])
    setPage((p) => p + 1)
  }

  function clearFilters() {
    setSearchDraft('')
    updateFilters({ category: '', application_id: '', outcome: '', q: '' })
  }

  const facets = data?.facets
  const dropdowns: { key: keyof Filters; label: string; options: FilterOption[] }[] = [
    { key: 'since_hours', label: 'Time', options: TIME_OPTIONS },
    {
      key: 'category',
      label: 'Type',
      options: [
        { value: '', label: 'All types', count: facets?.total.all },
        ...(Object.keys(CATEGORY_LABEL) as ActivityCategory[]).map((c) => ({ value: c, label: CATEGORY_LABEL[c], count: facets?.category[c] ?? 0 })),
      ],
    },
    {
      key: 'application_id',
      label: 'Application',
      options: [
        { value: '', label: 'All applications', count: facets?.total.all },
        ...applications.map((a) => ({ value: a.id, label: a.name, count: facets?.application[a.id] ?? 0 })),
      ],
    },
    {
      key: 'outcome',
      label: 'Result',
      options: [
        { value: '', label: 'All results', count: facets?.total.all },
        ...(Object.keys(RESULT) as ActivityOutcome[]).map((o) => ({ value: o, label: RESULT[o].label, count: facets?.outcome[o] ?? 0 })),
      ],
    },
  ]
  const filtered = Boolean(filters.category || filters.application_id || filters.outcome || filters.q)

  const groups: { day: string; items: ActivityItemRead[] }[] = []
  for (const item of data?.items ?? []) {
    const day = dayLabel(item.created_at)
    if (groups.at(-1)?.day !== day) groups.push({ day, items: [] })
    groups.at(-1)!.items.push(item)
  }
  const count = data?.items.length ?? 0

  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>Activity</h1>
          <div style={{ fontSize: 13.5, color: 'var(--fg-3)', marginTop: 4 }}>
            Every run, exploration, generation and settings change in this workspace, {oldestFirst ? 'oldest' : 'newest'} first.
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {updatedAt && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--fg-4)', whiteSpace: 'nowrap' }}>
              <span style={{ width: 6, height: 6, borderRadius: 1000, background: error ? 'var(--bad)' : 'var(--ok)' }} />
              Updated{' '}
              <span style={{ fontFamily: MONO, color: 'var(--fg-2)' }}>
                {updatedAt.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
              </span>{' '}
              · every 30 s
            </span>
          )}
          <button type="button" onClick={() => setReloadKey((k) => k + 1)} disabled={refreshing} style={secondaryButtonStyle}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      <div style={{ ...cardStyle, position: 'relative', zIndex: 3, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', padding: '10px 12px' }}>
        {dropdowns.map((d) => (
          <FilterDropdown
            key={d.key}
            label={d.label}
            value={filters[d.key]}
            defaultValue={DEFAULT_FILTERS[d.key]}
            options={d.options}
            open={openMenu === d.key}
            onToggle={() => setOpenMenu((m) => (m === d.key ? null : d.key))}
            onPick={(value) => {
              setOpenMenu(null)
              updateFilters({ [d.key]: value })
            }}
          />
        ))}
        <div style={{ position: 'relative', width: 290, maxWidth: '100%' }}>
          <FontAwesomeIcon
            icon={faMagnifyingGlass}
            style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 11.5, color: 'var(--fg-5)', pointerEvents: 'none' }}
          />
          <input
            type="text"
            aria-label="Search activity"
            placeholder="Search by application, person or event"
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            style={{ width: '100%', height: 32, boxSizing: 'border-box', padding: '0 10px 0 30px', borderRadius: 8, border: '1px solid var(--border-2)', background: 'var(--panel)', fontSize: 12.5, fontFamily: 'inherit', color: 'var(--fg-1)' }}
          />
        </div>
        {filtered && (
          <button
            type="button"
            onClick={clearFilters}
            style={{ height: 32, padding: '0 10px', borderRadius: 8, border: 'none', background: 'none', fontSize: 12.5, fontWeight: 500, color: 'var(--accent-hi)', cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}
          >
            Clear all
          </button>
        )}
        <div style={{ flex: 1 }} />
        <div style={{ fontSize: 12, color: 'var(--fg-4)', whiteSpace: 'nowrap', paddingRight: 4 }}>
          {data ? `${count} ${count === 1 ? 'event' : 'events'}${page > 0 ? ` · page ${page + 1}` : ''}` : ''}
        </div>
      </div>

      <div style={{ ...cardStyle, overflow: 'hidden' }}>
        <div role="row" style={{ display: 'grid', gridTemplateColumns: ROW_GRID, gap: 16, padding: '10px 20px', background: 'var(--panel-2)', borderBottom: '1px solid var(--border)' }}>
          <button
            type="button"
            role="columnheader"
            aria-sort={oldestFirst ? 'ascending' : 'descending'}
            title={oldestFirst ? 'Showing oldest first — click for newest first' : 'Showing newest first — click for oldest first'}
            onClick={() => {
              setOldestFirst((v) => !v)
              resetPaging()
            }}
            style={{ ...sectionLabelStyle, display: 'inline-flex', alignItems: 'center', gap: 5, padding: 0, border: 'none', background: 'none', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
          >
            Time
            <FontAwesomeIcon icon={faChevronDown} style={{ fontSize: 8, transform: oldestFirst ? 'rotate(180deg)' : undefined }} />
          </button>
          <div role="columnheader" style={sectionLabelStyle}>
            Event
          </div>
          <div role="columnheader" style={sectionLabelStyle}>
            By
          </div>
          <div role="columnheader" style={sectionLabelStyle}>
            Result
          </div>
        </div>

        {error && (
          <div role="alert" style={{ padding: '12px 20px', color: 'var(--bad)', fontSize: 13, borderBottom: '1px solid var(--row-line)' }}>
            {error}
          </div>
        )}

        {data === null && !error ? (
          <div style={{ padding: 20 }}>
            <SkeletonRows count={6} height={36} gap={12} />
          </div>
        ) : data && data.items.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '52px 24px' }}>
            <div style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--fg-1)' }}>
              {filtered ? 'No activity matches these filters' : 'Nothing has happened in this time range'}
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 6 }}>
              {filtered ? 'Try a wider time range or clear the filters.' : 'Try a wider time range. New activity appears here as it happens.'}
            </div>
            {filtered && (
              <button type="button" onClick={clearFilters} style={{ ...secondaryButtonStyle, marginTop: 18 }}>
                Clear filters
              </button>
            )}
          </div>
        ) : (
          groups.map((group) => (
            <div key={group.day}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '8px 20px', background: 'var(--panel-2)', borderBottom: '1px solid var(--row-line)' }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)' }}>{group.day}</span>
                <span style={{ fontSize: 11.5, color: 'var(--fg-4)' }}>
                  {group.items.length} {group.items.length === 1 ? 'event' : 'events'}
                </span>
              </div>
              {group.items.map((item) => (
                <ActivityRow key={item.id} item={item} selected={selected?.id === item.id} onSelect={() => setSelected(item)} />
              ))}
            </div>
          ))
        )}

        <Pagination page={page} hasPrev={page > 0} hasNext={Boolean(data?.next_cursor)} onPrev={() => setPage((p) => Math.max(0, p - 1))} onNext={goNext} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 20px', borderTop: '1px solid var(--border)', background: 'var(--panel-2)', flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>{data ? `Showing ${count} ${count === 1 ? 'event' : 'events'}` : ''}</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 12, color: 'var(--fg-4)' }}>History is kept for 90 days, then removed automatically.</span>
        </div>
      </div>

      {selected && <ActivityDetail item={selected} onClose={() => setSelected(null)} onOpen={onOpen} />}
    </div>
  )
}

function ActivityRow({ item, selected, onSelect }: { item: ActivityItemRead; selected: boolean; onSelect: () => void }) {
  const actor = actorParts(item.actor)
  return (
    <div
      role="row"
      tabIndex={0}
      aria-selected={selected}
      className="v2-table-row"
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
      style={{
        display: 'grid',
        gridTemplateColumns: ROW_GRID,
        gap: 16,
        alignItems: 'start',
        padding: '12px 20px',
        borderBottom: '1px solid var(--row-line)',
        cursor: 'pointer',
        background: selected ? 'var(--hover)' : undefined,
        boxShadow: selected ? 'inset 3px 0 0 var(--accent)' : undefined,
      }}
    >
      <div style={{ fontFamily: MONO, fontSize: 12, lineHeight: '20px', color: 'var(--fg-3)' }}>{timeLabel(item.created_at)}</div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13.5, lineHeight: '20px', fontWeight: 500, color: 'var(--fg-1)' }}>{item.summary}</div>
        <div style={{ fontSize: 12, lineHeight: '18px', color: 'var(--fg-4)', marginTop: 1 }}>
          {CATEGORY_LABEL[item.category]} · {appLabel(item)}
        </div>
        {item.reason && (
          <div style={{ fontSize: 12, lineHeight: '18px', color: item.outcome === 'failed' ? 'var(--bad)' : 'var(--fg-4)', marginTop: 2 }}>{item.reason}</div>
        )}
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 12.5, lineHeight: '20px', color: 'var(--fg-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{actor.name}</div>
        <div style={{ fontSize: 12, lineHeight: '18px', color: 'var(--fg-4)', marginTop: 1 }}>{actor.kind}</div>
      </div>
      <ResultLabel outcome={item.outcome} />
    </div>
  )
}

function ActivityDetail({ item, onClose, onOpen }: { item: ActivityItemRead; onClose: () => void; onOpen: (item: ActivityItemRead) => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const result = RESULT[item.outcome]
  const actor = actorParts(item.actor)
  const nextStep = suggestedNextStep(item)
  const canOpen = item.application_id && !item.application_deleted && item.target_tab
  const when = `${dayLabel(item.created_at)}, ${timeLabel(item.created_at)}`

  return (
    <>
      <div onClick={onClose} aria-hidden="true" style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(14,16,24,0.34)' }} />
      <aside
        role="dialog"
        aria-label="Activity details"
        style={{ position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 61, width: 'min(660px, 100vw)', background: 'var(--panel)', borderLeft: '1px solid var(--border)', boxShadow: '-28px 0 56px rgba(18,22,34,0.20)', display: 'flex', flexDirection: 'column' }}
      >
        <div style={{ flex: 'none', padding: '18px 22px 16px', borderBottom: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 600, padding: '3px 9px', borderRadius: 6, background: result.tint, color: result.color }}>
              <span style={{ width: 6, height: 6, borderRadius: 1000, background: result.color }} />
              {result.label}
            </span>
            <span style={{ fontSize: 12, color: 'var(--fg-4)' }}>{CATEGORY_LABEL[item.category]}</span>
            <div style={{ flex: 1 }} />
            <button
              type="button"
              aria-label="Close"
              title="Close"
              onClick={onClose}
              className="menu-item"
              style={{ width: 30, height: 30, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', border: 'none', background: 'none', cursor: 'pointer', color: 'var(--fg-3)' }}
            >
              <FontAwesomeIcon icon={faXmark} style={{ fontSize: 14 }} />
            </button>
          </div>
          <div style={{ fontSize: 17, lineHeight: '24px', fontWeight: 600, color: 'var(--fg)', letterSpacing: '-0.012em' }}>{item.summary}</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,minmax(0,1fr))', gap: 12 }}>
            <Meta label="By" value={`${actor.name} · ${actor.kind}`} />
            <Meta label="When" value={when} />
            <Meta label="Application" value={appLabel(item)} />
          </div>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '20px 22px 28px', display: 'grid', gridAutoRows: 'max-content', alignContent: 'start', gap: 20 }}>
          <div style={{ border: '1px solid var(--border)', borderRadius: 10, background: 'var(--panel-2)', overflow: 'hidden' }}>
            <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={sectionLabelStyle}>What happened</div>
              <div style={{ fontSize: 13.5, lineHeight: '21px', color: 'var(--fg-1)' }}>
                {item.summary}
                {item.reason ? `. ${item.reason}.` : '.'}
              </div>
            </div>
            {nextStep && (
              <div style={{ padding: '13px 16px', borderTop: '1px solid var(--border)', background: 'rgba(15,118,110,0.05)', display: 'flex', flexDirection: 'column', gap: 3 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent-hi)' }}>Suggested next step</div>
                <div style={{ fontSize: 13, lineHeight: '20px', color: 'var(--fg-2)' }}>{nextStep}</div>
              </div>
            )}
          </div>

          {item.kind === 'test_run' && item.application_id && item.test_run_id && !item.application_deleted && (
            <TestRunDetail applicationId={item.application_id} testRunId={item.test_run_id} running={item.outcome === 'running'} />
          )}
          {item.kind === 'discovery' && <DiscoveryDetail item={item} />}
          {item.details.journeys && item.details.journeys.length > 0 && <JourneyItems journeys={item.details.journeys} />}
          {item.details.changes && item.details.changes.length > 0 && <ChangesTable changes={item.details.changes} />}
        </div>

        {(canOpen || item.application_deleted) && (
          <div style={{ flex: 'none', padding: '14px 22px', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10, background: 'var(--panel-2)' }}>
            {canOpen ? (
              <button
                type="button"
                onClick={() => onOpen(item)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 36, padding: '0 16px', borderRadius: 8, background: 'var(--accent)', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer', border: 'none', fontFamily: 'inherit', boxShadow: 'var(--accent-glow)' }}
              >
                {item.kind === 'test_run' ? 'Open run' : 'Open application'}
                <FontAwesomeIcon icon={faArrowRight} style={{ fontSize: 11 }} />
              </button>
            ) : (
              <span style={{ fontSize: 12.5, color: 'var(--fg-4)' }}>This application was deleted.</span>
            )}
          </div>
        )}
      </aside>
    </>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 11, color: 'var(--fg-4)' }}>{label}</div>
      <div style={{ fontSize: 12.5, color: 'var(--fg-1)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={value}>
        {value}
      </div>
    </div>
  )
}

function Facts({ facts }: { facts: { k: string; v: string }[] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
      {facts.map((f) => (
        <div key={f.k} style={{ padding: '11px 14px', borderRight: '1px solid var(--row-line)', display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
          <div style={{ fontSize: 11, color: 'var(--fg-4)' }}>{f.k}</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg-1)', overflowWrap: 'anywhere' }}>
            {f.v}
          </div>
        </div>
      ))}
    </div>
  )
}

function ErrorBlock({ title, text }: { title: string; text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div style={{ borderRadius: 8, background: 'var(--code-bg)', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 8px 8px 14px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
        <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: '#8992A6' }}>{title}</span>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard?.writeText(text)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          }}
          style={{ display: 'inline-flex', alignItems: 'center', height: 26, padding: '0 10px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(255,255,255,0.04)', color: '#E6EAF2', fontSize: 11.5, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}
        >
          {copied ? 'Copied' : 'Copy error'}
        </button>
      </div>
      <pre style={{ margin: 0, padding: '12px 14px', fontFamily: MONO, fontSize: 11.5, lineHeight: '18px', color: '#FFC2CB', whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 240, overflow: 'auto' }}>{text}</pre>
    </div>
  )
}

function TestRunDetail({ applicationId, testRunId, running }: { applicationId: string; testRunId: string; running: boolean }) {
  const [run, setRun] = useState<TestRunRead | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setRun(null)
    api
      .getTestRun(applicationId, testRunId)
      .then(setRun)
      .catch(() => setError("This run's details couldn't be loaded."))
  }, [applicationId, testRunId])

  if (error) return <div style={{ fontSize: 13, color: 'var(--bad)' }}>{error}</div>
  if (!run) return <SkeletonRows count={3} height={28} gap={10} />

  const results = run.results ?? []
  const failures = results.filter((r) => FAILED_RESULT_STATUSES.has(r.status))
  const finished = results.filter((r) => r.status !== 'pending').length
  const total = run.total_count || results.length
  const pct = total ? Math.round((finished / total) * 100) : 0
  const duration = durationLabel(run.started_at, run.completed_at)
  return (
    <>
      {running && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--fg-2)' }}>
            <span style={{ flex: 1 }}>
              {finished} of {total} tests finished
            </span>
            <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 600, color: 'var(--accent-hi)' }}>{pct}%</span>
          </div>
          <div style={{ height: 6, borderRadius: 1000, background: 'var(--track)', overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', borderRadius: 1000, background: 'var(--accent)' }} />
          </div>
        </div>
      )}
      <Facts
        facts={[
          { k: 'Passed', v: String(run.passed_count) },
          { k: 'Failed', v: String(run.failed_count + run.timed_out_count + run.errored_count) },
          ...(run.blocked_count ? [{ k: 'Skipped', v: String(run.blocked_count) }] : []),
          { k: 'Duration', v: duration ?? '—' },
        ]}
      />
      {run.blocked_reason && <ErrorBlock title="Why it could not run" text={run.blocked_reason} />}
      {failures.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={sectionLabelStyle}>Failed tests ({failures.length})</div>
          {failures.map((result, index) => (
            <FailedResult key={result.id} result={result} defaultOpen={index === 0} />
          ))}
        </div>
      )}
    </>
  )
}

function FailedResult({ result, defaultOpen }: { result: TestResultRead; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const [tab, setTab] = useState<'screenshot' | 'trace'>('screenshot')
  const [artifacts, setArtifacts] = useState<TestResultArtifactRead[] | null>(null)
  const requested = useRef(false)

  useEffect(() => {
    if (!open || requested.current) return
    requested.current = true
    api
      .listTestResultArtifacts(result.id)
      .then(setArtifacts)
      .catch(() => setArtifacts([]))
  }, [open, result.id])

  const title = `${result.test_case_number != null ? `TC-${result.test_case_number} · ` : ''}${result.scenario_name}`
  const screenshot = artifacts?.find((a) => a.artifact_type === 'screenshot')
  const tabs: { key: 'screenshot' | 'trace'; label: string }[] = [
    { key: 'screenshot', label: 'Screenshot' },
    ...(result.stack_trace ? [{ key: 'trace' as const, label: 'Full trace' }] : []),
  ]
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden', background: 'var(--panel)' }}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="v2-table-row"
        style={{ display: 'flex', alignItems: 'center', gap: 11, width: '100%', padding: '12px 14px', border: 'none', background: 'none', cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit' }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)' }}>{title}</div>
          <div style={{ fontFamily: MONO, fontSize: 11, color: 'var(--fg-4)', marginTop: 2 }}>{result.journey_name}</div>
        </div>
        <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--bad)' }}>{result.status === 'timed_out' ? 'Timed out' : result.status === 'errored' ? 'Errored' : 'Failed'}</span>
        <FontAwesomeIcon icon={faChevronDown} style={{ fontSize: 10, color: 'var(--fg-4)', transform: open ? 'rotate(180deg)' : undefined, transition: 'transform 0.15s' }} />
      </button>
      {open && (
        <div style={{ padding: '2px 14px 14px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <ErrorBlock title="Exact error" text={result.error_message || 'No error message was recorded for this test.'} />
          <div style={{ display: 'flex', gap: 3, padding: 3, borderRadius: 8, background: 'var(--chip)', border: '1px solid var(--border)', width: 'fit-content', maxWidth: '100%', flexWrap: 'wrap' }}>
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                aria-pressed={tab === t.key}
                onClick={() => setTab(t.key)}
                style={{ height: 26, padding: '0 12px', borderRadius: 6, border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 12, fontWeight: tab === t.key ? 600 : 500, background: tab === t.key ? 'var(--panel)' : 'none', color: tab === t.key ? 'var(--fg-1)' : 'var(--fg-3)', boxShadow: tab === t.key ? '0 1px 2px rgba(0,0,0,0.08)' : undefined }}
              >
                {t.label}
              </button>
            ))}
          </div>
          {tab === 'screenshot' &&
            (screenshot ? (
              <a href={screenshot.url} target="_blank" rel="noreferrer" title="Open full size">
                <img src={screenshot.url} alt={`Screenshot when ${result.scenario_name} failed`} style={{ display: 'block', width: '100%', borderRadius: 8, border: '1px solid var(--border)' }} />
              </a>
            ) : (
              <div style={{ aspectRatio: '16 / 9', border: '1px dashed var(--border-2)', borderRadius: 8, background: 'var(--panel-2)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <FontAwesomeIcon icon={faImage} style={{ fontSize: 22, color: 'var(--fg-5)' }} />
                <span style={{ fontSize: 11.5, color: 'var(--fg-4)' }}>
                  {artifacts === null ? 'Loading screenshot…' : 'No screenshot was captured for this failure'}
                </span>
              </div>
            ))}
          {tab === 'trace' && result.stack_trace && <ErrorBlock title="Full trace" text={result.stack_trace} />}
        </div>
      )}
    </div>
  )
}

function DiscoveryDetail({ item }: { item: ActivityItemRead }) {
  const { pages, journeys_found, stop_reason, failure_reason, errors } = item.details
  return (
    <>
      <Facts
        facts={[
          { k: 'Pages found', v: String(pages ?? 0) },
          { k: 'Journeys found', v: String(journeys_found ?? 0) },
          ...(stop_reason ? [{ k: 'Stopped because', v: stop_reason }] : []),
        ]}
      />
      {failure_reason && <ErrorBlock title="Exact error" text={failure_reason} />}
      {errors && errors.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={sectionLabelStyle}>Errors during exploration ({errors.length})</div>
          <ErrorBlock title="Error log" text={errors.map((e) => `${e.code}: ${e.message}`).join('\n')} />
        </div>
      )}
    </>
  )
}

function JourneyItems({ journeys }: { journeys: NonNullable<ActivityItemRead['details']['journeys']> }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={sectionLabelStyle}>Journeys ({journeys.length})</div>
      <div style={{ border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        {journeys.map((j, i) => (
          <div key={i} style={{ padding: '11px 14px', borderBottom: i < journeys.length - 1 ? '1px solid var(--row-line)' : undefined, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ flex: 1, minWidth: 0, fontSize: 13, color: 'var(--fg-1)' }}>{j.name}</span>
              <ResultLabel outcome={j.status} />
            </div>
            {j.error && <ErrorBlock title="Exact error" text={j.error} />}
          </div>
        ))}
      </div>
    </div>
  )
}

function ChangesTable({ changes }: { changes: NonNullable<ActivityItemRead['details']['changes']> }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={sectionLabelStyle}>What changed</div>
      <div style={{ border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ display: 'flex', gap: 12, padding: '9px 14px', background: 'var(--panel-2)', borderBottom: '1px solid var(--border)' }}>
          <div style={{ ...sectionLabelStyle, width: '30%', flex: 'none' }}>Setting</div>
          <div style={{ ...sectionLabelStyle, flex: 1 }}>Before</div>
          <div style={{ ...sectionLabelStyle, flex: 1 }}>After</div>
        </div>
        {changes.map((c) => (
          <div key={c.field} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '11px 14px', borderBottom: '1px solid var(--row-line)' }}>
            <div style={{ width: '30%', flex: 'none', fontSize: 12.5, fontWeight: 500, color: 'var(--fg-1)', paddingTop: 3 }}>{c.field}</div>
            <div style={{ flex: 1, minHeight: 26, padding: '3px 10px', borderRadius: 6, background: 'rgba(201,48,73,0.06)', fontFamily: MONO, fontSize: 12, color: 'var(--fg-3)', textDecoration: 'line-through', wordBreak: 'break-word' }}>{c.before}</div>
            <div style={{ flex: 1, minHeight: 26, padding: '3px 10px', borderRadius: 6, background: 'rgba(13,138,100,0.08)', fontFamily: MONO, fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', wordBreak: 'break-word' }}>{c.after}</div>
          </div>
        ))}
      </div>
      <div style={{ fontSize: 12, color: 'var(--fg-4)' }}>Passwords, tokens and other credentials are never shown here.</div>
    </div>
  )
}
