import { useEffect, useMemo, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faCaretRight, faMagnifyingGlass, faXmark } from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, formatTestCaseNumber, type CollectionCaseRead } from '../../../api'
import { LoadingDots } from '../../LoadingDots'
import { SkeletonRows } from '../../Skeleton'
import { SuiteModal } from './SuiteModal'

// Rows rendered at a time in the test case pane; the rest sit behind "Show
// more" (search still covers every test case). Keeps a very large application
// from putting thousands of rows in the DOM without a virtualization library.
const PAGE_SIZE = 100
const ALL = '__all_journeys__'

// Layout shared by both panes so their edges line up: headers sit 20px in,
// and the list rows sit 8px in with their own 12px padding, so a row's
// checkbox lines up with the search field above it while its rounded
// highlight reaches a little past it.
const HEADER_PADDING = '18px 20px 12px'
const LIST_PADDING = '0 8px 12px'
const ROW_PADDING = '11px 12px'
const NOTE_PADDING = '4px 20px'

type Journey = { id: string; name: string; cases: CollectionCaseRead[] }

function TriStateCheckbox({
  label,
  selected,
  total,
  onToggle,
}: {
  label: string
  selected: number
  total: number
  onToggle: () => void
}) {
  return (
    <input
      type="checkbox"
      aria-label={label}
      checked={total > 0 && selected === total}
      ref={(el) => {
        if (el) el.indeterminate = selected > 0 && selected < total
      }}
      onClick={(e) => e.stopPropagation()}
      onChange={onToggle}
      style={{ width: 18, height: 18, flex: 'none', margin: 0, cursor: 'pointer' }}
    />
  )
}

const textLink = {
  background: 'none',
  border: 'none',
  padding: 0,
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 600,
} as const

function SearchField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div style={{ position: 'relative' }}>
      <FontAwesomeIcon
        icon={faMagnifyingGlass}
        style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--accent)', fontSize: 13 }}
      />
      <input
        type="text"
        aria-label={label}
        placeholder={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          // First Esc clears the search; the dialog's Esc-to-close only sees it
          // once there is nothing left to clear.
          if (e.key === 'Escape' && value) {
            e.nativeEvent.stopPropagation()
            onChange('')
          }
        }}
        style={{
          width: '100%',
          boxSizing: 'border-box',
          border: '1px solid var(--border-2)',
          borderRadius: 10,
          padding: '10px 36px',
          background: 'var(--panel)',
          color: 'var(--fg)',
          fontFamily: 'inherit',
          fontSize: 13.5,
        }}
      />
      {value && (
        <button
          type="button"
          aria-label={`Clear ${label.toLowerCase()}`}
          onClick={() => onChange('')}
          style={{
            position: 'absolute',
            right: 12,
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--fg-3)',
          }}
        >
          <FontAwesomeIcon icon={faXmark} />
        </button>
      )}
    </div>
  )
}

const columnTitle = {
  fontSize: 11.5,
  fontWeight: 700,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--fg-2)',
} as const

// "Manage test cases": pick which of the application's test cases belong to a
// suite. Save sends only what changed, and never drops a test case that is no
// longer available (those are removed from the suite page), which is why the
// footer says they are "kept".
export function SelectTestCasesDialog({
  applicationId,
  suite,
  onClose,
  onSaved,
}: {
  applicationId: string
  suite: { id: string; name: string }
  onClose: () => void
  onSaved: () => void
}) {
  const [cases, setCases] = useState<CollectionCaseRead[] | null>(null)
  const [initial, setInitial] = useState<Set<string>>(new Set())
  const [unavailableCount, setUnavailableCount] = useState(0)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [scope, setScope] = useState<string>(ALL)
  const [journeySearch, setJourneySearch] = useState('')
  const [caseSearch, setCaseSearch] = useState('')
  const [shown, setShown] = useState(PAGE_SIZE)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.listCollectionCases(applicationId), api.getCollection(suite.id)])
      .then(([allCases, detail]) => {
        if (cancelled) return
        const members = new Set(detail.available.map((m) => m.scenario_id))
        setCases(allCases)
        setInitial(members)
        setSelected(new Set(members))
        setUnavailableCount(detail.unavailable.length)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : 'Could not load test cases.')
      })
    return () => {
      cancelled = true
    }
  }, [applicationId, suite.id])

  const journeys = useMemo<Journey[]>(() => {
    const byId = new Map<string, Journey>()
    for (const c of cases ?? []) {
      const journey = byId.get(c.journey_id) ?? { id: c.journey_id, name: c.journey_name, cases: [] }
      journey.cases.push(c)
      byId.set(c.journey_id, journey)
    }
    return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name))
  }, [cases])

  const loading = cases === null && !loadError
  const total = cases?.length ?? 0
  const journeyQuery = journeySearch.trim().toLowerCase()
  const visibleJourneys = journeyQuery
    ? journeys.filter((j) => j.name.toLowerCase().includes(journeyQuery))
    : journeys
  const activeJourney = scope === ALL ? null : journeys.find((j) => j.id === scope) ?? null

  const caseQuery = caseSearch.trim().toLowerCase()
  const scopedCases = activeJourney ? activeJourney.cases : cases ?? []
  const matchingCases = caseQuery
    ? scopedCases.filter(
        (c) =>
          c.name.toLowerCase().includes(caseQuery) ||
          formatTestCaseNumber(c.test_case_number).toLowerCase().includes(caseQuery),
      )
    : scopedCases

  const selectedIn = (list: CollectionCaseRead[]) => list.filter((c) => selected.has(c.scenario_id)).length

  function toggleMany(list: CollectionCaseRead[]) {
    const next = new Set(selected)
    const allOn = list.length > 0 && list.every((c) => next.has(c.scenario_id))
    for (const c of list) {
      if (allOn) next.delete(c.scenario_id)
      else next.add(c.scenario_id)
    }
    setSelected(next)
  }

  function toggleOne(id: string) {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
  }

  const add = [...selected].filter((id) => !initial.has(id))
  const remove = [...initial].filter((id) => !selected.has(id))

  async function save() {
    if (saving || loading) return
    if (add.length === 0 && remove.length === 0) {
      onClose()
      return
    }
    setSaving(true)
    setSaveError(null)
    try {
      await api.changeCollectionMembers(suite.id, { add, remove })
      onSaved()
    } catch {
      setSaveError('Could not save the test cases. Try again.')
      setSaving(false)
    }
  }

  function alsoIn(c: CollectionCaseRead): string | null {
    const others = c.in_collections.filter((s) => s.id !== suite.id).map((s) => s.name)
    if (others.length === 0) return null
    return others.length <= 2 ? `also in ${others.join(', ')}` : `also in ${others.slice(0, 2).join(', ')} +${others.length - 2}`
  }

  // A journey row: a rounded, inset block (no hairline between rows); the one
  // whose test cases are showing on the right is tinted.
  const rowShell = (active: boolean) =>
    ({
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: ROW_PADDING,
      borderRadius: 10,
      cursor: 'pointer',
      background: active ? 'var(--hover)' : 'transparent',
    }) as const

  const countStyle = { fontSize: 12.5, flex: 'none', fontVariantNumeric: 'tabular-nums' } as const
  const caret = <FontAwesomeIcon icon={faCaretRight} style={{ color: 'var(--fg-3)', fontSize: 14, flex: 'none' }} />
  const journeyName = { flex: 1, minWidth: 0, fontSize: 14.5, fontWeight: 600, color: 'var(--fg)' } as const

  return (
    <SuiteModal
      title="Select test cases"
      subtitle={`Suite: ${suite.name}`}
      onClose={onClose}
      maxWidth={940}
      bodyScrolls={false}
      footer={
        <>
          <span className="caption" style={{ fontSize: 13 }}>
            {loading
              ? ''
              : `${selected.size.toLocaleString()} of ${total.toLocaleString()} test case${total === 1 ? '' : 's'} selected${
                  unavailableCount > 0 ? ` · ${unavailableCount} unavailable kept` : ''
                }`}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {saveError && (
              <span role="alert" style={{ fontSize: 12.5, color: 'var(--danger)' }}>
                {saveError}
              </span>
            )}
            <button type="button" className="button-secondary" onClick={onClose} style={{ padding: '10px 22px', fontSize: 14 }}>
              Cancel
            </button>
            <button
              type="button"
              className="button-primary"
              aria-disabled={saving || loading}
              onClick={() => void save()}
              style={{ padding: '10px 22px', fontSize: 14, opacity: saving || loading ? 0.65 : 1 }}
            >
              {saving ? <LoadingDots label="Saving" /> : 'Save test cases'}
            </button>
          </div>
        </>
      }
    >
      <div style={{ display: 'flex', height: 'min(540px, 62vh)', minHeight: 0 }}>
        <div style={{ width: '45%', display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--line)', minHeight: 0 }}>
          <div style={{ padding: HEADER_PADDING, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={columnTitle}>Journey</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <button
                  type="button"
                  disabled={loading || total === 0}
                  onClick={() => setSelected(new Set((cases ?? []).map((c) => c.scenario_id)))}
                  style={{ ...textLink, color: 'var(--accent)' }}
                >
                  Select all
                </button>
                <button
                  type="button"
                  disabled={selected.size === 0}
                  onClick={() => setSelected(new Set())}
                  style={{ ...textLink, color: 'var(--fg-3)', fontWeight: 500 }}
                >
                  Clear all
                </button>
              </span>
            </div>
            <SearchField label="Search journeys" value={journeySearch} onChange={setJourneySearch} />
          </div>
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: LIST_PADDING }}>
            {loading ? (
              <div style={{ padding: '0 12px' }}>
                <SkeletonRows count={5} height={36} gap={6} />
              </div>
            ) : loadError ? (
              <p role="alert" style={{ padding: NOTE_PADDING, margin: 0, color: 'var(--danger)', fontSize: 13 }}>
                {loadError}
              </p>
            ) : total === 0 ? (
              <p className="caption" style={{ padding: NOTE_PADDING, margin: 0 }}>No test cases yet. Generate test cases first.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {!journeyQuery && (
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => { setScope(ALL); setShown(PAGE_SIZE) }}
                    onKeyDown={(e) => { if (e.key === 'Enter') { setScope(ALL); setShown(PAGE_SIZE) } }}
                    style={rowShell(scope === ALL)}
                  >
                    <TriStateCheckbox label="Select all journeys" selected={selected.size} total={total} onToggle={() => toggleMany(cases ?? [])} />
                    <span style={journeyName}>All journeys</span>
                    <span className="caption" style={countStyle}>
                      {selected.size.toLocaleString()}/{total.toLocaleString()}
                    </span>
                    {caret}
                  </div>
                )}
                {visibleJourneys.length === 0 ? (
                  <p className="caption" style={{ padding: NOTE_PADDING, margin: 0 }}>No journeys match “{journeySearch.trim()}”.</p>
                ) : (
                  visibleJourneys.map((journey) => (
                    <div
                      key={journey.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => { setScope(journey.id); setShown(PAGE_SIZE) }}
                      onKeyDown={(e) => { if (e.key === 'Enter') { setScope(journey.id); setShown(PAGE_SIZE) } }}
                      style={rowShell(scope === journey.id)}
                    >
                      <TriStateCheckbox
                        label={`Select ${journey.name}`}
                        selected={selectedIn(journey.cases)}
                        total={journey.cases.length}
                        onToggle={() => toggleMany(journey.cases)}
                      />
                      <span style={journeyName}>{journey.name}</span>
                      <span className="caption" style={countStyle}>
                        {selectedIn(journey.cases)}/{journey.cases.length}
                      </span>
                      {caret}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>
          <div style={{ padding: HEADER_PADDING, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <span style={columnTitle}>Test cases{activeJourney ? ` · ${activeJourney.name}` : ''}</span>
            <SearchField label="Search test cases" value={caseSearch} onChange={(v) => { setCaseSearch(v); setShown(PAGE_SIZE) }} />
          </div>
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: LIST_PADDING }}>
            {loading ? (
              <div style={{ padding: '0 12px' }}>
                <SkeletonRows count={6} height={36} gap={6} />
              </div>
            ) : matchingCases.length === 0 ? (
              <p className="caption" style={{ padding: NOTE_PADDING, margin: 0 }}>
                {caseQuery ? `No test cases match “${caseSearch.trim()}”.` : 'No test cases here.'}
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {matchingCases.slice(0, shown).map((c) => {
                  const on = selected.has(c.scenario_id)
                  const also = alsoIn(c)
                  return (
                    <label
                      key={c.scenario_id}
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 12,
                        padding: ROW_PADDING,
                        borderRadius: 10,
                        cursor: 'pointer',
                        background: on ? 'var(--accent-wash)' : 'transparent',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() => toggleOne(c.scenario_id)}
                        style={{ width: 18, height: 18, flex: 'none', margin: 1, cursor: 'pointer' }}
                      />
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: 'block', fontSize: 14.5, fontWeight: 500, color: 'var(--fg)', lineHeight: 1.3 }}>
                          {c.name}
                        </span>
                        <span className="caption" style={{ display: 'block', fontSize: 12.5, marginTop: 1 }}>
                          {formatTestCaseNumber(c.test_case_number)}
                          {also ? ` · ${also}` : ''}
                        </span>
                      </span>
                    </label>
                  )
                })}
                {matchingCases.length > shown && (
                  <div style={{ padding: ROW_PADDING }}>
                    <button
                      type="button"
                      onClick={() => setShown(shown + PAGE_SIZE)}
                      style={{ ...textLink, color: 'var(--accent)' }}
                    >
                      Show more ({(matchingCases.length - shown).toLocaleString()} left)
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </SuiteModal>
  )
}
