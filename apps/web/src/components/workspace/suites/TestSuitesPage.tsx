import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCircleInfo, faEllipsisVertical, faMagnifyingGlass, faPlus } from '@fortawesome/free-solid-svg-icons'
import {
  ApiError,
  api,
  type CollectionDetail,
  type CollectionRunRead,
  type CollectionSummary,
} from '../../../api'
import { useCanEdit } from '../../../PermissionsContext'
import { AnchoredMenu } from '../../AnchoredMenu'
import { LoadingDots } from '../../LoadingDots'
import { SkeletonRows } from '../../Skeleton'
import { StatusPill } from '../../StatusPill'
import { relativeTime } from '../../Home'
import { ChevronIcon } from '../TestSuiteTab'
import { DeleteSuiteDialog } from './DeleteSuiteDialog'
import { SelectTestCasesDialog } from './SelectTestCasesDialog'
import { SuiteNameDialog } from './SuiteNameDialog'
import { plural } from './SuiteModal'

const card = {
  background: 'var(--panel)',
  border: '1px solid var(--border-1)',
  borderRadius: 14,
  boxShadow: 'var(--panel-shadow)',
} as const

type Dialog = 'new' | 'rename' | 'delete' | 'manage' | null
type Tab = 'runs' | 'cases'

// Amber (i) beside a suite's name when some of its test cases no longer exist;
// hovering or focusing it says how many. Quieter than a badge on every row.
function UnavailableInfo({ count }: { count: number }) {
  const [open, setOpen] = useState(false)
  if (count <= 0) return null
  return (
    <span
      tabIndex={0}
      role="img"
      aria-label={`${count} unavailable`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      style={{ position: 'relative', display: 'inline-flex', marginLeft: 8, color: 'var(--warn-strong)', outline: 'none' }}
    >
      <FontAwesomeIcon icon={faCircleInfo} style={{ fontSize: 15 }} />
      {open && (
        <span
          role="tooltip"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: -4,
            zIndex: 20,
            padding: '6px 12px',
            borderRadius: 8,
            border: '1px solid var(--border-2)',
            background: 'var(--panel)',
            boxShadow: 'var(--panel-shadow)',
            color: 'var(--fg)',
            fontSize: 13,
            fontWeight: 500,
            whiteSpace: 'nowrap',
          }}
        >
          {count} unavailable
        </span>
      )}
    </span>
  )
}

// "1 of 4 failed" / "4 of 4 passed"; a run still in motion shows a pulsing
// status instead of a result.
function RunResult({ run }: { run: CollectionRunRead }) {
  if (run.status === 'pending' || run.status === 'running') {
    return <StatusPill status="running" label="Running" pulsing />
  }
  if (run.status === 'cancelled') return <StatusPill status="cancelled" />
  if (run.total === 0) return null
  const failed = run.failed > 0
  const allPassed = run.passed === run.total
  const tone = failed
    ? { background: 'var(--danger-wash)', color: 'var(--danger-strong)' }
    : allPassed
      ? { background: 'var(--good-wash)', color: 'var(--good-strong)' }
      : { background: 'var(--warn-wash)', color: 'var(--warn-strong)' }
  return (
    <span
      style={{ ...tone, fontSize: 12, fontWeight: 600, padding: '3px 10px', borderRadius: 6, whiteSpace: 'nowrap' }}
    >
      {failed ? `${run.failed} of ${run.total} failed` : `${run.passed} of ${run.total} passed`}
    </span>
  )
}

const removeLink = {
  background: 'none',
  border: 'none',
  padding: '2px 4px',
  cursor: 'pointer',
  fontSize: 13,
  fontFamily: 'inherit',
  color: 'var(--fg-3)',
} as const

export function TestSuitesPage({ applicationId }: { applicationId: string }) {
  const canEdit = useCanEdit()
  const [suites, setSuites] = useState<CollectionSummary[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<CollectionDetail | null>(null)
  const [dialog, setDialog] = useState<Dialog>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const [tab, setTab] = useState<Tab>('runs')
  const [caseSearch, setCaseSearch] = useState('')
  const [journeyFilter, setJourneyFilter] = useState('')
  // Journeys the user has opened; the first one is open until they pick.
  const [expanded, setExpanded] = useState<Set<string> | null>(null)
  // 'all' while Remove all runs, or the scenario id of the row being removed.
  const [removing, setRemoving] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const loadSuites = useCallback(
    async (preferId?: string | null) => {
      try {
        const data = await api.listCollections(applicationId)
        setSuites(data)
        setLoadError(null)
        setSelectedId((current) => {
          const wanted = preferId ?? current
          return data.some((s) => s.id === wanted) ? wanted : (data[0]?.id ?? null)
        })
      } catch (err) {
        setLoadError(err instanceof ApiError ? err.message : 'Could not load test suites.')
      }
    },
    [applicationId],
  )

  useEffect(() => {
    void loadSuites()
  }, [loadSuites])

  const loadDetail = useCallback(async (id: string) => {
    try {
      setDetail(await api.getCollection(id))
    } catch {
      setDetail(null)
    }
  }, [])

  useEffect(() => {
    setTab('runs')
    setCaseSearch('')
    setJourneyFilter('')
    setExpanded(null)
    setActionError(null)
    if (selectedId === null) {
      setDetail(null)
      return
    }
    void loadDetail(selectedId)
  }, [selectedId, loadDetail])

  async function refresh() {
    await loadSuites()
    if (selectedId) await loadDetail(selectedId)
  }

  async function removeMembers(ids: string[], key: string) {
    if (!selectedId || removing) return
    setRemoving(key)
    setActionError(null)
    try {
      await api.changeCollectionMembers(selectedId, { remove: ids })
      await refresh()
    } catch {
      setActionError('Could not remove the test cases. Try again.')
    } finally {
      setRemoving(null)
    }
  }

  const selected = suites?.find((s) => s.id === selectedId) ?? null
  const loading = suites === null && !loadError

  const query = caseSearch.trim().toLowerCase()
  const groups = useMemo(() => {
    const byJourney = new Map<string, { name: string; cases: CollectionDetail['available'] }>()
    for (const member of detail?.available ?? []) {
      const group = byJourney.get(member.journey_name ?? '') ?? { name: member.journey_name ?? '', cases: [] }
      group.cases.push(member)
      byJourney.set(group.name, group)
    }
    return [...byJourney.values()].sort((a, b) => a.name.localeCompare(b.name))
  }, [detail])
  const visibleGroups = groups
    .filter((g) => !journeyFilter || g.name === journeyFilter)
    .map((g) => ({ ...g, cases: query ? g.cases.filter((c) => c.name.toLowerCase().includes(query)) : g.cases }))
    .filter((g) => g.cases.length > 0)
  const isOpen = (name: string, index: number) =>
    query ? true : expanded === null ? index === 0 : expanded.has(name)

  function toggleGroup(name: string, index: number) {
    const next = new Set(
      expanded ?? (visibleGroups[0] ? [visibleGroups[0].name] : []),
    )
    if (isOpen(name, index)) next.delete(name)
    else next.add(name)
    setExpanded(next)
  }

  const tabButton = (key: Tab, label: string, count: number) => (
    <button
      type="button"
      role="tab"
      aria-selected={tab === key}
      onClick={() => setTab(key)}
      style={{
        background: 'none',
        border: 'none',
        borderBottom: `2px solid ${tab === key ? 'var(--accent)' : 'transparent'}`,
        padding: '12px 4px',
        marginRight: 24,
        marginBottom: -1,
        cursor: 'pointer',
        fontFamily: 'inherit',
        fontSize: 14.5,
        fontWeight: tab === key ? 700 : 500,
        color: tab === key ? 'var(--fg)' : 'var(--fg-3)',
      }}
    >
      {label} ({count})
    </button>
  )

  return (
    <div style={{ maxWidth: 1560, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
        <h1 style={{ fontSize: 20, lineHeight: '26px', color: 'var(--fg)', letterSpacing: '-0.02em', fontWeight: 600, margin: 0 }}>
          Test suites
        </h1>
        {canEdit && (
          <button
            type="button"
            className="button-primary"
            onClick={() => setDialog('new')}
            style={{ padding: '10px 18px', fontSize: 14, display: 'inline-flex', alignItems: 'center', gap: 8, flex: 'none' }}
          >
            <FontAwesomeIcon icon={faPlus} size="xs" />
            New suite
          </button>
        )}
      </div>

      {loadError && (
        <div role="alert" style={{ color: 'var(--danger)', fontSize: 13.5 }}>{loadError}</div>
      )}

      {loading ? (
        <SkeletonRows count={4} height={64} gap={10} />
      ) : suites && suites.length === 0 ? (
        <div style={{ ...card, padding: '48px 24px', textAlign: 'center' }}>
          <p style={{ margin: 0, fontSize: 14.5, fontWeight: 600, color: 'var(--fg)' }}>No test suites yet</p>
          <p className="caption" style={{ margin: '6px 0 0', fontSize: 13 }}>
            {canEdit ? 'Create a suite, then add the test cases it should run.' : 'Suites created by your team will appear here.'}
          </p>
        </div>
      ) : (
        suites && (
          <div style={{ display: 'flex', gap: 20, alignItems: 'stretch', flexWrap: 'wrap' }}>
            <div style={{ ...card, flex: '1 1 300px', maxWidth: 400, padding: 16 }}>
              <div style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-2)', margin: '2px 4px 12px' }}>
                {suites.length} {suites.length === 1 ? 'Suite' : 'Suites'}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {suites.map((suite) => {
                  const on = suite.id === selectedId
                  return (
                    <button
                      key={suite.id}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setSelectedId(suite.id)}
                      style={{
                        display: 'block',
                        width: '100%',
                        padding: '12px 14px',
                        borderRadius: 10,
                        border: `1px solid ${on ? 'var(--accent)' : 'transparent'}`,
                        background: on ? 'var(--accent-wash)' : 'transparent',
                        cursor: 'pointer',
                        textAlign: 'left',
                        fontFamily: 'inherit',
                      }}
                    >
                      <span style={{ display: 'flex', alignItems: 'center' }}>
                        <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg)' }}>{suite.name}</span>
                        <UnavailableInfo count={suite.unavailable_count} />
                      </span>
                      <span className="caption" style={{ display: 'block', fontSize: 12.5, marginTop: 2 }}>
                        {plural(suite.test_case_count, 'test case')} · {plural(suite.run_count, 'run')}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            {selected && (
              <div style={{ flex: '2 1 480px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div style={{ ...card, padding: '18px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                  <div style={{ minWidth: 0 }}>
                    <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: 'var(--fg)' }}>{selected.name}</h2>
                    <p className="caption" style={{ margin: '4px 0 0', fontSize: 13 }}>
                      {detail
                        ? `${plural(detail.test_case_count, 'test case')} across ${plural(detail.journey_count, 'journey')}${
                            detail.unavailable.length > 0 ? ` · ${detail.unavailable.length} unavailable` : ''
                          }`
                        : ' '}
                    </p>
                  </div>
                  {canEdit && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 'none', position: 'relative' }}>
                      <button
                        type="button"
                        className="button-secondary"
                        onClick={() => setDialog('manage')}
                        style={{ padding: '9px 16px', fontSize: 13.5 }}
                      >
                        Manage test cases
                      </button>
                      <button
                        ref={menuButtonRef}
                        type="button"
                        className="button-secondary"
                        title="More options"
                        aria-label="More options"
                        aria-haspopup="menu"
                        aria-expanded={menuOpen}
                        onClick={() => setMenuOpen((v) => !v)}
                        style={{ width: 38, height: 38, padding: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
                      >
                        <FontAwesomeIcon icon={faEllipsisVertical} style={{ fontSize: 16 }} />
                      </button>
                      <AnchoredMenu anchorRef={menuButtonRef} open={menuOpen} onClose={() => setMenuOpen(false)}>
                          <div
                            role="menu"
                            style={{
                              minWidth: 150,
                              padding: 4,
                              background: 'var(--panel)',
                              border: '1px solid var(--border-2)',
                              borderRadius: 10,
                              boxShadow: 'var(--panel-shadow)',
                            }}
                          >
                            {(
                              [
                                ['Rename', 'rename', 'var(--fg-1)'],
                                ['Delete', 'delete', 'var(--danger)'],
                              ] as const
                            ).map(([label, target, color]) => (
                              <button
                                key={target}
                                type="button"
                                role="menuitem"
                                onClick={() => {
                                  setMenuOpen(false)
                                  setDialog(target)
                                }}
                                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '9px 12px', fontSize: 13, border: 'none', background: 'none', color, cursor: 'pointer', borderRadius: 6 }}
                              >
                                {label}
                              </button>
                            ))}
                          </div>
                      </AnchoredMenu>
                    </div>
                  )}
                </div>

                {actionError && (
                  <div role="alert" style={{ color: 'var(--danger)', fontSize: 13 }}>{actionError}</div>
                )}

                <div style={{ ...card, flex: 1, padding: '0 20px 20px' }}>
                  <div role="tablist" style={{ display: 'flex', borderBottom: '1px solid var(--line)', marginBottom: 18 }}>
                    {tabButton('runs', 'Run history', detail?.run_count ?? selected.run_count)}
                    {tabButton('cases', 'Test cases', detail?.test_case_count ?? selected.test_case_count)}
                  </div>

                  {tab === 'runs' && (
                    <>
                      {detail && detail.recent_runs.length === 0 ? (
                        <p className="caption" style={{ margin: 0, fontSize: 13 }}>
                          This suite has not been run yet.
                        </p>
                      ) : (
                        detail && (
                          <div style={{ border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
                            {detail.recent_runs.map((run, index) => (
                              <div
                                key={run.id}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 24,
                                  padding: '16px 28px',
                                  borderTop: index === 0 ? undefined : '1px solid var(--line)',
                                }}
                              >
                                <span style={{ fontSize: 14.5, fontWeight: 700, color: 'var(--fg)', width: 64 }}>
                                  Run {run.run_number}
                                </span>
                                <span style={{ flex: 1, fontSize: 14.5, color: 'var(--fg-2)' }}>
                                  {relativeTime(run.created_at)}
                                </span>
                                <RunResult run={run} />
                              </div>
                            ))}
                          </div>
                        )
                      )}
                      {detail && detail.run_count > detail.recent_runs.length && (
                        <p className="caption" style={{ margin: '10px 0 0', fontSize: 12.5 }}>
                          Showing the latest {detail.recent_runs.length} of {detail.run_count} runs.
                        </p>
                      )}
                    </>
                  )}

                  {tab === 'cases' && detail && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        <div style={{ position: 'relative', flex: '1 1 280px', maxWidth: 520 }}>
                          <FontAwesomeIcon
                            icon={faMagnifyingGlass}
                            style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--fg-3)', fontSize: 13 }}
                          />
                          <input
                            type="text"
                            aria-label="Search test cases in this suite"
                            placeholder="Search test cases in this suite"
                            value={caseSearch}
                            onChange={(e) => setCaseSearch(e.target.value)}
                            style={{
                              width: '100%',
                              boxSizing: 'border-box',
                              border: '1px solid var(--border-2)',
                              borderRadius: 10,
                              padding: '11px 14px 11px 38px',
                              background: 'var(--panel)',
                              color: 'var(--fg)',
                              fontFamily: 'inherit',
                              fontSize: 14,
                            }}
                          />
                        </div>
                        <select
                          aria-label="Filter by journey"
                          value={journeyFilter}
                          onChange={(e) => setJourneyFilter(e.target.value)}
                          style={{
                            border: '1px solid var(--border-2)',
                            borderRadius: 10,
                            padding: '11px 14px',
                            background: 'var(--panel)',
                            color: 'var(--fg)',
                            fontFamily: 'inherit',
                            fontSize: 14,
                            minWidth: 200,
                          }}
                        >
                          <option value="">All journeys</option>
                          {groups.map((g) => (
                            <option key={g.name} value={g.name}>{g.name}</option>
                          ))}
                        </select>
                      </div>

                      {detail.available.length === 0 ? (
                        <p className="caption" style={{ margin: 0, fontSize: 13 }}>
                          {canEdit ? 'No test cases in this suite yet. Use Manage test cases to add some.' : 'No test cases in this suite yet.'}
                        </p>
                      ) : visibleGroups.length === 0 ? (
                        <p className="caption" style={{ margin: 0, fontSize: 13 }}>
                          No test cases match your search.
                        </p>
                      ) : (
                        <div style={{ border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
                          {visibleGroups.map((group, index) => {
                            const open = isOpen(group.name, index)
                            return (
                              <div key={group.name} style={{ borderTop: index === 0 ? undefined : '1px solid var(--line)' }}>
                                <button
                                  type="button"
                                  aria-expanded={open}
                                  onClick={() => toggleGroup(group.name, index)}
                                  style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 14,
                                    width: '100%',
                                    padding: '14px 18px',
                                    border: 'none',
                                    background: 'var(--bg-2)',
                                    cursor: 'pointer',
                                    fontFamily: 'inherit',
                                    textAlign: 'left',
                                  }}
                                >
                                  <ChevronIcon open={open} />
                                  <span style={{ flex: 1, fontSize: 14.5, fontWeight: 600, color: 'var(--fg)' }}>{group.name}</span>
                                  <span className="caption" style={{ fontSize: 13 }}>{plural(group.cases.length, 'test case')}</span>
                                </button>
                                {open &&
                                  group.cases.map((member) => (
                                    <div
                                      key={member.scenario_id}
                                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '13px 18px 13px 50px', borderTop: '1px solid var(--line)' }}
                                    >
                                      <span style={{ fontSize: 14, color: 'var(--fg)' }}>{member.name}</span>
                                      {canEdit && (
                                        <button
                                          type="button"
                                          aria-label={`Remove ${member.name}`}
                                          aria-disabled={removing !== null}
                                          onClick={() => void removeMembers([member.scenario_id], member.scenario_id)}
                                          style={removeLink}
                                        >
                                          {removing === member.scenario_id ? <LoadingDots label="Removing" /> : 'Remove'}
                                        </button>
                                      )}
                                    </div>
                                  ))}
                              </div>
                            )
                          })}
                        </div>
                      )}

                      {detail.unavailable.length > 0 && (
                        <div
                          role="region"
                          aria-label="Unavailable test cases"
                          style={{ background: 'var(--warn-wash)', border: '1px solid var(--warn-strong)', borderRadius: 12, overflow: 'hidden' }}
                        >
                          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, padding: '16px 20px' }}>
                            <div>
                              <div style={{ fontSize: 14.5, fontWeight: 700, color: 'var(--fg)' }}>
                                {plural(detail.unavailable.length, 'test case')} no longer available
                              </div>
                              <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--fg-2)', maxWidth: 520 }}>
                                {detail.unavailable.length === 1 ? 'It no longer exists' : 'They no longer exist'} in this application and{' '}
                                {detail.unavailable.length === 1 ? 'is' : 'are'} skipped when the suite runs. Remove{' '}
                                {detail.unavailable.length === 1 ? 'it' : 'them'} to clean up.
                              </p>
                            </div>
                            {canEdit && (
                              <button
                                type="button"
                                className="button-secondary"
                                aria-disabled={removing !== null}
                                onClick={() => void removeMembers(detail.unavailable.map((m) => m.scenario_id), 'all')}
                                style={{ padding: '9px 16px', fontSize: 13.5, flex: 'none' }}
                              >
                                {removing === 'all' ? <LoadingDots label="Removing" /> : 'Remove all'}
                              </button>
                            )}
                          </div>
                          {detail.unavailable.map((member) => (
                            <div
                              key={member.scenario_id}
                              style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px', background: 'var(--panel)', borderTop: '1px solid var(--line)' }}
                            >
                              <span style={{ flex: 1, minWidth: 0, fontSize: 13.5, color: 'var(--fg-3)', textDecoration: 'line-through' }}>
                                {member.name}
                              </span>
                              <span style={{ fontSize: 11.5, fontWeight: 600, padding: '2px 10px', borderRadius: 999, background: 'var(--warn-wash)', color: 'var(--warn-strong)' }}>
                                No longer available
                              </span>
                              {canEdit && (
                                <button
                                  type="button"
                                  className="button-secondary"
                                  aria-label={`Remove ${member.name}`}
                                  aria-disabled={removing !== null}
                                  onClick={() => void removeMembers([member.scenario_id], member.scenario_id)}
                                  style={{ padding: '6px 14px', fontSize: 13, color: 'var(--danger)' }}
                                >
                                  {removing === member.scenario_id ? <LoadingDots label="Removing" /> : 'Remove'}
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )
      )}

      {dialog === 'new' && (
        <SuiteNameDialog
          title="New suite"
          submitLabel="Create suite"
          busyLabel="Creating"
          onClose={() => setDialog(null)}
          onSubmit={async (name) => {
            const created = await api.createCollection(applicationId, name)
            await loadSuites(created.id)
            setDialog('manage')
          }}
        />
      )}
      {dialog === 'rename' && selected && (
        <SuiteNameDialog
          title="Rename suite"
          initialName={selected.name}
          submitLabel="Save"
          busyLabel="Saving"
          onClose={() => setDialog(null)}
          onSubmit={async (name) => {
            await api.renameCollection(selected.id, name)
            setDialog(null)
            await refresh()
          }}
        />
      )}
      {dialog === 'delete' && selected && (
        <DeleteSuiteDialog
          suite={selected}
          onClose={() => setDialog(null)}
          onDeleted={async () => {
            setDialog(null)
            setDetail(null)
            await loadSuites()
          }}
        />
      )}
      {dialog === 'manage' && selected && (
        <SelectTestCasesDialog
          applicationId={applicationId}
          suite={{ id: selected.id, name: selected.name }}
          onClose={() => setDialog(null)}
          onSaved={async () => {
            setDialog(null)
            await refresh()
          }}
        />
      )}
    </div>
  )
}
