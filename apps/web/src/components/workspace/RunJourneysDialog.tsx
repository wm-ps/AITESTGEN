import { useEffect, useRef, useState } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import {
  faCircleExclamation,
  faEyeSlash,
  faMagnifyingGlass,
  faPlay,
  faXmark,
} from '@fortawesome/free-solid-svg-icons'
import { ApiError, api, formatTestCaseNumber, type TestSuiteRead } from '../../api'
import { SkeletonRows } from '../Skeleton'
import { useEscapeToClose } from '../../hooks/useEscapeToClose'
import { ChevronIcon } from './TestSuiteTab'

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

// Run Suite Flow — Run Journey(s): single-view form (no Next/Previous steps
// or nested dialogs) — reuses ScheduleDialog.tsx's overlay + card-panel
// modal shape. Selecting a Journey defaults every one of its Test Cases in;
// expanding it lets individual Test Cases be unchecked. Search only filters
// what's *shown* — selections (and Select all / Clear / Run) always cover
// every Journey, hidden ones included.
export function RunJourneysDialog({
  applicationId,
  onClose,
  onExecute,
}: {
  applicationId: string
  onClose: () => void
  onExecute: (suiteName: string, testCaseIds: string[]) => void
}) {
  useEscapeToClose(onClose)
  const [suiteName, setSuiteName] = useState('')
  const [nameError, setNameError] = useState(false)
  const [search, setSearch] = useState('')
  const [suites, setSuites] = useState<TestSuiteRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedTestCaseIds, setSelectedTestCaseIds] = useState<Set<string>>(new Set())
  const [expandedSuiteIds, setExpandedSuiteIds] = useState<Set<string>>(new Set())
  const nameInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    api
      .listTestSuites(applicationId)
      .then((data) => {
        if (!cancelled) setSuites(data)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : 'Could not load journeys.')
      })
    return () => {
      cancelled = true
    }
  }, [applicationId])

  function toggleExpanded(suiteId: string) {
    const next = new Set(expandedSuiteIds)
    if (next.has(suiteId)) next.delete(suiteId)
    else next.add(suiteId)
    setExpandedSuiteIds(next)
  }

  // Journey checkbox: off when none of its Test Cases are selected, on when
  // all are, indeterminate when some are — toggling it selects/deselects
  // every Test Case in that Journey at once.
  function toggleJourney(suite: TestSuiteRead) {
    const next = new Set(selectedTestCaseIds)
    const allSelected = suite.test_cases.every((tc) => next.has(tc.id))
    for (const tc of suite.test_cases) {
      if (allSelected) next.delete(tc.id)
      else next.add(tc.id)
    }
    setSelectedTestCaseIds(next)
  }

  function toggleTestCase(id: string) {
    const next = new Set(selectedTestCaseIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedTestCaseIds(next)
  }

  // A Journey with no Test Cases can't contribute a test_case_id, so it can
  // never run — left out of the list and every count rather than shown as an
  // unselectable row.
  const journeys = (suites ?? []).filter((s) => s.test_cases.length > 0)
  const query = search.trim().toLowerCase()
  const matching = query ? journeys.filter((s) => s.journey_name.toLowerCase().includes(query)) : journeys
  const isSelected = (s: TestSuiteRead) => s.test_cases.some((tc) => selectedTestCaseIds.has(tc.id))
  const selectedJourneyCount = journeys.filter(isSelected).length
  const hiddenSelectedCount = journeys.filter((s) => isSelected(s) && !matching.includes(s)).length
  const selectedCount = selectedTestCaseIds.size
  const loading = suites === null && !loadError
  const canExecute = selectedCount > 0

  function selectAll() {
    setSelectedTestCaseIds(new Set(journeys.flatMap((s) => s.test_cases.map((tc) => tc.id))))
  }

  function validateName() {
    const invalid = suiteName.trim().length === 0
    setNameError(invalid)
    return !invalid
  }

  function handleRun() {
    if (!validateName()) {
      nameInputRef.current?.focus()
      return
    }
    if (!canExecute) return
    onExecute(suiteName.trim(), [...selectedTestCaseIds])
  }

  const textLink = {
    background: 'none',
    border: 'none',
    padding: 0,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
  } as const

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
      <div
        role="dialog"
        aria-label="Selective Run"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--panel)',
          border: '1px solid var(--border-2)',
          borderRadius: 16,
          boxShadow: '0 30px 80px rgba(8,12,20,0.34), var(--panel-shadow)',
          width: '100%',
          maxWidth: 600,
          maxHeight: '86vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '20px 28px',
            borderBottom: '1px solid var(--line)',
          }}
        >
          <h2 style={{ fontSize: 17, fontWeight: 600, color: 'var(--fg)', margin: 0 }}>Selective Run</h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-3)', padding: 4 }}
          >
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '18px 28px', borderBottom: '1px solid var(--line)' }}>
            {loadError && (
              <div role="alert" style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 12 }}>
                {loadError}
              </div>
            )}
            <label className="field">
              <span className="label-required" style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>
                Run Name
              </span>
              <input
                ref={nameInputRef}
                required
                autoFocus
                placeholder="e.g., Regression Test"
                value={suiteName}
                aria-invalid={nameError}
                style={nameError ? { borderColor: 'var(--danger)' } : undefined}
                onChange={(e) => {
                  setSuiteName(e.target.value)
                  if (nameError && e.target.value.trim()) setNameError(false)
                }}
                onBlur={validateName}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleRun()
                }}
              />
            </label>
            {nameError ? (
              <p
                role="alert"
                style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '8px 0 0', fontSize: 12.5, color: 'var(--danger)' }}
              >
                <FontAwesomeIcon icon={faCircleExclamation} /> Enter a run name to continue
              </p>
            ) : (
              <p className="caption" style={{ fontSize: 12.5, margin: '8px 0 0' }}>
                Shown in the Test runs list so you can find this run later.
              </p>
            )}
          </div>

          <div style={{ padding: '18px 28px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--fg)' }}>Journeys</span>
                {!loading && (
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      padding: '2px 10px',
                      borderRadius: 999,
                      background: 'var(--accent-wash)',
                      color: 'var(--accent)',
                    }}
                  >
                    {selectedJourneyCount} of {journeys.length} selected
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <button
                  type="button"
                  onClick={selectAll}
                  disabled={loading || journeys.length === 0}
                  style={{ ...textLink, color: 'var(--accent)' }}
                >
                  Select all
                </button>
                <span style={{ width: 1, height: 14, background: 'var(--border-2)' }} />
                <button
                  type="button"
                  onClick={() => setSelectedTestCaseIds(new Set())}
                  disabled={selectedCount === 0}
                  style={{ ...textLink, color: 'var(--fg-3)', fontWeight: 500 }}
                >
                  Clear
                </button>
              </div>
            </div>

            <div style={{ position: 'relative' }}>
              <FontAwesomeIcon
                icon={faMagnifyingGlass}
                style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)', color: 'var(--fg-3)' }}
              />
              <input
                type="text"
                aria-label="Search journeys"
                placeholder="Search journeys"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => {
                  // First Esc clears the search; the document-level Esc-to-close
                  // listener (bubbles after React's root handler) only sees it
                  // when there's nothing left to clear.
                  if (e.key === 'Escape' && search) {
                    e.nativeEvent.stopPropagation()
                    setSearch('')
                  }
                }}
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  border: '1px solid var(--border-2)',
                  borderRadius: 999,
                  padding: '10px 40px',
                  background: 'var(--panel)',
                  color: 'var(--fg)',
                  fontFamily: 'inherit',
                  fontSize: 13.5,
                }}
              />
              {search && (
                <button
                  type="button"
                  aria-label="Clear search"
                  onClick={() => setSearch('')}
                  style={{
                    position: 'absolute',
                    right: 14,
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

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {loading ? (
                <SkeletonRows count={3} height={36} gap={6} />
              ) : journeys.length === 0 ? (
                <p className="caption">No journeys with test cases yet.</p>
              ) : matching.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '28px 0 16px' }}>
                  <FontAwesomeIcon icon={faMagnifyingGlass} size="lg" style={{ color: 'var(--fg-4)' }} />
                  <p style={{ margin: '12px 0 4px', fontSize: 14, fontWeight: 600, color: 'var(--fg)' }}>
                    No journeys match "{search.trim()}"
                  </p>
                  <p className="caption" style={{ margin: 0, fontSize: 13 }}>
                    Try a different name. Your selections are kept.
                  </p>
                </div>
              ) : (
                matching.map((suite) => {
                  const total = suite.test_cases.length
                  const selectedInSuite = suite.test_cases.filter((tc) => selectedTestCaseIds.has(tc.id)).length
                  const expanded = expandedSuiteIds.has(suite.id)
                  return (
                    <div
                      key={suite.id}
                      style={{
                        border: `1px solid ${selectedInSuite > 0 ? 'var(--accent)' : 'var(--line)'}`,
                        background: selectedInSuite > 0 ? 'var(--accent-wash)' : undefined,
                        borderRadius: 'var(--radius)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px' }}>
                        <input
                          type="checkbox"
                          aria-label={`Select ${suite.journey_name}`}
                          checked={selectedInSuite === total}
                          ref={(el) => {
                            if (el) el.indeterminate = selectedInSuite > 0 && selectedInSuite < total
                          }}
                          onChange={() => toggleJourney(suite)}
                        />
                        <span
                          style={{ flex: 1, fontSize: 14, fontWeight: 600, color: 'var(--fg)', cursor: 'pointer' }}
                          onClick={() => toggleExpanded(suite.id)}
                        >
                          {suite.journey_name}
                        </span>
                        <span className="caption" style={{ fontSize: 12, fontFamily: 'var(--font-mono, monospace)' }}>
                          {selectedInSuite}/{total} selected
                        </span>
                        <button
                          type="button"
                          aria-label={expanded ? 'Collapse' : 'Expand'}
                          aria-expanded={expanded}
                          onClick={() => toggleExpanded(suite.id)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, display: 'flex' }}
                        >
                          <ChevronIcon open={expanded} />
                        </button>
                      </div>
                      {expanded && (
                        <div
                          style={{
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 8,
                            padding: '4px 14px 12px 40px',
                          }}
                        >
                          {suite.test_cases.map((tc) => (
                            <label
                              key={tc.id}
                              style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, cursor: 'pointer' }}
                            >
                              <input
                                type="checkbox"
                                checked={selectedTestCaseIds.has(tc.id)}
                                onChange={() => toggleTestCase(tc.id)}
                              />
                              {formatTestCaseNumber(tc.test_case_number)} — {tc.name}
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })
              )}
            </div>

            {query && hiddenSelectedCount > 0 && (
              <p
                className="caption"
                style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0, fontSize: 12.5 }}
              >
                <FontAwesomeIcon icon={faEyeSlash} />
                {plural(hiddenSelectedCount, 'selected journey')} {hiddenSelectedCount === 1 ? 'is' : 'are'} hidden by
                your search
              </p>
            )}
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '16px 28px',
            background: 'var(--bg-2)',
            borderTop: '1px solid var(--line)',
          }}
        >
          <span className="caption" style={{ fontSize: 13 }}>
            {loading ? '' : `${plural(selectedCount, 'test case')} across ${plural(selectedJourneyCount, 'journey')}`}
          </span>
          <div style={{ display: 'flex', gap: 10 }}>
            <button type="button" className="button-secondary" onClick={onClose} style={{ padding: '10px 22px', fontSize: 14 }}>
              Back
            </button>
            <button
              type="button"
              className="button-primary"
              aria-disabled={!canExecute || loading}
              onClick={() => !loading && handleRun()}
              style={{
                padding: '10px 22px',
                fontSize: 14,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                opacity: canExecute && !loading ? 1 : 0.55,
                cursor: canExecute && !loading ? 'pointer' : 'not-allowed',
              }}
            >
              <FontAwesomeIcon icon={faPlay} size="xs" />
              {selectedJourneyCount === 0 ? 'Run journeys' : `Run ${plural(selectedJourneyCount, 'journey')}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
